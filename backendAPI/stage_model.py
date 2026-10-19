"""
The compost stage classifier, loaded once when the API starts.

Three settings (config.py, from the environment or .env) say where it comes from:

    ML_DIR              the code: ml/predict.py and ml/features.py
                        (default: the repo's ml/)
    STAGE_MODEL_PATH    the model bundle ml/train.py writes: the fitted classifier
                        (its weights) with its features, stage names and
                        stage-filter transitions
                        (default: ML_DIR/models/compost_stage_gb.joblib)
    STAGE_MODEL_PARAMS  optional JSON that replaces the bundle's "features",
                        "stage_names" and/or "transitions"
                        (default: none, the bundle's own)

Relative paths are taken from backendAPI/, like .env. To start a parameters
file from the current model:  uv run python stage_model.py --export-params FILE

Startup fails, with a message naming the setting, when a model or parameters
file that was asked for is missing, unreadable or doesn't fit: the bundle is
checked, then tried on a test batch. The one exception is the default setup
with no model file in ML_DIR/models: the model just isn't installed, so the
API starts without it, GET /bins/{id}/stage answers 503, and the reason is in
`load_error`.

The records table has no ambient probe or MQ-135, so the model runs on the
core temperature and moisture alone: features.py then assumes 28 °C ambient
(ambient_known = 0), as it does for the bins it was tested on without one.
"""
import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn

from config import settings

log = logging.getLogger(__name__)

API_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL = Path("models") / "compost_stage_gb.joblib"   # under ML_DIR
# what a STAGE_MODEL_PARAMS file can set
PARAM_KEYS = ("features", "stage_names", "transitions")

# the model's rolling features look back 24 h, so it needs a day of readings
MIN_HISTORY_HOURS = 24

predict = None
bundle = None
load_error = None


class StageModelError(Exception):
    """A model or parameters file that was asked for can't be used."""


def _path(value):
    path = Path(value).expanduser()
    return path if path.is_absolute() else API_DIR / path


def _import_predict():
    global predict
    ml_dir = _path(settings.ml_dir)
    # predict.py imports features.py as a top-level module, so ml/ itself goes on the path
    if str(ml_dir) not in sys.path:
        sys.path.append(str(ml_dir))
    try:
        import predict as ml_predict
    except Exception as error:
        raise StageModelError(f"ML_DIR={ml_dir}: can't import predict.py ({type(error).__name__}: {error})") from error
    predict = ml_predict
    return ml_predict


def _read_params(path):
    try:
        params = json.loads(path.read_text())
    except FileNotFoundError:
        raise StageModelError(f"STAGE_MODEL_PARAMS={path}: no such file") from None
    except (OSError, ValueError) as error:
        raise StageModelError(f"STAGE_MODEL_PARAMS={path}: can't read it as JSON ({error})") from error
    if not isinstance(params, dict):
        raise StageModelError(f"STAGE_MODEL_PARAMS={path}: should be a JSON object")
    unknown = sorted(set(params) - set(PARAM_KEYS))
    if unknown:
        raise StageModelError(f"STAGE_MODEL_PARAMS={path}: unknown keys {unknown}; it can set {', '.join(PARAM_KEYS)}")
    return params


def _check(loaded, source):
    """Whether the bundle's parts fit together; source[key] names the file each came from."""
    model = loaded["model"]
    if not hasattr(model, "predict_proba") or not hasattr(model, "classes_"):
        raise StageModelError(f"{source['model']}: 'model' isn't a fitted classifier")
    stages = len(model.classes_)

    features = loaded["features"]
    if not (isinstance(features, list) and features and all(isinstance(f, str) for f in features)):
        raise StageModelError(f"{source['features']}: 'features' should be a list of column names")
    fitted = getattr(model, "feature_names_in_", None)
    if fitted is not None and features != list(fitted):
        raise StageModelError(f"{source['features']}: 'features' must be the columns the model was fitted on, "
                              f"in order: {list(fitted)}")
    if len(features) != model.n_features_in_:
        raise StageModelError(f"{source['features']}: {len(features)} features, but the model takes {model.n_features_in_}")

    names = loaded["stage_names"]
    if not (isinstance(names, list) and all(isinstance(n, str) and n.strip() for n in names)):
        raise StageModelError(f"{source['stage_names']}: 'stage_names' should be a list of names")
    if len(names) != stages:
        raise StageModelError(f"{source['stage_names']}: {len(names)} stage names, but the model has {stages} stages")
    # predict.py names each probability column p_<stage in snake case>, so these must differ too
    if len({n.lower().replace(" ", "_") for n in names}) != len(names):
        raise StageModelError(f"{source['stage_names']}: 'stage_names' must all be different")

    try:
        transitions = np.asarray(loaded["transitions"], dtype=float)
    except (TypeError, ValueError):
        raise StageModelError(f"{source['transitions']}: 'transitions' should be a matrix of numbers") from None
    if transitions.shape != (stages, stages):
        raise StageModelError(f"{source['transitions']}: 'transitions' should be {stages} x {stages}, not "
                              f"{' x '.join(map(str, transitions.shape))}")
    if (transitions < 0).any() or not np.allclose(transitions.sum(axis=1), 1, atol=1e-6):
        raise StageModelError(f"{source['transitions']}: each row of 'transitions' holds the chances of moving "
                              "from that stage, so it must be non-negative and add up to 1")


