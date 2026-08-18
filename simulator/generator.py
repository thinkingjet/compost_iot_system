"""
Generates fake sensor data for one compost bin, going through all the
stages defined in composting_stages.py. Temperature climbs/falls toward
a target instead of just picking random numbers, moisture slowly dries
out with occasional "turning" bumps, and the gas readings are based on
how active the pile is (linked to temperature) instead of being random
too. At the end we add some noise to make it look like real sensor data.
"""
import math
import random
from datetime import datetime, timedelta

import pandas as pd

from composting_stages import STAGES

AMBIENT_TEMP = 28.0
SAMPLE_INTERVAL_MINUTES = 30
TURNING_CHANCE_PER_DAY = 0.2
MISSED_READING_CHANCE = 0.02

TEMP_NOISE_STD = 0.5
MOISTURE_NOISE_STD = 1.0
O2_NOISE_STD = 0.3
CO2_NOISE_STD = 0.2
NH3_NOISE_STD = 0.03

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


def get_activity_level(temp):
    # 0 = pile is basically cold/inactive, 1 = pile is as hot as it ever gets
    activity = (temp - AMBIENT_TEMP) / (GLOBAL_PEAK_TEMP - AMBIENT_TEMP)
    if activity < 0:
        activity = 0
    if activity > 1:
        activity = 1
    return activity


def update_moisture(moisture, activity, moisture_range, step_days):
    low = moisture_range[0]
    high = moisture_range[1]
    span = high - low

    # moisture slowly evaporates, faster when the pile is more active
    daily_loss = span * 0.15
    moisture = moisture - daily_loss * (0.5 + activity) * step_days

    # every now and then the pile gets turned (or it rains) and moisture jumps back up
    if random.random() < TURNING_CHANCE_PER_DAY * step_days:
        moisture = moisture + random.uniform(0.4, 0.8) * span

    if moisture < low - 2:
        moisture = low - 2
    if moisture > high + 2:
        moisture = high + 2

    return moisture


def get_true_gases(activity, stage):
    o2_low, o2_high = stage["o2_range"]
    co2_low, co2_high = stage["co2_range"]
    nh3_low, nh3_high = stage["nh3_relative"]

    # more activity = more oxygen used up, so this one goes the other way
    o2 = o2_high - activity * (o2_high - o2_low)
    co2 = co2_low + activity * (co2_high - co2_low)
    nh3 = nh3_low + activity * (nh3_high - nh3_low)

    return o2, co2, nh3


def add_noise(value, std):
    return value + random.gauss(0, std)


def generate_stage_data(stage, start_time, start_temp, start_moisture):
    duration_days = get_stage_duration(stage)
    step_days = SAMPLE_INTERVAL_MINUTES / (24 * 60)

    num_steps = round(duration_days / step_days)
    if num_steps < 1:
        num_steps = 1

    target_temp = get_temp_target(start_temp, stage["temp_range"])
    tau_days = duration_days * 0.3
    if tau_days < 0.25:
        tau_days = 0.25

    rows = []
    temp = start_temp
    moisture = start_moisture

    for step in range(num_steps):
        days_in_stage = step * step_days
        timestamp = start_time + timedelta(days=days_in_stage)

        temp = get_true_temp(days_in_stage, start_temp, target_temp, tau_days)
        activity = get_activity_level(temp)
        moisture = update_moisture(moisture, activity, stage["moisture_range"], step_days)
        o2, co2, nh3 = get_true_gases(activity, stage)

        # sometimes a reading just doesn't arrive (bad connection etc.)
        if random.random() < MISSED_READING_CHANCE:
            continue

        nh3_reading = round(add_noise(nh3, NH3_NOISE_STD), 3)
        if nh3_reading < 0:
            nh3_reading = 0.0
        if nh3_reading > 1:
            nh3_reading = 1.0

        rows.append({
            "timestamp": timestamp,
            "stage_id": stage["id"],
            "stage_name": stage["name"],
            "temperature_c": round(add_noise(temp, TEMP_NOISE_STD), 2),
            "moisture_pct": round(add_noise(moisture, MOISTURE_NOISE_STD), 2),
            "o2_pct": round(add_noise(o2, O2_NOISE_STD), 2),
            "co2_pct": round(add_noise(co2, CO2_NOISE_STD), 2),
            "nh3_relative": nh3_reading,
        })

    end_time = start_time + timedelta(days=duration_days)
    return rows, temp, moisture, end_time


def generate_bin_data(start_time=None, seed=None):
    if seed is not None:
        random.seed(seed)

    if start_time is None:
        current_time = datetime.now()
    else:
        current_time = start_time

    temp = AMBIENT_TEMP
    moisture = (STAGES[0]["moisture_range"][0] + STAGES[0]["moisture_range"][1]) / 2

    all_rows = []
    for stage in STAGES:
        rows, temp, moisture, current_time = generate_stage_data(stage, current_time, temp, moisture)
        all_rows = all_rows + rows

    return pd.DataFrame(all_rows)


if __name__ == "__main__":
    df = generate_bin_data(seed=42)
    print(df.head(10))
    print("Total rows:", len(df))

    print()
    for stage in STAGES:
        stage_rows = df[df["stage_id"] == stage["id"]]
        avg_temp = stage_rows["temperature_c"].mean()
        print(stage["name"], "- average temperature:", round(avg_temp, 2))
