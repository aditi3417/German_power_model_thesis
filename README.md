# Unplanned Outage Modeling

## Description

This project builds a predictive model for unplanned outages of German thermal power generation units, covering hard coal, lignite, and natural gas plants over the period 2015–2024.

The dataset is sourced from the [Zenodo repository](https://zenodo.org/records/15204429) published by Fusar Bassini (2025), which provides hourly time series of available and unavailable capacity for 384 generation units, constructed from outage reports on the ENTSO-E and EEX Transparency Platforms.

The goal is to predict whether a unit will experience an unplanned outage onset in a given hour, using weather features (temperature, humidity, precipitation), grid load, and operational history. Three model families are compared: logistic regression, LightGBM, and LSTM. Weather data is sourced from Open-Meteo; grid load from SMARD.

This work is inspired by the paper *"Seasonal and Weather Influences in the Outages of German Thermal Generators"* (Fusar Bassini et al., 2025).

---

## Repository Structure

```
├── notebooks/
│   ├── raw_data_outages.ipynb          # Raw outage data inspection
│   ├── eda.ipynb                       # Exploratory data analysis
│   ├── features.ipynb               # Feature engineering pipeline
│   ├── logistic_regression_final.ipynb # LR model training and evaluation
│   ├── lightgbm_final.ipynb            # LightGBM training, SHAP analysis
│   ├── lstm_final.ipynb                # LSTM training and saliency analysis
│   └── prediction_plots.ipynb          # Unit-level probability time series
├── figures/                            # All saved plots
├── scripts/                            # Data fetching scripts (weather, load)
├── data/                               # Input data — not tracked 
└── requirements.txt
```

The `data/` folder is in `.gitignore` as it is more than 100MB in size.

---

## Data Setup

1. Download the dataset from the [Zenodo repository](https://zenodo.org/records/15204429) and place the files in `data/raw/`.
2. Run `scripts/fetch_weather.py` to download ERA5 weather data via Open-Meteo.
3. Run `scripts/fetch_load.py` to download SMARD grid load data.

---

## Reproduction Order

Run the notebooks in the following order to reproduce all results end-to-end:

| Step | Notebook | Description |
|------|----------|-------------|
| 1 | `raw_data_outages.ipynb` | Inspect and validate raw outage data |
| 2 | `eda.ipynb` | Exploratory data analysis |
| 3 | `features.ipynb` | Feature engineering (produces the modelling dataset) |
| 4 | `logistic_regression_final.ipynb` | Logistic regression baseline |
| 5 | `lightgbm_final.ipynb` | LightGBM training and SHAP analysis |
| 6 | `lstm_final.ipynb` | LSTM training and saliency analysis |
| 7 | `prediction_plots.ipynb` | Unit-level probability time series plots |

