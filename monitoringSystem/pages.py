from datetime import datetime, timedelta

import dash_mantine_components as dmc
from dash import dcc, html

import api_client
from api_client import ApiError, ApiUnavailable, NotAuthenticated
from components import (
    account_type,
    alert_card,
    bin_card,
    button,
    detail_tabs,
    device_card,
    is_online,
    linked_button,
    metric_card,
    page_header,
    paired_device_card,
    plot,
    section_header,
    time_ago,
    user_bin_card,
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
from figures import GAS_SENSORS, daily_averages_figure, phase_history_figure, readings_figure, sparkline
from settings import PUBLIC_API_URL, SITE_TIMEZONE
from theme import SENSOR_COLORS, icon

CARD_GRID = {"base": 1, "sm": 2, "lg": 3}


def _card_title(eyebrow, title, subtitle=None):
    children = [dmc.Text(eyebrow, size="xs", fw=700, tt="uppercase", c="dimmed"), dmc.Title(title, order=4)]
    if subtitle:
        children.append(dmc.Text(subtitle, size="xs", c="dimmed"))
    return dmc.Stack(children, gap=2)


# --------------------------------------------------------------- overview ---

# what each alert type from GET /alerts means, and what to do about it
ALERT_TEXT = {
    "too_hot": ("Temperature is too high", "Turn the pile to cool it"),
    "too_dry": ("Moisture is too low", "Add water"),
    "too_wet": ("Moisture is too high", "Turn it and add dry material"),
    "low_oxygen": ("Oxygen is very low", "Turn the pile to let air in"),
    "high_co2": ("CO₂ is very high", "Turn the pile to let air in"),
    "offline": ("Sensor offline", "Check its power and Wi-Fi"),
}

# What to do about each alert, for the Maintenance tab. From the BC Ministry of
# Agriculture troubleshooting factsheet (2025), Cornell Composting and UC ANR;
# the offline steps and checking the lid are ours. To be checked with Prof. Komang.
MAINTENANCE_STEPS = {
    "too_hot": [
        "Turn the pile to let the heat out.",
        "If it stays hot, make the pile smaller.",
        "Check it hasn’t dried out, and add water while turning if it has.",
    ],
    "too_dry": [
        "Add water while turning the pile, so it spreads evenly.",
        "Stop when a squeezed handful feels damp and holds its shape but doesn’t drip.",
        "Cover the bin to keep the moisture in.",
    ],
    "too_wet": [
        "Turn the pile to let excess water evaporate.",
        "If it’s still soggy, mix in dry material (sawdust, wood chips, dry leaves, shredded cardboard) and turn again.",
        "Cover the bin to keep rain out.",
    ],
    "low_oxygen": [
        "Turn the pile to let air in.",
        "Mix in coarse, dry material (wood chips, twigs) to open up air channels.",
        "If it smells like rotten eggs, it’s probably too wet or packed down: follow the steps for a wet pile.",
    ],
    "high_co2": [
        "Turn the pile: the microbes are using up the air faster than it gets in.",
        "Mix in coarse material so air can move through.",
        "Check the lid and vents aren’t blocked.",
    ],
    "offline": [
        "Check the device has power.",
        "Check it’s in range of the Wi-Fi.",
        "Restart it.",
    ],
}


def alerts_grid(alerts):
    if not alerts:
        return dmc.Text("Nothing needs attention right now.", c="dimmed", size="sm")
    cards = []
    for alert in alerts:
        title, action = ALERT_TEXT.get(alert["type"], (alert["type"], ""))
        where = alert["bin_name"] if alert["type"] != "offline" else f"{alert['bin_name']} · {alert['device_name'] or 'Sensor'}"
        detail = f"{where} · {action} · started {time_ago(alert['triggered_at'])}"
        cards.append(alert_card(alert["type"], title, detail, alert["severity"].title()))
    return dmc.SimpleGrid(cards, cols={"base": 1, "md": 2})


def bin_cards(bins, devices, alerts):
    """One card per bin, each given the devices that are in it and its open alerts."""
    return [
        user_bin_card(
            b,
            [d for d in devices if d["bin"] and d["bin"]["id"] == b["id"]],
            [a for a in alerts if a["bin_id"] == b["id"]],
        )
        for b in bins
    ]


def overview_cards(bins, devices, alerts):
    """The three cards at the top of the home page."""
    online = [d for d in devices if is_online(d)]
    reporting = len({d["bin"]["id"] for d in online if d["bin"]})
    needs_setup = sum(not d["set_up"] for d in devices)
    high = sum(alert["severity"] == "high" for alert in alerts)

    metrics = [
        {"label": "Bins", "value": str(len(bins)), "unit": "", "delta": f"{reporting} reporting",
         "icon": "bin", "color": "health", "values": []},
        {"label": "Devices", "value": f"{len(online)}/{len(devices)}", "unit": "online",
         "delta": f"{needs_setup} need setup" if needs_setup else "All set up", "icon": "device", "color": "oxygen", "values": []},
        {"label": "Alerts", "value": str(len(alerts)), "unit": "open",
         "delta": f"{high} high priority" if alerts else "All clear", "icon": "alert", "color": "red" if high else "health", "values": []},
    ]
    return dmc.SimpleGrid([metric_card(metric) for metric in metrics], cols={"base": 1, "sm": 3})


def dashboard_page(user):
    now = datetime.now(SITE_TIMEZONE)
    header = page_header(
        f"{now:%A} · {now.day} {now:%B}",
        f"Welcome back, {user_name(user)}",
        "Here’s what’s happening across your compost system.",
        linked_button("Pair a device", "/devices/add", icon_name="link"),
    )
    try:
        bins = api_client.list_bins()
        devices = api_client.list_devices()
        alerts = api_client.list_alerts()
    except NotAuthenticated:
        return dmc.Stack([header, dmc.Alert("Your session has ended. Please sign in again.", color="yellow")])
    except (ApiError, ApiUnavailable):
        return dmc.Stack([header, dmc.Alert("Can’t load your compost system right now. Try again in a moment.", color="red")])

    return dmc.Stack(
        [
            header,
            overview_cards(bins, devices, alerts),
            dmc.Box(
                [
                    section_header("Needs attention"),
                    dmc.Box(alerts_grid(alerts), id="home-alerts"),
                    # asks the API again every minute, so new problems show up without a reload
                    dcc.Interval(id="alerts-poll", interval=60_000),
                ]
            ),
            dmc.Box([section_header("Compost bins", "View all", "/bins"),
                     dmc.SimpleGrid(bin_cards(bins, devices, alerts), cols=CARD_GRID) if bins else dmc.Text("No bins yet.", c="dimmed", size="sm")]),
            dmc.Box([section_header("Devices", "View all", "/devices"),
                     dmc.SimpleGrid([paired_device_card(d) for d in devices], cols=CARD_GRID) if devices else dmc.Text("No devices yet.", c="dimmed", size="sm")]),
        ],
        gap="xl",
    )


def bins_page():
    header = page_header(
                "Management",
                "Compost bins",
                "Monitor active batches and manage every compost location.",
                linked_button("Create bin", "/bins/new", icon_name="plus"),
            )
    try:
        user_bins = api_client.list_bins()
        devices = api_client.list_devices()
        alerts = api_client.list_alerts()
    except NotAuthenticated:
        return dmc.Box([header, dmc.Alert("You are not authenticated. Please sign in again.", color="orange")])
    except (ApiError, ApiUnavailable):
        return dmc.Box([header, dmc.Alert("Something went wrong. Please try again in a bit.", color="red")])
    if not user_bins:
        return dmc.Box([header, dmc.Text("You do not have any added bins yet.")])
    return dmc.Box([header, dmc.SimpleGrid(bin_cards(user_bins, devices, alerts), cols=CARD_GRID)])


def devices_page():
    header = page_header(
        "Hardware",
        "Devices",
        "The CompostIQ devices on your account.",
        linked_button("Pair a device", "/devices/add", icon_name="link"),
    )
    try:
        devices = api_client.list_devices()
    except NotAuthenticated:
        return dmc.Box([header, dmc.Alert("Your session has ended. Sign in again to see your devices.", color="yellow")])
    except (ApiUnavailable, ApiError):
        return dmc.Box([header, dmc.Alert("Can’t load your devices right now. Try again in a moment.", color="red")])

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
        return dmc.Box([header, empty])
    return dmc.Box([header, dmc.SimpleGrid([paired_device_card(device) for device in devices], cols=CARD_GRID)])


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


def readings_strip(readings):
    """The latest value of each sensor, with a small line of the readings behind it."""
    def chip(label, key, unit, color):
        values = [r[key] for r in readings]
        return _sensor_chip(label, f"{values[-1]:.1f}" if values else "–", unit, values, color)

    return dmc.SimpleGrid(
        [
            chip("Temperature", "temperature", "°C", "temperature"),
            chip("Moisture", "moisture_percent", "%", "moisture"),
            chip("Oxygen", "o2_percent", "%", "oxygen"),
            chip("CO₂", "co2_percent", "%", "co2"),
            chip("NH₃", "nh3_ratio", "", "nh3"),
        ],
        cols={"base": 2, "md": 5},
        mb="md",
    )


def live_panel(kind, readings, device_names):
    updated = f"Updated {time_ago(readings[-1]['timestamp'])}" if readings else "No readings yet"
    toolbar = dmc.Group(
        [
            _card_title("Live data", "Environmental telemetry" if kind == "bin" else "Sensor readings", updated),
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
    chart = plot(readings_figure(readings, device_names), name=f"{kind}-live-chart")
    gas_chart = plot(readings_figure(readings, device_names, GAS_SENSORS), name=f"{kind}-gas-chart")
    return dmc.Box([readings_strip(readings), dmc.Card([toolbar, chart, gas_chart], padding="md")])


def _hours_text(hours):
    # rounded down below two days, so 23.6 h doesn't read as the full day the model needs
    if hours < 1:
        return "under an hour"
    if hours < 48:
        return "1 hour" if hours < 2 else f"{int(hours)} hours"
    return f"{round(hours / 24)} days"


def _percent(probability):
    # an estimate is never certain, so 0.9997 reads ">99%", not "100%"
    return ">99%" if probability >= 0.995 else f"{probability:.0%}"


def stage_card(stage):
    """The compost stage the model estimates (GET /bins/{id}/stage), labelled as
    an estimate. stage is None when the API couldn't give one."""
    header = dmc.Group(
        [
            dmc.Text("Compost stage", size="xs", fw=700, tt="uppercase", c="dimmed"),
            dmc.Badge("Model estimate", variant="light", color="gray"),
        ],
        justify="space-between",
    )
    if stage is None:
        return dmc.Card([header, dmc.Text("The stage estimate isn't available right now.", size="sm", c="dimmed", mt="xs")], padding="md")
    if stage["stage"] is None:
        has = f"it has {_hours_text(stage['history_hours'])}" if stage["last_reading_at"] else "it has none yet"
        return dmc.Card(
            [
                header,
                dmc.Title("Not enough readings yet", order=3, mt=4),
                dmc.Text(f"The model needs a day of readings to estimate the stage ({has}).", size="sm", c="dimmed"),
            ],
            padding="md",
        )

    current = stage["stage_id"]
    # the API lists a probability for every stage, in order, so a swapped model
    # with other stages shows its own
    stages = list(stage["probabilities"])
    if stage["raw_stage"] == stage["stage"]:
        confidence = f"{_percent(stage['confidence'])} confidence"
    else:
        # the filter only moves forward, so for a while it can disagree with the latest hour
        confidence = f"the latest hour alone looks like {stage['raw_stage']} ({_percent(stage['confidence'])})"
    steps = dmc.SimpleGrid(
        [
            dmc.Stack(
                [
                    dmc.Progress(value=100 if i <= current else 0, size="sm"),
                    # no c=None for the current stage: Mantine can't parse a null colour and drops the text
                    dmc.Text(name, size="xs", visibleFrom="sm", **({"fw": 700} if i == current else {"c": "dimmed"})),
                ],
                gap=4,
            )
            for i, name in enumerate(stages)
        ],
        cols=len(stages),
        spacing="xs",
        mt="sm",
    )
    note = (
        f"Estimated by a machine-learning model from {_hours_text(stage['history_hours'])} of core temperature and "
        f"moisture readings, up to {time_ago(stage['last_reading_at'])}. It can be wrong, so check the pile too."
    )
    return dmc.Card(
        [
            header,
            dmc.Title(stage["stage"], order=3, mt=4),
            dmc.Text(f"Stage {current + 1} of {len(stages)} · {confidence}", size="sm", c="dimmed"),
            steps,
            dmc.Text(note, size="xs", c="dimmed", mt="sm"),
        ],
        padding="md",
    )


def maintenance_panel(alerts):
    """Steps to fix each of the bin's open alerts (GET /alerts?bin_id=...), one card each."""
    if not alerts:
        return dmc.Card(dmc.Text("Nothing to do right now. Steps will show here if this bin needs attention.", c="dimmed", size="sm"), padding="md")
    cards = []
    for alert in alerts:
        title = ALERT_TEXT.get(alert["type"], (alert["type"],))[0]
        if alert["type"] == "offline":
            title += f" · {alert['device_name'] or 'Sensor'}"
        cards.append(dmc.Card(
            [
                _card_title(f"Started {time_ago(alert['triggered_at'])}", title),
                dmc.List([dmc.ListItem(step) for step in MAINTENANCE_STEPS.get(alert["type"], [])], type="ordered", size="sm", mt="sm"),
            ],
            padding="md",
        ))
    return dmc.SimpleGrid(cards, cols={"base": 1, "md": 2})


# the daily averages GET /bins/{id}/history returns besides temperature
HISTORY_MOISTURE = [("Moisture", "avg_moisture", SENSOR_COLORS["moisture"], "%")]
HISTORY_GASES = [
    ("Oxygen", "avg_o2", SENSOR_COLORS["oxygen"], "%"),
    ("CO₂", "avg_co2", SENSOR_COLORS["co2"], "%"),
    ("NH₃", "avg_nh3", SENSOR_COLORS["nh3"], ""),
]


def history_panel(history, subtitle=None):
    temperature = dmc.Card(
        [
            dmc.Group([_card_title("Phase analysis", "Temperature over time", subtitle), dmc.Badge("Last 30 days", variant="light", color="gray")], justify="space-between", mb="sm"),
            plot(phase_history_figure(history)),
        ],
        padding="md",
    )
    moisture = dmc.Card(
        [_card_title("Daily average", "Moisture"), plot(daily_averages_figure(history, HISTORY_MOISTURE))],
        padding="md",
    )
    gases = dmc.Card(
        [_card_title("Daily average", "Gases"), plot(daily_averages_figure(history, HISTORY_GASES))],
        padding="md",
    )
    return dmc.Stack([temperature, dmc.SimpleGrid([moisture, gases], cols={"base": 1, "md": 2})], gap="md")


def devices_panel():
    return dmc.Card(
        [
            dmc.Group([dmc.Title("Devices monitoring Bin 1", order=4), linked_button("Pair a device", "/devices/add", icon_name="link")], justify="space-between", mb="md"),
            dmc.SimpleGrid([device_card(device) for device in DEVICES[:2]], cols={"base": 1, "sm": 2}),
        ],
        padding="md",
    )


def bin_devices_panel(bin_data, devices):
    cards = [paired_device_card(device) for device in devices]
    return dmc.Card(
        [
            dmc.Group([dmc.Title(f"Devices monitoring {bin_data['name']}", order=4), linked_button("Pair a device", "/devices/add", icon_name="link")], justify="space-between", mb="md"),
            dmc.SimpleGrid(cards, cols={"base": 1, "sm": 2}) if cards else dmc.Text("No devices in this bin yet.", c="dimmed", size="sm"),
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


def bin_settings_panel(bin_data):
    form = dmc.Stack(
        [
            _card_title("General", "Bin settings", "Update how this compost batch appears across CompostIQ."),
            dmc.SimpleGrid(
                [
                    dmc.TextInput(id="bin-name", label="Name", value=bin_data["name"]),
                    dmc.TextInput(id="bin-location", label="Location", value=bin_data["location"]),
                    dmc.Select(id="bin-country", label="Country", data=COUNTRIES, value=bin_data["country_code"],
                               searchable=True, allowDeselect=False),
                ],
                cols={"base": 1, "sm": 2},
            ),
            dmc.Group(button("Save changes", component_id="save-bin-settings"), justify="flex-end"),
        ]
    )
    delete = dmc.Stack(
        [
            _card_title("Danger zone", "Delete bin", "Removes the bin and all its readings. Its devices will need setting up again."),
            # asks "are you sure?" in the browser; the callback only runs on OK
            dcc.ConfirmDialogProvider(
                button("Delete bin", "light", color="red"),
                id="delete-bin",
                message="Delete this bin and all its readings? This can't be undone.",
            ),
        ]
    )
    return dmc.Card(dmc.SimpleGrid([form, delete], cols={"base": 1, "md": 2}, spacing="xl"), padding="lg")


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


def device_settings_panel(device, bins):
    form = dmc.Stack(
        [
            _card_title("General", "Device settings", "Rename this sensor or move it to another bin."),
            dmc.SimpleGrid(
                [
                    dmc.TextInput(id="device-name", label="Name", value=device["name"]),
                    dmc.Select(id="device-bin", label="Bin", data=[{"value": b["id"], "label": b["name"]} for b in bins],
                               value=device["bin"]["id"] if device["bin"] else None, allowDeselect=False),
                ],
                cols={"base": 1, "sm": 2},
            ),
            dmc.Group(button("Save changes", component_id="save-device-settings"), justify="flex-end"),
        ]
    )
    registered = device["registration"] == "manual"
    details = dmc.Stack(
        [
            _card_title("System information", "Device details"),
            _detail_row("Hardware ID", device["hardware_id"] or "None (registered with an API key)"),
            _detail_row("Model", device["model"] or "Unknown"),
            _detail_row("Firmware", device["firmware_version"] or "Unknown"),
            _detail_row("Registered" if registered else "Paired", time_ago(device["paired_at"]) if device["paired_at"] else "Unknown"),
            _detail_row("Last seen", time_ago(device["last_seen_at"]) if device["last_seen_at"] else "No readings yet"),
        ],
        gap="xs",
    )
    general = dmc.Card(dmc.SimpleGrid([form, details], cols={"base": 1, "md": 2}, spacing="xl"), padding="lg")
    remove = _remove_device_card(device, registered)
    if not registered:
        # a paired device gets a new key by being paired again
        return dmc.Stack([general, remove], gap="md")
    key = dmc.Card(
        dmc.Group(
            [
                _card_title("API key", "Replace the key", "For a key that was lost or leaked. The old one stops working straight away."),
                button("New API key", "light", icon_name="key", component_id={"type": "new-key", "device": device["id"]}),
            ],
            justify="space-between",
        ),
        padding="lg",
    )
    return dmc.Stack([general, key, remove, *_new_key_modal()], gap="md")


def _remove_device_card(device, registered):
    """Take the device off the account (DELETE /devices/{id}): every key it has
    stops working at once, so it can't send readings until it joins again."""
    name = device["name"] or "this device"
    bin_name = device["bin"]["name"] if device["bin"] else None
    again = "register it again and put the new key on it" if registered else "pair it again"
    readings = f" Its past readings stay in {bin_name}." if bin_name else ""
    return dmc.Card(
        dmc.Group(
            [
                _card_title("Danger zone", "Remove device",
                            f"Takes it off your account and its key stops working straight away. To use it again, {again}."),
                # asks "are you sure?" in the browser; the callback only runs on OK
                dcc.ConfirmDialogProvider(
                    button("Remove device", "light", icon_name="trash", color="red"),
                    id="remove-device",
                    message=f"Remove {name} from your account? Its key stops working at once, so it can't send readings.{readings}",
                ),
            ],
            justify="space-between",
        ),
        padding="lg",
    )


def detail_page(kind, item_id, tab):
    is_bin = kind == "bin"
    valid = {"live", "history", "settings"} | ({"maintenance", "devices"} if is_bin else set())
    tab = tab if tab in valid else "live"

    if tab == "live":
        # old mock route (/bin/live): no bin to read from, so an empty chart
        panel = live_panel(kind, [], {})
    elif tab == "history":
        panel = history_panel([])
    elif tab == "settings":
        panel = settings_panel(kind)
    elif tab == "maintenance":
        panel = maintenance_panel([])
    else:
        panel = devices_panel()

    header = page_header(
        "Compost bin" if is_bin else "Monitoring device",
        "Bin 1" if is_bin else "Outer Sensor",
        "UNRAM · Peak decomposition" if is_bin else "Bin 1 · ESP32-C3",
    )
    return dmc.Box([header, detail_tabs(kind, tab), panel])


def bin_detail_page(bin_id, tab):
    if tab not in {"live", "maintenance", "history", "devices", "settings"}:
        tab = "live"

    try:
        bin_data = api_client.get_bin(bin_id)
        all_devices = api_client.list_devices() if tab in ("devices", "live") else []
        readings = api_client.get_bin_records(bin_id) if tab == "live" else []
        history = api_client.get_bin_history(bin_id) if tab == "history" else []
        alerts = api_client.list_alerts(bin_id=bin_id) if tab in ("live", "maintenance") else []
    except NotAuthenticated:
        return dmc.Alert("Your session has ended. Please sign in again.", color="yellow")
    except ApiError:
        # 404 or a malformed id: the bin isn't there (or isn't the user's)
        return dmc.Alert("This bin doesn't exist.", color="yellow")
    except ApiUnavailable:
        return dmc.Alert("Can't load this bin right now.", color="red")

    stage = None
    if tab == "live":
        try:
            stage = api_client.get_bin_stage(bin_id)
        except (NotAuthenticated, ApiError, ApiUnavailable):
            # the card says the estimate is unavailable (a 503 when the API has no
            # model) and the rest of the page still works
            pass

    if tab == "history":
        panel = history_panel(history)
    elif tab == "settings":
        panel = bin_settings_panel(bin_data)
    elif tab == "maintenance":
        panel = maintenance_panel(alerts)
    elif tab == "devices":
        # the API lists all the user's devices; keep the ones in this bin
        panel = bin_devices_panel(bin_data, [d for d in all_devices if d["bin"] and d["bin"]["id"] == bin_id])
    else:
        panel = dmc.Stack([stage_card(stage), live_panel("bin", readings, {d["id"]: d["name"] for d in all_devices})], gap="md")
        if alerts:
            panel = dmc.Stack([dmc.Box([section_header("Needs attention"), alerts_grid(alerts)]), panel], gap="lg")

    header = page_header("Compost bin", bin_data["name"], bin_data["location"])
    return dmc.Box([header, detail_tabs("bin", tab), panel])


def device_detail_page(device_id, tab):
    if tab not in {"live", "history", "settings"}:
        tab = "live"

    try:
        device = api_client.get_device(device_id)
        # the settings form lets the user pick another of their bins
        bins = api_client.list_bins() if tab == "settings" else []
        readings = api_client.get_device_records(device_id) if tab == "live" else []
        # history is kept per bin, so the device page shows the bin it's in
        history = api_client.get_bin_history(device["bin"]["id"]) if tab == "history" and device["bin"] else []
    except NotAuthenticated:
        return dmc.Alert("Your session has ended. Please sign in again.", color="yellow")
    except ApiError:
        return dmc.Alert("This device doesn't exist.", color="yellow")
    except ApiUnavailable:
        return dmc.Alert("Can't load this device right now.", color="red")

    if tab == "history":
        bin_name = device["bin"]["name"] if device["bin"] else None
        panel = history_panel(history, f"For the whole of {bin_name}, all its sensors" if bin_name else "Not in a bin yet")
    elif tab == "settings":
        panel = device_settings_panel(device, bins)
    else:
        panel = live_panel("device", readings, {})

    bin_name = device["bin"]["name"] if device["bin"] else "Not in a bin yet"
    header = page_header("Monitoring device", device["name"] or "New device", bin_name)
    return dmc.Box([header, detail_tabs("device", tab), panel])


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


# ---------------------------------------------------------------- research ---
# A researcher's pages, and the only ones they have.

def _coming_soon(icon_name, text):
    """An empty page's one card, until what goes on it is built."""
    return dmc.Card(
        dmc.Stack(
            [
                dmc.ThemeIcon(icon(icon_name, 26), size=52, radius="xl", variant="light"),
                dmc.Title("Coming soon", order=4),
                dmc.Text(text, c="dimmed", size="sm", ta="center"),
            ],
            align="center",
            py="xl",
        ),
        padding="lg",
    )


def research_keys_card(keys, new_key=None):
    """The researcher's keys (GET /auth/research-keys), the form for a new
    one, and a new key, shown this once."""
    shown = []
    if new_key:
        shown = [dmc.Alert(
            [
                dmc.Text("Copy it now: this is the only time it’s shown.", size="sm", mb="xs"),
                dmc.Group(
                    [
                        dmc.Code(new_key, id="research-new-key", fz="sm", flex=1, style={"wordBreak": "break-all"}),
                        dmc.CopyButton(target_id="research-new-key", children="Copy", copiedChildren="Copied", size="xs", variant="default"),
                    ],
                    wrap="nowrap",
                ),
            ],
            title="Your new key",
            color="yellow",
            variant="light",
        )]
    rows = [
        dmc.Group(
            [
                dmc.Stack([dmc.Text(key["name"], fw=600, size="sm"), dmc.Text(f"Created {time_ago(key['created_at'])}", c="dimmed", size="xs")], gap=0),
                dcc.ConfirmDialogProvider(
                    button("Delete", "light", color="red", size="xs"),
                    id={"type": "research-key-delete", "id": key["id"]},
                    message=f"Delete the key “{key['name']}”? Anything using it stops working at once.",
                ),
            ],
            justify="space-between",
        )
        for key in keys
    ]
    form = dmc.Group(
        [
            dmc.TextInput(id="research-key-name", placeholder="Key name, e.g. Lab server", value="", flex=1),
            button("Create key", icon_name="key", component_id="research-key-create"),
        ],
    )
    return dmc.Stack(
        [
            *shown,
            form,
            *(rows or [dmc.Text("No keys yet.", c="dimmed", size="sm")]),
            dmc.Text(["You can have up to 5 keys. Send one in the ", dmc.Code("x-research-key"), " header."], c="dimmed", size="xs"),
        ],
    )


def research_keys_page():
    header = page_header("Research", "Research access", "Create a key to query anonymised CompostIQ data.")
    try:
        keys = api_client.list_research_keys()
    except NotAuthenticated:
        return dmc.Box([header, dmc.Alert("Your session has ended. Please sign in again.", color="yellow")])
    except (ApiError, ApiUnavailable):
        return dmc.Box([header, dmc.Alert("Can’t load your keys right now. Try again in a moment.", color="red")])
    return dmc.Stack([
        header,
        dmc.Text("Your account can read country-level aggregates. Create a key below, copy it once, then use it with the research API.", size="sm"),
        dmc.Card(research_keys_card(keys), id="research-keys", padding="lg"),
        dmc.Group([
            linked_button("Explore data", "/research/data", "default", icon_name="chart"),
            linked_button("API documentation", "/research/docs", "default", icon_name="book"),
        ]),
    ], gap="md")


RESEARCH_LABELS = {
    "day": "UTC day", "country_code": "Country", "bin_count": "Bins", "reading_count": "Readings",
    "temperature_c": "Temp °C", "moisture_percent": "Moisture %", "o2_percent": "O₂ %",
    "co2_percent": "CO₂ %", "nh3_ratio": "NH₃ ratio",
    "type": "Alert", "alert_count": "Times", "avg_hours_to_resolve": "Avg hours to fix",
}


def _research_cell(row, key):
    if key == "day":
        return str(row[key])[:10]
    if key + "_min" in row:
        # a sensor: average (min–max)
        return f"{row[key]} ({row[key + '_min']}–{row[key + '_max']})"
    return row[key]


def research_data_result(result):
    rows = result["data"]
    if not rows:
        return dmc.Alert("Nothing found for these filters.", color="blue", variant="light")
    # the columns of whichever view this is; spread is shown inside the sensor cells
    keys = [key for key in rows[0] if not key.endswith(("_min", "_max", "_sd"))]
    return dmc.Stack([
        dmc.Text(f"{len(rows)} rows. Sensors show average (min–max); the CSV also has the standard deviation.", size="sm", c="dimmed"),
        dmc.ScrollArea(html.Table([
            html.Thead(html.Tr([html.Th(RESEARCH_LABELS.get(key, key)) for key in keys])),
            html.Tbody([html.Tr([html.Td(_research_cell(row, key)) for key in keys]) for row in rows]),
        ], style={"width": "100%", "borderCollapse": "collapse"})),
    ], gap="sm")


def research_data_page():
    today = datetime.now().astimezone().date()
    start = (today - timedelta(days=30)).isoformat() + "T00:00:00Z"
    end = today.isoformat() + "T23:59:59Z"
    try:
        countries = api_client.research_countries()
        initial = research_data_result(api_client.research_data("daily", start=start, end=end))
    except (ApiError, ApiUnavailable, NotAuthenticated):
        countries, initial = [], dmc.Alert("Could not load research data right now.", color="red")
    return dmc.Stack([
        page_header("Research", "Explore data", "Country-level compost readings across participating owners."),
        dmc.Card(dmc.Stack([
            dmc.Group([
                dmc.SegmentedControl(id="research-kind", value="daily", data=[
                    {"label": "Daily", "value": "daily"}, {"label": "Overall", "value": "overview"},
                    {"label": "Alerts", "value": "alerts"}]),
                dmc.Select(id="research-country", label="Country", placeholder="All countries", clearable=True, data=[
                    {"value": c["country_code"], "label": f"{c['country_code']} · {c['bin_count']} bins"} for c in countries]),
                dmc.TextInput(id="research-start", label="From (ISO 8601)", value=start),
                dmc.TextInput(id="research-end", label="To (ISO 8601)", value=end),
                button("Apply filters", component_id="research-data-apply"),
                button("Download CSV", "default", icon_name="download", component_id="research-download-button"),
                dcc.Download(id="research-download"),
            ], align="end"),
            dmc.Text("Data is grouped by UTC day. Names, locations, IDs and individual readings are excluded.", size="xs", c="dimmed"),
            dmc.Box(initial, id="research-data-result"),
        ], gap="md"), padding="lg"),
        linked_button("Use the research API", "/research/docs", "default", icon_name="book"),
    ], gap="lg")


def research_docs_page():
    return dmc.Box(
        [
            page_header("Research", "Docs", "How to use the research API, and what its data holds."),
            dmc.Card(dmc.Stack([
                dmc.Text("Create an API key on the API keys page. Send it as x-research-key in each request.", size="sm"),
                dmc.Code("GET /research/overview?country_code=ID&start=2026-10-01T00:00:00Z&end=2026-10-16T00:00:00Z", block=True),
                dmc.Code("GET /research/daily?country_code=ID&start=2026-10-01T00:00:00Z&end=2026-10-16T00:00:00Z", block=True),
                dmc.Code("GET /research/alerts?country_code=ID", block=True),
                dmc.Code("GET /research/countries", block=True),
                dmc.Text("overview: one row per country for the whole period. daily: one row per country per UTC day. alerts: how often each alert type happened per country, and how long it took to fix. countries: which countries have data, with bin and reading counts and the date range.", size="sm"),
                dmc.Text("Country code is optional. Times are ISO 8601 with a timezone; the range can be up to 366 days. Defaults to the last 30 days. Add format=csv to overview, daily or alerts to get a CSV file.", size="sm"),
                dmc.Text("Sensor values come as the average, min, max and standard deviation (e.g. temperature_c, temperature_c_min, temperature_c_max, temperature_c_sd). No personal, bin, device or individual reading data is returned.", size="sm"),
                linked_button("Explore data", "/research/data", "default", icon_name="chart"),
            ], gap="md"), padding="lg"),
        ]
    )


# ------------------------------------------------------------ public pages ---

def not_found_page(home="/"):
    """`home` is where the button leads: the signed-in user's home page."""
    return dmc.Stack(
        [
            dmc.Text("404", fz=64, fw=700, c="dimmed", lh=1),
            dmc.Title("Page not found", order=2),
            dmc.Text("That page doesn’t exist, or it has moved.", c="dimmed"),
            linked_button("Back to home", home),
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
        "Sign in to your CompostIQ account.",
        [
            _form_alert("login-error"),
            dmc.TextInput(id="login-email", label="Email", placeholder="you@example.com", name="email", autoComplete="email", leftSection=icon("mail", 16), value=""),
            dmc.PasswordInput(id="login-password", label="Password", name="password", autoComplete="current-password", value=""),
            button("Sign in", component_id="login-submit", fullWidth=True),
            dmc.Text(["New to CompostIQ? ", dmc.Anchor("Create an account", href="/register", fw=600)], size="sm", c="dimmed", ta="center"),
        ],
    )


# the account types a new user picks from: (role, title, what it's for)
ROLES = [
    ("owner", "Compost bin owner", "I have compost bins and want to monitor them."),
    ("researcher", "Researcher", "I want to use the public composting data."),
]


def _role_card(role, title, description):
    return dmc.RadioCard(
        dmc.Group(
            [dmc.RadioIndicator(), dmc.Stack([dmc.Text(title, fw=600, size="sm"), dmc.Text(description, c="dimmed", size="xs")], gap=0)],
            wrap="nowrap",
            align="flex-start",
        ),
        value=role,
        p="sm",
        radius="md",
        className="ciq-role-card",
    )


def register_page():
    return _auth_card(
        "Create your account",
        "Free, and ready for your first device in a minute.",
        [
            _form_alert("register-error"),
            dmc.RadioGroup(
                dmc.Stack([_role_card(*role) for role in ROLES], gap="xs"),
                id="register-role",
                label="I'm signing up as",
                value="owner",
            ),
            dmc.TextInput(id="register-email", label="Email", placeholder="you@example.com", name="email", autoComplete="email", leftSection=icon("mail", 16), required=True, value=""),
            dmc.TextInput(id="register-name", label="Display name", description="Optional. Shown in the dashboard instead of your email.", name="name", autoComplete="name", value=""),
            dmc.PasswordInput(id="register-password", label="Password", description="At least 8 characters.", name="new-password", autoComplete="new-password", required=True, value=""),
            dmc.PasswordInput(id="register-confirm", label="Confirm password", name="confirm-password", autoComplete="new-password", required=True, value=""),
            button("Create account", component_id="register-submit", fullWidth=True),
            dmc.Text(["Already have an account? ", dmc.Anchor("Sign in", href="/login", fw=600)], size="sm", c="dimmed", ta="center"),
        ],
    )


# ----------------------------------------------------------------- account ---

# what deleting an account takes with it, by account type: (summary, warning)
DELETES = {
    "owner": ("Deletes your bins and all their readings, and unpairs your devices. This cannot be undone.",
              "This deletes your bins, devices and all their readings. It cannot be undone."),
    "researcher": ("Deletes your account and signs you out. This cannot be undone.",
                   "This deletes your account. It cannot be undone."),
}


def account_page(user):
    kind = account_type(user)
    type_name = {role: title for role, title, _ in ROLES}[kind]
    deletes_summary, deletes_warning = DELETES[kind]
    profile = dmc.Card(
        dmc.Stack(
            [
                _card_title("Profile", "Display name", "Shown in the dashboard. Leave it empty to use your email."),
                dmc.TextInput(id="account-name", label="Display name", value=user.get("display_name") or "", name="name", autoComplete="name"),
                dmc.TextInput(label="Email", value=user["email"], disabled=True),
                dmc.TextInput(label="Account type", value=type_name, description="Chosen when you signed up.", disabled=True),
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
                        dmc.Text(deletes_summary, size="sm", c="dimmed"),
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
                dmc.Text(deletes_warning, size="sm"),
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
