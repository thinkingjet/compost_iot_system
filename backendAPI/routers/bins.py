"""
The signed-in user's compost bins.

Only what pairing needs so far: list them, and create one. Every query is
scoped to the user, so another user's bin simply doesn't exist (404).
"""
import uuid
from typing import Annotated
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AfterValidator, BaseModel, BeforeValidator, Field
from sqlalchemy import text

import stage_model
from database import db_engine
from routers.auth import current_user, owner_only

# owners only: a researcher account has no bins
router = APIRouter(prefix="/bins", tags=["bins"], dependencies=[Depends(owner_only)])


def _strip(value):
    return value.strip() if isinstance(value, str) else value


Name = Annotated[str, BeforeValidator(_strip), Field(min_length=1, max_length=80)]
Location = Annotated[str, BeforeValidator(_strip), Field(max_length=120)]
# ISO 3166-1 alpha-2, stored upper case
CountryCode = Annotated[str, Field(pattern=r"^[A-Za-z]{2}$"), AfterValidator(str.upper)]


class BinCreate(BaseModel):
    name: Name
    location: Location = ""
    country_code: CountryCode

class Bin(BaseModel):
    id: uuid.UUID
    name: str | None
    location: str
    country_code: str | None

class BinChange(BaseModel):
    name: Name | None = None
    location: Location | None = None
    country_code: CountryCode | None = None
    
class Reading(BaseModel):
    timestamp: datetime.datetime
    temperature: float
    moisture_percent: float
    o2_percent: float
    co2_percent: float
    nh3_ratio: float
    device_id: uuid.UUID


class DailyReading(BaseModel):
    day: datetime.date
    avg_temp: float
    max_temp: float
    avg_moisture: float
    avg_o2: float
    avg_co2: float
    avg_nh3: float
    # the stage the bin spent the most saved hours in that day (bin_stages); None if none saved
    stage: str | None


class StageEstimate(BaseModel):
    # the stage after predict.py's forward-only filter (its stage_id_filtered / stage_filtered)
    stage_id: int | None
    stage: str | None
    # the latest hour on its own: its most likely stage, that stage's
    # probability, and every stage's probability
    raw_stage: str | None
    confidence: float | None
    probabilities: dict[str, float]
    last_reading_at: datetime.datetime | None
    history_hours: float


BIN_COLUMNS = "id, name, location, country_code"

READING_COLUMNS = "timestamp, temperature, moisture_percent, o2_percent, co2_percent, nh3_ratio, device_id"

# days in /history start at midnight here, not in the database server's timezone
SITE_TIMEZONE = "Asia/Makassar"


def owned_bin(db, bin_id, user_id):
    """The user's bin, or None if it doesn't exist or belongs to someone else."""
    return db.execute(
        text(f"SELECT {BIN_COLUMNS} FROM bins WHERE id = :id AND user_id = :user_id"),
        {"id": bin_id, "user_id": user_id},
    ).first()


@router.get("", response_model=list[Bin])
def list_bins(user=Depends(current_user)):
    with db_engine.connect() as db:
        rows = db.execute(
            text(f"SELECT {BIN_COLUMNS} FROM bins WHERE user_id = :user_id ORDER BY created_at, name"),
            {"user_id": user.id},
        ).all()
    return [Bin(**row._mapping) for row in rows]


@router.post("", status_code=201, response_model=Bin)
def create_bin(body: BinCreate, user=Depends(current_user)):
    with db_engine.begin() as db:
        row = db.execute(
            text(
                f"""
                INSERT INTO bins (name, location, country_code, user_id)
                VALUES (:name, :location, :country_code, :user_id)
                RETURNING {BIN_COLUMNS}
                """
            ),
            {**body.model_dump(), "user_id": user.id},
        ).first()
    return Bin(**row._mapping)


