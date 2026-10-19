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
| `PAIRING_CODE_MINUTES` | no | how long a pairing code stays valid; defaults to 10 |
| `ML_DIR` | no | the compost stage model's code, `predict.py` and `features.py` ([below](#compost-stage-estimate)); defaults to the repo's `ml/` |
| `STAGE_MODEL_PATH` | no | the model bundle; defaults to `ML_DIR/models/compost_stage_gb.joblib` |
| `STAGE_MODEL_PARAMS` | no | a JSON file replacing the bundle's features, stage names and/or stage filter; unset = the bundle's own |

`.env` is read from this folder, whatever directory the API is started from.

**Development sign-in.** The dev seed creates `dev@compostiq.local` with the password `compostiq-dev`. It exists only in the local Compose database (`database/seed_dev.sql`) and must never be loaded on the VM.

## Layout

| File | What it holds |
|---|---|
| `main.py` | the app, `POST /records` and the device `x-key` authentication |
| `routers/auth.py` | user accounts, and the `current_user` and `owner_only` dependencies |
| `routers/pairing.py` | pairing codes: issue, check, and redeem one for a device key |
| `routers/devices.py` | the user's devices: register without pairing, list, set up (name + bin), new key, unpair |
| `routers/bins.py` | the user's bins: list, create, read, readings, daily history, stage estimate |
| `routers/alerts.py` | the alert rules, run on each upload to `POST /records`, and `GET /alerts` |
| `routers/research_keys.py` | a researcher's API keys, and the `x-research-key` check |
| `routers/research_data.py` | the anonymised country aggregates under `/research/*` |
| `routers/public.py` | the website's figures under `/public/*`: no key, totals and countries only |
| `stage_model.py` | loads the compost stage classifier once at startup (from the settings above), checks it, and runs it on a bin's readings |
| `database.py` | the one SQLAlchemy engine everything shares |
| `config.py` | settings, from the environment or `.env` |

## Two kinds of authentication

| Who | Sends | Can reach |
|---|---|---|
| A device | `x-key: <api key>` | `POST /records` only |
| A device, before it has a key | a pairing code | `POST /pairing/redeem` only |
| A user | `Authorization: Bearer <JWT>` | `/auth/*`; and, for owner accounts only, `/pairing/codes`, `/devices`, `/bins`, `/alerts` (their own only) |
| A researcher's script | `x-research-key: <research key>` | `/research/overview`, `/research/daily`, `/research/alerts`, `/research/countries` |
| Anyone | nothing | `/public/stats`, `/public/bins-by-country`, `/public/trends` |

They are separate dependencies. A user token cannot write readings, and a device key cannot reach a user endpoint.

### Account types

Every account has a `role`, chosen at sign-up (migration 005). The two are exclusive:

| Role | Can reach |
|---|---|
| `owner` | `/auth/*`, and their bins, devices, alerts and pairing codes |
| `researcher` | `/auth/*` and anonymised, read-only country aggregates under `/research/*` |

**Owner-only endpoints.** The `owner_only` dependency (`require_role("owner")` in `routers/auth.py`) guards:

- every endpoint under `/bins`, `/devices` and `/alerts` (set on the whole router)
- `POST /pairing/codes` and `GET /pairing/codes/{code}`

A researcher's token gets **403** `{"detail": "Not available to researcher accounts."}` from all of them. There is no `WWW-Authenticate` header, so a client doesn't mistake it for an expired token. The 403 comes before any lookup, so it doesn't reveal whether a bin or device exists. The role is read from the database on every request, not from the token, so a token issued before a role change can't keep the old access. Nothing in the API changes the role after sign-up.

`/auth/*` works for both roles. The endpoints a device calls (`POST /records` with its `x-key`, `POST /pairing/redeem` with a code) have no user and are unaffected.

User tokens are JWTs (HS256) carrying `sub` (the user id) and `exp`. They last 8 hours and there are no refresh tokens: the user signs in again. Passwords are stored as argon2id hashes.

## Auth endpoints

| Method | Path | Auth | Body | Success | Errors |
|---|---|---|---|---|---|
| POST | `/auth/register` | none | `{email, password, display_name?, role?}` | 201 token | 409 email already used · 422 invalid |
| POST | `/auth/login` | none | `{email, password}` | 200 token | 401 |
| GET | `/auth/me` | Bearer | | 200 user | 401 |
| PATCH | `/auth/me` | Bearer | `{display_name}` | 200 user | 401 · 422 |
| POST | `/auth/change-password` | Bearer | `{current_password, new_password}` | 204 | 401 · 422 |
| DELETE | `/auth/me` | Bearer | `{password}` | 204 | 401 |

A token response is `{access_token, token_type: "bearer", expires_at, user}` and a user is `{id, email, display_name, role}`.

