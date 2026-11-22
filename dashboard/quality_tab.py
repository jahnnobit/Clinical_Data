"""
dashboard/quality_tab.py
------------------------
Part B tab of the dashboard: study data quality (query log and edit check results).

Reads the files produced by the Part B pipeline (data_quality_review/):
    output/query_log.xlsx               (queries, simulated statuses and dates)
    output/check_results_summary.csv    (catch rate)
    output/findings_injected.csv        (which records have a finding)
    data/injected/*.csv                 (number of subjects and records checked)

Two kinds of numbers:
- "Whole database" numbers (subjects, records checked, % records without a query,
  catch rate, database lock readiness) are NOT affected by the filters.
- Query numbers, charts and the top-10 table follow the filters.

The tab is shown by dashboard/app.py.
"""

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
from dash import Input, Output, dash_table, dcc, html

from theme import (BLUE, CRITICAL, GOOD, INK, INK_2, MUTED, ORANGE, SURFACE, TABLE_STYLE,
                   base_layout, empty_figure, stat_tile)

PART_ROOT = Path(__file__).resolve().parent.parent / "data_quality_review"
OUTPUT_DIR = PART_ROOT / "output"
INJECTED_DIR = PART_ROOT / "data" / "injected"

SEVERITY_ORDER = ["Critical", "Major", "Minor"]
STATUS_ORDER = ["Open", "Answered", "Closed"]


# --------------------------------------------------------------------------
# Load data once at start-up
# --------------------------------------------------------------------------

def load_inputs():
    queries = pd.read_excel(OUTPUT_DIR / "query_log.xlsx", sheet_name="Query Log", header=2)
    for col in ("Date opened", "Date answered", "Date closed"):
        queries[col] = pd.to_datetime(queries[col])
    summary = pd.read_csv(OUTPUT_DIR / "check_results_summary.csv")
    findings = pd.read_csv(OUTPUT_DIR / "findings_injected.csv", dtype=str, keep_default_na=False)
    return queries, summary, findings


QUERIES, SUMMARY, FINDINGS = load_inputs()
CHECK_ORDER = SUMMARY.loc[SUMMARY["check_id"] != "TOTAL", "check_id"].tolist()

# Whole-database numbers (not filtered). Only the columns needed are read, which
# keeps the dashboard's memory use low on a small web server.
N_SUBJECTS = pd.read_csv(INJECTED_DIR / "dm.csv", usecols=["SUBJID"], dtype=str,
                         keep_default_na=False)["SUBJID"].nunique()  # SUBJID is never changed by the injection
N_RECORDS = sum(len(pd.read_csv(INJECTED_DIR / f"{d}.csv", usecols=["STUDYID"], dtype=str))
                for d in ("dm", "ae", "vs", "lb"))
# A record with findings from two checks is counted once
N_RECORDS_WITH_FINDING = FINDINGS[["dataset", "usubjid", "record_key"]].drop_duplicates().shape[0]
PCT_CLEAN = 1 - N_RECORDS_WITH_FINDING / N_RECORDS
TOTAL = SUMMARY[SUMMARY["check_id"] == "TOTAL"].iloc[0]
CATCH_RATE = TOTAL["catch_rate"]


# --------------------------------------------------------------------------
# Small building blocks
# --------------------------------------------------------------------------

def bar_chart(counts, title, x_title, bargap=0.45):
    """Single-series column chart (one colour; the title names the series)."""
    fig = go.Figure(go.Bar(
        x=counts.index, y=counts.values, marker=dict(color=BLUE, cornerradius=4),
        text=counts.values, textposition="outside", textfont=dict(color=INK_2),
        hovertemplate="%{x}: %{y} queries<extra></extra>",
    ))
    fig.update_layout(bargap=bargap)        # wide gap keeps bars thin
    fig.update_xaxes(title=x_title, type="category")
    return base_layout(fig, title, "Queries")


# --------------------------------------------------------------------------
# Figures and tables built from the (filtered) query log
# --------------------------------------------------------------------------

def fig_by_check(q):
    if q.empty:
        return empty_figure("Queries by edit check", "No queries match the filters")
    counts = q["Check ID"].value_counts().reindex(CHECK_ORDER).dropna().astype(int)
    return bar_chart(counts, "Queries by edit check", "Check ID")


