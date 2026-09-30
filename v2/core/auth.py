"""Centralized POC authentication, session and authorization helpers."""
from __future__ import annotations

import streamlit as st

from components.login_ui import render_login_ui
from services.auth_service import (
    ROLE_ADMIN,
    ROLE_USER,
    authenticate,
    bootstrap_admin_from_environment,
    ensure_auth_table,
)


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
    """Render the unauthenticated entry screen without mixing UI into auth logic."""
    return render_login_ui(login)


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
    user = current_user()
    if not user:
        st.stop()
    if user.get("role") == ROLE_ADMIN:
        return
    if page_title not in {"🏠 Dashboard Home", "👤 Individual Assessment & Talent Profile"}:
        st.error("⛔ This area is restricted to administrators.")
        st.stop()


def render_user_identity() -> None:
    user = current_user()
    if not user:
        return
    identity_col, logout_col = st.columns([6, 1])
    with identity_col:
        label = user.get("display_name") or user.get("username")
        st.caption(f"Signed in as **{label}** · **{user.get('role', 'USER')}**")
    with logout_col:
        if st.button("Logout", key="v2_logout_button", use_container_width=True):
            logout()
