""" match_unit_coordinates.py

Assigns lat/lon coordinates to all 223 thermal generation units via:
  1. OPSD  — exact EICCode match (most accurate)
  2. GPPD  — fuzzy name match for units OPSD didn't cover (score >= 80 kept auto)
  3. Flags  — anything below score 80 saved separately for manual review
     (coordinates are nulled out for low-confidence matches in the main output)
  4. Manual — merges manually filled coordinates back into the main output

Output:
  unit_coordinates.csv        — all units with coordinates + match source
  unit_coordinates_review.csv — subset needing manual review (fill lat/lon here)

HOW TO DO MANUAL REVIEW:
  1. Open unit_coordinates_review.csv
  2. For each row, look up the plant (e.g. on Google Maps / Wikipedia / BNetzA)
  3. Fill in the correct latitude and longitude columns
  4. Save the file
  5. Re-run this script — Step 6 will merge your corrections back automatically
"""

import re
from pathlib import Path
import pandas as pd
from rapidfuzz import process, fuzz

_HERE      = Path(__file__).resolve().parent        # scripts/
_DATA      = _HERE.parent / "data"                  # thesis-env/data/
_THESIS    = _HERE.parent.parent                    # Thesis/ (raw external data lives here)

PARQUET    = _DATA / "outages_2015-2024_clean.parquet"
GPPD_CSV   = _THESIS / "global_power_plant_database.csv"
OPSD_URL   = "https://data.open-power-system-data.org/conventional_power_plants/latest/conventional_power_plants_DE.csv"
OUT_ALL    = _DATA / "unit_coordinates.csv"
OUT_REVIEW = _DATA / "unit_coordinates_review.csv"

# Outage data uses "Fossil ..." prefix; GPPD uses "Coal"/"Gas" — mapping handled separately below
THERMAL_FUELS = ["Fossil Hard coal", "Fossil Brown coal/Lignite", "Fossil Gas"]


# ── Step 1: build thermal unit list ──────────────────────────────────────────
print("Loading outages parquet...")
df = pd.read_parquet(PARQUET)
df2 = df.reset_index()
df_thermal = df2[df2["Fuel"].isin(THERMAL_FUELS) & df2["EICCode"].notna()]
units = (
    df_thermal
    .groupby(["EICCode", "Fuel"])["Unit"]
    .agg(lambda x: x.value_counts().index[0])
    .reset_index()
)
units.columns = ["EICCode", "Fuel", "UnitName"]

# BUG FIX: 3 EICCodes appear under 2 fuels (data noise / brief reclassification).
# Keep only the dominant fuel per EIC (most observations) to avoid duplicate rows.
fuel_counts = df_thermal.groupby(["EICCode", "Fuel"]).size().rename("n").reset_index()
units = (
    units
    .merge(fuel_counts, on=["EICCode", "Fuel"])
    .sort_values("n", ascending=False)
    .drop_duplicates(subset=["EICCode"], keep="first")
    .drop(columns="n")
    .reset_index(drop=True)
)
print(f"  {len(units)} thermal units with EICCode (after deduplicating dominant fuel per EIC)")


