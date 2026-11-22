"""
inject_errors.py
----------------
Creates a copy of the raw SDTM data with deliberately injected errors, plus an
answer key that lists every error. The edit checks (Stage 4) are then run on
this copy, and their findings are compared with the answer key to measure the
catch rate: how many of the known errors the checks actually find.

Rules followed:
- The raw files in data/raw/ are only READ. Output goes to data/injected/.
- A fixed random seed makes the result identical on every run.
- 50 errors, at least 2 per edit check.
- Errors are only placed on records that are clean for that check in the raw
  data, and no record receives more than one error. This keeps the catch-rate
  measurement fair (a genuine finding is never counted as a caught injection).
- Record identifiers (SUBJID in DM, AESEQ / VSSEQ / LBSEQ) are never changed,
  so every error can be traced back to its record.

Run from the project root:
    python data_quality_review/src/inject_errors.py
"""

import numpy as np
import pandas as pd

from load_data import INJECTED_DIR, load_all

SEED = 42
rng = np.random.default_rng(SEED)

answer_key = []   # one dict per injected error
used = {"dm": set(), "ae": set(), "vs": set(), "lb": set()}   # row indexes already changed


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def pick(domain, df, mask, n):
    """Randomly pick n row indexes where mask is True and the row is not used yet."""
    eligible = [i for i in df.index[mask] if i not in used[domain]]
    chosen = sorted(rng.choice(eligible, size=n, replace=False).tolist())
    used[domain].update(chosen)
    return chosen


RECORD_KEY = {"dm": "SUBJID", "ae": "AESEQ", "vs": "VSSEQ", "lb": "LBSEQ"}


def log(domain, df, i, variable, original, injected, check_id, description, partner=""):
    """Add one injected error to the answer key."""
    key_col = RECORD_KEY[domain]
    answer_key.append({
        "error_id": f"E{len(answer_key) + 1:03d}",
        "dataset": domain.upper(),
        "usubjid": df.at[i, "USUBJID"],            # value as it is in the injected file
        "record_key": f"{key_col}={df.at[i, key_col]}",
        "variable": variable,
        "original_value": original,
        "injected_value": injected,
        "expected_check_id": check_id,
        "description": description,
        "partner_record_key": partner,             # second record of a duplicate pair, if any
    })


def set_value(domain, df, i, variable, new_value, check_id, description):
    """Change one cell and log it."""
    original = df.at[i, variable]
    df.at[i, variable] = new_value
    log(domain, df, i, variable, original, new_value, check_id, description)


def minus_one_year(date_text):
    """'2014-07-02' -> '2013-07-02' (keeps any time part). Simulates a year typo."""
    return f"{int(date_text[:4]) - 1}{date_text[4:]}"


def full_date(series):
    """True where the value starts with a complete YYYY-MM-DD date (not Feb 29)."""
    s = series.fillna("")
    return s.str.match(r"^\d{4}-\d{2}-\d{2}") & ~s.str[5:10].eq("02-29")


def num(series):
    return pd.to_numeric(series, errors="coerce")


# --------------------------------------------------------------------------
# DM - Demographics (12 errors)
# --------------------------------------------------------------------------

