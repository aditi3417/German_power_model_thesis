""" fetch_load.py

Fetches hourly actual total load for Germany (DE-LU bidding zone) from the
ENTSO-E Transparency Platform REST API, 2015–2024.

Requires a free ENTSO-E API token: https://transparency.entsoe.eu/usrm/user/createPublicUser

Set your token as an environment variable before running:
    export ENTSOE_TOKEN="your-token-here"
Or paste it directly into the ENTSOE_TOKEN variable below.

Output:
    data/load_germany_hourly.parquet  — columns: DateTime (Europe/Berlin, hourly), load_mw
"""

import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import pandas as pd
import requests

# ── Config ────────────────────────────────────────────────────────────────────
ENTSOE_TOKEN = os.environ.get("ENTSOE_TOKEN", "")   # set env var or paste token here
OUT_PARQUET  = "/Users/aditi/Documents/Hertie/Thesis/thesis-env/data/load_germany_hourly.parquet"
CHECKPOINT   = "/Users/aditi/Documents/Hertie/Thesis/thesis-env/data/load_checkpoint.parquet"

YEARS        = list(range(2015, 2025))
DOMAIN       = "10Y1001A1001A83F"   # DE-LU bidding zone (Germany)
API_URL      = "https://web-api.tp.entsoe.eu/api"
MAX_RETRIES  = 5
PAUSE        = 3.0   # seconds between requests

NS = {
    "gl": "urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0",
    "ei": "urn:iec62325.351:tc57wg16:451-1:errormessage:1:0",
}


def fetch_year(year: int) -> pd.DataFrame:
    """Fetch actual total load for one calendar year. Returns hourly DataFrame."""
    params = {
        "documentType":       "A65",
        "processType":        "A16",
        "outBiddingZone_Domain": DOMAIN,
        "periodStart":        f"{year}01010000",
        "periodEnd":          f"{year}12312300",
        "securityToken":      ENTSOE_TOKEN,
    }
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(API_URL, params=params, timeout=60)
            if resp.status_code == 429:
                wait = 60 * attempt
                print(f"  rate-limited, waiting {wait}s (attempt {attempt}/{MAX_RETRIES})", flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return _parse_xml(resp.text, year)
        except Exception as e:
            if attempt == MAX_RETRIES:
                raise
            wait = 30 * attempt
            print(f"  error ({e}), retrying in {wait}s...", flush=True)
            time.sleep(wait)
    raise RuntimeError(f"Failed after {MAX_RETRIES} attempts for year {year}")


def _parse_xml(xml_text: str, year: int) -> pd.DataFrame:
    """Parse ENTSO-E GL_MarketDocument XML into a hourly DataFrame."""
    root = ET.fromstring(xml_text)

    # Check for API error response
    if root.tag.endswith("Acknowledgement_MarketDocument") or "error" in root.tag.lower():
        reason = root.findtext(".//{urn:iec62325.351:tc57wg16:451-1:errormessage:1:0}text", default="unknown")
        raise ValueError(f"ENTSO-E API error: {reason}")

    records = []
    for ts in root.findall(".//{urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0}TimeSeries"):
        period = ts.find("{urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0}Period")
        if period is None:
            continue

        start_str = period.findtext(
            "{urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0}timeInterval/"
            "{urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0}start"
        )
        resolution = period.findtext(
            "{urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0}resolution"
        )
        if not start_str or resolution != "PT60M":
            continue

        # Parse UTC start time
        start_utc = datetime.fromisoformat(start_str.replace("Z", "+00:00"))

        for point in period.findall(
            "{urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0}Point"
        ):
            pos = int(point.findtext(
                "{urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0}position"
            ))
            qty = point.findtext(
                "{urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0}quantity"
            )
            if qty is None:
                continue
            # position is 1-based; offset = (pos-1) hours from period start
            dt_utc = start_utc.replace(tzinfo=timezone.utc) if start_utc.tzinfo is None else start_utc
            dt_utc = dt_utc.replace(minute=0, second=0, microsecond=0)
            import datetime as dt_mod
            dt_hour = dt_utc + dt_mod.timedelta(hours=pos - 1)
            records.append({"DateTime_utc": dt_hour, "load_mw": float(qty)})

    if not records:
        raise ValueError(f"No load records parsed for year {year} — check token or domain")

    df = pd.DataFrame(records)
    df = df.drop_duplicates(subset=["DateTime_utc"]).sort_values("DateTime_utc")

    # Convert UTC → Europe/Berlin (matches weather data timezone)
    df["DateTime"] = (
        df["DateTime_utc"]
        .dt.tz_convert("Europe/Berlin")
        .dt.tz_localize(None)        # strip tz info for consistent joins
    )
    df = df.drop(columns=["DateTime_utc"])
    df = df.sort_values("DateTime").reset_index(drop=True)

    print(f"  Parsed {len(df):,} hourly rows for {year}")
    return df


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not ENTSOE_TOKEN:
        raise EnvironmentError(
            "No ENTSOE_TOKEN found.\n"
            "  Set it with: export ENTSOE_TOKEN='your-token-here'\n"
            "  Or paste it directly into ENTSOE_TOKEN at the top of this script.\n"
            "  Get a free token at: https://transparency.entsoe.eu/usrm/user/createPublicUser"
        )

    # Resume from checkpoint if it exists
    if os.path.exists(CHECKPOINT):
        done_df  = pd.read_parquet(CHECKPOINT)
        done_years = set(done_df["DateTime"].dt.year.unique())
        dfs = [done_df]
        print(f"Resuming — years already done: {sorted(done_years)}")
    else:
        done_years = set()
        dfs = []

    remaining = [y for y in YEARS if y not in done_years]
    print(f"Years to fetch: {remaining}\n")

    for year in remaining:
        print(f"Fetching {year}...", end=" ", flush=True)
        try:
            df_year = fetch_year(year)
            dfs.append(df_year)
            # Save checkpoint after each successful year
            pd.concat(dfs, ignore_index=True).to_parquet(CHECKPOINT, index=False)
            print(f"  [checkpoint saved]")
        except Exception as e:
            print(f"  FAILED: {e}")
            print("  Saving progress so far and stopping.")
            break
        time.sleep(PAUSE)

    if not dfs:
        print("No data fetched.")
    else:
        result = pd.concat(dfs, ignore_index=True)
        result = result.drop_duplicates(subset=["DateTime"]).sort_values("DateTime").reset_index(drop=True)

        print(f"\n=== Summary ===")
        print(f"  Total rows : {len(result):,}")
        print(f"  Years      : {sorted(result['DateTime'].dt.year.unique())}")
        print(f"  Date range : {result['DateTime'].min()} → {result['DateTime'].max()}")
        print(f"  Load range : {result['load_mw'].min():.0f} – {result['load_mw'].max():.0f} MW")
        missing = result["load_mw"].isna().sum()
        if missing:
            print(f"  Missing    : {missing:,} hours")

        result.to_parquet(OUT_PARQUET, index=False)
        print(f"\nSaved: {OUT_PARQUET}")

        if os.path.exists(CHECKPOINT):
            os.remove(CHECKPOINT)
            print("Checkpoint removed.")
