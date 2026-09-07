const state = {
  route: location.hash.slice(1) || "add-device",
  onboarding: {
    deviceName: "Outer Sensor",
    location: "Bin 1 · UNRAM",
    binName: "Bin 1",
    compostType: "Takakura",
    material: "Food scraps + dry leaves",
    capacity: "240",
    assigned: ["outer"]
  },
  range: "24h",
  sidebarOpen: false
};

const icons = {
  leaf: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M19.5 4.5C11 4.8 6.2 8.7 5.4 15.6c-.3 2.7 1.6 4.6 4.2 4.1 6.2-1.1 9.7-6 9.9-15.2Z"/><path d="M4 21c2.4-5.4 6.3-8.7 11.4-10.8"/></svg>`,
  home: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z"/></svg>`,
  bin: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M5 7h14l-1 14H6L5 7Z"/><path d="M4 7h16M9 7V4h6v3M9 11v6M15 11v6"/></svg>`,
  device: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="5" y="3" width="14" height="18" rx="3"/><path d="M9 7h6M10 17h4"/></svg>`,
  plus: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>`,
  menu: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16M4 12h16M4 17h16"/></svg>`,
  bell: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg>`,
  temp: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 14.8V5a4 4 0 0 0-8 0v9.8a6 6 0 1 0 8 0Z"/><path d="M10 5v11"/></svg>`,
  drop: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 2S5 10 5 15a7 7 0 0 0 14 0c0-5-7-13-7-13Z"/></svg>`,
  wind: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 8h10a3 3 0 1 0-3-3M4 12h15a3 3 0 1 1-3 3M4 16h7"/></svg>`,
  activity: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 12h4l2-7 4 14 2-7h6"/></svg>`,
  flame: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 22c4 0 7-3 7-7 0-5-4-9-7-13 0 5-7 7-7 13 0 4 3 7 7 7Z"/><path d="M9.5 18c0-2 1.7-3.4 2.5-5 .8 1.6 2.5 3 2.5 5"/></svg>`,
  arrow: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg>`,
  check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3"><path d="m5 12 4 4L19 6"/></svg>`,
  clock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>`,
  settings: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></svg>`
};

const routes = {
  "dashboard": dashboardPage,
  "add-device": () => onboardingPage(1),
  "create-bin": () => onboardingPage(2),
  "assign-devices": () => onboardingPage(3),
  "bins": binsPage,
  "devices": devicesPage,
  "bin-live": () => detailPage("bin", "live"),
  "bin-maintenance": () => detailPage("bin", "maintenance"),
  "bin-history": () => detailPage("bin", "history"),
  "bin-devices": () => detailPage("bin", "devices"),
  "bin-settings": () => detailPage("bin", "settings"),
  "device-live": () => detailPage("device", "live"),
  "device-history": () => detailPage("device", "history"),
  "device-settings": () => detailPage("device", "settings")
};

function go(route) {
  state.route = route;
  state.sidebarOpen = false;
  location.hash = route;
  render();
  window.scrollTo(0, 0);
}

function brand() { return `<div class="brand"><span class="brand-mark">${icons.leaf}</span>CompostIQ</div>`; }

function sidebar() {
  const active = ["bin-live","bin-maintenance","bin-history","bin-devices","bin-settings","bins"].includes(state.route) ? "bins" : ["device-live","device-history","device-settings","devices"].includes(state.route) ? "devices" : state.route;
  return `<aside class="sidebar ${state.sidebarOpen ? "open" : ""}">
    ${brand()}
    <div class="nav-label">Workspace</div>
    <button class="nav-item ${active === "dashboard" ? "active" : ""}" onclick="go('dashboard')">${icons.home}<span>Overview</span></button>
    <button class="nav-item ${active === "bins" ? "active" : ""}" onclick="go('bins')">${icons.bin}<span>Compost bins</span></button>
    <button class="nav-item ${active === "devices" ? "active" : ""}" onclick="go('devices')">${icons.device}<span>Devices</span></button>
    <div class="nav-label">Quick actions</div>
    <button class="nav-item" onclick="go('add-device')">${icons.plus}<span>Add device</span></button>
    <button class="nav-item" onclick="go('create-bin')">${icons.plus}<span>Create bin</span></button>
    <div class="sidebar-footer"><div class="account"><span class="avatar">GU</span><span class="account-copy"><strong>UNRAM Pilot</strong><span>Administrator</span></span></div></div>
  </aside>`;
}

