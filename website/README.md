# CompostIQ public website

The website at **compostiq.win**: the landing page, the open data page for
researchers, and the docs. It is plain HTML, CSS and one small script. There is
no build step and no app process: NGINX serves the files in `public/` exactly
as they are in the repo.

The dashboard stays at `dashboard.compostiq.win` (sign in, sign up and
everything behind them). Its own `/` sends signed-out visitors here and
signed-in users to `/dashboard`.

| URL | File |
|---|---|
| `/` | `public/index.html` |
| `/open-data/` | `public/open-data/index.html` |
| `/docs/` (quickstart) | `public/docs/index.html` |
| `/docs/api/` | `public/docs/api/index.html` |
| `/docs/security/` | `public/docs/security/index.html` |
| anything missing | `public/404.html` |

`public/assets/` holds `site.css`, `site.js` and the favicon. The header and
footer are repeated in each page, so a change there means editing all six.

## Editing

Edit the HTML, commit, push. On the VM, `git pull` publishes it; nothing needs
restarting. Links to the dashboard are full URLs
(`https://dashboard.compostiq.win/login`); everything else is a path on this
site.

## Live figures

The stat tiles, the two 30-day charts and the country list on `/` and
`/open-data/` are filled in by `assets/site.js`. It asks the API through NGINX
(`compostiq.win/api/public/...` goes to the API's `/public/...`):

| Endpoint | Shape |
|---|---|
| `GET /public/stats` | `{bins, countries, methods, active_devices, readings_total, readings_24h, first_reading_at, last_reading_at, updated_at}` |
| `GET /public/bins-by-country` | `[{country, name, bins}]` |
| `GET /public/trends` | `{days: [{date, temperature_c, moisture_pct}]}` |

**These endpoints aren't in `backendAPI/` yet.** Until they are, or whenever
the API can't be reached, the script shows the snapshot in
`public/assets/preview.json` and the pages say they are preview figures. That
snapshot and the files in `public/downloads/` are the simulated pilot data
(`mock-data/`), anonymised. Once the API has a bulk export, point the download
links at it.

The charts are drawn by `site.js` as SVG, in about 70 lines, so the page loads
no chart library. (Plotly, which the dashboard uses, is 1.5 MB gzipped.)

## Preview locally

```bash
.venv/bin/python -m http.server 8070 --bind 127.0.0.1 --directory website/public
```

Open <http://127.0.0.1:8070>. On `localhost`, `site.js` points the dashboard
links at `http://127.0.0.1:8050`, so Sign in reaches your local dashboard. Set
`WEBSITE_URL=http://127.0.0.1:8070` in `monitoringSystem/.env` so the
dashboard's `/` and Log out come back here. The live figures show the preview
snapshot locally, because nothing passes `/api/public/` through to the API.

## Set up on the VM (once)

1. **DNS**: A records for `compostiq.win` and `www.compostiq.win`, pointing at
   the VM.
2. **NGINX and the certificate**: install `deploy/nginx/compostiq.conf` and
   add the two names to the certificate. The steps are in
   [deploy/nginx/README.md](../deploy/nginx/README.md).
3. **Link the files into place**, from the repo on the VM:

   ```bash
   sudo ln -sfn "$(git rev-parse --show-toplevel)/website/public" /var/www/compostiq
   ```

   NGINX runs as `www-data`, which must be able to reach the repo. If the repo
   is in a home folder, check with
   `sudo -u www-data cat /var/www/compostiq/index.html`. If that fails, let it
   pass through (not list) the folders on the way:
   `chmod o+x /home/<user>`.

After that, every `git pull` publishes the site.
