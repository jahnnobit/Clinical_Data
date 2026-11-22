"""
run_all.py
----------
Runs both parts of the Clinical Trial Oversight Toolkit, in order:

Part A  portfolio_monitor/    portfolio and compliance monitoring of live
                              ClinicalTrials.gov data (EU Phase 3 oncology)
Part B  data_quality_review/  study-level data quality review of CDISC SDTM data

Each part runs in its own Python process, so their modules stay separate.
Part A works on the saved snapshot in portfolio_monitor/data/raw/; it does not
download new data. To take a new snapshot, run:
    python portfolio_monitor/src/fetch_studies.py

Run from this folder:
    python run_all.py
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PARTS = [
    ("Part A: Data profile", ROOT / "portfolio_monitor" / "src" / "registry_data.py"),
    ("Part A: Study and site tables", ROOT / "portfolio_monitor" / "src" / "build_tables.py"),
    ("Part B: Data quality review", ROOT / "data_quality_review" / "src" / "run_all.py"),
]


def main():
    for name, script in PARTS:
        print(f"\n{'#' * 78}\n# {name}\n{'#' * 78}")
        subprocess.run([sys.executable, str(script)], check=True)
    print("\nAll parts finished. Start the dashboard with: python dashboard/app.py")


if __name__ == "__main__":
    main()
