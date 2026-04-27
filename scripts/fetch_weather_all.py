""" fetch_weather_all.py

Fetches hourly weather data from Open-Meteo for ALL thermal plant locations
(hard coal, lignite, gas) across 2015-2024.

Strategy:
  1. Load all thermal outage rows (planned + unplanned + normal operation)
     that have coordinates — 12.5M rows, 83 unique locations
  2. Build 842 unique location × year combos
  3. Fetch full-year weather for each combo (8,760 rows each)
  4. Save a reusable weather lookup table: weather_lookup.parquet
  5. Join weather to all 12.5M rows and save complete dataset

Outputs:
  weather_lookup.parquet         — full hourly weather for all 83 locations, 2015-2024
  all_thermal_with_weather.parquet — all thermal rows + weather variables joined
"""

import os
import random
import time
from pathlib import Path
import requests
import pandas as pd

_DATA = Path(__file__).resolve().parent.parent / "data"   # thesis-env/data/

OUTAGES_PARQUET = _DATA / "outages_with_type.parquet"
COORDS_CSV      = _DATA / "unit_coordinates.csv"
LOOKUP_PARQUET  = _DATA / "weather_lookup.parquet"
OUT_PARQUET     = _DATA / "all_thermal_with_weather.parquet"
CHECKPOINT      = _DATA / "weather_checkpoint_all.parquet"

THERMAL_FUELS = ["Fossil Hard coal", "Fossil Brown coal/Lignite", "Fossil Gas"]

HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "precipitation",
    "snowfall",
    "wind_speed_10m",
    "wind_gusts_10m",
    "surface_pressure",
    "shortwave_radiation",
    "cloud_cover",
]

API_URL             = "https://archive-api.open-meteo.com/v1/archive"
PAUSE_BETWEEN       = 5.0   # base seconds between requests (jitter added)
MAX_RETRIES         = 5
COOLDOWN_AFTER_FAIL = 300   # seconds to wait after a complete failure
COOLDOWN_EVERY_N    = 50    # cool down every N successful fetches
COOLDOWN_DURATION   = 600   # 10-minute cooldown


