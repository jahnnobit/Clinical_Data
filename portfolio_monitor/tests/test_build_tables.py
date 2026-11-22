"""Unit tests for build_tables.py, using small hand-made study records."""

from build_tables import build_tables, flatten_study


def make_study(nct_id="NCT00000001", countries=("Germany", "United States"), **status):
    """A minimal registry record with one site per country given."""
    return {
        "hasResults": False,
        "protocolSection": {
            "identificationModule": {"nctId": nct_id, "briefTitle": "Test study"},
            "statusModule": {
                "overallStatus": "COMPLETED",
                "primaryCompletionDateStruct": {"date": "2024-05", "type": "ACTUAL"},
                **status,
            },
            "designModule": {"phases": ["PHASE2", "PHASE3"],
                             "enrollmentInfo": {"count": 120, "type": "ACTUAL"}},
            "contactsLocationsModule": {
                "locations": [{"facility": f"Site {c}", "city": "X", "country": c}
                              for c in countries]
            },
        },
    }


def test_flatten_counts_eu_and_non_eu_sites():
    row, sites = flatten_study(make_study(countries=("Germany", "France", "Japan")))
    assert row["n_sites"] == 3
    assert row["n_eu_sites"] == 2
    assert row["eu_countries"] == "France; Germany"
    assert [s["is_eu"] for s in sites] == [True, True, False]


def test_month_only_date_kept_as_registered():
    row, _ = flatten_study(make_study())
    assert row["primary_completion_date"] == "2024-05"
    assert row["primary_completion_type"] == "ACTUAL"


def test_missing_fields_become_empty_not_errors():
    row, _ = flatten_study(make_study())
    assert row["why_stopped"] is None
    assert row["completion_date"] is None
    assert row["phase"] == "PHASE2/PHASE3"


def test_build_tables_one_row_per_study_and_site():
    studies_df, sites_df = build_tables([make_study("NCT1"), make_study("NCT2", ("Spain",))])
    assert list(studies_df["nct_id"]) == ["NCT1", "NCT2"]
    assert len(sites_df) == 3
