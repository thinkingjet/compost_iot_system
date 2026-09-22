// CompostIQ - PM2 process file
// Start:   pm2 start deploy/pm2/ecosystem.config.js
// Both apps bind to 127.0.0.1 only; NGINX is the public entry point.
// PostgreSQL is NOT managed here - it runs as a normal systemd service.

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "../..");
const VENV_BIN = path.join(ROOT, ".venv/bin");

// Load secrets (DATABASE_URL etc.) from the repo-root .env, never from this file.
function loadEnv(file) {
  if (!fs.existsSync(file)) return {};
  return Object.fromEntries(
    fs.readFileSync(file, "utf8")
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l && !l.startsWith("#") && l.includes("="))
      .map((l) => {
        const i = l.indexOf("=");
        return [l.slice(0, i).trim(), l.slice(i + 1).trim().replace(/^["']|["']$/g, "")];
      })
  );
}
const env = loadEnv(path.join(ROOT, ".env"));

module.exports = {
  apps: [
    {
      name: "compostiq-dashboard",
      cwd: path.join(ROOT, "simulator"),
      script: path.join(VENV_BIN, "gunicorn"),
      args: "app:server --bind 127.0.0.1:8050 --workers 2 --timeout 60",
      interpreter: "none",
      env: { ...env },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 3000,
      max_memory_restart: "500M",
    },
    {
      // Assumes a Python ASGI app (e.g. FastAPI) at backendAPI/main.py exposing `app`.
      // Change `args` if the API ends up with a different entry point or stack.
      name: "compostiq-api",
      cwd: path.join(ROOT, "backendAPI"),
      script: path.join(VENV_BIN, "uvicorn"),
      args: "main:app --host 127.0.0.1 --port 8000 --workers 2 --proxy-headers",
      interpreter: "none",
      env: { ...env },
      autorestart: true,
      max_restarts: 10,
      restart_delay: 3000,
      max_memory_restart: "500M",
    },
  ],
};
