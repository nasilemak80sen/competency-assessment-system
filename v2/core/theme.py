"""Shared PETRONAS visual theme used by the native v2 application."""
from __future__ import annotations

from pathlib import Path
import streamlit as st


THEME_CSS = """
:root {
  --petronas-green: #00A19C;
  --petronas-lime: #BFD730;
  --petronas-blue: #20419A;
  --petronas-purple: #763F98;
  --petronas-yellow: #FDB924;
  --petronas-white: #FFFFFF;
  --petronas-ink: #0F172A;
  --petronas-soft: #F5FAF9;
  --petronas-shadow: 0 16px 40px rgba(32, 65, 154, 0.12);
}

html, body {
  font-family: "Museo Sans", "Segoe UI", Arial, sans-serif;
  background: linear-gradient(135deg, #ffffff 0%, #f7fcfb 100%);
  color: var(--petronas-ink);
}

[data-testid="stAppViewContainer"] {
  background: linear-gradient(135deg, #ffffff 0%, #f7fcfb 100%);
  padding-top: 0.35rem;
}

[data-testid="stHeader"] { background: transparent; box-shadow: none; }

[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #ffffff 0%, #f6fbfa 100%);
  border-right: 1px solid rgba(32, 65, 154, 0.10);
}

[data-testid="stMain"] { padding-top: 0.4rem; }

h1, h2, h3, h4, h5, h6 {
  font-family: "Museo Sans", "Segoe UI", Arial, sans-serif;
  color: var(--petronas-blue);
  letter-spacing: -0.02em;
}

.stButton > button {
  background: linear-gradient(135deg, var(--petronas-green), var(--petronas-blue));
  color: var(--petronas-white);
  border: 0;
  border-radius: 999px;
  padding: 0.6rem 1rem;
  font-weight: 700;
  box-shadow: 0 10px 20px rgba(0, 161, 156, 0.18);
}

[data-testid="stMetric"] {
  background: var(--petronas-white);
  border: 1px solid rgba(32, 65, 154, 0.08);
  border-radius: 20px;
  box-shadow: var(--petronas-shadow);
  padding: 1rem 1.1rem;
}

[data-testid="stMetric"] [data-testid="stMetricValue"] {
  color: var(--petronas-green);
  font-weight: 700;
}

[data-testid="stMetric"] [data-testid="stMetricLabel"] {
  color: var(--petronas-blue);
  font-weight: 600;
}

.stTextInput > div > div > input,
.stSelectbox > div > div > div,
.stMultiSelect > div > div > div,
.stDateInput > div > div > input {
  border-radius: 12px;
  border: 1px solid rgba(32, 65, 154, 0.16);
  box-shadow: inset 0 1px 2px rgba(32, 65, 154, 0.04);
}

div[data-testid="stVerticalBlock"] { gap: 0.65rem; }
div[data-testid="stBlockContainer"] { padding: 0.3rem 0; }

.stTabs [role="tablist"] { gap: 0.5rem; }
.stTabs [role="tab"] {
  border-radius: 999px;
  padding: 0.45rem 0.9rem;
  font-weight: 600;
  color: var(--petronas-blue);
}
.stTabs [role="tab"][aria-selected="true"] {
  background: linear-gradient(135deg, var(--petronas-green), var(--petronas-blue));
  color: var(--petronas-white);
}
"""


def apply_theme() -> None:
    """Inject the shared v2 PETRONAS visual system once per app run."""
    st.markdown(f"<style>{THEME_CSS}</style>", unsafe_allow_html=True)
