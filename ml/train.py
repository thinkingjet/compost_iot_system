"""
Train the compost stage classifier from simulator CSVs and export it.

    python ml/train.py            # experiments, final model, test-grid report, export to ml/models/
    python ml/train.py --quick    # fewer, smaller experiments; exports to ml/outputs/quick_model/

Steps, all scored with macro-F1 on held-out *batches* (never rows of a batch
the model trained on):

  1. feature sets      which sensors and features earn their place
  2. hyperparameters   a small grid of gradient-boosting settings
  3. learning curve    how much training data is enough (uses the larger
                       --pool CSV when it exists, see ml/README.md)
  4. stage filter      how readily stage 1 may skip straight to Cooling
  5. final model       trained on train + validation, scored on every
                       scenario of the test grid, then exported:

     ml/models/compost_stage_gb.joblib         model + features + stage filter
     ml/models/model_card.json                 settings, data, every score
     ml/models/test_grid_predictions.csv.gz    per-hour predictions on the test grid
     ml/models/TRAINING_REPORT.md              the iterations and results, readable
     ml/models/figures/*.png
"""
import argparse
import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import sklearn  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier  # noqa: E402
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score  # noqa: E402

import features as F  # noqa: E402
from predict import predict_features  # noqa: E402

ML = Path(__file__).resolve().parent
DATASETS = ML / "datasets"
MODELS = ML / "models"
SEED = 42

# Every fit stops early on the validation batches' (class-balanced) log loss: with a fixed
# 300 trees the model kept going after its best point, its probabilities saturated, and on
# 1,600 batches it collapsed from 0.93 to 0.80 macro-F1. max_iter is only a ceiling.
# "every_h" thins the hourly rows (neighbouring hours are near-duplicates).
QUICK = dict(learning_rate=0.2, max_iter=300, max_leaf_nodes=31, min_samples_leaf=20, l2_regularization=0.0, every_h=2)
BASE = dict(learning_rate=0.1, max_iter=1000, max_leaf_nodes=31, min_samples_leaf=20, l2_regularization=0.0, every_h=1)
CONFIGS = {
    "lr 0.1, 31 leaves": BASE,
    "lr 0.05, 31 leaves": {**BASE, "learning_rate": 0.05},
    "lr 0.1, 63 leaves": {**BASE, "max_leaf_nodes": 63},
    "lr 0.1, 15 leaves": {**BASE, "max_leaf_nodes": 15},
    "lr 0.1, 31 leaves, 200 rows per leaf, l2 1.0": {**BASE, "min_samples_leaf": 200, "l2_regularization": 1.0},
    "lr 0.1, 31 leaves, every 2nd hour": {**BASE, "every_h": 2},
    "lr 0.1, 31 leaves, every 3rd hour": {**BASE, "every_h": 3},
}
SKIP_SHARES = [0.2, 0.4, 0.6, 0.8, 0.9]
FILTER_SPEEDS = [1.0, 2.0, 4.0, 8.0]
STOP_AFTER = 15     # boosting rounds without a better validation loss

# chart colours: categorical slots 1-3 of the validated palette (see the notebook)
BLUE, ORANGE, AQUA, INK_2, MUTED, GRID, SURFACE = "#2a78d6", "#eb6834", "#1baf7a", "#52514e", "#8a8984", "#e4e3df", "#fcfcfb"
plt.rcParams.update({"figure.dpi": 110, "savefig.dpi": 150, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
                     "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": MUTED,
                     "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
                     "axes.titleweight": "bold", "axes.titlesize": 11, "font.size": 9.5, "legend.frameon": False})


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def balanced_weights(y):
    counts = np.bincount(y, minlength=len(F.STAGE_NAMES))
    return (len(y) / (len(F.STAGE_NAMES) * np.maximum(counts, 1)))[y]


def thin(frame, cfg):
    every = cfg.get("every_h", 1)
    return frame if every == 1 else frame[frame.elapsed_h % every == 0]


