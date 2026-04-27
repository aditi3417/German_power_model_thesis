# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Master's thesis at Hertie School: **predicting unplanned power plant outages in Germany (2015–2024)** for thermal plants (hard coal, lignite, gas). Framed as a **binary classification** problem where the target is `is_onset = 1` for the first hour of an unplanned outage, `0` otherwise.

## Environment

This directory is a Python 3.14 virtual environment. Activate it before running anything:

```bash
source /Users/aditi/Documents/Hertie/Thesis/thesis-env/bin/activate
```

Run notebooks with:
```bash
jupyter notebook notebooks/
```

Run a script:
```bash
python scripts/fetch_coordinates.py
python scripts/fetch_weather_all.py
```

## Data Pipeline (in order)

1. **Raw ENTSO-E CSVs** → `raw_data_outages.ipynb` → `data/outages_2015-2024_clean.parquet`, then `data/outages_with_type.parquet`
2. **Unit coordinates** → `scripts/fetch_coordinates.py` → `data/unit_coordinates.csv`
   - Uses OPSD (exact EICCode match), then GPPD (fuzzy name match), then manual review via `data/unit_coordinates_review.csv`
3. **Weather data** → `scripts/fetch_weather_all.py` → `data/weather_lookup.parquet` + `data/all_thermal_with_weather.parquet`
   - Fetches hourly weather from Open-Meteo archive API for 83 unique plant locations × 10 years
   - Supports checkpoint/resume via `data/weather_checkpoint_all.parquet`
4. **Feature engineering** → `notebooks/features.ipynb` → `data/features.parquet`
5. **Modelling** → `notebooks/fit.model.ipynb` (empty — next step)

## Key Data Facts

- **Source dataset**: `data/all_thermal_with_weather.parquet` — 12.5M rows, 83 unique locations, 3 fuels
- **Working dataset** (after dropping continuation hours): ~11.9M rows
- **Class imbalance**: 9,832 onsets vs 11.9M non-onsets → **1,213:1 ratio**
- **Fuels**: `Fossil Hard coal`, `Fossil Brown coal/Lignite`, `Fossil Gas` (lignite is the one-hot base)
- **Unit identifier**: `EICCode`
- **Known missing data**: `utilisation_rate` has ~2.7M NaN (units at zero generation); `unavailable_ratio` / `available_ratio` have 185 NaN

## Feature Matrix (`data/features.parquet`)

29 features across 6 categories:

| Category | Features |
|---|---|
| Temporal | month, hour, day_of_week, year, is_weekend, season |
| Weather raw | temperature_2m, relative_humidity_2m, precipitation, snowfall, wind_speed_10m, wind_gusts_10m, surface_pressure, shortwave_radiation, cloud_cover |
| Weather engineered | is_hot (≥25°C), is_very_hot (≥30°C), rolling_temp_max_24h, rolling_temp_max_48h, temp_dev_from_monthly |
| Capacity (t-1 lagged) | InstalledCapacity, utilisation_rate, unavailable_ratio, available_ratio, capacity_size |
| Unit history | days_since_last_onset (999 if never), n_onsets_last_90d |
| Fuel dummies | fuel_Fossil Gas, fuel_Fossil Hard coal |

All capacity/lag features use **t-1 values** to avoid leakage. Unit history features use only past data.

## Related Work — Direct Predecessor

**"Seasonal and Weather Influences in the Outages of German Thermal Generators"**, ACM SIGENERGY Energy Informatics Review, Vol. 5 Issue 3, September 2025.

This thesis is an **extension** of that paper. Key details to keep in mind:

- **What they did**: weekly binary availability prediction (unavailable if >24h outage in the week) using decision trees on 3 features — total load, average temperature, total precipitation — for the same German thermal units (hard coal, lignite, gas), 2015–2024. Used 5-fold blocked validation (train on 5-year window, evaluate on next year). Applied SMOTE for class imbalance.
- **Key findings**: load is the most important feature (38.4% Gini importance), temperature second (36.4%), precipitation third (25.2%). Strong heterogeneity across gas units (CHP plants driven by temperature; peaker plants driven by load). Clear upward trend in outage frequency (+10.2 hrs/year). Summer unavailability ~2× winter.
- **Their limitations / where this thesis goes further**:
  - They used **weekly aggregation** and only 3 features — this thesis uses **hourly onset detection** with 29 features
  - They predicted general unavailability (planned + unplanned) — this thesis targets **unplanned onsets only**
  - They used decision trees — this thesis aims for **probabilistic models with calibrated outputs**
  - They used 3 weather stations — this thesis uses **unit-specific coordinates** with matched weather
  - Their model struggled on the minority (unavailable) class — this thesis addresses this directly via onset framing and proper imbalance handling

## Modelling Considerations

- **Goal: probabilistic models** — output should be calibrated probabilities of onset, not just binary predictions
- **Always use time-based train/val/test splits** — never random splits (temporal data)
- Use **precision-recall AUC / average precision** as primary metric — ROC-AUC is misleading at 1213:1 imbalance
- Evaluate calibration explicitly (reliability diagrams, Brier score) — well-calibrated probabilities matter as much as discrimination
- LightGBM/XGBoost handle this tabular setup well; use `scale_pos_weight` or equivalent for imbalance; apply Platt scaling or isotonic regression post-hoc if needed
- Threshold calibration matters: define target recall vs. acceptable false alarm rate explicitly

## Directory Structure

```
notebooks/          # Analysis and modelling notebooks (run in order above)
scripts/            # Data collection scripts (coordinates, weather)
data/               # All parquet/CSV data files (not versioned)
figures/            # Exported plots from EDA and feature analysis
delete_later/       # Superseded scripts (fetch_weather.py, fetch_weather_planned.py)
```
