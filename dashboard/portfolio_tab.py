"""
dashboard/portfolio_tab.py
--------------------------
Part A tab of the dashboard: portfolio overview of EU Phase 3 oncology trials
from the ClinicalTrials.gov snapshot.

Reads the tables built by portfolio_monitor/src/build_tables.py:
    data/processed/studies.csv   (one row per study)
    data/processed/sites.csv     (one row per site)
    data/raw/snapshot_*/metadata.json   (registry date of the snapshot)

The filters (sponsor type, status) apply to every number and chart on the tab.
The tab is shown by dashboard/app.py.
"""

import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dcc, html

from theme import BLUE, INK_2, base_layout, empty_figure, stat_tile

PART_ROOT = Path(__file__).resolve().parent.parent / "portfolio_monitor"
PROCESSED_DIR = PART_ROOT / "data" / "processed"

# Registry status codes in life-cycle order, with readable labels
STATUS_LABELS = {
    "NOT_YET_RECRUITING": "Not yet recruiting",
    "RECRUITING": "Recruiting",
    "ENROLLING_BY_INVITATION": "Enrolling by invitation",
    "ACTIVE_NOT_RECRUITING": "Active, not recruiting",
    "SUSPENDED": "Suspended",
    "COMPLETED": "Completed",
    "TERMINATED": "Terminated",
    "WITHDRAWN": "Withdrawn",
    "UNKNOWN": "Unknown (not verified for 2+ years)",
}
SPONSOR_TYPES = ["Industry", "Academic & other"]
NO_MATCH = "No studies match the filters"


def load_inputs():
    studies = pd.read_csv(PROCESSED_DIR / "studies.csv", dtype={"nct_id": str})
    studies["sponsor_type"] = studies["sponsor_class"].map(
        lambda c: "Industry" if c == "INDUSTRY" else "Academic & other")
    studies["status_label"] = studies["overall_status"].map(STATUS_LABELS)
    studies["start_year"] = studies["start_date"].str[:4].astype(int)
    # Only EU sites are needed here; reading three columns keeps memory low.
    sites = pd.read_csv(PROCESSED_DIR / "sites.csv", usecols=["nct_id", "country", "is_eu"])
    eu_sites = sites[sites["is_eu"]].drop(columns="is_eu")
    snapshot = sorted((PART_ROOT / "data" / "raw").glob("snapshot_*"))[-1]
    metadata = json.loads((snapshot / "metadata.json").read_text(encoding="utf-8"))
    return studies, eu_sites, metadata


STUDIES, EU_SITES, METADATA = load_inputs()
REGISTRY_DATE = METADATA["registry_data_timestamp"][:10]


def hbar(counts, title, x_title, unit, height=380):
    """Horizontal bar chart, largest at the top (one series, one colour)."""
    counts = counts.iloc[::-1]          # plotly draws the first bar at the bottom
    fig = go.Figure(go.Bar(
        x=counts.values, y=counts.index, orientation="h",
        marker=dict(color=BLUE, cornerradius=4),
        text=[f"{v:,}" for v in counts.values], textposition="outside",
        textfont=dict(color=INK_2), cliponaxis=False,
        hovertemplate=f"%{{y}}: %{{x:,}} {unit}<extra></extra>",
    ))
    fig = base_layout(fig, title, "")
    fig.update_layout(bargap=0.35, height=height,
                      margin=dict(l=8, r=48, t=48, b=40))
    fig.update_xaxes(title=x_title, showgrid=True, gridcolor="#e1e0d9", rangemode="tozero")
    fig.update_yaxes(showgrid=False, automargin=True, type="category")
    return fig


def fig_status(s):
    if s.empty:
        return empty_figure("Studies by status", NO_MATCH)
    order = [label for label in STATUS_LABELS.values() if label in set(s["status_label"])]
    counts = s["status_label"].value_counts().reindex(order)   # life-cycle order, top-down
    return hbar(counts, "Studies by status", "Studies", "studies")


