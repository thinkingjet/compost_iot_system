import dash_mantine_components as dmc
from components import (
    alert_card,
    bin_card,
    button,
    detail_tabs,
    device_card,
    linked_button,
    metric_card,
    page_header,
    plot,
    section_header,
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
from theme import icon

CARD_GRID = {"base": 1, "sm": 2, "lg": 3}


def _card_title(eyebrow, title, subtitle=None):
    children = [dmc.Text(eyebrow, size="xs", fw=700, tt="uppercase", c="dimmed"), dmc.Title(title, order=4)]
    if subtitle:
        children.append(dmc.Text(subtitle, size="xs", c="dimmed"))
    return dmc.Stack(children, gap=2)


# --------------------------------------------------------------- overview ---

def dashboard_page():
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
                "Good morning, UNRAM",
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
    return dmc.Box(
        [
            page_header(
                "Hardware",
                "Devices",
                "Connected sensors across all compost locations.",
                linked_button("Pair a device", "/devices/add", icon_name="link"),
            ),
            dmc.SimpleGrid([device_card(item) for item in DEVICES], cols=CARD_GRID),
        ]
    )


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

def add_device_page():
    """Pairing wizard (UI only for now - wired to POST /pairing/claim later)."""
    code_step = dmc.Stack(
        [
            dmc.Text("Power on your CompostIQ device and open its local page. Start pairing there, then enter the 6-digit code it shows.", c="dimmed", size="sm"),
            dmc.PinInput(id="pair-code", length=6, type="number", oneTimeCode=True, size="lg"),
            dmc.Text("Codes expire after 10 minutes.", size="xs", c="dimmed"),
        ],
        align="flex-start",
        gap="md",
        py="md",
    )
    details_step = dmc.Stack(
        [
            dmc.TextInput(id="pair-device-name", label="Device name", placeholder="e.g. Outer Sensor", value=""),
            dmc.Select(id="pair-bin", label="Compost bin", data=[{"value": b["id"], "label": b["name"]} for b in BINS], placeholder="Choose a bin", allowDeselect=False),
            dmc.Anchor("Or create a new bin", href="/bins/new", size="sm"),
        ],
        maw=420,
        py="md",
    )
    done_step = dmc.Stack(
        [
            dmc.ThemeIcon(icon("check", 28), size=56, radius="xl", variant="light"),
            dmc.Title("Waiting for your device…", order=4),
            dmc.Text("Your device collects its key and starts sending readings. This page updates once the first reading arrives.", c="dimmed", size="sm"),
        ],
        align="center",
        py="xl",
    )
    stepper = dmc.Stepper(
        id="pair-stepper",
        active=0,
        children=[
            dmc.StepperStep(label="Enter code", description="From the device", children=code_step),
            dmc.StepperStep(label="Name & bin", description="Where it lives", children=details_step),
            dmc.StepperCompleted(children=done_step),
        ],
    )
    actions = dmc.Group(
        [button("Back", "default", component_id="pair-back"), button("Continue", component_id="pair-next")],
        justify="flex-end",
        mt="md",
    )
    return dmc.Box(
        [
            page_header("Connect hardware", "Pair a device", "Link a CompostIQ device to your account with its pairing code."),
            dmc.Card([stepper, actions], padding="lg"),
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
