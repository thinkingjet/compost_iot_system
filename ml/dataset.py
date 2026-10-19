"""
Labelled training and test data for the stage classifier, straight from the simulator.

Each batch is one bin run from fresh feedstock until it's cured (or 90 days),
driven step by step through the simulator's pile model (emulator/model.py,
which runs the stage table in simulator/composting_stages.py). The model knows
the true stage, and that's the label. Around it we add what the model leaves
out: a day/night ambient swing, some of that swing leaking into the core, an
owner who turns and waters (or doesn't), sensor noise, missed readings and the
logger's sample rate.

Every setting is drawn per batch from a preset, so one CSV covers a wide range
of bins:

    train         broad: everything varied at once (domain randomisation)
    validation    same distribution as train, different seeds (model selection)
    test-grid     one setting pushed at a time from a baseline, 15 batches each,
                  plus a combined worst case (final evaluation)

Each run writes two files:

    <name>.csv.gz          one row per reading, in the simulator's column names
                           (simulator/generator.py, mock-data schema) plus
                           batch_id, ambient_c, mq135 and faults. Time is
                           elapsed_h, hours since the batch started (much
                           smaller than a timestamp per row)
    <name>_batches.csv     one row per batch: the settings it was drawn with,
                           including its start_time

Usage (from the repo root):

    python ml/dataset.py --preset train --batches 800
    python ml/dataset.py --preset validation --batches 200
    python ml/dataset.py --preset test-grid
"""
import argparse
import math
import random
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "simulator"))
sys.path.insert(0, str(REPO / "emulator"))

from composting_stages import STAGES  # noqa: E402
from mock_data import _mq135_response as mq135_response  # noqa: E402  the repo's own MQ-135 model
from model import NOISE, SENSOR_LIMITS, CompostModel  # noqa: E402

DATASETS = Path(__file__).resolve().parent / "datasets"
LAST_STAGE = STAGES[-1]["id"]
MAX_DAYS = 90
EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)

# how an owner looks after the bin: (turn every N days, water when moisture is below %)
CARE = {
    "diligent": {"turn_every": [3, 4], "water_below": [50.0]},
    "irregular": {"turn_every": [None, 2, 3, 5, 7], "water_below": [None, 42.0, 45.0, 48.0, 52.0]},
    "neglected": {"turn_every": [None], "water_below": [None]},
    "overwatered": {"turn_every": [None, 3, 5], "water_below": [62.0]},
}

# settings a batch is drawn from: (low, high) ranges, or {choice: weight}
BASELINE = {
    "ambient_base_c": (26.0, 30.0),
    "ambient_swing_c": (2.5, 4.5),
    "core_leak": (0.10, 0.35),
    "heat_factor": (0.8, 1.0),
    "care": {"irregular": 1},
    "noise_scale": (1.0, 1.0),
    "sample_minutes": {30: 1},
    "missing_chance": (0.02, 0.02),
    # every MQ-135 unit reads differently and drifts (per-unit R0, warm-up, humidity)
    "mq135_gain": (1.0, 1.0),
    "mq135_offset": (0.0, 0.0),
    "mq135_drift_per_day": (0.0, 0.0),
    "has_mq135": {True: 1},
    "has_ambient_probe": {True: 1},
}
BROAD = {
    "ambient_base_c": (22.0, 34.0),
    "ambient_swing_c": (2.0, 5.0),
    "core_leak": (0.05, 0.40),
    "heat_factor": (0.15, 1.0),
    "care": {"diligent": 3, "irregular": 5, "neglected": 1, "overwatered": 1},
    "noise_scale": (0.5, 2.5),
    "sample_minutes": {15: 1, 30: 2, 60: 1},
    "missing_chance": (0.0, 0.10),
    "mq135_gain": (0.7, 1.4),
    "mq135_offset": (-30.0, 30.0),
    "mq135_drift_per_day": (-1.0, 1.0),
    # some loggers have no gas sensor, or no ambient probe yet (today's hardware)
    "has_mq135": {True: 9, False: 1},
    "has_ambient_probe": {True: 4, False: 1},
}

