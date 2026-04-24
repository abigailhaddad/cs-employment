"""Run the full pipeline: extract -> analysis -> export_web_data."""

import subprocess
import sys

SCRIPTS = ["extract.py", "analysis.py", "export_web_data.py"]


def main():
    for script in SCRIPTS:
        print(f"\n{'='*60}\nRunning {script}\n{'='*60}")
        r = subprocess.run([sys.executable, script])
        if r.returncode != 0:
            print(f"\n{script} failed with code {r.returncode}")
            sys.exit(r.returncode)
    print("\nAll done.")


if __name__ == "__main__":
    main()
