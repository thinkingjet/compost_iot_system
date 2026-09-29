"""
The signed-in user's compost bins.

Only what pairing needs so far: list them, and create one. Every query is
scoped to the user, so another user's bin simply doesn't exist (404).
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AfterValidator, BaseModel, BeforeValidator, Field
from sqlalchemy import text

from database import db_engine
from routers.auth import current_user

router = APIRouter(prefix="/bins", tags=["bins"])


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


BIN_COLUMNS = "id, name, location, country_code"


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