@router.get("/{bin_id}", response_model = Bin)
def get_specific_bin(bin_id: uuid.UUID, user = Depends(current_user)):
    with db_engine.connect() as db:
        row = db.execute(
            text(
                """
                SELECT id, name, location, country_code FROM bins
                WHERE id = :id AND user_id = :user_id
                """
            ),
            {"id": bin_id, "user_id": user.id}
        ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="The bin with the given ID does not exist.")
    return Bin(**row._mapping)


@router.patch("/{bin_id}", response_model=Bin)
def change_bin(bin_id: uuid.UUID, body: BinChange, user = Depends(current_user)):
    changed_fields = body.model_dump(exclude_none=True)
    if changed_fields == {}:
        raise HTTPException(status_code=422, detail="No fields are being changed.")
    set_parts = []
    for column in changed_fields:
        set_parts.append(f"{column} = :{column}")
    set_query = ", ".join(set_parts)
    with db_engine.begin() as db:
        row = db.execute(
            text(
            f"""
            UPDATE bins
            SET {set_query}
            WHERE id = :id AND user_id = :user_id
            RETURNING id, name, location, country_code
            """),
            {"id": bin_id, "user_id": user.id, **changed_fields}
        ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="The bin with the given ID does not exist.")
    return Bin(**row._mapping)


@router.delete("/{bin_id}", status_code=204)
def delete_bin(bin_id: uuid.UUID, user = Depends(current_user)):
    with db_engine.begin() as db:
        row = db.execute(
            text(
                """
                DELETE from bins
                WHERE id = :bin_id AND user_id = :user_id
                RETURNING id
                """
            ),
            {"bin_id": bin_id, "user_id":user.id}
        ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="The bin with the given ID does not exist.")
        

@router.get("/{bin_id}/records", response_model=list[Reading])
def get_bin_records(bin_id: uuid.UUID, hours: Annotated[int, Query(ge=1, le=168)] = 24, user = Depends(current_user)):
    with db_engine.connect() as db:
        if owned_bin(db, bin_id, user.id) is None:
            raise HTTPException(status_code=404, detail="The bin with the given ID does not exist.")
        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
        results = db.execute(
            text(
                f"""
                SELECT {READING_COLUMNS} FROM records
                WHERE bin_id = :bin_id AND timestamp >= :since
                ORDER BY timestamp ASC
                """
            ),
            {"bin_id":bin_id, "since": since}
        ).all()
    return [Reading(**row._mapping) for row in results]


@router.get("/{bin_id}/history", response_model=list[DailyReading])
def get_bin_history(bin_id: uuid.UUID, days: Annotated[int, Query(ge=1, le=365)] = 30, user = Depends(current_user)):
    with db_engine.connect() as db:
        if owned_bin(db, bin_id, user.id) is None:
            raise HTTPException(status_code=404, detail="The bin with the given ID does not exist.")
        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        results = db.execute(
            text(
                """
                WITH readings AS (
                    SELECT (timestamp AT TIME ZONE :tz)::date AS day,
                        avg(temperature) AS avg_temp,
                        max(temperature) AS max_temp,
                        avg(moisture_percent) AS avg_moisture,
                        avg(o2_percent) AS avg_o2,
                        avg(co2_percent) AS avg_co2,
                        avg(nh3_ratio) AS avg_nh3
                    FROM records
                    WHERE bin_id = :bin_id AND timestamp >= :since
                    GROUP BY day
                ), stages AS (
                    SELECT (hour AT TIME ZONE :tz)::date AS day, mode() WITHIN GROUP (ORDER BY stage) AS stage
                    FROM bin_stages
                    WHERE bin_id = :bin_id AND hour >= :since
                    GROUP BY day
                )
                SELECT * FROM readings LEFT JOIN stages USING (day)
                ORDER BY day
                """
            ),
            {"bin_id":bin_id, "since": since, "tz": SITE_TIMEZONE}
        ).all()
    return [DailyReading(**row._mapping) for row in results]


