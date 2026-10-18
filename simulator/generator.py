"""
Generates fake sensor data for one compost bin, going through all the
stages defined in composting_stages.py. Temperature climbs/falls toward
a target instead of just picking random numbers, moisture slowly dries
out with occasional "turning" bumps, and the gas readings are based on
how active the pile is (linked to temperature) instead of being random
too. At the end we add some noise to make it look like real sensor data.

Active Thermophilic and Peak Decomposition share one heating curve, and a
reading only counts as Peak Decomposition once the core has held 55C (see
composting_stages.py). The gases and the drying rate don't depend on the
stage at all, so nothing jumps the moment the stage changes.
"""
import json
import math
import os
import random
from datetime import datetime, timedelta

import pandas as pd

from composting_stages import (
    PEAK_HOLD_DAYS,
    PEAK_TEMP_C,
    STAGES,
    START_MOISTURE_PCT,
    drying_per_day,
    hot_phase_curve,
    pile_gases,
)

# paths built off this script's own location, not wherever it's run from
THIS_FOLDER = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(THIS_FOLDER, "..", "mock-data", "compostiq_mock_dataset.schema.json")
# generated datasets live next to the simulator now, not in ../mock-data
DATA_DIR = os.path.join(THIS_FOLDER, "Data")
DATA_PATH = os.path.join(DATA_DIR, "compostiq_mock_dataset.json")

# the schema is our blueprint: it says what fields exist and what range each
# one is allowed to be in, so we read it once and use it to clamp readings
with open(SCHEMA_PATH) as f:
    SCHEMA = json.load(f)
FIELD_RULES = SCHEMA["items"]["properties"]

AMBIENT_TEMP = 28.0
SAMPLE_INTERVAL_MINUTES = 30
TURNING_CHANCE_PER_DAY = 0.2
TURNING_MOISTURE_BUMP = (2.0, 6.0)  # % a turn (or a shower) puts back, in any stage
TOP_UP_BELOW_PCT = 50.0  # only a pile that's looking dry gets topped up
MOISTURE_FLOOR = 15.0  # same limits as the emulator's pile
MOISTURE_CEILING = 85.0
MISSED_READING_CHANCE = 0.02

TEMP_NOISE_STD = 0.5
MOISTURE_NOISE_STD = 1.0
O2_NOISE_STD = 0.3
CO2_NOISE_STD = 0.2
NH3_NOISE_STD = 0.03

# same numbers again, keyed by column name, so a caller (e.g. the simulator UI)
# can hand us a partial override without knowing our constant names
NOISE_DEFAULTS = {
    "temperature_c": TEMP_NOISE_STD,
    "moisture_pct": MOISTURE_NOISE_STD,
    "o2_pct": O2_NOISE_STD,
    "co2_pct": CO2_NOISE_STD,
    "nh3_relative": NH3_NOISE_STD,
}


def resolve_noise(noise):
    # fill any missing sensor in the override with its default
    if not noise:
        return dict(NOISE_DEFAULTS)
    resolved = dict(NOISE_DEFAULTS)
    for field in NOISE_DEFAULTS:
        if noise.get(field) is not None:
            resolved[field] = float(noise[field])
    return resolved

# highest temperature any stage reaches, used to work out how "active" the
# pile is at a given moment (find it once instead of looping every step)
GLOBAL_PEAK_TEMP = 0
for stage in STAGES:
    if stage["temp_range"][1] > GLOBAL_PEAK_TEMP:
        GLOBAL_PEAK_TEMP = stage["temp_range"][1]


def get_stage_duration(stage):
    low, likely, high = stage["duration_days"]
    return random.triangular(low, high, likely)


def get_temp_target(current_temp, temp_range):
    # head towards whichever end of the range we are already closer to
    low = temp_range[0]
    high = temp_range[1]
    midpoint = (low + high) / 2
    if current_temp <= midpoint:
        return high
    else:
        return low


def get_true_temp(days_in_stage, start_temp, target_temp, tau_days):
    # moves fast towards the target at first, then slows down (like a pot
    # of water heating up and levelling off)
    return target_temp + (start_temp - target_temp) * math.exp(-days_in_stage / tau_days)


def get_core_temp(curve_temp, heat_factor):
    # the curve is for a full-size bin; a smaller one keeps less of the heat
    # above ambient, and a pile never sits below ambient on its own
    return AMBIENT_TEMP + heat_factor * max(0.0, curve_temp - AMBIENT_TEMP)


def get_activity_level(temp):
    # 0 = pile is basically cold/inactive, 1 = pile is as hot as it ever gets
    activity = (temp - AMBIENT_TEMP) / (GLOBAL_PEAK_TEMP - AMBIENT_TEMP)
    if activity < 0:
        activity = 0
    if activity > 1:
        activity = 1
    return activity


