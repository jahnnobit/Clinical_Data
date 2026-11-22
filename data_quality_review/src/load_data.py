"""
load_data.py
------------
Loads the four SDTM datasets (DM, AE, VS, LB) and prints a short data profile.

SDTM (Study Data Tabulation Model) is the CDISC standard for how clinical trial
data is organised for regulatory submission: one dataset ("domain") per topic,
with standard variable names such as USUBJID (unique subject ID).

Design choice: every column is read as TEXT (dtype=str). This keeps the values
exactly as they appear in the file, so later edit checks can see problems such
as "12OO" in a numeric field or a malformed date instead of pandas silently
converting or dropping them. Numeric conversion is done explicitly inside the
checks.

Missing values: the CSVs were exported from R, which writes a missing value as
an unquoted NA (real text values are always in quotes). We verified that the
text "NA" never appears as a genuine quoted value, so both NA and empty cells
are read as missing.

Run from the project root:
    python data_quality_review/src/load_data.py
"""

import re
from pathlib import Path

import pandas as pd

# Project root = the folder above src/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
INJECTED_DIR = PROJECT_ROOT / "data" / "injected"

DOMAINS = ["dm", "ae", "vs", "lb"]

# Key variables we expect to need in the edit checks, per domain
KEY_VARIABLES = {
    "dm": ["USUBJID", "AGE", "SEX", "RFSTDTC", "RFENDTC", "BRTHDTC", "ARM"],
    "ae": ["USUBJID", "AESEQ", "AETERM", "AEDECOD", "AESER", "AEOUT", "AESTDTC", "AEENDTC"],
    "vs": ["USUBJID", "VSTESTCD", "VSSTRESN", "VSSTRESU", "VISITNUM", "VSDTC", "VSTPT"],
    "lb": ["USUBJID", "LBTESTCD", "LBSTRESN", "LBSTRESU", "LBSTNRLO", "LBSTNRHI", "LBNRIND", "VISITNUM", "LBDTC"],
}


def load_dataset(domain, folder=RAW_DIR):
    """Read one domain CSV (e.g. 'dm') as text. NA and empty cells become NaN."""
    path = Path(folder) / f"{domain}.csv"
    return pd.read_csv(
        path,
        dtype=str,               # keep every value as text
        keep_default_na=False,   # switch off pandas' long default list of "missing" words...
        na_values=["", "NA"],    # ...and use only the two markers present in these files
    )


def load_all(folder=RAW_DIR):
    """Return a dict {'dm': DataFrame, 'ae': ..., 'vs': ..., 'lb': ...}."""
    return {d: load_dataset(d, folder) for d in DOMAINS}


# --------------------------------------------------------------------------
# Profiling helpers
# --------------------------------------------------------------------------

# Regular expressions that describe the ISO 8601 shapes we may see in --DTC columns.
# ISO 8601 allows partial dates (e.g. "2014-01" when the day is unknown).
DATE_PATTERNS = [
    ("YYYY-MM-DDThh:mm:ss", r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$"),
    ("YYYY-MM-DDThh:mm",    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$"),
    ("YYYY-MM-DD",          r"^\d{4}-\d{2}-\d{2}$"),
    ("YYYY-MM",             r"^\d{4}-\d{2}$"),
    ("YYYY",                r"^\d{4}$"),
]


def classify_date(value):
    """Return the name of the ISO 8601 pattern a value matches, or 'OTHER'."""
    if pd.isna(value):
        return "(missing)"
    for name, pattern in DATE_PATTERNS:
        if re.match(pattern, value):
            return name
    return "OTHER"


def profile(domain, df):
    """Print a short profile of one dataset."""
    print("=" * 78)
    print(f"{domain.upper()}  -  {len(df):,} rows x {df.shape[1]} columns")
    print("=" * 78)
    print("Columns:", ", ".join(df.columns))

    # Key variables: present or not?
    missing_keys = [v for v in KEY_VARIABLES[domain] if v not in df.columns]
    print("Key variables expected but NOT present:", missing_keys or "none")

    print(f"Distinct subjects (USUBJID): {df['USUBJID'].nunique():,}")

    # Missing values, only for columns that have any
    na = df.isna().sum()
    na = na[na > 0]
    print("\nMissing values (columns with at least one empty cell):")
    if na.empty:
        print("  none")
    else:
        for col, n in na.items():
            print(f"  {col:<10} {n:>7,}  ({n / len(df):.1%})")

    # Date formats in every --DTC column
    print("\nDate formats in --DTC columns:")
    for col in [c for c in df.columns if c.endswith("DTC")]:
        counts = df[col].apply(classify_date).value_counts()
        summary = ", ".join(f"{k}: {v:,}" for k, v in counts.items())
        print(f"  {col:<10} {summary}")

    # Test codes for the findings domains
    if domain in ("vs", "lb"):
        prefix = domain.upper()
        code, unit = f"{prefix}TESTCD", f"{prefix}STRESU"
        print(f"\nDistinct {code} values (with standard units and record counts):")
        grouped = (
            df.groupby(code, dropna=False)
            .agg(n=(code, "size"),
                 units=(unit, lambda s: "/".join(sorted(s.dropna().unique())) or "(none)"))
            .sort_index()
        )
        for testcd, row in grouped.iterrows():
            print(f"  {testcd:<10} n={row['n']:>6,}  unit: {row['units']}")
    print()


def main():
    data = load_all()
    for domain, df in data.items():
        profile(domain, df)


if __name__ == "__main__":
    main()
