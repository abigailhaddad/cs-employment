"""Re-submit the IPUMS USA extract behind this repo, wait for it, download it.

Reads IPUMS_API_KEY from the environment (never from a file in the repo).
The extract definition comes from config.yaml (samples = ACS 1-year for each
year in `years`, variables = `variables`), the same definition extract.py
submits. Output: usa_NNNNN.dat.gz + usa_NNNNN.xml (DDI) in --download-dir,
which must be gitignored (default data/, covered by .gitignore's usa_* rules).
Raw IPUMS microdata must never be committed (IPUMS terms of use).

Examples:
  python scripts/resubmit_extract.py --dry-run          # no key, no network
  IPUMS_API_KEY=... python scripts/resubmit_extract.py  # submit, wait, download
  IPUMS_API_KEY=... python scripts/resubmit_extract.py --extract-number 123
      # resume: skip submission, wait for / download an already-submitted extract
"""
import argparse
import gzip
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import SAMPLES, VARIABLES  # noqa: E402

COLLECTION = "usa"
DESCRIPTION = "cs-employment rebuild: ACS 1-year samples from config.yaml"


def build_extract():
    from ipumspy import MicrodataExtract
    return MicrodataExtract(
        collection=COLLECTION,
        description=DESCRIPTION,
        samples=SAMPLES,
        variables=VARIABLES,
    )


def check_ignored(download_dir: Path) -> None:
    """Refuse to download microdata anywhere git would track it."""
    for name in ("usa_99999.dat.gz", "usa_99999.xml"):
        probe = download_dir / name
        rc = subprocess.run(
            ["git", "check-ignore", "-q", str(probe)], cwd=ROOT
        ).returncode
        if rc != 0:
            sys.exit(f"ERROR: {probe} is not gitignored; refusing to download microdata there.")


def log(msg: str) -> None:
    print(msg, flush=True)


def summary(msg: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as f:
            f.write(msg + "\n")


def wait(client, extract_id: int, timeout_s: int, poll_s: int) -> None:
    start = time.monotonic()
    last = None
    while True:
        status = client.extract_status(extract_id, collection=COLLECTION)
        if status != last or int(time.monotonic() - start) % 600 < poll_s:
            log(f"[{int(time.monotonic() - start):>6}s] extract {extract_id}: {status}")
            last = status
        if status == "completed":
            return
        if status in ("failed", "canceled", "not found"):
            sys.exit(f"ERROR: extract {extract_id} ended with status '{status}'")
        if time.monotonic() - start > timeout_s:
            sys.exit(
                f"ERROR: timed out after {timeout_s}s waiting for extract {extract_id} "
                f"(last status '{status}'). The extract stays on IPUMS; re-run with "
                f"--extract-number {extract_id} to resume without resubmitting."
            )
        time.sleep(poll_s)


def verify_gzip(path: Path) -> int:
    n = 0
    with gzip.open(path, "rb") as f:
        while chunk := f.read(1 << 24):
            n += chunk.count(b"\n")
    return n


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--download-dir", default=str(ROOT / "data"))
    ap.add_argument("--timeout-seconds", type=int, default=5 * 3600 + 1800,
                    help="max wait for IPUMS to build the extract (default 5.5h)")
    ap.add_argument("--poll-seconds", type=int, default=60)
    ap.add_argument("--extract-number", type=int, default=None,
                    help="resume an extract already submitted to IPUMS USA")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the extract definition and exit (no key, no network)")
    args = ap.parse_args()

    extract = build_extract()
    if args.dry_run:
        print(json.dumps(extract.build(), indent=2))
        return

    key = os.environ.get("IPUMS_API_KEY", "").strip()
    if not key:
        sys.exit("ERROR: IPUMS_API_KEY is not set (create one at https://account.ipums.org/api_keys)")

    download_dir = Path(args.download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)
    check_ignored(download_dir)

    from ipumspy import IpumsApiClient
    client = IpumsApiClient(key)

    if args.extract_number:
        extract_id = args.extract_number
        log(f"Resuming extract {extract_id}")
    else:
        client.submit_extract(extract)
        extract_id = extract._id
        log(f"Submitted extract {extract_id} ({len(SAMPLES)} samples, {len(VARIABLES)} variables)")
    summary(f"IPUMS USA extract number: **{extract_id}** "
            f"(resume with `extract_number` input if this job times out)")

    wait(client, extract_id, args.timeout_seconds, args.poll_seconds)

    try:
        info = client.get(
            f"{client.base_url}/extracts/{extract_id}",
            params={"collection": COLLECTION, "version": client.api_version},
        ).json()
        log(f"Reported data file size: {info['downloadLinks']['data']['bytes']:,} bytes")
    except Exception as e:  # informational only
        log(f"(could not read file size: {e})")

    log(f"Downloading to {download_dir} ...")
    client.download_extract(extract_id, collection=COLLECTION, download_dir=download_dir)

    ddis = sorted(download_dir.glob("usa_*.xml"))
    dats = sorted(download_dir.glob("usa_*.dat.gz"))
    if not ddis or not dats:
        sys.exit(f"ERROR: download incomplete: xml={ddis} dat={dats}")
    stem = f"usa_{extract_id:05d}"
    if not (download_dir / f"{stem}.xml").exists() or not (download_dir / f"{stem}.dat.gz").exists():
        sys.exit(f"ERROR: expected {stem}.xml and {stem}.dat.gz in {download_dir}, found {[p.name for p in ddis + dats]}")
    rows = verify_gzip(download_dir / f"{stem}.dat.gz")
    log(f"{stem}.dat.gz is valid gzip, {rows:,} records")
    summary(f"Downloaded {stem}: {rows:,} person records (not committed)")


if __name__ == "__main__":
    main()
