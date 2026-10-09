import dash_mantine_components as dmc
from dash import dcc

import api_client
from api_client import ApiError, ApiUnavailable, NotAuthenticated
from components import (
    alert_card,
    bin_card,
    button,
    detail_tabs,
    device_card,
    linked_button,
    metric_card,
    page_header,
    paired_device_card,
    plot,
    section_header,
    user_name,
)
from data import (
    BINS,
    COUNTRIES,
    DEVICES,
    HISTORICAL,
    MAINTENANCE_TASKS,
    METRICS,
    TELEMETRY,
)
from figures import health_figure, phase_history_figure, sparkline, telemetry_figure
from settings import PUBLIC_API_URL
from theme import icon

CARD_GRID = {"base": 1, "sm": 2, "lg": 3}


def _card_title(eyebrow, title, subtitle=None):
    children = [dmc.Text(eyebrow, size="xs", fw=700, tt="uppercase", c="dimmed"), dmc.Title(title, order=4)]
    if subtitle:
        children.append(dmc.Text(subtitle, size="xs", c="dimmed"))
    return dmc.Stack(children, gap=2)


# --------------------------------------------------------------- overview ---

def dashboard_page(user):
    alerts = dmc.SimpleGrid(
        [
            alert_card("hot", "Temperature is running high", "Bin 1 · Turn compost within 2 hours", "High"),
            alert_card("dry", "Moisture is trending low", "Primary School · Add approximately 3L water", "Medium"),
        ],
        cols={"base": 1, "md": 2},
    )
    return dmc.Stack(
        [
            page_header(
                "Monday · 8 September",
                f"Welcome back, {user_name(user)}",
                "Here’s what’s happening across your compost system.",
                linked_button("Pair a device", "/devices/add", icon_name="link"),
            ),
            dmc.SimpleGrid([metric_card(metric) for metric in METRICS], cols={"base": 1, "sm": 2, "lg": 4}),
            dmc.Box([section_header("Needs attention", "Review all", action_id="review-alerts"), alerts]),
            dmc.Box([section_header("Compost bins", "View all", "/bins"), dmc.SimpleGrid([bin_card(item) for item in BINS], cols=CARD_GRID)]),
            dmc.Box([section_header("Devices", "View all", "/devices"), dmc.SimpleGrid([device_card(item) for item in DEVICES], cols=CARD_GRID)]),
        ],
        gap="xl",
    )


def bins_page():
    return dmc.Box(
        [
            page_header(
                "Management",
                "Compost bins",
                "Monitor active batches and manage every compost location.",
                linked_button("Create bin", "/bins/new", icon_name="plus"),
            ),
            dmc.SimpleGrid([bin_card(item) for item in BINS], cols=CARD_GRID),
        ]
    )


def devices_page():
    header = page_header(
        "Hardware",
        "Devices",
        "The CompostIQ devices on your account.",
        linked_button("Pair a device", "/devices/add", icon_name="link"),
    )

    def page(content):
        # the new-key modal is always there, so its callbacks always have their outputs
        return dmc.Box([header, content, *_new_key_modal()])

    try:
        devices = api_client.list_devices()
    except NotAuthenticated:
        return page(dmc.Alert("Your session has ended. Sign in again to see your devices.", color="yellow"))
    except (ApiUnavailable, ApiError):
        return page(dmc.Alert("Can’t load your devices right now. Try again in a moment.", color="red"))

    if not devices:
        empty = dmc.Card(
            dmc.Stack(
                [
                    dmc.ThemeIcon(icon("device", 26), size=52, radius="xl", variant="light"),
                    dmc.Title("No devices yet", order=4),
                    dmc.Text("Turn your CompostIQ device on, then pair it with your account.", c="dimmed", size="sm", ta="center"),
                    dmc.Group(
                        [
                            linked_button("Pair a device", "/devices/add", icon_name="link", slot="empty"),
                            linked_button("Register with API key", "/devices/register", "default", icon_name="key", slot="empty"),
                        ],
                        justify="center",
                    ),
                ],
                align="center",
                py="xl",
            ),
            padding="lg",
        )
        return page(empty)
    return page(dmc.SimpleGrid([paired_device_card(device) for device in devices], cols=CARD_GRID))


