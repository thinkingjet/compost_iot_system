from fastapi import FastAPI
from pydantic import BaseModel
import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader
import hashlib


class Record(BaseModel):
    timestamp: datetime.datetime
    temperature: float
    moisture_percent: float
    o2_percent: float
    co2_percent: float
    nh3_ratio: float

app = FastAPI()

POSTGRES_DB_URL = "postgresql+psycopg2://postgres:devpassword@localhost:5432/compostiq"
db_engine = create_engine(POSTGRES_DB_URL)
# with db_engine.connect() as connection:
#     result = connection.execute(text("SELECT count(*) FROM USERS"))
#     for row in result:
#         print(row)

api_key_header = APIKeyHeader(name = "x-key")

def authentication(api_key: str = Security(api_key_header)):
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    with db_engine.connect() as db:
        result = db.execute(text(
            """
            SELECT device_id FROM device_apikeys
            WHERE api_key_hash = :key_hash AND revoked_at IS NULL
            """
        ),
        {
            "key_hash": key_hash
        }
        )
        res = result.first()
    if res is None:
        raise HTTPException(status_code=401, "Authentication failed: invalid API key.")
    else:
        return res.device_id
    return "This should never happen."

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.post("/records")
async def send_records (readings: list[Record]):
    device_id = "28d7f6b0-20ab-4d41-906b-31b6634b56ea"
    bin_id = "33155618-6336-4447-9f64-a80ae4802b36"
    with db_engine.connect() as db:
        print(f"Database connection was successful: {db}")
        for reading in readings:
            db.execute(text("""
                            INSERT INTO records (device_id, bin_id, timestamp, 
                            temperature, moisture_percent, o2_percent, co2_percent, nh3_ratio)
                            VALUES (:device_id, :bin_id, :timestamp, :temperature,
                            :moisture_percent, :o2_percent, :co2_percent, :nh3_ratio)
                            """),
                {
                    "device_id":device_id,
                    "bin_id":bin_id,
                    "timestamp": reading.timestamp,
                    "temperature": reading.temperature,
                    "moisture_percent": reading.moisture_percent,
                    "o2_percent": reading.o2_percent,
                    "co2_percent":reading.co2_percent,
                    "nh3_ratio": reading.nh3_ratio
                })
        db.commit()
    return readings

