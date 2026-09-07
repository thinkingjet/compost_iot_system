# CompostIQ React frontend

Responsive React mockup for the CompostIQ device onboarding, dashboard, bin,
device, telemetry, maintenance, history, and configuration flows.

## Run locally

```bash
npm install
npm run dev
```

Open `http://127.0.0.1:4173`. Detail views have dedicated paths such as
`/device/live` and `/bin/history`; they are not embedded hash views.

Create a production build with:

```bash
npm run build
```

## Structure

- `src/components/` — reusable application shell, navigation, cards, fields,
  buttons, icons, and other UI primitives.
- `src/components/charts/PlotlyCharts.jsx` — reusable Plotly wrapper and all
  chart types. Shared layout and configuration live here.
- `src/pages/` — route-level compositions built from shared components.
- `src/context/AppContext.jsx` — onboarding state and application toasts.
- `src/data/mockData.js` — placeholder telemetry, devices, bins, and tasks.
- `src/router.jsx` — lightweight history routing with dedicated page paths.

All graphs—including card sparklines—are Plotly charts. Replace the arrays in
`mockData.js` with API response data when the Flask endpoints are connected.
