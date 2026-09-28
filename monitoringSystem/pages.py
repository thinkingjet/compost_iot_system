from dash import dcc, html

from components import (
    alert_card,
    app_shell,
    bin_card,
    button,
    detail_tabs,
    device_card,
    field,
    linked_button,
    metric_card,
    onboarding_shell,
    page_header,
    plot,
    section_header,
)
from data import BINS, DEFAULT_SETUP, DEVICES, HISTORICAL, MAINTENANCE_TASKS, METRICS, TELEMETRY
from figures import health_figure, phase_history_figure, sparkline, telemetry_figure


def dashboard_page(setup=None):
    setup = {**DEFAULT_SETUP, **(setup or {})}

    alerts = html.Div(
        [
            alert_card(
                "hot",
                "Temperature is running high",
                f'{setup["bin_name"]} · Turn compost within 2 hours',
                "High",
            ),
            alert_card(
                "dry",
                "Moisture is trending low",
                "Primary School · Add approximately 3L water",
                "Medium",
            ),
        ],
        className="grid grid-2",
    )

    bins = html.Div([bin_card(item) for item in BINS], className="grid grid-3")
    devices = html.Div([device_card(item) for item in DEVICES], className="grid grid-3")

    content = html.Div(
        [
            page_header(
                "Monday · 8 September",
                "Good morning, UNRAM",
                "Here’s what’s happening across your compost system.",
                linked_button("Add device", "/setup/device", icon="+"),
            ),
            html.Section([metric_card(metric) for metric in METRICS], className="grid grid-4"),
            html.Section(
                [section_header("Needs attention", "Review all", action_id="review-alerts"), alerts],
                className="section",
            ),
            html.Section([section_header("Compost bins", "View all", "/bins"), bins], className="section"),
            html.Section([section_header("Devices", "View all", "/devices"), devices], className="section"),
        ]
    )
    return app_shell(content, "Overview", "dashboard")


def bins_page():
    heading = page_header(
        "Management",
        "Compost bins",
        "Monitor active batches and manage every compost location.",
        linked_button("Create bin", "/setup/bin", icon="+"),
    )
    cards = html.Div([bin_card(item) for item in BINS], className="grid grid-3")
    content = html.Div([heading, cards])
    return app_shell(content, "Compost bins", "bins")


def devices_page():
    heading = page_header(
        "Hardware",
        "Devices",
        "Connected sensors across all compost locations.",
        linked_button("Add device", "/setup/device", icon="+"),
    )
    cards = html.Div([device_card(item) for item in DEVICES], className="grid grid-3")
    content = html.Div([heading, cards])
    return app_shell(content, "Devices", "devices")


def _sensor_chip(label, value, unit, values, color):
    return html.Article([html.Span(label), html.Strong([value, " ", html.Small(unit)]), plot(sparkline(values, color, 24), "tiny-line", static=True)], className="card sensor-chip")


def sensor_strip():
    return html.Div(
        [
            _sensor_chip("Temperature", "54.2", "°C", TELEMETRY["temperature"], "red"),
            _sensor_chip("Moisture", "50.7", "%", TELEMETRY["moisture"], "blue"),
            _sensor_chip("Oxygen", "20.4", "%", TELEMETRY["oxygen"], "green"),
            _sensor_chip("Maturation", "Day 18", "of 28", HISTORICAL["health"], "lime"),
        ],
        className="sensor-strip",
    )


def live_panel(kind):
    return html.Div(
        [
            sensor_strip(),
            html.Article(
                [
                    html.Div([html.Div([html.P("Live data", className="eyebrow"), html.H2("Environmental telemetry" if kind == "bin" else "Sensor readings"), html.P("Updated 14 seconds ago")]), dcc.RadioItems(id=f"{kind}-live-range", options=[{"label": "6h", "value": 6}, {"label": "24h", "value": 24}, {"label": "7d", "value": 168}], value=24, inline=True, className="range-control")], className="chart-toolbar"),
                    plot(telemetry_figure(), graph_id=f"{kind}-live-chart"),
                ],
                className="card chart-card",
            ),
        ]
    )


