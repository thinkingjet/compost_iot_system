"""
Features for the compost stage classifier, from a CSV of sensor readings.

Shared by train.py, predict.py and the notebook, so the model always sees
features computed the same way it was trained on.

Input: one row per reading, with
    temperature_c, moisture_pct            required
    timestamp (ISO) or elapsed_h           required, one of the two
    batch_id                               optional (one bin if missing)
    ambient_c                              optional (DEFAULT_AMBIENT_C if missing)
    mq135, o2_pct, co2_pct, nh3_relative   optional
    stage_id                               optional (the label, when known)

Readings can come at any interval. They're averaged onto a 30-minute grid,
gaps up to 2 h are carried forward (as a server would), and one feature row
comes out per hour. Every feature uses only past readings, so the same code
can run live.
"""
import numpy as np
import pandas as pd

STEP_H = 0.5                  # grid the features are computed on
W6, W24 = int(6 / STEP_H), int(24 / STEP_H)
CARRY_FORWARD_STEPS = 4       # 2 h
DEFAULT_AMBIENT_C = 28.0      # simulator/generator.py's AMBIENT_TEMP, for CSVs without an ambient probe

STAGE_NAMES = ["Early Mesophilic", "Active Thermophilic", "Peak Decomposition", "Cooling", "Maturation"]
SENSORS = ["temperature_c", "moisture_pct", "ambient_c", "mq135", "o2_pct", "co2_pct", "nh3_relative"]

TEMP_HISTORY = ["temp", "temp_mean_6h", "temp_mean_24h", "temp_slope_6h", "temp_slope_24h", "temp_std_24h",
                "temp_peak", "below_peak", "hours_since_peak", "hours_above_45", "hours_above_55",
                "hours_above_55_run"]
MOISTURE = ["moist", "moist_mean_24h", "moist_slope_24h"]
AMBIENT = ["ambient_known", "amb_mean_24h", "dT", "dT_mean_24h", "dT_peak"]
SCALE_FREE = ["frac_of_peak", "frac_of_peak_24h", "slope_rel_6h", "slope_rel_24h", "std_rel_24h",
              "hours_since_peak"] + MOISTURE
MQ135 = ["mq135_mean_6h", "mq135_mean_24h", "mq135_slope_24h"]
SIM_GASES = ["o2_mean_6h", "co2_mean_6h", "nh3_mean_6h"]   # sensors the real bin doesn't have

FEATURE_SETS = {
    "core probe + moisture": TEMP_HISTORY + MOISTURE,
    "scale-free": SCALE_FREE + ["dT_peak"],
    "core + moisture + ambient": TEMP_HISTORY + MOISTURE + AMBIENT,
    "all hardware (+ scale-free)": list(dict.fromkeys(TEMP_HISTORY + MOISTURE + AMBIENT + SCALE_FREE)),
    "all hardware + MQ-135": list(dict.fromkeys(TEMP_HISTORY + MOISTURE + AMBIENT + SCALE_FREE + MQ135)),
    "+ simulated O2/CO2/NH3": list(dict.fromkeys(TEMP_HISTORY + MOISTURE + AMBIENT + SCALE_FREE + MQ135 + SIM_GASES)),
}


def read_readings(path):
    """Read a readings CSV (plain or .gz) and make sure it has batch_id and elapsed_h."""
    df = pd.read_csv(path, keep_default_na=False, na_values=[""], low_memory=False,
                     dtype={"batch_id": str, "faults": str})
    return prepare(df)


def prepare(df):
    df = df.copy()
    if "batch_id" not in df:
        df["batch_id"] = "bin"
    df["batch_id"] = df["batch_id"].astype(str)
    if "elapsed_h" not in df:
        if "timestamp" not in df:
            raise ValueError("readings need a timestamp or an elapsed_h column")
        ts = pd.to_datetime(df["timestamp"], utc=True)
        df["elapsed_h"] = (ts - ts.groupby(df["batch_id"]).transform("min")).dt.total_seconds() / 3600
    missing = [c for c in ("temperature_c", "moisture_pct") if c not in df]
    if missing:
        raise ValueError(f"readings are missing {missing}")
    for col in SENSORS:
        if col not in df:
            df[col] = np.nan          # ambient falls back to DEFAULT_AMBIENT_C in _one_batch
    return df.sort_values(["batch_id", "elapsed_h"], kind="stable").reset_index(drop=True)


