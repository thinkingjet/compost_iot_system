"""
A researcher's API keys: list, make and delete them (signed in, researcher
accounts only), and `research_key`, the check the research endpoints use.

A key only works on the research endpoints, sent as `x-research-key`. A
device key (`x-key`) or a login token doesn't work there, and a research key
works nowhere else. Only the key's SHA-256 hash is stored, like device keys.
"""
import datetime
import hashlib
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, BeforeValidator, Field
from sqlalchemy import text

from database import db_engine
from routers.auth import require_role

router = APIRouter(prefix="/auth/research-keys", tags=["research keys"])

MAX_KEYS = 5

KeyName = Annotated[str, BeforeValidator(lambda v: v.strip() if isinstance(v, str) else v),
                    Field(min_length=1, max_length=80)]


class KeyCreate(BaseModel):
    name: KeyName


class ResearchKey(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime.datetime


class NewResearchKey(ResearchKey):
    # returned this once; only its hash is stored
    api_key: str


@router.get("", response_model=list[ResearchKey])
def list_keys(user=Depends(require_role("researcher"))):
    with db_engine.connect() as db:
        rows = db.execute(
            text("SELECT id, name, created_at FROM research_apikeys WHERE user_id = :user_id ORDER BY created_at"),
            {"user_id": user.id},
        ).all()
    return [ResearchKey(**row._mapping) for row in rows]


@router.post("", status_code=201, response_model=NewResearchKey)
def create_key(body: KeyCreate, user=Depends(require_role("researcher"))):
    api_key = secrets.token_hex(32)
    with db_engine.begin() as db:
        count = db.execute(
            text("SELECT count(*) FROM research_apikeys WHERE user_id = :user_id"), {"user_id": user.id}
        ).scalar_one()
        if count >= MAX_KEYS:
            raise HTTPException(status_code=409, detail=f"You can have up to {MAX_KEYS} keys. Delete one first.")
        row = db.execute(
            text(
                """
                INSERT INTO research_apikeys (user_id, name, api_key_hash)
                VALUES (:user_id, :name, :hash)
                RETURNING id, name, created_at
                """
            ),
            {"user_id": user.id, "name": body.name, "hash": hashlib.sha256(api_key.encode()).hexdigest()},
        ).first()
    return NewResearchKey(**row._mapping, api_key=api_key)


@router.delete("/{key_id}", status_code=204)
def delete_key(key_id: uuid.UUID, user=Depends(require_role("researcher"))):
    with db_engine.begin() as db:
        deleted = db.execute(
            text("DELETE FROM research_apikeys WHERE id = :id AND user_id = :user_id RETURNING id"),
            {"id": key_id, "user_id": user.id},
        ).first()
    if deleted is None:
        raise HTTPException(status_code=404, detail="Key not found.")
    return Response(status_code=204)


research_key_header = APIKeyHeader(name="x-research-key")


def research_key(api_key: str = Security(research_key_header)):
    """For the research endpoints: the researcher's user id for a valid
    `x-research-key`, else 401. Use it as `Depends(research_key)`."""
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    with db_engine.connect() as db:
        user_id = db.execute(
            text("""
                SELECT k.user_id FROM research_apikeys k
                JOIN users u ON u.id = k.user_id
                WHERE k.api_key_hash = :hash AND u.role = 'researcher'
            """), {"hash": key_hash}
        ).scalar()
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid research API key.")
    return user_id
