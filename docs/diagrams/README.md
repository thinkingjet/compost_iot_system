# Architecture diagrams

How the parts of CompostIQ fit together, how a compost device joins an account and how its readings flow, what owners and researchers each get to see, and how the production VM is laid out and kept running. Every box and arrow is checked against the code on main at 4e51a31 (19 October 2026).

Each diagram comes as an `.svg` (used here and in the top-level README), a `.png` for slides and
reports, and an `.html` page. [`index.html`](index.html) has them all on one page and follows
your light or dark theme; open it from a clone, because GitHub shows HTML as source.


## Contents

- **The system**: [CompostIQ at a glance](#compostiq-at-a-glance), [The data model](#the-data-model)
- **Devices and data**: [Pairing a device](#pairing-a-device), [Registering a device with an API key](#registering-a-device-with-an-api-key), [Readings in, charts, stage and alerts out](#readings-in-charts-stage-and-alerts-out), [The composting cycle](#the-composting-cycle)
- **Owners and researchers**: [Owners and researchers](#owners-and-researchers), [One database, two views](#one-database-two-views)
- **The VM**: [The production VM](#the-production-vm), [How PM2 keeps the apps up](#how-pm2-keeps-the-apps-up)

## The system

The parts, the one rule between them, and what the database holds.

### CompostIQ at a glance

Only the API touches the database. The dashboard, the devices and researchers' own scripts all go through it, each with its own kind of credential.

![CompostIQ at a glance](system-overview.svg)

1. Owners and researchers use the dashboard. It calls the API from its own server with the user's token, so the browser never sees the token or talks to the API.
2. A compost device sends batches of readings with its own key. It gets that key by pairing with a 6-digit code, or the owner registers it and copies the key over by hand. `emulator/` plays the device in demos.
3. The simulator generates a whole composting cycle on a developer's machine and can upload it to `/records` with a device key.
4. Researchers' own scripts read per-country aggregates with a research key created on the dashboard.
5. The public website is plain HTML pages, served straight from the repo.
6. Only the API has the database password. Every rule about who may see or change what is checked there, next to the data.
7. To estimate a bin's composting stage, the API runs the stage model trained in `ml/` on the bin's temperature and moisture readings.

**Notes**

- In production, devices, scripts and the website reach the API through NGINX on one VM, and the dashboard calls it over the VM's loopback address. The production VM diagram shows how.
- Three credentials never stand in for each other: a device key only sends readings, a user token only works for its account type, and a research key only reads research data.

Files: [`system-overview.png`](system-overview.png) · [`system-overview.html`](system-overview.html) · [`specs/system-overview.json`](specs/system-overview.json)

### The data model

A user owns bins and devices. A device is placed in a bin through an assignment that keeps its history, and every reading is stored against the bin it was taken in as well as the device that sent it.

![The data model](data-model.svg)

**Notes**

- Moving a device closes its open assignment and opens a new one, so older readings stay with the bin they were taken in. The database allows only one open assignment per device.
- Deleting an account deletes its bins, and with them their readings and alerts, along with its research keys and pairing codes. Its devices are released (`owner_id` becomes empty) so they can be paired again.
- Left off: `pairing_failures` (wrong pairing codes per address, for the 429 limit) and `device_maintenance`, which the code does not use.

Files: [`data-model.png`](data-model.png) · [`data-model.html`](data-model.html) · [`specs/data-model.json`](specs/data-model.json)

## Devices and data

The two ways a device joins an owner's account, the round trip its readings make, and the composting stages the readings follow.

### Pairing a device

The owner carries a 6-digit code to the device by hand, and the device swaps it for its own key straight from the API. Its readings are refused until the owner gives it a name and a bin.

![Pairing a device](pairing.svg)

1. The owner opens Devices → Pair a device and presses Get pairing code.
2. The dashboard's server asks the API for a code. The API saves it in `setup_codes`: 6 digits, valid for 10 minutes (`PAIRING_CODE_MINUTES`), at most 5 live codes per owner.
3. The owner reads the code off the screen and types it into the device's own web page. The code is the only credential, and it travels by hand.
4. The device sends the code and its hardware ID (its MAC) to the API. After 10 wrong codes from one address in 15 minutes, the API answers 429.
5. In one transaction the API creates the device row, stores a SHA-256 hash of a new key and marks the code used. It returns the key to the device once; the dashboard never sees it.
6. Meanwhile the wizard asks every 2 seconds whether its code has been used. Once it has, it shows which hardware ID used it.
7. The owner checks the ID against the device's page. If it is not theirs, "That's not my device" unpairs it. Otherwise they give it a name and choose or create a bin.
8. `POST /devices/{id}/setup` saves the name and opens the device's bin assignment.
9. Until then every upload got 409, and the device kept only its newest reading and checked again every 10 seconds. Now readings are stored, alert rules are checked, and the wizard shows the device as online.

**Notes**

- The wizard's steps are Pair, Confirm, Set up and Done. Confirm only loads the owner's bins; the setup is saved by Finish setup (step 8).
- A device can also be added with no pairing at all, by registering it with an API key. That path is in the next diagram.
- The device in this demo is `emulator/`, a standard-library Python program that behaves like a sensor and keeps close to what ESP32 firmware could do.

Files: [`pairing.png`](pairing.png) · [`pairing.html`](pairing.html) · [`specs/pairing.json`](specs/pairing.json)

### Registering a device with an API key

With no pairing, the owner sets the name and bin first and copies the key onto the device by hand. Only a device added this way can be given a new key; a paired device gets one by pairing again.

![Registering a device with an API key](manual-registration.svg)

1. The owner chooses Register with API key, then gives the device a name and picks or creates a bin.
2. In one transaction the API adds the device with `registration = 'manual'` and no MAC, puts it in the bin and issues a key. The database only accepts `manual` when the MAC is empty.
3. The key is shown once on the page, with the address to send readings to. The owner copies it onto the device; readings are accepted at once because the bin is already set.

- **A.** A new key is checked three times: the Settings tab only offers the button for a `manual` device, the API refuses anything else with 409, and the database column the API checks is tied to the device having no MAC. A new key revokes the old one straight away.

**Notes**

- The two ways in are kept separate on purpose. Pairing proves the device holds the code; registration trusts the owner to put the key where it belongs.
- The emulator cannot take a key by hand, so this path is tested with `emulator/tools/compostiq_test_device.py`.

Files: [`manual-registration.png`](manual-registration.png) · [`manual-registration.html`](manual-registration.html) · [`specs/manual-registration.json`](specs/manual-registration.json)

### Readings in, charts, stage and alerts out

A batch of readings and the alerts it triggers are saved together or not at all. The dashboard reads them back per bin, only from the signed-in owner's bins, as charts, a stage estimate and alerts with suggested steps.

![Readings in, charts, stage and alerts out](readings-flow.svg)

1. The device takes a reading every 30 seconds and sends what it has queued, up to 50 at a time, to `POST /records` with its key in the `x-key` header.
2. The API looks the key up by its hash. In a transaction of its own it notes the time of contact on the device, so that is kept even when the upload is then refused with 409.
3. If the device is in a bin, each new reading is checked against five rules: above 70 °C, moisture below 30 % or above 70 %, oxygen below 1 %, CO₂ above 12 %. A rule newly broken opens an incident; one back in range resolves it.
4. In the same transaction the readings are saved, each tagged with its device and bin. If anything fails, the alerts and the readings are rolled back together.
5. The dashboard's server asks for a bin's readings (or, on a device's page, `GET /devices/{id}/records`). The API first checks that the bin belongs to the signed-in owner; someone else's bin is answered with 404.
6. The bin's Live tab asks for a stage estimate. The API averages the bin's last 60 days of core temperature and moisture onto a 30-minute grid and runs the stage model from `ml/`. With less than a day of readings it gives no stage.
7. Alert cards show the open incidents plus an `offline` alert for any device in a bin that has not been heard from for 10 minutes. Offline alerts are worked out on each request and never stored. Only the overview page refreshes its cards, every 60 seconds.
8. A bin's Maintenance tab loads that bin's open alerts and shows three suggested steps for each alert type. The steps are written into the dashboard (`MAINTENANCE_STEPS` in `pages.py`), taken from composting guides, and the API holds none of them.

**Notes**

- Every owner-facing read is scoped to the owner in SQL, by `bins.user_id` or `devices.owner_id`.
- There is no ammonia rule: the sensor gives a relative level, not a concentration.
- Offline means 10 minutes in both the alerts and the device cards, but the rules differ: a card looks at the last contact only, while the alert also counts from pairing and covers only devices in a bin. A newly registered device shows Offline at once but raises no alert for 10 minutes.

Files: [`readings-flow.png`](readings-flow.png) · [`readings-flow.html`](readings-flow.html) · [`specs/readings-flow.json`](specs/readings-flow.json)

### The composting cycle

A pile passes through five stages, each with its own expected readings, over about seven weeks. Peak decomposition is the stretch held at 55 °C or above, where pathogens die. The simulator and the emulator generate their readings from these ranges, and the stage model learned from them.

![The composting cycle](compost-stages.svg)

**Notes**

- Holding 55 °C or more for three days in a row kills pathogens: the EPA Class A sanitation target. Peak decomposition starts once the core has held 55 °C for 6 hours. A bin that never gets that hot, like a small Takakura basket, goes straight from active thermophilic to cooling.
- The ranges, their sources and the ammonia level (0 to 1, relative, not ppm) are in `simulator/composting_stages.py`. The floor is 28 °C because the pilot site in Mataram is 24 to 32 °C outside.
- The API estimates a real bin's stage with a model trained in `ml/` on cycles simulated from these ranges. Alerts use their own fixed limits.

Files: [`compost-stages.png`](compost-stages.png) · [`compost-stages.html`](compost-stages.html) · [`specs/compost-stages.json`](specs/compost-stages.json)

## Owners and researchers

Two account types on one platform, and what each sees of the same data.

### Owners and researchers

Everyone signs up on one page and picks an account type once. Each type then gets its own pages, and the API checks the type again on every request, reading it from the database: owners cannot reach research data, and researchers cannot reach bins or devices.

![Owners and researchers](roles-journeys.svg)

1. Both kinds of user start on the same sign-up page and choose Compost owner or Researcher. Owner is preselected.
2. The type is stored in `users.role` as `owner` or `researcher`. It is chosen once: nothing in the dashboard or the API changes it later, and the account page shows it read-only.
3. Each type lands on its own home page with its own menu: `/dashboard` for owners, `/research` (the API keys page) for researchers. Only Account is shared. Opening the other type's page quietly sends you back to your own home page.
4. Owners pair or register devices, create bins, follow them on charts and see alerts.
5. Every dashboard page calls the API from the dashboard's server with the user's token. `require_role` reads the account type from the database and refuses the wrong type with 403, "Not available to researcher accounts." An owner only ever gets rows they own.
6. The Explore data page shows the research figures as a table with a Daily, Overall and Alerts switch and a CSV download. It calls `/research/preview/*` with the researcher's token, so it needs no key.
7. A researcher names and creates a key on the API keys page. The key is shown once; only its SHA-256 hash is stored in `research_apikeys`. Deleting it stops it working at once.
8. The researcher's own scripts call `/research/overview`, `/daily`, `/alerts` and `/countries` with the key in the `x-research-key` header. The API looks the hash up and also checks that the key's account is still a researcher.

**Notes**

- The dashboard's per-type pages are a convenience. The real control is the API's check on every request, using the role stored in the database: the sign-in token carries only the user id and its expiry.
- `POST /pairing/redeem` is the one pairing route with no account check, because the device calls it with a code, not a signed-in user.

Files: [`roles-journeys.png`](roles-journeys.png) · [`roles-journeys.html`](roles-journeys.html) · [`specs/roles-journeys.json`](specs/roles-journeys.json)

### One database, two views

An owner sees every detail of their own bins and nothing of anyone else's. A researcher gets totals and averages per country, by day or over a period, with names, places and IDs left out.

![One database, two views](data-views.svg)

1. Every owner request is answered from the owner's own rows only (`bins.user_id`, `devices.owner_id`). The owner sees exact readings per device, their alerts and their history, and another owner's bin is answered as if it did not exist (404).
2. The research routes select only the country and aggregates. Bins without a `country_code` are left out. Overall gives one row per country for the chosen period (up to 366 days, 30 by default); Daily gives one row per country per UTC day; Alerts gives a count per country and alert type, with the average hours to resolve. Each sensor comes as its average, minimum, maximum and standard deviation.

**Notes**

- Every owner's bins that have a country are included in the research figures. There is no opt-out.

Files: [`data-views.png`](data-views.png) · [`data-views.html`](data-views.html) · [`specs/data-views.json`](specs/data-views.json)

## The VM

One Ubuntu VM, three public sites, two app processes kept alive by PM2.

### The production VM

Only NGINX answers web traffic from the internet. The dashboard, the API and the database listen on the VM's loopback address, and PM2 keeps the two apps running.

![The production VM](vm-overview.svg)

1. A browser looks the name up in DNS, gets the VM's address and connects on port 443. All four names (`compostiq.win`, `www`, `dashboard`, `api`) point at this one VM, and one Let's Encrypt certificate covers them all.
2. NGINX chooses a site by the name that was asked for. `dashboard.compostiq.win` goes to the dashboard on `127.0.0.1:8050`.
3. The dashboard builds each page on the server and calls the API over loopback, never through NGINX. A signed-in user's browser never talks to the API itself.
4. Only the API has the database password. PostgreSQL listens on `127.0.0.1:5432`, and that port is never opened to the outside.

- **A.** `compostiq.win` is plain HTML. Its folder is mounted straight from the repo, so a `git pull` publishes a change with no restart. Its live figures ask `/api/public/*`, which NGINX passes to the API's `/public/*`.
- **B.** Devices send readings to `api.compostiq.win`, and researchers' own scripts call `/research/*` there with a research key. Sign-in and pairing requests on this name are limited to 10 a minute per address before they reach the API; `/research/*` has no limit.

**Notes**

- PM2 runs the dashboard and the API from `deploy/pm2/ecosystem.config.js`. It restarts either app when it crashes or passes 500 MB, and starts both again after a reboot. NGINX and PostgreSQL are ordinary systemd services.
- PM2 reads the one `.env` file and gives each app only the settings it needs, which is how the dashboard never sees `DATABASE_URL`.
- SSH is not part of this picture: the repo holds no firewall settings, and a deploy is done by logging in to the VM.

Files: [`vm-overview.png`](vm-overview.png) · [`vm-overview.html`](vm-overview.html) · [`specs/vm-overview.json`](specs/vm-overview.json)

### How PM2 keeps the apps up

PM2 brings an app back after a crash, a memory overrun or a reboot without anyone logging in. A person is needed only when an app keeps failing as it starts, and for a deploy.

![How PM2 keeps the apps up](vm-reliability.svg)

1. When the VM boots, systemd starts NGINX, PostgreSQL and PM2. Running `pm2 startup systemd` once installed the unit that starts PM2.
2. PM2 comes up and reads the process list that `pm2 save` stored.
3. It starts the dashboard (gunicorn) and the API (uvicorn), each with only its own settings from `.env`.
4. PM2 notices when an app's process exits, or when it grows past `max_memory_restart: 500M`.
5. Unless the app has failed ten times in a row, each time within a second of starting, PM2 restarts it.
6. After `restart_delay` (3 seconds) a fresh process starts and the app is back, usually before anyone notices.

- **A.** Ten quick failures in a row (`max_restarts: 10`) usually means a start-up problem, such as a missing secret. PM2 stops trying and marks the app errored; `pm2 logs` shows why.
- **B.** A deploy is done by hand on the VM: pull, install, stop the API while the database is backed up and any new migrations run, then reload both apps so they pick up new code and settings.

**Notes**

- Only quick failures count towards the ten. An app that runs for a while and then crashes is restarted every time. This is PM2's documented `min_uptime` behaviour (1 second by default), not something set in this repo.
- PM2 restarts a process that has exited, not one that is up but not answering. The repo has no health check or uptime monitor.
- Logs are rotated by `pm2-logrotate`: 10 MB a file, 7 files kept. A `git pull` alone publishes the website, but an NGINX config change also has to be copied into `/etc/nginx` and reloaded.

Files: [`vm-reliability.png`](vm-reliability.png) · [`vm-reliability.html`](vm-reliability.html) · [`specs/vm-reliability.json`](specs/vm-reliability.json)

## Changing a diagram

The JSON files in [`specs/`](specs) are the source. The pictures are drawn from them by the
architecture-flowmaps skill for Claude Code:

```bash
python3 ~/.claude/skills/architecture-flowmaps/scripts/flowmap.py render specs/pairing.json --png -o .
```

```bash
python3 ~/.claude/skills/architecture-flowmaps/scripts/flowmap.py page manifest.json -o index.html
```

Run both from this folder, then run `python3 build_gallery.py` to rebuild this page so its steps
match the specs. When the code
changes, check it first, then edit the spec.
