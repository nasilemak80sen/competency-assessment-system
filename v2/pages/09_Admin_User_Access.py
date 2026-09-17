"""Admin-only POC user and role management."""
from __future__ import annotations

import streamlit as st

from components.navigation import render_header, render_navigation
from core.auth import current_user, require_roles
from core.bootstrap import get_master_data
from services.auth_service import ROLE_ADMIN, ROLE_USER, create_user, list_users, reset_password, set_active
from core.bootstrap import open_session

require_roles(ROLE_ADMIN)
render_navigation()
render_header("🔐 Admin: User Access Management", "Create and maintain POC USER / ADMIN access accounts")

user = current_user()
st.caption(f"Signed in as **{user.get('display_name') or user.get('username')}** · **ADMIN**")

personnel_df = get_master_data()
personnel_options = {}
if personnel_df is not None and not personnel_df.empty and "id" in personnel_df.columns:
    for _, row in personnel_df.dropna(subset=["id"]).iterrows():
        label = f"{row.get('Name', 'Unknown')} · {row.get('Staff ID', 'N/A')}"
        personnel_options[label] = int(row["id"])

create_tab, users_tab = st.tabs(["➕ Create Account", "👥 Existing Accounts"])

with create_tab:
    st.info("USER accounts must be linked to one personnel record. ADMIN accounts have full system access.")
    with st.form("create_app_user_form"):
        c1, c2 = st.columns(2)
        with c1:
            username = st.text_input("Username", placeholder="firstname.lastname")
            display_name = st.text_input("Display Name")
            role = st.selectbox("Role", [ROLE_USER, ROLE_ADMIN])
        with c2:
            password = st.text_input("Initial Password", type="password")
            password_confirm = st.text_input("Confirm Password", type="password")
            personnel_label = None
            if role == ROLE_USER:
                if personnel_options:
                    personnel_label = st.selectbox("Linked Personnel", sorted(personnel_options))
                else:
                    st.warning("No personnel records are available for USER account linking.")
        submitted = st.form_submit_button("Create Account", type="primary")

    if submitted:
        if password != password_confirm:
            st.error("Passwords do not match.")
        elif role == ROLE_USER and not personnel_label:
            st.error("Select the personnel record that owns this account.")
        else:
            session = open_session()
            try:
                personnel_id = personnel_options.get(personnel_label) if personnel_label else None
                ok, message, _ = create_user(username, password, role, personnel_id=personnel_id, display_name=display_name or username)
                if ok:
                    st.success(message)
                else:
                    st.error(message)
            finally:
                session.close()

with users_tab:
    users = list_users()
    if not users:
        st.info("No application accounts have been created yet.")
    for account in users:
        card = st.container(border=True)
        with card:
            c1, c2, c3 = st.columns([3, 2, 2])
            with c1:
                st.markdown(f"**{account['display_name'] or account['username']}**")
                st.caption(account["username"])
            with c2:
                st.caption(f"Role: **{account['role']}**")
                st.caption(f"Personnel ID: **{account['personnel_id'] or 'N/A'}**")
            with c3:
                st.caption("Active" if account["is_active"] else "Disabled")
                toggle_label = "Disable" if account["is_active"] else "Enable"
                if st.button(toggle_label, key=f"toggle_user_{account['id']}"):
                    ok, message = set_active(account["id"], not bool(account["is_active"]))
                    if ok:
                        st.success(message)
                        st.rerun()
            with st.expander("Reset password"):
                with st.form(f"reset_password_{account['id']}"):
                    new_password = st.text_input("New Password", type="password", key=f"new_pw_{account['id']}")
                    confirm = st.text_input("Confirm New Password", type="password", key=f"confirm_pw_{account['id']}")
                    reset = st.form_submit_button("Reset Password")
                if reset:
                    if new_password != confirm:
                        st.error("Passwords do not match.")
                    else:
                        ok, message = reset_password(account["id"], new_password)
                        if ok: st.success(message)
                        else: st.error(message)
