"""GET /bins/{bin_id}/stage: the compost stage the model in ml/ estimates from
a bin's readings.

The piles here are drawn by hand (warm up, hold hot, cool down), so the tests
check the estimate is in the right part of the cycle rather than one exact
stage, and keep passing when the model is retrained. The tests that need the
model are skipped with a hint when the API couldn't load it.

Every test works in throwaway accounts, so bins and readings go with the
account at teardown; devices are removed by their MAC prefix.
"""
import datetime
import secrets

import pytest
from sqlalchemy import text

import stage_model
from conftest import TEST_PASSWORD, reading
from main import db_engine

# upper case, as the API stores hardware IDs; test_dashboard_endpoints.py uses ...:FC:
TEST_MAC_PREFIX = "02:00:00:00:FB:"
RANDOM_ID = "11111111-2222-4333-8444-555555555555"
STAGES = ["Early Mesophilic", "Active Thermophilic", "Peak Decomposition", "Cooling", "Maturation"]
NO_STAGE = {"stage_id": None, "stage": None, "raw_stage": None, "confidence": None, "probabilities": {}}


@pytest.fixture(autouse=True)
def clean_devices():
    def clean():
        devices = "SELECT id FROM devices WHERE mac LIKE :like"
        like = {"like": TEST_MAC_PREFIX + "%"}
        with db_engine.begin() as db:
            for table in ("device_apikeys", "device_bin_assn", "records", "setup_codes"):
                db.execute(text(f"DELETE FROM {table} WHERE device_id IN ({devices})"), like)
            db.execute(text("DELETE FROM devices WHERE mac LIKE :like"), like)
    clean()
    yield
    clean()


@pytest.fixture
def model():
    if stage_model.bundle is None:
        pytest.skip(f"stage model not loaded ({stage_model.load_error}) - it comes from ml/; set ML_DIR if ml/ is elsewhere")


@pytest.fixture
def other_account(client, new_email):
    response = client.post("/auth/register", json={"email": new_email(), "password": TEST_PASSWORD})
    return {"headers": {"Authorization": f"Bearer {response.json()['access_token']}"}}


# ----------------------------------------------------------------- helpers ---

