import os
import time
from pathlib import Path

import pandas as pd
from ipumspy import IpumsApiClient, MicrodataExtract, readers

API_KEY = os.environ.get("IPUMS_API_KEY") or (
    next(
        (v.split("=", 1)[1].strip() for v in
         (Path(__file__).parent / ".env").read_text().splitlines()
         if v.startswith("IPUMS_API_KEY=")),
        None
    ) if (Path(__file__).parent / ".env").exists() else None
)
if not API_KEY:
    raise RuntimeError("IPUMS_API_KEY not set")

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

YEARS   = list(range(2009, 2020)) + [2021, 2022, 2023, 2024]  # no 2020 (experimental)
SAMPLES = [f"us{y}a" for y in YEARS]

VARIABLES = [
    "AGE", "SCHOOL", "EMPSTAT", "EDUC", "DEGFIELD",
    "OCC", "OCC2010", "IND", "IND1990",
    "INCWAGE", "UHRSWORK", "PERWT",
]

FIELD_CODES = {
    "Computer Science": [21],
    "Engineering":      [24],
    "Mathematics":      [37],
    "Business":         [61],
    "Humanities":       [33, 34, 48, 62],
}

AGE_BUCKETS = [
    ("22-27 (young)",       22, 27),
    ("28-34 (early career)", 28, 34),
    ("35-50 (established)", 35, 50),
]


def download_extract():
    client  = IpumsApiClient(API_KEY)
    extract = MicrodataExtract(
        collection="usa",
        description="CS grad employment 2009-2024",
        samples=SAMPLES,
        variables=VARIABLES,
    )
    client.submit_extract(extract)
    print(f"Submitted extract {extract._id}. Polling...")
    start = time.time()
    while True:
        status = client.extract_status(extract)
        print(f"  [{int(time.time()-start)}s] {status}")
        if status == "completed":
            break
        if status == "failed":
            raise RuntimeError("IPUMS extract failed")
        time.sleep(20)
    client.download_extract(extract, download_dir=DATA_DIR)


def load_and_filter(ddi_path: Path) -> pd.DataFrame:
    ddi = readers.read_ipums_ddi(ddi_path)
    dat = next(iter(DATA_DIR.glob(f"{ddi_path.stem}.dat*")))

    chunks = []
    for chunk in readers.read_microdata_chunked(ddi, dat, chunksize=500_000):
        chunk = chunk[
            chunk["AGE"].between(22, 50)
            & (chunk["SCHOOL"] == 1)
            & (chunk["DEGFIELD"] > 0)
        ]
        if len(chunk):
            chunks.append(chunk)

    df = pd.concat(chunks, ignore_index=True)

    df["age_bucket"] = pd.NA
    for label, lo, hi in AGE_BUCKETS:
        df.loc[df["AGE"].between(lo, hi), "age_bucket"] = label

    df["field"] = pd.NA
    for label, codes in FIELD_CODES.items():
        df.loc[df["DEGFIELD"].isin(codes), "field"] = label

    return df.dropna(subset=["age_bucket", "field"])


def main():
    ddis = sorted(DATA_DIR.glob("usa_*.xml"))
    if not ddis:
        download_extract()
        ddis = sorted(DATA_DIR.glob("usa_*.xml"))

    ddi = ddis[-1]
    print(f"Using {ddi.name}")
    df = load_and_filter(ddi)
    print(f"{len(df):,} rows after filtering")

    out = DATA_DIR / "analysis_ready.parquet"
    df.to_parquet(out, index=False)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
