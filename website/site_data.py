"""Where the website's numbers come from.

Two sources give the same shape of data:

* `ApiSource` reads the public endpoints of the CompostIQ API. Production
  builds use it (`build.py --api-url ...`). If the API can't be reached the
  build fails, and the site that is already published stays as it was.
* `MockSource` reads mock-data/compostiq_mock_readings.csv, so the site can be
  built and previewed before those endpoints exist. Pages built from it say
  that their figures are a preview.

Readings are anonymised here as well as in the API, so a preview build can
never publish a site, bin or device identifier from the mock data.
"""
import csv
import datetime
import hashlib
import json
import statistics
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MOCK_CSV = REPO / "mock-data" / "compostiq_mock_readings.csv"

# The columns of an anonymised reading, in order: the bulk files, the API and
# the data dictionary on the open data page all use these.
READING_FIELDS = [
    "bin_ref", "country", "method", "recorded_at",
    "temperature_c", "moisture_pct", "oxygen_pct", "co2_pct",
    "nh3_relative", "mq135_composite_ppm", "stage_id", "stage_name", "faults",
]

TREND_DAYS = 30
HTTP_TIMEOUT_SECONDS = 30
PAGE_LIMIT = 5000

# The mock data names sites, not countries. Both pilot sites are on Lombok.
_MOCK_SITE_COUNTRY = {"site-unram-pilot": "ID", "site-smk-lombok-01": "ID"}
_COUNTRY_NAMES = {"ID": "Indonesia"}


@dataclass
class SiteData:
    preview: bool
    stats: dict        # bins, countries, active_devices, readings_24h, updated_at (datetime)
    countries: list    # [{"code", "name", "bins"}], most bins first
    trend: list        # [{"date": date, "temperature_c": float, "moisture_pct": float | None}]
    readings: list     # anonymised rows keyed by READING_FIELDS, oldest first


def _parse_time(text):
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


def _number(text):
    return float(text) if text not in ("", None) else None


def bin_ref(bin_id, salt):
    """A stable, random-looking reference for a bin that can't be reversed."""
    return "b_" + hashlib.sha256(f"{salt}:{bin_id}".encode()).hexdigest()[:6]


class MockSource:
    """The simulated pilot dataset in mock-data/."""

    preview = True

    def __init__(self, path=MOCK_CSV, salt="compostiq-preview"):
        with open(path, newline="") as f:
            self.rows = list(csv.DictReader(f))
        self.salt = salt

    def load(self):
        rows = self.rows
        latest = max(_parse_time(r["recorded_at"]) for r in rows)
        bins_by_country = Counter()
        for bin_id in {r["bin_id"] for r in rows}:
            site = next(r["site_id"] for r in rows if r["bin_id"] == bin_id)
            bins_by_country[_MOCK_SITE_COUNTRY[site]] += 1

        stats = {
            "bins": len({r["bin_id"] for r in rows}),
            "countries": len(bins_by_country),
            "active_devices": len({r["device_id"] for r in rows}),
            "readings_24h": sum(1 for r in rows if _parse_time(r["recorded_at"]) > latest - datetime.timedelta(hours=24)),
            "updated_at": latest,
        }
        countries = [
            {"code": code, "name": _COUNTRY_NAMES.get(code, code), "bins": n}
            for code, n in bins_by_country.most_common()
        ]

        # Daily means across every bin. The preview shows the dataset's first
        # 30 days, which cover a whole heat-up and cool-down; the live site
        # shows the latest 30.
        by_day = defaultdict(lambda: {"t": [], "m": []})
        for r in rows:
            day = by_day[_parse_time(r["recorded_at"]).date()]
            day["t"].append(float(r["temperature_c"]))
            if r["moisture_pct"]:
                day["m"].append(float(r["moisture_pct"]))
        trend = [
            {
                "date": day,
                "temperature_c": statistics.fmean(v["t"]),
                "moisture_pct": statistics.fmean(v["m"]) if v["m"] else None,
            }
            for day, v in sorted(by_day.items())
        ][:TREND_DAYS]

        readings = [self._anonymise(r) for r in sorted(rows, key=lambda r: r["recorded_at"])]
        return SiteData(preview=True, stats=stats, countries=countries, trend=trend, readings=readings)

    def _anonymise(self, r):
        return {
            "bin_ref": bin_ref(r["bin_id"], self.salt),
            "country": _MOCK_SITE_COUNTRY[r["site_id"]],
            "method": r["method"],
            "recorded_at": r["recorded_at"],
            "temperature_c": _number(r["temperature_c"]),
            "moisture_pct": _number(r["moisture_pct"]),
            "oxygen_pct": _number(r["oxygen_pct"]),
            "co2_pct": _number(r["co2_pct"]),
            "nh3_relative": _number(r["nh3_relative"]),
            "mq135_composite_ppm": _number(r["mq135_composite_ppm"]),
            "stage_id": int(r["stage_id"]),
            "stage_name": r["stage_name"],
            "faults": [code for code in r["fault_codes"].split(";") if code],
        }

    def bin_card_sample(self, bin_id="bin-unram-takakura-01", count=40):
        """Readings for the illustrated bin card on the home page."""
        rows = [r for r in self.rows if r["bin_id"] == bin_id][:count]
        return rows


class ApiSource:
    """The public endpoints of a running CompostIQ API."""

    preview = False

    def __init__(self, api_url):
        self.api_url = api_url.rstrip("/")

    def _get(self, path, **params):
        query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        url = f"{self.api_url}{path}" + (f"?{query}" if query else "")
        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "compostiq-website-build"})
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return json.load(response)

    def load(self):
        stats = self._get("/public/stats")
        stats["updated_at"] = _parse_time(stats["updated_at"])

        countries = [
            {"code": c["country"], "name": c.get("name") or _COUNTRY_NAMES.get(c["country"], c["country"]), "bins": c["bins"]}
            for c in self._get("/public/bins-by-country")
        ]
        countries.sort(key=lambda c: c["bins"], reverse=True)

        trends = self._get("/public/trends")
        days = trends["days"] if isinstance(trends, dict) else trends
        trend = [
            {"date": datetime.date.fromisoformat(d["date"]), "temperature_c": d["temperature_c"], "moisture_pct": d.get("moisture_pct")}
            for d in days
        ][-TREND_DAYS:]

        readings, cursor = [], None
        while True:
            page = self._get("/research/readings", limit=PAGE_LIMIT, cursor=cursor)
            readings += [{field: item.get(field) for field in READING_FIELDS} for item in page["items"]]
            cursor = page.get("next_cursor")
            if not cursor:
                break
        return SiteData(preview=False, stats=stats, countries=countries, trend=trend, readings=readings)


def load(api_url=None):
    return (ApiSource(api_url) if api_url else MockSource()).load()
