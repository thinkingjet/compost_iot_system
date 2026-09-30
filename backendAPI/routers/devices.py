"""
The signed-in user's devices: list, set up, edit and unpair them.

A device joins an account in two steps (routers/pairing.py): it redeems a
pairing code and gets its key, then the user confirms it here and gives it a
name and a bin. Until then it has an owner but no bin, and /records answers
409, which the device takes as "not set up yet".
"""
import datetime
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, BeforeValidator, Field
from sqlalchemy import text

from database import db_engine
from routers.auth import current_user
from routers.bins import owned_bin

router = APIRouter(prefix="/devices", tags=["devices"])

NOT_FOUND = HTTPException(status_code=404, detail="Device not found.")


class BinRef(BaseModel):
    id: uuid.UUID
    name: str | None


class Device(BaseModel):
    id: uuid.UUID
    hardware_id: str
    name: str | None
    model: str | None
    firmware_version: str | None
    paired_at: datetime.datetime | None
    last_seen_at: datetime.datetime | None
    bin: BinRef | None
    # confirmed in the dashboard, named and in a bin: its readings are accepted
    set_up: bool


class DeviceSetup(BaseModel):
    name: Annotated[str, BeforeValidator(lambda v: v.strip() if isinstance(v, str) else v),
                    Field(min_length=1, max_length=80)]
    bin_id: uuid.UUID


DEVICE_SELECT = """
    SELECT d.id, d.mac, d.name, d.model, d.firmware_version, d.paired_at, d.last_seen_at,
           b.id AS bin_id, b.name AS bin_name
    FROM devices d
    LEFT JOIN device_bin_assn a ON a.device_id = d.id AND a.unassigned_at IS NULL
    LEFT JOIN bins b ON b.id = a.bin_id
"""


def device_out(row):
    bin_ref = BinRef(id=row.bin_id, name=row.bin_name) if row.bin_id else None
    return Device(
        id=row.id,
        hardware_id=row.mac,
        name=row.name,
        model=row.model,
        firmware_version=row.firmware_version,
        paired_at=row.paired_at,
        last_seen_at=row.last_seen_at,
        bin=bin_ref,
        set_up=bin_ref is not None and bool(row.name),
    )


def owned_device(db, device_id, user_id):
    """The user's device row, or None - someone else's device is never shown."""
    return db.execute(
        text(DEVICE_SELECT + " WHERE d.id = :id AND d.owner_id = :user_id"),
        {"id": device_id, "user_id": user_id},
    ).first()


def release_device(db, device_id):
    """Revoke its keys and take it out of its bin: it can no longer send readings."""
    db.execute(
        text("UPDATE device_apikeys SET revoked_at = now() WHERE device_id = :id AND revoked_at IS NULL"),
        {"id": device_id},
    )
    db.execute(
        text("UPDATE device_bin_assn SET unassigned_at = now() WHERE device_id = :id AND unassigned_at IS NULL"),
        {"id": device_id},
    )


@router.get("", response_model=list[Device])
def list_devices(user=Depends(current_user)):
    with db_engine.connect() as db:
        rows = db.execute(
            text(DEVICE_SELECT + " WHERE d.owner_id = :user_id ORDER BY d.paired_at DESC NULLS LAST, d.name"),
            {"user_id": user.id},
        ).all()
    return [device_out(row) for row in rows]


@router.get("/{device_id}", response_model=Device)
def read_device(device_id: uuid.UUID, user=Depends(current_user)):
    with db_engine.connect() as db:
        row = owned_device(db, device_id, user.id)
    if row is None:
        raise NOT_FOUND
    return device_out(row)


@router.post("/{device_id}/setup", response_model=Device)
def set_up_device(device_id: uuid.UUID, body: DeviceSetup, user=Depends(current_user)):
    """Confirm the registration: name the device and put it in one of the user's bins."""
    with db_engine.begin() as db:
        device = owned_device(db, device_id, user.id)
        if device is None:
            raise NOT_FOUND
        if owned_bin(db, body.bin_id, user.id) is None:
            raise HTTPException(status_code=404, detail="Bin not found.")

        db.execute(text("UPDATE devices SET name = :name WHERE id = :id"), {"name": body.name, "id": device_id})
        if device.bin_id != body.bin_id:
            db.execute(
                text("UPDATE device_bin_assn SET unassigned_at = now() WHERE device_id = :id AND unassigned_at IS NULL"),
                {"id": device_id},
            )
            db.execute(
                text("INSERT INTO device_bin_assn (device_id, bin_id) VALUES (:id, :bin_id)"),
                {"id": device_id, "bin_id": body.bin_id},
            )
        row = owned_device(db, device_id, user.id)
    return device_out(row)


@router.patch("/{device_id}", response_model=Device)
def update_device(device_id: uuid.UUID, body: DeviceSetup, user=Depends(current_user)):
    """Rename a paired device or move it to another bin owned by the user."""
    return set_up_device(device_id, body, user)


@router.delete("/{device_id}", status_code=204)
def unpair_device(device_id: uuid.UUID, user=Depends(current_user)):
    """Unpair: the key stops working at once and the device can be paired again."""
    with db_engine.begin() as db:
        if owned_device(db, device_id, user.id) is None:
            raise NOT_FOUND
        release_device(db, device_id)
        db.execute(
            text("UPDATE devices SET owner_id = NULL, name = NULL, is_active = false WHERE id = :id"),
            {"id": device_id},
        )
    return Response(status_code=204)