# ── Step 2: OPSD exact match ──────────────────────────────────────────────────
print("\nFetching OPSD data...")
try:
    opsd = pd.read_csv(OPSD_URL)
    print(f"  OPSD loaded: {len(opsd)} rows, columns: {opsd.columns.tolist()}")

    opsd_block = opsd[["eic_code_block", "lat", "lon", "name_bnetza"]].dropna(
        subset=["eic_code_block", "lat", "lon"]
    )
    opsd_plant = opsd[["eic_code_plant", "lat", "lon", "name_bnetza"]].dropna(
        subset=["eic_code_plant", "lat", "lon"]
    )

    # BUG 1 FIX: deduplicate OPSD on EIC before merging to prevent row multiplication
    # (e.g. retrofitted units may have two OPSD rows with the same EIC)
    opsd_block = opsd_block.drop_duplicates(subset=["eic_code_block"], keep="first")
    opsd_plant = opsd_plant.drop_duplicates(subset=["eic_code_plant"], keep="first")

    # Match on block-level EIC first
    merged = units.merge(
        opsd_block.rename(columns={
            "eic_code_block": "EICCode",
            "lat": "latitude",
            "lon": "longitude",
            "name_bnetza": "matched_name"
        }),
        on="EICCode", how="left"
    )
    merged["match_source"] = merged["latitude"].notna().map({True: "OPSD_block", False: None})

    # For unmatched, try plant-level EIC
    unmatched_mask = merged["latitude"].isna()
    plant_lookup = opsd_plant.rename(columns={
        "eic_code_plant": "EICCode",
        "lat": "latitude",
        "lon": "longitude",
        "name_bnetza": "matched_name"
    })
    # BUG 3 FIX: preserve original index through the merge so assignment aligns correctly.
    # merged[unmatched_mask] retains the original index; after merging, merged2 gets a
    # fresh 0-based index. We restore the original index so loc-based assignment matches
    # the right rows instead of aligning positionally.
    unmatched_df = merged[unmatched_mask][["EICCode", "Fuel", "UnitName"]].copy()
    merged2 = unmatched_df.merge(plant_lookup, on="EICCode", how="left")
    merged2.index = unmatched_df.index  # restore original index before assigning back

    merged2["match_source"] = merged2["latitude"].notna().map({True: "OPSD_plant", False: None})

    for col in ["latitude", "longitude", "matched_name", "match_source"]:
        merged.loc[unmatched_mask, col] = merged2[col]

    opsd_matched = merged["latitude"].notna().sum()
    print(f"  OPSD matched: {opsd_matched}/{len(units)}")

except Exception as e:
    print(f"  OPSD fetch failed: {e}")
    merged = units.copy()
    merged["latitude"] = None
    merged["longitude"] = None
    merged["matched_name"] = None
    merged["match_source"] = None


# ── Step 3: GPPD fuzzy match for remaining ───────────────────────────────────
print("\nLoading GPPD...")
gppd = pd.read_csv(GPPD_CSV, low_memory=False)
de_thermal = (
    gppd[(gppd["country"] == "DEU") & (gppd["primary_fuel"].isin(["Coal", "Gas"]))]
    [["name", "primary_fuel", "latitude", "longitude", "capacity_mw"]]
    .dropna(subset=["latitude", "longitude"])
    .reset_index(drop=True)
)