def _new_key_modal():
    """A registered device's new key: confirm first, then the key, shown once.

    Only its buttons close it, so a stray click outside can't lose the key.
    """
    ask = dmc.Stack(
        [
            dmc.Text(id="new-key-warning", size="sm"),
            dmc.Group(
                [
                    button("Cancel", "default", component_id="new-key-cancel"),
                    button("Generate new key", icon_name="key", component_id="new-key-confirm", color="red"),
                ],
                justify="flex-end",
            ),
        ],
        id="new-key-ask",
    )
    show = dmc.Stack(
        [
            *_api_key_panel("new"),
            dmc.Group([button("I’ve saved the key", icon_name="check", component_id="new-key-saved")], justify="flex-end"),
        ],
        id="new-key-show",
        style=_hidden(True),
    )
    return [
        # {id, name} of the device the modal is for - never its key
        dcc.Store(id="new-key-device", data=None),
        dmc.Modal(
            [ask, show],
            id="new-key-modal",
            title="New API key",
            size="lg",
            centered=True,
            opened=False,
            closeOnClickOutside=False,
            closeOnEscape=False,
            withCloseButton=False,
        ),
    ]


# ----------------------------------------------------------- detail pages ---

def _sensor_chip(label, value, unit, values, color):
    return dmc.Card(
        [
            dmc.Text(label, size="xs", c="dimmed", fw=500),
            dmc.Group([dmc.Text(value, fz=22, fw=700), dmc.Text(unit, size="xs", c="dimmed")], gap=4, align="baseline"),
            plot(sparkline(values, color, 24), static=True),
        ],
        padding="sm",
    )


def sensor_strip():
    return dmc.SimpleGrid(
        [
            _sensor_chip("Temperature", "54.2", "°C", TELEMETRY["temperature"], "temperature"),
            _sensor_chip("Moisture", "50.7", "%", TELEMETRY["moisture"], "moisture"),
            _sensor_chip("Oxygen", "20.4", "%", TELEMETRY["oxygen"], "oxygen"),
            _sensor_chip("Maturation", "Day 18", "of 28", HISTORICAL["health"], "health"),
        ],
        cols={"base": 2, "md": 4},
        mb="md",
    )


def live_panel(kind):
    toolbar = dmc.Group(
        [
            _card_title("Live data", "Environmental telemetry" if kind == "bin" else "Sensor readings", "Updated 14 seconds ago"),
            dmc.SegmentedControl(
                id={"type": "live-range", "kind": kind},
                data=[{"label": "6h", "value": "6"}, {"label": "24h", "value": "24"}, {"label": "7d", "value": "168"}],
                value="24",
                size="xs",
            ),
        ],
        justify="space-between",
        align="flex-start",
        mb="sm",
    )
    return dmc.Box([sensor_strip(), dmc.Card([toolbar, plot(telemetry_figure(), name=f"{kind}-live-chart")], padding="md")])


def maintenance_panel():
    timeline = dmc.Timeline(
        [
            dmc.TimelineItem(
                [dmc.Text(task["detail"], size="sm", c="dimmed"), dmc.Text(task["time"], size="xs", c="dimmed", mt=4)],
                title=task["title"],
                bullet=icon("check", 12),
            )
            for task in MAINTENANCE_TASKS
        ],
        active=0,
        bulletSize=22,
        lineWidth=2,
    )
    header = dmc.Group(
        [_card_title("Smart schedule", "Estimated next tasks"), button("Generate predictions", component_id="refresh-predictions")],
        justify="space-between",
        mb="md",
    )
    return dmc.Box([sensor_strip(), dmc.Card([header, timeline], padding="md")])


def history_panel():
    def chart_card(eyebrow, title, figure):
        return dmc.Card(
            [dmc.Group([_card_title(eyebrow, title), dmc.Badge("Last 36 days", variant="light", color="gray")], justify="space-between", mb="sm"), plot(figure)],
            padding="md",
        )

    return dmc.Box(
        [
            sensor_strip(),
            dmc.SimpleGrid(
                [chart_card("Phase analysis", "Temperature over time", phase_history_figure()), chart_card("Quality score", "Compost health", health_figure())],
                cols={"base": 1, "md": 2},
            ),
        ]
    )