def _one_batch(batch_id, g):
    # average onto the 30-minute grid, then carry short gaps forward
    slot = np.floor(g["elapsed_h"].to_numpy() / STEP_H + 1e-6).astype(int)
    cols = SENSORS + (["stage_id"] if "stage_id" in g else [])
    binned = g[cols].groupby(slot).mean()
    if "stage_id" in g:
        binned["stage_id"] = g["stage_id"].groupby(slot).last()
    binned = binned.reindex(np.arange(slot.max() + 1))
    binned[SENSORS] = binned[SENSORS].ffill(limit=CARRY_FORWARD_STEPS)
    hours = binned.index.to_numpy() * STEP_H
    T, M, A = binned.temperature_c, binned.moisture_pct, binned.ambient_c.fillna(DEFAULT_AMBIENT_C)

    f = pd.DataFrame(index=binned.index)
    f["batch_id"] = batch_id
    f["elapsed_h"] = hours
    if "stage_id" in binned:
        f["stage_id"] = binned.stage_id.ffill().bfill()
    f["temp"] = T
    f["temp_mean_6h"] = T.rolling(W6, min_periods=1).mean()
    f["temp_mean_24h"] = T.rolling(W24, min_periods=1).mean()
    f["temp_slope_6h"] = f.temp_mean_6h.diff(W6).fillna(0) / 6
    f["temp_slope_24h"] = f.temp_mean_24h.diff(W24).fillna(0) / 24
    f["temp_std_24h"] = T.rolling(W24, min_periods=2).std().fillna(0)
    f["temp_peak"] = f.temp_mean_6h.cummax()
    f["below_peak"] = f.temp_peak - f.temp_mean_6h
    at_peak = pd.Series(np.where(f.temp_mean_6h >= f.temp_peak, hours, np.nan), index=f.index).ffill()
    f["hours_since_peak"] = hours - at_peak
    hot45 = f.temp_mean_6h > 45
    hot55 = f.temp_mean_6h >= 55
    f["hours_above_45"] = hot45.cumsum() * STEP_H
    f["hours_above_55"] = hot55.cumsum() * STEP_H
    # how long the core has been at >= 55 C without a break (the Peak Decomposition rule)
    f["hours_above_55_run"] = hot55.groupby((~hot55).cumsum()).cumsum() * STEP_H

    f["moist"] = M
    f["moist_mean_24h"] = M.rolling(W24, min_periods=1).mean()
    f["moist_slope_24h"] = f.moist_mean_24h.diff(W24).fillna(0) / 24

    # share of the last 24 h with a real ambient reading (0 = no probe, ambient assumed)
    f["ambient_known"] = binned.ambient_c.notna().astype(float).rolling(W24, min_periods=1).mean()
    f["amb_mean_24h"] = A.rolling(W24, min_periods=1).mean()
    f["dT"] = T - A
    f["dT_mean_24h"] = f.temp_mean_24h - f.amb_mean_24h
    dT_6h = f.temp_mean_6h - A.rolling(W6, min_periods=1).mean()
    f["dT_peak"] = dT_6h.cummax()
    peak_heat = f.dT_peak.clip(lower=1.0)
    f["frac_of_peak"] = dT_6h / peak_heat
    f["frac_of_peak_24h"] = f.dT_mean_24h / peak_heat
    f["slope_rel_6h"] = f.temp_slope_6h / peak_heat
    f["slope_rel_24h"] = f.temp_slope_24h / peak_heat
    f["std_rel_24h"] = f.temp_std_24h / peak_heat

    Q = binned.mq135
    f["mq135_mean_6h"] = Q.rolling(W6, min_periods=1).mean()
    f["mq135_mean_24h"] = Q.rolling(W24, min_periods=1).mean()
    f["mq135_slope_24h"] = f.mq135_mean_24h.diff(W24) / 24
    f["o2_mean_6h"] = binned.o2_pct.rolling(W6, min_periods=1).mean()
    f["co2_mean_6h"] = binned.co2_pct.rolling(W6, min_periods=1).mean()
    f["nh3_mean_6h"] = binned.nh3_relative.rolling(W6, min_periods=1).mean()
    f["batch_day"] = hours / 24
    return f[(f.index % int(1 / STEP_H)) == 0]          # one row per hour


def make_features(readings):
    """Hourly feature rows for every batch in a readings frame (see module docstring)."""
    df = prepare(readings)
    parts = [_one_batch(b, g) for b, g in df.groupby("batch_id", sort=False)]
    out = pd.concat(parts, ignore_index=True)
    if "stage_id" in out:
        out["stage_id"] = out["stage_id"].astype(int)
    return out


# ---------------------------------------------------------------------------
# The stage filter: stages only move forward, so a causal left-to-right HMM
# over the classifier's hourly probabilities removes flicker.

def transition_matrix(stage_days=(2, 3, 5, 8, 30), skip_peak_share=0.4, speed=1.0):
    """Hourly transition probabilities from each stage's typical length (days).

    Active Thermophilic can skip Peak Decomposition and go straight to
    Cooling (a bin that never holds 55 C), so stage 1 has two exits.
    speed > 1 lets the filter move on sooner (less lag, a little more flicker).
    """
    k = len(stage_days)
    A = np.zeros((k, k))
    for s, days in enumerate(stage_days):
        leave = 0.0 if s == k - 1 else min(0.5, speed / (days * 24))
        A[s, s] = 1.0 - leave
        if s == 1:
            A[1, 2] = leave * (1 - skip_peak_share)
            A[1, 3] = leave * skip_peak_share
        elif leave:
            A[s, s + 1] = leave
    return A


def stage_filter(proba, transitions):
    """Forward pass over one batch's hourly class probabilities; returns the stage path."""
    belief = np.eye(len(transitions))[0]     # a fresh batch starts in stage 0
    path = np.empty(len(proba), dtype=int)
    for i, p in enumerate(proba):
        # balanced class weights make the probabilities usable as likelihoods
        belief = (belief @ transitions) * np.clip(p, 1e-4, None)
        belief /= belief.sum()
        path[i] = belief.argmax()
    return path


def filtered(frame, proba, transitions):
    out = np.empty(len(frame), dtype=int)
    for idx in frame.groupby("batch_id", sort=False).indices.values():
        out[idx] = stage_filter(proba[idx], transitions)
    return out