def inject_dm(dm):
    # Screen failures have no AE/VS/LB records (verified in Stage 1), so changing
    # their USUBJID does not create side effects in other domains.
    screen_fail = dm["ARM"].eq("Screen Failure")

    # DM01 - missing subject ID
    for i in pick("dm", dm, screen_fail, 1):
        set_value("dm", dm, i, "USUBJID", np.nan, "DM01", "Subject ID deleted")

    # DM01 - duplicated subject: the same demographics row entered twice
    for i in pick("dm", dm, screen_fail, 1):
        dm.loc[len(dm)] = dm.loc[i].copy()     # append an exact copy at the end
        used["dm"].add(len(dm) - 1)
        log("dm", dm, i, "(whole record)", "", f"copy of SUBJID={dm.at[i, 'SUBJID']}", "DM01",
            "Demographics row entered twice (duplicate USUBJID)")

    # DM02 - age missing / implausible typing error
    i, j = pick("dm", dm, dm["AGE"].notna(), 2)
    set_value("dm", dm, i, "AGE", np.nan, "DM02", "Age deleted")
    set_value("dm", dm, j, "AGE", dm.at[j, "AGE"] + "0", "DM02", "Extra digit typed in age")

    # DM03 - sex not in controlled terminology
    i, j = pick("dm", dm, dm["SEX"].eq("F"), 2)
    set_value("dm", dm, i, "SEX", "Female", "DM03", "Sex written as free text")
    set_value("dm", dm, j, "SEX", "f", "DM03", "Sex entered in lower case")

    # DM04 - reference end date before start date (year typo in RFENDTC).
    # RFENDTC is used by no other check, so this has no side effects.
    eligible = (full_date(dm["RFENDTC"]) & dm["RFSTDTC"].notna()
                & (dm["RFENDTC"].fillna("").apply(lambda d: minus_one_year(d) if d else "")
                   < dm["RFSTDTC"].fillna("")))
    for i in pick("dm", dm, eligible, 2):
        set_value("dm", dm, i, "RFENDTC", minus_one_year(dm.at[i, "RFENDTC"]), "DM04",
                  "Year typo in reference end date (one year too early)")

    # DM05 - invalid dates (dates not used by any other check)
    i, j, k = pick("dm", dm, full_date(dm["BRTHDTC"]) & full_date(dm["DMDTC"]), 3)
    bad = dm.at[i, "BRTHDTC"][:5] + "13" + dm.at[i, "BRTHDTC"][7:]
    set_value("dm", dm, i, "BRTHDTC", bad, "DM05", "Invalid month (13) in birth date")
    d = dm.at[j, "DMDTC"]
    set_value("dm", dm, j, "DMDTC", f"{d[8:10]}/{d[5:7]}/{d[:4]}", "DM05",
              "Date entered as DD/MM/YYYY instead of ISO 8601")
    d = dm.at[k, "DMDTC"]
    set_value("dm", dm, k, "DMDTC", d[:5] + "02-30", "DM05", "Non-existent calendar date (30 February)")
    return dm


# --------------------------------------------------------------------------
# AE - Adverse events (19 errors)
# --------------------------------------------------------------------------

