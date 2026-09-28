# CompostIQ Dash monitoring system

The monitoring UI is implemented entirely with
[Plotly Dash](https://dash.plotly.com/) and Python. It includes device and bin
onboarding, overview cards, dedicated device/bin pages, live telemetry,
maintenance tasks, historical analytics, and settings.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:8050`.

Dedicated pages include:

- `/device/live`
- `/device/history`
- `/device/settings`
- `/bin/live`
- `/bin/maintenance`
- `/bin/history`
- `/bin/devices`
- `/bin/settings`

## Structure

- `app.py` — Dash server, routing, stores, and callbacks.
- `components.py` — reusable layout, card, navigation, form, and graph factories.
- `pages.py` — page-level compositions built from reusable components.
- `figures.py` — all Python Plotly figure factories and shared graph settings.
- `data.py` — deterministic placeholder data.
- `assets/styles.css` — visual design and responsive styles loaded automatically by Dash.

All visualizations, including sparklines, are Dash `dcc.Graph` components using
Python `plotly.graph_objects` figures.
