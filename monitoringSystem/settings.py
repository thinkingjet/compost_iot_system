"""
Environment settings for the dashboard.

Locally they come from monitoringSystem/.env (see .env.example); on the VM,
PM2 passes them in from the repo-root .env. Variables that are already set
win over the file.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

API_URL = os.environ.get("API_URL", "http://127.0.0.1:8000").rstrip("/")
# signs the session cookie; app.py decides what a missing key means
DASHBOARD_SECRET_KEY = os.environ.get("DASHBOARD_SECRET_KEY")
# how long the session cookie lasts - matches the API's 8-hour token
SESSION_HOURS = 8
