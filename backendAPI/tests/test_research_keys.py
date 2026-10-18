"""/auth/research-keys - a researcher's API keys, and the research_key check."""
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from conftest import _register
from routers.research_keys import MAX_KEYS, research_key

# a stand-in research endpoint, until the real ones exist
research_app = FastAPI()


@research_app.get("/research/me")
def who(user_id=Depends(research_key)):
    return {"user_id": str(user_id)}


research_client = TestClient(research_app)


def _create(client, researcher, name="Lab server"):
    return client.post("/auth/research-keys", json={"name": name}, headers=researcher["headers"])


def test_a_key_works_once_made_and_stops_once_deleted(client, researcher):
    response = _create(client, researcher)
    assert response.status_code == 201
    key = response.json()
    assert key["name"] == "Lab server"

    # the key is never listed, only shown when made
    listed = client.get("/auth/research-keys", headers=researcher["headers"]).json()
    assert listed == [{k: key[k] for k in ("id", "name", "created_at")}]

    me = research_client.get("/research/me", headers={"x-research-key": key["api_key"]})
    assert me.json() == {"user_id": researcher["user"]["id"]}

    assert client.delete(f"/auth/research-keys/{key['id']}", headers=researcher["headers"]).status_code == 204
    assert research_client.get("/research/me", headers={"x-research-key": key["api_key"]}).status_code == 401
    assert client.get("/auth/research-keys", headers=researcher["headers"]).json() == []


def test_a_key_needs_a_name_and_there_is_a_limit(client, researcher):
    assert _create(client, researcher, name="  ").status_code == 422
    for number in range(MAX_KEYS):
        assert _create(client, researcher, name=f"Key {number}").status_code == 201
    assert _create(client, researcher).status_code == 409


def test_keys_are_for_researchers_and_their_own(client, researcher, account, new_email):
    # an owner account can't have research keys
    assert _create(client, account).status_code == 403
    assert client.get("/auth/research-keys", headers=account["headers"]).status_code == 403

    # another researcher can't see or delete this one's key
    other = _register(client, new_email(), role="researcher")
    key = _create(client, researcher).json()
    assert client.get("/auth/research-keys", headers=other["headers"]).json() == []
    assert client.delete(f"/auth/research-keys/{key['id']}", headers=other["headers"]).status_code == 404


def test_only_a_research_key_opens_research_endpoints(researcher, device_key):
    assert research_client.get("/research/me", headers={"x-research-key": "not-a-key"}).status_code == 401
    assert research_client.get("/research/me", headers={"x-research-key": device_key}).status_code == 401
    assert research_client.get("/research/me", headers=researcher["headers"]).status_code in (401, 403)