def fig_by_dataset(q):
    if q.empty:
        return empty_figure("Queries by dataset", "No queries match the filters")
    counts = q["Dataset"].value_counts().reindex(["DM", "AE", "VS", "LB"]).dropna().astype(int)
    return bar_chart(counts, "Queries by dataset", "Dataset", bargap=0.8)


def fig_over_time(q):
    """Cumulative closed queries vs queries still outstanding (open or answered), per day."""
    title = "Closed vs outstanding queries over time (simulated dates)"
    if q.empty:
        return empty_figure(title, "No queries match the filters")
    days = pd.date_range(QUERIES["Date opened"].min(), QUERIES["Date closed"].max(), freq="D")
    opened = q["Date opened"].values
    closed = q["Date closed"].dropna().values
    n_opened = [(opened <= d).sum() for d in days.values]
    n_closed = [(closed <= d).sum() for d in days.values]
    outstanding = [o - c for o, c in zip(n_opened, n_closed)]

    fig = go.Figure()
    for name, values, color in [("Closed (cumulative)", n_closed, BLUE),
                                ("Outstanding (open or answered)", outstanding, ORANGE)]:
        fig.add_trace(go.Scatter(
            x=days, y=values, name=name, mode="lines", line=dict(color=color, width=2),
            hovertemplate=f"{name}: %{{y}}<extra></extra>",
        ))
        # Direct label at the end of each line (text in ink colour, not series colour)
        fig.add_trace(go.Scatter(
            x=[days[-1]], y=[values[-1]], mode="markers+text", showlegend=False,
            marker=dict(color=color, size=8, line=dict(color=SURFACE, width=2)),
            text=[f"  {values[-1]}"], textposition="middle right", textfont=dict(color=INK),
            hoverinfo="skip",
        ))
    fig = base_layout(fig, title, "Queries")
    fig.update_layout(hovermode="x unified",
                      legend=dict(orientation="h", y=1.02, yanchor="bottom", x=1, xanchor="right"))
    fig.update_xaxes(title="Date", showspikes=True, spikecolor=MUTED, spikethickness=1)
    return fig


def top_subjects(q):
    q = q[q["USUBJID"] != "(missing)"]      # queries about a missing subject ID belong to no subject
    if q.empty:
        return []
    q = q.assign(outstanding=q["Status"].ne("Closed"), critical=q["Severity"].eq("Critical"))
    top = (q.groupby("USUBJID")
           .agg(Queries=("Query ID", "size"), Outstanding=("outstanding", "sum"),
                Critical=("critical", "sum"), Checks=("Check ID", lambda s: ", ".join(sorted(set(s)))))
           .reset_index()
           .sort_values(["Queries", "USUBJID"], ascending=[False, True])
           .head(10))
    return top.to_dict("records")


def lock_readiness():
    """Database lock requires every query to be closed. Uses the whole query log (no filters)."""
    outstanding = QUERIES[QUERIES["Status"] != "Closed"]
    n_open = int((outstanding["Status"] == "Open").sum())
    n_answered = int((outstanding["Status"] == "Answered").sum())
    ready = outstanding.empty

    blocking = (outstanding.groupby(["Check ID", "Severity"])["Status"]
                .value_counts().unstack(fill_value=0)
                .reindex(columns=["Open", "Answered"], fill_value=0)
                .reset_index())
    blocking["Total"] = blocking["Open"] + blocking["Answered"]
    blocking["sev_rank"] = blocking["Severity"].map({s: i for i, s in enumerate(SEVERITY_ORDER)})
    blocking = blocking.sort_values(["sev_rank", "Total"], ascending=[True, False]).drop(columns="sev_rank")

    icon, text, color = (("✓", "Ready for database lock", GOOD) if ready else
                         ("✕", "Not ready for database lock", CRITICAL))
    return html.Div(className="panel", children=[
        html.H3("Database lock readiness"),
        html.Div(className="lock-status", children=[
            html.Span(icon, className="lock-icon", style={"backgroundColor": color}),
            html.Span(text, className="lock-text"),
        ]),
        html.P(f"Lock criterion: all queries closed. Outstanding: {len(outstanding)} "
               f"({n_open} open, {n_answered} answered and awaiting data management review). "
               f"Whole database, not affected by filters.", className="muted"),
        html.P("Checks blocking the lock:", className="subhead"),
        dash_table.DataTable(
            data=blocking.to_dict("records"),
            columns=[{"name": c, "id": c} for c in ["Check ID", "Severity", "Open", "Answered", "Total"]],
            style_as_list_view=True, page_size=20, **TABLE_STYLE,
        ),
    ])


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------

