"""
dashboard/theme.py
------------------
Colours and small building blocks shared by both dashboard tabs.
"""

import plotly.graph_objects as go
from dash import html

# Colours (validated default data-viz palette: categorical slots 1-2, status colours)
BLUE, ORANGE = "#2a78d6", "#eb6834"
CRITICAL, GOOD = "#d03b3b", "#0ca30c"
INK, INK_2, MUTED, GRID, BASELINE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SURFACE = "#fcfcfb"
FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif'

TABLE_STYLE = dict(
    style_header={"fontWeight": "600", "backgroundColor": SURFACE, "color": INK,
                  "borderBottom": f"1px solid {BASELINE}"},
    style_cell={"fontFamily": FONT, "fontSize": "13px", "color": INK_2, "padding": "6px 10px",
                "textAlign": "left", "backgroundColor": SURFACE, "border": "none",
                "borderBottom": f"1px solid {GRID}", "fontVariantNumeric": "tabular-nums"},
)


def stat_tile(label, value, note=""):
    return html.Div(className="tile", children=[
        html.Div(label, className="tile-label"),
        html.Div(value, className="tile-value"),
        html.Div(note, className="tile-note"),
    ])


def base_layout(fig, title, y_title):
    """Shared, quiet chart styling: hairline grid, muted axes, system font."""
    fig.update_layout(
        title=dict(text=title, x=0, xanchor="left", font=dict(size=15, color=INK)),
        font=dict(family=FONT, size=12, color=INK_2),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE,
        margin=dict(l=48, r=24, t=48, b=48),
        hoverlabel=dict(bgcolor="white", font=dict(family=FONT, color=INK)),
    )
    fig.update_xaxes(showgrid=False, linecolor=BASELINE, tickfont=dict(color=MUTED))
    fig.update_yaxes(title=y_title, gridcolor=GRID, zeroline=False, tickfont=dict(color=MUTED),
                     rangemode="tozero")
    return fig


def empty_figure(title, message):
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(color=MUTED, size=14))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return base_layout(fig, title, "")
