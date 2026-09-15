"""V2 dashboard entry point.

The root app.py remains the golden reference. V2 owns a canonical Streamlit
page registry while sharing the same visual theme and data-loading contract.
"""
import streamlit as st

from core import bootstrap  # noqa: F401,E402
from core.pages import PAGES
from core.theme import apply_theme

st.set_page_config(
    page_title=bootstrap.APP_TITLE,
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items=None,
)
apply_theme()

pg = st.navigation(PAGES, position="hidden")
pg.run()
