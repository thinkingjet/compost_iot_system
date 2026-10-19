# ml — compost stage classifier

Reads a bin's sensor history and says which of our five composting stages it is in
(`simulator/composting_stages.py`):
0 Early Mesophilic, 1 Active Thermophilic, 2 Peak Decomposition (held ≥ 55 °C), 3 Cooling, 4 Maturation.

Everything runs from CSV: the simulator exports labelled data, the training script reads it, and the
exported gradient boosting model predicts from any CSV of readings.

```
ml/
├── dataset.py                     simulator → labelled CSVs
├── features.py                    CSV readings → hourly features (+ the stage filter)
├── train.py                       iterations, final model, test-grid report, export
├── predict.py                     exported model + any readings CSV → predictions CSV
├── compost_stage_classifier.ipynb research notebook (literature, checks, 4 models compared)
├── datasets/                      the CSVs (committed)
│   ├── train.csv.gz               800 batches, every simulator setting varied
│   ├── validation.csv.gz          200 batches, same distribution, for choosing settings
│   ├── test_grid.csv.gz           20 scenarios × 15 batches, one setting changed at a time
│   ├── example_device_readings.csv one bin as a logger would export it (timestamp, core °C, moisture)
│   └── *_batches.csv              the settings each batch was drawn with
├── models/                        the exported model (committed)
│   ├── compost_stage_gb.joblib    gradient boosting + feature list + stage filter
│   ├── model_card.json            settings, data hashes, every score
│   ├── TRAINING_REPORT.md         the iterations and results, readable
│   ├── test_grid_predictions.csv.gz
│   └── figures/
└── outputs/                       notebook figures, ESP32 C tree, large local pools (git-ignored)
```

## Results

The exported model scores **0.946 macro-F1** on 300 unseen test batches covering 20 simulator scenarios,
and no scenario drops below 0.917. `models/TRAINING_REPORT.md` has the per-scenario table and every
iteration.

These numbers are only as good as the simulator's stage rules. The model has not seen a real bin yet.

## Use the model

```bash
pip install -r ml/requirements.txt
python ml/predict.py ml/datasets/example_device_readings.csv -o predictions.csv
```

The input CSV needs `temperature_c`, `moisture_pct`, and either `timestamp` or `elapsed_h`. These
columns help when present:

- `batch_id`: several bins in one file
- `ambient_c`: a second probe outside the bin. Without it, 28 °C is assumed and the model is told so.
- `mq135`: the gas sensor
- `stage_id`: the true stage, so the script can print a score

The output has one row per bin per hour:

- **`stage_filtered`:** what a dashboard should show; the forward-only filter stops it flickering
- **`predicted_stage`:** the raw hourly guess
- **`confidence`:** how sure the raw guess is
- **`p_<stage>`:** the probability of each stage

From Python:

```python
import sys; sys.path.insert(0, "ml")
from predict import load_model, predict_readings
import pandas as pd
predictions = predict_readings(load_model(), pd.read_csv("readings.csv"))
```

The model bundle was saved with scikit-learn 1.9. Load it with the same version: `model_card.json`
records the exact one.

## Rebuild the data and the model

```bash
python ml/dataset.py --preset train          # 800 batches  -> ml/datasets/train.csv.gz
python ml/dataset.py --preset validation     # 200 batches
python ml/dataset.py --preset test-grid      # 15 batches per scenario
python ml/train.py                           # ~7 min (--quick: short run into ml/outputs/quick_model/)
```

- **Deterministic:** the same command always writes the same CSV, because every batch has its own seed.
- **Size:** the committed CSVs are about 41 MB, the 800-batch training set being most of it. The learning
  curve flattens at about 800 batches, so more training data adds little.
- **Learning curve:** `train.py` uses a larger pool when one exists:
  `python ml/dataset.py --preset train --batches 1600 --name train_pool --out-dir ml/outputs/datasets`
  (about 50 MB, so it's kept out of git).
- **What each batch draws:** ambient, bin size (`heat_factor`), owner care, sensor noise, sample
  interval, dropouts, MQ-135 gain/offset/drift, and whether the logger has an MQ-135 and an ambient probe.
  The ranges are at the top of `dataset.py`.

## Notebook

`compost_stage_classifier.ipynb` holds the literature review, checks on the simulator and a
comparison of four models on the same CSVs: literature rules, an ESP32-sized decision tree, the
exported gradient boosting model and a PyTorch GRU. Run All takes about 6 minutes.