def devices_panel():
    return dmc.Card(
        [
            dmc.Group([dmc.Title("Devices monitoring Bin 1", order=4), linked_button("Pair a device", "/devices/add", icon_name="link")], justify="space-between", mb="md"),
            dmc.SimpleGrid([device_card(device) for device in DEVICES[:2]], cols={"base": 1, "sm": 2}),
        ],
        padding="md",
    )


def _detail_row(label, value):
    return dmc.Group([dmc.Text(label, size="sm", c="dimmed"), dmc.Text(value, size="sm", fw=600)], justify="space-between")


def settings_panel(kind):
    is_bin = kind == "bin"
    fields = [
        dmc.TextInput(label="Name", value="Bin 1" if is_bin else "Outer Sensor"),
        dmc.Select(label="Location", data=["UNRAM", "Primary School", "Mataram"], value="UNRAM", allowDeselect=False),
    ]
    if is_bin:
        fields.append(dmc.Select(label="Country", data=COUNTRIES, value="ID", searchable=True, allowDeselect=False))
    if is_bin:
        details = [_detail_row("Outer Sensor", "Monitoring · Online"), _detail_row("Inner Sensor", "Monitoring · Online")]
    else:
        details = [
            _detail_row("Device ID", "CMP-IQ-ESP32-01-84BF"),
            _detail_row("MAC address", "84:F7:03:A1:2D:90"),
            _detail_row("Firmware", "v2.4.1 · Up to date"),
            _detail_row("Created", "18 August 2026"),
        ]
    general = dmc.Stack(
        [
            _card_title("General", "Bin settings" if is_bin else "Device settings", f'Update how this {"compost batch" if is_bin else "sensor"} appears across CompostIQ.'),
            dmc.SimpleGrid(fields, cols={"base": 1, "sm": 2}),
            dmc.Group(button("Save changes", component_id=f"save-{kind}-settings"), justify="flex-end"),
        ],
    )
    info = dmc.Stack([_card_title("System information", "Assigned devices" if is_bin else "Device details"), dmc.Stack(details, gap="xs")])
    return dmc.Card(dmc.SimpleGrid([general, info], cols={"base": 1, "md": 2}, spacing="xl"), padding="lg")


def detail_page(kind, tab):
    is_bin = kind == "bin"
    valid = {"live", "history", "settings"} | ({"maintenance", "devices"} if is_bin else set())
    tab = tab if tab in valid else "live"

    if tab == "live":
        panel = live_panel(kind)
    elif tab == "history":
        panel = history_panel()
    elif tab == "settings":
        panel = settings_panel(kind)
    elif tab == "maintenance":
        panel = maintenance_panel()
    else:
        panel = devices_panel()

    header = page_header(
        "Compost bin" if is_bin else "Monitoring device",
        "Bin 1" if is_bin else "Outer Sensor",
        "UNRAM · Peak decomposition" if is_bin else "Bin 1 · ESP32-C3",
        button("Export report", "default", icon_name="download", component_id="export-report"),
    )
    return dmc.Box([header, detail_tabs(kind, tab), panel])


# ------------------------------------------------------------ create flows ---

def _hidden(hidden):
    return {"display": "none"} if hidden else {}