function shell(content, title = "Overview") {
  return `<div class="shell">${sidebar()}<main class="main">
    <header class="topbar"><button class="mobile-menu" onclick="toggleSidebar()">${icons.menu}</button><div class="crumb"><span>CompostIQ</span><span>/</span><strong>${title}</strong></div><div class="top-actions"><span class="status-pill"><i class="dot"></i> All systems online</span><button class="icon-btn" onclick="toast('No new notifications')">${icons.bell}</button></div></header>
    ${content}</main></div>`;
}

function toggleSidebar() { state.sidebarOpen = !state.sidebarOpen; render(); }

function onboardingPage(step) {
  const content = step === 1 ? deviceForm() : step === 2 ? binForm() : assignForm();
  return `<div class="onboarding"><section class="onboard-side">${brand()}<div class="onboard-hero"><p class="eyebrow">Smart composting</p><h1>Better compost, backed by data.</h1><p>Connect your sensors, monitor every batch, and know exactly when your compost needs attention.</p><div class="feature-list"><span class="feature"><i>✓</i>Live environmental telemetry</span><span class="feature"><i>✓</i>Actionable maintenance alerts</span><span class="feature"><i>✓</i>Automatic phase detection</span></div></div><div class="onboard-art"><div class="soil"></div><div class="bin-illustration"></div></div></section><section class="onboard-main"><div class="wizard"><div class="wizard-top"><span class="step-label">Setup · <b>Step ${step} of 3</b></span><span class="progress"><i style="width:${step/3*100}%"></i></span></div>${content}</div></section></div>`;
}

function deviceForm() {
  return `<p class="eyebrow">Connect hardware</p><h1>Add your first device</h1><p>Give the sensor a recognisable name. You can update these details at any time.</p><form class="wizard-form" onsubmit="saveDevice(event)"><div class="field"><label for="device-name">Device name</label><input id="device-name" required value="${state.onboarding.deviceName}" placeholder="e.g. Outer Sensor" /></div><div class="field"><label for="device-location">Initial location</label><select id="device-location"><option>Unassigned</option><option selected>Bin 1 · UNRAM</option><option>Primary School</option></select></div><div class="wizard-actions"><button type="button" class="btn btn-ghost" onclick="go('dashboard')">Skip for now</button><button class="btn btn-primary">Continue ${icons.arrow}</button></div></form>`;
}

function binForm() {
  return `<p class="eyebrow">Compost profile</p><h1>Create a compost bin</h1><p>Add the details we’ll use to calibrate insights and phase predictions.</p><form class="wizard-form" onsubmit="saveBin(event)"><div class="form-grid"><div class="field"><label for="bin-name">Bin name</label><input id="bin-name" required value="${state.onboarding.binName}" /></div><div class="field"><label for="capacity">Capacity (litres)</label><input id="capacity" type="number" value="${state.onboarding.capacity}" /></div><div class="field"><label for="compost-type">Compost method</label><select id="compost-type"><option>Takakura</option><option>Tumbler</option><option>Hot compost</option></select></div><div class="field"><label for="material">Primary material</label><select id="material"><option>Food scraps + dry leaves</option><option>Garden waste</option><option>Mixed organics</option></select></div></div><div class="wizard-actions"><button type="button" class="btn btn-ghost" onclick="go('add-device')">Back</button><button class="btn btn-primary">Continue ${icons.arrow}</button></div></form>`;
}