def _slots(db, bin_id, since):
    """The bin's readings since `since`, averaged per 30 minutes, oldest first.

    features.py averages readings onto a 30-minute grid first, so do that
    here: a device sending every 30 s would otherwise mean 170,000 rows.
    """
    return db.execute(
        text(
            """
            SELECT date_bin('30 minutes', timestamp, TIMESTAMPTZ '2000-01-01') AS slot,
                avg(temperature) AS temperature,
                avg(moisture_percent) AS moisture_percent,
                min(timestamp) AS first_at,
                max(timestamp) AS last_at
            FROM records
            WHERE bin_id = :bin_id AND timestamp >= :since
            GROUP BY slot
            ORDER BY slot
            """
        ),
        {"bin_id": bin_id, "since": since}
    ).all()


def save_stages(bin_id):
    """Save the model's stage for each new hour of the bin's readings (bin_stages, migration 007).

    POST /records calls this after storing readings. It does nothing if the
    model isn't installed, the bin has under 24 h of readings, or the newest
    saved hour is under an hour behind the newest reading. Hours without
    readings (a sensor that was down) aren't saved, and saved hours are never
    overwritten, so each keeps the prediction made at the time.
    """
    if stage_model.bundle is None:
        return
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=60)
    with db_engine.begin() as db:
        slots = _slots(db, bin_id, since)
        if not slots or slots[-1].last_at - slots[0].first_at < datetime.timedelta(hours=stage_model.MIN_HISTORY_HOURS):
            return
        last_saved = db.execute(text("SELECT max(hour) FROM bin_stages WHERE bin_id = :bin_id"), {"bin_id": bin_id}).scalar()
        if last_saved and slots[-1].last_at - last_saved < datetime.timedelta(hours=1):
            return
        # the model predicts every hour, gaps included; keep the hours that had readings
        with_readings = {row.slot for row in slots}
        half_hour = datetime.timedelta(minutes=30)
        rows = [
            {"bin_id": bin_id, "hour": hour, "stage_id": stage_id, "stage": stage, "confidence": confidence}
            for hour, stage_id, stage, confidence in stage_model.hourly([(r.slot, r.temperature, r.moisture_percent) for r in slots])
            if (last_saved is None or hour > last_saved) and (hour in with_readings or hour + half_hour in with_readings)
        ]
        if rows:
            db.execute(
                text(
                    """
                    INSERT INTO bin_stages (bin_id, hour, stage_id, stage, confidence)
                    VALUES (:bin_id, :hour, :stage_id, :stage, :confidence)
                    ON CONFLICT DO NOTHING
                    """
                ),
                rows,
            )


@router.get("/{bin_id}/stage", response_model=StageEstimate)
def get_bin_stage(bin_id: uuid.UUID, days: Annotated[int, Query(ge=1, le=365)] = 60, user = Depends(current_user)):
    """The compost stage the model estimates from the bin's last `days` of readings.

    The readings are treated as one batch: the model remembers the hottest the
    pile has been, so more history is better, but a window that reaches back
    into a previous batch misleads it. Under 24 h of readings gives no stage.
    """
    with db_engine.connect() as db:
        if owned_bin(db, bin_id, user.id) is None:
            raise HTTPException(status_code=404, detail="The bin with the given ID does not exist.")
        if stage_model.bundle is None:
            raise HTTPException(status_code=503, detail="The stage model isn't available on this server.")
        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        slots = _slots(db, bin_id, since)

    if not slots:
        return StageEstimate(stage_id=None, stage=None, raw_stage=None, confidence=None, probabilities={},
                             last_reading_at=None, history_hours=0)
    last_reading_at = slots[-1].last_at
    history_hours = (last_reading_at - slots[0].first_at).total_seconds() / 3600
    if history_hours < stage_model.MIN_HISTORY_HOURS:
        return StageEstimate(stage_id=None, stage=None, raw_stage=None, confidence=None, probabilities={},
                             last_reading_at=last_reading_at, history_hours=history_hours)
    estimate = stage_model.estimate([(row.slot, row.temperature, row.moisture_percent) for row in slots])
    return StageEstimate(**estimate, last_reading_at=last_reading_at, history_hours=history_hours)