def _device_setup_fields(prefix):
    """A device name and its bin, existing or new: the form both the pairing
    and the registration wizards end with.

    Every id starts with `prefix`; app.py registers the callbacks that go
    with the fields (switching bin choice, clearing errors) once per prefix.
    """
    return [
        dmc.TextInput(id=f"{prefix}-device-name", label="Device name", placeholder="e.g. Outer sensor", value="", required=True),
        dmc.Stack(
            [
                dmc.Text("Compost bin", size="sm", fw=500),
                dmc.SegmentedControl(
                    id=f"{prefix}-bin-mode",
                    data=[{"value": "existing", "label": "An existing bin"}, {"value": "new", "label": "A new bin"}],
                    value="existing",
                ),
            ],
            gap=4,
        ),
        dmc.Select(id=f"{prefix}-bin", placeholder="Choose a bin", data=[], allowDeselect=False),
        dmc.Stack(
            [
                dmc.TextInput(id=f"{prefix}-new-bin-name", label="Bin name", placeholder="e.g. Bin 1", value="", required=True),
                dmc.TextInput(id=f"{prefix}-new-bin-location", label="Location", placeholder="e.g. UNRAM Engineering", value=""),
                dmc.Select(id=f"{prefix}-new-bin-country", label="Country", data=COUNTRIES, searchable=True, required=True, placeholder="Choose a country"),
                dmc.Text("Only the country is shown publicly, as part of the anonymised global statistics.", size="xs", c="dimmed"),
            ],
            id=f"{prefix}-new-bin",
            style=_hidden(True),
        ),
    ]


def add_device_page():
    """Pairing: get a code here, enter it on the device, confirm, then name it and pick a bin.

    The device swaps the code for its own API key (the dashboard never sees
    the key). This page only issues the code, watches for it being used, and
    sets the device up once the user confirms it's theirs.
    """
    code_step = dmc.Stack(
        [
            dmc.Stack(
                [
                    dmc.Text("Turn your CompostIQ device on and open its page. Then get a pairing code here and enter it on the device.", c="dimmed", size="sm"),
                    button("Get pairing code", icon_name="link", component_id="pair-start"),
                ],
                id="pair-code-empty",
                align="flex-start",
                gap="md",
            ),
            dmc.Stack(
                [
                    dmc.Text("Enter this code on your device’s page:", size="sm"),
                    dmc.Paper(
                        dmc.Text(id="pair-code-value", ff="monospace", fz=44, fw=700, style={"letterSpacing": "0.3em"}),
                        withBorder=True,
                        px="xl",
                        py="md",
                        radius="md",
                    ),
                    dmc.Text(id="pair-code-expiry", size="xs", c="dimmed"),
                    dmc.Group([dmc.Loader(size="sm", id="pair-code-loader"), dmc.Text(id="pair-code-status", size="sm")], gap="sm"),
                    button("Get a new code", "default", component_id="pair-restart", size="xs"),
                ],
                id="pair-code-live",
                align="flex-start",
                gap="sm",
                style=_hidden(True),
            ),
        ],
        py="md",
    )
    confirm_step = dmc.Stack(
        [
            dmc.Text("Check that this hardware ID matches the one on your device’s page before you confirm. If it doesn’t, someone else’s device used the code.", c="dimmed", size="sm"),
            dmc.Paper(
                dmc.SimpleGrid(
                    [
                        dmc.Stack([dmc.Text("Hardware ID", size="xs", c="dimmed"), dmc.Code(id="pair-device-hardware", fz="md")], gap=2),
                        dmc.Stack([dmc.Text("Model", size="xs", c="dimmed"), dmc.Text(id="pair-device-model")], gap=2),
                        dmc.Stack([dmc.Text("Firmware", size="xs", c="dimmed"), dmc.Text(id="pair-device-firmware")], gap=2),
                    ],
                    cols={"base": 1, "sm": 3},
                ),
                withBorder=True,
                p="md",
                radius="md",
            ),
            dmc.Group(
                [
                    button("That’s not my device", "subtle", component_id="pair-reject", color="red"),
                    button("Confirm registration", icon_name="check", component_id="pair-confirm"),
                ],
                justify="flex-end",
            ),
        ],
        py="md",
    )
    details_step = dmc.Stack(
        [
            *_device_setup_fields("pair"),
            dmc.Group([button("Finish setup", component_id="pair-finish")], justify="flex-end"),
        ],
        maw=480,
        py="md",
    )
    done_step = dmc.Stack(
        [
            dmc.ThemeIcon(icon("check", 28), size=56, radius="xl", variant="light", id="pair-done-icon"),
            dmc.Title("Waiting for the first reading…", order=4, id="pair-done-title"),
            dmc.Text("Your device is set up. It checks in every few seconds, so its first reading should arrive shortly.",
                     c="dimmed", size="sm", ta="center", id="pair-done-text"),
            dmc.Group(
                [
                    button("Pair another device", "default", component_id="pair-another"),
                    linked_button("Go to devices", "/devices", icon_name="arrow-right"),
                ]
            ),
        ],
        align="center",
        py="xl",
    )
    stepper = dmc.Stepper(
        id="pair-stepper",
        active=0,
        allowNextStepsSelect=False,
        children=[
            dmc.StepperStep(label="Pair", description="Get a code", children=code_step),
            dmc.StepperStep(label="Confirm", description="Is it yours?", children=confirm_step),
            dmc.StepperStep(label="Set up", description="Name & bin", children=details_step),
            dmc.StepperCompleted(children=done_step),
        ],
    )
    return dmc.Box(
        [
            # the code and the device's id - never the device's key, which only the device holds
            dcc.Store(id="pair-state", data=None),
            # never changes: fires resume_setup once when the page opens
            dcc.Store(id="pair-init", data=0),
            dcc.Interval(id="pair-poll", interval=2000, disabled=True),
            page_header("Connect hardware", "Pair a device", "Link a CompostIQ device to your account."),
            dmc.Card(stepper, padding="lg"),
        ]
    )