def inject_ae(ae, dm):
    # Each AE record's reference start date, looked up from DM by subject
    rfstdtc = ae["USUBJID"].map(dm.dropna(subset=["USUBJID"])
                                .drop_duplicates("USUBJID").set_index("USUBJID")["RFSTDTC"])
    both_full = full_date(ae["AESTDTC"]) & full_date(ae["AEENDTC"])
    # Records that are NOT a genuine AE07 finding in the raw data (start on/after RFSTDTC)
    after_start = full_date(ae["AESTDTC"]) & rfstdtc.notna() & (ae["AESTDTC"] >= rfstdtc.fillna(""))
    # Records that are part of a genuine duplicate pair in the raw data
    dup_cols = [c for c in ae.columns if c not in ("AESEQ", "AESPID")]
    genuine_dup = ae.duplicated(dup_cols, keep=False)

    # AE01 - subject ID not in DM
    i, j, k = pick("ae", ae, ae["USUBJID"].notna(), 3)
    set_value("ae", ae, i, "USUBJID", np.nan, "AE01", "Subject ID deleted on AE record")
    u = ae.at[j, "USUBJID"]
    set_value("ae", ae, j, "USUBJID", u[:-4] + "9" + u[-3:], "AE01", "Typing error in subject number")
    u = ae.at[k, "USUBJID"]
    set_value("ae", ae, k, "USUBJID", u.replace("-", "", 1), "AE01", "Separator missing in subject ID")

    # AE02 - end date before start date
    i, j = pick("ae", ae, both_full & after_start & (ae["AEENDTC"] > ae["AESTDTC"]), 2)
    for idx in (i, j):
        start, end = ae.at[idx, "AESTDTC"], ae.at[idx, "AEENDTC"]
        ae.at[idx, "AESTDTC"], ae.at[idx, "AEENDTC"] = end, start
        log("ae", ae, idx, "AESTDTC, AEENDTC", f"{start} / {end}", f"{end} / {start}", "AE02",
            "Start and end dates swapped")
    eligible = both_full & after_start & (ae["AEENDTC"].apply(
        lambda d: minus_one_year(d) if isinstance(d, str) else "") < ae["AESTDTC"].fillna(""))
    for i in pick("ae", ae, eligible, 1):
        set_value("ae", ae, i, "AEENDTC", minus_one_year(ae.at[i, "AEENDTC"]), "AE02",
                  "Year typo in AE end date (one year too early)")

    # AE03 - AE term missing
    for i in pick("ae", ae, ae["AETERM"].notna(), 2):
        set_value("ae", ae, i, "AETERM", np.nan, "AE03", "Reported AE term deleted")

    # AE04 - AE not coded (dictionary term removed)
    for i in pick("ae", ae, ae["AEDECOD"].notna(), 2):
        set_value("ae", ae, i, "AEDECOD", np.nan, "AE04", "Coded term (AEDECOD) removed")

    # AE05 - serious flag not Y/N
    i, j = pick("ae", ae, ae["AESER"].eq("N"), 2)
    set_value("ae", ae, i, "AESER", "No", "AE05", "Serious flag written as 'No'")
    set_value("ae", ae, j, "AESER", np.nan, "AE05", "Serious flag deleted")

    # AE06 - serious AE without outcome (only 3 serious AEs exist)
    for i in pick("ae", ae, ae["AESER"].eq("Y"), 2):
        set_value("ae", ae, i, "AEOUT", np.nan, "AE06", "Outcome deleted on serious AE")

    # AE07 - AE start moved before treatment start (year typo)
    eligible = after_start & (ae["AESTDTC"].apply(
        lambda d: minus_one_year(d) if isinstance(d, str) else "") < rfstdtc.fillna(""))
    for i in pick("ae", ae, eligible, 2):
        set_value("ae", ae, i, "AESTDTC", minus_one_year(ae.at[i, "AESTDTC"]), "AE07",
                  "Year typo in AE start date (one year too early)")

    # AE08 - same AE entered twice: copy gets the next free AESEQ for that subject
    for i in pick("ae", ae, ae["USUBJID"].notna() & ~genuine_dup, 3):
        copy = ae.loc[i].copy()
        subject_seqs = num(ae.loc[ae["USUBJID"] == copy["USUBJID"], "AESEQ"])
        copy["AESEQ"] = str(int(subject_seqs.max()) + 1)
        new = len(ae)
        ae.loc[new] = copy
        used["ae"].add(new)
        log("ae", ae, new, "(whole record)", "", f"copy of AESEQ={ae.at[i, 'AESEQ']}", "AE08",
            "AE record entered twice", partner=f"AESEQ={ae.at[i, 'AESEQ']}")
    return ae


# --------------------------------------------------------------------------
# VS - Vital signs (11 errors)
# --------------------------------------------------------------------------

def set_vs_result(vs, i, new_value, check_id, description):
    """Change a VS result in the original and both standard result columns."""
    original = vs.at[i, "VSSTRESN"]
    for col in ("VSORRES", "VSSTRESC", "VSSTRESN"):
        vs.at[i, col] = new_value
    log("vs", vs, i, "VSORRES, VSSTRESC, VSSTRESN", original, new_value, check_id, description)


