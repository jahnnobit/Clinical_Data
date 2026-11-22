"""
edit_checks.py
--------------
The 20 edit checks defined in docs/Edit_Check_Specification.xlsx.

Every check is one function. It receives DataFrames (all values as text, see
load_data.py) and returns the FAILING records in one standard format:

    check_id | dataset | usubjid | record_key | visit | variable | value

record_key identifies the exact record (SUBJID in DM, AESEQ / VSSEQ / LBSEQ in
the other domains), so every finding can be traced back to one row.

Running this file:
1. runs all checks on the RAW data   -> genuine findings in the public data
2. runs all checks on the INJECTED data and compares the findings with the
   answer key -> catch rate per check and overall, plus false positives
3. saves output/check_results_summary.csv and the findings lists

Run from the project root:
    python data_quality_review/src/edit_checks.py
"""

import re
from datetime import datetime

import pandas as pd

from build_edit_check_spec import CHECKS as SPEC
from load_data import INJECTED_DIR, PROJECT_ROOT, load_all

OUTPUT_DIR = PROJECT_ROOT / "output"

RECORD_KEY = {"dm": "SUBJID", "ae": "AESEQ", "vs": "VSSEQ", "lb": "LBSEQ"}
FINDING_COLUMNS = ["check_id", "dataset", "usubjid", "record_key", "visit", "variable", "value"]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def num(series):
    """Convert text to numbers. Anything that is not a number becomes NaN."""
    return pd.to_numeric(series, errors="coerce")


def show(value):
    """Text used in the 'value' column; missing values are written out."""
    return "(missing)" if pd.isna(value) else str(value)


def make_findings(df, mask, check_id, domain, variables):
    """Turn the rows where mask is True into findings in the standard format."""
    rows = df[mask]
    if len(variables) == 1:
        values = rows[variables[0]].map(show)
    else:
        values = rows[variables].apply(
            lambda r: "; ".join(f"{v}={show(r[v])}" for v in variables), axis=1)
    key = RECORD_KEY[domain]
    return pd.DataFrame({
        "check_id": check_id,
        "dataset": domain.upper(),
        "usubjid": rows["USUBJID"].map(lambda u: "" if pd.isna(u) else u),
        "record_key": key + "=" + rows[key].astype(str),
        "visit": rows["VISIT"].fillna("") if "VISIT" in rows else "",
        "variable": ", ".join(variables),
        "value": values,
    }, columns=FINDING_COLUMNS)


def date_before(a, b):
    """
    True where date a is before date b. Both must be present.
    ISO 8601 dates can be partial ('2012-02', '2003'), so the dates are compared
    on the precision they share: '2012-02' vs '2012-03-15' compares '2012-02'
    with '2012-03'. Time parts are ignored (only the first 10 characters count).
    """
    result = []
    for x, y in zip(a, b):
        if pd.isna(x) or pd.isna(y):
            result.append(False)
            continue
        x, y = str(x)[:10], str(y)[:10]
        n = min(len(x), len(y))
        result.append(x[:n] < y[:n])
    return pd.Series(result, index=a.index)


ISO_PATTERN = re.compile(
    r"^(\d{4})"                       # YYYY
    r"(?:-(\d{2})"                    # -MM
    r"(?:-(\d{2})"                    # -DD
    r"(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?"   # Thh:mm or Thh:mm:ss
    r")?)?$"
)


def is_valid_iso_date(value):
    """True if value is a complete or partial ISO 8601 date that exists in the calendar."""
    match = ISO_PATTERN.match(str(value))
    if not match:
        return False
    year, month, day, hour, minute, second = match.groups()
    try:
        datetime(int(year), int(month or 1), int(day or 1),
                 int(hour or 0), int(minute or 0), int(second or 0))
    except ValueError:            # e.g. month 13, 30 February, hour 25
        return False
    return True


# --------------------------------------------------------------------------
# DM checks
# --------------------------------------------------------------------------

def dm01(dm):
    """USUBJID missing or duplicated."""
    bad = dm["USUBJID"].isna() | (dm["USUBJID"].duplicated(keep=False) & dm["USUBJID"].notna())
    return make_findings(dm, bad, "DM01", "dm", ["USUBJID"])


def dm02(dm):
    """AGE missing, not numeric, or outside 18-100 (assumed plausibility limits)."""
    age = num(dm["AGE"])
    bad = age.isna() | (age < 18) | (age > 100)
    return make_findings(dm, bad, "DM02", "dm", ["AGE"])


def dm03(dm):
    """SEX not in M, F, U."""
    bad = ~dm["SEX"].isin(["M", "F", "U"])
    return make_findings(dm, bad, "DM03", "dm", ["SEX"])


