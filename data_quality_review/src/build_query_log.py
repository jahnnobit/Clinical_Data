"""
build_query_log.py
------------------
Turns the edit check findings into a query log: output/query_log.xlsx.

A *query* is a question from data management to the trial site about a data
point that failed an edit check. The *query log* tracks every query through
its life cycle:
    Open      -> query sent, waiting for the site
    Answered  -> site has responded, data management must review the answer
    Closed    -> data management accepted the answer (data corrected or confirmed)

Input: the findings on the INJECTED data (output/findings_injected.csv,
produced by edit_checks.py). These contain the 50 injected errors plus the
genuine findings already present in the public data.

One query per problem, not per record:
- X01: one query per subject and visit (one wrong visit date can affect ~30 lab records)
- AE08 / DM01 duplicates: one query per duplicate pair

SIMULATED workflow: real statuses come from site responses. Here they are
assigned at random (fixed seed): about 60% Closed, 25% Answered, 15% Open,
with plausible working-day dates inside a fixed review window. This is clearly
labelled in the output file.

Run from the project root (after edit_checks.py):
    python data_quality_review/src/build_query_log.py
"""

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from build_edit_check_spec import CHECKS as SPEC
from load_data import PROJECT_ROOT

SEED = 2025
rng = np.random.default_rng(SEED)

OUTPUT_DIR = PROJECT_ROOT / "output"
FINDINGS_FILE = OUTPUT_DIR / "findings_injected.csv"
QUERY_LOG_FILE = OUTPUT_DIR / "query_log.xlsx"

# Fixed simulated review window (fixed dates keep the output reproducible)
FIRST_OPEN_DATE = "2025-02-03"     # first day queries can be opened (a Monday)
LAST_OPEN_DATE = "2025-03-31"      # last day queries can be opened
DATA_CUT_DATE = "2025-04-30"       # snapshot date of the log: no date after this

STATUS_SHARES = {"Closed": 0.60, "Answered": 0.25, "Open": 0.15}

COLUMNS = ["Query ID", "Check ID", "Severity", "USUBJID", "Dataset", "Variable", "Visit",
           "Value found", "Query text", "Status", "Date opened", "Date answered",
           "Date closed", "Resolution", "Record(s)", "Origin"]

NOTE = ("NOTE: Status, dates and resolutions are SIMULATED (random, seed "
        f"{SEED}) to demonstrate a query workflow. Findings and query texts are real "
        "output of the edit checks. Portfolio project on public CDISC pilot data, not a real trial.")


# --------------------------------------------------------------------------
# 1. Findings -> queries
# --------------------------------------------------------------------------

def group_findings(findings):
    """Combine findings that describe the same problem into one query."""
    findings = findings.fillna("")
    group_key = findings["record_key"].copy()             # default: one query per record
    is_x01 = findings["check_id"].eq("X01")
    group_key[is_x01] = "VISIT=" + findings.loc[is_x01, "visit"]
    is_pair = findings["check_id"].isin(["AE08", "DM01"])
    group_key[is_pair] = "VALUE=" + findings.loc[is_pair, "value"]
    findings["group_key"] = group_key

    groups = findings.groupby(["check_id", "dataset", "usubjid", "group_key"], sort=False)
    queries = groups.agg(
        variable=("variable", "first"),
        visit=("visit", "first"),
        value=("value", "first"),
        records=("record_key", lambda s: ", ".join(s)),
        n_records=("record_key", "size"),
        origin=("classification", "first"),
    ).reset_index()
    many = queries["n_records"] > 1
    queries.loc[many, "value"] = (queries.loc[many, "value"] + " (" +
                                  queries.loc[many, "n_records"].astype(str) + " records)")
    return queries


def add_spec_info(queries):
    """Add severity and query text from the edit check specification."""
    spec = pd.DataFrame(SPEC).set_index("Check ID")
    queries["severity"] = queries["check_id"].map(spec["Severity"])
    queries["query_text"] = queries["check_id"].map(spec["Query text"])
    # Order queries like the specification (DM01 first ... X01 last), then by subject
    order = {cid: i for i, cid in enumerate(spec.index)}
    queries = queries.sort_values(["check_id", "usubjid"], key=lambda s: s.map(order) if s.name == "check_id" else s)
    queries = queries.reset_index(drop=True)
    queries.insert(0, "query_id", [f"Q{i + 1:04d}" for i in range(len(queries))])
    return queries


# --------------------------------------------------------------------------
# 2. Simulated workflow
# --------------------------------------------------------------------------

def simulate_status(queries):
    """Assign Closed / Answered / Open in the target proportions, in random order."""
    n = len(queries)
    n_closed = round(n * STATUS_SHARES["Closed"])
    n_answered = round(n * STATUS_SHARES["Answered"])
    statuses = ["Closed"] * n_closed + ["Answered"] * n_answered + ["Open"] * (n - n_closed - n_answered)
    queries["status"] = rng.permutation(statuses)
    return queries


def working_days_after(date, low, high):
    """A date between low and high working days (Mon-Fri) after date."""
    return np.busday_offset(date, int(rng.integers(low, high + 1)), roll="forward")


