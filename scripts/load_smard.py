""" load_smard.py

Combines SMARD hourly electricity consumption CSV files into a single parquet.

Download from: https://www.smard.de/en/downloadcenter/download-market-data/
  Category: Electricity consumption → Total (grid load)
  Region: Germany | Resolution: Hourly

Place all downloaded CSVs in one folder and set SMARD_DIR below.

Output:
    data/load_germany_hourly.parquet  — columns: DateTime (Europe/Berlin, tz-naive), load_mwh
"""

import glob
import os

import pandas as pd

SMARD_DIR = "/Users/aditi/Downloads"           # folder containing SMARD CSVs
OUT_PATH  = "/Users/aditi/Documents/Hertie/Thesis/thesis-env/data/load_germany_hourly.parquet"

TARGET_YEARS = set(range(2015, 2025))


def parse_smard_file(path: str) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        sep=";",
        thousands=",",
        decimal=".",
        encoding="utf-8",
    )

    # Rename to standard names
    df.columns = df.columns.str.strip()
    col_map = {c: c for c in df.columns}

    start_col = [c for c in df.columns if "start" in c.lower()][0]
    load_col  = [c for c in df.columns if "grid load" in c.lower()
                 and "pumped" not in c.lower()][0]

    df = df[[start_col, load_col]].copy()
    df.columns = ["DateTime", "load_mwh"]

    # Parse date: "Jan 1, 2015 12:00 AM"
    df["DateTime"] = pd.to_datetime(df["DateTime"], format="%b %d, %Y %I:%M %p")

    # Drop rows outside target years or where load is missing
    df = df[df["DateTime"].dt.year.isin(TARGET_YEARS)]
    df = df.dropna(subset=["load_mwh"])

    return df


# ── Find all SMARD CSVs ───────────────────────────────────────────────────────
csv_files = sorted(glob.glob(os.path.join(SMARD_DIR, "Actual_consumption_*.csv")))

if not csv_files:
    raise FileNotFoundError(
        f"No SMARD CSV files found in {SMARD_DIR}\n"
        f"Expected files matching: Actual_consumption_*.csv"
    )

print(f"Found {len(csv_files)} file(s):")
for f in csv_files:
    print(f"  {os.path.basename(f)}")

# ── Parse and combine ─────────────────────────────────────────────────────────
dfs = []
for path in csv_files:
    print(f"\nParsing {os.path.basename(path)}...", end=" ")
    df = parse_smard_file(path)
    print(f"{len(df):,} rows, years: {sorted(df['DateTime'].dt.year.unique())}")
    dfs.append(df)

result = (
    pd.concat(dfs, ignore_index=True)
    .drop_duplicates(subset=["DateTime"])
    .sort_values("DateTime")
    .reset_index(drop=True)
)

# ── Coverage check ────────────────────────────────────────────────────────────
print(f"\n=== Summary ===")
print(f"  Total rows : {len(result):,}")
print(f"  Date range : {result['DateTime'].min()} → {result['DateTime'].max()}")
print(f"  Load range : {result['load_mwh'].min():.0f} – {result['load_mwh'].max():.0f} MWh")

covered_years = set(result["DateTime"].dt.year.unique())
missing_years = TARGET_YEARS - covered_years
if missing_years:
    print(f"\n  WARNING: missing data for years: {sorted(missing_years)}")
    print("  Download the remaining files from SMARD and re-run.")
else:
    print(f"  All years 2015–2024 covered.")

# Expected ~87,672 hours for 10 years (accounting for DST)
expected = 87_672
actual   = len(result)
gap      = expected - actual
if gap > 0:
    print(f"  Note: {gap} hours below expected ({expected:,}) — may be DST transitions or missing data")

# ── Save ──────────────────────────────────────────────────────────────────────
result.to_parquet(OUT_PATH, index=False)
print(f"\nSaved: {OUT_PATH}")
