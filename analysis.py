"""
Compute weighted employment rates by year, field, and age bucket.

Reads data/analysis_ready.parquet (written by extract.py).
Writes data/employment_rates.csv, which export_web_data.py reads to
build the JSON files that the HTML page consumes.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from extract import DATA_DIR, AGE_BUCKETS, FIELD_CODES

MIN_N = 50  # drop cells with fewer unweighted observations


def employment_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Weighted share Employed / Unemployed / NILF by year, field, age bucket."""
    rows = []
    grouped = df.groupby(["YEAR", "field", "age_bucket"], observed=True)
    for (year, field, bucket), g in grouped:
        w = g["PERWT"].values.astype(float)
        total = w.sum()
        if total == 0 or len(g) < MIN_N:
            continue
        emp   = w[g["EMPSTAT"].values == 1].sum()
        unemp = w[g["EMPSTAT"].values == 2].sum()
        nilf  = w[g["EMPSTAT"].values == 3].sum()
        rows.append({
            "year":           int(year),
            "field":          field,
            "age_bucket":     bucket,
            "n_unweighted":   len(g),
            "n_weighted":     total,
            "employed_pct":   100 * emp   / total,
            "unemployed_pct": 100 * unemp / total,
            "nilf_pct":       100 * nilf  / total,
        })
    return (
        pd.DataFrame(rows)
        .sort_values(["field", "age_bucket", "year"])
        .reset_index(drop=True)
    )


def main():
    path = DATA_DIR / "analysis_ready.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run extract.py first.")
    df = pd.read_parquet(path)
    print(f"Loaded {len(df):,} rows")

    print("\nComputing employment rates...")
    emp_rates = employment_rates(df)
    emp_rates.to_csv(DATA_DIR / "employment_rates.csv", index=False)
    print(f"  wrote employment_rates.csv ({len(emp_rates)} rows)")

    # Sanity check: CS age 22-27 employment rate should match IFP chart (~90%)
    print("\nSanity check — CS age 22-27 employment rate over time:")
    cs_young = emp_rates[
        (emp_rates["field"] == "Computer Science")
        & (emp_rates["age_bucket"] == "22-27 (young)")
    ]
    print(cs_young[
        ["year", "employed_pct", "unemployed_pct", "nilf_pct", "n_unweighted"]
    ].to_string(index=False))


if __name__ == "__main__":
    main()
