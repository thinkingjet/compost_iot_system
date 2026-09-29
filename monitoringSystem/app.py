"""
CompostIQ monitoring dashboard.

One MantineProvider and one AppShell (header + navbar) wrap the whole app;
`render_page` swaps the page into `page-root` whenever the URL changes, and
decides who may see it: the public pages (/, /login, /register) get the
header only, everything else needs a sign-in and gets the navbar too.

Run it with:  python monitoringSystem/app.py
"""
import logging
import re
import secrets
import time
from datetime import timedelta
from urllib.parse import parse_qs, urlencode

import auth
import dash_mantine_components as dmc
from api_client import ApiError, ApiUnavailable, NotAuthenticated
from components import NAVBAR, app_shell, header_actions, navbar_account
from dash import (
    ALL,
    Dash,
    Input,
    Output,
    Patch,
    State,
    callback,
    clientside_callback,
    ctx,
    dcc,
    html,
    no_update,
)
from figures import telemetry_figure
from pages import (
    account_page,
    add_device_page,
    bins_page,
    dashboard_page,
    detail_page,
    devices_page,
    landing_page,
    login_page,
    new_bin_page,
    not_found_page,
    register_page,
)
from settings import DASHBOARD_SECRET_KEY, SESSION_HOURS
from theme import FONT_URL, THEME, figure_template, register_figure_templates

logger = logging.getLogger("compostiq.dashboard")

# `python app.py` is local development; under gunicorn (the VM) this module
# is imported as "app", so the production rules below apply
LOCAL = __name__ == "__main__"

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


def configure_session(flask_server):
    """The signed session cookie that holds the user's token."""
    secret_key = DASHBOARD_SECRET_KEY
    if not secret_key:
        if not LOCAL:
            raise RuntimeError(
                "DASHBOARD_SECRET_KEY is not set. Add it to the repo-root .env "
                "(see .env.example) - the dashboard cannot sign sessions without it."
            )
        secret_key = secrets.token_urlsafe(48)
        logger.warning(
            "DASHBOARD_SECRET_KEY is not set: using a random key, so everyone is signed out "
            "whenever the dashboard restarts. Set it in monitoringSystem/.env (see .env.example)."
        )
    flask_server.config.update(
        SECRET_KEY=secret_key,
        SESSION_COOKIE_NAME="compostiq_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        # HTTPS only on the VM; plain http://127.0.0.1 needs it off
        SESSION_COOKIE_SECURE=not LOCAL,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=SESSION_HOURS),
    )


configure_session(server)

app.layout = dmc.MantineProvider(
    # the "dmc" class maps Dash 4 core-component colours onto the Mantine
    # theme (see assets/styles.css); MantineProvider itself takes no class
    html.Div(
        [
            dcc.Location(id="url", refresh=False),
            # where a callback wants the browser to go next
            dcc.Store(id="redirect"),
            # which shell is showing: {"public": bool}. Never holds the token.
            dcc.Store(id="shell", data={"public": True}),
            # the DMC docs: exactly one container, in the top-level layout
            dmc.NotificationContainer(id="notify", position="top-right"),
            app_shell(html.Div(id="page-root")),
        ],
        className="dmc",
    ),
    theme=THEME,
)

PUBLIC_ROUTES = {"/", "/login", "/register"}
AFTER_SIGN_IN = "/dashboard"

# private pages; the two in USER_PAGES are built from the signed-in user
PRIVATE_ROUTES = {
    "/bins": bins_page,
    "/bins/new": new_bin_page,
    "/devices": devices_page,
    "/devices/add": add_device_page,
}
USER_PAGES = {
    "/dashboard": dashboard_page,
    "/account": account_page,
}

SESSION_EXPIRED = "Your session expired, please sign in again."
API_DOWN = "Can’t reach CompostIQ right now. Try again in a moment."
TOO_MANY_ATTEMPTS = "Too many attempts, try again in a few minutes."
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8
MAX_NAME = 80


def toast(message, color="compost", title=None):
    note = {"action": "show", "id": f"toast-{abs(hash(message))}", "message": message, "color": color, "autoClose": 4000}
    if title:
        note["title"] = title
    return [note]


def goto(target):
    """A value for the `redirect` store: a local path, with or without a query."""
    pathname, _, query = target.partition("?")
    # the timestamp makes every redirect a new value, even to the same place
    return {"pathname": pathname, "search": f"?{query}" if query else "", "at": time.time()}


def login_url(next_path):
    return f"/login?{urlencode({'next': next_path})}"


