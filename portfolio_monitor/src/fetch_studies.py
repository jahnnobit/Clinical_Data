"""
fetch_studies.py
----------------
Downloads the live study records for the project scope (see portfolio_config.py) from the
ClinicalTrials.gov API v2 and saves them as a dated snapshot.

Why a snapshot? The registry changes every day. Saving the exact download, with
the API version and the registry's data timestamp, means every later result can
be traced back to one fixed version of the data (like a database "data cut").
Snapshots are written once and made read-only; they are never edited.

Run from the project root:
    python portfolio_monitor/src/fetch_studies.py
"""

import gzip
import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from portfolio_config import API_URL, QUERY_PARAMS, RAW_DIR

PAGE_SIZE = 1000  # maximum the API allows per page


def get_json(url, params=None, retries=3):
    """GET a URL and return the parsed JSON, retrying on network errors."""
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return json.load(response)
        except OSError as error:
            if attempt == retries:
                raise
            print(f"  network error ({error}), retrying...")
            time.sleep(5 * attempt)


def fetch_all_studies():
    """Page through the search results and return all study records."""
    params = dict(QUERY_PARAMS, pageSize=PAGE_SIZE, countTotal="true")
    studies, total = [], None
    while True:
        page = get_json(API_URL, params)
        if total is None:
            total = page["totalCount"]
            print(f"Studies matching the scope: {total}")
        studies.extend(page["studies"])
        print(f"  downloaded {len(studies)} / {total}")
        token = page.get("nextPageToken")
        if not token:
            break
        params["pageToken"] = token
    if len(studies) != total:
        raise RuntimeError(f"Expected {total} studies, got {len(studies)}")
    return studies


def main():
    version = get_json(API_URL.replace("/studies", "/version"))
    data_date = version["dataTimestamp"][:10]
    snapshot_dir = RAW_DIR / f"snapshot_{data_date}"
    if snapshot_dir.exists():
        print(f"Snapshot for registry date {data_date} already exists: {snapshot_dir}")
        print("Snapshots are never overwritten. Nothing downloaded.")
        return snapshot_dir

    studies = fetch_all_studies()

    snapshot_dir.mkdir(parents=True)
    studies_file = snapshot_dir / "studies.json.gz"
    with gzip.open(studies_file, "wt", encoding="utf-8") as f:
        json.dump(studies, f)

    metadata = {
        "source": "ClinicalTrials.gov API v2",
        "endpoint": API_URL,
        "api_version": version["apiVersion"],
        "registry_data_timestamp": version["dataTimestamp"],
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "query_params": QUERY_PARAMS,
        "study_count": len(studies),
    }
    metadata_file = snapshot_dir / "metadata.json"
    metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    # Make the snapshot read-only so it cannot be changed by accident.
    for path in (studies_file, metadata_file):
        path.chmod(0o444)

    print(f"Saved {len(studies)} studies to {snapshot_dir}")
    return snapshot_dir


if __name__ == "__main__":
    main()