function assignForm() {
  return `<p class="eyebrow">Device assignment</p><h1>Connect devices to ${state.onboarding.binName}</h1><p>Select the sensors that will monitor this compost batch.</p><div class="wizard-form"><div class="device-option selected" data-device="outer" onclick="toggleDevice(this)"><span class="device-icon">${icons.device}</span><span class="device-copy"><strong>${state.onboarding.deviceName}</strong><span>ESP32 · Online · Added just now</span></span><span class="check">${icons.check}</span></div><div class="device-option" data-device="inner" onclick="toggleDevice(this)"><span class="device-icon">${icons.device}</span><span class="device-copy"><strong>Inner Sensor</strong><span>ESP32 · Online · Available</span></span><span class="check">${icons.check}</span></div><div class="wizard-actions"><button class="btn btn-ghost" onclick="go('create-bin')">Back</button><button class="btn btn-primary" onclick="completeSetup()">Finish setup ${icons.check}</button></div></div>`;
}

function saveDevice(e) { e.preventDefault(); state.onboarding.deviceName = document.querySelector("#device-name").value; state.onboarding.location = document.querySelector("#device-location").value; go("create-bin"); }
function saveBin(e) { e.preventDefault(); state.onboarding.binName = document.querySelector("#bin-name").value; state.onboarding.capacity = document.querySelector("#capacity").value; state.onboarding.compostType = document.querySelector("#compost-type").value; state.onboarding.material = document.querySelector("#material").value; go("assign-devices"); }
function toggleDevice(el) { el.classList.toggle("selected"); }
function completeSetup() { localStorage.setItem("compostiq-setup", "complete"); go("dashboard"); setTimeout(() => toast("Bin and devices added successfully"), 120); }

function pageHead(eyebrow, title, desc, action = "") { return `<div class="page-head"><div><p class="eyebrow">${eyebrow}</p><h1>${title}</h1><p>${desc}</p></div>${action}</div>`; }

function dashboardPage() {
  return shell(`${pageHead("Monday · 7 September", "Good morning, UNRAM", "Here’s what’s happening across your compost system.", `<button class="btn btn-primary" onclick="go('add-device')">${icons.plus} Add device</button>`)}
  <section class="grid grid-4">
    ${metricCard("Temperature", "54.2", "°C", "+2.4%", "temp", "red")}
    ${metricCard("Moisture", "50.7", "%", "Within target", "drop", "blue")}
    ${metricCard("Oxygen", "20.4", "%", "+0.8%", "wind", "green")}
    ${metricCard("Compost health", "86", "/ 100", "Optimal", "activity", "lime")}
  </section>
  <section class="section"><div class="section-head"><h2>Needs attention</h2><a onclick="toast('All alerts marked as reviewed')">Review all</a></div><div class="grid grid-2"><article class="card alert-card"><span class="alert-icon hot">${icons.flame}</span><span class="alert-copy"><strong>Temperature is running high</strong><p>${state.onboarding.binName} · Turn compost within 2 hours</p></span><span class="tag">High</span></article><article class="card alert-card"><span class="alert-icon dry">${icons.drop}</span><span class="alert-copy"><strong>Moisture is trending low</strong><p>Primary School · Add approximately 3L water</p></span><span class="tag">Medium</span></article></div></section>
  <section class="section"><div class="section-head"><h2>Compost bins</h2><a onclick="go('bins')">View all</a></div><div class="grid grid-3">${unitCard("Bin 1", "UNRAM · 2 devices", "Peak decomposition", 86, "bin-live")}${unitCard("Bin 3", "Mataram · 1 device", "Active thermophilic", 74, "bin-live", "blue")}${unitCard("Primary School", "Lombok · 1 device", "Cooling", 68, "bin-live")}</div></section>
  <section class="section"><div class="section-head"><h2>Devices</h2><a onclick="go('devices')">View all</a></div><div class="grid grid-3">${deviceCard("Outer Sensor", "Bin 1", "54.2°C", "device-live")}${deviceCard("Inner Sensor", "Bin 1", "52.8°C", "device-live")}${deviceCard("School Compost", "Primary School", "41.6°C", "device-live")}</div></section>`, "Overview");
}

