# ml — compost stage classifier

`compost_stage_classifier.ipynb` trains models that read a bin's sensor history and say which
of our five composting stages (`simulator/composting_stages.py`) it is in.

- **Data:** labelled batches generated with the emulator's pile model (`emulator/model.py`), plus
  ambient day/night swings, owner behaviour (turning/watering), small-basket bins and sensor noise.
- **Research:** section 1 summarises the compost literature (phase temperatures, EPA/EU
  sanitisation rules, maturity, MQ-135 limits, ML evaluation pitfalls) and checks our stage
  envelopes against it.
- **Models:** literature rules, an ESP32-sized decision tree, gradient boosting and a PyTorch GRU,
  all evaluated with batch-grouped splits, plus a stage filter that keeps predictions moving forward.
- **Stress tests:** hot season, neglected bins, small baskets and noisy sensors.

## Run

```bash
pip install -r ml/requirements.txt
jupyter lab ml/compost_stage_classifier.ipynb
```

Run All takes about 7 minutes on a laptop CPU. Figures, the exported C decision tree
(`compost_stage_tree.h`), the gradient boosting model and the GRU weights are written to
`ml/outputs/` (git-ignored, so they're recreated on each run).

The optional appendix compares against the SmartBox Peltier CSV if `SMARTBOX_CSV` points to it
(it defaults to `~/Downloads/smartbox-ml-kompospeltier-data-fase.csv`).