def fig_start_year(s):
    title = "Studies by start year (recent years include planned start dates)"
    if s.empty:
        return empty_figure(title, NO_MATCH)
    counts = s["start_year"].value_counts().sort_index()
    fig = go.Figure(go.Bar(
        x=counts.index.astype(str), y=counts.values, marker=dict(color=BLUE, cornerradius=4),
        hovertemplate="%{x}: %{y} studies<extra></extra>",
    ))
    fig = base_layout(fig, title, "Studies")
    fig.update_layout(bargap=0.45, height=320)
    fig.update_xaxes(title="Start year", type="category")
    return fig


def fig_sponsors(s):
    if s.empty:
        return empty_figure("Top 10 lead sponsors", NO_MATCH)
    counts = s["lead_sponsor"].value_counts().head(10)
    return hbar(counts, "Top 10 lead sponsors", "Studies", "studies")


def fig_eu_countries(s):
    if s.empty:
        return empty_figure("EU sites by country", NO_MATCH)
    counts = EU_SITES[EU_SITES["nct_id"].isin(s["nct_id"])]["country"].value_counts()
    return hbar(counts, "EU sites by country", "Sites", "sites", height=60 + 24 * len(counts))


def dropdown(id_, label, options):
    return html.Div(className="filter", children=[
        html.Label(label, htmlFor=id_),
        dcc.Dropdown(id=id_, options=options, value=[], multi=True, placeholder="All"),
    ])


def layout():
    graph = lambda id_: dcc.Graph(id=id_, config={"displayModeBar": False})
    return html.Div(children=[
        html.Header(children=[
            html.H2("Part A: Trial portfolio monitor"),
            html.P(f"Phase 3 interventional oncology trials with at least one EU site, started "
                   f"2015 or later. Live public data from ClinicalTrials.gov, snapshot of "
                   f"{REGISTRY_DATE}.", className="muted"),
        ]),
        html.Section(id="p-tiles", className="tiles"),
        html.Section(className="filters", children=[
            dropdown("p-f-sponsor", "Sponsor type", SPONSOR_TYPES),
            dropdown("p-f-status", "Status",
                     [{"label": v, "value": k} for k, v in STATUS_LABELS.items()]),
            html.Div(),
            html.P("Filters apply to every number and chart on this tab.", className="muted small"),
        ]),
        html.Section(className="grid-2", children=[
            html.Div(className="panel", children=[graph("p-g-status")]),
            html.Div(className="panel", children=[graph("p-g-sponsors")]),
        ]),
        html.Section(className="panel", children=[graph("p-g-year")]),
        html.Section(className="panel", children=[graph("p-g-countries")]),
    ])


def tiles(s):
    eu = EU_SITES[EU_SITES["nct_id"].isin(s["nct_id"])]
    return [
        stat_tile("Studies", f"{len(s):,}", "after filters"),
        stat_tile("Lead sponsors", f"{s['lead_sponsor'].nunique():,}", "organisations"),
        stat_tile("EU sites", f"{len(eu):,}", f"in {eu['country'].nunique()} EU countries"),
        stat_tile("Recruiting now", f"{(s['overall_status'] == 'RECRUITING').sum():,}",
                  "registry status"),
    ]


def update(sponsor_types, statuses):
    s = STUDIES
    if sponsor_types:
        s = s[s["sponsor_type"].isin(sponsor_types)]
    if statuses:
        s = s[s["overall_status"].isin(statuses)]
    return tiles(s), fig_status(s), fig_start_year(s), fig_sponsors(s), fig_eu_countries(s)


def register_callbacks(app):
    app.callback(
        Output("p-tiles", "children"),
        Output("p-g-status", "figure"), Output("p-g-year", "figure"),
        Output("p-g-sponsors", "figure"), Output("p-g-countries", "figure"),
        Input("p-f-sponsor", "value"), Input("p-f-status", "value"),
    )(update)
