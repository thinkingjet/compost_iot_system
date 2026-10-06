"""Build the site from the mock data and check what comes out.

Run from the repo root:  .venv/bin/pytest website/tests
"""
import datetime
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build  # noqa: E402
import charts  # noqa: E402
import site_data  # noqa: E402

PAGES = [
    "index.html",
    "open-data/index.html",
    "docs/index.html",
    "docs/api/index.html",
    "docs/security/index.html",
    "404.html",
]

# Identifiers in the mock data that must never reach a published file.
MOCK_IDENTIFIERS = ["site-unram", "site-smk", "bin-unram", "bin-smk", "cmpiq-", "rdg-", "batch-"]


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.links, self.style_attrs, self.inline_scripts = set(), [], 0, 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if "style" in attrs:
            self.style_attrs += 1
        if tag == "script" and "src" not in attrs:
            self.inline_scripts += 1
        for name in ("href", "src"):
            if attrs.get(name):
                self.links.append(attrs[name])


def _parse(path):
    page = _Page()
    page.feed(path.read_text())
    return page


def _file_for(site, url_path):
    target = site / url_path.lstrip("/")
    return target / "index.html" if url_path.endswith("/") else target


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("site") / "dist"
    build.build(out)
    return out


def test_every_page_is_built(site):
    for page in PAGES:
        assert (site / page).is_file(), page
    assert (site / "sitemap.xml").is_file()
    assert (site / "robots.txt").is_file()


def test_pages_work_under_a_strict_content_security_policy(site):
    # The NGINX config sends a CSP without 'unsafe-inline', so any style=""
    # attribute or inline <script> would be blocked in production.
    for page in PAGES:
        parsed = _parse(site / page)
        assert parsed.style_attrs == 0, f"{page} has style attributes"
        assert parsed.inline_scripts == 0, f"{page} has an inline script"


def test_internal_links_and_anchors_resolve(site):
    ids = {page: _parse(site / page).ids for page in PAGES}
    for page in PAGES:
        for link in _parse(site / page).links:
            parts = urlsplit(link)
            if parts.scheme or link.startswith("//") or link.startswith("mailto:"):
                continue
            if not parts.path:  # "#section" on the same page
                assert parts.fragment in ids[page], f"{page}: {link}"
                continue
            target = _file_for(site, parts.path)
            assert target.is_file(), f"{page}: {link}"
            if parts.fragment:
                assert parts.fragment in ids[str(target.relative_to(site))], f"{page}: {link}"


def test_downloads_are_anonymised(site):
    csv_text = (site / "downloads" / "compostiq-readings.csv").read_text()
    json_text = (site / "downloads" / "compostiq-readings.json").read_text()
    assert csv_text.splitlines()[0].split(",") == site_data.READING_FIELDS
    assert json.loads(json_text)["fields"] == site_data.READING_FIELDS
    for identifier in MOCK_IDENTIFIERS:
        assert identifier not in csv_text
        assert identifier not in json_text
    for page in PAGES:
        html = (site / page).read_text()
        for identifier in MOCK_IDENTIFIERS:
            assert identifier not in html, f"{identifier} in {page}"


def test_a_preview_build_says_so(site):
    assert "simulated pilot dataset" in (site / "index.html").read_text()
    assert "simulated pilot dataset" in (site / "open-data" / "index.html").read_text()


def test_a_rebuild_replaces_the_old_site(tmp_path):
    out = tmp_path / "dist"
    build.build(out)
    (out / "stale.html").write_text("left over")
    build.build(out)
    assert not (out / "stale.html").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dist"]


def test_a_failed_build_keeps_the_published_site(tmp_path, monkeypatch):
    out = tmp_path / "dist"
    build.build(out)
    published = (out / "index.html").read_text()

    def fail(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(build, "write_downloads", fail)
    with pytest.raises(RuntimeError):
        build.build(out)
    assert (out / "index.html").read_text() == published
    assert sorted(p.name for p in tmp_path.iterdir()) == ["dist"]


def test_a_missing_day_breaks_the_line():
    days = [datetime.date(2026, 8, d) for d in range(1, 6)]
    svg = charts.line_chart(
        days, [30, 31, None, 33, 34], series="temp", unit="°", point_unit="°C",
        y_min=20, y_max=70, y_ticks=[30, 50, 70], label="test",
    )
    assert svg.count("<polyline") == 2
    assert svg.count("<circle") == 4