function metricCard(label, value, unit, delta, icon, color) {
  return `<article class="card card-pad metric"><div class="metric-top"><span>${label}</span><i class="metric-icon">${icons[icon]}</i></div><div class="metric-value">${value} <small>${unit}</small></div><div class="metric-delta"><b>${delta}</b> · last 24 hours</div>${sparkSvg(color, "metric-spark")}</article>`;
}
function sparkSvg(color="green", cls="") {
  const colors = {red:"#d6574e",blue:"#4b84d1",green:"#1d7b50",lime:"#83a841"};
  return `<svg class="${cls}" viewBox="0 0 100 50" preserveAspectRatio="none"><path d="M1 41 C13 34,17 37,27 27 S43 36,52 20 S70 23,79 13 S92 18,99 7" fill="none" stroke="${colors[color]||color}" stroke-width="2"/><path d="M1 41 C13 34,17 37,27 27 S43 36,52 20 S70 23,79 13 S92 18,99 7 V50 H1Z" fill="${colors[color]||color}" opacity=".09"/></svg>`;
}
function unitCard(name, location, phase, health, route, variant="") {
  return `<article class="card unit-card" onclick="go('${route}')"><div class="unit-visual ${variant}"><div class="unit-head"><div><strong>${name}</strong><div class="unit-location">${location}</div></div><span class="phase-orb">${icons.leaf}</span></div>${sparkSvg("#1d7b50", "mini-chart")}</div><div class="unit-body"><div class="unit-row"><span class="phase">${phase}</span><span class="tag"><i class="dot"></i> Online</span></div><div class="unit-row"><span class="health">Health score <span class="health-bar"><i style="width:${health}%"></i></span></span><strong>${health}%</strong></div></div></article>`;
}
function deviceCard(name, location, reading, route) {
  return `<article class="card card-pad unit-card" onclick="go('${route}')"><div class="unit-row"><span class="device-icon">${icons.device}</span><span class="tag"><i class="dot"></i> Online</span></div><h3 style="font-size:16px;margin:18px 0 4px">${name}</h3><p style="color:var(--muted);font-size:11px;margin-bottom:18px">Monitoring ${location}</p><div class="unit-row"><span class="metric-value" style="font-size:22px">${reading}</span><span style="color:var(--green);font-size:11px;font-weight:700">View telemetry →</span></div></article>`;
}

function binsPage() { return shell(`${pageHead("Management", "Compost bins", "Monitor active batches and manage every compost location.", `<button class="btn btn-primary" onclick="go('create-bin')">${icons.plus} Create bin</button>`)}<div class="grid grid-3">${unitCard("Bin 1", "UNRAM · 2 devices", "Peak decomposition", 86, "bin-live")}${unitCard("Bin 3", "Mataram · 1 device", "Active thermophilic", 74, "bin-live", "blue")}${unitCard("Primary School", "Lombok · 1 device", "Cooling", 68, "bin-live")}</div>`, "Compost bins"); }
function devicesPage() { return shell(`${pageHead("Hardware", "Devices", "Connected sensors across all compost locations.", `<button class="btn btn-primary" onclick="go('add-device')">${icons.plus} Add device</button>`)}<div class="grid grid-3">${deviceCard("Outer Sensor", "Bin 1", "54.2°C", "device-live")}${deviceCard("Inner Sensor", "Bin 1", "52.8°C", "device-live")}${deviceCard("School Compost", "Primary School", "41.6°C", "device-live")}</div>`, "Devices"); }

function detailPage(type, tab) {
  const isBin = type === "bin";
  const title = isBin ? "Bin 1" : "Outer Sensor";
  const sub = isBin ? "UNRAM · Peak decomposition" : "Bin 1 · ESP32-C3";
  const prefix = isBin ? "bin" : "device";
  const nav = isBin ? [["live","Live telemetry"],["maintenance","Maintenance"],["history","Historical stats"],["devices","Devices"],["settings","Settings"]] : [["live","Live telemetry"],["history","Historical stats"],["settings","Settings"]];
  const panel = tab === "live" ? livePanel(isBin) : tab === "maintenance" ? maintenancePanel() : tab === "history" ? historyPanel() : tab === "devices" ? devicesPanel() : settingsPanel(isBin);
  return shell(`${pageHead(isBin ? "Compost bin" : "Monitoring device", title, sub, `<button class="btn btn-secondary" onclick="toast('Report exported')">Export report</button>`)}<div class="workspace"><nav class="card subnav">${nav.map(([key,label])=>`<button class="${tab===key?"active":""}" onclick="go('${prefix}-${key}')">${label}</button>`).join("")}</nav><section class="content-panel">${panel}</section></div>`, title);
}

