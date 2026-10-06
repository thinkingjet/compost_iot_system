"""Build the CompostIQ public website into a folder of static files.

    python website/build.py                                  # preview, from mock-data/
    python website/build.py --api-url http://127.0.0.1:8000 \\
                            --out /var/www/compostiq         # production

The output is plain HTML, one stylesheet, one small optional script and the
bulk download files. Charts are drawn here as inline SVG (charts.py), so no
page needs a chart library. The new build replaces the old one with a rename,
so a build that fails leaves the published site as it was.
"""
import argparse
import csv
import datetime
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

import charts
import site_data
from icons import icon

HERE = Path(__file__).resolve().parent
DEFAULT_OUT = HERE / "dist"

# (template, output file, URL path, nav section, <title>, meta description)
PAGES = [
    ("index.html", "index.html", "/", "home",
     "CompostIQ: better compost, backed by data",
     "A sensor in your compost bin, a dashboard that tells you when to turn, water or wait, and open data for researchers."),
    ("open-data.html", "open-data/index.html", "/open-data/", "open-data",
     "Open compost data for research · CompostIQ",
     "Anonymised hourly readings from working compost bins, labelled by composting phase. Free to use, no sign-up."),
    ("docs/quickstart.html", "docs/index.html", "/docs/", "docs",
     "Quickstart · CompostIQ docs",
     "Make your first request to the CompostIQ open API in about five minutes. No account or key needed."),
    ("docs/api.html", "docs/api/index.html", "/docs/api/", "docs",
     "List readings · CompostIQ API reference",
     "GET /research/readings: anonymised compost readings, one row per bin per hour, with filters and cursor paging."),
    ("docs/security.html", "docs/security/index.html", "/docs/security/", "docs",
     "Pairing & security · CompostIQ docs",
     "How a device joins your account, the safeguards on pairing codes and device keys, and what to do if one is exposed."),
    ("404.html", "404.html", "/404.html", None,
     "Page not found · CompostIQ",
     "That page doesn't exist."),
]

NAV = [
    {"key": "how", "label": "How it works", "href": "/#how"},
    {"key": "open-data", "label": "Open data", "href": "/open-data/"},
    {"key": "docs", "label": "Docs", "href": "/docs/"},
]


def docs_nav(public_api_url):
    return [
        {"title": "Get started", "links": [
            {"key": "quickstart", "label": "Quickstart", "href": "/docs/"},
            {"label": "Data dictionary", "href": "/open-data/#fields"},
            {"label": "Rate limits & errors", "href": "/docs/api/#errors"},
        ]},
        {"title": "Public statistics", "links": [
            {"verb": "GET", "label": "/public/stats", "href": "/docs/api/#public-stats"},
            {"verb": "GET", "label": "/public/bins-by-country", "href": "/docs/api/#public-bins-by-country"},
            {"verb": "GET", "label": "/public/trends", "href": "/docs/api/#public-trends"},
        ]},
        {"title": "Research data", "links": [
            {"key": "readings", "verb": "GET", "label": "/research/readings", "href": "/docs/api/"},
            {"verb": "GET", "label": "/research/bins", "href": "/docs/api/#research-bins"},
            {"verb": "GET", "label": "/research/stages", "href": "/docs/api/#research-stages"},
        ]},
        {"title": "Devices & accounts", "links": [
            {"key": "security", "label": "Pairing & security", "href": "/docs/security/"},
        ]},
        {"title": "Resources", "links": [
            {"label": "Bulk downloads", "href": "/open-data/#downloads"},
            {"label": "OpenAPI spec (JSON)", "href": f"{public_api_url}/openapi.json"},
            {"label": "Changelog", "href": "/docs/api/#changelog"},
        ]},
    ]


def human_size(n_bytes):
    for unit in ("bytes", "KB", "MB", "GB"):
        if n_bytes < 1024 or unit == "GB":
            return f"{n_bytes:.0f} {unit}" if unit == "bytes" else f"{n_bytes:.1f} {unit}"
        n_bytes /= 1024


