"""Presentation layer for the v2 authentication screen.

Authentication decisions stay in ``core.auth``; this module only renders the
login experience and returns submitted credentials through the supplied
callback. The layout is intentionally ready for a future Microsoft Entra SSO
entry point without coupling the POC to an identity provider.
"""
from __future__ import annotations

from collections.abc import Callable

import streamlit as st


LoginCallback = Callable[[str, str], bool]


_LOGIN_CSS = """
<style>
/* Keep the unauthenticated screen visually quieter than the application UI. */
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at 12% 15%, rgba(0, 161, 156, 0.11), transparent 28%),
        radial-gradient(circle at 88% 82%, rgba(32, 65, 154, 0.08), transparent 30%),
        var(--background-color, #ffffff);
}

[data-testid="stMainBlockContainer"] {
    max-width: 1180px;
    padding-top: 4.5rem;
    padding-bottom: 2rem;
}

.login-shell {
    margin: 0 auto;
}

.login-brand {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 1.6rem;
}

.login-mark {
    width: 48px;
    height: 48px;
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    letter-spacing: -0.03em;
    color: white;
    background: linear-gradient(135deg, #00A19C, #007F7C);
    box-shadow: 0 10px 28px rgba(0, 161, 156, 0.22);
}

.login-brand-title {
    font-size: 1rem;
    font-weight: 800;
    line-height: 1.1;
    margin-bottom: 2px;
}

.login-brand-subtitle {
    font-size: 0.78rem;
    opacity: 0.62;
}

.login-hero {
    padding: 18px 0 10px;
}

.login-eyebrow {
    font-size: 0.76rem;
    font-weight: 800;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #008C88;
    margin-bottom: 10px;
}

.login-title {
    font-size: clamp(2.1rem, 4.3vw, 3.45rem);
    line-height: 1.02;
    font-weight: 800;
    letter-spacing: -0.04em;
    margin: 0 0 14px 0;
}

.login-description {
    max-width: 580px;
    font-size: 1rem;
    line-height: 1.65;
    opacity: 0.72;
    margin-bottom: 1.8rem;
}

.login-pill-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 8px 0 24px;
}

.login-pill {
    border: 1px solid rgba(0, 161, 156, 0.18);
    background: rgba(0, 161, 156, 0.055);
    border-radius: 999px;
    padding: 7px 11px;
    font-size: 0.78rem;
    font-weight: 700;
}

.login-note {
    border-left: 3px solid #00A19C;
    padding: 10px 14px;
    margin-top: 22px;
    font-size: 0.8rem;
    line-height: 1.5;
    opacity: 0.67;
}

.login-card-wrap {
    margin-top: 6px;
}

.login-card {
    border: 1px solid rgba(128, 128, 128, 0.18);
    border-radius: 20px;
    padding: 28px 28px 24px;
    background: rgba(255, 255, 255, 0.88);
    box-shadow: 0 24px 70px rgba(0, 0, 0, 0.08);
    backdrop-filter: blur(12px);
}

.login-card-title {
    font-size: 1.35rem;
    font-weight: 800;
    margin-bottom: 4px;
}

.login-card-subtitle {
    font-size: 0.84rem;
    opacity: 0.62;
    margin-bottom: 18px;
}

.login-secure-badge {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    border-radius: 999px;
    padding: 6px 10px;
    margin-bottom: 18px;
    font-size: 0.72rem;
    font-weight: 700;
    background: rgba(0, 161, 156, 0.08);
    color: #007F7C;
}

.login-submit button {
    min-height: 46px;
    font-weight: 800;
    border-radius: 10px;
}

.login-help {
    text-align: center;
    font-size: 0.76rem;
    opacity: 0.54;
    margin-top: 13px;
}

.login-footer {
    text-align: center;
    font-size: 0.72rem;
    opacity: 0.48;
    margin-top: 42px;
    padding-bottom: 10px;
}

@media (max-width: 900px) {
    [data-testid="stMainBlockContainer"] {
        padding-top: 2rem;
    }

    .login-card {
        margin-top: 8px;
    }
}

@media (prefers-color-scheme: dark) {
    .login-card {
        background: rgba(22, 24, 27, 0.82);
        border-color: rgba(255, 255, 255, 0.10);
        box-shadow: 0 24px 70px rgba(0, 0, 0, 0.26);
    }
}
</style>
"""


def render_login_ui(login_callback: LoginCallback) -> bool:
    """Render the polished login page and return whether authentication exists."""
    if st.session_state.get("auth_user") is not None:
        return True

    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)

    left, right = st.columns([1.16, 0.84], gap="large")

    with left:
        st.markdown(
            """
            <div class="login-shell">
                <div class="login-brand">
                    <div class="login-mark">RE</div>
                    <div>
                        <div class="login-brand-title">Reservoir Engineering</div>
                        <div class="login-brand-subtitle">Development Petroleum Engineering</div>
                    </div>
                </div>

                <div class="login-hero">
                    <div class="login-eyebrow">Competency & Career Workspace</div>
                    <div class="login-title">Know where you are.<br>Grow where you’re going.</div>
                    <div class="login-description">
                        A focused workspace for competency assessment, readiness,
                        career development and talent information across Reservoir Engineering.
                    </div>

                    <div class="login-pill-row">
                        <span class="login-pill">📊 Competency</span>
                        <span class="login-pill">🎯 Readiness</span>
                        <span class="login-pill">🚀 Career</span>
                        <span class="login-pill">👤 Talent Profile</span>
                    </div>

                    <div class="login-note">
                        Your access level determines which workspace and information
                        are available after sign-in.
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        st.markdown('<div class="login-card-wrap"><div class="login-card">', unsafe_allow_html=True)
        st.markdown('<div class="login-secure-badge">🔒 Secure internal access</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-card-title">Welcome back</div>', unsafe_allow_html=True)
        st.markdown('<div class="login-card-subtitle">Sign in to continue to your competency workspace.</div>', unsafe_allow_html=True)

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

            st.markdown('<div class="login-submit">', unsafe_allow_html=True)
            submitted = st.form_submit_button("🔐  Sign In", type="primary")
            st.markdown('</div>', unsafe_allow_html=True)

        if submitted:
            if login_callback(username.strip(), password):
                st.rerun()
            elif not username.strip() or not password:
                st.error("Please enter both your username and password.")
            else:
                st.error("Invalid username/password or inactive account.")

        st.markdown('<div class="login-help">Use your assigned system credentials.</div>', unsafe_allow_html=True)
        st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown(
        """
        <div class="login-footer">
            Reservoir Engineering · Competency Assessment System · v3.0
            <br>For authorised personnel only
        </div>
        """,
        unsafe_allow_html=True,
    )

    return False