# the test grid: one change from BASELINE per scenario
TEST_GRID = {
    "baseline": {},
    "ambient_cool": {"ambient_base_c": (22.0, 25.0)},
    "ambient_hot": {"ambient_base_c": (31.0, 34.0)},
    "bin_tiny": {"heat_factor": (0.15, 0.25)},
    "bin_small": {"heat_factor": (0.30, 0.45)},
    "bin_medium": {"heat_factor": (0.50, 0.70)},
    "care_diligent": {"care": {"diligent": 1}},
    "care_neglected": {"care": {"neglected": 1}},
    "care_overwatered": {"care": {"overwatered": 1}},
    "noise_low": {"noise_scale": (0.5, 0.5)},
    "noise_high": {"noise_scale": (2.5, 2.5)},
    "noise_extreme": {"noise_scale": (4.0, 4.0)},
    "sampling_15min": {"sample_minutes": {15: 1}},
    "sampling_60min": {"sample_minutes": {60: 1}},
    "dropouts_10pct": {"missing_chance": (0.10, 0.10)},
    "dropouts_25pct": {"missing_chance": (0.25, 0.25)},
    "mq135_drift": {"mq135_gain": (0.5, 1.8), "mq135_offset": (-60.0, 60.0), "mq135_drift_per_day": (-2.0, 2.0)},
    "no_mq135": {"has_mq135": {False: 1}},
    "no_ambient_probe": {"has_ambient_probe": {False: 1}},
    "worst_case": {"ambient_base_c": (31.0, 34.0), "heat_factor": (0.15, 0.45),
                   "care": {"neglected": 1}, "noise_scale": (2.5, 2.5), "missing_chance": (0.10, 0.10)},
}

# seeds never overlap between splits
SEED_BASE = {"train": 1_000_000, "validation": 2_000_000, "test-grid": 3_000_000}


def _draw(r, spec):
    if isinstance(spec, dict):
        choices, weights = zip(*spec.items())
        return r.choices(choices, weights=weights)[0]
    low, high = spec
    return low if low == high else r.uniform(low, high)


def draw_settings(seed, spec):
    r = random.Random(seed)
    s = {name: _draw(r, value) for name, value in spec.items()}
    s["turn_every_days"] = r.choice(CARE[s["care"]]["turn_every"])
    s["water_below_pct"] = r.choice(CARE[s["care"]]["water_below"])
    s["start_time"] = EPOCH + timedelta(days=r.randrange(0, 270), hours=r.randrange(0, 24))
    return s


