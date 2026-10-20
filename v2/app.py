"""V2 dashboard entry point with POC authentication/RBAC gate."""
import streamlit as st

from core import bootstrap  # noqa: F401,E402
from core.auth import initialize_auth, is_admin, render_login, render_user_identity
from core.pages import PAGES, USER_PAGES
from core.theme import apply_theme

st.set_page_config(page_title=bootstrap.APP_TITLE, page_icon="📊", layout="wide", initial_sidebar_state="collapsed", menu_items=None)
apply_theme()
initialize_auth()
if not render_login():
    st.stop()
render_user_identity()

st.session_state["_v2_navigation_rendered"] = False
pages = PAGES if is_admin() else USER_PAGES
pg = st.navigation(pages, position="hidden")
st.session_state.current_page = pg.title
pg.run()