def dm04(dm):
    """RFSTDTC after RFENDTC (missing dates are not compared)."""
    bad = date_before(dm["RFENDTC"], dm["RFSTDTC"])
    return make_findings(dm, bad, "DM04", "dm", ["RFSTDTC", "RFENDTC"])


DM_DATE_VARIABLES = ["RFSTDTC", "RFENDTC", "RFXSTDTC", "RFXENDTC", "RFICDTC",
                     "RFPENDTC", "DTHDTC", "BRTHDTC", "DMDTC"]


def dm05(dm):
    """Any DM date that is present but not a valid ISO 8601 date. One finding per bad date."""
    parts = []
    for var in DM_DATE_VARIABLES:
        bad = dm[var].notna() & ~dm[var].map(is_valid_iso_date)
        parts.append(make_findings(dm, bad, "DM05", "dm", [var]))
    return pd.concat(parts, ignore_index=True)


# --------------------------------------------------------------------------
# AE checks
# --------------------------------------------------------------------------

def ae01(ae, dm):
    """AE subject not found in DM."""
    bad = ae["USUBJID"].isna() | ~ae["USUBJID"].isin(dm["USUBJID"].dropna())
    return make_findings(ae, bad, "AE01", "ae", ["USUBJID"])


def ae02(ae):
    """AE end date before start date."""
    bad = date_before(ae["AEENDTC"], ae["AESTDTC"])
    return make_findings(ae, bad, "AE02", "ae", ["AESTDTC", "AEENDTC"])


def ae03(ae):
    """AETERM missing or blank."""
    bad = ae["AETERM"].isna() | ae["AETERM"].str.strip().eq("")
    return make_findings(ae, bad, "AE03", "ae", ["AETERM"])


def ae04(ae):
    """AETERM filled but AEDECOD missing (AE not coded)."""
    bad = ae["AETERM"].notna() & ae["AEDECOD"].isna()
    return make_findings(ae, bad, "AE04", "ae", ["AETERM", "AEDECOD"])


def ae05(ae):
    """AESER not Y or N."""
    bad = ~ae["AESER"].isin(["Y", "N"])
    return make_findings(ae, bad, "AE05", "ae", ["AESER"])


def ae06(ae):
    """Serious AE without outcome."""
    bad = ae["AESER"].eq("Y") & ae["AEOUT"].isna()
    return make_findings(ae, bad, "AE06", "ae", ["AESER", "AEOUT"])


def ae07(ae, dm):
    """AE start before the subject's reference start date (review flag)."""
    ref = dm.dropna(subset=["USUBJID"]).drop_duplicates("USUBJID").set_index("USUBJID")["RFSTDTC"]
    ae = ae.assign(RFSTDTC=ae["USUBJID"].map(ref))
    bad = date_before(ae["AESTDTC"], ae["RFSTDTC"])
    return make_findings(ae, bad, "AE07", "ae", ["AESTDTC", "RFSTDTC"])


def ae08(ae):
    """Duplicate AE records: identical on all variables except AESEQ and AESPID."""
    compare = [c for c in ae.columns if c not in ("AESEQ", "AESPID")]
    bad = ae.duplicated(subset=compare, keep=False)
    return make_findings(ae, bad, "AE08", "ae", ["AETERM", "AESTDTC"])


# --------------------------------------------------------------------------
# VS checks
# --------------------------------------------------------------------------

def _vs_out_of_range(vs, testcd, low, high):
    """Records of one test with a result present that is non-numeric or outside low-high."""
    value = num(vs["VSSTRESN"])
    present = vs["VSSTRESC"].notna() | vs["VSSTRESN"].notna()
    return vs["VSTESTCD"].eq(testcd) & present & (value.isna() | (value < low) | (value > high))


def vs01(vs):
    """Systolic BP outside 60-250 mmHg (assumed plausibility limits)."""
    bad = _vs_out_of_range(vs, "SYSBP", 60, 250)
    return make_findings(vs, bad, "VS01", "vs", ["VSTESTCD", "VSSTRESN"])


def vs02(vs):
    """Diastolic BP higher than systolic BP at the same subject/visit/date/time point."""
    key = ["USUBJID", "VISITNUM", "VSDTC", "VSTPTNUM"]
    sys_bp = vs[vs["VSTESTCD"].eq("SYSBP")][key + ["VSSTRESN"]].rename(columns={"VSSTRESN": "SYS"})
    sys_bp = sys_bp.drop_duplicates(subset=key)   # one systolic value per measurement
    dia = vs[vs["VSTESTCD"].eq("DIABP")].reset_index().merge(sys_bp, on=key, how="left")
    bad_rows = dia.loc[num(dia["VSSTRESN"]) > num(dia["SYS"]), "index"]
    bad = vs.index.isin(bad_rows)
    findings = make_findings(vs, bad, "VS02", "vs", ["VSTESTCD", "VSSTRESN"])
    # Show both values in the finding
    sys_lookup = dia.set_index("index")["SYS"]
    findings["value"] = [f"DIABP={vs.at[i, 'VSSTRESN']}; SYSBP={sys_lookup[i]}" for i in vs.index[bad]]
    return findings