def maintenance_panel():
    tasks = []
    for number, task in enumerate(MAINTENANCE_TASKS, start=1):
        tasks.append(
            html.Div(
                [
                    html.Span(f"{number:02}", className="task-num"),
                    html.Div([html.Strong(task["title"]), html.P(task["detail"])]),
                    html.Time(task["time"]),
                ],
                className="task",
            )
        )

    header = html.Div(
        [
            html.Div([html.P("Smart schedule", className="eyebrow"), html.H2("Estimated next tasks")]),
            button("Generate predictions", component_id="refresh-predictions"),
        ],
        className="section-head",
    )
    schedule = html.Article([header, html.Div(tasks, className="task-list")], className="card card-pad")
    return html.Div([sensor_strip(), schedule])


def history_panel(kind):
    return html.Div(
        [
            sensor_strip(),
            html.Div(
                [
                    html.Article([html.Div([html.Div([html.P("Phase analysis", className="eyebrow"), html.H2("Temperature over time")]), html.Span("Last 36 days", className="tag")], className="chart-toolbar"), plot(phase_history_figure())], className="card chart-card"),
                    html.Article([html.Div([html.Div([html.P("Quality score", className="eyebrow"), html.H2("Compost health")]), html.Span("Last 36 days", className="tag")], className="chart-toolbar"), plot(health_figure())], className="card chart-card"),
                ],
                className="grid grid-2",
            ),
        ]
    )


def devices_panel():
    return html.Article([section_header("Devices monitoring Bin 1"), html.Div(linked_button("Add device", "/setup/device", icon="+"), className="panel-actions"), html.Div([device_card(device) for device in DEVICES[:2]], className="grid grid-2 device-panel-grid")], className="card card-pad")


def _detail_row(label, value):
    return html.Div([html.Span(label), html.Strong(value)], className="detail-row")


def settings_panel(kind):
    is_bin = kind == "bin"
    fields = [
        field("Name", dcc.Input(id=f"{kind}-settings-name", value="Bin 1" if is_bin else "Outer Sensor", type="text")),
        field("Location", dcc.Dropdown(id=f"{kind}-settings-location", options=["UNRAM", "Primary School", "Mataram"], value="UNRAM", clearable=False)),
    ]
    if is_bin:
        fields.extend([field("Compost method", dcc.Dropdown(options=["Takakura", "Tumbler"], value="Takakura", clearable=False)), field("Capacity", dcc.Input(value="240 L", type="text"))])
    details = [_detail_row("Outer Sensor", "Monitoring · Online"), _detail_row("Inner Sensor", "Monitoring · Online")] if is_bin else [_detail_row("UUID", "CMP-IQ-ESP32-01-84BF"), _detail_row("MAC address", "84:F7:03:A1:2D:90"), _detail_row("Firmware", "v2.4.1 · Up to date"), _detail_row("Created", "18 August 2026")]
    return html.Article([html.Div([html.P("General", className="eyebrow"), html.H2("Bin settings" if is_bin else "Device settings"), html.P(f'Update how this {"compost batch" if is_bin else "sensor"} appears across CompostIQ.'), html.Div(fields, className="form-grid"), html.Div(button("Save changes", component_id=f"save-{kind}-settings"), className="settings-save")], className="settings-block"), html.Div([html.P("System information", className="eyebrow"), html.H2("Assigned devices" if is_bin else "Device details"), html.Div(details, className="details-table")], className="settings-block")], className="card settings")