def date_range(first, last):
    if first.year == last.year:
        return f"{first.day} {first:%b} – {last.day} {last:%b} {last.year}"
    return f"{first.day} {first:%b} {first.year} – {last.day} {last:%b} {last.year}"


def write_downloads(out, readings):
    """The bulk files: the same anonymised rows as GET /research/readings."""
    folder = out / "downloads"
    folder.mkdir(parents=True)
    csv_path, json_path = folder / "compostiq-readings.csv", folder / "compostiq-readings.json"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=site_data.READING_FIELDS)
        writer.writeheader()
        for row in readings:
            writer.writerow({**row, "faults": ";".join(row["faults"] or [])})
    with open(json_path, "w") as f:
        json.dump({"fields": site_data.READING_FIELDS, "items": readings}, f, separators=(",", ":"))
    return {
        "csv": {"href": "/downloads/compostiq-readings.csv", "name": csv_path.name, "size": human_size(csv_path.stat().st_size)},
        "json": {"href": "/downloads/compostiq-readings.json", "name": json_path.name, "size": human_size(json_path.stat().st_size)},
    }


def dataset_summary(readings):
    times = [site_data._parse_time(r["recorded_at"]) for r in readings]
    return {
        "bins": len({r["bin_ref"] for r in readings}),
        "countries": len({r["country"] for r in readings}),
        "methods": len({r["method"] for r in readings}),
        "readings": len(readings),
        "period": date_range(min(times).date(), max(times).date()) if times else "No readings yet",
    }


def trend_charts(trend):
    if len(trend) < 2:
        return None  # the page says there isn't enough data yet
    days = [d["date"] for d in trend]
    temps = [d["temperature_c"] for d in trend]
    moist = [d["moisture_pct"] for d in trend]
    span = f"{days[0].day} {days[0]:%B} to {days[-1].day} {days[-1]:%B}"
    known_moist = [m for m in moist if m is not None]
    temp_svg = charts.line_chart(
        days, temps, series="temp", unit="°", point_unit="°C",
        y_min=20, y_max=70, y_ticks=[30, 50, 70], threshold=(55, "55 °C pathogen kill"),
        label=f"Daily mean temperature, {span}. It ranges from {min(temps):.0f} to {max(temps):.0f} °C.",
    )
    moist_svg = charts.line_chart(
        days, moist, series="moist", unit="%", point_unit="%",
        y_min=30, y_max=70, y_ticks=[40, 55, 70], band=(40, 65, "Target 40–65 %"),
        label=f"Daily mean moisture, {span}. It ranges from {min(known_moist):.0f} to {max(known_moist):.0f} %, against a 40 to 65 % target.",
    )
    return {"temperature": temp_svg, "moisture": moist_svg, "range": date_range(days[0], days[-1])}


def bin_card():
    """The illustrated dashboard card in the home page hero.

    It always uses the mock data: it shows what the dashboard looks like, not
    anyone's real bin.
    """
    rows = site_data.MockSource().bin_card_sample()
    last = rows[-1]
    first_day = site_data._parse_time(rows[0]["recorded_at"]).date()
    last_day = site_data._parse_time(last["recorded_at"]).date()
    temps = [float(r["temperature_c"]) for r in rows]
    return {
        "method": last["method"].replace("_", " ").title(),
        "stage": last["stage_name"].capitalize(),
        "day": (last_day - first_day).days + 1,
        "temperature": float(last["temperature_c"]),
        "moisture": float(last["moisture_pct"]),
        "oxygen": float(last["oxygen_pct"]),
        "co2": float(last["co2_pct"]),
        "spark": charts.sparkline(temps, y_min=25, y_max=70, reference=55),
    }