REGISTER_INTRO = "Name the device and choose the bin it monitors. You’ll get its API key next."

# how a device sends readings with its key; the key itself stays out of it,
# in an environment variable, so it never lands in shell history
READINGS_EXAMPLE = f"""curl -X POST {PUBLIC_API_URL}/records \\
  -H "x-key: $COMPOSTIQ_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '[{{"timestamp": "2026-10-09T08:00:00Z", "temperature": 55.0,
        "moisture_percent": 52.0, "o2_percent": 10.0,
        "co2_percent": 6.0, "nh3_ratio": 0.9}}]'"""


def _labelled(label, child):
    return dmc.Stack([dmc.Text(label, size="sm", fw=500), child], gap=4)


def _api_key_panel(prefix):
    """The one-time view of a device's API key: copy it, and how to use it.

    Shared by the registration wizard and the new-key modal. A callback puts
    the key into `{prefix}-key-value` and empties it again as the user moves on.
    """
    key_id = f"{prefix}-key-value"
    return [
        dmc.Alert(
            "This is the only time the key is shown. Copy it onto your device now and keep it private: "
            "anyone who has it can send readings to your bin.",
            title="Save this key",
            color="yellow",
            variant="light",
            icon=icon("alert-circle"),
        ),
        _labelled(
            "API key",
            dmc.Group(
                [
                    dmc.Code(id=key_id, fz="sm", flex=1, style={"wordBreak": "break-all"}),
                    dmc.CopyButton(target_id=key_id, children="Copy", copiedChildren="Copied", size="xs", variant="default"),
                ],
                wrap="nowrap",
            ),
        ),
        _labelled("Endpoint", dmc.Code(f"POST {PUBLIC_API_URL}/records", w="fit-content")),
        dmc.Text(
            ["Send the key in the ", dmc.Code("x-key"), " header with every batch of readings. With the key in ",
             dmc.Code("COMPOSTIQ_API_KEY"), ":"],
            size="sm",
        ),
        dmc.Code(READINGS_EXAMPLE, block=True),
        dmc.Text("The API answers 200 with the readings it stored, or 401 if the key is wrong or has been revoked.", size="xs", c="dimmed"),
    ]


