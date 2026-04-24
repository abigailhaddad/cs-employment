"""
Pull ACS microdata from IPUMS USA to analyze bachelor's-degree holders'
labor market outcomes by field of degree, 2009-2024.

Universe: ages 22-50, not in school, holds a bachelor's degree.
Fields analyzed: Computer Science, Engineering, Math/Stats, Business,
and a Humanities bucket (English, Liberal Arts, Philosophy, History).

Age buckets (applied in analysis, not at extract time):
  - 22-27 (young)
  - 28-34 (early career)
  - 35-50 (established)
"""

import os
import time
from pathlib import Path

import pandas as pd
from ipumspy import IpumsApiClient, MicrodataExtract, readers

# -------------------------------------------------------------------
# Config
# -------------------------------------------------------------------

# Load .env if present (python-dotenv not required; simple parser)
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

API_KEY = os.environ.get("IPUMS_API_KEY")
if not API_KEY:
    raise RuntimeError(
        "IPUMS_API_KEY not set. Add it to a .env file or run:\n"
        "  export IPUMS_API_KEY=your_key_here"
    )

REPO_ROOT = Path(__file__).parent
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# ACS 1-year samples, 2009-2024.
# 2020 1-year file is "experimental" per Census Bureau guidance and not
# comparable to other years, so we skip it.
YEARS = list(range(2009, 2020)) + [2021, 2022, 2023, 2024]
SAMPLES = [f"us{y}a" for y in YEARS]

# Variables needed for employment, jobs, income analyses.
VARIABLES = [
    "AGE",
    "SCHOOL",    # in-school status (restrict to not in school)
    "EMPSTAT",   # employment status
    "EDUC",      # educational attainment
    "DEGFIELD",  # field of first BA
    "OCC",       # occupation (contemporaneous Census code)
    "OCC2010",   # harmonized occupation across years
    "IND",       # industry (contemporaneous)
    "IND1990",   # harmonized industry
    "INCWAGE",   # wage/salary income
    "UHRSWORK",  # usual hours worked per week (needed for full-time filter)
    "PERWT",     # person weight
]

# 2-digit DEGFIELD codes grouped into analysis buckets.
FIELD_CODES = {
    "Computer Science": [21],
    "Engineering": [24],
    "Mathematics": [37],
    "Business": [61],
    "Humanities": [33, 34, 48, 62],  # English, Liberal Arts, Philosophy, History
}

AGE_BUCKETS = [
    ("22-27 (young)", 22, 27),
    ("28-34 (early career)", 28, 34),
    ("35-50 (established)", 35, 50),
]


# -------------------------------------------------------------------
# Submit + download extract
# -------------------------------------------------------------------

def submit_and_download():
    """Submit an extract, poll until ready, download the .dat.gz + DDI."""
    client = IpumsApiClient(API_KEY)

    extract = MicrodataExtract(
        collection="usa",
        description="CS grad employment/jobs/income replication 2009-2024",
        samples=SAMPLES,
        variables=VARIABLES,
    )

    print(f"Submitting extract for {len(SAMPLES)} samples, "
          f"{len(VARIABLES)} variables...")
    client.submit_extract(extract)
    print(f"Submitted. Extract number: {extract._id}")

    # Poll every 20s. IPUMS API allows 100 req/min; this is well under.
    print("Waiting for extract to complete (typically 10-30 min)...")
    start = time.time()
    while True:
        status = client.extract_status(extract)
        elapsed = int(time.time() - start)
        print(f"  [{elapsed:>4}s] status: {status}")
        if status == "completed":
            break
        if status == "failed":
            raise RuntimeError("IPUMS extract failed")
        time.sleep(20)

    print(f"Downloading to {DATA_DIR}...")
    client.download_extract(extract, download_dir=DATA_DIR)
    print("Download complete.")


def find_existing_extract():
    """If we've already downloaded an extract, reuse the most recent DDI."""
    ddis = sorted(DATA_DIR.glob("usa_*.xml"))
    if ddis:
        print(f"Reusing existing extract: {ddis[-1].name}")
        return ddis[-1]
    return None


# -------------------------------------------------------------------
# Load + universe filter
# -------------------------------------------------------------------

CHUNK_SIZE = 500_000  # rows per chunk; keeps peak RAM manageable


def load_data(ddi_path: Path) -> pd.DataFrame:
    """Read the fixed-width .dat.gz in chunks, filtering to universe on the fly.

    Reading the full multi-year ACS file into memory at once requires ~10GB+
    RAM. Chunked reading keeps peak usage well under 2GB by discarding
    out-of-universe rows before accumulating.
    """
    ddi = readers.read_ipums_ddi(ddi_path)
    candidates = list(DATA_DIR.glob(f"{ddi_path.stem}.dat*"))
    if not candidates:
        raise FileNotFoundError(f"No .dat file found for {ddi_path}")
    dat_path = candidates[0]
    print(f"Reading {dat_path.name} in chunks of {CHUNK_SIZE:,}...")

    kept = []
    total_read = 0
    for chunk in readers.read_microdata_chunked(ddi, dat_path, chunksize=CHUNK_SIZE):
        total_read += len(chunk)
        chunk = chunk[
            (chunk["AGE"] >= 22) & (chunk["AGE"] <= 50)
            & (chunk["SCHOOL"] == 1)
            & (chunk["DEGFIELD"] > 0)
        ]
        if len(chunk):
            kept.append(chunk)
        if total_read % 5_000_000 == 0:
            print(f"  ...{total_read:,} rows read so far")

    df = pd.concat(kept, ignore_index=True)
    print(f"  read {total_read:,} total rows -> kept {len(df):,} "
          f"(age 22-50, not in school, BA)")
    return df


def filter_universe(df: pd.DataFrame) -> pd.DataFrame:
    """No-op: universe filter now happens inside load_data for memory safety."""
    return df


def add_buckets(df: pd.DataFrame) -> pd.DataFrame:
    """Add age_bucket and field columns. Drop rows outside buckets."""
    df = df.copy()
    df["age_bucket"] = pd.NA
    for label, lo, hi in AGE_BUCKETS:
        mask = (df["AGE"] >= lo) & (df["AGE"] <= hi)
        df.loc[mask, "age_bucket"] = label

    df["field"] = pd.NA
    for label, codes in FIELD_CODES.items():
        df.loc[df["DEGFIELD"].isin(codes), "field"] = label

    df = df.dropna(subset=["age_bucket", "field"])
    return df


def main():
    ddi = find_existing_extract()
    if ddi is None:
        submit_and_download()
        ddi = find_existing_extract()
        if ddi is None:
            raise RuntimeError("Extract completed but no DDI found")

    df = load_data(ddi)
    df = filter_universe(df)
    df = add_buckets(df)

    out = DATA_DIR / "analysis_ready.parquet"
    df.to_parquet(out, index=False)
    print(f"\nWrote {out} ({len(df):,} rows)")

    print("\nRow counts by field x age bucket:")
    print(df.groupby(["field", "age_bucket"], observed=True).size().unstack())


if __name__ == "__main__":
    main()
