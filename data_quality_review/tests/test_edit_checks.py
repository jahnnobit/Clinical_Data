"""
Unit tests for src/edit_checks.py.

Each test builds a tiny hand-made DataFrame with at least one record that
should PASS and one that should FAIL the check, then asserts that exactly the
failing records are returned. All values are text, as in load_data.py
(missing = None).

Run from the project root:
    pytest
"""

import pandas as pd

import edit_checks as ec


def frame(rows):
    """Build a DataFrame where every value is text (or missing)."""
    return pd.DataFrame(rows).astype("object").where(lambda d: d.notna(), None)


def flagged(findings):
    """The record keys returned by a check, as a sorted list."""
    return sorted(findings["record_key"])


# ---------------- helpers ----------------

def test_date_before_compares_partial_dates_on_shared_precision():
    a = pd.Series(["2012-02", "2014-01-05", None, "2013"])
    b = pd.Series(["2012-03-15", "2014-01-05T10:00", "2014-01-01", "2013-06-01"])
    assert ec.date_before(a, b).tolist() == [True, False, False, False]


def test_is_valid_iso_date():
    assert ec.is_valid_iso_date("2014-01-02")
    assert ec.is_valid_iso_date("2014-01-02T11:45")
    assert ec.is_valid_iso_date("2014-01")          # partial date is allowed
    assert not ec.is_valid_iso_date("2014-13-01")   # month 13
    assert not ec.is_valid_iso_date("2014-02-30")   # 30 February
    assert not ec.is_valid_iso_date("02/01/2014")   # not ISO 8601


# ---------------- DM ----------------

def dm_row(subjid, **values):
    row = {"USUBJID": f"01-701-{subjid}", "SUBJID": subjid, "AGE": "65", "SEX": "F",
           "RFSTDTC": "2014-01-02", "RFENDTC": "2014-07-02"}
    for var in ec.DM_DATE_VARIABLES:
        row.setdefault(var, None)
    row.update(values)
    return row


def test_dm01_missing_or_duplicated_usubjid():
    dm = frame([dm_row("1001"), dm_row("1002", USUBJID=None),
                dm_row("1003", USUBJID="01-701-1004"), dm_row("1004")])
    assert flagged(ec.dm01(dm)) == ["SUBJID=1002", "SUBJID=1003", "SUBJID=1004"]


def test_dm02_age_missing_or_out_of_range():
    dm = frame([dm_row("1001", AGE="18"), dm_row("1002", AGE="100"), dm_row("1003", AGE="17"),
                dm_row("1004", AGE="560"), dm_row("1005", AGE=None), dm_row("1006", AGE="6O")])
    assert flagged(ec.dm02(dm)) == ["SUBJID=1003", "SUBJID=1004", "SUBJID=1005", "SUBJID=1006"]


def test_dm03_sex_not_in_codelist():
    dm = frame([dm_row("1001", SEX="M"), dm_row("1002", SEX="U"), dm_row("1003", SEX="Female"),
                dm_row("1004", SEX="f"), dm_row("1005", SEX=None)])
    assert flagged(ec.dm03(dm)) == ["SUBJID=1003", "SUBJID=1004", "SUBJID=1005"]


def test_dm04_start_after_end_and_missing_dates_ignored():
    dm = frame([dm_row("1001"),
                dm_row("1002", RFSTDTC="2014-07-02", RFENDTC="2014-01-02"),
                dm_row("1003", RFSTDTC=None, RFENDTC=None)])          # screen failure
    assert flagged(ec.dm04(dm)) == ["SUBJID=1002"]


def test_dm05_invalid_iso_dates():
    dm = frame([dm_row("1001", BRTHDTC="1950-12-26"),
                dm_row("1002", BRTHDTC="1950-13-26"),
                dm_row("1003", DMDTC="26/12/2013"),
                dm_row("1004", DTHDTC="2014-02")])                     # partial date: valid
    assert flagged(ec.dm05(dm)) == ["SUBJID=1002", "SUBJID=1003"]


# ---------------- AE ----------------

