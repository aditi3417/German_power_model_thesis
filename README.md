# Unplanned Outage Prediction — German Thermal Power Plants

Binary classification of unplanned outage onsets for 179 German thermal units (hard coal, lignite, gas), 2015–2024. Hourly resolution, 11.9M rows, 1213:1 class imbalance.

**Data**: [Fusar Bassini (2025), Zenodo](https://zenodo.org/records/15204429) — ENTSO-E/EEX outage reports. Weather from Open-Meteo. Grid load from SMARD.

---

## Results

| Model | Test AUC-ROC |
|-------|-------------|
| LR M1 — weather only (18f) | 0.6624 |
| LR M2 — weather + history (19f) | 0.7603 |
| LGB M1 — weather only (18f) | 0.6226 |
| LGB M2 — weather + history (19f) | 0.7572 |
| LSTM — 48h weather sequences (5f) | 0.6226 |

Temporal split: train 2015–2021 · val 2022 · test 2023–2024. All probabilities Platt-calibrated.

---

## Notebooks

| Notebook | Description |
|----------|-------------|
| `raw_data_outages.ipynb` | Raw outage data inspection |
| `eda.ipynb` | Exploratory analysis — class balance, seasonality, feature–outcome relationships |
| `features_v2.ipynb` | Feature engineering pipeline → `data/features_v2.parquet` |
| `logistic_regression_final.ipynb` | LR M1/M2 training, evaluation, coefficient analysis |
| `lightgbm_final.ipynb` | LGB M1/M2 training, SHAP analysis, 4-model comparison |
| `lstm_final.ipynb` | LSTM training, temporal saliency analysis |
| `prediction_plots.ipynb` | Unit-level 5-day forward probability time series (3 fuel types × 3 models) |

---

## Reproduce

```bash
pip install -r requirements.txt

# 1. Build feature matrix
jupyter nbconvert --to notebook --execute notebooks/features_v2.ipynb

# 2. Train models (run in order)
jupyter nbconvert --to notebook --execute notebooks/logistic_regression_final.ipynb
jupyter nbconvert --to notebook --execute notebooks/lightgbm_final.ipynb
jupyter nbconvert --to notebook --execute notebooks/lstm_final.ipynb

# 3. Generate prediction plots
jupyter nbconvert --to notebook --execute notebooks/prediction_plots.ipynb
```

Raw data files go in `data/` (gitignored). Models are regenerated on each run.
