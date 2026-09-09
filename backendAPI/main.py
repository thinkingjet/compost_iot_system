from fastapi import FastAPI
from pydantic import BaseModel
import datetime

class Record(BaseModel):
    timestamp: datetime
    temperature: float
    moisture_percent: float
    o2_percent: float
    co2_percent: float
    nh3_ratio: float

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Hello World"}