def _bin(client, headers):
    response = client.post("/bins", headers=headers, json={"name": "Stage test bin", "country_code": "ID"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _device(client, headers, bin_id):
    """A paired, set-up device in bin_id; returns its API key."""
    code = client.post("/pairing/codes", headers=headers).json()["code"]
    mac = f"{TEST_MAC_PREFIX}{secrets.randbelow(256):02X}"
    redeemed = client.post("/pairing/redeem", json={"code": code, "device_uid": mac})
    assert redeemed.status_code == 201, redeemed.text
    device_id, api_key = redeemed.json()["device_id"], redeemed.json()["api_key"]
    setup = client.post(f"/devices/{device_id}/setup", headers=headers, json={"name": "Core probe", "bin_id": bin_id})
    assert setup.status_code == 200, setup.text
    return api_key


def _pile(client, headers, temperature, hours, every_minutes=30):
    """A bin whose sensor sent temperature(h) every half hour for `hours`, up to
    5 minutes ago (h = hours since the first reading). Returns (bin_id, readings)."""
    bin_id = _bin(client, headers)
    api_key = _device(client, headers, bin_id)
    last = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
    count = int(hours * 60 / every_minutes) + 1
    readings = []
    for i in range(count):
        h = i * every_minutes / 60
        at = last - datetime.timedelta(hours=hours - h)
        readings.append(reading(timestamp=at.isoformat(), temperature=round(temperature(h), 2), moisture_percent=55.0))
    response = client.post("/records", json=readings, headers={"x-key": api_key})
    assert response.status_code == 200, response.text
    return bin_id, readings


def _warm_up(h):
    """From 25 °C to 62 °C over the first 30 h."""
    return 25 + 37 * min(h, 30) / 30


def _hot_then_cooled(h):
    """Warm up, hold 62 °C for 3 days, cool to 32 °C over 4 days, then stay there."""
    if h < 102:
        return _warm_up(h)
    return max(32.0, 62 - 30 * (h - 102) / 96)


def _stage(client, headers, bin_id, query=""):
    response = client.get(f"/bins/{bin_id}/stage{query}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------------ stages ---

def test_a_hot_pile_is_in_a_hot_stage(client, account, model):
    headers = account["headers"]
    bin_id, readings = _pile(client, headers, _warm_up, hours=72)

    body = _stage(client, headers, bin_id)
    assert set(body) == {"stage_id", "stage", "raw_stage", "confidence", "probabilities", "last_reading_at", "history_hours"}
    assert body["stage"] in {"Active Thermophilic", "Peak Decomposition"}
    assert body["stage"] == STAGES[body["stage_id"]]
    # the latest hour's probabilities, one per stage
    assert list(body["probabilities"]) == STAGES
    assert sum(body["probabilities"].values()) == pytest.approx(1, abs=0.01)
    assert body["raw_stage"] == max(body["probabilities"], key=body["probabilities"].get)
    assert body["confidence"] == body["probabilities"][body["raw_stage"]]
    assert datetime.datetime.fromisoformat(body["last_reading_at"]) == datetime.datetime.fromisoformat(readings[-1]["timestamp"])
    assert body["history_hours"] == pytest.approx(72)


def test_a_pile_that_has_cooled_down_is_past_the_hot_stages(client, account, model):
    headers = account["headers"]
    bin_id, _ = _pile(client, headers, _hot_then_cooled, hours=12 * 24)
    assert _stage(client, headers, bin_id)["stage"] in {"Cooling", "Maturation"}


def test_a_new_bin_has_no_stage_yet(client, account, model):
    bin_id = _bin(client, account["headers"])
    assert _stage(client, account["headers"], bin_id) == {**NO_STAGE, "last_reading_at": None, "history_hours": 0}


def test_less_than_a_day_of_readings_gives_no_stage(client, account, model):
    headers = account["headers"]
    bin_id, readings = _pile(client, headers, _warm_up, hours=5)
    body = _stage(client, headers, bin_id)
    assert {key: body[key] for key in NO_STAGE} == NO_STAGE
    assert body["history_hours"] == pytest.approx(5)
    assert datetime.datetime.fromisoformat(body["last_reading_at"]) == datetime.datetime.fromisoformat(readings[-1]["timestamp"])


def test_the_window_leaves_out_older_readings(client, account, model):
    headers = account["headers"]
    bin_id, _ = _pile(client, headers, _warm_up, hours=72)
    assert _stage(client, headers, bin_id, "?days=3")["stage"] is not None
    # the last day only: not enough to go on
    body = _stage(client, headers, bin_id, "?days=1")
    assert body["stage"] is None and body["history_hours"] < 24


def test_the_stage_checks_the_window_and_the_owner(client, account, other_account):
    bin_id = _bin(client, account["headers"])
    for days in (0, 366, -1):
        assert client.get(f"/bins/{bin_id}/stage?days={days}", headers=account["headers"]).status_code == 422
    assert client.get(f"/bins/{bin_id}/stage", headers=other_account["headers"]).status_code == 404
    assert client.get(f"/bins/{RANDOM_ID}/stage", headers=account["headers"]).status_code == 404
    assert client.get(f"/bins/{bin_id}/stage").status_code == 401


def test_without_the_model_the_stage_is_unavailable(client, account, monkeypatch):
    monkeypatch.setattr(stage_model, "bundle", None)
    bin_id = _bin(client, account["headers"])
    response = client.get(f"/bins/{bin_id}/stage", headers=account["headers"])
    assert response.status_code == 503
    assert response.json() == {"detail": "The stage model isn't available on this server."}
    # someone else's or a missing bin is still a 404, not a hint that it exists
    assert client.get(f"/bins/{RANDOM_ID}/stage", headers=account["headers"]).status_code == 404


# ------------------------------------------------- saved stages (bin_stages) ---

def _saved(bin_id):
    with db_engine.connect() as db:
        return db.execute(text("SELECT hour, stage FROM bin_stages WHERE bin_id = :id ORDER BY hour"), {"id": bin_id}).all()


def test_an_upload_saves_a_stage_per_hour_and_history_shows_it(client, account, model):
    bin_id, readings = _pile(client, account["headers"], _warm_up, hours=48)
    saved = _saved(bin_id)
    assert 40 <= len(saved) <= 49
    assert {row.stage for row in saved} <= set(STAGES)
    history = client.get(f"/bins/{bin_id}/history", headers=account["headers"]).json()
    assert history[-1]["stage"] in STAGES


def test_under_a_day_of_readings_saves_no_stage(client, account, model):
    bin_id, _ = _pile(client, account["headers"], _warm_up, hours=12)
    assert _saved(bin_id) == []


def test_saved_hours_are_kept_and_saving_is_at_most_hourly(client, account, model):
    bin_id, readings = _pile(client, account["headers"], _warm_up, hours=48)
    before = _saved(bin_id)
    api_key = _device(client, account["headers"], bin_id)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    assert client.post("/records", json=[reading(timestamp=now, temperature=20.0)], headers={"x-key": api_key}).status_code == 200
    assert _saved(bin_id) == before


def test_hours_without_readings_are_not_saved(client, account, model):
    bin_id = _bin(client, account["headers"])
    api_key = _device(client, account["headers"], bin_id)
    last = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
    # 72 hours, with the sensor down from hour 30 to hour 50
    readings = [reading(timestamp=(last - datetime.timedelta(hours=72 - h / 2)).isoformat(), temperature=_warm_up(h / 2), moisture_percent=55.0)
                for h in range(145) if not 60 <= h < 100]
    assert client.post("/records", json=readings, headers={"x-key": api_key}).status_code == 200
    gap_start, gap_end = last - datetime.timedelta(hours=41), last - datetime.timedelta(hours=23)
    saved = _saved(bin_id)
    assert saved and not [row for row in saved if gap_start < row.hour < gap_end]


def test_a_model_error_does_not_fail_the_upload(client, account, model, monkeypatch):
    def broken(readings):
        raise RuntimeError("model broke")
    monkeypatch.setattr(stage_model, "hourly", broken)
    bin_id, readings = _pile(client, account["headers"], _warm_up, hours=48)
    assert _saved(bin_id) == []
    assert len(client.get(f"/bins/{bin_id}/records?hours=72", headers=account["headers"]).json()) == len(readings)
