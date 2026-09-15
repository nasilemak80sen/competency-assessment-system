"""Chart Builder & Depth Analysis — native v2 page."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.navigation import render_navigation
from core.bootstrap import get_master_data
from config import SCORE_COLS
from chart_builder import ChartBuilder, ChartCompatibility

render_navigation()
st.title("📊 Dynamic Chart Builder")
st.markdown("Create custom charts by selecting data elements from the personnel dataset. The builder detects data types, recommends compatible chart types, and supports filters.")
st.markdown("---")
st.subheader("👥 Personnel Competency Comparison")
st.markdown("Select 1 to 3 personnel to compare their competency profiles using radar charts.")

df = get_master_data()
if df is None or df.empty:
    st.info("No personnel data is available. Import the master workbook first.")
    st.stop()

personnel_names = sorted(df["Name"].dropna().astype(str).unique()) if "Name" in df.columns else []
selected_people = st.multiselect("Select up to 3 personnel", personnel_names, max_selections=3, key="personnel_comparison_select")
if selected_people:
    comparison_competencies = [c for c in SCORE_COLS if c in df.columns]
    if comparison_competencies:
        comparison_cols = st.columns(len(selected_people))
        for idx, person_name in enumerate(selected_people):
            person_rows = df[df["Name"].astype(str) == person_name]
            if person_rows.empty:
                continue
            person_row = person_rows.iloc[0]
            values = pd.to_numeric(person_row[comparison_competencies], errors="coerce").fillna(0).astype(float).tolist()
            figure = go.Figure(go.Scatterpolar(r=values + [values[0]], theta=comparison_competencies + [comparison_competencies[0]], fill="toself", name=person_name))
            figure.update_layout(title=person_name, height=320, polar=dict(radialaxis=dict(visible=True, range=[0, 5], dtick=1)), showlegend=False)
            with comparison_cols[idx]:
                st.plotly_chart(figure, width="stretch", config={"displaylogo": False, "responsive": True})
    else:
        st.info("No competency score columns are available for comparison.")
else:
    st.info("Choose 1 to 3 personnel to view their competency radar profiles.")

st.markdown("---")
st.subheader("📈 Data Element Analysis")
if "cb_filters" not in st.session_state:
    st.session_state.cb_filters = {}

with st.expander("🔽 Step 1: Apply Filters (Optional)", expanded=False):
    filter_cols = st.columns(3)
    filters = {}
    for idx, column in enumerate(["Department", "Staff Position", "SG"]):
        if column in df.columns:
            with filter_cols[idx]:
                label = column if column != "SG" else "Salary Grade (SG)"
                values = st.multiselect(label, sorted(df[column].dropna().astype(str).unique()), key=f"chart_{column.lower().replace(' ', '_')}_filter")
                if values:
                    filters[column] = values
    working_df = df.copy()
    for column, values in filters.items():
        working_df = working_df[working_df[column].astype(str).isin(values)]
    if filters and not working_df.empty:
        st.session_state.cb_filters = filters
        st.info(f"Filters applied: Showing {len(working_df):,} of {len(df):,} records")
    elif filters:
        st.warning("Filters resulted in no records. Showing the original dataset instead.")
        st.session_state.cb_filters = {}
        working_df = df.copy()
    else:
        st.session_state.cb_filters = {}
        st.info(f"No filters applied: Using all {len(df):,} records")

if st.session_state.cb_filters:
    working_df = df.copy()
    for column, values in st.session_state.cb_filters.items():
        working_df = working_df[working_df[column].astype(str).isin(values)]
if working_df.empty:
    st.warning("No data is available for chart construction.")
    st.stop()

st.markdown("### Step 2: Select Data Elements")
element_names = [c for c in working_df.columns if c != "id"]
x_col = st.selectbox("X-axis data element", element_names, key="cb_x_element")
y_selection = st.selectbox("Y-axis data element", ["(None)"] + [c for c in element_names if c != x_col], key="cb_y_element")
y_col = None if y_selection == "(None)" else y_selection
x_info = ChartCompatibility.analyze_data_element(working_df[x_col], x_col)
y_info = ChartCompatibility.analyze_data_element(working_df[y_col], y_col) if y_col else None
info_cols = st.columns(2)
with info_cols[0]:
    st.caption(f"**X:** {x_info.data_type.value} · {x_info.unique_count:,} unique · {x_info.null_count:,} missing")
with info_cols[1]:
    if y_info:
        st.caption(f"**Y:** {y_info.data_type.value} · {y_info.unique_count:,} unique · {y_info.null_count:,} missing")

compatibility = ChartCompatibility.get_compatible_charts(x_info, y_info)
compatible_names = [name for name, details in compatibility.items() if details["is_compatible"]]
if not compatible_names:
    st.warning("No compatible chart types were found for the selected elements.")
    st.stop()

st.markdown("### Step 3: Choose Chart Type")
chart_type = st.selectbox("Chart type", compatible_names, key="cb_chart_type")
st.caption(compatibility[chart_type]["requirements"]["description"])
color_options = ["(None)"] + [c for c in element_names if c not in {x_col, y_col}]
color_col = st.selectbox("Color / grouping (optional)", color_options, key="cb_color_element")
color_col = None if color_col == "(None)" else color_col
size_col = None
if chart_type == "Bubble Chart":
    size_options = [c for c in element_names if c not in {x_col, y_col}]
    if size_options:
        size_col = st.selectbox("Bubble size", size_options, key="cb_size_element")

st.markdown("### Step 4: Generate Chart")
if st.button("📊 Generate Chart", type="primary", width="stretch"):
    try:
        builder = ChartBuilder(working_df)
        figure = builder.create_chart(chart_type=chart_type, x_col=x_col, y_col=y_col, color_col=color_col, size_col=size_col)
        st.plotly_chart(figure, width="stretch", config={"displaylogo": False, "responsive": True})
    except Exception as exc:
        st.error(f"❌ Unable to generate chart: {exc}")
        with st.expander("Error details"):
            st.exception(exc)
else:
    st.info("Select your data elements and chart type, then generate the visualization.")