def register_device_page():
    """Registering without pairing: name it and pick a bin, then copy its API key.

    For a device that can't run the pairing flow. Unlike pairing, the key
    passes through the dashboard: it is shown on the second step, this once,
    to be copied onto the device, and is emptied from the page after that.
    """
    setup_step = dmc.Stack(
        [
            dmc.Text(REGISTER_INTRO, id="reg-setup-intro", c="dimmed", size="sm"),
            *_device_setup_fields("reg"),
            dmc.Group([button("Register device", icon_name="key", component_id="reg-create")], justify="flex-end"),
        ],
        maw=480,
        py="md",
    )
    key_step = dmc.Stack(
        [
            *_api_key_panel("reg"),
            dmc.Group([button("I’ve saved the key", icon_name="check", component_id="reg-saved")], justify="flex-end"),
        ],
        py="md",
    )
    done_step = dmc.Stack(
        [
            dmc.ThemeIcon(icon("check", 28), size=56, radius="xl", variant="light"),
            dmc.Title("Waiting for the first reading…", order=4, id="reg-done-title"),
            dmc.Text(id="reg-done-text", c="dimmed", size="sm", ta="center"),
            dmc.Group(
                [
                    button("Register another device", "default", component_id="reg-another"),
                    linked_button("Go to devices", "/devices", icon_name="arrow-right"),
                ]
            ),
        ],
        align="center",
        py="xl",
    )
    stepper = dmc.Stepper(
        id="reg-stepper",
        active=0,
        allowNextStepsSelect=False,
        children=[
            # no going back once the device exists: a second submit would register another
            dmc.StepperStep(label="Set up", description="Name & bin", children=setup_step, allowStepSelect=False),
            dmc.StepperStep(label="API key", description="Copy it", children=key_step, allowStepSelect=False),
            dmc.StepperCompleted(children=done_step),
        ],
    )
    return dmc.Box(
        [
            # the device's id - never its key, which only ever sits in the step-2 text
            dcc.Store(id="reg-state", data=None),
            # never changes: fires open_registration once when the page opens
            dcc.Store(id="reg-init", data=0),
            dcc.Interval(id="reg-poll", interval=2000, disabled=True),
            page_header("Connect hardware", "Register a device", "Add a device without pairing: choose its bin, then copy the API key it sends readings with."),
            dmc.Card(stepper, padding="lg"),
        ]
    )


def new_bin_page():
    form = dmc.Stack(
        [
            dmc.TextInput(id="new-bin-name", label="Bin name", placeholder="e.g. Bin 1", required=True),
            dmc.TextInput(id="new-bin-location", label="Location", placeholder="e.g. UNRAM Engineering"),
            dmc.Select(id="new-bin-country", label="Country", data=COUNTRIES, searchable=True, required=True, placeholder="Choose a country"),
            dmc.Text("Only the country is shown publicly, as part of the anonymised global statistics.", size="xs", c="dimmed"),
            dmc.Group([linked_button("Cancel", "/bins", variant="default"), button("Create bin", component_id="new-bin-submit")], justify="flex-end"),
        ],
        maw=480,
    )
    return dmc.Box(
        [
            page_header("Compost profile", "Create a compost bin", "Add the details used to group readings and calibrate insights."),
            dmc.Card(form, padding="lg"),
        ]
    )


# ------------------------------------------------------------ public pages ---

def not_found_page(signed_in):
    home = linked_button("Go to dashboard", "/dashboard") if signed_in else linked_button("Back to home", "/")
    return dmc.Stack(
        [
            dmc.Text("404", fz=64, fw=700, c="dimmed", lh=1),
            dmc.Title("Page not found", order=2),
            dmc.Text("That page doesn’t exist, or it has moved.", c="dimmed"),
            home,
        ],
        align="center",
        gap="sm",
        py=80,
    )


def _auth_card(title, subtitle, fields):
    card = dmc.Card(
        dmc.Stack([dmc.Stack([dmc.Title(title, order=2), dmc.Text(subtitle, c="dimmed", size="sm")], gap=4), *fields], gap="md"),
        padding="xl",
        w="100%",
        maw=440,
    )
    return dmc.Center(card, py={"base": "md", "sm": 48})


def _form_alert(component_id):
    # hidden until a callback has something to say
    return dmc.Alert(id=component_id, color="red", variant="light", icon=icon("alert-circle"), hide=True)


def login_page():
    return _auth_card(
        "Welcome back",
        "Sign in to see your bins and devices.",
        [
            _form_alert("login-error"),
            dmc.TextInput(id="login-email", label="Email", placeholder="you@example.com", name="email", autoComplete="email", leftSection=icon("mail", 16), value=""),
            dmc.PasswordInput(id="login-password", label="Password", name="password", autoComplete="current-password", value=""),
            button("Sign in", component_id="login-submit", fullWidth=True),
            dmc.Text(["New to CompostIQ? ", dmc.Anchor("Create an account", href="/register", fw=600)], size="sm", c="dimmed", ta="center"),
        ],
    )