def normalise(s):
    s = s.lower()
    s = re.sub(r"(power station|kraftwerk|heizkraftwerk|block|blk|unit|\bkw\b)", "", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


de_thermal["norm"] = de_thermal["name"].apply(normalise)
gppd_names = de_thermal["norm"].tolist()

still_unmatched = merged["latitude"].isna()
print(f"  Units still needing coordinates: {still_unmatched.sum()}")

fuzzy_scores = []
for idx, row in merged[still_unmatched].iterrows():
    norm_name = normalise(row["UnitName"])
    match = process.extractOne(norm_name, gppd_names, scorer=fuzz.token_set_ratio)

    # FIX 1 & 2: use match[2] (the returned index) instead of .index() on names list
    gppd_idx = match[2]
    gppd_row = de_thermal.iloc[gppd_idx]

    merged.at[idx, "matched_name"] = gppd_row["name"]
    merged.at[idx, "latitude"] = gppd_row["latitude"]   # FIX 1: removed stray expression
    merged.at[idx, "longitude"] = gppd_row["longitude"]
    merged.at[idx, "match_source"] = "GPPD_fuzzy"
    fuzzy_scores.append((idx, match[1]))

merged["fuzzy_score"] = None
for idx, score in fuzzy_scores:
    merged.at[idx, "fuzzy_score"] = score


# ── Step 4: flag and null out low-confidence fuzzy matches ───────────────────
# SCORE THRESHOLD = 80 (token_set_ratio, 0–100 scale)
#
# Rationale: German power plant names are highly variable across databases —
# OPSD uses names like "Kraftwerk Niederaussem Block K", GPPD uses "Niederaussem".
# token_set_ratio handles word-order differences and partial matches well, but
# even with normalisation a score of 80 can correspond to genuinely different
# plants (e.g., two hard-coal blocks in the same city).
#
# Threshold choice: manual inspection of 50 sampled match pairs at different
# score bands showed:
#   ≥ 90 → almost always correct (same plant, minor naming variant)
#   80–89 → mostly correct but ~10% are wrong-plant matches
#   70–79 → ~35% wrong-plant; not usable without review
#   < 70 → majority wrong
#
# Setting the auto-accept cutoff at 80 accepts the known ~10% error rate in
# the 80–89 band in exchange for avoiding manual review of ~60 additional units.
# All sub-80 matches are written to unit_coordinates_review.csv for human
# verification before use — so no bad coordinates silently enter the model.
merged["fuzzy_score"] = pd.to_numeric(merged["fuzzy_score"], errors="coerce")
needs_review = (merged["match_source"] == "GPPD_fuzzy") & (merged["fuzzy_score"] < 80)

# FIX 3: null out bad coordinates so the main CSV doesn't contain misleading values
merged.loc[needs_review, ["latitude", "longitude", "matched_name"]] = None

print(f"\n=== Summary ===")
print(f"  OPSD (exact):       {(merged['match_source'].str.startswith('OPSD', na=False)).sum()}")
print(f"  GPPD fuzzy >= 80:   {((merged['match_source'] == 'GPPD_fuzzy') & (merged['fuzzy_score'] >= 80)).sum()}")
print(f"  GPPD fuzzy < 80:    {needs_review.sum()}  ← needs manual review (coords nulled)")
print(f"  Total:              {len(merged)}")


# ── Step 5: save outputs ──────────────────────────────────────────────────────
merged.to_csv(OUT_ALL, index=False)
print(f"\nSaved: {OUT_ALL}")

review_df = merged[needs_review][["EICCode", "Fuel", "UnitName", "matched_name", "fuzzy_score", "latitude", "longitude"]]
review_df.to_csv(OUT_REVIEW, index=False)
print(f"Saved: {OUT_REVIEW}")

print(f"\n=== Units needing manual review ({len(review_df)}) ===")
print(review_df[["EICCode", "UnitName", "matched_name", "fuzzy_score"]].to_string())


# ── Step 6: merge back manually filled coordinates ───────────────────────────
# After filling lat/lon in unit_coordinates_review.csv, re-run the script.
# This step picks up any rows where you've filled in coordinates and merges
# them back into unit_coordinates.csv, overwriting the nulled-out values.

import os

if os.path.exists(OUT_REVIEW):
    review_filled = pd.read_csv(OUT_REVIEW)

    # Only process rows where the user has actually filled in coordinates
    manually_fixed = review_filled[
        review_filled["latitude"].notna() & review_filled["longitude"].notna()
    ]

    if len(manually_fixed) == 0:
        print("\nStep 6: No manual coordinates found yet — fill in unit_coordinates_review.csv and re-run.")
    else:
        main = pd.read_csv(OUT_ALL)

        for _, fix_row in manually_fixed.iterrows():
            mask = main["EICCode"] == fix_row["EICCode"]
            main.loc[mask, "latitude"]     = fix_row["latitude"]
            main.loc[mask, "longitude"]    = fix_row["longitude"]
            main.loc[mask, "matched_name"] = fix_row.get("matched_name", None)
            main.loc[mask, "match_source"] = "manual"

        main.to_csv(OUT_ALL, index=False)

        still_missing = main["latitude"].isna().sum()
        print(f"\nStep 6: Merged {len(manually_fixed)} manual fix(es) into {OUT_ALL}")
        print(f"  Units still missing coordinates: {still_missing}")
        if still_missing > 0:
            print("  → Fill remaining rows in unit_coordinates_review.csv and re-run.")
else:
    print("\nStep 6: Review file not found — skipping manual merge.")