function sensorStrip() { return `<div class="sensor-strip">${sensorChip("Temperature","54.2","°C","red")}${sensorChip("Moisture","50.7","%","blue")}${sensorChip("Oxygen","20.4","%","green")}${sensorChip("Maturation","Day 18","of 28","lime")}</div>`; }
function sensorChip(label, value, unit, color) { return `<article class="card sensor-chip"><span>${label}</span><strong>${value} <small>${unit}</small></strong>${sparkSvg(color,"tiny-line")}</article>`; }

function livePanel(isBin) {
  return `${sensorStrip()}<article class="card chart-card"><div class="chart-toolbar"><div><p class="eyebrow">Live data</p><h2>${isBin ? "Environmental telemetry" : "Sensor readings"}</h2><p>Updated 14 seconds ago</p></div>${rangeControl()}</div>${lineChart()}<div class="legend"><span><i style="background:#4b84d1"></i>Temperature</span><span><i style="background:#1fae78"></i>Moisture</span><span><i style="background:#8b67c6"></i>CO₂</span></div></article>`;
}
function rangeControl() { return `<div class="segmented">${["6h","24h","7d"].map(x=>`<button class="${state.range===x?"active":""}" onclick="setRange('${x}')">${x}</button>`).join("")}</div>`; }
function setRange(range) { state.range=range; render(); }

function lineChart() {
  const xs=[46,95,144,193,242,291,340,389,438,487,536];
  const temp=[150,145,151,128,119,105,112,108,114,91,82];
  const moist=[191,186,190,178,172,144,132,158,171,135,130];
  const gas=[221,216,213,210,201,191,186,183,188,177,171];
  const path = ys => ys.map((y,i)=>`${i?"L":"M"}${xs[i]} ${y}`).join(" ");
  return `<svg class="chart" viewBox="0 0 580 260" preserveAspectRatio="none"><defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4b84d1" stop-opacity=".18"/><stop offset="1" stop-color="#4b84d1" stop-opacity="0"/></linearGradient></defs>${[40,80,120,160,200,240].map(y=>`<line x1="42" y1="${y}" x2="550" y2="${y}" stroke="#e7ebe6" stroke-width="1"/>`).join("")}<path d="${path(temp)} L536 240 L46 240Z" fill="url(#area)"/><path d="${path(temp)}" fill="none" stroke="#4b84d1" stroke-width="2.1"/><path d="${path(moist)}" fill="none" stroke="#1fae78" stroke-width="2"/><path d="${path(gas)}" fill="none" stroke="#8b67c6" stroke-width="1.8"/>${["12am","4am","8am","12pm","4pm","8pm"].map((t,i)=>`<text x="${45+i*98}" y="256">${t}</text>`).join("")}</svg>`;
}