def simulate_dates(queries):
    """Plausible dates: opened in the review window, answered 1-15 and closed 1-10 working days later."""
    open_days = np.arange(np.datetime64(FIRST_OPEN_DATE), np.datetime64(LAST_OPEN_DATE) + np.timedelta64(1, "D"))
    open_days = open_days[np.is_busday(open_days)]
    cut = np.datetime64(DATA_CUT_DATE)

    opened, answered, closed = [], [], []
    for status in queries["status"]:
        d_open = rng.choice(open_days)
        d_answer = working_days_after(d_open, 1, 15) if status in ("Answered", "Closed") else None
        d_close = working_days_after(d_answer, 1, 10) if status == "Closed" else None
        # With these windows no date can pass the data cut; checked to be safe
        assert all(d is None or d <= cut for d in (d_answer, d_close))
        opened.append(d_open)
        answered.append(d_answer)
        closed.append(d_close)

    to_date = lambda values: pd.to_datetime(pd.Series(values, dtype="object")).dt.date
    queries["date_opened"] = to_date(opened)
    queries["date_answered"] = to_date(answered)
    queries["date_closed"] = to_date(closed)
    return queries


def simulate_resolution(queries):
    """
    Resolution text for closed queries. Injected errors are real mistakes, so the
    simulated site corrects them. Findings that also exist in the raw public data
    are treated as confirmed by the site.
    """
    resolution = np.where(queries["origin"] == "injected error",
                          "Value corrected by site", "Confirmed correct by site")
    queries["resolution"] = np.where(queries["status"] == "Closed", resolution, "")
    return queries


# --------------------------------------------------------------------------
# 3. Excel output
# --------------------------------------------------------------------------

def write_excel(queries, path=QUERY_LOG_FILE):
    table = pd.DataFrame({
        "Query ID": queries["query_id"],
        "Check ID": queries["check_id"],
        "Severity": queries["severity"],
        "USUBJID": queries["usubjid"].replace("", "(missing)"),
        "Dataset": queries["dataset"],
        "Variable": queries["variable"],
        "Visit": queries["visit"],
        "Value found": queries["value"],
        "Query text": queries["query_text"],
        "Status": queries["status"],
        "Date opened": queries["date_opened"],
        "Date answered": queries["date_answered"],
        "Date closed": queries["date_closed"],
        "Resolution": queries["resolution"],
        "Record(s)": queries["records"],
        "Origin": queries["origin"].map({"injected error": "Injected error",
                                         "genuine (also in raw data)": "Genuine (raw data)"}),
    }, columns=COLUMNS)

    # Row 1 = simulation note, row 2 empty, row 3 = header, data from row 4
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        table.to_excel(writer, sheet_name="Query Log", index=False, startrow=2)
        about = pd.DataFrame({"Item": [
            "Purpose", "Source of findings", "Simulated", "Status shares (target)",
            "Review window (simulated)", "Data cut date (simulated)", "Origin column", "Record(s) column"],
            "Description": [
            "Query log for the edit checks in docs/Edit_Check_Specification.xlsx.",
            "Edit checks run on the injected data (data/injected/), see output/findings_injected.csv.",
            "Status, all dates and resolution texts are randomly simulated (seed "
            f"{SEED}). They do not come from a real site.",
            "Closed 60%, Answered 25%, Open 15%.",
            f"Queries opened on working days {FIRST_OPEN_DATE} to {LAST_OPEN_DATE}.",
            f"{DATA_CUT_DATE}. Answered 1-15 and closed 1-10 working days after the previous step.",
            "Injected error = deliberately added (see data/injected/answer_key.csv). "
            "Genuine (raw data) = finding also present in the original public data.",
            "The records behind each query. X01 is one query per visit; duplicates are one query per pair."]})
        about.to_excel(writer, sheet_name="About", index=False)

    # Formatting
    wb = load_workbook(path)
    ws = wb["Query Log"]
    ws["A1"] = NOTE
    ws["A1"].font = Font(bold=True, color="9C0006")
    ws["A1"].fill = PatternFill("solid", fgColor="FFC7CE")
    for cell in ws[3]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    widths = {"A": 9, "B": 8, "C": 9, "D": 13, "E": 8, "F": 24, "G": 18, "H": 40, "I": 60,
              "J": 10, "K": 12, "L": 13, "M": 12, "N": 26, "O": 30, "P": 18}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    for col in ("K", "L", "M"):
        for cell in ws[col][3:]:
            cell.number_format = "yyyy-mm-dd"
    ws.freeze_panes = "B4"
    ws.auto_filter.ref = f"A3:P{ws.max_row}"
    about_ws = wb["About"]
    about_ws.column_dimensions["A"].width = 26
    about_ws.column_dimensions["B"].width = 110
    for cell in about_ws[1]:
        cell.font = Font(bold=True)
    wb.save(path)
    return table


def main():
    findings = pd.read_csv(FINDINGS_FILE, dtype=str, keep_default_na=False)
    queries = add_spec_info(group_findings(findings))
    queries = simulate_resolution(simulate_dates(simulate_status(queries)))
    table = write_excel(queries)

    print(f"{len(findings)} findings -> {len(table)} queries  ({QUERY_LOG_FILE.relative_to(PROJECT_ROOT)})")
    print("\nStatus (simulated):")
    print(table["Status"].value_counts().to_string())
    print("\nOrigin:")
    print(table["Origin"].value_counts().to_string())
    print("\nQueries per check:")
    print(table["Check ID"].value_counts(sort=False).to_string())


if __name__ == "__main__":
    main()
