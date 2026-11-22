# Clinical Trial Oversight Toolkit

A portfolio project, built on public data, that covers two levels of clinical trial oversight:

| Part | Level | Data | What it does |
|---|---|---|---|
| **A. Trial portfolio monitor** | Portfolio | Live **ClinicalTrials.gov** data: 1,937 EU Phase 3 oncology trials | Portfolio overview, site footprint, and (in progress) results reporting and timeline monitoring |
| **B. Study data quality review** | One study | **CDISC pilot** SDTM data (DM, AE, VS, LB) | 20 edit checks, query log, database lock readiness |

Part A shows what a clinical project manager or coordinator sees across many trials. Part B goes inside one trial and checks the quality of its data. Both parts share one interactive dashboard.

> **Note:** this is a portfolio project on public data, not real clinical trial work. In Part B, errors were injected on purpose and query statuses are simulated. Part A uses real registry records exactly as published.

**Live dashboard:** *add your Render URL here after deploying (see [Deploy](#deploy))*

<!-- Placeholder: add a screenshot as docs/dashboard_screenshot.png -->

---

## Part A: Trial portfolio monitor

**Status:** data download, profiling, tables and dashboard tab are finished. Monitoring rules (results reporting, overdue completion dates, stale records) are in progress.

**Scope:** Phase 3 interventional oncology trials with at least one site in an EU member state, started in 2015 or later.

**Data:** [ClinicalTrials.gov API v2](https://clinicaltrials.gov/data-api/api). The download is saved as a dated, read-only snapshot (`portfolio_monitor/data/raw/snapshot_2026-11-20/`), together with the API version, the registry date and the exact query. This works like a "data cut": every number can be traced back to one fixed version of the registry.

**Results so far** (snapshot of 2026-11-20):

| | Count |
|---|---|
| Studies | 1,937 (1,737 Phase 3, 200 Phase 2/3) |
| Lead sponsors | 599 organisations; 1,227 studies (63%) sponsored by industry |
| Status | 557 Completed, 521 Recruiting, 497 Active (not recruiting), 188 Terminated, 119 Unknown |
| Sites | 199,255 in 90 countries; 75,613 in 26 EU countries |
| Completed studies with results posted | 370 of 557 |

**What the profile showed before any rule was written:**
- 412 primary completion dates have a month but no day. They are kept as registered, because converting them would invent a day nobody reported.
- 72% of site records have no site status, so site status is not used for KPIs.
- The registry keeps only the latest enrollment number, not the original target. Timeline slippage is therefore measured with dates and reasons for stopping, not with planned vs actual enrollment.
- Sponsors often hide site names ("Research Site" appears 6,312 times), so site rows that look the same are counted as separate sites.

## Part B: Study data quality review

The core work of a clinical data manager on the CDISC pilot study SDTM data ([pharmaversesdtm](https://github.com/pharmaverse/pharmaversesdtm), commit `7ec53ea`). Details are in [data_quality_review/README.md](data_quality_review/README.md) and the [Data Management Plan](data_quality_review/docs/Data_Management_Plan.md).

| | Result |
|---|---|
| Edit checks | 20 (4 Critical, 12 Major, 4 Minor) |
| Records checked | 90,724 from 306 subjects |
| Injected errors | 50 injected, 50 caught (100%), 0 false positives |
| Genuine findings in the public data | 267 records (e.g. 65 AEs starting before treatment, 1 duplicate AE) |
| Query log | 122 queries (one per problem): 73 Closed, 30 Answered, 19 Open (simulated) |
| Database lock | Not ready: 49 queries outstanding across 13 checks, 4 of them Critical |

The 100% catch rate shows that the checks work as specified. The same person designed the errors and the checks, so it is not an independent accuracy estimate.

---

## How to run

Requires Python 3.14.

```bash
# 1. Set up the environment (once)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Rebuild every output from the saved data (both parts)
python run_all.py

# 3. Run the unit tests
pytest

# 4. Start the dashboard, then open http://127.0.0.1:8050
python dashboard/app.py
```

`run_all.py` works on the saved snapshot and does not download anything. To take a new snapshot of the registry, run `python portfolio_monitor/src/fetch_studies.py`. Snapshots are never overwritten.

## Deploy

The dashboard is a Python web app (Plotly Dash), so it needs a Python host. GitHub Pages only serves static pages and cannot run it. The repository is ready for [Render](https://render.com), which has a free plan:

1. Push this folder to a GitHub repository.
2. On Render, choose **New > Blueprint** and select the repository. Render reads `render.yaml`.
3. Render installs the packages, runs `python run_all.py` to rebuild the outputs, and starts the dashboard with gunicorn. The Python version comes from `.python-version`.
4. Copy the URL Render gives you into the "Live dashboard" line at the top of this README.

On the free plan the app sleeps after a period without visits, so the first page load can take up to about a minute.

## Project structure

```
clinical-trial-oversight/
├── README.md
├── run_all.py                  # runs both parts
├── requirements.txt, .python-version, render.yaml, pytest.ini
├── dashboard/                  # one dashboard, one tab per part
│   ├── app.py
│   ├── portfolio_tab.py        # Part A tab
│   ├── quality_tab.py          # Part B tab
│   ├── theme.py                # shared colours and chart style
│   └── assets/style.css
├── portfolio_monitor/          # Part A
│   ├── src/                    # portfolio_config, fetch_studies, registry_data, build_tables
│   ├── data/raw/               # read-only snapshot(s) of the registry
│   ├── data/processed/         # studies.csv, sites.csv
│   └── tests/
└── data_quality_review/        # Part B
    ├── src/                    # load_data, build_edit_check_spec, inject_errors, edit_checks, build_query_log, run_all
    ├── data/raw/               # original CDISC CSVs (read-only)
    ├── data/injected/          # copies with 50 injected errors + answer key
    ├── docs/                   # Data Management Plan, Edit Check Specification
    ├── output/                 # query log, findings, check summary
    └── tests/
```

## Limitations

- **Part A:** a missing result on ClinicalTrials.gov is not, by itself, a legal breach. US reporting rules apply only to certain trials, and EU trials report results in the EU Clinical Trials Information System (CTIS), which this project does not read.
- **Part B:** errors were injected and query statuses are simulated. The project does not perform MedDRA coding and does not use an EDC system.
