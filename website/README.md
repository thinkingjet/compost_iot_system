# CompostIQ public website

The static site at **compostiq.win**: the landing page, the open data page for
researchers, and the docs (quickstart, API reference, pairing & security).
The dashboard (`dashboard.compostiq.win`) and the API (`api.compostiq.win`)
stay separate apps.

| URL | Template | What it is |
|---|---|---|
| `/` | `templates/index.html` | Landing page: the product, phases, how it works, alerts, live open-data figures |
| `/open-data/` | `templates/open-data.html` | Data dictionary, anonymisation, sensor caveats, phase ranges, bulk downloads, citation |
| `/docs/` | `templates/docs/quickstart.html` | Quickstart for the open API |
| `/docs/api/` | `templates/docs/api.html` | API reference (`GET /research/readings` and the other public endpoints) |
| `/docs/security/` | `templates/docs/security.html` | How pairing works, and the safeguards on codes, keys and accounts |

## How it works

`build.py` is a small static site generator. It reads the figures, renders the
Jinja templates, and writes plain files to `dist/`:

```
website/
  build.py        renders every page into a folder of static files
  site_data.py    where the figures come from: the API, or the mock data
  charts.py       the charts, drawn as inline SVG
  icons.py        inline Tabler icons, the same set the dashboard uses
  templates/      Jinja templates (base.html and _docs.html are the layouts)
  assets/         site.css, site.js (optional extras), favicon.svg
  tests/          builds the site and checks links, CSP-safety and anonymisation
```

The output is HTML, one stylesheet and one 1 KB script. The pages work without
JavaScript: the script only adds the cURL/Python/R tabs and the Copy buttons.
There are no `style=""` attributes or inline scripts, so NGINX can send a
strict Content-Security-Policy (see `deploy/nginx/compostiq.conf`).

### Why the charts aren't Plotly

The dashboard draws its charts with Plotly, and that is the right tool there:
you zoom, hover and switch ranges on your own bin's data. On a public page that
only shows a 30-day trend, Plotly costs more than it gives:

| | Plotly (as the dashboard ships it) | Build-time SVG (this site) |
|---|---|---|
| Script to download | `plotly.min.js` 6.9: 4.9 MB, 1.5 MB gzipped | none |
| When the chart appears | after the script downloads and runs | with the HTML |
| Size of one 30-day chart | the data, plus the library above | about 3.5 KB of markup |
| Without JavaScript | blank | works |
| Hover values | rich tooltips, zoom, pan | the browser's own tooltip on each point |

The whole home page, both charts included, is about 7 KB gzipped. `charts.py`
draws the lines, target bands and reference lines in a few dozen lines of
Python, and the colours come from `site.css`, so the charts follow the theme.
If a page ever needs real interactivity, a light library such as uPlot (about
50 KB) can be loaded on just that page.

## Build and preview

From the repo root, with the project's virtualenv (it already has Jinja2):

```bash
.venv/bin/python website/build.py
.venv/bin/python -m http.server 8070 --bind 127.0.0.1 --directory website/dist
```

Open <http://127.0.0.1:8070>. In Claude Code the `website` entry in
`.claude/launch.json` starts that server.

Run the tests:

```bash
.venv/bin/pytest website/tests
```

## Where the figures come from

| Build | Source | Pages say |
|---|---|---|
| `build.py` | `mock-data/compostiq_mock_readings.csv`, anonymised on the way in | "Preview figures from the simulated pilot dataset" |
| `build.py --api-url http://127.0.0.1:8000` | The API's public endpoints | "Updated 5 Oct 2026, 09:55 UTC" |

With `--api-url` the build reads:

| Endpoint | Used for |
|---|---|
| `GET /public/stats` → `{bins, countries, active_devices, readings_24h, updated_at}` | Stat tiles, quickstart example |
| `GET /public/bins-by-country` → `[{country, name?, bins}]` | "Where the bins are" |
| `GET /public/trends` → `{days: [{date, temperature_c, moisture_pct}]}` | The two 30-day charts |
| `GET /research/readings` (all pages, via `next_cursor`) | Bulk CSV/JSON downloads, dataset totals |

**These endpoints don't exist in `backendAPI/` yet.** The docs pages describe
them as the contract to build to. Until they exist, build without `--api-url`.

The home page's bin card always uses the mock data: it illustrates the
dashboard, not a real user's bin.

Other options (flags or environment variables):

| Flag | Variable | Default |
|---|---|---|
| `--out` | `WEBSITE_OUT` | `website/dist` |
| `--api-url` | `WEBSITE_API_URL` | none (mock data) |
| `--site-url` | `SITE_URL` | `https://compostiq.win` |
| `--dashboard-url` | `DASHBOARD_URL` | `https://dashboard.compostiq.win` |
| `--public-api-url` | `PUBLIC_API_URL` | `https://api.compostiq.win` (shown to readers in the docs) |

## Deploy on the VM

NGINX serves the files directly; there is no website process in PM2.

1. DNS: A records for `compostiq.win` and `www.compostiq.win`, then expand the
   certificate and install the NGINX config (`deploy/nginx/README.md`).
2. Give your user a folder the build can write to:

   ```bash
   sudo install -d -o "$USER" -g "$USER" /var/www/compostiq
   ```

3. Build into it. NGINX's root is `/var/www/compostiq/site`:

   ```bash
   .venv/bin/python website/build.py --out /var/www/compostiq/site
   ```

4. Once the public endpoints exist, rebuild on a schedule so the figures stay
   fresh. `crontab -e`:

   ```
   */15 * * * * cd /path/to/compost_iot_system && .venv/bin/python website/build.py --api-url http://127.0.0.1:8000 --out /var/www/compostiq/site >> $HOME/compostiq-website.log 2>&1
   ```

Each build is written to a temporary folder next to `site/` and swapped in at
the end. If the API is down or anything fails, the build stops and the
published site stays as it was.

## Still to fill in

`[LICENCE]`, `[SECURITY CONTACT EMAIL]`, `[CONTACT EMAIL]`, the citation's
`[YEAR]` and `[VERSION]`, and the changelog's `[DATE]`. Search the templates
for `[`.
