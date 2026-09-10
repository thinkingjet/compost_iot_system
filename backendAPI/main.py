from fastapi import FastAPI
from pydantic import BaseModel
import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


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
with db_engine.connect() as connection:
    result = connection.execute(text("SELECT count(*) FROM USERS"))
    for row in result:
        print(row)


@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.post("/records")
async def send_records (readings: list[Record]):
    return readings

