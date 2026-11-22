"""
portfolio_config.py
-------------------
One place for the project's scope and folder paths.

Scope (agreed before building):
- Disease area: oncology. ClinicalTrials.gov expands the condition search
  "cancer" to its synonyms (e.g. neoplasm, tumour, carcinoma).
- Region: at least one trial site in one of the 27 EU member states.
- Study type: interventional, Phase 3 (the pivotal trials a clinical project
  manager typically runs).
- Start date: 1 January 2015 or later, so the portfolio is recent.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR = PROJECT_ROOT / "output"
DOCS_DIR = PROJECT_ROOT / "docs"

API_URL = "https://clinicaltrials.gov/api/v2/studies"

# The 27 EU member states, spelled as ClinicalTrials.gov stores them.
# Czechia is listed under both names in the registry, so both are included.
EU_COUNTRIES = [
    "Austria", "Belgium", "Bulgaria", "Croatia", "Cyprus", "Czech Republic",
    "Czechia", "Denmark", "Estonia", "Finland", "France", "Germany", "Greece",
    "Hungary", "Ireland", "Italy", "Latvia", "Lithuania", "Luxembourg", "Malta",
    "Netherlands", "Poland", "Portugal", "Romania", "Slovakia", "Slovenia",
    "Spain", "Sweden",
]


def _quoted(name):
    """Essie search syntax needs quotes around names with spaces."""
    return f'"{name}"' if " " in name else name


QUERY_PARAMS = {
    "query.cond": "cancer",
    "query.term": (
        "AREA[LocationCountry](" + " OR ".join(_quoted(c) for c in EU_COUNTRIES) + ")"
        " AND AREA[StudyType]INTERVENTIONAL"
        " AND AREA[Phase]PHASE3"
        " AND AREA[StartDate]RANGE[2015-01-01,MAX]"
    ),
    # Only the registration data and the results flag. The full results
    # section is large and not needed for portfolio monitoring.
    "fields": "protocolSection,hasResults",
}
