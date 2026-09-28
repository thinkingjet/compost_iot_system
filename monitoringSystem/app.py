"""
CompostIQ monitoring dashboard.

One MantineProvider and one AppShell (header + navbar) wrap the whole app;
`render_page` swaps the page into `page-root` whenever the URL changes.

Run it with:  python monitoringSystem/app.py
"""
import dash_mantine_components as dmc
from components import app_shell
from dash import (
    ALL,
    Dash,
    Input,
    Output,
    Patch,
    State,
    callback,
    ctx,
    dcc,
    html,
    no_update,
)
from figures import telemetry_figure
from pages import (
    add_device_page,
    bins_page,
    dashboard_page,
    detail_page,
    devices_page,
    new_bin_page,
)
from theme import FONT_URL, THEME, figure_template, register_figure_templates

# apply the stored light/dark choice before the first paint, so there is no
# flash of the wrong theme on reload
dmc.pre_render_color_scheme()
register_figure_templates()

app = Dash(
    __name__,
    title="CompostIQ — Monitoring Console",
    external_stylesheets=[FONT_URL],
    suppress_callback_exceptions=True,
)
server = app.server

app.layout = dmc.MantineProvider(
    # the "dmc" class maps Dash 4 core-component colours onto the Mantine
    # theme (see assets/styles.css); MantineProvider itself takes no class
    html.Div(
        [
            dcc.Location(id="url", refresh=False),
            # the DMC docs: exactly one container, in the top-level layout
            dmc.NotificationContainer(id="notify", position="top-right"),
            app_shell(html.Div(id="page-root")),
        ],
        className="dmc",
    ),
    theme=THEME,
)

STATIC_ROUTES = {
    "/": dashboard_page,
    "/dashboard": dashboard_page,
    "/bins": bins_page,
    "/bins/new": new_bin_page,
    "/devices": devices_page,
    "/devices/add": add_device_page,
}


def toast(message, color="compost", title=None):
    note = {"action": "show", "id": f"toast-{abs(hash(message))}", "message": message, "color": color, "autoClose": 4000}
    if title:
        note["title"] = title
    return [note]


# ----------------------------------------------------------------- routing ---

@callback(Output("page-root", "children"), Input("url", "pathname"))
def render_page(pathname):
    pathname = pathname or "/"
    if pathname in STATIC_ROUTES:
        return STATIC_ROUTES[pathname]()

    parts = [part for part in pathname.split("/") if part]
    if len(parts) == 2 and parts[0] in {"bin", "device"}:
        return detail_page(parts[0], parts[1])

    return dashboard_page()


