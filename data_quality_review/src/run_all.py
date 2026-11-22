"""
run_all.py
----------
Runs the whole pipeline end to end, in order:

1. build_edit_check_spec  -> docs/Edit_Check_Specification.xlsx
2. inject_errors          -> data/injected/*.csv + answer_key.csv
3. edit_checks            -> output/check_results_summary.csv, findings_*.csv
4. build_query_log        -> output/query_log.xlsx

The raw data in data/raw/ is only read, never changed. Every step uses fixed
random seeds, so running this again gives the same results.

Run from the project root:
    python data_quality_review/src/run_all.py
Then start the dashboard:
    python dashboard/app.py
"""

import build_edit_check_spec
import build_query_log
import edit_checks
import inject_errors

STEPS = [
    ("Edit check specification", build_edit_check_spec.write_spec),
    ("Error injection", inject_errors.main),
    ("Edit checks", edit_checks.main),
    ("Query log", build_query_log.main),
]


def main():
    for number, (name, step) in enumerate(STEPS, start=1):
        print(f"\n{'=' * 78}\nStep {number}/{len(STEPS)}: {name}\n{'=' * 78}")
        step()
    print("\nPipeline finished. Start the dashboard with: python dashboard/app.py")


if __name__ == "__main__":
    main()
