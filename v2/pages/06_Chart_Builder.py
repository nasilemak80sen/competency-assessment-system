"""Self-service chart builder page backed by the existing ChartBuilder class."""
import streamlit as st
import pandas as pd

from core.bootstrap import initialise_session, get_master_data
from components.navigation import render_header, render_navigation
from chart_builder import ChartBuilder, ChartCompatibility

initialise_session()
render_navigation()
render_header("📊 Chart Builder", "Explore the master dataset without coupling the UI to other pages.")

df = get_master_data().copy()

builder = ChartBuilder(df)
columns = df.columns.tolist()

x_col = st.selectbox("X-axis", columns, index=0)
y_col = st.selectbox("Y-axis", ["None"] + columns, index=1 if len(columns) > 1 else 0)
y_value = None if y_col == "None" else y_col

x_info = ChartCompatibility.analyze_data_element(df[x_col], x_col)
y_info = ChartCompatibility.analyze_data_element(df[y_value], y_value) if y_value else None
compat = ChartCompatibility.get_compatible_charts(x_info, y_info)
compatible_types = [name for name, info in compat.items() if info["is_compatible"]]

if not compatible_types:
    st.warning("No chart type is compatible with the current axis selections. Choose a numeric Y-axis for most analytical charts.")
    st.stop()

chart_type = st.selectbox("Chart type", compatible_types)
color_options = ["None"] + [c for c in columns if c not in {x_col, y_value}]
color_col = st.selectbox("Color / grouping", color_options)
color_value = None if color_col == "None" else color_col

if chart_type in {"Scatter Plot", "Bubble Chart"} and y_value is None:
    st.stop()

try:
    fig = builder.create_chart(
        chart_type,
        x_col=x_col,
        y_col=y_value,
        color_col=color_value,
    )
    st.plotly_chart(fig, use_container_width=True)
except Exception as exc:
    st.error(f"Chart could not be generated: {exc}")
