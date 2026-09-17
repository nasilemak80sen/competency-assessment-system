"""V2 dashboard entry point with POC authentication/RBAC gate."""
import streamlit as st

from core import bootstrap  # noqa: F401,E402
from core.auth import enforce_page_access, initialize_auth, render_login, render_user_identity
from core.pages import PAGES
from core.theme import apply_theme

st.set_page_config(page_title=bootstrap.APP_TITLE, page_icon="📊", layout="wide", initial_sidebar_state="collapsed", menu_items=None)
apply_theme()
initialize_auth()
if not render_login():
    st.stop()
render_user_identity()

st.session_state["_v2_navigation_rendered"] = False
pg = st.navigation(PAGES, position="hidden")
st.session_state.current_page = pg.title
enforce_page_access(pg.title)
pg.run()
