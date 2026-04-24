import json
from pathlib import Path

import pandas as pd

from config import TECH_OCC, BUBBLE_YEARS, TECH_OCC_YEARS
from extract import DATA_DIR

WEB_DATA_DIR = Path(__file__).parent / "web" / "data"
WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)


def write(name: str, obj) -> None:
    (WEB_DATA_DIR / f"{name}.json").write_text(json.dumps(obj, indent=2))
    print(f"  wrote {name}.json")


def main():
    emp = pd.read_csv(DATA_DIR / "employment_rates.csv")
    df  = pd.read_parquet(DATA_DIR / "analysis_ready.parquet")

    cs_young = emp[(emp["field"] == "Computer Science") & (emp["age_bucket"] == "22-27 (young)")].sort_values("year")
    write("cs_unemployment", [
        {"y": int(r["year"]), "u": round(r["unemployed_pct"], 1), "n": round(r["nilf_pct"], 1)}
        for r in cs_young.to_dict("records")
    ])

    young_emp = emp[emp["age_bucket"] == "22-27 (young)"]
    for yr in BUBBLE_YEARS:
        rows = young_emp[young_emp["year"] == yr].to_dict("records")
        write(f"bubble_{yr}", [
            {"field": r["field"], "unemp": round(r["unemployed_pct"], 1), "n": int(r["n_weighted"])}
            for r in rows
        ])

    young_df = df[
        (df["age_bucket"] == "22-27 (young)")
        & df["YEAR"].isin(TECH_OCC_YEARS)
        & (df["EMPSTAT"] == 1)
    ].copy()
    young_df["in_tech_occ"] = young_df["OCC2010"].isin(TECH_OCC)
    tech_pct = {}
    for field, g in young_df.groupby("field"):
        w = g["PERWT"].values.astype(float)
        tech_pct[field] = round(100 * w[g["in_tech_occ"].values].sum() / w.sum(), 1) if w.sum() > 0 else 0
    write("tech_occ_pct", tech_pct)

    bucket_keys = [
        ("22-27 (young)",        "young"),
        ("28-34 (early career)", "mid"),
        ("35-50 (established)",  "est"),
    ]
    cs = emp[emp["field"] == "Computer Science"]
    age_data = {}
    for bucket, key in bucket_keys:
        rows = cs[cs["age_bucket"] == bucket].sort_values("year").to_dict("records")
        age_data[key] = [{"y": int(r["year"]), "u": round(r["unemployed_pct"], 1)} for r in rows]
    write("cs_age_unemployment", age_data)


if __name__ == "__main__":
    main()
