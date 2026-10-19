"""
Predict compost stages for a CSV of sensor readings with the exported model.

    python ml/predict.py readings.csv -o predictions.csv
    python ml/predict.py ml/datasets/test_grid.csv.gz -o ml/models/test_grid_predictions.csv.gz

The input is any CSV that features.py accepts: at least temperature_c,
moisture_pct and a timestamp or elapsed_h, ideally with batch_id and
ambient_c (see features.py). One row comes out per bin per hour with:

    predicted_stage_id / predicted_stage   the hour on its own (raw)
    stage_id_filtered / stage_filtered     after the forward-only stage filter
                                           (what a dashboard should show)
    confidence                             the raw prediction's probability
    p_<stage>                              every stage's probability
    stage_id                               the true stage, if the input had it
"""
import argparse
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

import features as F

DEFAULT_MODEL = Path(__file__).resolve().parent / "models" / "compost_stage_gb.joblib"


def load_model(path=DEFAULT_MODEL):
    bundle = joblib.load(path)
    if bundle.get("format") != "compost-stage-gb/1":
        raise ValueError(f"{path} is not a compost stage model bundle")
    return bundle


def predict_features(bundle, feats):
    """Predictions for a frame from features.make_features."""
    proba = bundle["model"].predict_proba(feats[bundle["features"]])
    raw = proba.argmax(axis=1)
    smooth = F.filtered(feats, proba, np.asarray(bundle["transitions"]))
    names = np.array(bundle["stage_names"])
    out = pd.DataFrame({"batch_id": feats["batch_id"].values, "elapsed_h": feats["elapsed_h"].values})
    if "stage_id" in feats:
        out["stage_id"] = feats["stage_id"].values
    out["predicted_stage_id"] = raw
    out["predicted_stage"] = names[raw]
    out["stage_id_filtered"] = smooth
    out["stage_filtered"] = names[smooth]
    out["confidence"] = proba.max(axis=1).round(4)
    for i, name in enumerate(bundle["stage_names"]):
        out[f"p_{name.lower().replace(' ', '_')}"] = proba[:, i].round(4)
    return out


def predict_readings(bundle, readings):
    readings = F.prepare(readings)
    out = predict_features(bundle, F.make_features(readings))
    if "timestamp" in readings:
        # put the clock time back: each bin's first reading plus the hours since then
        start = pd.to_datetime(readings["timestamp"], utc=True).groupby(readings["batch_id"]).min()
        stamps = out["batch_id"].map(start) + pd.to_timedelta(out["elapsed_h"], unit="h")
        out.insert(1, "timestamp", stamps.dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
    return out


def main():
    parser = argparse.ArgumentParser(description="Predict compost stages from a readings CSV.")
    parser.add_argument("readings", type=Path, help="CSV (or .csv.gz) of sensor readings")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="where to write predictions (default: <input>_predictions.csv)")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    args = parser.parse_args()

    bundle = load_model(args.model)
    readings = pd.read_csv(args.readings, keep_default_na=False, na_values=[""], low_memory=False,
                           dtype={"batch_id": str, "faults": str})
    predictions = predict_readings(bundle, readings)
    stem = args.readings.name.split(".")[0]
    out = args.output or args.readings.with_name(f"{stem}_predictions.csv")
    predictions.to_csv(out, index=False)
    print(f"{len(predictions):,} hourly predictions for {predictions.batch_id.nunique()} bin(s) -> {out}")
    if "stage_id" in predictions:
        from sklearn.metrics import f1_score
        print(f"macro-F1 vs. the true stage: raw {f1_score(predictions.stage_id, predictions.predicted_stage_id, average='macro'):.3f}, "
              f"filtered {f1_score(predictions.stage_id, predictions.stage_id_filtered, average='macro'):.3f}")


if __name__ == "__main__":
    main()