def vs03(vs):
    """Pulse outside 30-200 /min or temperature outside 34-42 C (assumed plausibility limits)."""
    bad = _vs_out_of_range(vs, "PULSE", 30, 200) | _vs_out_of_range(vs, "TEMP", 34, 42)
    return make_findings(vs, bad, "VS03", "vs", ["VSTESTCD", "VSSTRESN"])


def vs04(vs):
    """Result present but unit missing (original or standard)."""
    bad = ((vs["VSORRES"].notna() & vs["VSORRESU"].isna())
           | (vs["VSSTRESC"].notna() & vs["VSSTRESU"].isna()))
    return make_findings(vs, bad, "VS04", "vs", ["VSTESTCD", "VSORRESU", "VSSTRESU"])


# --------------------------------------------------------------------------
# LB checks
# --------------------------------------------------------------------------

def lb01(lb):
    """Result outside the original-unit normal range but not flagged LOW/HIGH in LBNRIND."""
    result, low, high = num(lb["LBORRES"]), num(lb["LBORNRLO"]), num(lb["LBORNRHI"])
    outside = (result < low) | (result > high)       # False when any value is not numeric
    bad = outside & ~lb["LBNRIND"].isin(["LOW", "HIGH"])
    return make_findings(lb, bad, "LB01", "lb",
                         ["LBTESTCD", "LBORRES", "LBORNRLO", "LBORNRHI", "LBNRIND"])


def lb02(lb):
    """Result present but standard unit missing, for tests that are reported with a unit."""
    tests_with_unit = lb.loc[lb["LBSTRESU"].notna(), "LBTESTCD"].unique()
    bad = lb["LBSTRESC"].notna() & lb["LBSTRESU"].isna() & lb["LBTESTCD"].isin(tests_with_unit)
    return make_findings(lb, bad, "LB02", "lb", ["LBTESTCD", "LBSTRESC", "LBSTRESU"])


# --------------------------------------------------------------------------
# Cross-domain check
# --------------------------------------------------------------------------

def x01(df, domain):
    """
    Visit dates not chronological by VISITNUM within a subject.
    A record is flagged when its date is earlier than the latest date recorded
    at any lower-numbered visit of the same subject.
    """
    dtc = f"{domain.upper()}DTC"
    t = pd.DataFrame({
        "USUBJID": df["USUBJID"],
        "vn": num(df["VISITNUM"]),
        "date": pd.to_datetime(df[dtc].str[:10], errors="coerce"),
    })
    # Latest date of each visit, then the latest date of all EARLIER visits
    visit_max = t.groupby(["USUBJID", "vn"])["date"].max().reset_index().sort_values(["USUBJID", "vn"])
    visit_max["earlier_max"] = visit_max.groupby("USUBJID")["date"].transform(
        lambda s: s.cummax().shift())
    t = t.reset_index().merge(visit_max[["USUBJID", "vn", "earlier_max"]],
                              on=["USUBJID", "vn"], how="left").set_index("index")
    bad = (t["date"] < t["earlier_max"]).reindex(df.index, fill_value=False)
    return make_findings(df, bad, "X01", domain, ["VISITNUM", dtc])


# --------------------------------------------------------------------------
# Running all checks
# --------------------------------------------------------------------------

def run_all_checks(data):
    """Run every check on a dict of DataFrames. Returns one DataFrame of findings."""
    dm, ae, vs, lb = data["dm"], data["ae"], data["vs"], data["lb"]
    results = [
        dm01(dm), dm02(dm), dm03(dm), dm04(dm), dm05(dm),
        ae01(ae, dm), ae02(ae), ae03(ae), ae04(ae), ae05(ae), ae06(ae), ae07(ae, dm), ae08(ae),
        vs01(vs), vs02(vs), vs03(vs), vs04(vs),
        lb01(lb), lb02(lb),
        x01(vs, "vs"), x01(lb, "lb"),
    ]
    return pd.concat(results, ignore_index=True)


def finding_ids(findings):
    """Set of (check_id, dataset, usubjid, record_key) - the identity of a finding."""
    return set(zip(findings["check_id"], findings["dataset"], findings["usubjid"], findings["record_key"]))