def _asset_version():
    digest = hashlib.sha256()
    for path in sorted((HERE / "assets").iterdir()):
        digest.update(path.read_bytes())
    return digest.hexdigest()[:10]


def _publish(staging, out):
    """Swap the finished build into place."""
    old = out.with_name(out.name + ".old")
    if old.exists():
        shutil.rmtree(old)
    if out.exists():
        out.rename(old)
    staging.rename(out)
    if old.exists():
        shutil.rmtree(old)


def build(out=DEFAULT_OUT, api_url=None, site_url="https://compostiq.win",
          dashboard_url="https://dashboard.compostiq.win", public_api_url="https://api.compostiq.win"):
    out = Path(out).resolve()
    data = site_data.load(api_url)

    out.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{out.name}-", dir=out.parent))
    try:
        staging.chmod(0o755)  # mkdtemp makes it private; NGINX must be able to read it
        shutil.copytree(HERE / "assets", staging / "assets")
        downloads = write_downloads(staging, data.readings)

        env = Environment(
            loader=FileSystemLoader(HERE / "templates"),
            autoescape=select_autoescape(["html", "xml"]),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        env.globals.update(
            icon=icon,
            site_url=site_url.rstrip("/"),
            dashboard_url=dashboard_url.rstrip("/"),
            public_api_url=public_api_url.rstrip("/"),
            nav=NAV,
            docs_nav=docs_nav(public_api_url.rstrip("/")),
            asset_version=_asset_version(),
            year=datetime.date.today().year,
        )
        updated = data.stats["updated_at"]
        most_bins = max((c["bins"] for c in data.countries), default=1)
        context = {
            "preview": data.preview,
            "stats": data.stats,
            "updated_label": f"{updated.day} {updated:%b %Y, %H:%M} UTC",
            "countries": [{**c, "bar": charts.bar(c["bins"] / most_bins)} for c in data.countries],
            "charts": trend_charts(data.trend),
            "dataset": dataset_summary(data.readings),
            "downloads": downloads,
            "bin_card": bin_card(),
            # A real reference from this build, so the docs' examples match the downloads.
            "example_ref": next((r["bin_ref"] for r in data.readings if r["method"] == "takakura"), "b_7f3a91"),
        }
        for template, filename, path, section, title, description in PAGES:
            html = env.get_template(template).render(
                path=path, section=section, page_title=title, description=description, **context
            )
            target = staging / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(html)

        urls = "".join(
            f"<url><loc>{site_url.rstrip('/')}{path}</loc></url>" for _, _, path, _, _, _ in PAGES if path != "/404.html"
        )
        (staging / "sitemap.xml").write_text(
            f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'
        )
        (staging / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {site_url.rstrip('/')}/sitemap.xml\n")

        for folder, _, _ in os.walk(staging):
            os.chmod(folder, 0o755)
        _publish(staging, out)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=os.environ.get("WEBSITE_OUT", DEFAULT_OUT),
                        help="folder to write the site to (default: website/dist)")
    parser.add_argument("--api-url", default=os.environ.get("WEBSITE_API_URL"),
                        help="CompostIQ API to read live figures from; without it the mock data is used")
    parser.add_argument("--site-url", default=os.environ.get("SITE_URL", "https://compostiq.win"))
    parser.add_argument("--dashboard-url", default=os.environ.get("DASHBOARD_URL", "https://dashboard.compostiq.win"))
    parser.add_argument("--public-api-url", default=os.environ.get("PUBLIC_API_URL", "https://api.compostiq.win"),
                        help="the API address shown to readers in the docs")
    args = parser.parse_args(argv)

    data = build(args.out, args.api_url, args.site_url, args.dashboard_url, args.public_api_url)
    source = f"API at {args.api_url}" if args.api_url else "mock data (preview)"
    print(f"Built {Path(args.out).resolve()} from {source}: {len(data.readings)} readings.")


if __name__ == "__main__":
    sys.exit(main())