def _try_out(ml_predict, loaded, where):
    """Runs the model on two days of a pile warming up, so a broken model stops the start, not a request."""
    hours = np.arange(0, 48.5, 0.5)
    batch = pd.DataFrame({"elapsed_h": hours, "temperature_c": 25 + 35 * np.minimum(hours, 30) / 30, "moisture_pct": 55.0})
    try:
        out = ml_predict.predict_readings(loaded, batch)
    except Exception as error:
        raise StageModelError(f"{where}: the model failed on a test batch ({type(error).__name__}: {error})") from error
    if out.empty:
        raise StageModelError(f"{where}: the model gave nothing for a test batch")


def load(model_path, params_path=None):
    """The bundle at model_path, with params_path's overrides, checked and tried out.

    Raises StageModelError, naming the setting at fault, if anything doesn't fit.
    """
    model_source = f"STAGE_MODEL_PATH={model_path}"
    if not model_path.is_file():
        raise StageModelError(f"{model_source}: no such file")
    ml_predict = _import_predict()
    try:
        loaded = ml_predict.load_model(model_path)
    except Exception as error:
        raise StageModelError(f"{model_source}: can't read it as a model bundle ({type(error).__name__}: {error})") from error
    missing = [key for key in ("model", *PARAM_KEYS) if key not in loaded]
    if missing:
        raise StageModelError(f"{model_source}: the bundle has no {', '.join(missing)}")
    # a pickled model is only safe with the scikit-learn minor version that saved it
    saved = str(loaded.get("sklearn_version", "unknown"))
    if saved.split(".")[:2] != sklearn.__version__.split(".")[:2]:
        raise StageModelError(f"{model_source}: saved with scikit-learn {saved}, but {sklearn.__version__} is installed")

    source = dict.fromkeys(("model", *PARAM_KEYS), model_source)
    where = model_source
    if params_path is not None:
        params = _read_params(params_path)
        loaded.update(params)
        source.update(dict.fromkeys(params, f"STAGE_MODEL_PARAMS={params_path}"))
        where += f", STAGE_MODEL_PARAMS={params_path}"
    _check(loaded, source)
    _try_out(ml_predict, loaded, where)
    return loaded


def _load_at_startup():
    global bundle, load_error
    bundle, load_error = None, None
    configured =settings.stage_model_path is not None or settings.stage_model_params is not None
    if settings.stage_model_path is not None:
        model_path = _path(settings.stage_model_path)
    else:
        model_path = _path(settings.ml_dir) / DEFAULT_MODEL
    if not configured and not model_path.is_file():
        load_error = f"no model at {model_path} (set STAGE_MODEL_PATH, or ML_DIR if ml/ is elsewhere)"
        log.warning("Compost stage model not installed: %s. GET /bins/{id}/stage will answer 503", load_error)
        return
    params_path = _path(settings.stage_model_params) if settings.stage_model_params is not None else None
    bundle = load(model_path, params_path)
    log.info("Compost stage model loaded from %s%s", model_path, f" with parameters from {params_path}" if params_path else "")


def estimate(readings):
    """The bin's current stage from its readings, oldest first.

    readings: (timestamp, temperature, moisture_percent) rows from the records table.
    Returns the latest hour of predict.py's output: the filtered stage (what a
    dashboard should show), the hour's own top stage and its probability, and
    every stage's probability.
    """
    frame = pd.DataFrame(readings, columns=["timestamp", "temperature_c", "moisture_pct"])
    latest = predict.predict_readings(bundle, frame).iloc[-1]
    return {
        "stage_id": int(latest["stage_id_filtered"]),
        "stage": latest["stage_filtered"],
        "raw_stage": latest["predicted_stage"],
        "confidence": float(latest["confidence"]),
        # predict.py names each probability column p_<stage in snake case>
        "probabilities": {
            name: float(latest[f"p_{name.lower().replace(' ', '_')}"]) for name in bundle["stage_names"]
        },
    }


def hourly(readings):
    """Every hour of predict.py's output for the same readings as estimate():
    (hour, stage_id, stage, confidence) tuples, oldest first, using the filtered stage."""
    frame = pd.DataFrame(readings, columns=["timestamp", "temperature_c", "moisture_pct"])
    out = predict.predict_readings(bundle, frame)
    return [(pd.Timestamp(row.timestamp).to_pydatetime(), int(row.stage_id_filtered), row.stage_filtered, float(row.confidence))
            for row in out.itertuples()]


def export_params(loaded, path):
    """Writes the bundle's parameters as a STAGE_MODEL_PARAMS file to start from."""
    params = {key: loaded[key] for key in PARAM_KEYS}
    params["transitions"] = np.asarray(params["transitions"], dtype=float).tolist()
    path.write_text(json.dumps(params, indent=2) + "\n")


_load_at_startup()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Show the compost stage model the API loads, with these settings.")
    parser.add_argument("--export-params", type=Path, metavar="FILE",
                        help="write its features, stage names and transitions as a STAGE_MODEL_PARAMS file")
    args = parser.parse_args()
    if bundle is None:
        sys.exit(f"No model loaded: {load_error}")
    print(f"created {bundle.get('created', 'unknown')}, scikit-learn {bundle['sklearn_version']}")
    print(f"stages: {', '.join(bundle['stage_names'])}")
    print(f"{len(bundle['features'])} features: {', '.join(bundle['features'])}")
    if args.export_params:
        export_params(bundle, args.export_params)
        print(f"parameters written to {args.export_params}")
