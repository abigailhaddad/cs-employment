import yaml
from pathlib import Path

_cfg = yaml.safe_load((Path(__file__).parent / "config.yaml").read_text())

YEARS          = _cfg["years"]
SAMPLES        = [f"us{y}a" for y in YEARS]
VARIABLES      = _cfg["variables"]
FIELD_CODES    = _cfg["field_codes"]
AGE_BUCKETS    = [(_b["label"], _b["min"], _b["max"]) for _b in _cfg["age_buckets"]]
MIN_N          = _cfg["min_n"]
TECH_OCC       = set().union(*[range(lo, hi + 1) for lo, hi in _cfg["tech_occ_ranges"]])
BUBBLE_YEARS   = _cfg["bubble_years"]
TECH_OCC_YEARS = _cfg["tech_occ_years"]
