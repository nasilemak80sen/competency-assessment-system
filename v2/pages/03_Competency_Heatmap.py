"""Workforce competency heatmap page."""
import streamlit as st
import plotly.express as px

from core.bootstrap import initialise_session, get_master_data
from components.navigation import render_header, render_navigation
from config import SCORE_COLS, COMPETENCY_FULLNAMES
import analytics as an

initialise_session()
render_navigation()
render_header("🌡️ Competency Heatmap", "Workforce-level competency performance using the shared analytics layer.")

df = get_master_data().copy()

if "Department" in df.columns:
    departments = ["All"] + sorted(df["Department"].dropna().astype(str).unique().tolist())
    dept = st.selectbox("Department", departments)
    if dept != "All":
        df = df[df["Department"].astype(str) == dept]

available = [c for c in SCORE_COLS if c in df.columns]
if not available:
    st.warning("No competency score columns are available.")
    st.stop()

matrix = an.build_heatmap_matrix(df, available)
if matrix.empty:
    st.info("No assessed competency records are available for the selected scope.")
    st.stop()

max_people = st.slider("Personnel displayed", min_value=5, max_value=max(5, len(matrix)), value=min(30, len(matrix)))
# Keep the page responsive by limiting the rendered matrix.
view = matrix.head(max_people)
labels = {code: f"{code} — {COMPETENCY_FULLNAMES.get(code, code)}" for code in available}
view = view.rename(columns=labels)

fig = px.imshow(view, aspect="auto", labels={"x": "Competency", "y": "Personnel", "color": "Score"})
fig.update_layout(height=max(500, 24 * len(view) + 220))
st.plotly_chart(fig, use_container_width=True)

st.caption(f"Showing {len(view)} of {len(matrix)} assessed personnel records.")
