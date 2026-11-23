"""Statcast umpire and pitch dashboard.

Reads the small Parquet exports written by `python -m statcast_pipeline.publish`
(dashboard/data/), so it needs no database connection.

    streamlit run dashboard/app.py
"""

import streamlit as st
from views import arsenal_page, health, health_page, two_strike_page, umpires_page

st.set_page_config(page_title="Statcast umpire & pitch dashboard", page_icon="⚾", layout="wide")

if health().get("sample_data"):
    st.warning("Showing generated **sample data**, not real MLB results. Run the pipeline and "
               "`python -m statcast_pipeline.publish` to publish real data.", icon="🧪")

nav = st.navigation([
    st.Page(two_strike_page, title="The two-strike zone", icon="🎯", url_path="two-strike", default=True),
    st.Page(umpires_page, title="Umpires", icon="🧑‍⚖️", url_path="umpires"),
    st.Page(arsenal_page, title="Pitcher arsenals", icon="⚾", url_path="arsenals"),
    st.Page(health_page, title="Pipeline health", icon="🩺", url_path="health"),
])
with st.sidebar:
    st.caption("Data: Baseball Savant (Statcast) and the MLB Stats API, via an automated ELT pipeline "
               "(Python, DuckDB, dbt, Airflow). Not affiliated with MLB.")
nav.run()
