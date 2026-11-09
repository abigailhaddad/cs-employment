# CS Employment

Analyzes labor market outcomes for young bachelor's degree holders by field,
using ACS microdata from IPUMS USA (2009–2024, no 2020).

The final output is a scrollytelling page (`web/index.html`) that reads
pre-generated JSON files from `web/data/`.

## Setup

```bash
python3 -m venv myenv
. myenv/bin/activate
pip install uv && uv pip install -r requirements.txt
```

You need an IPUMS USA API key (register at <https://usa.ipums.org/usa/>).
Either set it as an env var or put it in a `.env` file:

```bash
export IPUMS_API_KEY=your_key_here
```

## Run

```bash
python run_all.py
```

Three steps run in sequence:

1. **`extract.py`** — submits an IPUMS extract for ACS 1-year samples
   2009–2024, polls until ready, downloads the fixed-width data + DDI
   codebook, filters to the universe (ages 22–50, not in school, holds a BA),
   and writes `data/analysis_ready.parquet`. First run takes 15–30 min
   (IPUMS queue); subsequent runs reuse the cached extract.

2. **`analysis.py`** — computes weighted employment rates (employed /
   unemployed / NILF) by year, field, and age bucket. Writes
   `data/employment_rates.csv`. Prints a sanity-check table of CS age 22–27
   rates — these should match IFP's chart within ~2 percentage points.

3. **`export_web_data.py`** — reads the CSVs and parquet, builds the JSON
   files the HTML page fetches at runtime, and writes them to `web/data/`.

## Rebuild on GitHub Actions

`.github/workflows/rebuild.yml` (manual, "Run workflow") re-submits the IPUMS
extract, regenerates `data/employment_rates.csv` and `web/data/*.json`, runs
`scripts/check_outputs.py`, and opens a PR from a `regen/<run-id>` branch. It
never pushes to the default branch and never commits raw microdata.

- One-time setup: create a key at <https://account.ipums.org/api_keys> and add
  it as the repository secret `IPUMS_API_KEY`. Settings > Actions > General >
  "Allow GitHub Actions to create and approve pull requests" lets the workflow
  open the PR itself; otherwise it pushes the branch and prints a compare link.
- Expect 1 to 5 hours, almost all of it waiting in the IPUMS queue. If the job
  times out, the extract number is printed in the run summary; re-run the
  workflow with it in the `extract_number` input to resume.
- The numbers written in `web/index.html` (prose and values hard-coded in its
  script) are not regenerated. The PR body lists the new values to copy in.
- Pinned versions for CI are in `requirements-ci.txt`.
- Locally: `python scripts/resubmit_extract.py --dry-run` prints the extract
  definition without a key.

## Layout

```
.
├── extract.py           # IPUMS extract + universe filter
├── analysis.py          # weighted employment rates
├── export_web_data.py   # JSON export for the web page
├── run_all.py           # orchestrator
├── requirements.txt
├── data/                # created on first run; holds raw + processed data
└── web/
    ├── index.html       # scrollytelling page
    └── data/            # JSON files read by index.html
```

## Methodology

- **Universe**: ages 22–50, not in school (SCHOOL=1), holds a bachelor's
  degree (DEGFIELD > 0).
- **Age buckets**: 22–27 (young), 28–34 (early career), 35–50 (established).
- **Fields** (DEGFIELD codes): Computer Science (21), Engineering (24),
  Mathematics/Statistics (37), Business (61), Humanities — English (33),
  Liberal Arts (34), Philosophy (48), History (62).
- **Employment**: EMPSTAT 1 = employed, 2 = unemployed, 3 = not in labor
  force.
- **2020**: skipped. The 2020 1-year ACS is experimental per Census Bureau
  guidance and not comparable to other years.
- **Cell minimum**: cells with fewer than 50 unweighted observations are
  dropped.

## Data source

American Community Survey via IPUMS USA:
Steven Ruggles et al., IPUMS USA: Version 15.0 [dataset],
Minneapolis, MN: IPUMS, 2024. <https://doi.org/10.18128/D010.V15.0>