def inject_vs(vs):
    result = num(vs["VSSTRESN"])
    # Only use records where original and standard values are identical, so one
    # typing error affects all three result columns in the same way.
    same_units = vs["VSORRES"].eq(vs["VSSTRESC"]) & vs["VSORRESU"].eq(vs["VSSTRESU"])

    # VS01 - systolic BP typing errors (always too high, so VS02 is not triggered)
    sysbp = same_units & vs["VSTESTCD"].eq("SYSBP") & result.between(100, 199)
    i, j, k = pick("vs", vs, sysbp, 3)
    set_vs_result(vs, i, vs.at[i, "VSSTRESN"] + "0", "VS01", "Extra zero typed in systolic BP")
    set_vs_result(vs, j, vs.at[j, "VSSTRESN"] + "0", "VS01", "Extra zero typed in systolic BP")
    set_vs_result(vs, k, vs.at[k, "VSSTRESN"][0] + vs.at[k, "VSSTRESN"], "VS01",
                  "First digit typed twice in systolic BP")

    # VS02 - systolic and diastolic values swapped at one measurement
    key = ["USUBJID", "VISITNUM", "VSDTC", "VSTPTNUM"]
    sbp = vs[vs["VSTESTCD"].eq("SYSBP") & same_units].reset_index().set_index(key)
    dbp = vs[vs["VSTESTCD"].eq("DIABP") & same_units].reset_index().set_index(key)
    pairs = sbp[["index"]].join(dbp[["index"]], how="inner", suffixes=("_sys", "_dia"))
    # Diastolic >= 60 so that the swapped systolic stays inside VS01 limits
    ok = num(vs.loc[pairs["index_dia"], "VSSTRESN"]).ge(60).to_numpy() & \
        (num(vs.loc[pairs["index_dia"], "VSSTRESN"]).to_numpy() <
         num(vs.loc[pairs["index_sys"], "VSSTRESN"]).to_numpy())
    pairs = pairs[ok & ~pairs["index_sys"].isin(used["vs"]) & ~pairs["index_dia"].isin(used["vs"])]
    rows = sorted(rng.choice(len(pairs), size=2, replace=False).tolist())
    for r in rows:
        s, d = int(pairs.iloc[r]["index_sys"]), int(pairs.iloc[r]["index_dia"])
        used["vs"].update([s, d])
        sys_val, dia_val = vs.at[s, "VSSTRESN"], vs.at[d, "VSSTRESN"]
        for col in ("VSORRES", "VSSTRESC", "VSSTRESN"):
            vs.at[s, col], vs.at[d, col] = dia_val, sys_val
        log("vs", vs, d, "VSSTRESN (DIABP and SYSBP)", f"DIABP {dia_val} / SYSBP {sys_val}",
            f"DIABP {sys_val} / SYSBP {dia_val}", "VS02",
            f"Systolic and diastolic values swapped (SYSBP record VSSEQ={vs.at[s, 'VSSEQ']})")

    # VS03 - pulse and temperature typing errors
    pulse = same_units & vs["VSTESTCD"].eq("PULSE") & result.between(50, 99)
    i, j = pick("vs", vs, pulse, 2)
    set_vs_result(vs, i, vs.at[i, "VSSTRESN"] + "0", "VS03", "Extra zero typed in pulse")
    set_vs_result(vs, j, vs.at[j, "VSSTRESN"][0], "VS03", "Digit missing in pulse")
    # Most temperatures were entered in Fahrenheit (VSORRESU = F) and converted to
    # Celsius in VSSTRESN. The typo is made in the Fahrenheit value and the Celsius
    # value is re-derived with the same conversion: C = (F - 32) * 5 / 9.
    temp = (vs["VSTESTCD"].eq("TEMP") & vs["VSORRESU"].eq("F")
            & vs["VSORRES"].str.contains(r"\.", na=False))
    for i in pick("vs", vs, temp, 1):
        original = vs.at[i, "VSSTRESN"]
        typo_f = vs.at[i, "VSORRES"].replace(".", "")
        celsius = f"{(float(typo_f) - 32) * 5 / 9:.2f}"
        vs.at[i, "VSORRES"] = typo_f
        vs.at[i, "VSSTRESC"] = vs.at[i, "VSSTRESN"] = celsius
        log("vs", vs, i, "VSORRES, VSSTRESC, VSSTRESN", original, celsius, "VS03",
            f"Decimal point missing in Fahrenheit temperature (VSORRES typed as {typo_f})")

    # VS04 - unit missing
    has_result = vs["VSORRES"].notna() & vs["VSSTRESU"].notna() & vs["VSORRESU"].notna()
    i, j, k = pick("vs", vs, has_result, 3)
    set_value("vs", vs, i, "VSSTRESU", np.nan, "VS04", "Standard unit deleted")
    set_value("vs", vs, j, "VSSTRESU", np.nan, "VS04", "Standard unit deleted")
    set_value("vs", vs, k, "VSORRESU", np.nan, "VS04", "Original unit deleted")
    return vs


