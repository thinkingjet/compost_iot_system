"""Where the API's compost stage model comes from: ML_DIR, STAGE_MODEL_PATH and
STAGE_MODEL_PARAMS (stage_model.py).

The tests change the settings and reload the model the way startup does; the
`reloads` fixture puts the API's own model back afterwards. Model and
parameter files are written to pytest's tmp_path. They need the real model to
copy from, so they're skipped with a hint when it isn't installed.
"""
import json
import os
import subprocess
import sys

import joblib
import numpy as np
import pytest

import stage_model
from config import settings
from stage_model import StageModelError
# the stage endpoint check reuses test_stage.py's hand-drawn pile and its device cleanup
from test_stage import _pile, _stage, _warm_up, clean_devices  # noqa: F401

RENAMED = ["Warming", "Hot", "Hottest", "Cooling down", "Done"]


@pytest.fixture(scope="module")
def default_model():
    path = stage_model._path(settings.ml_dir) / stage_model.DEFAULT_MODEL
    if not path.is_file():
        pytest.skip(f"no model at {path} - set ML_DIR to the folder with models/compost_stage_gb.joblib")
    return path


@pytest.fixture(scope="module")
def original(default_model):
    """The default bundle as saved, to copy and change."""
    return joblib.load(default_model)


@pytest.fixture
def reloads(monkeypatch):
    """Lets a test change the settings and reload; the API's model is restored afterwards."""
    for name in ("bundle", "load_error"):
        monkeypatch.setattr(stage_model, name, getattr(stage_model, name))
    for name in ("ml_dir", "stage_model_path", "stage_model_params"):
        monkeypatch.setattr(settings, name, getattr(settings, name))
    monkeypatch.setattr(settings, "stage_model_path", None)
    monkeypatch.setattr(settings, "stage_model_params", None)
    return settings


def _model_file(tmp_path, bundle, **changes):
    path = tmp_path / "model.joblib"
    joblib.dump({**bundle, **changes}, path)
    return path


def _params_file(tmp_path, content):
    path = tmp_path / "params.json"
    path.write_text(content if isinstance(content, str) else json.dumps(content))
    return path


# ----------------------------------------------------------------- defaults ---

def test_with_nothing_set_the_model_in_ml_dir_is_loaded(reloads, default_model, original):
    stage_model._load_at_startup()
    assert stage_model.bundle is not None and stage_model.load_error is None
    assert stage_model.bundle["created"] == original["created"]
    assert stage_model.bundle["stage_names"] == original["stage_names"]


def test_with_nothing_set_and_no_model_the_api_starts_without_it(reloads, tmp_path):
    reloads.ml_dir = tmp_path
    stage_model._load_at_startup()
    assert stage_model.bundle is None
    assert "no model at" in stage_model.load_error and "STAGE_MODEL_PATH" in stage_model.load_error


# ---------------------------------------------------------------- overrides ---

def test_stage_model_path_picks_another_model_file(reloads, tmp_path, original):
    reloads.stage_model_path = _model_file(tmp_path, original, created="another model")
    stage_model._load_at_startup()
    assert stage_model.bundle["created"] == "another model"


def test_a_relative_stage_model_path_is_taken_from_backendapi(reloads, tmp_path, original):
    path = _model_file(tmp_path, original, created="relative")
    reloads.stage_model_path = os.path.relpath(path, stage_model.API_DIR)
    stage_model._load_at_startup()
    assert stage_model.bundle["created"] == "relative"


def test_stage_model_params_replace_the_bundles_and_reach_the_endpoint(reloads, tmp_path, original, client, account):
    transitions = np.asarray(original["transitions"])
    quicker = np.eye(5) * 0.5 + np.roll(np.eye(5), 1, axis=1) * 0.5
    quicker[4] = [0, 0, 0, 0, 1]
    reloads.stage_model_params = _params_file(tmp_path, {"stage_names": RENAMED, "transitions": quicker.tolist()})
    stage_model._load_at_startup()
    assert stage_model.bundle["stage_names"] == RENAMED
    assert np.allclose(stage_model.bundle["transitions"], quicker) and not np.allclose(quicker, transitions)
    # what the params file leaves out comes from the bundle
    assert stage_model.bundle["features"] == original["features"]

    bin_id, _ = _pile(client, account["headers"], _warm_up, hours=72)
    body = _stage(client, account["headers"], bin_id)
    assert list(body["probabilities"]) == RENAMED
    assert body["stage"] in {"Hot", "Hottest"}


