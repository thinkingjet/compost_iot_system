"""The dashboard Create Bin action reaches the API and persists the new bin."""
import sys
from pathlib import Path

from sqlalchemy import text

from main import db_engine

sys.path.insert(0, str(Path(__file__).parents[2] / "monitoringSystem"))
import app as dashboard  # noqa: E402
import pages  # noqa: E402


def test_create_bin_dashboard_action_persists_record(client, account, monkeypatch):
    def via_api(name, country_code, location):
        response = client.post("/bins", headers=account["headers"],
                               json={"name": name, "country_code": country_code, "location": location})
        assert response.status_code == 201, response.text
        return response.json()

    monkeypatch.setattr(dashboard, "_clicked", lambda: True)
    monkeypatch.setattr(dashboard.api_client, "create_bin", via_api)
    redirect, notification = dashboard.create_bin(1, "  Test compost  ", "  Mataram  ", "ID", "/bins/new")

    assert notification[0]["message"] == "Bin created."
    bin_id = redirect["pathname"].split("/")[2]
    assert redirect["pathname"] == f"/bin/{bin_id}/settings"
    with db_engine.connect() as db:
        row = db.execute(text("""
            SELECT name, location, country_code, user_id::text AS user_id
            FROM bins WHERE id = :id
        """), {"id": bin_id}).mappings().one()
    assert dict(row) == {"name": "Test compost", "location": "Mataram", "country_code": "ID",
                         "user_id": account["user"]["id"]}
    assert client.get(f"/bins/{bin_id}", headers=account["headers"]).status_code == 200


def test_research_pages_can_render(monkeypatch):
    monkeypatch.setattr(pages.api_client, "research_data", lambda *args, **kwargs: {"data": []})
    monkeypatch.setattr(pages.api_client, "list_research_keys", lambda: [])
    with dashboard.server.test_request_context("/"):
        pages.research_data_page()
        pages.research_keys_page()
        pages.research_docs_page()