def dropdown(id_, label, options):
    return html.Div(className="filter", children=[
        html.Label(label, htmlFor=id_),
        dcc.Dropdown(id=id_, options=options, value=[], multi=True, placeholder="All"),
    ])


def layout():
    return html.Div(children=[
        html.Header(children=[
            html.H2("Part B: Study data quality review"),
            html.P("Edit checks and query management on CDISC pilot SDTM data (DM, AE, VS, LB). "
                   "Public data with deliberately injected errors; "
                   "query statuses and dates are simulated.", className="muted"),
        ]),

        html.Section(className="tiles", children=[
            stat_tile("Subjects", f"{N_SUBJECTS:,}", "in DM"),
            stat_tile("Records checked", f"{N_RECORDS:,}", "DM + AE + VS + LB"),
            html.Div(id="q-tile-queries", className="tile-wrap"),
            html.Div(id="q-tile-open", className="tile-wrap"),
            stat_tile("Records without any query", f"{PCT_CLEAN:.1%}",
                      f"{N_RECORDS - N_RECORDS_WITH_FINDING:,} of {N_RECORDS:,}"),
            stat_tile("Catch rate", f"{CATCH_RATE:.0%}",
                      f"{int(TOTAL['errors_caught'])} of {int(TOTAL['errors_injected'])} injected errors found"),
        ]),

        html.Section(className="filters", children=[
            dropdown("q-f-dataset", "Dataset", ["DM", "AE", "VS", "LB"]),
            dropdown("q-f-severity", "Severity", SEVERITY_ORDER),
            dropdown("q-f-status", "Status", STATUS_ORDER),
            html.P("Filters apply to query counts, charts and the top-10 table.", className="muted small"),
        ]),

        html.Section(className="grid-2", children=[
            html.Div(className="panel", children=[dcc.Graph(id="q-g-check", config={"displayModeBar": False})]),
            html.Div(className="panel", children=[dcc.Graph(id="q-g-dataset", config={"displayModeBar": False})]),
        ]),
        html.Section(className="panel", children=[dcc.Graph(id="q-g-time", config={"displayModeBar": False})]),

        html.Section(className="grid-2", children=[
            html.Div(className="panel", children=[
                html.H3("Top 10 subjects by number of queries"),
                dash_table.DataTable(
                    id="q-t-subjects",
                    columns=[{"name": c, "id": c} for c in ["USUBJID", "Queries", "Outstanding", "Critical", "Checks"]],
                    style_as_list_view=True, **TABLE_STYLE,
                ),
            ]),
            lock_readiness(),
        ]),
    ])


# --------------------------------------------------------------------------
# Callback: re-draw everything that depends on the filters
# --------------------------------------------------------------------------

def register_callbacks(app):
    app.callback(
        Output("q-tile-queries", "children"), Output("q-tile-open", "children"),
        Output("q-g-check", "figure"), Output("q-g-dataset", "figure"), Output("q-g-time", "figure"),
        Output("q-t-subjects", "data"),
        Input("q-f-dataset", "value"), Input("q-f-severity", "value"), Input("q-f-status", "value"),
    )(update)


def update(datasets, severities, statuses):
    q = QUERIES
    if datasets:
        q = q[q["Dataset"].isin(datasets)]
    if severities:
        q = q[q["Severity"].isin(severities)]
    if statuses:
        q = q[q["Status"].isin(statuses)]
    n_open = int((q["Status"] == "Open").sum())
    return (
        stat_tile("Queries raised", f"{len(q):,}", "after filters"),
        stat_tile("Open queries", f"{n_open:,}", "awaiting site response"),
        fig_by_check(q), fig_by_dataset(q), fig_over_time(q), top_subjects(q),
    )

