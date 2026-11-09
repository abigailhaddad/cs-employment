"""Checks on regenerated outputs; writes a markdown summary of the numbers the
page text quotes. Exit code 1 if any hard check fails.

Run after `python run_all.py`. Uses the freshly downloaded DDI (data/usa_*.xml,
gitignored) to confirm every configured DEGFIELD code means what the field
group claims, so a wrong code in config.yaml cannot slip through again.

  python scripts/check_outputs.py --summary .rebuild/summary.md
"""
import argparse
import json
import re
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import FIELD_CODES, MIN_N, YEARS, BUBBLE_YEARS, TECH_OCC_YEARS  # noqa: E402

# What each configured group is supposed to contain: field -> {DEGFIELD code:
# text that must appear in the DDI's label for that code}. config.yaml must
# match this exactly (same groups, same codes), and every label is checked
# against the freshly downloaded DDI. Edit deliberately if a group's definition
# is changed.
EXPECTED = {
    "Computer Science": {21: "Computer and Information Sciences"},
    "Engineering": {24: "Engineering"},
    "Mathematics": {37: "Mathematics and Statistics"},
    "Business": {62: "Business"},
    "Humanities": {33: "English Language", 34: "Liberal Arts", 48: "Philosophy", 64: "History"},
}
EXPECTED_FIELDS = set(EXPECTED)
YOUNG = "22-27 (young)"

failures: list[str] = []
notes: list[str] = []


def fail(msg: str) -> None:
    failures.append(msg)
    print("FAIL:", msg)


def ok(msg: str) -> None:
    print("ok:  ", msg)


def ddi_labels(xml: Path) -> dict[int, str]:
    t = xml.read_text(encoding="utf-8", errors="replace")
    block = re.search(r'<var ID="DEGFIELD".*?</var>', t, re.S).group(0)
    return {int(c): l.strip() for c, l in re.findall(r"<catValu>(\d+)</catValu>\s*<labl>(.*?)</labl>", block, re.S)}


def check_codes(df: pd.DataFrame, labels: dict[int, str]) -> None:
    if set(FIELD_CODES) != EXPECTED_FIELDS:
        fail(f"config field groups {sorted(FIELD_CODES)} != expected {sorted(EXPECTED_FIELDS)}")
    for field, want in EXPECTED.items():
        if sorted(FIELD_CODES.get(field, [])) != sorted(want):
            fail(f"{field}: config codes {FIELD_CODES.get(field)} != expected {sorted(want)}")
        for c, text in want.items():
            got = labels.get(c)
            if got is None or text not in got:
                fail(f"{field}: code {c} DDI label is '{got}', expected to contain '{text}'")
            else:
                ok(f"{field}: {c} = {got}")
    seen = df.groupby("field", observed=True)["DEGFIELD"].unique()
    for field, codes in FIELD_CODES.items():
        got = sorted(int(x) for x in seen.get(field, []))
        if got != sorted(codes):
            fail(f"parquet {field}: DEGFIELD values {got} != config {sorted(codes)}")
        else:
            ok(f"parquet {field}: DEGFIELD values {got} match config")
        # every configured code should show up in every year (catches silent drops)
        for c in codes:
            yrs = set(df.loc[df["DEGFIELD"] == c, "YEAR"].unique())
            missing = sorted(set(YEARS) - yrs)
            if missing:
                fail(f"DEGFIELD {c} ({field}) has no rows in years {missing}")


def check_cells(emp: pd.DataFrame) -> None:
    if sorted(emp["year"].unique()) != sorted(YEARS):
        fail(f"CSV years {sorted(emp['year'].unique())} != config years")
    else:
        ok(f"CSV covers years {YEARS[0]}-{YEARS[-1]}, no 2020: {2020 not in set(emp['year'])}")
    if set(emp["field"]) != EXPECTED_FIELDS:
        fail(f"CSV fields {sorted(set(emp['field']))}")
    n_expected = len(YEARS) * len(EXPECTED_FIELDS) * 3
    if len(emp) != n_expected:
        fail(f"CSV has {len(emp)} cells, expected {n_expected} (some cell dropped under min_n={MIN_N}?)")
    else:
        ok(f"CSV has all {n_expected} year x field x age cells")
    if (emp["n_unweighted"] < MIN_N).any():
        fail("cell below min_n present")
    tot = emp[["employed_pct", "unemployed_pct", "nilf_pct"]].sum(axis=1)
    if not ((tot - 100).abs() < 1e-6).all():
        fail(f"E+U+NILF != 100 in some cells (max dev {(tot - 100).abs().max()})")
    else:
        ok("employed+unemployed+NILF = 100 in every cell")


