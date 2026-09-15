"""V2 dashboard entry point.

Every v2 page is registered through Streamlit's explicit navigation API.
Pages own their UI and call shared v2 services/analytics rather than loading
branches from the legacy root app.
"""
import streamlit as st

from core import bootstrap  # noqa: F401,E402
from core.pages import PAGES

pg = st.navigation(PAGES, position="hidden")
pg.run()
