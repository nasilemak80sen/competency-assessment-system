"""V2 dashboard entry point.

The dashboard is rendered from the original app.py branch without changing
its UI or business rules. This is the first exact-parity migration step.
"""

import streamlit as st

from core.bootstrap import initialise_session
from core.legacy_runtime import render_legacy_page

st.set_page_config(
    page_title="RE Fraternity | Dashboard",
    page_icon="📊",
    layout="wide",
)

initialise_session()
render_legacy_page("🏠 Dashboard Home")
