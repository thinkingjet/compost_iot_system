"""
Public figures for the website (compostiq.win): totals across every bin, bins
per country, and 30 days of daily averages. No key and no sign-in.

Like /research, nothing that identifies an owner, bin or device is returned,
and a country is the finest place given. The website asks for these through
NGINX (compostiq.win/api/public/... goes to /public/...), so they stay on its
own origin.
"""
import datetime
import time
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from database import db_engine
from routers.alerts import OFFLINE_AFTER

router = APIRouter(prefix="/public", tags=["public"])

# anyone can call these, so each answer is kept for a minute instead of
# counting every reading on every page view
CACHE_SECONDS = 60
TREND_DAYS = 30
_cache = {}


class Stats(BaseModel):
    # bins that have sent at least one reading
    bins: int
    # countries those bins are in; bins without a country aren't counted
    countries: int
    # devices in a bin that were heard from in the last 10 minutes, the same
    # window as the offline alert
    active_devices: int
    readings_total: int
    readings_24h: int
    first_reading_at: datetime.datetime | None
    last_reading_at: datetime.datetime | None
    updated_at: datetime.datetime


class CountryBins(BaseModel):
    country_code: str
    bins: int


class TrendDay(BaseModel):
    date: datetime.date
    # None on a day without readings
    temperature_c: float | None
    moisture_percent: float | None


class Trends(BaseModel):
    days: list[TrendDay]


def _cached(name, compute):
    hit = _cache.get(name)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    value = compute()
    _cache[name] = (time.monotonic() + CACHE_SECONDS, value)
    return value


# bins that have reported, so a bin created and never used isn't counted
REPORTING_BINS = "SELECT DISTINCT bin_id FROM records"


def _stats():
    with db_engine.connect() as db:
        row = db.execute(text(f"""
            SELECT
                (SELECT count(*) FROM ({REPORTING_BINS}) b) AS bins,
                (SELECT count(DISTINCT country_code) FROM bins WHERE id IN ({REPORTING_BINS})) AS countries,
                (SELECT count(*) FROM devices d
                 JOIN device_bin_assn a ON a.device_id = d.id AND a.unassigned_at IS NULL
                 WHERE d.is_active AND d.last_seen_at >= now() - :offline_after) AS active_devices,
                count(*) AS readings_total,
                count(*) FILTER (WHERE timestamp >= now() - interval '24 hours') AS readings_24h,
                min(timestamp) AS first_reading_at,
                max(timestamp) AS last_reading_at,
                now() AS updated_at
            FROM records
        """), {"offline_after": OFFLINE_AFTER}).mappings().one()
    return Stats(**row)


def _bins_by_country():
    with db_engine.connect() as db:
        rows = db.execute(text(f"""
            SELECT country_code, count(*) AS bins FROM bins
            WHERE country_code IS NOT NULL AND id IN ({REPORTING_BINS})
            GROUP BY country_code ORDER BY bins DESC, country_code
        """)).mappings().all()
    return [CountryBins(**row) for row in rows]


def _trends():
    # every UTC day of the last 30, today included, so a day without readings
    # is there with nulls and the website's chart shows a gap
    with db_engine.connect() as db:
        rows = db.execute(text("""
            SELECT d.day::date AS date,
                   round(avg(r.temperature)::numeric, 2) AS temperature_c,
                   round(avg(r.moisture_percent)::numeric, 2) AS moisture_percent
            FROM generate_series(date_trunc('day', now() AT TIME ZONE 'UTC') - make_interval(days => :days - 1),
                                 date_trunc('day', now() AT TIME ZONE 'UTC'), interval '1 day') AS d(day)
            LEFT JOIN records r ON r.timestamp >= d.day AT TIME ZONE 'UTC'
                               AND r.timestamp < (d.day + interval '1 day') AT TIME ZONE 'UTC'
            GROUP BY d.day ORDER BY d.day
        """), {"days": TREND_DAYS}).mappings().all()
    return Trends(days=[
        TrendDay(**{key: float(value) if isinstance(value, Decimal) else value for key, value in row.items()})
        for row in rows
    ])


@router.get("/stats", response_model=Stats)
def stats():
    """Totals across every bin: bins, countries, devices online, readings."""
    return _cached("stats", _stats)


@router.get("/bins-by-country", response_model=list[CountryBins])
def bins_by_country():
    """How many bins have reported from each country."""
    return _cached("bins-by-country", _bins_by_country)


@router.get("/trends", response_model=Trends)
def trends():
    """The daily average temperature and moisture across every bin, for the last 30 UTC days."""
    return _cached("trends", _trends)