def update_moisture(moisture, activity, step_days):
    # moisture slowly evaporates, faster when the pile is more active. The
    # rate and the limits are the same in every stage: clamping to each
    # stage's own range made moisture snap into place at a stage change
    moisture = moisture - drying_per_day(activity) * step_days

    # every now and then the pile gets turned (or it rains) and moisture jumps
    # back up - once it's drying out, or a well-kept pile would creep up to soaking
    if moisture < TOP_UP_BELOW_PCT and random.random() < TURNING_CHANCE_PER_DAY * step_days:
        moisture = moisture + random.uniform(TURNING_MOISTURE_BUMP[0], TURNING_MOISTURE_BUMP[1])

    if moisture < MOISTURE_FLOOR:
        moisture = MOISTURE_FLOOR
    if moisture > MOISTURE_CEILING:
        moisture = MOISTURE_CEILING

    return moisture


def get_true_gases(activity):
    # one curve for every stage (composting_stages.pile_gases): more activity
    # = more oxygen used up and the same amount of CO2 made, so the gases
    # follow the temperature and don't jump when the stage changes
    return pile_gases(activity)


def add_noise(value, std):
    return value + random.gauss(0, std)


def clamp_to_schema(value, field_name):
    # look up the allowed range for this field straight from the schema
    # file, instead of hardcoding "if x < 0: x = 0" per field
    rules = FIELD_RULES[field_name]
    if "minimum" in rules and value < rules["minimum"]:
        value = rules["minimum"]
    if "maximum" in rules and value > rules["maximum"]:
        value = rules["maximum"]
    return value


def generate_stage_data(stage, start_time, start_temp, start_moisture, days_left=None,
                        sample_interval_minutes=None, noise=None, heat_factor=1.0):
    if sample_interval_minutes is None:
        sample_interval_minutes = SAMPLE_INTERVAL_MINUTES
    noise = resolve_noise(noise)

    # how long this stage would naturally run for
    full_duration_days = get_stage_duration(stage)

    hot_phase = stage["id"] == 1
    if hot_phase:
        # Active Thermophilic runs on into Peak Decomposition on the same
        # heating curve, so this covers both stages
        active_days = full_duration_days
        full_duration_days = active_days + get_stage_duration(STAGES[2])
        target_temp, tau_days = hot_phase_curve(start_temp, active_days, full_duration_days)
    else:
        target_temp = get_temp_target(start_temp, stage["temp_range"])
        # tau is based on the stage's natural (untruncated) duration, so cutting
        # the output short doesn't change how fast the stage actually behaves
        tau_days = full_duration_days * 0.3
        if tau_days < 0.25:
            tau_days = 0.25

    # how long we're actually allowed to run it for, if a day limit was set
    duration_days = full_duration_days
    if days_left is not None and duration_days > days_left:
        duration_days = days_left

    step_days = sample_interval_minutes / (24 * 60)

    num_steps = round(duration_days / step_days)
    if num_steps < 1:
        num_steps = 1

    rows = []
    temp = start_temp
    moisture = start_moisture
    label = stage
    hot_hold_days = 0.0

    for step in range(num_steps):
        days_in_stage = step * step_days
        timestamp = start_time + timedelta(days=days_in_stage)

        temp = get_true_temp(days_in_stage, start_temp, target_temp, tau_days)
        core_temp = get_core_temp(temp, heat_factor)
        activity = get_activity_level(core_temp)
        moisture = update_moisture(moisture, activity, step_days)
        o2, co2, nh3 = get_true_gases(activity)

        # Peak Decomposition starts once the core has held 55C for a while;
        # a bin that never gets that hot stays in Active Thermophilic
        if core_temp >= PEAK_TEMP_C:
            hot_hold_days = hot_hold_days + step_days
        else:
            hot_hold_days = 0.0
        if hot_phase and hot_hold_days >= PEAK_HOLD_DAYS:
            label = STAGES[2]

        # sometimes a reading just doesn't arrive (bad connection etc.)
        if random.random() < MISSED_READING_CHANCE:
            continue

        temperature_reading = clamp_to_schema(round(add_noise(core_temp, noise["temperature_c"]), 2), "temperature_c")
        moisture_reading = clamp_to_schema(round(add_noise(moisture, noise["moisture_pct"]), 2), "moisture_pct")
        o2_reading = clamp_to_schema(round(add_noise(o2, noise["o2_pct"]), 2), "o2_pct")
        co2_reading = clamp_to_schema(round(add_noise(co2, noise["co2_pct"]), 2), "co2_pct")
        nh3_reading = clamp_to_schema(round(add_noise(nh3, noise["nh3_relative"]), 3), "nh3_relative")

        rows.append({
            "timestamp": timestamp,
            "stage_id": label["id"],
            "stage_name": label["name"],
            "temperature_c": temperature_reading,
            "moisture_pct": moisture_reading,
            "o2_pct": o2_reading,
            "co2_pct": co2_reading,
            "nh3_relative": nh3_reading,
        })

    end_time = start_time + timedelta(days=duration_days)
    return rows, temp, moisture, end_time, duration_days