def fit(cfg, cols, frame, val=None):
    """Fit gradient boosting; with `val`, stop early on its class-balanced log loss."""
    params = {k: v for k, v in cfg.items() if k != "every_h"}
    data = thin(frame, cfg)
    if val is None:
        model = HistGradientBoostingClassifier(**params, early_stopping=False, class_weight="balanced",
                                               random_state=SEED)
        return model.fit(data[cols], data.stage_id)
    model = HistGradientBoostingClassifier(**params, early_stopping=True, scoring="loss",
                                           n_iter_no_change=STOP_AFTER, class_weight="balanced",
                                           random_state=SEED)
    return model.fit(data[cols], data.stage_id, X_val=val[cols], y_val=val.stage_id,
                     sample_weight_val=balanced_weights(val.stage_id.to_numpy()))


def score(y, pred):
    return {"macro_f1": round(f1_score(y, pred, average="macro"), 4),
            "balanced_accuracy": round(balanced_accuracy_score(y, pred), 4),
            "accuracy": round(accuracy_score(y, pred), 4)}


def evaluate(model, cols, frame, transitions):
    proba = model.predict_proba(frame[cols])
    return (f1_score(frame.stage_id, proba.argmax(1), average="macro"),
            f1_score(frame.stage_id, F.filtered(frame, proba, transitions), average="macro"))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    t0 = time.time()
    feats = F.make_features(F.read_readings(path))
    log(f"{path.name}: {feats.batch_id.nunique()} batches -> {len(feats):,} hourly rows ({time.time() - t0:.0f}s)")
    return feats


