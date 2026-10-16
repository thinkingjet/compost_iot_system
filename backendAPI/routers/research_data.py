"""Read-only country aggregates for researcher accounts.

No owner, bin, device, location, or individual reading is returned.
"""
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
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


def _aggregate(w: Window, daily: bool):
    period = "date_trunc('day', r.timestamp AT TIME ZONE 'UTC')" if daily else "NULL"
    sql = text(f"""
        SELECT b.country_code, {period} AS day,
               count(DISTINCT r.bin_id) AS bin_count,
               count(*) AS reading_count,
               round(avg(r.temperature)::numeric, 2) AS temperature_c,
               round(avg(r.moisture_percent)::numeric, 2) AS moisture_percent,
               round(avg(r.o2_percent)::numeric, 2) AS o2_percent,
               round(avg(r.co2_percent)::numeric, 2) AS co2_percent,
               round(avg(r.nh3_ratio)::numeric, 3) AS nh3_ratio
        FROM records r JOIN bins b ON b.id = r.bin_id
        WHERE r.timestamp >= :start AND r.timestamp < :end
          AND b.country_code IS NOT NULL
          AND (:country_code IS NULL OR b.country_code = :country_code)
        GROUP BY b.country_code, day
        ORDER BY b.country_code, day
    """)
    with db_engine.connect() as db:
        rows = db.execute(sql, {"start": w.start, "end": w.end,
                                "country_code": w.country_code}).mappings().all()
    return [{key: float(value) if key in {"temperature_c", "moisture_percent", "o2_percent", "co2_percent", "nh3_ratio"} and value is not None else value
             for key, value in row.items() if daily or key != "day"} for row in rows]


def _result(w: Window, daily: bool):
    return {"start": w.start, "end": w.end, "country_code": w.country_code,
            "data": _aggregate(w, daily)}


@router.get("/overview", dependencies=[Depends(research_key)])
def overview(w: Window = Depends(window)):
    """Country aggregates for a time window. Send x-research-key."""
    return _result(w, False)


@router.get("/daily", dependencies=[Depends(research_key)])
def daily(w: Window = Depends(window)):
    """Daily country aggregates for a time window. Send x-research-key."""
    return _result(w, True)


@router.get("/preview/overview")
def preview_overview(w: Window = Depends(window), _user=Depends(require_role("researcher"))):
    """The same aggregate for the signed-in research dashboard."""
    return _result(w, False)


@router.get("/preview/daily")
def preview_daily(w: Window = Depends(window), _user=Depends(require_role("researcher"))):
    return _result(w, True)
