"""Admin-only user directory, role/personnel linking, and access audit."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from components.navigation import render_header, render_navigation
from core.auth import current_user, require_roles
from core.bootstrap import open_session
from models import Personnel
from services.auth_service import (
    ROLE_ADMIN,
    ROLE_USER,
    create_user,
    list_auth_audit,
    list_users,
    reset_password,
    set_active,
    update_user_access,
)

require_roles(ROLE_ADMIN)
render_navigation()
render_header(
    "🔐 Admin: User Access Management",
    "Search application accounts, manage access and personnel links, and review administrator actions.",
)

user = current_user() or {}
actor_name = user.get("display_name") or user.get("username") or "Administrator"
st.caption(f"Signed in as **{actor_name}** · **ADMIN**")


def _load_personnel_options() -> tuple[dict[str, int], str | None]:
    """Return active, non-deleted SQL personnel records for secure account linking."""
    session = open_session()
    try:
        rows = (
            session.query(Personnel)
            .filter(Personnel.is_deleted.is_(False))
            .order_by(Personnel.name.asc(), Personnel.staff_id.asc())
            .all()
        )
        return {
            f"{person.name} · {person.staff_id}": int(person.id)
            for person in rows
        }, None
    except Exception as exc:
        return {}, str(exc)
    finally:
        session.close()


personnel_options, personnel_error = _load_personnel_options()
personnel_by_id = {value: label for label, value in personnel_options.items()}

create_tab, directory_tab, audit_tab = st.tabs(
    ["➕ Create Account", "👥 User Directory", "🧾 Access Audit"]
)

with create_tab:
    st.subheader("Create a new account")
    st.info(
        "USER accounts must be linked to one active personnel record. "
        "ADMIN accounts are system-wide and do not have a personnel link."
    )
    if personnel_error:
        st.error(f"Unable to load personnel records: {personnel_error}")

    with st.form("create_app_user_form_v3", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            username = st.text_input("Username", placeholder="firstname.lastname")
            display_name = st.text_input("Display name")
            role = st.selectbox("Role", [ROLE_USER, ROLE_ADMIN])
        with c2:
            password = st.text_input("Initial password", type="password")
            password_confirm = st.text_input("Confirm password", type="password")
            personnel_label = None
            if role == ROLE_USER:
                if personnel_options:
                    personnel_label = st.selectbox(
                        "Linked personnel",
                        sorted(personnel_options),
                        help="Select the database personnel record owned by this account.",
                    )
                else:
                    st.warning("No active personnel records are available for USER linking.")
        submitted = st.form_submit_button(
            "Create account", type="primary", use_container_width=True
        )

    if submitted:
        if password != password_confirm:
            st.error("Passwords do not match.")
        elif role == ROLE_USER and not personnel_label:
            st.error("Select the personnel record that owns this account.")
        else:
            personnel_id = personnel_options.get(personnel_label) if personnel_label else None
            ok, message, _ = create_user(
                username,
                password,
                role,
                personnel_id=personnel_id,
                display_name=display_name or username,
                actor=user,
            )
            if ok:
                st.success(message)
                st.rerun()
            else:
                st.error(message)

with directory_tab:
    st.subheader("Searchable user directory")
    search_term = st.text_input(
        "Search accounts",
        placeholder="Username, display name, personnel name, Staff ID or department",
        key="user_directory_search",
    )
    accounts = list_users(search_term)
    if not accounts:
        st.info("No accounts match the current search.")
    else:
        directory = pd.DataFrame(
            [
                {
                    "Display name": account["display_name"] or account["username"],
                    "Username": account["username"],
                    "Role": account["role"],
                    "Personnel": account.get("personnel_name") or "—",
                    "Staff ID": account.get("personnel_staff_id") or "—",
                    "Department": account.get("personnel_department") or "—",
                    "Status": "Active" if account["is_active"] else "Disabled",
                    "Last login": account.get("last_login") or "Never",
                }
                for account in accounts
            ]
        )
        st.dataframe(directory, width="stretch", hide_index=True)

        account_labels = {
            (
                f"{account['display_name'] or account['username']} · "
                f"{account['username']} · {account['role']}"
            ): int(account["id"])
            for account in accounts
        }
        selected_label = st.selectbox(
            "Select an account to manage",
            list(account_labels),
            key="user_directory_selected_account",
        )
        selected_id = account_labels[selected_label]
        account = next(row for row in accounts if int(row["id"]) == selected_id)

        with st.container(border=True):
            st.markdown(f"**{account['display_name'] or account['username']}**")
            st.caption(
                f"{account['username']} · Created {account['created_at']} · "
                f"Last login: {account.get('last_login') or 'Never'}"
            )

            with st.form(f"edit_user_access_{selected_id}"):
                new_role = st.selectbox(
                    "Account role",
                    [ROLE_USER, ROLE_ADMIN],
                    index=[ROLE_USER, ROLE_ADMIN].index(account["role"]),
                    key=f"user_role_{selected_id}",
                )
                current_link_label = personnel_by_id.get(account.get("personnel_id"))
                linked_personnel_label = None
                if new_role == ROLE_USER:
                    if personnel_options:
                        options = sorted(personnel_options)
                        default_index = (
                            options.index(current_link_label)
                            if current_link_label in options else 0
                        )
                        linked_personnel_label = st.selectbox(
                            "Linked personnel",
                            options,
                            index=default_index,
                            key=f"user_personnel_link_{selected_id}",
                        )
                    else:
                        st.warning("No active personnel records are available.")
                else:
                    st.caption("ADMIN accounts are not linked to an individual personnel record.")
                save_access = st.form_submit_button(
                    "Save role and personnel link", type="primary"
                )

            if save_access:
                personnel_id = (
                    personnel_options.get(linked_personnel_label)
                    if new_role == ROLE_USER and linked_personnel_label else None
                )
                ok, message = update_user_access(
                    selected_id, new_role, personnel_id, actor=user
                )
                if ok:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)

            action_col, password_col = st.columns(2)
            with action_col:
                status_label = "Disable account" if account["is_active"] else "Enable account"
                if st.button(status_label, key=f"toggle_user_{selected_id}"):
                    ok, message = set_active(
                        selected_id, not bool(account["is_active"]), actor=user
                    )
                    if ok:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
            with password_col:
                with st.expander("Reset password"):
                    with st.form(f"reset_password_{selected_id}"):
                        new_password = st.text_input(
                            "New password", type="password",
                            key=f"new_pw_{selected_id}",
                        )
                        confirm_password = st.text_input(
                            "Confirm new password", type="password",
                            key=f"confirm_pw_{selected_id}",
                        )
                        reset = st.form_submit_button("Reset password")
                    if reset:
                        if new_password != confirm_password:
                            st.error("Passwords do not match.")
                        else:
                            ok, message = reset_password(
                                selected_id, new_password, actor=user
                            )
                            if ok:
                                st.success(message)
                                st.rerun()
                            else:
                                st.error(message)

with audit_tab:
    st.subheader("Administrator activity log")
    st.caption(
        "Each user-management change is recorded with the signed-in administrator's "
        "username and user ID. Passwords and password hashes are never stored in audit details."
    )
    audit_search = st.text_input(
        "Search audit records",
        placeholder="Administrator, action or affected username",
        key="user_audit_search",
    )
    audit_rows = list_auth_audit(audit_search, limit=300)
    if not audit_rows:
        st.info("No matching user-access changes have been recorded.")
    else:
        audit_display = pd.DataFrame(
            [
                {
                    "Time (UTC)": row["created_at"],
                    "Administrator": (
                        f"{row['actor_display_name']} ({row['actor_username']})"
                    ),
                    "Action": row["action"],
                    "Affected account": row["target_username"] or "—",
                    "Details": ", ".join(
                        f"{key}: {value}" for key, value in row["details"].items()
                    ) or "—",
                }
                for row in audit_rows
            ]
        )
        st.dataframe(audit_display, width="stretch", hide_index=True)