def check_vs_committed(emp: pd.DataFrame) -> None:
    """CS/Engineering/Math codes did not change, so those rows should barely move."""
    try:
        old = pd.read_csv(StringIO(subprocess.run(
            ["git", "show", "HEAD:data/employment_rates.csv"], cwd=ROOT,
            capture_output=True, text=True, check=True).stdout))
    except Exception as e:
        notes.append(f"Could not compare with committed CSV: {e}")
        return
    keys = ["year", "field", "age_bucket"]
    m = emp.merge(old, on=keys, suffixes=("", "_old"))
    for fld in ("Computer Science", "Engineering", "Mathematics"):
        s = m[m["field"] == fld]
        d = max((s[c] - s[c + "_old"]).abs().max() for c in ("employed_pct", "unemployed_pct", "nilf_pct"))
        line = f"{fld}: max abs change vs committed CSV = {d:.3f} pp over {len(s)} cells (codes unchanged, expect ~0)"
        notes.append(line)
        print(line)
        if d > 1.0:
            fail(line)


def build_summary(emp: pd.DataFrame, web: Path) -> str:
    y = emp[emp["age_bucket"] == YOUNG].copy()
    y["u_over_eu"] = 100 * y["unemployed_pct"] / (y["employed_pct"] + y["unemployed_pct"])
    tech = json.loads((web / "tech_occ_pct.json").read_text())
    out = ["## Regenerated numbers (ages 22-27), computed from the new extract", "",
           "`unemployed_pct` = unemployed / all people (page's current definition); "
           "`U/(E+U)` = conventional unemployment rate. Both shown; the page text needs one chosen.", ""]
    for yr in BUBBLE_YEARS:
        out += [f"### {yr}", "", "| field | unemployed_pct | U/(E+U) | employed | NILF | unweighted n | weighted n |", "|---|---|---|---|---|---|---|"]
        for _, r in y[y["year"] == yr].sort_values("field").iterrows():
            out.append(f"| {r['field']} | {r['unemployed_pct']:.1f} | {r['u_over_eu']:.1f} | {r['employed_pct']:.1f} | "
                       f"{r['nilf_pct']:.1f} | {int(r['n_unweighted']):,} | {int(r['n_weighted']):,} |")
        out.append("")
    out += [f"### Share employed in software/engineering occupations, ages 22-27, {TECH_OCC_YEARS[0]}-{TECH_OCC_YEARS[-1]} (OCC2010)", "",
            "| field | % |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(tech.items())] + [""]
    cs = y[y["field"] == "Computer Science"].sort_values("year")
    out += ["### CS, ages 22-27, all years", "", "| year | unemployed_pct | U/(E+U) | NILF |", "|---|---|---|---|"]
    out += [f"| {int(r['year'])} | {r['unemployed_pct']:.1f} | {r['u_over_eu']:.1f} | {r['nilf_pct']:.1f} |" for _, r in cs.iterrows()]
    out += ["", "### Checks", ""] + [f"- {n}" for n in notes]
    return "\n".join(out) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--summary", default=None)
    a = ap.parse_args()
    root = Path(a.root)
    data, web = root / "data", root / "web" / "data"

    ddis = sorted(data.glob("usa_*.xml"))
    if not ddis:
        sys.exit("FAIL: no DDI (data/usa_*.xml); run the extract first")
    labels = ddi_labels(ddis[-1])
    df = pd.read_parquet(data / "analysis_ready.parquet", columns=["YEAR", "DEGFIELD", "field"])
    emp = pd.read_csv(data / "employment_rates.csv")
    print(f"DDI: {ddis[-1].name}; parquet rows: {len(df):,}; CSV cells: {len(emp)}")

    check_codes(df, labels)
    check_cells(emp)
    check_vs_committed(emp)
    for name in ("cs_unemployment", "bubble_2022", "bubble_2024", "tech_occ_pct", "cs_age_unemployment"):
        if not (web / f"{name}.json").exists():
            fail(f"missing web/data/{name}.json")
    tech = json.loads((web / "tech_occ_pct.json").read_text())
    tech_expected = {"Computer Science", "Engineering", "Mathematics"}
    if set(tech) != tech_expected:
        fail(f"tech_occ_pct fields {sorted(tech)} != {sorted(tech_expected)}")

    text = build_summary(emp, web)
    if a.summary:
        p = Path(a.summary)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    print(text)
    if failures:
        print(f"\n{len(failures)} check(s) FAILED")
        sys.exit(1)
    print("\nAll checks passed")


if __name__ == "__main__":
    main()