def generate_bin_data(start_time=None, seed=None, start_stage_id=0, max_days=None,
                      sample_interval_minutes=None, noise=None, heat_factor=1.0):
    """
    start_time    - when the simulated timeline begins (defaults to now)
    seed          - set this to get the exact same "random" data every run
    start_stage_id - which stage to start at (0 = Early Mesophilic, ... 4 = Maturation)
    max_days      - stop once this many days of data have been generated
                     (None = run all the way through to the end of Maturation)
    sample_interval_minutes - gap between readings (None = SAMPLE_INTERVAL_MINUTES)
    noise         - per-sensor standard deviations, e.g. {"temperature_c": 0.5}.
                     Anything left out falls back to NOISE_DEFAULTS.
    heat_factor   - how much of a full-size pile's heat above ambient the bin
                     keeps: 1.0 = the stage table as written, about 0.2 = a
                     small Takakura basket that peaks near 35C. A bin that
                     never holds 55C skips Peak Decomposition.
    """
    if seed is not None:
        random.seed(seed)

    if start_time is None:
        current_time = datetime.now()
    else:
        current_time = start_time

    stages_to_run = [stage for stage in STAGES if stage["id"] >= start_stage_id]

    first_stage = stages_to_run[0]
    if first_stage["id"] == 0:
        # Stage 0 specifically can't start below ambient (see composting_stages.py)
        temp = AMBIENT_TEMP
        # every batch starts a little wetter or drier, so moisture isn't a clock
        moisture = random.uniform(START_MOISTURE_PCT[0], START_MOISTURE_PCT[1])
    else:
        temp = (first_stage["temp_range"][0] + first_stage["temp_range"][1]) / 2
        moisture = random.uniform(first_stage["moisture_range"][0], first_stage["moisture_range"][1])

    all_rows = []
    days_used = 0.0

    for stage in stages_to_run:
        # Peak Decomposition is part of Active Thermophilic's run when that came first
        if stage["id"] == 2 and first_stage["id"] < 2:
            continue

        days_left = None
        if max_days is not None:
            days_left = max_days - days_used
            if days_left <= 0:
                break

        rows, temp, moisture, current_time, days_added = generate_stage_data(
            stage, current_time, temp, moisture, days_left,
            sample_interval_minutes=sample_interval_minutes,
            noise=noise,
            heat_factor=heat_factor,
        )
        all_rows = all_rows + rows
        days_used = days_used + days_added

    return pd.DataFrame(all_rows)


def dataframe_to_records(df):
    # turn the dataframe into a plain list of dicts so it reads like a normal JSON array
    records = df.to_dict(orient="records")
    for row in records:
        row["timestamp"] = row["timestamp"].isoformat()
    return records


def save_json_file(records, filepath):
    folder = os.path.dirname(filepath)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)

    with open(filepath, "w") as f:
        json.dump(records, f, indent=2)


def ask_for_settings():
    print("Stages available:")
    for stage in STAGES:
        print(" ", stage["id"], "-", stage["name"])

    start_stage_input = input("Start stage id [0]: ").strip()
    if start_stage_input == "":
        start_stage_id = 0
    else:
        start_stage_id = int(start_stage_input)

    start_date_input = input("Start date, YYYY-MM-DD [today]: ").strip()
    if start_date_input == "":
        start_time = datetime.now()
    else:
        start_time = datetime.strptime(start_date_input, "%Y-%m-%d")

    max_days_input = input("Duration in days [no limit, full cycle]: ").strip()
    if max_days_input == "":
        max_days = None
    else:
        max_days = float(max_days_input)

    return start_stage_id, start_time, max_days


if __name__ == "__main__":
    start_stage_id, start_time, max_days = ask_for_settings()

    df = generate_bin_data(seed=42, start_stage_id=start_stage_id, start_time=start_time, max_days=max_days)
    print()
    print(df.head(10))
    print("Total rows:", len(df))

    print()
    for stage in STAGES:
        stage_rows = df[df["stage_id"] == stage["id"]]
        if len(stage_rows) == 0:
            continue
        avg_temp = stage_rows["temperature_c"].mean()
        print(stage["name"], "- average temperature:", round(avg_temp, 2))

    records = dataframe_to_records(df)
    save_json_file(records, DATA_PATH)
    print()
    print("Saved data to", DATA_PATH)