def next_page(search):
    """Where to go after signing in: ?next= if it is a path on this site."""
    target = parse_qs((search or "").lstrip("?")).get("next", [""])[0]
    # a lone leading slash only - "//host" and "/\\host" would leave the site
    if not target.startswith("/") or target[1:2] in ("/", "\\") or target.split("?")[0] in PUBLIC_ROUTES:
        return AFTER_SIGN_IN
    return target


def _detail_route(pathname):
    """("bin" | "device", tab) for a detail URL such as /bin/live, else None."""
    parts = [part for part in pathname.split("/") if part]
    return parts if len(parts) == 2 and parts[0] in {"bin", "device"} else None


def is_private(pathname):
    return pathname in USER_PAGES or pathname in PRIVATE_ROUTES or _detail_route(pathname) is not None


def private_page(pathname, user):
    if pathname in USER_PAGES:
        return USER_PAGES[pathname](user)
    if pathname in PRIVATE_ROUTES:
        return PRIVATE_ROUTES[pathname]()
    return detail_page(*_detail_route(pathname))


# ----------------------------------------------------------------- routing ---

@callback(
    Output("page-root", "children"),
    Output("header-actions", "children"),
    Output("navbar-account", "children"),
    Output("shell", "data"),
    Output("redirect", "data"),
    Output("notify", "sendNotifications"),
    Input("url", "pathname"),
)
def render_page(pathname):
    pathname = pathname or "/"

    def redirect(target, note=no_update):
        # leave the current page alone; the redirect renders the next one
        return no_update, no_update, no_update, no_update, goto(target), note

    def public(page, signed_in):
        return page, header_actions(True, signed_in), None, {"public": True}, no_update, no_update

    if pathname in PUBLIC_ROUTES:
        signed_in = auth.is_signed_in()
        if pathname == "/":
            # a signed-in user stays here; only the header button changes
            return public(landing_page(signed_in), signed_in)
        if signed_in:
            return redirect(AFTER_SIGN_IN)
        return public(login_page() if pathname == "/login" else register_page(), False)

    if not is_private(pathname):
        # an unknown route: a 404 in whichever shell the visitor is already in
        user = auth.current_user()
        if user is None:
            return public(not_found_page(False), False)
        return not_found_page(True), header_actions(False, True), navbar_account(user), {"public": False}, no_update, no_update

    # a private page: the guard. This is for the user's experience only -
    # the API checks the token on every call and is what keeps data private.
    if not auth.has_session():
        return redirect(login_url(pathname))
    note = no_update
    try:
        user = auth.current_user(refresh=True)
    except NotAuthenticated:
        return redirect(login_url(pathname), toast(SESSION_EXPIRED, "yellow", "Signed out"))
    except ApiUnavailable:
        # the pages still show mock data, so carry on with what the session knows
        user = auth.current_user()
        note = toast(API_DOWN, "red")
    return private_page(pathname, user), header_actions(False, True), navbar_account(user), {"public": False}, no_update, note


# Redirects run in the browser. A callback cannot send render_page's own
# input (url.pathname) back to it - Dash drops that as a circular chain - so
# this does what dcc.Link does: change the address, then tell dcc.Location to
# read it again. replaceState keeps the page being left out of the history,
# so Back does not bounce off the same redirect.
clientside_callback(
    """
    function (target) {
        if (target) {
            window.history.replaceState({}, "", target.pathname + target.search);
            window.dispatchEvent(new CustomEvent("_dashprivate_pushstate"));
        }
    }
    """,
    Input("redirect", "data"),
    prevent_initial_call=True,
)


