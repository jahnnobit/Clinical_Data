# Data Management Plan

**Project:** Clinical Trial Data Quality Review (portfolio project)
**Data:** CDISC pilot study SDTM test data (study CDISCPILOT01): DM, AE, VS, LB
**Status:** Portfolio project on public data. This is not real clinical trial work. Errors were injected deliberately and query statuses are simulated.

---

## 1. Purpose and scope

This plan describes how data quality is reviewed in this project: which data is checked, how checks are defined and run, how findings become queries, and when the database would be ready to lock.

**In scope:** four SDTM domains from the `pharmaversesdtm` package (commit `7ec53ea`):

| Domain | Content | Records | Subjects |
|---|---|---|---|
| DM | Demographics | 306 | 306 (52 screen failures) |
| AE | Adverse events | 1,191 | 225 |
| VS | Vital signs | 29,643 | 254 |
| LB | Laboratory results | 59,580 | 254 |

**Out of scope:** data entry in an EDC system, MedDRA coding, SAE reconciliation, external data (e.g. central lab transfers), other SDTM domains.

## 2. Roles

In this project one person performs all roles. In a real study they would be separate:

| Role | Responsibility | In this project |
|---|---|---|
| Clinical Data Manager | Writes the edit check specification, runs checks, raises and closes queries, confirms lock criteria | Project author |
| Site staff | Answer queries, correct source data | Simulated |
| Medical coder | Codes AE terms with MedDRA | Not performed; only missing coding is detected (AE04) |
| Medical monitor | Reviews clinically relevant findings (e.g. pre-treatment AEs) | Not available |
| Statistician | Uses the locked data for analysis | Not part of this project |

## 3. Data flow

```
data/raw/*.csv  (original public data, read-only)
      |
      |  src/load_data.py          read every value as text; NA and empty = missing
      v
src/inject_errors.py  -->  data/injected/*.csv + answer_key.csv  (50 deliberate errors, seed 42)
      |
      |  src/edit_checks.py        20 edit checks, run on raw AND injected data
      v
output/findings_raw.csv, findings_injected.csv, check_results_summary.csv
      |
      |  src/build_query_log.py    one query per problem; simulated workflow (seed 2025)
      v
output/query_log.xlsx  -->  dashboard/quality_tab.py (Plotly Dash, project root)
```

The full pipeline runs with one command: `python src/run_all.py`.

## 4. Data validation

Validation rules are defined in **[Edit_Check_Specification.xlsx](Edit_Check_Specification.xlsx)**. Each rule has an ID, the variables it uses, the rule in plain English, pseudo-code logic, a severity and a neutral query text.

| Dataset | Checks | Examples |
|---|---|---|
| DM | 5 (DM01-DM05) | Missing or duplicated subject ID, age outside 18-100, invalid ISO 8601 date |
| AE | 8 (AE01-AE08) | AE subject not in DM, end date before start date, serious AE without outcome, duplicate AE |
| VS | 4 (VS01-VS04) | Systolic BP outside 60-250 mmHg, diastolic higher than systolic, unit missing |
| LB | 2 (LB01-LB02) | Result outside normal range but not flagged, standard unit missing |
| Cross-domain | 1 (X01) | Visit dates not in chronological order of VISITNUM (VS and LB) |

**Severity:** 4 Critical (subject identity, safety data), 12 Major (data used in analysis), 4 Minor (review or completeness items).

**Adaptation to the real data.** Before writing any check, the data was profiled (`src/load_data.py`). Six checks were adapted to the real structure, and each change is documented in the "Notes" column of the specification. For example:
- LB01 uses the original-unit normal range, because rounding of the standard-unit limits produced 156 false hits.
- AE08 ignores the record identifiers AESEQ and AESPID, because every AE record has a unique AESEQ and two rows could never be exactly identical.
- X01 runs on VS and LB only, because DM and AE have no VISITNUM.

**Numeric limits** in DM02, VS01 and VS03 are *assumed plausibility limits*, not clinical rules.