def register_page():
    return _auth_card(
        "Create your account",
        "Free, and ready for your first device in a minute.",
        [
            _form_alert("register-error"),
            dmc.TextInput(id="register-email", label="Email", placeholder="you@example.com", name="email", autoComplete="email", leftSection=icon("mail", 16), required=True, value=""),
            dmc.TextInput(id="register-name", label="Display name", description="Optional. Shown in the dashboard instead of your email.", name="name", autoComplete="name", value=""),
            dmc.PasswordInput(id="register-password", label="Password", description="At least 8 characters.", name="new-password", autoComplete="new-password", required=True, value=""),
            dmc.PasswordInput(id="register-confirm", label="Confirm password", name="confirm-password", autoComplete="new-password", required=True, value=""),
            button("Create account", component_id="register-submit", fullWidth=True),
            dmc.Text(["Already have an account? ", dmc.Anchor("Sign in", href="/login", fw=600)], size="sm", c="dimmed", ta="center"),
        ],
    )


# ----------------------------------------------------------------- account ---

def account_page(user):
    profile = dmc.Card(
        dmc.Stack(
            [
                _card_title("Profile", "Display name", "Shown in the dashboard. Leave it empty to use your email."),
                dmc.TextInput(id="account-name", label="Display name", value=user.get("display_name") or "", name="name", autoComplete="name"),
                dmc.TextInput(label="Email", value=user["email"], disabled=True),
                dmc.Group(button("Save", component_id="account-name-save"), justify="flex-end"),
            ]
        ),
        padding="lg",
    )
    password = dmc.Card(
        dmc.Stack(
            [
                _card_title("Password", "Change password"),
                dmc.PasswordInput(id="account-current-password", label="Current password", name="current-password", autoComplete="current-password", value=""),
                dmc.PasswordInput(id="account-new-password", label="New password", description="At least 8 characters.", name="new-password", autoComplete="new-password", value=""),
                dmc.PasswordInput(id="account-confirm-password", label="Confirm new password", name="confirm-password", autoComplete="new-password", value=""),
                dmc.Group(button("Change password", component_id="account-password-save"), justify="flex-end"),
            ]
        ),
        padding="lg",
    )
    danger = dmc.Card(
        dmc.Group(
            [
                dmc.Stack(
                    [
                        dmc.Text("Danger zone", size="xs", fw=700, tt="uppercase", c="red"),
                        dmc.Title("Delete account", order=4),
                        dmc.Text("Deletes your bins and all their readings, and unpairs your devices. This cannot be undone.", size="sm", c="dimmed"),
                    ],
                    gap=2,
                    flex=1,
                    miw=220,
                ),
                button("Delete account", "outline", icon_name="trash", component_id="account-delete-open", color="red"),
            ],
            justify="space-between",
        ),
        padding="lg",
        style={"borderColor": "var(--mantine-color-red-outline)"},
    )
    confirm = dmc.Modal(
        dmc.Stack(
            [
                dmc.Text("This deletes your bins, devices and all their readings. It cannot be undone.", size="sm"),
                dmc.PasswordInput(id="account-delete-password", label="Enter your password to confirm", name="password", autoComplete="current-password", value="", **{"data-autofocus": True}),
                dmc.Group(
                    [
                        button("Cancel", "default", component_id="account-delete-cancel"),
                        button("Delete my account", component_id="account-delete-confirm", color="red"),
                    ],
                    justify="flex-end",
                ),
            ]
        ),
        id="account-delete-modal",
        title="Delete your account?",
        centered=True,
        opened=False,
    )
    return dmc.Box(
        [
            page_header("Account", "Your account", "Manage how you appear and how you sign in."),
            dmc.Stack([dmc.SimpleGrid([profile, password], cols={"base": 1, "md": 2}), danger], gap="md"),
            confirm,
        ]
    )