@callback(
    Output("url", "pathname", allow_duplicate=True),
    Output("url", "search", allow_duplicate=True),
    Input({"type": "nav-button", "href": ALL, "slot": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def navigate(_clicks):
    # buttons fire with n_clicks=0 when a page first renders them - ignore that
    if not ctx.triggered_id or not ctx.triggered[0]["value"]:
        return no_update, no_update
    # the empty search drops a left-over ?next= from the sign-in page
    return ctx.triggered_id["href"], ""


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
    Output("navbar", "display"),
    Output("burger", "display"),
    Input("burger", "opened"),
    Input("shell", "data"),
)
def toggle_navbar(opened, shell):
    # the public shell has no navbar at all, and so no burger to open it;
    # display:none also keeps its links away from the Tab key
    public = shell["public"]
    hidden = "none" if public else None
    collapsed = {"mobile": public or not opened, "desktop": public}
    return {**NAVBAR, "collapsed": collapsed}, hidden, hidden


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


# ------------------------------------------------------- sign in / sign up ---

def _clicked():
    # a callback also fires when one of its inputs is first rendered (a page
    # or a modal opening). Only a real click or Enter key triggers it with a
    # count, so look at what triggered this call, not at every input.
    return any(item["value"] for item in ctx.triggered)


def _api_problem(error):
    """The message for an API failure that no form field explains."""
    if isinstance(error, ApiUnavailable):
        return API_DOWN
    if error.status == 429:
        return TOO_MANY_ATTEMPTS
    return "Something went wrong. Please try again."


@callback(
    Output("redirect", "data", allow_duplicate=True),
    Output("login-error", "children"),
    Output("login-error", "hide"),
    Input("login-submit", "n_clicks"),
    Input("login-email", "n_submit"),
    Input("login-password", "n_submit"),
    State("login-email", "value"),
    State("login-password", "value"),
    State("url", "search"),
    running=[(Output("login-submit", "loading"), True, False)],
    prevent_initial_call=True,
)
def sign_in(n_clicks, email_enter, password_enter, email, password, search):
    if not _clicked():
        return no_update, no_update, no_update
    if not (email or "").strip() or not password:
        return no_update, "Enter your email and password.", False
    try:
        auth.login(email.strip(), password)
    except ApiError as error:
        # 401: the API answers the same for an unknown email and a wrong password
        message = "Email or password is incorrect." if error.status in (401, 422) else _api_problem(error)
        return no_update, message, False
    except ApiUnavailable as error:
        return no_update, _api_problem(error), False
    return goto(next_page(search)), no_update, True


@callback(
    Output("redirect", "data", allow_duplicate=True),
    Output("register-error", "children"),
    Output("register-error", "hide"),
    Output("register-email", "error"),
    Output("register-name", "error"),
    Output("register-password", "error"),
    Output("register-confirm", "error"),
    Input("register-submit", "n_clicks"),
    Input("register-email", "n_submit"),
    Input("register-name", "n_submit"),
    Input("register-password", "n_submit"),
    Input("register-confirm", "n_submit"),
    State("register-email", "value"),
    State("register-name", "value"),
    State("register-password", "value"),
    State("register-confirm", "value"),
    running=[(Output("register-submit", "loading"), True, False)],
    prevent_initial_call=True,
)
def sign_up(n_clicks, enter_1, enter_2, enter_3, enter_4, email, name, password, confirm):
    if not _clicked():
        return (no_update,) * 7

    def answer(alert=None, email_error=None, name_error=None, password_error=None, confirm_error=None):
        return no_update, alert, alert is None, email_error, name_error, password_error, confirm_error

    email, name, password = (email or "").strip(), (name or "").strip(), password or ""
    errors = {}
    if not EMAIL_PATTERN.match(email):
        errors["email_error"] = "Enter a valid email address."
    if len(name) > MAX_NAME:
        errors["name_error"] = f"Keep it to {MAX_NAME} characters or fewer."
    if len(password) < MIN_PASSWORD:
        errors["password_error"] = f"Use at least {MIN_PASSWORD} characters."
    if (confirm or "") != password:
        errors["confirm_error"] = "The passwords don’t match."
    if errors:
        return answer(**errors)

    try:
        auth.register(email, password, name or None)
    except ApiError as error:
        if error.status == 409:
            taken = ["An account with this email already exists. ", dmc.Anchor("Sign in?", href="/login", fw=600, size="sm")]
            return answer(alert=taken)
        if error.status == 422:
            # the API is stricter than the quick checks above
            fields = error.fields
            return answer(
                email_error="Enter a valid email address." if "email" in fields else None,
                name_error="That name can’t be used." if "display_name" in fields else None,
                password_error=f"Use {MIN_PASSWORD} to 128 characters." if "password" in fields else None,
                alert=None if fields & {"email", "display_name", "password"} else _api_problem(error),
            )
        return answer(alert=_api_problem(error))
    except ApiUnavailable as error:
        return answer(alert=_api_problem(error))
    return goto(AFTER_SIGN_IN), None, True, None, None, None, None


@callback(
    Output("redirect", "data", allow_duplicate=True),
    Output("notify", "sendNotifications", allow_duplicate=True),
    Input("logout-button", "n_clicks"),
    prevent_initial_call=True,
)
def sign_out(n_clicks):
    if not _clicked():
        return no_update, no_update
    auth.logout()
    return goto("/"), toast("You’ve been signed out.")


# ----------------------------------------------------------------- account ---

def _session_ended(pathname):
    """The `redirect` and `notify` values for a token the API turned away."""
    return goto(login_url(pathname or "/account")), toast(SESSION_EXPIRED, "yellow", "Signed out")


@callback(
    Output("redirect", "data", allow_duplicate=True),
    Output("notify", "sendNotifications", allow_duplicate=True),
    Output("navbar-account", "children", allow_duplicate=True),
    Output("account-name", "error"),
    Input("account-name-save", "n_clicks"),
    Input("account-name", "n_submit"),
    State("account-name", "value"),
    State("url", "pathname"),
    running=[(Output("account-name-save", "loading"), True, False)],
    prevent_initial_call=True,
)
def save_display_name(n_clicks, enter, name, pathname):
    if not _clicked():
        return (no_update,) * 4
    name = (name or "").strip()
    if len(name) > MAX_NAME:
        return no_update, no_update, no_update, f"Keep it to {MAX_NAME} characters or fewer."
    try:
        user = auth.update_display_name(name or None)
    except NotAuthenticated:
        return *_session_ended(pathname), no_update, no_update
    except (ApiError, ApiUnavailable) as error:
        return no_update, toast(_api_problem(error), "red"), no_update, no_update
    return no_update, toast("Display name saved."), navbar_account(user), None


@callback(
    Output("redirect", "data", allow_duplicate=True),
    Output("notify", "sendNotifications", allow_duplicate=True),
    Output("account-current-password", "error"),
    Output("account-new-password", "error"),
    Output("account-confirm-password", "error"),
    Output("account-current-password", "value"),
    Output("account-new-password", "value"),
    Output("account-confirm-password", "value"),
    Input("account-password-save", "n_clicks"),
    Input("account-current-password", "n_submit"),
    Input("account-new-password", "n_submit"),
    Input("account-confirm-password", "n_submit"),
    State("account-current-password", "value"),
    State("account-new-password", "value"),
    State("account-confirm-password", "value"),
    State("url", "pathname"),
    running=[(Output("account-password-save", "loading"), True, False)],
    prevent_initial_call=True,
)
def change_password(n_clicks, enter_1, enter_2, enter_3, current, new, confirm, pathname):
    if not _clicked():
        return (no_update,) * 8

    def answer(current_error=None, new_error=None, confirm_error=None, note=no_update):
        return no_update, note, current_error, new_error, confirm_error, no_update, no_update, no_update

    current, new = current or "", new or ""
    errors = {}
    if not current:
        errors["current_error"] = "Enter your current password."
    if len(new) < MIN_PASSWORD:
        errors["new_error"] = f"Use at least {MIN_PASSWORD} characters."
    if (confirm or "") != new:
        errors["confirm_error"] = "The passwords don’t match."
    if errors:
        return answer(**errors)

    try:
        auth.change_password(current, new)
    except NotAuthenticated:
        return *_session_ended(pathname), *((no_update,) * 6)
    except ApiError as error:
        if error.status == 401:
            return answer(current_error="That’s not your current password.")
        if error.status == 422:
            return answer(new_error=f"Use {MIN_PASSWORD} to 128 characters.")
        return answer(note=toast(_api_problem(error), "red"))
    except ApiUnavailable as error:
        return answer(note=toast(_api_problem(error), "red"))
    return no_update, toast("Password changed."), None, None, None, "", "", ""


@callback(
    Output("account-delete-modal", "opened"),
    Output("account-delete-password", "value", allow_duplicate=True),
    Output("account-delete-password", "error", allow_duplicate=True),
    Input("account-delete-open", "n_clicks"),
    Input("account-delete-cancel", "n_clicks"),
    prevent_initial_call=True,
)
def toggle_delete_modal(open_clicks, cancel_clicks):
    if not _clicked():
        return no_update, no_update, no_update
    # always start (and leave) with an empty password box
    return ctx.triggered_id == "account-delete-open", "", None


@callback(
    Output("redirect", "data", allow_duplicate=True),
    Output("notify", "sendNotifications", allow_duplicate=True),
    Output("account-delete-password", "error"),
    Input("account-delete-confirm", "n_clicks"),
    Input("account-delete-password", "n_submit"),
    State("account-delete-password", "value"),
    State("url", "pathname"),
    running=[(Output("account-delete-confirm", "loading"), True, False)],
    prevent_initial_call=True,
)
def delete_account(n_clicks, enter, password, pathname):
    if not _clicked():
        return no_update, no_update, no_update
    if not password:
        return no_update, no_update, "Enter your password to confirm."
    try:
        auth.delete_account(password)
    except NotAuthenticated:
        return *_session_ended(pathname), no_update
    except ApiError as error:
        if error.status == 401:
            return no_update, no_update, "That’s not your password."
        return no_update, toast(_api_problem(error), "red"), no_update
    except ApiUnavailable as error:
        return no_update, toast(_api_problem(error), "red"), no_update
    return goto("/"), toast("Your account and its data have been deleted.", title="Account deleted"), None


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
