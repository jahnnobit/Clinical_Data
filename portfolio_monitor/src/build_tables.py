"""
build_tables.py
---------------
Turns the nested JSON study records of the snapshot into two flat tables:

- studies.csv : one row per study (status, dates, sponsor, enrollment, results)
- sites.csv   : one row per study site (facility, city, country, site status)

Flat tables are what a clinical trial management system (CTMS) report or a
portfolio dashboard works with. Dates are kept as text exactly as registered
("2025-03" or "2025-03-14"), because the registry allows month-only dates and
converting them would invent a day that was never reported.

Output goes to portfolio_monitor/data/processed/. These files are derived from
the snapshot and are rebuilt every run; the snapshot itself is never changed.

Each location record counts as one site. Some sponsors hide site names (e.g.
"Research Site" several times in the same city), so rows that look identical
are separate sites, not duplicates.

Run from the project root:
    python portfolio_monitor/src/build_tables.py
"""

import pandas as pd

from portfolio_config import EU_COUNTRIES, PROCESSED_DIR
from registry_data import get, latest_snapshot_dir, load_snapshot


def date_and_type(status_module, field):
    """Return (date text, ACTUAL/ESTIMATED) of a registry date field."""
    struct = status_module.get(field) or {}
    return struct.get("date"), struct.get("type")


def flatten_study(study):
    """One study record -> (study row dict, list of site row dicts)."""
    p = study.get("protocolSection", {})
    ident = p.get("identificationModule", {})
    status = p.get("statusModule", {})
    sponsor = p.get("sponsorCollaboratorsModule", {})
    design = p.get("designModule", {})
    locations = get(p, "contactsLocationsModule", "locations", default=[])
    nct_id = ident.get("nctId")

    sites = [
        {
            "nct_id": nct_id,
            "facility": loc.get("facility"),
            "city": loc.get("city"),
            "country": loc.get("country"),
            "is_eu": loc.get("country") in EU_COUNTRIES,
            "site_status": loc.get("status"),
        }
        for loc in locations
    ]
    countries = {s["country"] for s in sites if s["country"]}
    eu_countries = sorted(c for c in countries if c in EU_COUNTRIES)

    start, start_type = date_and_type(status, "startDateStruct")
    pcd, pcd_type = date_and_type(status, "primaryCompletionDateStruct")
    completion, completion_type = date_and_type(status, "completionDateStruct")

    row = {
        "nct_id": nct_id,
        "brief_title": ident.get("briefTitle"),
        "acronym": ident.get("acronym"),
        "overall_status": status.get("overallStatus"),
        "phase": "/".join(design.get("phases", [])),
        "lead_sponsor": get(sponsor, "leadSponsor", "name"),
        "sponsor_class": get(sponsor, "leadSponsor", "class"),
        "responsible_party_type": get(sponsor, "responsibleParty", "type"),
        "is_fda_regulated_drug": get(p, "oversightModule", "isFdaRegulatedDrug"),
        "has_dmc": get(p, "oversightModule", "oversightHasDmc"),
        "conditions": "; ".join(get(p, "conditionsModule", "conditions", default=[])),
        "start_date": start,
        "start_date_type": start_type,
        "primary_completion_date": pcd,
        "primary_completion_type": pcd_type,
        "completion_date": completion,
        "completion_type": completion_type,
        "first_posted": get(status, "studyFirstPostDateStruct", "date"),
        "last_update_posted": get(status, "lastUpdatePostDateStruct", "date"),
        "status_verified": status.get("statusVerifiedDate"),
        "has_results": bool(study.get("hasResults")),
        "results_first_posted": get(status, "resultsFirstPostDateStruct", "date"),
        "enrollment_count": get(design, "enrollmentInfo", "count"),
        "enrollment_type": get(design, "enrollmentInfo", "type"),
        "why_stopped": status.get("whyStopped"),
        "n_sites": len(sites),
        "n_eu_sites": sum(s["is_eu"] for s in sites),
        "n_countries": len(countries),
        "n_eu_countries": len(eu_countries),
        "eu_countries": "; ".join(eu_countries),
    }
    return row, sites


def build_tables(studies):
    """All study records -> (studies DataFrame, sites DataFrame)."""
    study_rows, site_rows = [], []
    for study in studies:
        row, sites = flatten_study(study)
        study_rows.append(row)
        site_rows.extend(sites)
    studies_df = pd.DataFrame(study_rows)
    sites_df = pd.DataFrame(site_rows)
    studies_df["enrollment_count"] = studies_df["enrollment_count"].astype("Int64")
    return studies_df, sites_df


def main():
    snapshot_dir = latest_snapshot_dir()
    studies, metadata = load_snapshot(snapshot_dir)
    studies_df, sites_df = build_tables(studies)

    # Reconciliation: the flat tables must hold exactly what the snapshot holds.
    n_locations = sum(len(get(s, "protocolSection", "contactsLocationsModule",
                              "locations", default=[])) for s in studies)
    assert len(studies_df) == metadata["study_count"], "study count mismatch"
    assert studies_df["nct_id"].is_unique, "duplicate NCT IDs"
    assert len(sites_df) == n_locations, "site count mismatch"
    assert (studies_df["n_eu_sites"] > 0).all(), "study without an EU site"

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    studies_df.to_csv(PROCESSED_DIR / "studies.csv", index=False)
    sites_df.to_csv(PROCESSED_DIR / "sites.csv", index=False)

    print(f"Snapshot: {snapshot_dir.name} (registry data as of "
          f"{metadata['registry_data_timestamp']})")
    print(f"studies.csv: {len(studies_df)} rows x {studies_df.shape[1]} columns")
    print(f"sites.csv:   {len(sites_df)} rows x {sites_df.shape[1]} columns")
    print("Reconciliation with snapshot: study count, unique IDs, site count, "
          "EU site per study - all OK")

    print("\nMissing values per column (studies.csv):")
    missing = studies_df.isna().sum()
    for column, n in missing[missing > 0].items():
        print(f"  {column:<26} {n:>5}")

    print("\nSites: EU vs non-EU")
    print(f"  EU sites:     {sites_df['is_eu'].sum()}")
    print(f"  non-EU sites: {(~sites_df['is_eu']).sum()}")
    print(f"  site_status missing: {sites_df['site_status'].isna().sum()}")
    print(f"\nEU sites per study: median {studies_df['n_eu_sites'].median():.0f}, "
          f"max {studies_df['n_eu_sites'].max()}")
    print(f"EU countries per study: median {studies_df['n_eu_countries'].median():.0f}, "
          f"max {studies_df['n_eu_countries'].max()}")


if __name__ == "__main__":
    main()
