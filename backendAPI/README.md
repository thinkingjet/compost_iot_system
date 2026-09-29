# CompostIQ API

FastAPI, with raw SQL through SQLAlchemy Core, on PostgreSQL. It is the only part of CompostIQ that touches the database.

| | |
|---|---|
| Production | `https://api.compostiq.win` → uvicorn on `127.0.0.1:8000` ([PM2](../deploy/pm2/README.md), [NGINX](../deploy/nginx/README.md)) |
| Interactive docs | `/docs` |

## Run it locally

```bash
docker compose up -d                 # from the repo root: Postgres 16 with schema, migrations and dev seed
uv sync --all-packages
cp backendAPI/.env.example backendAPI/.env   # then set JWT_SECRET
cd backendAPI
uv run uvicorn main:app --reload --port 8000
```

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | the example matches `compose.yaml` |
| `JWT_SECRET` | yes | at least 32 characters; the API will not start without it |
| `JWT_EXPIRY_HOURS` | no | defaults to 8 |

`.env` is read from this folder, whatever directory the API is started from.

**Development sign-in.** The dev seed creates `dev@compostiq.local` with the password `compostiq-dev`. It exists only in the local Compose database (`database/seed_dev.sql`) and must never be loaded on the VM.

## Layout

| File | What it holds |
|---|---|
| `main.py` | the app, `POST /records` and the device `x-key` authentication |
| `routers/auth.py` | user accounts and the `current_user` dependency |
| `database.py` | the one SQLAlchemy engine everything shares |
| `config.py` | settings, from the environment or `.env` |

## Two kinds of authentication

| Who | Sends | Can reach |
|---|---|---|
| A device | `x-key: <api key>` | `POST /records` only |
| A user | `Authorization: Bearer <JWT>` | `/auth/me`, `/auth/change-password` (and, later, their bins and devices) |

They are separate dependencies. A user token cannot write readings, and a device key cannot reach a user endpoint.

User tokens are JWTs (HS256) carrying `sub` (the user id) and `exp`. They last 8 hours and there are no refresh tokens: the user signs in again. Passwords are stored as argon2id hashes.

## Auth endpoints

| Method | Path | Auth | Body | Success | Errors |
|---|---|---|---|---|---|
| POST | `/auth/register` | none | `{email, password, display_name?}` | 201 token | 409 email already used · 422 invalid |
| POST | `/auth/login` | none | `{email, password}` | 200 token | 401 |
| GET | `/auth/me` | Bearer | | 200 user | 401 |
| PATCH | `/auth/me` | Bearer | `{display_name}` | 200 user | 401 · 422 |
| POST | `/auth/change-password` | Bearer | `{current_password, new_password}` | 204 | 401 · 422 |
| DELETE | `/auth/me` | Bearer | `{password}` | 204 | 401 |

A token response is `{access_token, token_type: "bearer", expires_at, user}` and a user is `{id, email, display_name}`.

- Emails are stored in lower case and compared without regard to case.
- Passwords are 8 to 128 characters. Display names are up to 80; a blank one is stored as empty.
- `POST /auth/login` gives the same 401 body for an unknown email and a wrong password, and takes as long for both.
- **Two kinds of 401.** A missing, invalid or expired token is answered with a `WWW-Authenticate: Bearer` header. A wrong password (login, change-password, delete) is a 401 without that header. Clients use the header to tell "sign in again" from "wrong password".
- `DELETE /auth/me` runs in one transaction. The user's bins are deleted, along with their device assignments, readings and events. The user's devices are kept but unpaired (no owner, inactive, assignment closed) with their API keys revoked, so they can be paired again. Their setup codes are removed.
- Requests to `/auth/` are rate-limited per IP by NGINX in production (429). See the [NGINX README](../deploy/nginx/README.md).

## Tests

```bash
cd backendAPI && uv run pytest
```

These are integration tests against the Compose database; if it is not running they are skipped with a hint. The auth tests register their own users (`pytest-…@example.com`) and remove everything they create.