def md_table(df, floatfmt="{:.3f}"):
    cols = [df.index.name or ""] + list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    is_float = [pd.api.types.is_float_dtype(t) for t in df.dtypes]
    for idx, row in zip(df.index, df.itertuples(index=False)):
        cells = [floatfmt.format(v) if f else (f"{v:,}" if isinstance(v, (int, np.integer)) else str(v))
                 for v, f in zip(row, is_float)]
        lines.append("| " + " | ".join([str(idx)] + cells) + " |")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Train and export the compost stage classifier.")
    parser.add_argument("--train", type=Path, default=DATASETS / "train.csv.gz")
    parser.add_argument("--validation", type=Path, default=DATASETS / "validation.csv.gz")
    parser.add_argument("--test", type=Path, default=DATASETS / "test_grid.csv.gz")
    parser.add_argument("--pool", type=Path, default=ML / "outputs" / "datasets" / "train_pool.csv.gz",
                        help="larger training CSV for the learning curve (skipped if missing)")
    parser.add_argument("--quick", action="store_true",
                        help="smaller experiments; exports to ml/outputs/quick_model/ so ml/models/ is untouched")
    args = parser.parse_args()
    global MODELS
    if args.quick:
        MODELS = ML / "outputs" / "quick_model"
    started = time.time()

    train, val, test = load(args.train), load(args.validation), load(args.test)
    scenario_of = pd.read_csv(args.test.with_name(args.test.name.replace(".csv.gz", "_batches.csv")))
    scenario_of = scenario_of.set_index("batch_id").scenario
    default_T = F.transition_matrix()
    report = {}

    # 1. feature sets -------------------------------------------------------------------------
    rows = []
    for name, cols in F.FEATURE_SETS.items():
        t0 = time.time()
        m = fit(QUICK, cols, train, val)
        raw, smooth = evaluate(m, cols, val, default_T)
        rows.append({"feature set": name, "features": len(cols), "trees": m.n_iter_, "raw": raw, "filtered": smooth})
        log(f"feature set {name!r}: raw {raw:.3f}, filtered {smooth:.3f}, {m.n_iter_} trees ({time.time() - t0:.0f}s)")
    fs = pd.DataFrame(rows).set_index("feature set")
    report["feature_sets"] = fs
    usable = fs.drop(index=[n for n in fs.index if "simulated" in n])
    best_set = usable.filtered.idxmax()
    cols = F.FEATURE_SETS[best_set]
    log(f"best usable feature set: {best_set}")

    # 2. hyperparameters ----------------------------------------------------------------------
    rows = []
    configs = {k: CONFIGS[k] for k in list(CONFIGS)[:3]} if args.quick else CONFIGS
    for name, cfg in configs.items():
        t0 = time.time()
        m = fit(cfg, cols, train, val)
        raw, smooth = evaluate(m, cols, val, default_T)
        rows.append({"settings": name, "trees": m.n_iter_, "raw": raw, "filtered": smooth,
                     "fit seconds": round(time.time() - t0)})
        log(f"settings {name!r}: raw {raw:.3f}, filtered {smooth:.3f}, {m.n_iter_} trees ({time.time() - t0:.0f}s)")
    hp = pd.DataFrame(rows).set_index("settings")
    report["hyperparameters"] = hp
    best_cfg_name = hp.filtered.idxmax()
    best_cfg = CONFIGS[best_cfg_name]
    log(f"best settings: {best_cfg_name}")

    # 3. learning curve -----------------------------------------------------------------------
    pool = load(args.pool) if args.pool.exists() else train
    batches = pool.batch_id.drop_duplicates().tolist()
    sizes = [n for n in ([25, 100, 400] if args.quick else [25, 50, 100, 200, 400, 800, 1600]) if n <= len(batches)]
    if len(batches) not in sizes:
        sizes.append(len(batches))
    rows = []
    for n in sizes:
        t0 = time.time()
        part = pool[pool.batch_id.isin(set(batches[:n]))]
        m = fit(best_cfg, cols, part, val)
        raw, smooth = evaluate(m, cols, val, default_T)
        rows.append({"training batches": n, "hourly rows": len(part), "trees": m.n_iter_, "raw": raw, "filtered": smooth})
        log(f"learning curve {n} batches: raw {raw:.3f}, filtered {smooth:.3f}, {m.n_iter_} trees ({time.time() - t0:.0f}s)")
    lc = pd.DataFrame(rows).set_index("training batches")
    report["learning_curve"] = lc
    del pool

    # 4. stage filter, on the early-stopped model trained on train only --------------------------
    m = fit(best_cfg, cols, train, val)
    trees = int(m.n_iter_)
    proba_val = m.predict_proba(val[cols])
    raw_val = f1_score(val.stage_id, proba_val.argmax(1), average="macro")
    rows = []
    for speed in FILTER_SPEEDS:
        for share in SKIP_SHARES:
            T = F.transition_matrix(skip_peak_share=share, speed=speed)
            rows.append({"filter": f"speed {speed:g}, skip {share:g}", "speed": speed, "skip share": share,
                         "filtered": f1_score(val.stage_id, F.filtered(val, proba_val, T), average="macro")})
    fl = pd.DataFrame(rows).set_index("filter")
    report["filter"] = fl
    best_filter = fl.filtered.idxmax()
    best_skip, best_speed = float(fl.loc[best_filter, "skip share"]), float(fl.loc[best_filter, "speed"])
    transitions = F.transition_matrix(skip_peak_share=best_skip, speed=best_speed)
    log(f"best filter: {best_filter} ({fl.filtered.max():.3f} vs raw {raw_val:.3f}); early stopping chose {trees} trees")

    # 5. final model on train + validation with that many trees, scored on the test grid ---------
    final_data = pd.concat([train, val], ignore_index=True)
    final_cfg = {**best_cfg, "max_iter": trees}
    t0 = time.time()
    final = fit(final_cfg, cols, final_data)
    log(f"final model fit on {final_data.batch_id.nunique()} batches / {len(thin(final_data, final_cfg)):,} rows, "
        f"{trees} trees ({time.time() - t0:.0f}s)")
    bundle = {"format": "compost-stage-gb/1", "model": final, "features": cols, "stage_names": F.STAGE_NAMES,
              "transitions": transitions.tolist(), "feature_step_h": F.STEP_H, "settings": final_cfg,
              "feature_set": best_set, "sklearn_version": sklearn.__version__,
              "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    preds = predict_features(bundle, test)
    preds.insert(1, "scenario", preds.batch_id.map(scenario_of))

    per = []
    for scenario, g in preds.groupby("scenario", sort=False):
        per.append({"scenario": scenario, "batches": g.batch_id.nunique(),
                    "raw": f1_score(g.stage_id, g.predicted_stage_id, average="macro"),
                    "filtered": f1_score(g.stage_id, g.stage_id_filtered, average="macro"),
                    "filtered accuracy": accuracy_score(g.stage_id, g.stage_id_filtered)})
    grid = pd.DataFrame(per).set_index("scenario")
    report["test_grid"] = grid
    overall = {"raw": score(preds.stage_id, preds.predicted_stage_id),
               "filtered": score(preds.stage_id, preds.stage_id_filtered)}
    cm = confusion_matrix(preds.stage_id, preds.stage_id_filtered, labels=range(5), normalize="true")
    log(f"test grid overall: raw {overall['raw']['macro_f1']:.3f}, filtered {overall['filtered']['macro_f1']:.3f}")

    # export -----------------------------------------------------------------------------------
    MODELS.mkdir(parents=True, exist_ok=True)
    (MODELS / "figures").mkdir(exist_ok=True)
    joblib.dump(bundle, MODELS / "compost_stage_gb.joblib", compress=3)
    preds.to_csv(MODELS / "test_grid_predictions.csv.gz", index=False,
                 compression={"method": "gzip", "compresslevel": 9})
    figures(report, cm)

    data = {name: {"path": str(path.relative_to(ML.parent)), "sha256": sha256(path),
                   "batches": int(frame.batch_id.nunique()), "hourly_rows": int(len(frame))}
            for name, path, frame in [("train", args.train, train), ("validation", args.validation, val),
                                      ("test_grid", args.test, test)]}
    card = {
        "model": "HistGradientBoostingClassifier (scikit-learn), class_weight=balanced",
        "created": bundle["created"], "sklearn_version": sklearn.__version__, "python": platform.python_version(),
        "feature_set": best_set, "features": cols, "settings": final_cfg, "settings_name": best_cfg_name,
        "stage_filter_skip_share": best_skip, "stage_filter_speed": best_speed,
        "stages": dict(enumerate(F.STAGE_NAMES)), "trained_on": ["train", "validation"], "data": data,
        "test_grid_overall": overall, "test_grid_by_scenario": grid.round(4).reset_index().to_dict("records"),
        "experiments": {k: v.round(4).reset_index().to_dict("records") for k, v in report.items() if k != "test_grid"},
        "runtime_seconds": round(time.time() - started),
    }
    (MODELS / "model_card.json").write_text(json.dumps(card, indent=2, default=str))
    write_report(report, card, cm, args)
    log(f"exported to {MODELS} in {time.time() - started:.0f}s total")


def figures(report, cm):
    lc = report["learning_curve"]
    fig, ax = plt.subplots(figsize=(7, 3))
    ax.plot(lc.index, lc.filtered, marker="o", color=BLUE, label="with stage filter")
    ax.plot(lc.index, lc.raw, marker="o", color=ORANGE, label="raw")
    ax.set_xscale("log")
    ax.set_xticks(lc.index, [str(i) for i in lc.index])
    ax.set_xlabel("Training batches (log scale)")
    ax.set_ylabel("Validation macro-F1")
    ax.set_title("How much training data is enough?", loc="left")
    ax.legend(loc="lower right")
    fig.savefig(MODELS / "figures" / "learning_curve.png", bbox_inches="tight")
    plt.close(fig)

    grid = report["test_grid"].sort_values("filtered")
    fig, ax = plt.subplots(figsize=(8, 5.2))
    y = np.arange(len(grid))
    ax.hlines(y, grid.raw, grid.filtered, color=GRID, lw=2)
    ax.plot(grid.raw, y, "o", color=ORANGE, ms=6, label="raw")
    ax.plot(grid.filtered, y, "o", color=BLUE, ms=7, label="with stage filter")
    for yi, v in zip(y, grid.filtered):
        ax.text(v + 0.006, yi, f"{v:.3f}", va="center", fontsize=8, color=INK_2)
    ax.set_yticks(y, [s.replace("_", " ") for s in grid.index])
    ax.set_xlabel(f"Macro-F1 on {int(grid.batches.median())} unseen batches per scenario")
    ax.set_title("Final model across the simulator's parameter grid", loc="left")
    ax.legend(loc="lower right")
    ax.grid(axis="y", visible=False)
    fig.savefig(MODELS / "figures" / "test_grid_by_scenario.png", bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(5.6, 4.6))
    ax.imshow(cm, cmap="Blues", vmin=0, vmax=1)
    for i in range(5):
        for j in range(5):
            ax.text(j, i, f"{cm[i, j]:.2f}", ha="center", va="center", fontsize=8.5,
                    color="white" if cm[i, j] > 0.6 else INK_2)
    ticks = [f"{i} {n}" for i, n in enumerate(F.STAGE_NAMES)]
    ax.set_xticks(range(5), [str(i) for i in range(5)])
    ax.set_yticks(range(5), ticks)
    ax.set_xlabel("Predicted stage (filtered)")
    ax.set_title("Test grid, all scenarios (row-normalised)", loc="left")
    ax.grid(False)
    fig.savefig(MODELS / "figures" / "confusion_matrix.png", bbox_inches="tight")
    plt.close(fig)


def write_report(report, card, cm, args):
    o = card["test_grid_overall"]
    lines = [
        "# Compost stage classifier — training report",
        "",
        f"Generated by `ml/train.py` on {card['created']} (scikit-learn {card['sklearn_version']}, "
        f"{card['runtime_seconds'] // 60} min). Re-run it to reproduce; every number comes from `model_card.json`.",
        "",
        "## Final model",
        "",
        f"- **Gradient boosting** (`HistGradientBoostingClassifier`, balanced class weights): "
        f"{card['settings_name']}, {card['settings']['max_iter']} trees (chosen by early stopping on the "
        f"validation batches, then refit on train + validation). Settings `{json.dumps(card['settings'])}`",
        f"- **Features:** {card['feature_set']} ({len(card['features'])} features, see `ml/features.py`)",
        f"- **Stage filter:** forward-only HMM, speed {card['stage_filter_speed']:g}, stage 1 → Cooling skip share "
        f"{card['stage_filter_skip_share']:g}",
        f"- **Trained on:** train + validation, {card['data']['train']['batches'] + card['data']['validation']['batches']} "
        f"simulated batches ({card['data']['train']['hourly_rows'] + card['data']['validation']['hourly_rows']:,} hourly rows)",
        f"- **Test grid (all {card['data']['test_grid']['batches']} batches):** macro-F1 **{o['filtered']['macro_f1']:.3f}** "
        f"with the filter ({o['raw']['macro_f1']:.3f} raw), balanced accuracy {o['filtered']['balanced_accuracy']:.3f}, "
        f"accuracy {o['filtered']['accuracy']:.3f}",
        "",
        "## Test grid: one simulator setting changed at a time",
        "",
        f"Each scenario is {int(report['test_grid'].batches.median())} batches the model never saw, with one setting moved away from the baseline "
        "(ambient 26–30 °C, full-size bin, irregular care, normal noise, 30-minute readings, 2 % dropouts, "
        "a calibrated MQ-135 and an ambient probe). "
        "`worst_case` changes five at once.",
        "",
        md_table(report["test_grid"]),
        "",
        "![test grid](figures/test_grid_by_scenario.png)",
        "",
        "![confusion matrix](figures/confusion_matrix.png)",
        "",
        f"## Iterations (validation set: {card['data']['validation']['batches']} batches from the training distribution)",
        "",
        "Every fit below stops early once the validation batches' log loss stops improving (15 rounds). An "
        "earlier version used a fixed 300 trees: the model kept going past its best point, its probabilities "
        "saturated, and with 1,600 training batches it collapsed from 0.93 to 0.80 macro-F1.",
        "",
        "### 1. Feature sets (quick model, every 2nd hour)",
        "",
        md_table(report["feature_sets"]),
        "",
        "### 2. Gradient boosting settings",
        "",
        md_table(report["hyperparameters"], "{:.3f}"),
        "",
        "### 3. Learning curve",
        "",
        md_table(report["learning_curve"]),
        "",
        "![learning curve](figures/learning_curve.png)",
        "",
        "### 4. Stage filter: how fast stages may advance, and how often stage 1 skips straight to Cooling",
        "",
        md_table(report["filter"]),
        "",
        "## Files",
        "",
        "- `compost_stage_gb.joblib`: the model bundle (`predict.py` loads it)",
        "- `model_card.json`: settings, data hashes and every score above",
        "- `test_grid_predictions.csv.gz`: per-hour predictions on the test grid",
    ]
    (MODELS / "TRAINING_REPORT.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