# --------------------------------------------------------------------------
# LB - Laboratory (6 errors)
# --------------------------------------------------------------------------

def inject_lb(lb):
    r, lo, hi = num(lb["LBORRES"]), num(lb["LBORNRLO"]), num(lb["LBORNRHI"])
    numeric = r.notna() & lo.notna() & hi.notna()

    # LB01 - abnormal result not flagged
    i = pick("lb", lb, numeric & lb["LBNRIND"].eq("HIGH"), 1)[0]
    set_value("lb", lb, i, "LBNRIND", "NORMAL", "LB01", "Reference range flag HIGH changed to NORMAL")
    j = pick("lb", lb, numeric & lb["LBNRIND"].eq("LOW"), 1)[0]
    set_value("lb", lb, j, "LBNRIND", np.nan, "LB01", "Reference range flag LOW deleted")
    # Decimal-point typing error: result x10, still flagged NORMAL
    eligible = numeric & lb["LBNRIND"].eq("NORMAL") & (r * 10 > hi) & (r > 0)
    k = pick("lb", lb, eligible, 1)[0]
    original = lb.at[k, "LBORRES"]
    for col in ("LBORRES", "LBSTRESC", "LBSTRESN"):
        lb.at[k, col] = f"{float(lb.at[k, col]) * 10:g}"
    log("lb", lb, k, "LBORRES", original, lb.at[k, "LBORRES"], "LB01",
        "Decimal point typed one place wrong (result x10), flag left as NORMAL")

    # LB02 - standard unit missing on tests that normally have a unit
    for i in pick("lb", lb, lb["LBSTRESC"].notna() & lb["LBSTRESU"].notna(), 3):
        set_value("lb", lb, i, "LBSTRESU", np.nan, "LB02", "Standard unit deleted")
    return lb


# --------------------------------------------------------------------------
# X01 - Visit chronology (2 in VS, 1 in LB)
# --------------------------------------------------------------------------

def in_order_subjects(df, dtc):
    """Subjects whose visits are already in chronological order in the raw data."""
    t = df[["USUBJID", "VISITNUM"]].copy()
    t["vn"], t["d"] = num(df["VISITNUM"]), pd.to_datetime(df[dtc].str[:10])
    g = t.groupby(["USUBJID", "vn"])["d"].agg(["min", "max"]).reset_index().sort_values(["USUBJID", "vn"])
    g["prev_max"] = g.groupby("USUBJID")["max"].transform(lambda s: s.cummax().shift())
    bad = g.loc[g["min"] < g["prev_max"], "USUBJID"].unique()
    return ~df["USUBJID"].isin(bad)


def inject_x01(domain, df, dtc, n):
    # Year typo on one record of a scheduled post-screening visit (VISITNUM 4 = WEEK 2 or later)
    eligible = in_order_subjects(df, dtc) & num(df["VISITNUM"]).between(4, 13) & full_date(df[dtc])
    for i in pick(domain, df, eligible, n):
        set_value(domain, df, i, dtc, minus_one_year(df.at[i, dtc]), "X01",
                  "Year typo in visit date (one year too early)")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    data = load_all()                       # always start again from the raw files
    dm = inject_dm(data["dm"])
    ae = inject_ae(data["ae"], data["dm"])
    vs = inject_vs(data["vs"])
    inject_x01("vs", vs, "VSDTC", 2)
    lb = inject_lb(data["lb"])
    inject_x01("lb", lb, "LBDTC", 1)

    INJECTED_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in {"dm": dm, "ae": ae, "vs": vs, "lb": lb}.items():
        df.to_csv(INJECTED_DIR / f"{name}.csv", index=False, na_rep="NA")  # same missing marker as raw

    key = pd.DataFrame(answer_key)
    key.to_csv(INJECTED_DIR / "answer_key.csv", index=False)
    print(f"Injected {len(key)} errors (seed {SEED}) into {INJECTED_DIR.name}/")
    print(key.groupby(["dataset", "expected_check_id"]).size().to_string())


if __name__ == "__main__":
    main()