def fetch_year(lat, lon, year):
    params = {
        "latitude":        lat,
        "longitude":       lon,
        "start_date":      f"{year}-01-01",
        "end_date":        f"{year}-12-31",
        "hourly":          ",".join(HOURLY_VARS),
        "timezone":        "Europe/Berlin",
        "wind_speed_unit": "ms",
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(API_URL, params=params, timeout=60)
            if resp.status_code == 429:
                wait = 60 * attempt
                print(f"rate-limited, waiting {wait}s (attempt {attempt}/{MAX_RETRIES})", flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            df = pd.DataFrame(data["hourly"])
            df.rename(columns={"time": "datetime"}, inplace=True)
            df["datetime"] = pd.to_datetime(df["datetime"])
            df["latitude"]  = lat
            df["longitude"] = lon
            return df
        except requests.exceptions.HTTPError:
            raise
        except Exception as e:
            if attempt == MAX_RETRIES:
                raise
            wait = 30 * attempt
            print(f"error ({e}), retrying in {wait}s...", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"Failed after {MAX_RETRIES} attempts")


# ── Step 1: load all thermal rows with coordinates ────────────────────────────
print("Loading outages...")
df = pd.read_parquet(OUTAGES_PARQUET).reset_index()
coords = pd.read_csv(COORDS_CSV)
units_with_coords = coords.dropna(subset=["latitude", "longitude"])[["EICCode", "latitude", "longitude"]]

all_thermal = (
    df[df["Fuel"].isin(THERMAL_FUELS)]
    .merge(units_with_coords, on="EICCode", how="inner")
    .copy()
)
all_thermal["DateTime"] = pd.to_datetime(all_thermal["DateTime"])
all_thermal["year"] = all_thermal["DateTime"].dt.year

print(f"  Total thermal rows with coordinates: {len(all_thermal):,}")
print(f"  Unique units: {all_thermal['EICCode'].nunique()}")
print(f"  Type breakdown:\n{all_thermal['Type_entsoe_ex_post'].value_counts().to_string()}")

# ── Step 2: build location × year fetch list ──────────────────────────────────
loc_years = (
    all_thermal[["latitude", "longitude", "year"]]
    .drop_duplicates()
    .sort_values(["latitude", "longitude", "year"])
    .reset_index(drop=True)
)
print(f"\n  Unique location × year combos to fetch: {len(loc_years)}")

# ── Step 3: resume from checkpoint ───────────────────────────────────────────
if os.path.exists(CHECKPOINT):
    done_df = pd.read_parquet(CHECKPOINT)
    done_keys = set(
        zip(done_df["latitude"].round(6), done_df["longitude"].round(6), done_df["year"])
    )
    print(f"  Resuming — {len(done_keys)} location×year already in checkpoint.")
    weather_dfs = [done_df]
else:
    done_keys = set()
    weather_dfs = []

# ── Step 4: fetch weather year-by-year per location ───────────────────────────
to_fetch = loc_years[
    ~loc_years.apply(
        lambda r: (round(r["latitude"], 6), round(r["longitude"], 6), r["year"]) in done_keys,
        axis=1
    )
].reset_index(drop=True)

print(f"  Remaining to fetch: {len(to_fetch)}\n")

failed = []
success_count = 0

for i, row in enumerate(to_fetch.itertuples(), start=1):
    lat, lon, year = row.latitude, row.longitude, row.year
    print(f"  [{i}/{len(to_fetch)}] ({lat:.4f}, {lon:.4f}) {year}", end=" ... ", flush=True)

    try:
        df_year = fetch_year(lat, lon, year)
        df_year["year"] = year
        weather_dfs.append(df_year)
        success_count += 1
        print(f"OK ({len(df_year):,} rows)")

        # Checkpoint + cooldown every N successes
        if success_count % COOLDOWN_EVERY_N == 0:
            pd.concat(weather_dfs, ignore_index=True).to_parquet(CHECKPOINT, index=False)
            print(f"    [checkpoint saved — cooling down {COOLDOWN_DURATION//60} min...]")
            time.sleep(COOLDOWN_DURATION)

    except Exception as e:
        print(f"FAILED: {e}")
        failed.append((lat, lon, year))
        print(f"    [failure cooldown {COOLDOWN_AFTER_FAIL}s...]")
        time.sleep(COOLDOWN_AFTER_FAIL)

    time.sleep(PAUSE_BETWEEN + random.uniform(-2, 2))

# ── Step 5: build and save weather lookup table ───────────────────────────────
print(f"\nBuilding weather lookup table from {len(weather_dfs)} dataframe(s)...")
weather_lookup = pd.concat(weather_dfs, ignore_index=True)
weather_lookup = weather_lookup.drop(columns=["year"])
print(f"  Lookup table size: {len(weather_lookup):,} rows")

weather_lookup.to_parquet(LOOKUP_PARQUET, index=False)
print(f"  Saved: {LOOKUP_PARQUET}")

# ── Step 6: join weather to all thermal rows ──────────────────────────────────
print("\nJoining weather to all thermal rows...")
all_thermal = all_thermal.drop(columns=["year"])
result = all_thermal.merge(
    weather_lookup,
    left_on=["latitude", "longitude", "DateTime"],
    right_on=["latitude", "longitude", "datetime"],
    how="left"
).drop(columns=["datetime"])

matched = result[HOURLY_VARS[0]].notna().sum()
print(f"  Rows with weather matched: {matched:,} / {len(result):,}")
print(f"  Columns: {result.columns.tolist()}")

# ── Step 7: save complete dataset ─────────────────────────────────────────────
result.to_parquet(OUT_PARQUET, index=False)
print(f"\nSaved: {OUT_PARQUET}")

if os.path.exists(CHECKPOINT):
    os.remove(CHECKPOINT)
    print("Checkpoint removed.")

if failed:
    print(f"\nFailed ({len(failed)}): {failed}")
else:
    print("All location×year combos fetched successfully.")
