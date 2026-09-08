from dash import ALL, Dash, Input, Output, State, callback, dcc, html, no_update

from data import DEFAULT_SETUP
from figures import telemetry_figure
from pages import (
    assign_setup_page,
    bin_setup_page,
    bins_page,
    dashboard_page,
    detail_page,
    device_setup_page,
    devices_page,
)


FONT_URL = "https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@500;600;700&display=swap"

app = Dash(
    __name__,
    title="CompostIQ — Monitoring Console",
    external_stylesheets=[FONT_URL],
    suppress_callback_exceptions=True,
)
server = app.server

app.layout = html.Div(
    [
        dcc.Location(id="url", refresh=False),
        dcc.Store(id="setup-store", data=DEFAULT_SETUP, storage_type="session"),
        html.Div(id="page-root"),
        html.Div(id="notice", className="notice", **{"aria-live": "polite"}),
    ]
)


@callback(Output("page-root", "children"), Input("url", "pathname"), Input("setup-store", "data"))
def render_page(pathname, setup):
    pathname = pathname or "/"

    if pathname in ("/", "/setup/device"):
        return device_setup_page(setup)
    if pathname == "/setup/bin":
        return bin_setup_page(setup)
    if pathname == "/setup/assign":
        return assign_setup_page(setup)
    if pathname == "/dashboard":
        return dashboard_page(setup)
    if pathname == "/bins":
        return bins_page()
    if pathname == "/devices":
        return devices_page()

    parts = [part for part in pathname.split("/") if part]
    if len(parts) == 2 and parts[0] in {"bin", "device"}:
        return detail_page(parts[0], parts[1])

    return dashboard_page(setup)


@callback(
    Output("setup-store", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("device-next", "n_clicks"),
    State("device-name", "value"),
    State("device-location", "value"),
    State("setup-store", "data"),
    prevent_initial_call=True,
)
def save_device(n_clicks, name, location, setup):
    if not n_clicks:
        return no_update, no_update
    updated = {**DEFAULT_SETUP, **(setup or {})}
    updated["device_name"] = name or "Outer Sensor"
    updated["location"] = location or "Unassigned"
    return updated, "/setup/bin"


@callback(
    Output("setup-store", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("bin-next", "n_clicks"),
    State("bin-name", "value"),
    State("bin-capacity", "value"),
    State("compost-type", "value"),
    State("bulk-material", "value"),
    State("setup-store", "data"),
    prevent_initial_call=True,
)
def save_bin(n_clicks, name, capacity, compost_type, material, setup):
    if not n_clicks:
        return no_update, no_update
    updated = {**DEFAULT_SETUP, **(setup or {})}
    updated.update(
        bin_name=name or "Bin 1",
        capacity=str(capacity or 240),
        compost_type=compost_type or "Takakura",
        material=material or "Food scraps + dry leaves",
    )
    return updated, "/setup/assign"


@callback(
    Output("setup-store", "data", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Output("notice", "children", allow_duplicate=True),
    Input("setup-finish", "n_clicks"),
    State({"type": "assigned-device", "index": ALL}, "value"),
    State({"type": "assigned-device", "index": ALL}, "id"),
    State("setup-store", "data"),
    prevent_initial_call=True,
)
def finish_setup(n_clicks, selections, identifiers, setup):
    if not n_clicks:
        return no_update, no_update, no_update
    assigned = []
    for selection, device_id in zip(selections or [], identifiers or []):
        if selection:
            assigned.append(device_id["index"])

    updated = {**DEFAULT_SETUP, **(setup or {}), "assigned": assigned}
    return updated, "/dashboard", "Bin and devices added successfully"


@callback(Output("device-live-chart", "figure"), Input("device-live-range", "value"), prevent_initial_call=True)
def update_device_range(value):
    return telemetry_figure(value or 24)


@callback(Output("bin-live-chart", "figure"), Input("bin-live-range", "value"), prevent_initial_call=True)
def update_bin_range(value):
    return telemetry_figure(value or 24)


@callback(Output("main-sidebar", "className"), Input("mobile-menu", "n_clicks"), prevent_initial_call=True)
def toggle_mobile_menu(n_clicks):
    return "sidebar open" if n_clicks % 2 else "sidebar"


@callback(Output("notice", "children", allow_duplicate=True), Input("export-report", "n_clicks"), prevent_initial_call=True)
def export_notice(n_clicks):
    return "Report export prepared" if n_clicks else no_update


@callback(Output("notice", "children", allow_duplicate=True), Input("review-alerts", "n_clicks"), prevent_initial_call=True)
def review_notice(n_clicks):
    return "All alerts marked as reviewed" if n_clicks else no_update


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050, debug=False)
