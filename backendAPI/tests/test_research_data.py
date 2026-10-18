"""Research data is aggregated, private, read-only, and available by key."""
from sqlalchemy import text

from main import db_engine
from tests.conftest import _register


def test_country_daily_aggregates_include_one_owner(client, researcher, new_email):
    key = client.post("/auth/research-keys", json={"name": "analysis"},
                      headers=researcher["headers"]).json()["api_key"]
    headers = {"x-research-key": key}
    query = "?country_code=ZZ&start=2000-01-01T00:00:00Z&end=2000-01-03T00:00:00Z"

    assert client.get("/research/daily" + query, headers=headers).json()["data"] == []
    for number in range(3):
        owner = _register(client, new_email())
        with db_engine.begin() as db:
            bin_id = db.execute(text("""
                INSERT INTO bins (user_id, name, location, country_code)
                VALUES (:user_id, 'Research test bin', 'private location', 'ZZ') RETURNING id
            """), {"user_id": owner["user"]["id"]}).scalar_one()
            db.execute(text("""
                INSERT INTO records (device_id, bin_id, timestamp, temperature,
                                     moisture_percent, o2_percent, co2_percent, nh3_ratio)
                VALUES ('00000000-0000-4000-8000-000000000201', :bin_id,
                        '2000-01-01T12:00:00Z', :temperature, 50, 10, 5, 0.5)
            """), {"bin_id": bin_id, "temperature": 40 + number * 10})
        result = client.get("/research/daily" + query, headers=headers).json()["data"]
        assert len(result) == 1
        assert result[0]["reading_count"] == number + 1

    row = result[0]
    assert row["country_code"] == "ZZ"
    assert row["bin_count"] == 3
    assert row["reading_count"] == 3
    assert row["temperature_c"] == 50.0
    assert not ({"bin_id", "device_id", "user_id", "location", "email"} & row.keys())
    assert len(client.get("/research/overview" + query, headers=headers).json()["data"]) == 1
    assert len(client.get("/research/preview/daily" + query,
                          headers=researcher["headers"]).json()["data"]) == 1


def test_research_access_and_window_validation(client, researcher, account, device_key):
    path = "/research/overview?country_code=ID"
    assert client.get(path).status_code in (401, 403)
    assert client.get(path, headers={"x-research-key": device_key}).status_code == 401
    assert client.get("/research/preview/overview", headers=account["headers"]).status_code == 403
    key = client.post("/auth/research-keys", json={"name": "analysis"},
                      headers=researcher["headers"]).json()["api_key"]
    headers = {"x-research-key": key}
    assert client.get(path + "&start=2026-01-01&end=2026-02-01", headers=headers).status_code == 422
    assert client.get(path + "&start=2026-02-01T00:00:00Z&end=2026-01-01T00:00:00Z",
                      headers=headers).status_code == 422
    assert client.get("/research/daily?country_code=not-a-country", headers=headers).status_code == 422


def test_research_key_stops_working_if_account_role_changes(client, researcher):
    key = client.post("/auth/research-keys", json={"name": "analysis"},
                      headers=researcher["headers"]).json()["api_key"]
    headers = {"x-research-key": key}
    assert client.get("/research/overview", headers=headers).status_code == 200
    with db_engine.begin() as db:
        db.execute(text("UPDATE users SET role = 'owner' WHERE id = :id"),
                   {"id": researcher["user"]["id"]})
    assert client.get("/research/overview", headers=headers).status_code == 401


def test_spread_alerts_countries_and_csv(client, researcher, account):
    key = client.post("/auth/research-keys", json={"name": "analysis"},
                      headers=researcher["headers"]).json()["api_key"]
    headers = {"x-research-key": key}
    query = "?country_code=ZY&start=2000-01-01T00:00:00Z&end=2000-01-03T00:00:00Z"
    with db_engine.begin() as db:
        bin_id = db.execute(text("""
            INSERT INTO bins (user_id, name, location, country_code)
            VALUES (:user_id, 'Spread test bin', 'private', 'ZY') RETURNING id
        """), {"user_id": account["user"]["id"]}).scalar_one()
        for temperature in (40, 60):
            db.execute(text("""
                INSERT INTO records (device_id, bin_id, timestamp, temperature,
                                     moisture_percent, o2_percent, co2_percent, nh3_ratio)
                VALUES ('00000000-0000-4000-8000-000000000201', :bin_id,
                        '2000-01-01T12:00:00Z', :temperature, 50, 10, 5, 0.5)
            """), {"bin_id": bin_id, "temperature": temperature})
        db.execute(text("""
            INSERT INTO bin_events (bin_id, type, severity, triggered_at, resolved_at)
            VALUES (:bin_id, 'too_hot', 'high', '2000-01-01T12:00:00Z', '2000-01-01T14:00:00Z')
        """), {"bin_id": bin_id})

    row = client.get("/research/overview" + query, headers=headers).json()["data"][0]
    assert (row["temperature_c"], row["temperature_c_min"], row["temperature_c_max"]) == (50.0, 40.0, 60.0)
    assert row["temperature_c_sd"] > 0

    alerts = client.get("/research/alerts" + query, headers=headers).json()["data"]
    assert alerts == [{"country_code": "ZY", "type": "too_hot", "alert_count": 1, "bin_count": 1, "avg_hours_to_resolve": 2.0}]

    zy = [c for c in client.get("/research/countries", headers=headers).json() if c["country_code"] == "ZY"]
    assert zy[0]["bin_count"] == 1 and zy[0]["reading_count"] == 2

    response = client.get("/research/daily" + query + "&format=csv", headers=headers)
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text.splitlines()[0].startswith("country_code,day,bin_count,reading_count,temperature_c")