def simulate_batch(batch_id, seed, settings):
    """Run one bin. Returns (readings rows, summary)."""
    r = random.Random(seed)
    s = settings
    pile = CompostModel(rng=random.Random(seed + 1), ambient_temp_c=s["ambient_base_c"],
                        heat_factor=s["heat_factor"])
    step_min = int(s["sample_minutes"])
    dt_days = step_min / 1440
    turn_every = s["turn_every_days"]
    next_turn = turn_every if turn_every else math.inf
    start_hour = s["start_time"].hour
    rows, peak, reached_peak = [], 0.0, False
    for k in range(int(MAX_DAYS * 1440 / step_min)):
        if pile.cured:
            break
        minutes = k * step_min
        days = minutes / 1440
        hour_of_day = (start_hour + minutes / 60) % 24
        amb = s["ambient_base_c"] + s["ambient_swing_c"] * math.sin(2 * math.pi * (hour_of_day - 9) / 24)

        # the owner checks the bin once a day at 08:00
        if hour_of_day == 8 and s["water_below_pct"] is not None and pile.moisture < s["water_below_pct"]:
            pile.add_water()
        if days >= next_turn and pile.stage_id < LAST_STAGE:
            pile.turn()
            next_turn += turn_every

        true = pile.true_values()
        peak = max(peak, true["temperature_c"])
        reached_peak = reached_peak or pile.stage_id == 2
        if r.random() >= s["missing_chance"]:
            noisy = {}
            for field, value in true.items():
                if field == "temperature_c":
                    value += s["core_leak"] * (amb - s["ambient_base_c"])
                low, high = SENSOR_LIMITS[field]
                noisy[field] = min(high, max(low, value + r.gauss(0, NOISE[field] * s["noise_scale"])))
            mq = mq135_response(noisy["co2_pct"], noisy["nh3_relative"], r)
            mq = s["mq135_gain"] * mq + s["mq135_offset"] + s["mq135_drift_per_day"] * days
            # rounded to well under each sensor's noise, which keeps the CSVs small
            rows.append({
                "batch_id": batch_id,
                "elapsed_h": round(minutes / 60, 2),
                "temperature_c": round(noisy["temperature_c"], 1),
                "moisture_pct": round(noisy["moisture_pct"], 1),
                # second DS18B20 outside the bin, blank when the logger has none
                "ambient_c": round(amb + r.gauss(0, 0.3), 1) if s["has_ambient_probe"] else None,
                "o2_pct": round(noisy["o2_pct"], 1),
                "co2_pct": round(noisy["co2_pct"], 1),
                "nh3_relative": round(noisy["nh3_relative"], 2),
                "mq135": round(max(0.0, mq)) if s["has_mq135"] else None,
                "stage_id": pile.stage_id,
                "faults": "|".join(pile.faults()),
            })
        pile.step(dt_days)

    summary = {"days": round(k * step_min / 1440, 2), "cured": pile.cured,
               "peak_temp_c": round(peak, 2), "reached_peak_stage": reached_peak,
               "turns": pile.turns, "waterings": pile.waterings}
    return rows, summary


def _run(job):
    return simulate_batch(*job)


def build(preset, batches, workers):
    jobs = []
    if preset == "test-grid":
        for cell, (scenario, change) in enumerate(TEST_GRID.items()):
            spec = {**BASELINE, **change}
            for i in range(batches):
                seed = SEED_BASE[preset] + cell * 1000 + i
                jobs.append((f"test-{scenario}-{i:03d}", seed, draw_settings(seed, spec), scenario))
    else:
        for i in range(batches):
            seed = SEED_BASE[preset] + i
            jobs.append((f"{preset}-{i:04d}", seed, draw_settings(seed, BROAD), preset))

    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(_run, [(b, seed, s) for b, seed, s, _ in jobs], chunksize=4))

    readings = pd.DataFrame([row for rows, _ in results for row in rows])
    info = pd.DataFrame([{"batch_id": b, "split": preset, "scenario": scenario, "seed": seed,
                          **{k: v for k, v in s.items() if k != "start_time"},
                          "start_time": s["start_time"].strftime("%Y-%m-%dT%H:%M:%SZ"), **summary}
                         for (b, seed, s, scenario), (_, summary) in zip(jobs, results)])
    return readings, info


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--preset", choices=["train", "validation", "test-grid"], required=True)
    parser.add_argument("--batches", type=int, default=None,
                        help="batches to simulate (test-grid: per scenario). Defaults: 800 / 200 / 15")
    parser.add_argument("--name", default=None, help="output file stem (default: the preset name)")
    parser.add_argument("--out-dir", type=Path, default=DATASETS, help="where to write (default: ml/datasets)")
    parser.add_argument("--workers", type=int, default=None)
    args = parser.parse_args()

    batches = args.batches or {"train": 800, "validation": 200, "test-grid": 15}[args.preset]
    name = args.name or args.preset.replace("-", "_")
    readings, info = build(args.preset, batches, args.workers)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    out = args.out_dir / f"{name}.csv.gz"
    readings.to_csv(out, index=False, compression={"method": "gzip", "compresslevel": 9})
    info.to_csv(args.out_dir / f"{name}_batches.csv", index=False)
    print(f"{name}: {len(info)} batches, {len(readings):,} readings -> {out}")


if __name__ == "__main__":
    main()
