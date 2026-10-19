# CompostIQ

**An IoT system that monitors compost bins and tells people what to do next.**

Sensors inside a compost bin report temperature, moisture, oxygen, carbon dioxide and ammonia to the cloud. Owners follow their bins on a web dashboard: live charts, a 30-day history, an estimate of which composting stage each bin is in, and alerts that come with steps for putting things right. Researchers get their own accounts and API keys, and read per-country figures drawn from every bin, with no names, places or IDs.

CompostIQ is an RMIT capstone project, built around a pilot site in Mataram, Indonesia.

## Contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [The systems](#the-systems)
- [How it works](#how-it-works)
- [Security model](#security-model)
- [Who sees what](#who-sees-what)
- [Data model](#data-model)
- [The composting cycle and alerts](#the-composting-cycle-and-alerts)
- [Deployment](#deployment)
- [Getting started](#getting-started)
- [Repository layout](#repository-layout)
- [Documentation](#documentation)

## What it does

| For | CompostIQ provides |
|---|---|
| **Compost owners** | A dashboard for their own bins and devices. Pair a device with a 6-digit code or register it with an API key, follow live and 30-day charts, see which composting stage each bin is in, get alerts with suggested fixes, and remove a device when it is retired |
| **Researchers** | A separate account type with up to five API keys, and per-country aggregates of the readings and alerts from every bin with a country, by day or over a period, as JSON or CSV. An Explore data page shows the same figures in the browser |
| **The public** | A website at `compostiq.win` with country-level totals, an open-data page for researchers, and API docs |
| **Developers** | An emulator that behaves like a real device, and a simulator that generates whole composting cycles, so the system can be built and tested without a physical bin |

## Architecture

The rule that shapes the design: **only the API touches the database.** The dashboard, the devices and researchers' own scripts all go through it, and each uses its own kind of credential.

![CompostIQ at a glance: people, the clients they use, the API and the database](docs/diagrams/system-overview.svg)

Four ideas follow from that rule:

1. **The API is the single gatekeeper.** Every rule about who may see or change what is checked in one place, next to the data, using the account type stored in the database.
2. **The browser never talks to the API for the dashboard.** The dashboard's server makes the calls, so a user's token never reaches browser JavaScript.
3. **Three credentials that cannot stand in for each other.** A device key only sends readings, a user token only works for its account type, and a research key only reads research data.
4. **The emulator is just a device.** It pairs and uploads through the same endpoints, with the same kind of key, that a physical device would use, so nothing in the cloud is emulator-specific.

All ten diagrams, with numbered steps and notes, are in [`docs/diagrams`](docs/diagrams/README.md).

## The systems

| System | What it does | Built with | Folder |
|---|---|---|---|
| **API** | Receives readings, runs the alert rules, estimates each bin's composting stage, manages accounts, pairing, bins and devices, and serves research data and the website's public figures. The only path to the database | FastAPI, SQLAlchemy Core, PyJWT, pwdlib (argon2) | [`backendAPI/`](backendAPI/README.md) |
| **Dashboard** | Sign-up and sign-in, then separate pages for owners (bins, devices, alerts) and researchers (API keys, Explore data, docs) | Dash, dash-mantine-components, Plotly | [`monitoringSystem/`](monitoringSystem/README.md) |
| **Website** | The public site: landing page, open data, quickstart, API reference and security pages | Plain HTML, CSS and JavaScript | [`website/`](website/README.md) |
| **Emulator** | One emulated device with its own web page. It pairs with a dashboard code, models a live compost pile and uploads a reading every 30 seconds | Python standard library, Docker | [`emulator/`](emulator/README.md) |
| **Simulator** | Generates a whole composting cycle on a developer's machine, charts it, and can upload it to the API | Dash, pandas, Plotly | [`simulator/`](simulator/README.md) |
| **Stage model** | A gradient-boosting classifier, trained on simulated cycles, that estimates a bin's composting stage from its temperature and moisture. The API loads it at start | scikit-learn, pandas | [`ml/`](ml/README.md) |
| **Database** | 11 tables. Schema changes are versioned as migrations `002` to `006` | PostgreSQL 16 | [`database/`](database/README.md) |
| **Deployment** | Runs the API and dashboard on one VM behind HTTPS, and serves the website | NGINX, PM2, Let's Encrypt | [`deploy/`](deploy/pm2/README.md) |

## How it works

### Adding a device

The owner gets a 6-digit code from the dashboard and types it into the device's own web page. The device swaps the code for its API key directly with the API, so the key never passes through the dashboard. The device's readings are refused (409) until the owner confirms the hardware ID and gives the device a name and a bin.

![Pairing a device: owner, dashboard, API and device, from code to first reading](docs/diagrams/pairing.svg)

A device can also be added without pairing. The owner chooses **Register with API key**, gives a name and a bin, and copies the key, shown once, onto the device. Only a device added this way can be given a new key later; a paired device gets one by pairing again. See [Registering a device with an API key](docs/diagrams/README.md#registering-a-device-with-an-api-key).

### A reading's journey

A device takes a reading every 30 seconds and uploads them in batches to `POST /records` with its key. The API checks the readings against the alert rules and saves the readings and any alerts in one transaction, so either both are stored or neither is. The dashboard reads them back per bin, and only from the signed-in owner's bins.

![Readings in, charts, stage and alerts out](docs/diagrams/readings-flow.svg)

Each reading holds a timestamp, temperature, moisture, oxygen, carbon dioxide and a relative ammonia level (0 to 1). A bin's **Maintenance** tab turns each open alert into three suggested steps.

### Estimating the composting stage

A bin's **Live** tab opens with the composting stage the API estimates from the bin's readings (`GET /bins/{id}/stage`). The API averages the last 60 days of core temperature and moisture onto a 30-minute grid and runs the stage model from [`ml/`](ml/README.md) on them. The model needs a day of readings, and a forward-only filter keeps the stage from flickering back. The dashboard shows the result as a model estimate, with its confidence.

### Signing in and account types

Everyone signs up on the same page and chooses **Compost owner** or **Researcher** once. The API issues a token valid for 8 hours. The dashboard keeps it in a signed, HttpOnly session cookie that browser scripts cannot read, and checks the account type on every private page. When the token expires the user signs in again and returns to the page they were on.

![Owners and researchers: one sign-up, separate pages, checked by the API on every request](docs/diagrams/roles-journeys.svg)

The dashboard's separate pages are a convenience. The real control is in the API: `require_role` reads the account type from the database on every request and refuses the wrong type with 403.

## Security model

| Caller | Credential | Stored as | Allowed to |
|---|---|---|---|
| **Device** | API key in the `x-key` header | SHA-256 hash, revocable | Send readings. Nothing else |
| **Device being paired** | 6-digit code, typed in by the owner | Valid 10 minutes, used once | Swap the code for its API key, once |
| **Owner** | Token (JWT), valid 8 hours | Not stored | Manage their own account, bins, devices and alerts |
| **Researcher** | Token (JWT), valid 8 hours | Not stored | Manage their own account and research keys, and read research data in the dashboard |
| **Researcher's script** | Research key in the `x-research-key` header | SHA-256 hash; deleting it revokes it | Read research data |

- Passwords are stored as argon2id hashes.
- Ownership is checked in the database query itself, so an owner can only ever reach their own data. Someone else's bin is answered as if it did not exist (404).
- The sign-in token carries only the user's id and its expiry. The account type is read from the database on every request, and a research key works only while its account is a researcher's.
- The dashboard holds no database credentials. In production it is not even given the database address.
- NGINX allows 10 requests a minute per address to `/auth/` and `/pairing/`. The API also refuses pairing from an address that has entered 10 wrong codes in 15 minutes.

## Who sees what

The same database reaches each audience through its own filter.

![One database, two views: owner and researcher](docs/diagrams/data-views.svg)

- **Owners** see every detail of their own bins: exact readings per device, alerts and a daily history.
- **Researchers** get one row per country, for each UTC day (Daily) or for the whole chosen period (Overall), up to 366 days. Each row has bin and reading counts and the average, minimum, maximum and standard deviation of each sensor; Alerts gives counts and the average hours to resolve. Names, emails, locations, MACs and database IDs are never selected, and bins without a country are left out.
- **The public** sees totals only, on the website, from the API's keyless `/public` endpoints: how many bins, countries and active devices, bins per country, and 30 days of daily average temperature and moisture.

## Data model

A user owns bins and devices. A device is placed in a bin through an assignment that keeps its history, and every reading is stored against both the bin it was taken in and the device that sent it.

![The data model: users, bins, devices, assignments, readings, alerts and keys](docs/diagrams/data-model.svg)

| Table | Holds |
|---|---|
| `users` | Accounts, with their account type (`owner` or `researcher`) |
| `bins` | Compost bins, each owned by one user, with an optional country |
| `devices` | Sensor devices, each owned by one user once paired or registered |
| `device_bin_assn` | Which device is in which bin, and when |
| `device_apikeys` | Hashed device keys, which can be revoked |
| `setup_codes` | Pairing codes, and which device redeemed each one |
| `pairing_failures` | Wrong pairing codes per address, for the rate limit |
| `records` | Sensor readings, each with its bin and the device that sent it |
| `bin_events` | Alerts raised for a bin, open or resolved |
| `research_apikeys` | Researchers' hashed API keys |
| `device_maintenance` | Reserved for a device maintenance schedule; the code does not use it |

- **Assignments keep their history.** Moving a device closes one assignment and opens another, so old readings stay with the bin they were taken in.
- **Deleting an account** removes its bins, readings, alerts, pairing codes and research keys, and releases its devices so they can be paired again.

## The composting cycle and alerts

Compost passes through five stages, each with its own expected readings. The simulator and the emulator generate their readings from these ranges, and the stage model was trained on cycles generated from them.

![The composting cycle: five stages with their temperature, moisture, oxygen, CO₂ and length](docs/diagrams/compost-stages.svg)

One milestone matters most: holding **55 °C or above for three days in a row** kills pathogens, which is the EPA Class A sanitation target. Peak decomposition is that stretch: it starts once the core has held 55 °C for 6 hours, and a bin that never gets that hot, like a small Takakura basket, goes straight from active thermophilic to cooling. The dashboard draws the 55 °C line on a bin's history chart. The ranges and their sources are in [`simulator/composting_stages.py`](simulator/composting_stages.py).

Alerts use fixed limits, set in [`backendAPI/routers/alerts.py`](backendAPI/routers/alerts.py):

| Alert | Raised when | Priority |
|---|---|---|
| `too_hot` | Temperature above 70 °C | High |
| `low_oxygen` | Oxygen below 1 % | High |
| `too_dry` | Moisture below 30 % | Medium |
| `too_wet` | Moisture above 70 % | Medium |
| `high_co2` | Carbon dioxide above 12 % | Medium |
| `offline` | A device in a bin has not been heard from for 10 minutes | Medium |

An alert opens when a new reading breaks its rule and resolves when a reading is back in range. Offline alerts are worked out on each request and never stored. There is no ammonia rule.

## Deployment

One Ubuntu VM serves three sites under one certificate: the website at `compostiq.win`, the dashboard at `dashboard.compostiq.win` and the API at `api.compostiq.win`. Only NGINX answers web traffic. The dashboard, the API and PostgreSQL listen on the VM's loopback address, and PM2 restarts the two apps after a crash, a memory overrun or a reboot.

![The production VM: NGINX, PM2, the dashboard, the API and PostgreSQL](docs/diagrams/vm-overview.svg)

How PM2 recovers, and when a person is needed, is in [How PM2 keeps the apps up](docs/diagrams/README.md#how-pm2-keeps-the-apps-up). The setup steps are in [`deploy/pm2/README.md`](deploy/pm2/README.md) and [`deploy/nginx/README.md`](deploy/nginx/README.md).

## Getting started

You need [Docker](https://docs.docker.com/get-docker/) and [uv](https://docs.astral.sh/uv/). Run each command from the repository root.

> **Docker is only used locally**, for the development database and, if you like, the emulator. The API, dashboard, website and simulator run directly with Python, and the production VM does not use Docker.

**1. Set the local database password.** Compose reads it from a `.env` file in the repository root, and `backendAPI/.env.example` expects `compostiq_dev`.

```bash
printf 'POSTGRES_PASSWORD=compostiq_dev\n' >> .env
```

**2. Start the database.** The first start loads the schema, the migrations and a development user.

```bash
docker compose up -d
```

**3. Install the dependencies.**

```bash
uv sync --all-packages
```

**4. Create the local settings files**, then set `JWT_SECRET` and `DASHBOARD_SECRET_KEY` inside them. Each file explains how to generate a value.

```bash
cp backendAPI/.env.example backendAPI/.env
```

```bash
cp monitoringSystem/.env.example monitoringSystem/.env
```

**5. Start the API**, in its own terminal.

```bash
uv run --directory backendAPI uvicorn main:app --port 8000
```

**6. Start the website**, in another terminal. The dashboard's `/` and Log out go here.

```bash
uv run python -m http.server 8070 --bind 127.0.0.1 --directory website/public
```

**7. Start the dashboard**, in a third terminal.

```bash
uv run python monitoringSystem/app.py
```

Open <http://127.0.0.1:8050/register> and create an account, or sign in at `/login` as the development user described in [`backendAPI/README.md`](backendAPI/README.md). The development data has no researcher and its bin has no country, so the research pages stay empty until a bin with a country has readings.

**8. Add a device (optional).** Run the emulator in Docker and point it at your API by setting `CLOUD_API_URL=http://host.docker.internal:8000` in `emulator/.env`. Without that line it talks to the production cloud.

```bash
cp emulator/.env.example emulator/.env
```

```bash
docker compose -f emulator/compose.yaml up -d --build
```

Open the device's page at <http://127.0.0.1:8080>, then in the dashboard choose **Pair a device** → **Get pairing code** and type the code into the device's page. [`emulator/README.md`](emulator/README.md) has the details, a second device and a fake cloud for working offline.

**Tests.** The API's tests need the database from step 2; without it they are skipped.

```bash
uv run --directory backendAPI pytest
```

The emulator's tests need nothing else running.

```bash
python3 -m unittest discover -s emulator/tests -t emulator
```

The simulator is optional and runs on port 8051 (`uv run python simulator/app.py`). To upload a cycle, register a device with an API key in the dashboard, then set `API_URL=http://127.0.0.1:8000` and `SIMULATOR_API_KEY` to that key in `simulator/.env` (copy `simulator/.env.example`). See its [README](simulator/README.md).

## Repository layout

```text
compost_iot_system/
├── backendAPI/                    The API, and its tests
├── monitoringSystem/              The dashboard
├── website/                       The public website (static files)
├── emulator/                      The emulated device, its tests and a test-device tool
├── simulator/                     The composting-cycle simulator
├── ml/                            The stage model: training data, training code and the exported model
├── database/                      Schema, migrations, development seed and checks
├── deploy/                        NGINX and PM2 configuration for the VM
├── docs/                          The storyboard, and the architecture diagrams with their specs
├── slides/                        The project overview deck
├── mock-data/                     Sample readings and the schema they follow
├── Archive/                       The original prototype, kept for reference
├── mock-api-schema.openapi.json   The August draft of the research API, used only by Archive/
├── compose.yaml                   The local development database
├── pyproject.toml, uv.lock        The Python workspace and its locked dependencies
└── .env.example                   Settings for the VM, which PM2 shares out to each app
```

## Documentation

| To learn about | Read |
|---|---|
| How the parts fit together, in ten diagrams with numbered steps | [`docs/diagrams/README.md`](docs/diagrams/README.md) |
| Endpoints, authentication and running the API | [`backendAPI/README.md`](backendAPI/README.md) |
| Pages, sign-in and the structure of the dashboard | [`monitoringSystem/README.md`](monitoringSystem/README.md) |
| Running the emulated device, pairing it and its API contract | [`emulator/README.md`](emulator/README.md) |
| Generating and inspecting composting cycles | [`simulator/README.md`](simulator/README.md) |
| Training and using the stage model | [`ml/README.md`](ml/README.md) |
| The public website and how it is published | [`website/README.md`](website/README.md) |
| The schema, and how to apply a migration safely | [`database/README.md`](database/README.md) |
| Setting up the VM | [`deploy/pm2/README.md`](deploy/pm2/README.md), [`deploy/nginx/README.md`](deploy/nginx/README.md) |
