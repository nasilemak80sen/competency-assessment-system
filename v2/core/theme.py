"""Shared PETRONAS visual theme, loaded directly from the golden asset."""
from __future__ import annotations

from pathlib import Path

import streamlit as st


_THEME_PATH = Path(__file__).resolve().parents[2] / "assets" / "css" / "petronas_theme.css"


def _load_theme_css() -> str:
    """Load the repository's canonical PETRONAS CSS without maintaining a copy."""
    try:
        return _THEME_PATH.read_text(encoding="utf-8")
    except OSError:
        # Keep startup resilient if the asset is unavailable in an unusual
        # deployment, while preserving the most important visual tokens.
        return """
        :root {
          --petronas-green: #00A19C;
          --petronas-lime: #BFD730;
          --petronas-blue: #20419A;
          --petronas-purple: #763F98;
          --petronas-yellow: #FDB924;
        }
        """


THEME_CSS = _load_theme_css()


def apply_theme() -> None:
    """Inject the exact shared PETRONAS theme used by the golden application."""
    st.markdown(f"<style>{THEME_CSS}</style>", unsafe_allow_html=True)
