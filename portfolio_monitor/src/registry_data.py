"""
registry_data.py
----------------
Loads the newest snapshot from data/raw/ and prints a data profile.

The profile is the first step before writing any monitoring rule: it shows what
the registry actually contains (statuses, date precision, missing fields, site
countries), so the rules can be written for the real data, not for assumptions.

Run from the project root:
    python portfolio_monitor/src/registry_data.py
"""

import gzip
import json
from collections import Counter

from portfolio_config import EU_COUNTRIES, RAW_DIR


def latest_snapshot_dir():
    """Return the newest snapshot folder (names sort by registry date)."""
    snapshots = sorted(RAW_DIR.glob("snapshot_*"))
    if not snapshots:
        raise FileNotFoundError("No snapshot found. Run: python portfolio_monitor/src/fetch_studies.py")
    return snapshots[-1]


def load_snapshot(snapshot_dir=None):
    """Return (studies, metadata) for a snapshot folder (default: newest)."""
    snapshot_dir = snapshot_dir or latest_snapshot_dir()
    with gzip.open(snapshot_dir / "studies.json.gz", "rt", encoding="utf-8") as f:
        studies = json.load(f)
    metadata = json.loads((snapshot_dir / "metadata.json").read_text(encoding="utf-8"))
    return studies, metadata


def get(record, *path, default=None):
    """Safely read a nested field, e.g. get(s, "protocolSection", "statusModule")."""
    for key in path:
        if not isinstance(record, dict) or key not in record:
            return default
        record = record[key]
    return record


def print_counts(title, counter, top=None):
    print(f"\n{title}")
    total = sum(counter.values())
    for value, n in counter.most_common(top):
        print(f"  {str(value):<45} {n:>6}  ({n / total:.1%})")


def profile(studies, metadata):
    print("=" * 78)
    print("DATA PROFILE")
    print("=" * 78)
    print(f"Source:               {metadata['source']} (API {metadata['api_version']})")
    print(f"Registry data as of:  {metadata['registry_data_timestamp']}")
    print(f"Downloaded (UTC):     {metadata['downloaded_at_utc']}")
    print(f"Studies:              {len(studies)}")

    status = lambda s: get(s, "protocolSection", "statusModule") or {}
    design = lambda s: get(s, "protocolSection", "designModule") or {}

    # Duplicate study IDs would double-count trials in every KPI.
    ids = Counter(get(s, "protocolSection", "identificationModule", "nctId") for s in studies)
    print(f"Unique NCT IDs:       {len(ids)} (duplicates: {sum(n > 1 for n in ids.values())})")

    print_counts("Overall status", Counter(status(s).get("overallStatus") for s in studies))
    print_counts("Phase", Counter("/".join(design(s).get("phases", [])) for s in studies))
    print_counts("Lead sponsor class", Counter(
        get(s, "protocolSection", "sponsorCollaboratorsModule", "leadSponsor", "class")
        for s in studies))
    print_counts("Results posted (hasResults) by status", Counter(
        (status(s).get("overallStatus"), s.get("hasResults")) for s in studies))

    # Dates: precision (full date vs month only) and actual vs estimated.
    for field in ("startDateStruct", "primaryCompletionDateStruct", "completionDateStruct"):
        precision = Counter()
        for s in studies:
            d = status(s).get(field)
            if d is None:
                precision["missing"] += 1
            else:
                kind = {10: "YYYY-MM-DD", 7: "YYYY-MM"}.get(len(d["date"]), d["date"])
                precision[f"{kind} / {d.get('type', 'no type')}"] += 1
        print_counts(f"{field}: precision / type", precision)

    print_counts("Enrollment type", Counter(
        get(design(s), "enrollmentInfo", "type", default="missing") for s in studies))
    print(f"\nEnrollment count missing: "
          f"{sum(get(design(s), 'enrollmentInfo', 'count') is None for s in studies)}")

    print_counts("Reason for stopping (whyStopped) given, by status", Counter(
        (status(s).get("overallStatus"), "whyStopped" in status(s)) for s in studies
        if status(s).get("overallStatus") in ("TERMINATED", "WITHDRAWN", "SUSPENDED")))
    print_counts("Record last verified (year of statusVerifiedDate)", Counter(
        status(s).get("statusVerifiedDate", "missing")[:4] for s in studies))
    print_counts("FDA-regulated drug flag", Counter(
        get(s, "protocolSection", "oversightModule", "isFdaRegulatedDrug", default="missing")
        for s in studies))

    # Sites
    locations = [loc for s in studies
                 for loc in get(s, "protocolSection", "contactsLocationsModule",
                                "locations", default=[])]
    countries = Counter(loc.get("country") for loc in locations)
    eu_sites = sum(n for c, n in countries.items() if c in EU_COUNTRIES)
    print(f"\nSites (location records): {len(locations)} in {len(countries)} countries")
    print(f"  of which in the EU:     {eu_sites} ({eu_sites / len(locations):.1%})")
    print(f"  EU country names found: "
          f"{sorted(c for c in countries if c in EU_COUNTRIES)}")
    print(f"  EU names not found:     "
          f"{sorted(c for c in EU_COUNTRIES if c not in countries)}")
    print_counts("Top 10 site countries", countries, top=10)
    print_counts("Site recruitment status", Counter(
        loc.get("status", "missing") for loc in locations))
    sites_per_study = sorted(len(get(s, "protocolSection", "contactsLocationsModule",
                                     "locations", default=[])) for s in studies)
    print(f"\nSites per study: min {sites_per_study[0]}, "
          f"median {sites_per_study[len(sites_per_study) // 2]}, max {sites_per_study[-1]}")


if __name__ == "__main__":
    profile(*load_snapshot())
