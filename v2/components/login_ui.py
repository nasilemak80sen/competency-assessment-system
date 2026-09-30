"""Presentation layer for the v2 authentication screen.

Authentication decisions stay in ``core.auth``. This module owns only the
login page presentation and delegates credential validation through the
supplied callback. The layout intentionally leaves room for a future
Microsoft Entra sign-in option without coupling the POC to an identity
provider today.
"""
from __future__ import annotations

from collections.abc import Callable

import streamlit as st


LoginCallback = Callable[[str, str], bool]


_LOGIN_CSS = """
<style>
/* Login-only visual treatment. Keep widgets native Streamlit components. */
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at 8% 10%, rgba(0, 161, 156, 0.10), transparent 28%),
        radial-gradient(circle at 92% 88%, rgba(32, 65, 154, 0.07), transparent 30%);
}

[data-testid="stMainBlockContainer"] {
    max-width: 1180px;
    padding-top: 3.5rem;
    padding-bottom: 1.5rem;
}

.login-re-mark {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 44px;
    height: 44px;
    border-radius: 12px;
    background: linear-gradient(135deg, #00A19C, #007F7C);
    color: #ffffff;
    font-size: 0.95rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    box-shadow: 0 8px 22px rgba(0, 161, 156, 0.20);
}

.login-eyebrow {
    margin-top: 2.0rem;
    margin-bottom: 0.65rem;
    color: #008C88;
    font-size: 0.76rem;
    font-weight: 800;
    letter-spacing: 0.12em;
    text-transform: uppercase;
}

.login-footer {
    text-align: center;
    margin-top: 2.2rem;
    padding-bottom: 0.5rem;
    color: rgba(128, 128, 128, 0.72);
    font-size: 0.72rem;
    line-height: 1.5;
}

.login-muted {
    color: rgba(128, 128, 128, 0.82);
    font-size: 0.82rem;
}

@media (max-width: 900px) {
    [data-testid="stMainBlockContainer"] {
        padding-top: 1.5rem;
    }
}
</style>
"""


def render_login_ui(login_callback: LoginCallback) -> bool:
    """Render the login page and return whether an authenticated user exists."""
    if st.session_state.get("auth_user") is not None:
        return True

    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)

    left, right = st.columns([1.15, 0.85], gap="large", vertical_alignment="center")

    with left:
        brand_mark, brand_text = st.columns([0.12, 0.88], gap="small", vertical_alignment="center")
        with brand_mark:
            st.markdown('<div class="login-re-mark">RE</div>', unsafe_allow_html=True)
        with brand_text:
            st.markdown("**Reservoir Engineering**")
            st.markdown('<div class="login-muted">Development Petroleum Engineering</div>', unsafe_allow_html=True)

        st.markdown('<div class="login-eyebrow">Competency & Career Workspace</div>', unsafe_allow_html=True)
        st.title("Know where you are.\nGrow where you’re going.")
        st.write(
            "A focused workspace for competency assessment, readiness, career "
            "development and talent information across Reservoir Engineering."
        )

        pill_1, pill_2 = st.columns(2, gap="small")
        with pill_1:
            st.info("📊 **Competency**\n\nAssessment and competency insights")
        with pill_2:
            st.info("🎯 **Readiness**\n\nTarget levels and development gaps")

        pill_3, pill_4 = st.columns(2, gap="small")
        with pill_3:
            st.info("🚀 **Career**\n\nCareer progression and context")
        with pill_4:
            st.info("👤 **Talent Profile**\n\nYour role, strengths and profile")

        st.caption(
            "Your access level determines which workspace and information are available after sign-in."
        )

    with right:
        with st.container(border=True):
            st.success("🔒 Secure internal access")
            st.subheader("Welcome back")
            st.caption("Sign in to continue to your competency workspace.")

            with st.form("poc_login_form", clear_on_submit=False):
                username = st.text_input(
                    "Username",
                    autocomplete="username",
                    placeholder="Enter your username",
                )
                password = st.text_input(
                    "Password",
                    type="password",
                    autocomplete="current-password",
                    placeholder="Enter your password",
                )
                submitted = st.form_submit_button("🔐  Sign In", type="primary")

            if submitted:
                username = username.strip()
                if not username or not password:
                    st.warning("Please enter both your username and password.")
                elif login_callback(username, password):
                    st.rerun()
                else:
                    st.error("Invalid username/password or inactive account.")

            st.caption("Use your assigned system credentials.")

    st.markdown(
        """
        <div class="login-footer">
            Reservoir Engineering · Competency Assessment System · v3.0<br>
            For authorised personnel only
        </div>
        """,
        unsafe_allow_html=True,
    )

    return False
