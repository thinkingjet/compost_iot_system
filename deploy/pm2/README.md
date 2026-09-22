# PM2 setup (Ubuntu VM)

PM2 runs the two app processes and restarts them on crash or reboot.
PostgreSQL runs as its own systemd service and is only reachable from the VM itself.

| Component | Managed by | Listens on | Public? |
|---|---|---|---|
| Dashboard (Dash, via gunicorn) | PM2 `compostiq-dashboard` | `127.0.0.1:8050` | Yes, through NGINX at `/` |
| API (via uvicorn) | PM2 `compostiq-api` | `127.0.0.1:8000` | Yes, through NGINX at `/api/` |
| PostgreSQL | systemd `postgresql` | `127.0.0.1:5432` | No |

## 1. Install system packages

```bash
sudo apt update
sudo apt install -y postgresql nodejs npm
sudo npm install -g pm2
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 2. Database (systemd, not PM2)

```bash
sudo systemctl enable --now postgresql
sudo -u postgres psql -c "CREATE USER compostiq WITH PASSWORD 'CHANGE_ME';"
sudo -u postgres psql -c "CREATE DATABASE compostiq OWNER compostiq;"
sudo -u postgres psql -d compostiq -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
psql "postgresql://compostiq:CHANGE_ME@127.0.0.1:5432/compostiq" -f database/CompostIQ_PostgreSQL_schema_fix1.sql
```

Ubuntu's PostgreSQL only listens on localhost by default. Keep it that way, and do not open port 5432 in the firewall.

## 3. App code and Python environment

```bash
git clone <repo-url> ~/compost_iot_system
cd ~/compost_iot_system
uv sync
cp .env.example .env    # then edit .env and set the real DATABASE_URL password
chmod 600 .env
```

`ecosystem.config.js` reads `.env` from the repo root and passes its values to both apps.

## 4. Start the apps

```bash
pm2 start deploy/pm2/ecosystem.config.js
pm2 status
```

## 5. Survive reboots

```bash
pm2 startup systemd     # prints a sudo command - run it
pm2 save                # remembers the current process list
```

## 6. Log rotation

```bash
pm2 install pm2-logrotate
pm2 set pm2-logrotate:max_size 10M
pm2 set pm2-logrotate:retain 7
```

## Everyday commands

```bash
pm2 status
pm2 logs compostiq-api
pm2 restart compostiq-dashboard
pm2 reload deploy/pm2/ecosystem.config.js --update-env   # after editing .env
```

To deploy new code, run `git pull` and `uv sync`, then restart both apps.

## Notes

- **API entry point.** The API isn't written yet. The ecosystem file assumes a Python ASGI app such as FastAPI at `backendAPI/main.py` exposing `app`. Change the `args` line if that ends up different.
- **API routes.** NGINX forwards `/api/...` with the prefix intact, so API routes should start with `/api`.
- **Dashboard workers.** The simulator stores runs on disk, so two gunicorn workers are safe.
