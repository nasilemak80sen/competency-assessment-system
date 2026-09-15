"""Individual Assessment & Talent Profile — exact legacy branch."""

import streamlit as st

from core.bootstrap import initialise_session
from core.legacy_runtime import render_legacy_page

st.set_page_config(
    page_title="RE Fraternity | Individual Assessment",
    page_icon="👤",
    layout="wide",
)

initialise_session()
render_legacy_page("👤 Individual Assessment & Talent Profile")
