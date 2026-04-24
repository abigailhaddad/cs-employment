"""
Export all chart data for the scrollytelling page as JSON files.
Run after run_all.py. Writes to web/data/.

The HTML fetches these files at runtime instead of using hardcoded values,
so re-running the pipeline automatically updates the page.
"""

import json
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
WEB_DATA_DIR = Path(__file__).parent / "web" / "data"
WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)

CS_OCC  = set(range(1000, 1108))
ENG_OCC = set(range(1300, 1531))
TECH_OCC = CS_OCC | ENG_OCC


def write(name: str, obj) -> None:
    path = WEB_DATA_DIR / f"{name}.json"
    path.write_text(json.dumps(obj, indent=2))
    print(f"  wrote {name}.json")


def main():
    emp = pd.read_csv(DATA_DIR / "employment_rates.csv")
    df  = pd.read_parquet(DATA_DIR / "analysis_ready.parquet")

    # ── 1. CS 22-27 unemployment + NILF line ──────────────────────────
    cs_young = (
        emp[(emp["field"] == "Computer Science") & (emp["age_bucket"] == "22-27 (young)")]
        .sort_values("year")
    )
    write("cs_unemployment", [
        {"y": int(r.year), "u": round(r.unemployed_pct, 1), "n": round(r.nilf_pct, 1)}
        for _, r in cs_young.iterrows()
    ])

    # ── 2. Bubble chart — field unemployment + population, 2022 & 2024 ─
    young_emp = emp[emp["age_bucket"] == "22-27 (young)"]
    for yr in [2022, 2024]:
        d = young_emp[young_emp["year"] == yr]
        write(f"bubble_{yr}", [
            {"field": r.field, "unemp": round(r.unemployed_pct, 1), "n": int(r.n_weighted)}
            for _, r in d.iterrows()
        ])

    # ── 3. % of employed grads in software/engineering roles, by field ─
    young_df = df[
        (df["age_bucket"] == "22-27 (young)")
        & df["YEAR"].isin([2022, 2023, 2024])
        & (df["EMPSTAT"] == 1)
    ].copy()
    young_df["in_tech_occ"] = young_df["OCC2010"].isin(TECH_OCC)

    tech_pct = {}
    for field, g in young_df.groupby("field"):
        w = g["PERWT"].values.astype(float)
        tech_w = w[g["in_tech_occ"].values].sum()
        tech_pct[field] = round(100 * tech_w / w.sum(), 1) if w.sum() > 0 else 0
    write("tech_occ_pct", tech_pct)

    # ── 4. CS unemployment by age bucket ──────────────────────────────
    age_data = {}
    for bucket, key in [
        ("22-27 (young)", "young"),
        ("28-34 (early career)", "mid"),
        ("35-50 (established)", "est"),
    ]:
        d = (
            emp[(emp["field"] == "Computer Science") & (emp["age_bucket"] == bucket)]
            .sort_values("year")
        )
        age_data[key] = [
            {"y": int(r.year), "u": round(r.unemployed_pct, 1)}
            for _, r in d.iterrows()
        ]
    write("cs_age_unemployment", age_data)

    print(f"\nAll files written to {WEB_DATA_DIR}/")


if __name__ == "__main__":
    main()
