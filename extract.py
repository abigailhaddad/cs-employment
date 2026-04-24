import os
import time
from pathlib import Path

import pandas as pd
from ipumspy import IpumsApiClient, MicrodataExtract, readers

from config import SAMPLES, VARIABLES, FIELD_CODES, AGE_BUCKETS

def _api_key() -> str:
    if key := os.environ.get("IPUMS_API_KEY"):
        return key
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("IPUMS_API_KEY="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("IPUMS_API_KEY not set")

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def download_extract():
    client  = IpumsApiClient(_api_key())
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
    dat = next(DATA_DIR.glob(f"{ddi_path.stem}.dat*"))

    needed = ["YEAR", "AGE", "SCHOOL", "DEGFIELD", "EMPSTAT", "OCC2010", "PERWT"]
    chunks = []
    for chunk in readers.read_microdata_chunked(ddi, dat, chunksize=1_000_000, subset=needed):
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