function maintenancePanel() {
  return `${sensorStrip()}<article class="card card-pad"><div class="section-head"><div><p class="eyebrow">Smart schedule</p><h2>Estimated next tasks</h2></div><button class="btn btn-primary" onclick="toast('Predictions refreshed')">Generate predictions</button></div><div class="task-list"><div class="task"><span class="task-num">01</span><div><strong>Temperature reaching high point</strong><p>Turn the compost to maintain an even breakdown.</p></div><time>In 2 hours</time></div><div class="task"><span class="task-num">02</span><div><strong>Moisture will fall below target</strong><p>Add approximately 3 litres of water.</p></div><time>In 2 days</time></div><div class="task"><span class="task-num">03</span><div><strong>Transition to maturation phase</strong><p>The compost is progressing normally.</p></div><time>In 10 days</time></div></div></article>`;
}
function historyPanel() {
  return `${sensorStrip()}<div class="grid grid-2"><article class="card chart-card"><div class="chart-toolbar"><div><p class="eyebrow">Phase analysis</p><h2>Temperature over time</h2></div>${rangeControl()}</div>${areaChart()}</article><article class="card chart-card"><div class="chart-toolbar"><div><p class="eyebrow">Quality score</p><h2>Compost health</h2></div><span class="tag">Last 30 days</span></div>${lineChart()}</article></div>`;
}
function areaChart() { return `<svg class="chart" viewBox="0 0 580 260" preserveAspectRatio="none"><defs><linearGradient id="phaseA" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ef8c35" stop-opacity=".8"/><stop offset="1" stop-color="#ef8c35" stop-opacity=".16"/></linearGradient><linearGradient id="phaseB" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1fae78" stop-opacity=".75"/><stop offset="1" stop-color="#1fae78" stop-opacity=".12"/></linearGradient></defs>${[40,80,120,160,200,240].map(y=>`<line x1="42" y1="${y}" x2="550" y2="${y}" stroke="#e7ebe6"/>`).join("")}<path d="M42 70 L94 77 L130 133 L160 162 L190 184 L220 194 L220 240 L42 240Z" fill="url(#phaseA)"/><path d="M220 194 C290 185 360 181 550 179 L550 240 L220 240Z" fill="url(#phaseB)"/><path d="M42 70 L94 77 L130 133 L160 162 L190 184 L220 194 C290 185 360 181 550 179" fill="none" stroke="#173d2b" stroke-width="2"/><line x1="42" y1="105" x2="550" y2="105" stroke="#d6574e" stroke-dasharray="5 4"/><text x="48" y="96">Target threshold</text><text x="42" y="256">Aug 16</text><text x="216" y="256">Aug 28</text><text x="380" y="256">Sep 09</text><text x="515" y="256">Sep 21</text></svg>`; }
function devicesPanel() { return `<article class="card card-pad"><div class="section-head"><div><p class="eyebrow">Assigned hardware</p><h2>Devices monitoring Bin 1</h2></div><button class="btn btn-primary" onclick="go('add-device')">${icons.plus} Add device</button></div><div class="grid grid-2" style="margin-top:20px">${deviceCard("Outer Sensor","Bin 1","54.2°C","device-live")}${deviceCard("Inner Sensor","Bin 1","52.8°C","device-live")}</div></article>`; }
function settingsPanel(isBin) { return `<article class="card settings"><div class="settings-block"><p class="eyebrow">General</p><h2>${isBin ? "Bin settings" : "Device settings"}</h2><p>Update how this ${isBin ? "compost batch" : "sensor"} appears across CompostIQ.</p><div class="form-grid"><div class="field"><label>Name</label><input value="${isBin ? "Bin 1" : "Outer Sensor"}" /></div><div class="field"><label>Location</label><select><option>UNRAM</option><option>Primary School</option><option>Mataram</option></select></div>${isBin ? `<div class="field"><label>Compost method</label><select><option>Takakura</option><option>Tumbler</option></select></div><div class="field"><label>Capacity</label><input value="240 L" /></div>` : ""}</div><div style="margin-top:18px"><button class="btn btn-primary" onclick="toast('Settings saved')">Save changes</button></div></div><div class="settings-block"><p class="eyebrow">System information</p><h2>${isBin ? "Assigned devices" : "Device details"}</h2><div class="details-table">${isBin ? `<div class="detail-row"><span>Outer Sensor</span><strong>Monitoring · Online</strong></div><div class="detail-row"><span>Inner Sensor</span><strong>Monitoring · Online</strong></div>` : `<div class="detail-row"><span>UUID</span><strong>CMP-IQ-ESP32-01-84BF</strong></div><div class="detail-row"><span>MAC address</span><strong>84:F7:03:A1:2D:90</strong></div><div class="detail-row"><span>Firmware</span><strong>v2.4.1 · Up to date</strong></div><div class="detail-row"><span>Created</span><strong>18 August 2026</strong></div>`}</div></div></article>`; }

function toast(message) { const root=document.querySelector("#toast-root"); root.innerHTML=`<div class="toast">${message}</div>`; setTimeout(()=>root.innerHTML="",2600); }
function render() { const page = routes[state.route] || dashboardPage; document.querySelector("#app").innerHTML = page(); }
window.addEventListener("hashchange", () => { state.route = location.hash.slice(1) || "add-device"; render(); });
render();