- `role` is `owner` or `researcher` ([Account types](#account-types)). Leaving it out of `/auth/register` makes an owner.
- Emails are stored in lower case and compared without regard to case.
- Passwords are 8 to 128 characters. Display names are up to 80; a blank one is stored as empty.
- `POST /auth/login` gives the same 401 body for an unknown email and a wrong password, and takes as long for both.
- **Two kinds of 401.** A missing, invalid or expired token is answered with a `WWW-Authenticate: Bearer` header. A wrong password (login, change-password, delete) is a 401 without that header. Clients use the header to tell "sign in again" from "wrong password".
- `DELETE /auth/me` runs in one transaction. The user's bins are deleted, along with their device assignments, readings and events. The user's devices are kept but unpaired (no owner, inactive, assignment closed) with their API keys revoked, so they can be paired again. Their setup codes are removed.
- Requests to `/auth/` are rate-limited per IP by NGINX in production (429). See the [NGINX README](../deploy/nginx/README.md).

## Pairing a device

Pairing (the device gets its key) and setup (the user names it and picks a bin) are separate steps, so a pairing code carries nothing but the account.

1. The dashboard asks for a code: `POST /pairing/codes`.
2. The user types it into the device's own page, and the device calls `POST /pairing/redeem` with the code and its hardware ID (MAC). It gets its API key back, once. The device now belongs to the user but has no bin, so `/records` answers **409** and the device waits.
3. The dashboard polls `GET /pairing/codes/{code}` until it says `redeemed`, and shows which hardware ID used the code. The user checks it matches the device.
4. The user presses **Confirm registration**, and the dashboard calls `POST /devices/{id}/setup` with a name and a bin (creating the bin first with `POST /bins` if it's new). From then on `/records` accepts the device's readings.

If the hardware ID doesn't match, "That's not my device" calls `DELETE /devices/{id}`, which revokes the new key at once. The full sequence diagram, and how the device behaves at each step, is in the [emulator README](../emulator/README.md#pairing).

| Method | Path | Auth | Body | Success | Errors |
|---|---|---|---|---|---|
| POST | `/pairing/codes` | Bearer | | 201 `{code, expires_at}` | 401 |
| GET | `/pairing/codes/{code}` | Bearer | | 200 `{code, status, expires_at, device}` | 401 · 404 (not this user's code) |
| POST | `/pairing/redeem` | the code | `{code, device_uid, model?, firmware_version?}` | 201 `{device_id, api_key}` | 404 unknown · 409 already used · 410 expired · 422 · 429 too many wrong codes |
| POST | `/devices` | Bearer | `{name, bin_id}` | 201 `{device, api_key}` | 401 · 404 bin not the user's · 422 |
| GET | `/devices` | Bearer | | 200 list of devices | 401 |
| GET | `/devices/{id}` | Bearer | | 200 device | 401 · 404 |
| POST | `/devices/{id}/setup` | Bearer | `{name, bin_id}` | 200 device | 401 · 404 device or bin not the user's · 422 |
| POST | `/devices/{id}/key` | Bearer | | 201 `{device, api_key}` | 401 · 404 · 409 a paired device |
| DELETE | `/devices/{id}` | Bearer | | 204 | 401 · 404 |
| GET | `/bins` | Bearer | | 200 list of bins | 401 |
| POST | `/bins` | Bearer | `{name, location?, country_code}` | 201 bin | 401 · 422 |
| GET | `/bins/{id}/stage?days=60` | Bearer | | 200 stage estimate ([below](#compost-stage-estimate)) | 401 · 404 · 422 · 503 no model |

Every Bearer endpoint in this table is [owner-only](#account-types): a researcher account gets 403.

`status` is `pending`, `expired` or `redeemed`; once redeemed, `device` is the device that used it. A device is `{id, hardware_id, registration, name, model, firmware_version, paired_at, last_seen_at, bin: {id, name} | null, set_up}`, where `set_up` means it has a name and a bin, so its readings are accepted. `registration` is `pairing` or `manual` (below); a manual device's `hardware_id` is `null`.

- **Codes** are 6 digits (leading zeros kept), valid for `PAIRING_CODE_MINUTES`, and used once. Only live codes have to be unique, so a number can come round again later. A user can hold up to 5 live codes; asking for more drops the oldest.
- **Guessing is limited.** Every wrong, used or expired code sent to `/pairing/redeem` is counted per client IP in `pairing_failures`. After 10 in 15 minutes that IP gets 429 until the oldest fall out of the window. The count lives in the database because PM2 runs two API workers. NGINX also rate-limits `/pairing/` in production.
- **Keys** are 64 hex characters from `secrets`. Only their SHA-256 hash is stored, as `/records` expects, and the key is only ever in the redeem (or register) response.
- **Pairing hardware again** (after a factory reset, or passing the device on) reuses its `devices` row. Its old keys are revoked, and it leaves its bin and loses its name, so the new owner sets it up from scratch.
- **Someone else's device or bin** is always a 404, never a 403.
- `/records` also rejects a key whose device is inactive (unpaired), and records `last_seen_at` on every call, including the 409s before setup, so the dashboard can see a device is in contact.

## Registering a device without pairing

For hardware that can't run the pairing flow. `POST /devices` with a name and one of the user's bins creates the device, puts it in the bin and returns `{device, api_key}`. The key is in that response only; the dashboard shows it once for the user to copy onto the device, and never stores it. There is no code and no confirm step, and nothing is learnt from the hardware, so the device has no hardware ID (`devices.mac` is null, migration 004) and its readings are accepted straight away.

A lost or leaked key is replaced with `POST /devices/{id}/key`: the old key stops working at once and the new one is returned, once, the same way. The dashboard offers this as **New API key** on the device's settings tab.

**Only registered devices can get a new key.** A paired device has to receive its key itself, so it gets a new one by being paired again, which revokes the old one too. This is enforced in three places:

- **The database.** `devices.registration` (`pairing` or `manual`, migration 004) is set when the device is created and nothing changes it. Two checks keep it `manual` exactly when the device has no MAC, so a paired device can't be marked as registered by any code path.
- **The API.** `POST /devices/{id}/key` reads that column, with the device row locked, and answers 409 for anything but `manual`, without revoking or adding a key. `PATCH /devices/{id}` ignores a `registration` field.
- **The dashboard.** It only shows the button for registered devices, refuses to open the dialog for a paired one, and shows the API's 409 as a plain message.

Everything else is shared with paired devices: `DELETE /devices/{id}` revokes the key, and if the device's bin is deleted it goes back to "not set up" (409 on `/records`) until `POST /devices/{id}/setup` gives it another bin. It keeps its key throughout.

## Compost stage estimate

`GET /bins/{id}/stage` estimates which of the five composting stages a bin is in, with the gradient-boosting classifier from [ml/](../ml/README.md). The API loads `ml/models/compost_stage_gb.joblib` once at startup with `ml/predict.py`'s `load_model()`, and runs `predict_readings()` on the bin's readings.

**Swapping the model.** The model is two files, set in the environment (or `.env`), so it can be replaced without a code change. Paths are absolute or relative to `backendAPI/`, and are read at startup, so restart the API after changing one.

| Variable | What it points to | Unset |
|---|---|---|
| `STAGE_MODEL_PATH` | the bundle `ml/train.py` writes (`format: compost-stage-gb/1`): the fitted classifier, its `features`, `stage_names` and stage-filter `transitions` | `ML_DIR/models/compost_stage_gb.joblib` |
| `STAGE_MODEL_PARAMS` | JSON with any of `features`, `stage_names` and `transitions`, replacing the bundle's | the bundle's own |
| `ML_DIR` | the code that runs the model: `predict.py` and `features.py` | the repo's `ml/` |

`uv run python stage_model.py` (from `backendAPI/`) shows which model these settings load, and `--export-params FILE` writes its parameters as a file to edit. Typically you'd edit `transitions` (each row: the hourly chances of staying in a stage or moving on, adding up to 1) to make the stage filter quicker or slower, or rename `stage_names`. The dashboard shows whatever stages the model has. `features` must stay the columns the classifier was fitted on, in order, so a new feature set needs a new bundle.

**Startup checks.** The API won't start, and says which setting is wrong, when a model or parameters file it was asked for is missing, can't be read, isn't a model bundle, was saved with another scikit-learn minor version, or doesn't fit together (features not the fitted ones, a stage-name count that doesn't match the classes, transitions that aren't a square matrix of rows adding up to 1, unknown keys in the parameters file). The model also has to get through a two-day test batch. The one exception is the default setup, with no variables set and no model file in `ML_DIR/models`: then the model isn't installed, the API starts without it, and this endpoint answers 503.

- **Input.** The bin's last `days` (1–365, default 60) of `records`, every sensor in the bin averaged onto a 30-minute grid in SQL (the grid `ml/features.py` uses), as `timestamp`, `temperature_c` and `moisture_pct`. The records table has no ambient probe or MQ-135, so the model assumes 28 °C ambient. The gas columns are not used: the model was trained without them.
- **Output.** `{stage_id, stage, raw_stage, confidence, probabilities, last_reading_at, history_hours}`. `stage` is predict.py's `stage_filtered`: the latest hour after its forward-only stage filter, which is what to show. `raw_stage` is the latest hour on its own, `confidence` that stage's probability, and `probabilities` every stage's probability for that hour. `last_reading_at` is the newest reading used.
- **Not enough history.** The model's features look back 24 hours, so with under a day of readings the stage fields are `null` (and `probabilities` is empty), with `history_hours` saying how much there is.
- **One batch.** The model remembers how hot the pile has been since it started, so more history is better, but readings from a previous batch mislead it. Nothing records when fresh feedstock goes in yet, so the window is the only control.
- **No model.** Not installed (above): 503. The current model was saved with scikit-learn 1.9, which `pyproject.toml` pins (`>=1.9,<1.10`).
- **The emulator.** The model reads timestamps as real time, and by default the emulator gives it what it needs: 5 days of a batch's history at real-time spacing the first time the cloud takes its readings, then live readings at `TIME_SCALE=1`. Its page's **Starting point** card sets how many days, and the stage and how far through it the batch begins ([emulator README](../emulator/README.md#the-starting-point)). At a `TIME_SCALE` above 1 the live pile runs ahead of its timestamps and the estimate can't follow it for long.

## Research data API

A researcher selects the **researcher** account type at registration, then creates a key on the dashboard's **API keys** page (up to five). Send that key as `x-research-key`. Owner tokens and device keys cannot call these endpoints. The signed-in dashboard's **Explore data** page uses the equivalent `/research/preview/*` routes with the researcher's Bearer token.

| Endpoint | Returns |
|---|---|
| `GET /research/daily` | one row per country per UTC day |
| `GET /research/overview` | one row per country for the whole window |
| `GET /research/alerts` | one row per country and alert type: how many, in how many bins, average hours to resolve |
| `GET /research/countries` | every country with readings: bins, readings, first and last reading. No parameters |

The first three accept optional `country_code` (two-letter ISO code), `start` and `end` (ISO 8601 timestamps with timezone), and `format` (`json` or `csv`). The default window is the last 30 days; the maximum is 366 days. The end is exclusive. Reading rows carry the contributing bin and reading counts and each sensor's average, minimum, maximum and standard deviation. Names, locations, account IDs, device IDs, bin IDs and individual readings are never returned, and bins without a country are left out. Groups appear whenever they contain readings, regardless of the number of owners.

```bash
curl -H "x-research-key: $RESEARCH_API_KEY" \
  'http://127.0.0.1:8000/research/daily?country_code=ID&start=2026-10-01T00:00:00Z&end=2026-10-16T00:00:00Z'
```

## Public figures

`routers/public.py` serves the figures on the public website. They need no key, and NGINX passes `compostiq.win/api/public/...` through to them.

| Endpoint | Returns |
|---|---|
| `GET /public/stats` | `bins` and `countries` that have sent readings, `active_devices` (in a bin and heard from in the last 10 minutes), `readings_total`, `readings_24h`, `first_reading_at`, `last_reading_at`, `updated_at` |
| `GET /public/bins-by-country` | `[{country_code, bins}]`, bins that have sent readings, most first |
| `GET /public/trends` | `{days: [{date, temperature_c, moisture_percent}]}`: the daily averages across every bin for the last 30 UTC days, with `null` on a day without readings |

Anyone can call them, so each answer is kept in memory for 60 seconds rather than counting every reading on every page view.

## Tests

```bash
cd backendAPI && uv run pytest
```

These are integration tests against the Compose database; if it is not running they are skipped with a hint. The auth tests register their own users (`pytest-…@example.com`) and remove everything they create. The pairing tests (`tests/test_pairing.py`) cover every step above, including expired, reused and guessed codes, another user's device or bin, re-pairing and unpairing, and remove their devices (`02:00:00:00:FD:…`) afterwards. The registration tests (`tests/test_registration.py`) cover registering, the key working at once, another user's bin, unpairing, setting a device up again after its bin is deleted, replacing a key, and the paired-device rules above (409 with nothing revoked, `registration` can't be changed through the API, the database checks reject a mismatched row), and remove the devices they register. The account-type tests (`tests/test_roles.py`) send a researcher's token to every endpoint under the owner-only prefixes, read from the app's OpenAPI schema so new endpoints are covered too, and check that owners still get through and `/auth` still works for a researcher. The stage tests (`tests/test_stage.py`) send hand-drawn piles (warming up, hot, cooled down) and check the estimate is in the right part of the cycle, the under-a-day and no-readings answers, the window, the owner checks, and the 503 without a model; the ones that need the model are skipped with a hint if the API couldn't load it. The model-loading tests (`tests/test_stage_model.py`) cover the defaults, `STAGE_MODEL_PATH` and `STAGE_MODEL_PARAMS` overrides (custom stage names reach the endpoint), each kind of bad file, the not-installed case, and that the API refuses to start with a bad path.
