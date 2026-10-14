"""Account types: owner-only endpoints refuse researcher accounts (403), and
/auth works for both.

The guarded endpoints are read from the app itself, so a new endpoint on one
of these routers is covered here without being listed.
"""
import pytest
from sqlalchemy import text

from main import app, db_engine

OWNER_ONLY_PREFIXES = ("/bins", "/devices", "/alerts", "/pairing/codes")
REFUSED = {"detail": "Not available to researcher accounts."}

# stand-ins for path parameters; the guard answers before they are looked up
PATH_VALUES = {
    "bin_id": "11111111-2222-4333-8444-555555555555",
    "device_id": "11111111-2222-4333-8444-555555555555",
    "code": "123456",
}


def _owner_only_endpoints():
    # from the OpenAPI schema: included routers are not listed in app.routes
    endpoints = [
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        if path.startswith(OWNER_ONLY_PREFIXES)
        for method in operations
    ]
    # each prefix still exists, so a renamed router can't silently drop out
    for prefix in OWNER_ONLY_PREFIXES:
        assert any(path.startswith(prefix) for _, path in endpoints), prefix
    return endpoints


@pytest.mark.parametrize(("method", "path"), _owner_only_endpoints(), ids=lambda value: value)
def test_a_researcher_is_refused_owner_only_endpoints(client, researcher, method, path):
    response = client.request(method, path.format(**PATH_VALUES), headers=researcher["headers"])

    assert response.status_code == 403
    assert response.json() == REFUSED
    # not a token problem, so the dashboard doesn't sign the user out over it
    assert "www-authenticate" not in response.headers


def test_an_owner_still_reaches_owner_only_endpoints(client, account):
    for path in ("/bins", "/devices", "/alerts"):
        response = client.get(path, headers=account["headers"])
        assert response.status_code == 200, path

    created = client.post("/pairing/codes", headers=account["headers"])
    assert created.status_code == 201
    status = client.get(f"/pairing/codes/{created.json()['code']}", headers=account["headers"])
    assert status.status_code == 200
    assert status.json()["status"] == "pending"


def test_the_role_is_read_from_the_database_on_every_request(client, account):
    with db_engine.begin() as db:
        db.execute(text("UPDATE users SET role = 'researcher' WHERE id = :id"), {"id": account["user"]["id"]})

    # the same token, issued while it was an owner
    assert client.get("/bins", headers=account["headers"]).status_code == 403


def test_signed_out_is_still_a_401_not_a_403(client):
    response = client.get("/bins")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


# -------------------------------------------------------------------- auth ---

def test_a_researcher_can_read_their_account(client, researcher):
    response = client.get("/auth/me", headers=researcher["headers"])

    assert response.status_code == 200
    assert response.json() == researcher["user"]
    assert response.json()["role"] == "researcher"


def test_a_researcher_can_manage_their_account(client, researcher):
    headers = researcher["headers"]

    renamed = client.patch("/auth/me", headers=headers, json={"display_name": "Dr Ayu"})
    assert renamed.status_code == 200
    assert renamed.json()["display_name"] == "Dr Ayu"

    changed = client.post(
        "/auth/change-password",
        headers=headers,
        json={"current_password": researcher["password"], "new_password": "a-new-password"},
    )
    assert changed.status_code == 204

    deleted = client.request("DELETE", "/auth/me", headers=headers, json={"password": "a-new-password"})
    assert deleted.status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401
