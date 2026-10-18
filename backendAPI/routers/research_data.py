"""Read-only country aggregates for researcher accounts.

No owner, bin, device, location, or individual reading is returned.
"""
import csv
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import text

from database import db_engine
from routers.auth import require_role
from routers.research_keys import research_key

router = APIRouter(prefix="/research", tags=["research data"])


class Window(BaseModel):
    start: datetime
    end: datetime
    country_code: str | None = None


def window(
    start: datetime | None = None,
    end: datetime | None = None,
    country_code: Annotated[str | None, Query(pattern=r"^[A-Za-z]{2}$")] = None,
) -> Window:
    end = end or datetime.now(timezone.utc)
    start = start or end - timedelta(days=30)
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(422, "start and end must include a timezone")
    if start >= end or end - start > timedelta(days=366):
        raise HTTPException(422, "Choose a time window of up to 366 days, with start before end")
    return Window(start=start, end=end, country_code=country_code.upper() if country_code else None)


# column -> sensor; each gets its average, min, max and standard deviation
SENSORS = {"temperature_c": "temperature", "moisture_percent": "moisture_percent",
           "o2_percent": "o2_percent", "co2_percent": "co2_percent", "nh3_ratio": "nh3_ratio"}
FILTER = """b.country_code IS NOT NULL AND (:country_code IS NULL OR b.country_code = :country_code)"""


def _rows(sql, params=None):
    with db_engine.connect() as db:
        rows = db.execute(text(sql), params or {}).mappings().all()
    # numeric (Decimal) -> float, so JSON and CSV get plain numbers
    return [{key: float(value) if isinstance(value, Decimal) else value for key, value in row.items()} for row in rows]


def _readings(w: Window, daily: bool):
    day = "date_trunc('day', r.timestamp AT TIME ZONE 'UTC') AS day," if daily else ""
    stats = ",".join(
        f"round(avg(r.{col})::numeric, 3) AS {name}, round(min(r.{col})::numeric, 3) AS {name}_min,"
        f"round(max(r.{col})::numeric, 3) AS {name}_max, round(stddev_samp(r.{col})::numeric, 3) AS {name}_sd"
        for name, col in SENSORS.items()
    )
    return _rows(f"""
        SELECT b.country_code, {day} count(DISTINCT r.bin_id) AS bin_count, count(*) AS reading_count, {stats}
        FROM records r JOIN bins b ON b.id = r.bin_id
        WHERE r.timestamp >= :start AND r.timestamp < :end AND {FILTER}
        GROUP BY b.country_code {", day" if daily else ""}
        ORDER BY b.country_code {", day" if daily else ""}
    """, w.model_dump())


def _alerts(w: Window):
    # offline alerts aren't stored, so they aren't counted
    return _rows(f"""
        SELECT b.country_code, e.type, count(*) AS alert_count, count(DISTINCT e.bin_id) AS bin_count,
               round(avg(extract(epoch FROM e.resolved_at - e.triggered_at) / 3600)::numeric, 2) AS avg_hours_to_resolve
        FROM bin_events e JOIN bins b ON b.id = e.bin_id
        WHERE e.triggered_at >= :start AND e.triggered_at < :end AND {FILTER}
        GROUP BY b.country_code, e.type
        ORDER BY b.country_code, e.type
    """, w.model_dump())


def _countries():
    return _rows("""
        SELECT b.country_code, count(DISTINCT r.bin_id) AS bin_count, count(*) AS reading_count,
               min(r.timestamp) AS first_reading, max(r.timestamp) AS last_reading
        FROM records r JOIN bins b ON b.id = r.bin_id
        WHERE b.country_code IS NOT NULL
        GROUP BY b.country_code ORDER BY b.country_code
    """)


def _result(w: Window, rows, format):
    if format == "csv":
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=list(rows[0]) if rows else [])
        writer.writeheader()
        writer.writerows(rows)
        return Response(out.getvalue(), media_type="text/csv")
    return {"start": w.start, "end": w.end, "country_code": w.country_code, "data": rows}


Format = Annotated[Literal["json", "csv"], Query()]


@router.get("/overview", dependencies=[Depends(research_key)])
def overview(w: Window = Depends(window), format: Format = "json"):
    """Country aggregates for a time window. Send x-research-key."""
    return _result(w, _readings(w, False), format)


@router.get("/daily", dependencies=[Depends(research_key)])
def daily(w: Window = Depends(window), format: Format = "json"):
    """Daily country aggregates for a time window. Send x-research-key."""
    return _result(w, _readings(w, True), format)


@router.get("/alerts", dependencies=[Depends(research_key)])
def alerts(w: Window = Depends(window), format: Format = "json"):
    """How often each alert type happened per country, and how long it lasted. Send x-research-key."""
    return _result(w, _alerts(w), format)


@router.get("/countries", dependencies=[Depends(research_key)])
def countries():
    """Which countries have data: bins, readings and the date range. Send x-research-key."""
    return _countries()


# the same, for the signed-in research dashboard (Bearer token instead of a key)

@router.get("/preview/overview")
def preview_overview(w: Window = Depends(window), _user=Depends(require_role("researcher"))):
    return _result(w, _readings(w, False), "json")


@router.get("/preview/daily")
def preview_daily(w: Window = Depends(window), _user=Depends(require_role("researcher"))):
    return _result(w, _readings(w, True), "json")


@router.get("/preview/alerts")
def preview_alerts(w: Window = Depends(window), _user=Depends(require_role("researcher"))):
    return _result(w, _alerts(w), "json")


@router.get("/preview/countries")
def preview_countries(_user=Depends(require_role("researcher"))):
    return _countries()
