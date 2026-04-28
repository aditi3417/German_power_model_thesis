# Unplanned Outage Modeling

## Description

This project builds a predictive model for unplanned outages of German thermal power generation units, covering hard coal, lignite, and natural gas plants over the period 2015–2024.

The dataset is sourced from the [Zenodo repository](https://zenodo.org/records/15204429) published by Fusar Bassini (2025), which provides hourly time series of available and unavailable capacity for 384 generation units, constructed from outage reports on the ENTSO-E and EEX Transparency Platforms.

The goal is to predict whether a unit will experience an unplanned outage onset in a given hour, using weather features (temperature, humidity, precipitation), grid load, and operational history. Three model families are compared: logistic regression, LightGBM, and LSTM. Weather data is sourced from Open-Meteo; grid load from SMARD.

This work is inspired by the paper *"Seasonal and Weather Influences in the Outages of German Thermal Generators"* (Fusar Bassini et al., 2025).

---

## Data Setup

1. Download the dataset from the [Zenodo repository](https://zenodo.org/records/15204429) and place the files in `data/raw/`.
2. Fetch weather data: `python scripts/fetch_weather_all.py`
3. Fetch grid load data: `python scripts/fetch_load.py`

The `data/` directory is excluded from version control as it is more than 100 MB in size. Trained models are saved in `models/` and are also excluded.

---

## Repository Structure

```
├── notebooks/
│   ├── raw_data_outages.ipynb          # Raw outage data inspection
│   ├── eda.ipynb                       # Exploratory data analysis
│   ├── features.ipynb                  # Feature engineering pipeline
│   ├── logistic_regression_final.ipynb # LR model training and evaluation
│   ├── lightgbm_final.ipynb            # LightGBM training, SHAP analysis
│   ├── lstm_final.ipynb                # LSTM training and saliency analysis
│   ├── prediction_plots.ipynb          # Unit-level probability time series
│   └── bootstrap_ci.ipynb              # Bootstrap confidence intervals for AUC
├── figures/                            # All saved plots
├── scripts/                            # Data fetching scripts (weather, load)
├── data/                               # Input data — not tracked (>100 MB)
└── requirements.txt
```

## Reproduction Order

Run the notebooks in this order to reproduce all results:

1. `raw_data_outages.ipynb` — inspect and validate raw outage data
2. `eda.ipynb` — exploratory data analysis
3. `features.ipynb` — build the feature matrix (outputs saved to `data/`)
4. `logistic_regression_final.ipynb` — train and evaluate logistic regression baseline
5. `lightgbm_final.ipynb` — train LightGBM, compute SHAP values
6. `lstm_final.ipynb` — train LSTM, compute saliency maps
7. `prediction_plots.ipynb` — generate unit-level probability plots
8. `bootstrap_ci.ipynb` — compute bootstrap confidence intervals for reported AUC scores