def ae_row(seq, **values):
    row = {"USUBJID": "01-701-1001", "AESEQ": seq, "AESPID": f"E{seq}", "AETERM": "HEADACHE",
           "AEDECOD": "HEADACHE", "AESER": "N", "AEOUT": "RECOVERED/RESOLVED",
           "AESTDTC": f"2014-02-{int(seq):02d}", "AEENDTC": None}
    row.update(values)
    return row


DM_FOR_AE = frame([dm_row("1001", RFSTDTC="2014-01-10")])


def test_ae01_subject_not_in_dm():
    ae = frame([ae_row("1"), ae_row("2", USUBJID="01-701-9999"), ae_row("3", USUBJID=None)])
    assert flagged(ec.ae01(ae, DM_FOR_AE)) == ["AESEQ=2", "AESEQ=3"]


def test_ae02_end_before_start():
    ae = frame([ae_row("1", AESTDTC="2014-02-01", AEENDTC="2014-02-05"),
                ae_row("2", AESTDTC="2014-02-05", AEENDTC="2014-02-01"),
                ae_row("3", AESTDTC="2014-02", AEENDTC="2014-01-20"),    # partial start date
                ae_row("4", AESTDTC="2014-02-05", AEENDTC=None)])        # ongoing
    assert flagged(ec.ae02(ae)) == ["AESEQ=2", "AESEQ=3"]


def test_ae03_term_missing():
    ae = frame([ae_row("1"), ae_row("2", AETERM=None), ae_row("3", AETERM="  ")])
    assert flagged(ec.ae03(ae)) == ["AESEQ=2", "AESEQ=3"]


def test_ae04_term_not_coded():
    ae = frame([ae_row("1"), ae_row("2", AEDECOD=None), ae_row("3", AETERM=None, AEDECOD=None)])
    assert flagged(ec.ae04(ae)) == ["AESEQ=2"]


def test_ae05_serious_flag_not_y_or_n():
    ae = frame([ae_row("1", AESER="Y"), ae_row("2", AESER="No"), ae_row("3", AESER=None)])
    assert flagged(ec.ae05(ae)) == ["AESEQ=2", "AESEQ=3"]


def test_ae06_serious_without_outcome():
    ae = frame([ae_row("1", AESER="Y"), ae_row("2", AESER="Y", AEOUT=None),
                ae_row("3", AESER="N", AEOUT=None)])
    assert flagged(ec.ae06(ae)) == ["AESEQ=2"]


def test_ae07_start_before_reference_start():
    ae = frame([ae_row("1", AESTDTC="2014-01-10"),                    # same day: not before
                ae_row("2", AESTDTC="2014-01-09"),
                ae_row("3", AESTDTC="2013"),                          # partial year, earlier
                ae_row("4", USUBJID="01-701-9999", AESTDTC="2000-01-01")])  # no DM record: skipped
    assert flagged(ec.ae07(ae, DM_FOR_AE)) == ["AESEQ=2", "AESEQ=3"]


def test_ae08_duplicate_ignores_aeseq_and_aespid():
    ae = frame([ae_row("1", AESTDTC="2014-02-01"),
                ae_row("2", AESTDTC="2014-02-01"),                    # copy of 1 except AESEQ/AESPID
                ae_row("3", AESTDTC="2014-02-01", AETERM="NAUSEA")])
    assert flagged(ec.ae08(ae)) == ["AESEQ=1", "AESEQ=2"]


# ---------------- VS ----------------

def vs_row(seq, testcd, value, unit, **values):
    row = {"USUBJID": "01-701-1001", "VSSEQ": seq, "VSTESTCD": testcd,
           "VSORRES": value, "VSORRESU": unit, "VSSTRESC": value, "VSSTRESN": value, "VSSTRESU": unit,
           "VISITNUM": "3", "VISIT": "BASELINE", "VSDTC": "2014-01-02", "VSTPTNUM": "815"}
    row.update(values)
    return row


def test_vs01_systolic_out_of_range():
    vs = frame([vs_row("1", "SYSBP", "60", "mmHg"), vs_row("2", "SYSBP", "250", "mmHg"),
                vs_row("3", "SYSBP", "1660", "mmHg"), vs_row("4", "SYSBP", "59", "mmHg"),
                vs_row("5", "DIABP", "30", "mmHg"),                    # other test: ignored
                vs_row("6", "SYSBP", None, None)])                     # not done: ignored
    assert flagged(ec.vs01(vs)) == ["VSSEQ=3", "VSSEQ=4"]