**Validation of the checks themselves.**
- Every check has a unit test with hand-made data (`tests/test_edit_checks.py`, 22 tests).
- The checks were run on a copy of the data with 50 known injected errors. All 50 were found (catch rate 100%) with 0 false positives. Because the same person designed the errors and the checks, this shows that the checks work as specified. It is not an independent measure of sensitivity.

## 5. Query management

- **One query per problem, not per record.** A wrong visit date can affect around 30 lab records of the same visit, so X01 is raised once per subject and visit. A duplicate pair is raised once (DM01, AE08).
- **Query text** comes from the specification. It is neutral and specific, and it never suggests the "correct" value (e.g. *"AE end date is before AE start date. Please verify both dates."*).
- **Life cycle:** *Open* (sent to site), then *Answered* (site responded, data management reviews), then *Closed* (answer accepted: value corrected or confirmed correct).
- **Result:** 321 findings on the injected data became **122 queries**: 50 for injected errors and 72 for genuine findings in the public data (AE07: 65, AE08: 1, X01: 6).
- **Simulation:** status, dates and resolutions are randomly simulated (seed 2025: 73 Closed, 30 Answered, 19 Open). This is labelled in the query log file and on the dashboard.

## 6. Coding

AE coding is **checked for completeness only**. AE04 flags a reported term (AETERM) that has no dictionary-derived term (AEDECOD). In the source data all MedDRA code variables (AELLTCD, AEPTCD, AEHLTCD, AEHLGTCD, AEBDSYCD, AESOCCD) are empty, so the check uses AEDECOD. This project does **not** perform MedDRA coding and does not verify whether existing codes are correct.

## 7. Data integrity

The project follows the ALCOA+ principles as far as they apply to a scripted review:

| Principle | How it is applied |
|---|---|
| Attributable | Data source and repository commit recorded in `data/raw/SOURCE.md`; changes tracked with git |
| Legible | Plain CSV and Excel outputs; readable, commented code |
| Contemporaneous | Not applicable to a retrospective review of public data (no real-time data entry) |
| Original | Raw files are never overwritten; they are read-only on disk. Injected copies are stored separately |
| Accurate | Every check is unit-tested; the injected errors are reconciled against an answer key |
| Complete, Consistent | Every finding traces back to one record (`record_key`); every query lists its records |
| Enduring, Available | All inputs, scripts and outputs are kept in version control |

**Reproducibility:** fixed random seeds (42 for error injection, 2025 for the query simulation). A clean rebuild with `python src/run_all.py` produces identical output files.

## 8. Database lock criteria

The database is ready to lock when **all** of these are true:

1. All queries are **Closed**. Answered queries still block the lock until data management has reviewed the answer.
2. No Critical finding is unresolved.
3. All edit checks have been re-run on the final data and produce no new findings.
4. Any finding accepted as "confirmed correct" is documented in the query log.

**Current status (simulated):** not ready for lock.
- 49 queries are outstanding (19 Open, 30 Answered), across 13 checks.
- 4 of them are Critical (DM01, AE03, AE06).
- The status is shown live in the dashboard's "Database lock readiness" panel.

## 9. Assumptions and limitations

- **Public pilot data.** The CDISC pilot SDTM datasets are test data, already cleaned and derived. They are not raw EDC data, and some variables are empty by design (e.g. RFICDTC, MedDRA codes).
- **Errors injected on purpose.** The 50 errors in `data/injected/` were added deliberately (see `answer_key.csv`). The 100% catch rate applies to these designed errors only.
- **Simulated query statuses.** No site was contacted. Statuses, dates and resolution texts are random (fixed seed).
- **Assumed plausibility limits.** The limits in DM02 (age 18-100), VS01 (SBP 60-250 mmHg) and VS03 (pulse 30-200 /min, temperature 34-42 °C) are assumptions, not protocol or clinical limits.
- **Genuine findings are not judged.** AE07 (65 AEs starting before treatment) is a review flag; many such events may be correct. In a real study the medical monitor would decide whether they belong in medical history.
- **Known gaps.** Three AEs with outcome FATAL are recorded as not serious (AESER = N). This was found during data profiling but is not covered by the 20 checks. The same applies to 250 AEs with an end date but the outcome "NOT RECOVERED/NOT RESOLVED".