def detail_page(kind, tab):
    is_bin = kind == "bin"
    valid = {"live", "history", "settings"} | ({"maintenance", "devices"} if is_bin else set())
    tab = tab if tab in valid else "live"

    if tab == "live":
        panel = live_panel(kind)
    elif tab == "history":
        panel = history_panel(kind)
    elif tab == "settings":
        panel = settings_panel(kind)
    elif tab == "maintenance":
        panel = maintenance_panel()
    else:
        panel = devices_panel()

    title = "Bin 1" if is_bin else "Outer Sensor"
    description = "UNRAM · Peak decomposition" if is_bin else "Bin 1 · ESP32-C3"
    header = page_header(
        "Compost bin" if is_bin else "Monitoring device",
        title,
        description,
        button("Export report", "secondary", component_id="export-report"),
    )
    body = html.Div(
        [detail_tabs(kind, tab), html.Section(panel, className="content-panel")],
        className="detail-page",
    )
    content = html.Div([header, body])
    return app_shell(content, "Bin 1" if is_bin else "Outer Sensor", "bins" if is_bin else "devices")


def device_setup_page(setup=None):
    setup = {**DEFAULT_SETUP, **(setup or {})}
    content = html.Div([html.P("Connect hardware", className="eyebrow"), html.H1("Add your first device"), html.P("Give the sensor a recognisable name. You can update these details at any time."), html.Div([field("Device name", dcc.Input(id="device-name", value=setup["device_name"], placeholder="e.g. Outer Sensor", type="text")), field("Initial location", dcc.Dropdown(id="device-location", options=["Unassigned", "Bin 1 · UNRAM", "Primary School"], value=setup["location"], clearable=False)), html.Div([dcc.Link("Skip for now", href="/dashboard", className="btn btn-ghost"), button("Continue  →", component_id="device-next")], className="wizard-actions")], className="wizard-form")])
    return onboarding_shell(1, content)


def bin_setup_page(setup=None):
    setup = {**DEFAULT_SETUP, **(setup or {})}
    content = html.Div([html.P("Compost profile", className="eyebrow"), html.H1("Create a compost bin"), html.P("Add the details we’ll use to calibrate insights and phase predictions."), html.Div([html.Div([field("Bin name", dcc.Input(id="bin-name", value=setup["bin_name"], type="text")), field("Capacity (litres)", dcc.Input(id="bin-capacity", value=setup["capacity"], type="number")), field("Compost method", dcc.Dropdown(id="compost-type", options=["Takakura", "Tumbler", "Hot compost"], value=setup["compost_type"], clearable=False)), field("Primary material", dcc.Dropdown(id="bulk-material", options=["Food scraps + dry leaves", "Garden waste", "Mixed organics"], value=setup["material"], clearable=False))], className="form-grid"), html.Div([dcc.Link("Back", href="/setup/device", className="btn btn-ghost"), button("Continue  →", component_id="bin-next")], className="wizard-actions")], className="wizard-form")])
    return onboarding_shell(2, content)


def assign_setup_page(setup=None):
    setup = {**DEFAULT_SETUP, **(setup or {})}
    available = [("outer", setup["device_name"], "ESP32 · Online · Added just now"), ("inner", "Inner Sensor", "ESP32 · Online · Available")]
    options = [html.Label([dcc.Checklist(options=[{"label": "", "value": device_id}], value=[device_id] if device_id in setup["assigned"] else [], id={"type": "assigned-device", "index": device_id}, className="device-check"), html.Span("▣", className="device-icon"), html.Span([html.Strong(name), html.Span(detail)], className="device-copy")], className="device-option selected" if device_id in setup["assigned"] else "device-option") for device_id, name, detail in available]
    content = html.Div([html.P("Device assignment", className="eyebrow"), html.H1(f'Connect devices to {setup["bin_name"]}'), html.P("Select the sensors that will monitor this compost batch."), html.Div([*options, html.Div([dcc.Link("Back", href="/setup/bin", className="btn btn-ghost"), button("Finish setup  ✓", component_id="setup-finish")], className="wizard-actions")], className="wizard-form")])
    return onboarding_shell(3, content)
