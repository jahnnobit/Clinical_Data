"""
dashboard/app.py
----------------
Clinical Trial Oversight Toolkit dashboard (Plotly Dash), with one tab per part:

    Part A  Trial portfolio monitor      (dashboard/portfolio_tab.py)
    Part B  Study data quality review    (dashboard/quality_tab.py)

Run locally from the project root (after python run_all.py):
    python dashboard/app.py
then open http://127.0.0.1:8050 in a browser.

On a web server (e.g. Render) the app is started by gunicorn instead:
    gunicorn --chdir dashboard app:server
"""

import os

from dash import Dash, dcc, html

import portfolio_tab
import quality_tab

app = Dash(__name__, title="Clinical Trial Oversight Toolkit")
server = app.server   # the WSGI server object gunicorn runs

app.layout = html.Div(className="page", children=[
    html.Header(children=[
        html.H1("Clinical Trial Oversight Toolkit"),
        html.P("Portfolio project on public data: oversight of a live trial portfolio "
               "(Part A) and a data quality review inside one study (Part B). "
               "Not real clinical trial work.", className="muted"),
    ]),
    dcc.Tabs(className="tabs", parent_className="tabs-parent", children=[
        dcc.Tab(label="Part A: Trial portfolio monitor", className="tab",
                selected_className="tab--selected", children=[portfolio_tab.layout()]),
        dcc.Tab(label="Part B: Study data quality review", className="tab",
                selected_className="tab--selected", children=[quality_tab.layout()]),
    ]),
])

portfolio_tab.register_callbacks(app)
quality_tab.register_callbacks(app)


if __name__ == "__main__":
    # Locally: http://127.0.0.1:8050. A host that sets PORT gets 0.0.0.0:PORT.
    port = int(os.environ.get("PORT", 8050))
    host = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"
    app.run(host=host, port=port, debug=False)
