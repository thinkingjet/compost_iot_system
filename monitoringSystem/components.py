from dash import dcc, html

from figures import GRAPH_CONFIG, sparkline


def brand():
    return html.Div([html.Span("⌁", className="brand-mark"), "CompostIQ"], className="brand")


def button(label, variant="primary", icon=None, component_id=None, button_type="button"):
    children = ([html.Span(icon, className="button-icon")] if icon else []) + [label]
    props = {"type": button_type, "className": f"btn btn-{variant}", "n_clicks": 0}
    if component_id is not None:
        props["id"] = component_id
    return html.Button(children, **props)


def linked_button(label, href, variant="primary", icon=None):
    return dcc.Link(button(label, variant, icon), href=href, className="button-link")


def page_header(eyebrow, title, description, action=None):
    return html.Div(
        [html.Div([html.P(eyebrow, className="eyebrow"), html.H1(title), html.P(description)]), action],
        className="page-head",
    )


def section_header(title, action_label=None, action_href=None, action_id=None):
    action = None
    if action_href:
        action = dcc.Link(action_label, href=action_href, className="text-action")
    elif action_label:
        action = html.Button(action_label, id=action_id, className="text-action", n_clicks=0)
    return html.Div([html.H2(title), action], className="section-head")


def field(label, control):
    return html.Div([html.Label(label), control], className="field")


def plot(figure, class_name="chart", static=False, graph_id=None):
    config = {**GRAPH_CONFIG, "staticPlot": static}
    height = figure.layout.height or 260
    props = {"figure": figure, "config": config, "className": class_name, "responsive": "auto", "style": {"height": f"{height}px"}}
    if graph_id is not None:
        props["id"] = graph_id
    return dcc.Graph(**props)


def metric_card(metric):
    return html.Article(
        [
            html.Div([html.Span(metric["label"]), html.I(metric["icon"], className="metric-icon")], className="metric-top"),
            html.Div([metric["value"], " ", html.Small(metric["unit"])], className="metric-value"),
            html.Div([html.B(metric["delta"]), " · last 24 hours"], className="metric-delta"),
            plot(sparkline(metric["values"], metric["color"]), "metric-spark", static=True),
        ],
        className="card card-pad metric",
    )


def bin_card(bin_data):
    device_label = "device" if bin_data["devices"] == 1 else "devices"
    card = html.Article(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div([html.Strong(bin_data["name"]), html.Div(f'{bin_data["location"]} · {bin_data["devices"]} {device_label}', className="unit-location")]),
                            html.Span("⌁", className="phase-orb"),
                        ],
                        className="unit-head",
                    ),
                    plot(sparkline([48, 51, 50, 56, 54, 60, 63, 61, 68], "green"), "mini-chart", static=True),
                ],
                className=f'unit-visual {bin_data.get("variant", "")}',
            ),
            html.Div(
                [
                    html.Div([html.Span(bin_data["phase"], className="phase"), html.Span([html.I(className="dot"), " Online"], className="tag")], className="unit-row"),
                    html.Div([html.Span(["Health score ", html.Span(html.I(style={"width": f'{bin_data["health"]}%'}), className="health-bar")], className="health"), html.Strong(f'{bin_data["health"]}%')], className="unit-row"),
                ],
                className="unit-body",
            ),
        ],
        className="card unit-card",
    )
    return dcc.Link(card, href="/bin/live", className="card-link")


def device_card(device):
    card = html.Article(
        [
            html.Div([html.Span("▣", className="device-icon"), html.Span([html.I(className="dot"), " Online"], className="tag")], className="unit-row"),
            html.H3(device["name"], className="device-title"),
            html.P(f'Monitoring {device["location"]} · {device["model"]}', className="device-location"),
            html.Div([html.Span(device["reading"], className="metric-value device-reading"), html.Span("View telemetry →", className="view-link")], className="unit-row"),
        ],
        className="card card-pad unit-card",
    )
    return dcc.Link(card, href="/device/live", className="card-link")


def alert_card(kind, title, detail, priority):
    return html.Article(
        [
            html.Span("♨" if kind == "hot" else "◒", className=f"alert-icon {kind}"),
            html.Span([html.Strong(title), html.P(detail)], className="alert-copy"),
            html.Span(priority, className="tag"),
        ],
        className="card alert-card",
    )


def sidebar(active):
    groups = [
        ("Workspace", [("/dashboard", "⌂", "Overview", "dashboard"), ("/bins", "▱", "Compost bins", "bins"), ("/devices", "▣", "Devices", "devices")]),
        ("Quick actions", [("/setup/device", "+", "Add device", "setup-device"), ("/setup/bin", "+", "Create bin", "setup-bin")]),
    ]
    children = [brand()]
    for label, items in groups:
        children.append(html.Div(label, className="nav-label"))
        children.extend(
            dcc.Link([html.Span(icon, className="nav-icon"), html.Span(text)], href=href, className=f"nav-item {'active' if active == key else ''}")
            for href, icon, text, key in items
        )
    children.append(html.Div(html.Div([html.Span("GU", className="avatar"), html.Span([html.Strong("UNRAM Pilot"), html.Span("Administrator")], className="account-copy")], className="account"), className="sidebar-footer"))
    return html.Aside(children, className="sidebar", id="main-sidebar")


def app_shell(content, title, active):
    topbar = html.Header(
        [
            html.Button("☰", id="mobile-menu", className="mobile-menu", n_clicks=0, **{"aria-label": "Open navigation"}),
            html.Div([html.Span("CompostIQ"), html.Span("/"), html.Strong(title)], className="crumb"),
            html.Div([html.Span([html.I(className="dot"), " All systems online"], className="status-pill"), html.Button("♧", id="notification-button", className="icon-btn", n_clicks=0, **{"aria-label": "Notifications"})], className="top-actions"),
        ],
        className="topbar",
    )
    return html.Div([sidebar(active), html.Main([topbar, content], className="main")], className="shell")


def detail_tabs(kind, current):
    items = [("live", "Live telemetry"), ("history", "Historical stats"), ("settings", "Settings")]
    if kind == "bin":
        items = [("live", "Live telemetry"), ("maintenance", "Maintenance"), ("history", "Historical stats"), ("devices", "Devices"), ("settings", "Settings")]
    return html.Nav(
        [dcc.Link(label, href=f"/{kind}/{key}", className="active" if current == key else "") for key, label in items],
        className="card detail-tabs",
        **{"aria-label": f"{kind} sections"},
    )


def onboarding_shell(step, content):
    features = ["Live environmental telemetry", "Actionable maintenance alerts", "Automatic phase detection"]
    side = html.Section(
        [
            brand(),
            html.Div([html.P("Smart composting", className="eyebrow"), html.H1("Better compost, backed by data."), html.P("Connect your sensors, monitor every batch, and know exactly when your compost needs attention."), html.Div([html.Span([html.I("✓"), feature], className="feature") for feature in features], className="feature-list")], className="onboard-hero"),
            html.Div([html.Div(className="soil"), html.Div(className="bin-illustration")], className="onboard-art"),
        ],
        className="onboard-side",
    )
    wizard = html.Div([html.Div([html.Span(["Setup · ", html.B(f"Step {step} of 3")], className="step-label"), html.Span(html.I(style={"width": f"{step / 3 * 100}%"}), className="progress")], className="wizard-top"), content], className="wizard")
    return html.Div([side, html.Section(wizard, className="onboard-main")], className="onboarding")