def test_vs02_diastolic_higher_than_systolic():
    vs = frame([vs_row("1", "SYSBP", "130", "mmHg"), vs_row("2", "DIABP", "80", "mmHg"),
                vs_row("3", "SYSBP", "70", "mmHg", VSTPTNUM="816"),
                vs_row("4", "DIABP", "130", "mmHg", VSTPTNUM="816"),
                vs_row("5", "DIABP", "90", "mmHg", VSTPTNUM="817")])   # no systolic partner
    result = ec.vs02(vs)
    assert flagged(result) == ["VSSEQ=4"]
    assert result["value"].iloc[0] == "DIABP=130; SYSBP=70"


def test_vs03_pulse_or_temperature_out_of_range():
    vs = frame([vs_row("1", "PULSE", "72", "BEATS/MIN"), vs_row("2", "PULSE", "740", "BEATS/MIN"),
                vs_row("3", "PULSE", "6", "BEATS/MIN"), vs_row("4", "TEMP", "36.6", "C"),
                vs_row("5", "TEMP", "526.11", "C"), vs_row("6", "TEMP", "34", "C")])
    assert flagged(ec.vs03(vs)) == ["VSSEQ=2", "VSSEQ=3", "VSSEQ=5"]


def test_vs04_result_without_unit():
    vs = frame([vs_row("1", "PULSE", "72", "BEATS/MIN"),
                vs_row("2", "PULSE", "72", "BEATS/MIN", VSSTRESU=None),
                vs_row("3", "PULSE", "72", "BEATS/MIN", VSORRESU=None),
                vs_row("4", "PULSE", None, None)])                     # no result, no unit: fine
    assert flagged(ec.vs04(vs)) == ["VSSEQ=2", "VSSEQ=3"]


# ---------------- LB ----------------

def lb_row(seq, testcd, value, low, high, flag, unit="mmol/L", **values):
    row = {"USUBJID": "01-701-1001", "LBSEQ": seq, "LBTESTCD": testcd,
           "LBORRES": value, "LBORNRLO": low, "LBORNRHI": high, "LBNRIND": flag,
           "LBSTRESC": value, "LBSTRESU": unit,
           "VISITNUM": "3", "VISIT": "BASELINE", "LBDTC": "2014-01-02T08:00"}
    row.update(values)
    return row


def test_lb01_out_of_range_not_flagged():
    lb = frame([lb_row("1", "K", "4.0", "3.5", "5.1", "NORMAL"),
                lb_row("2", "K", "6.0", "3.5", "5.1", "HIGH"),
                lb_row("3", "K", "6.0", "3.5", "5.1", "NORMAL"),
                lb_row("4", "K", "2.0", "3.5", "5.1", None),
                lb_row("5", "BILI", "<3.42", "3", "21", None)])        # non-numeric: not compared
    assert flagged(ec.lb01(lb)) == ["LBSEQ=3", "LBSEQ=4"]


def test_lb02_unit_missing_only_for_tests_with_units():
    lb = frame([lb_row("1", "K", "4.0", "3.5", "5.1", "NORMAL"),
                lb_row("2", "K", "4.2", "3.5", "5.1", "NORMAL", unit=None),
                lb_row("3", "PH", "6", None, None, None, unit=None),   # pH never has a unit
                lb_row("4", "PH", "7", None, None, None, unit=None)])
    assert flagged(ec.lb02(lb)) == ["LBSEQ=2"]


# ---------------- Cross-domain ----------------

def test_x01_visit_dates_not_chronological():
    vs = frame([vs_row("1", "PULSE", "72", "BEATS/MIN", VISITNUM="1", VSDTC="2014-01-01"),
                vs_row("2", "PULSE", "72", "BEATS/MIN", VISITNUM="3", VSDTC="2014-01-15"),
                vs_row("3", "PULSE", "72", "BEATS/MIN", VISITNUM="4", VSDTC="2013-01-29"),  # year typo
                vs_row("4", "PULSE", "72", "BEATS/MIN", VISITNUM="5", VSDTC="2014-02-12")])
    assert flagged(ec.x01(vs, "vs")) == ["VSSEQ=3"]