def compare_with_answer_key(raw_findings, inj_findings, key):
    """
    Classify every finding on the injected data and compute the catch rate.
    - caught:      the injected error was flagged by its expected check
    - genuine:     the same finding also exists in the raw data (real issue in the public data)
    - false positive: neither genuine nor an expected injected error
    """
    key = key.fillna("")
    found = finding_ids(inj_findings)
    key["caught"] = [
        (c, d, u, r) in found or (p != "" and (c, d, u, p) in found)
        for c, d, u, r, p in zip(key["expected_check_id"], key["dataset"], key["usubjid"],
                                 key["record_key"], key["partner_record_key"])
    ]

    expected = set()
    for _, e in key.iterrows():
        expected.add((e["expected_check_id"], e["dataset"], e["usubjid"], e["record_key"]))
        if e["partner_record_key"]:
            expected.add((e["expected_check_id"], e["dataset"], e["usubjid"], e["partner_record_key"]))
    genuine = finding_ids(raw_findings)

    def classify(row):
        ident = (row["check_id"], row["dataset"], row["usubjid"], row["record_key"])
        if ident in expected:
            return "injected error"
        if ident in genuine:
            return "genuine (also in raw data)"
        return "false positive"

    inj_findings = inj_findings.copy()
    inj_findings["classification"] = inj_findings.apply(classify, axis=1)
    return key, inj_findings


def build_summary(raw_findings, inj_findings, key):
    """One row per check plus a TOTAL row."""
    spec = pd.DataFrame(SPEC)[["Check ID", "Dataset", "Severity", "Rule"]]
    rows = []
    for _, s in spec.iterrows():
        cid = s["Check ID"]
        k = key[key["expected_check_id"] == cid]
        f = inj_findings[inj_findings["check_id"] == cid]
        rows.append({
            "check_id": cid,
            "dataset": s["Dataset"],
            "severity": s["Severity"],
            "rule": s["Rule"],
            "findings_raw_data": int((raw_findings["check_id"] == cid).sum()),
            "errors_injected": len(k),
            "errors_caught": int(k["caught"].sum()),
            "catch_rate": round(k["caught"].mean(), 3) if len(k) else None,
            "findings_injected_data": len(f),
            "false_positives": int((f["classification"] == "false positive").sum()),
        })
    summary = pd.DataFrame(rows)
    total = {
        "check_id": "TOTAL", "dataset": "", "severity": "", "rule": "",
        "findings_raw_data": summary["findings_raw_data"].sum(),
        "errors_injected": summary["errors_injected"].sum(),
        "errors_caught": summary["errors_caught"].sum(),
        "catch_rate": round(summary["errors_caught"].sum() / summary["errors_injected"].sum(), 3),
        "findings_injected_data": summary["findings_injected_data"].sum(),
        "false_positives": summary["false_positives"].sum(),
    }
    return pd.concat([summary, pd.DataFrame([total])], ignore_index=True)


def main():
    raw_findings = run_all_checks(load_all())
    inj_findings = run_all_checks(load_all(INJECTED_DIR))
    key = pd.read_csv(INJECTED_DIR / "answer_key.csv", dtype=str, keep_default_na=False)
    key, inj_findings = compare_with_answer_key(raw_findings, inj_findings, key)
    summary = build_summary(raw_findings, inj_findings, key)

    OUTPUT_DIR.mkdir(exist_ok=True)
    summary.to_csv(OUTPUT_DIR / "check_results_summary.csv", index=False)
    raw_findings.to_csv(OUTPUT_DIR / "findings_raw.csv", index=False)
    inj_findings.to_csv(OUTPUT_DIR / "findings_injected.csv", index=False)

    print("=== 1. Genuine findings in the RAW public data ===")
    print(raw_findings.groupby(["check_id", "dataset"]).size().to_string() if len(raw_findings) else "none")
    print("\n=== 2. Injected data vs answer key ===")
    cols = ["check_id", "errors_injected", "errors_caught", "catch_rate",
            "findings_injected_data", "false_positives"]
    print(summary[cols].to_string(index=False))
    missed = key[~key["caught"]]
    print("\nMissed injected errors:", "none" if missed.empty else "")
    if not missed.empty:
        print(missed[["error_id", "expected_check_id", "usubjid", "record_key", "description"]].to_string(index=False))
    fp = inj_findings[inj_findings["classification"] == "false positive"]
    print("\nFalse positives:", "none" if fp.empty else "")
    if not fp.empty:
        print(fp.to_string(index=False))
    print(f"\nSaved {OUTPUT_DIR.name}/check_results_summary.csv, findings_raw.csv, findings_injected.csv")


if __name__ == "__main__":
    main()