@callback(
    Output("url", "pathname", allow_duplicate=True),
    Input({"type": "nav-button", "href": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def navigate(_clicks):
    # buttons fire with n_clicks=0 when a page first renders them - ignore that
    if not ctx.triggered_id or not ctx.triggered[0]["value"]:
        return no_update
    return ctx.triggered_id["href"]


@callback(
    Output("url", "pathname", allow_duplicate=True),
    Input({"type": "detail-tabs", "kind": ALL}, "value"),
    State("url", "pathname"),
    prevent_initial_call=True,
)
def switch_detail_tab(values, pathname):
    if not ctx.triggered_id or not values or not values[0]:
        return no_update
    target = f'/{ctx.triggered_id["kind"]}/{values[0]}'
    return no_update if target == pathname else target


# ------------------------------------------------------------------- shell ---

@callback(
    Output("appshell", "navbar"),
    Input("burger", "opened"),
    State("appshell", "navbar"),
)
def toggle_navbar(opened, navbar):
    navbar["collapsed"] = {"mobile": not opened}
    return navbar


@callback(Output("burger", "opened"), Input("url", "pathname"), prevent_initial_call=True)
def close_navbar_on_navigate(_):
    return False


@callback(
    Output({"type": "graph", "index": ALL}, "figure"),
    Input("color-scheme-toggle", "computedColorScheme"),
    Input({"type": "graph", "index": ALL}, "id"),
)
def apply_figure_template(color_scheme, ids):
    # Patch only swaps the template, so figures are not rebuilt or resent.
    # With Patch the template object is required, not just its name.
    template = figure_template(color_scheme)
    patches = []
    for _ in ids:
        patch = Patch()
        patch["layout"]["template"] = template
        patches.append(patch)
    return patches


# ------------------------------------------------------------ live charts ---

def _register_live_range(kind):
    @callback(
        Output({"type": "graph", "index": f"{kind}-live-chart"}, "figure", allow_duplicate=True),
        Input({"type": "live-range", "kind": kind}, "value"),
        State("color-scheme-toggle", "computedColorScheme"),
        prevent_initial_call=True,
    )
    def update_range(value, color_scheme):
        figure = telemetry_figure(int(value or 24))
        figure.update_layout(template=figure_template(color_scheme))
        return figure


for _kind in ("bin", "device"):
    _register_live_range(_kind)


# ---------------------------------------------------------- pairing wizard ---

@callback(
    Output("pair-stepper", "active"),
    Output("pair-next", "disabled"),
    Output("pair-back", "disabled"),
    Output("notify", "sendNotifications", allow_duplicate=True),
    Input("pair-next", "n_clicks"),
    Input("pair-back", "n_clicks"),
    State("pair-stepper", "active"),
    State("pair-code", "value"),
    State("pair-device-name", "value"),
    State("pair-bin", "value"),
    prevent_initial_call=True,
)
def step_pairing(_next, _back, active, code, name, bin_id):
    active = active or 0
    if ctx.triggered_id == "pair-back":
        active = max(active - 1, 0)
        return active, False, active == 0, no_update

    if active == 0 and len(str(code or "")) != 6:
        return no_update, no_update, no_update, toast("Enter the full 6-digit code shown on your device.", "red")
    if active == 1 and not (name and bin_id):
        return no_update, no_update, no_update, toast("Give the device a name and choose a bin.", "red")

    active = min(active + 1, 2)
    done = active == 2
    note = toast("Pairing isn't connected to the API yet. This step is a preview.", "yellow", "Preview") if done else no_update
    return active, done, done, note


# ---------------------------------------------------------------- new bin ---

@callback(
    Output("notify", "sendNotifications", allow_duplicate=True),
    Output("url", "pathname", allow_duplicate=True),
    Input("new-bin-submit", "n_clicks"),
    State("new-bin-name", "value"),
    State("new-bin-country", "value"),
    prevent_initial_call=True,
)
def create_bin(n_clicks, name, country):
    if not n_clicks:
        return no_update, no_update
    if not (name and country):
        return toast("A bin needs a name and a country.", "red"), no_update
    return toast(f"{name} created (preview only, not saved yet).", title="Bin created"), "/bins"


# ------------------------------------------------------- placeholder toasts ---

PLACEHOLDER_TOASTS = {
    "export-report": "Report export prepared",
    "review-alerts": "All alerts marked as reviewed",
    "refresh-predictions": "Predictions refreshed",
    "save-bin-settings": "Bin settings saved",
    "save-device-settings": "Device settings saved",
    "notification-button": "No new notifications",
}


def _register_toast(component_id, message):
    @callback(
        Output("notify", "sendNotifications", allow_duplicate=True),
        Input(component_id, "n_clicks"),
        prevent_initial_call=True,
    )
    def show(n_clicks):
        return toast(message) if n_clicks else no_update


for _component_id, _message in PLACEHOLDER_TOASTS.items():
    _register_toast(_component_id, _message)


if __name__ == "__main__":
    # 8050 is the production port behind NGINX; locally the simulator also
    # defaults to 8050, so run one of them on another port when using both
    app.run(host="127.0.0.1", port=8050, debug=False)