def test_exported_params_load_back_unchanged(reloads, tmp_path, original):
    path = tmp_path / "exported.json"
    stage_model.export_params(original, path)
    assert set(json.loads(path.read_text())) == {"features", "stage_names", "transitions"}
    reloads.stage_model_params = path
    stage_model._load_at_startup()
    for key in ("features", "stage_names"):
        assert stage_model.bundle[key] == original[key]
    assert np.allclose(stage_model.bundle["transitions"], original["transitions"])


# ---------------------------------------------------------------- bad files ---

def _missing(tmp_path, original):
    return tmp_path / "nope.joblib", None


def _not_a_bundle(tmp_path, original):
    path = tmp_path / "model.joblib"
    path.write_text("not a pickle")
    return path, None


def _wrong_format(tmp_path, original):
    return _model_file(tmp_path, {"format": "something-else/1"}), None


def _old_sklearn(tmp_path, original):
    return _model_file(tmp_path, original, sklearn_version="1.4.2"), None


def _params(content):
    def make(tmp_path, original):
        return None, _params_file(tmp_path, content(original) if callable(content) else content)
    return make


def _missing_params(tmp_path, original):
    return None, tmp_path / "nope.json"


BAD_FILES = [
    pytest.param(_missing, "STAGE_MODEL_PATH=", "no such file", id="no model file"),
    pytest.param(_not_a_bundle, "STAGE_MODEL_PATH=", "can't read it as a model bundle", id="not a pickle"),
    pytest.param(_wrong_format, "STAGE_MODEL_PATH=", "is not a compost stage model bundle", id="wrong format"),
    pytest.param(_old_sklearn, "STAGE_MODEL_PATH=", "saved with scikit-learn 1.4.2", id="other scikit-learn"),
    pytest.param(_missing_params, "STAGE_MODEL_PARAMS=", "no such file", id="no params file"),
    pytest.param(_params("{not json"), "STAGE_MODEL_PARAMS=", "can't read it as JSON", id="not JSON"),
    pytest.param(_params([1, 2]), "STAGE_MODEL_PARAMS=", "should be a JSON object", id="not an object"),
    pytest.param(_params({"stage_name": RENAMED}), "STAGE_MODEL_PARAMS=", "unknown keys ['stage_name']", id="unknown key"),
    pytest.param(_params({"stage_names": RENAMED[:4]}), "STAGE_MODEL_PARAMS=", "4 stage names, but the model has 5 stages",
                 id="too few stage names"),
    pytest.param(_params({"stage_names": ["A", "B", "C", "D", "a"]}), "STAGE_MODEL_PARAMS=", "must all be different",
                 id="duplicate stage names"),
    pytest.param(_params({"transitions": np.eye(4).tolist()}), "STAGE_MODEL_PARAMS=", "should be 5 x 5, not 4 x 4",
                 id="transitions wrong size"),
    pytest.param(_params({"transitions": (np.eye(5) * 0.9).tolist()}), "STAGE_MODEL_PARAMS=", "add up to 1",
                 id="transitions rows not 1"),
    pytest.param(_params({"transitions": "fast"}), "STAGE_MODEL_PARAMS=", "should be a matrix of numbers",
                 id="transitions not numbers"),
    pytest.param(_params(lambda original: {"features": original["features"][::-1]}), "STAGE_MODEL_PARAMS=",
                 "the columns the model was fitted on", id="features reordered"),
]


@pytest.mark.parametrize("make, setting, message", BAD_FILES)
def test_a_bad_file_is_refused_naming_the_setting(tmp_path, default_model, original, make, setting, message):
    model_path, params_path = make(tmp_path, original)
    with pytest.raises(StageModelError) as refused:
        stage_model.load(model_path or default_model, params_path)
    assert str(refused.value).startswith(setting)
    assert message in str(refused.value)


def test_a_model_path_that_was_asked_for_must_exist(reloads, tmp_path):
    # unlike the default, an explicit path that isn't there is a mistake, not "not installed"
    reloads.stage_model_path = tmp_path / "nope.joblib"
    with pytest.raises(StageModelError, match="STAGE_MODEL_PATH=.*no such file"):
        stage_model._load_at_startup()


def test_the_api_refuses_to_start_with_a_bad_path(tmp_path):
    bad = tmp_path / "nope.joblib"
    started = subprocess.run(
        [sys.executable, "-c", "import main"],
        cwd=stage_model.API_DIR, env={**os.environ, "STAGE_MODEL_PATH": str(bad)},
        capture_output=True, text=True, timeout=120,
    )
    assert started.returncode != 0
    assert f"StageModelError: STAGE_MODEL_PATH={bad}: no such file" in started.stderr
