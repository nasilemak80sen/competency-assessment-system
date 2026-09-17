"""Centralized POC authentication, session and authorization helpers."""
from __future__ import annotations
import streamlit as st
from components import navigation as _navigation_module
from services.auth_service import ROLE_ADMIN, ROLE_USER, authenticate, bootstrap_admin_from_environment, ensure_auth_table


def initialize_auth() -> None:
    ensure_auth_table()
    bootstrap_admin_from_environment()


def current_user() -> dict | None:
    return st.session_state.get("auth_user")


def is_authenticated() -> bool:
    return current_user() is not None


def is_admin() -> bool:
    user = current_user()
    return bool(user and user.get("role") == ROLE_ADMIN)


def is_user() -> bool:
    user = current_user()
    return bool(user and user.get("role") == ROLE_USER)


def personnel_id() -> int | None:
    user = current_user()
    if not user or user.get("personnel_id") is None:
        return None
    return int(user["personnel_id"])


def login(username: str, password: str) -> bool:
    user = authenticate(username, password)
    if user is None:
        return False
    st.session_state.auth_user = user
    return True


def logout() -> None:
    st.session_state.pop("auth_user", None)
    st.session_state.pop("current_page", None)
    st.rerun()


def render_login() -> bool:
    """Render login gate. Returns True only for an authenticated session."""
    if is_authenticated():
        return True
    st.markdown("# 🔐 RE Competency Assessment System")
    st.caption("POC secure access — sign in to continue")
    left, center, right = st.columns([1, 2, 1])
    with center:
        with st.form("poc_login_form"):
            username = st.text_input("Username", autocomplete="username")
            password = st.text_input("Password", type="password", autocomplete="current-password")
            submitted = st.form_submit_button("🔐 Sign In", type="primary")
        if submitted:
            if login(username, password):
                st.rerun()
            else:
                st.error("Invalid username/password or inactive account.")
        if not st.session_state.get("auth_user"):
            st.info("POC note: the first admin account can be bootstrapped from POC_ADMIN_USERNAME / POC_ADMIN_PASSWORD environment variables.")
    return False


def require_roles(*roles: str) -> bool:
    user = current_user()
    if user is None:
        st.error("Authentication required.")
        st.stop()
    if user.get("role") not in set(roles):
        st.error("⛔ You do not have access to this page.")
        st.stop()
    return True


def enforce_page_access(page_title: str) -> None:
    """Block direct navigation to restricted pages even when visible nav is hidden."""
    user = current_user()
    if not user:
        st.stop()
    if user.get("role") == ROLE_ADMIN:
        return
    allowed = {"🏠 Dashboard Home", "👤 Individual Assessment & Talent Profile"}
    if page_title not in allowed:
        st.error("⛔ This area is restricted to administrators.")
        st.stop()


def render_user_identity() -> None:
    """Render a small identity/logout control in the shared top bar."""
    user = current_user()
    if not user:
        return
    with st.container():
        identity_col, logout_col = st.columns([6, 1])
        with identity_col:
            label = user.get("display_name") or user.get("username")
            st.caption(f"Signed in as **{label}** · **{user.get('role', 'USER')}**")
        with logout_col:
            if st.button("Logout", key="v2_logout_button", use_container_width=True):
                logout()
