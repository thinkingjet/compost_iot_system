"""The public figures need no key, count only bins that report, and name nothing finer than a country."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from conftest import reading
from main import db_engine
from routers import public

IDENTIFYING = {"bin_id", "device_id", "user_id", "id", "name", "location", "email", "mac"}


@pytest.fixture
def fresh():
    """Clears the public figures' one-minute cache, before and after."""
    public._cache.clear()
    yield
    public._cache.clear()


@pytest.fixture
def registered():
    device_ids = []
    yield device_ids
    with db_engine.begin() as db:
        for device_id in device_ids:
            for table in ("records", "device_apikeys", "device_bin_assn"):
                db.execute(text(f"DELETE FROM {table} WHERE device_id = :d"), {"d": device_id})
            db.execute(text("DELETE FROM devices WHERE id = :d"), {"d": device_id})


def _figures(client):
    stats = client.get("/public/stats")
    countries = client.get("/public/bins-by-country")
    assert stats.status_code == countries.status_code == 200
    return stats.json(), {row["country_code"]: row["bins"] for row in countries.json()}


def _bin(client, account, country_code):
    response = client.post("/bins", headers=account["headers"],
                           json={"name": "Public test bin", "location": "Private", "country_code": country_code})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_public_figures_count_reporting_bins_by_country(client, account, registered, fresh):
    stats_before, countries_before = _figures(client)

    reporting = _bin(client, account, "zx")
    _bin(client, account, "zx")  # never reports, so it isn't counted
    response = client.post("/devices", headers=account["headers"], json={"name": "Public test sensor", "bin_id": reporting})
    registered.append(response.json()["device"]["id"])
    batch = [reading(timestamp="2000-01-01T00:00:00+00:00"), reading(timestamp="2000-01-01T00:30:00+00:00")]
    assert client.post("/records", json=batch, headers={"x-key": response.json()["api_key"]}).status_code == 200

    # cached: the same answer until the minute is up
    assert _figures(client) == (stats_before, countries_before)
    public._cache.clear()
    stats, countries = _figures(client)

    assert stats["bins"] == stats_before["bins"] + 1
    assert stats["countries"] == stats_before["countries"] + ("ZX" not in countries_before)
    assert stats["readings_total"] == stats_before["readings_total"] + 2
    # just uploaded, so it's online
    assert stats["active_devices"] == stats_before["active_devices"] + 1
    assert datetime.fromisoformat(stats["first_reading_at"]) <= datetime(2000, 1, 1, tzinfo=timezone.utc)
    assert countries["ZX"] == countries_before.get("ZX", 0) + 1
    assert not IDENTIFYING & stats.keys()
    assert all(row.keys() == {"country_code", "bins"} for row in client.get("/public/bins-by-country").json())


def test_trends_cover_the_last_30_days_with_gaps_as_nulls(client, account, fresh):
    bin_id = _bin(client, account, "zx")
    now = datetime.now(timezone.utc)
    with db_engine.begin() as db:
        # removed with the test account's bin
        db.execute(text("""
            INSERT INTO records (device_id, bin_id, timestamp, temperature, moisture_percent, o2_percent, co2_percent, nh3_ratio)
            VALUES ('00000000-0000-4000-8000-000000000201', :bin_id, :at, 60, 50, 12, 6, 0.5)
        """), {"bin_id": bin_id, "at": now - timedelta(minutes=1)})

    days = client.get("/public/trends").json()["days"]
    assert len(days) == public.TREND_DAYS
    assert days[-1]["date"] == now.date().isoformat()
    by_date = {day["date"]: day for day in days}
    assert by_date[(now - timedelta(minutes=1)).date().isoformat()]["temperature_c"] is not None
    assert all(day.keys() == {"date", "temperature_c", "moisture_percent"} for day in days)
    dates = [day["date"] for day in days]
    assert dates == sorted(dates) and len(set(dates)) == len(dates)
