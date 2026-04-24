import pandas as pd

from config import MIN_N
from extract import DATA_DIR


def employment_rates(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (year, field, bucket), g in df.groupby(["YEAR", "field", "age_bucket"], observed=True):
        w = g["PERWT"].values.astype(float)
        total = w.sum()
        if total == 0 or len(g) < MIN_N:
            continue
        rows.append({
            "year":           int(year),
            "field":          field,
            "age_bucket":     bucket,
            "n_unweighted":   len(g),
            "n_weighted":     total,
            "employed_pct":   100 * w[g["EMPSTAT"].values == 1].sum() / total,
            "unemployed_pct": 100 * w[g["EMPSTAT"].values == 2].sum() / total,
            "nilf_pct":       100 * w[g["EMPSTAT"].values == 3].sum() / total,
        })
    return pd.DataFrame(rows).sort_values(["field", "age_bucket", "year"]).reset_index(drop=True)


def main():
    df = pd.read_parquet(DATA_DIR / "analysis_ready.parquet")
    print(f"Loaded {len(df):,} rows")

    emp_rates = employment_rates(df)
    emp_rates.to_csv(DATA_DIR / "employment_rates.csv", index=False)
    print(f"Wrote employment_rates.csv ({len(emp_rates)} rows)")

    # Sanity check: should match IFP chart within ~2pp
    cs_young = emp_rates[
        (emp_rates["field"] == "Computer Science")
        & (emp_rates["age_bucket"] == "22-27 (young)")
    ]
    print("\nCS age 22-27 employment rates:")
    print(cs_young[["year", "employed_pct", "unemployed_pct", "nilf_pct", "n_unweighted"]].to_string(index=False))


if __name__ == "__main__":
    main()
