"""Chart Builder & Depth Analysis — faithful native-v2 reproduction."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from chart_builder import ChartBuilder, ChartCompatibility
from components.navigation import render_navigation
from config import SCORE_COLS
from core.bootstrap import get_master_data


render_navigation()
st.title("📊 Dynamic Chart Builder")
st.markdown(
    "Create custom charts by selecting data elements from your dataset. "
    "The builder analyzes data types, recommends compatible chart types, "
    "flags data-quality issues, and supports filters."
)
st.markdown("---")

# -----------------------------------------------------------------------------
# PERSONNEL COMPETENCY COMPARISON
# -----------------------------------------------------------------------------

st.subheader("👥 Personnel Competency Comparison")
st.markdown("Select 1 to 3 personnel to compare their competency profiles using radar charts.")

df = get_master_data()
if df is None or df.empty:
    st.info("No personnel data is available. Import the master workbook first.")
    st.stop()

personnel_names = (
    sorted(df["Name"].dropna().astype(str).unique())
    if "Name" in df.columns
    else []
)
selected_people = st.multiselect(
    "Select up to 3 personnel",
    personnel_names,
    max_selections=3,
    key="personnel_comparison_select",
)

if selected_people:
    comparison_competencies = [c for c in SCORE_COLS if c in df.columns]
    if comparison_competencies:
        comparison_cols = st.columns(len(selected_people))
        for idx, person_name in enumerate(selected_people):
            person_rows = df[df["Name"].astype(str) == person_name]
            if person_rows.empty:
                continue
            person_row = person_rows.iloc[0]
            values = (
                pd.to_numeric(
                    person_row[comparison_competencies], errors="coerce"
                )
                .fillna(0)
                .astype(float)
                .tolist()
            )
            figure = go.Figure(
                go.Scatterpolar(
                    r=values + [values[0]],
                    theta=comparison_competencies + [comparison_competencies[0]],
                    fill="toself",
                    name=person_name,
                )
            )
            figure.update_layout(
                title=person_name,
                height=320,
                polar=dict(radialaxis=dict(visible=True, range=[0, 5], dtick=1)),
                showlegend=False,
            )
            with comparison_cols[idx]:
                st.plotly_chart(
                    figure,
                    width="stretch",
                    config={"displaylogo": False, "responsive": True},
                )
    else:
        st.info("No competency score columns are available for comparison.")
else:
    st.info("Choose 1 to 3 personnel to view their competency radar profiles.")

st.markdown("---")
st.subheader("📈 Data Element Analysis")

if "cb_filters" not in st.session_state:
    st.session_state.cb_filters = {}

# -----------------------------------------------------------------------------
# STEP 1 — FILTERS
# -----------------------------------------------------------------------------

with st.expander("🔽 Step 1: Apply Filters (Optional)", expanded=False):
    st.markdown("Filter the dataset before selecting chart elements.")
    filter_cols = st.columns(3)
    filters = {}
    filter_definitions = [
        ("Department", "chart_dept_filter"),
        ("Staff Position", "chart_pos_filter"),
        ("SG", "chart_sg_filter"),
    ]
    for column_index, (column, widget_key) in enumerate(filter_definitions):
        if column not in df.columns:
            continue
        with filter_cols[column_index]:
            label = "Salary Grade (SG)" if column == "SG" else column
            values = st.multiselect(
                label,
                sorted(df[column].dropna().astype(str).unique()),
                key=widget_key,
            )
            if values:
                filters[column] = values

    working_df = df.copy()
    for column, values in filters.items():
        working_df = working_df[working_df[column].astype(str).isin(values)]

    if filters and working_df.empty:
        st.warning("⚠️ Filters resulted in no records. Showing the original dataset instead.")
        working_df = df.copy()
        st.session_state.cb_filters = {}
    else:
        st.session_state.cb_filters = filters
        st.info(
            f"✅ Filters applied: Showing {len(working_df):,} of {len(df):,} records"
            if filters
            else f"📊 No filters applied: Using all {len(df):,} records"
        )

# Re-apply persisted filters after the expander closes.
if st.session_state.cb_filters:
    working_df = df.copy()
    for column, values in st.session_state.cb_filters.items():
        working_df = working_df[working_df[column].astype(str).isin(values)]

if working_df.empty:
    st.warning("No data is available for chart construction.")
    st.stop()

# -----------------------------------------------------------------------------
# STEP 2 — DATA ELEMENT SELECTION
# -----------------------------------------------------------------------------

st.markdown("---")
st.subheader("📈 Step 2: Select Data Elements")

numeric_cols = [c for c in working_df.select_dtypes(include=["number"]).columns if c != "id"]
categorical_cols = []
for column in working_df.select_dtypes(include=["object", "category"]).columns:
    unique_count = working_df[column].nunique(dropna=True)
    if 1 < unique_count <= 50:
        categorical_cols.append(column)

datetime_cols = [
    c for c in working_df.columns
    if pd.api.types.is_datetime64_any_dtype(working_df[c])
]
all_selectable = numeric_cols + categorical_cols + datetime_cols
if not all_selectable:
    st.error("❌ No suitable data elements found for charting.")
    st.stop()

select_col1, select_col2 = st.columns(2)
with select_col1:
    x_element = st.selectbox(
        "🔴 X-Axis Data Element",
        all_selectable,
        key="chart_x_select",
    )
with select_col2:
    y_element = st.selectbox(
        "🔵 Y-Axis Data Element (optional, for paired charts)",
        ["— No Y-Axis —"] + [c for c in all_selectable if c != x_element],
        key="chart_y_select",
    )

y_col = None if y_element == "— No Y-Axis —" else y_element

# -----------------------------------------------------------------------------
# STEP 3 — ANALYSIS + COMPATIBILITY
# -----------------------------------------------------------------------------

st.markdown("---")
st.subheader("🔍 Step 3: Data Analysis & Compatibility Check")
x_info = ChartCompatibility.analyze_data_element(working_df[x_element], x_element)
y_info = (
    ChartCompatibility.analyze_data_element(working_df[y_col], y_col)
    if y_col
    else None
)

info_col1, info_col2 = st.columns(2)
with info_col1:
    st.markdown(f"#### 🔴 X-Axis: **{x_element}**")
    st.write(f"- **Type**: {x_info.data_type.value}")
    st.write(f"- **Unique Values**: {x_info.unique_count:,}")
    st.write(f"- **Missing Values**: {x_info.null_count:,}")
    if x_info.numeric_range:
        st.write(f"- **Range**: {x_info.numeric_range[0]:.2f} to {x_info.numeric_range[1]:.2f}")
    if x_info.sample_values:
        st.write(f"- **Sample**: {', '.join(str(v)[:15] for v in x_info.sample_values[:3])}")
with info_col2:
    if y_info:
        st.markdown(f"#### 🔵 Y-Axis: **{y_col}**")
        st.write(f"- **Type**: {y_info.data_type.value}")
        st.write(f"- **Unique Values**: {y_info.unique_count:,}")
        st.write(f"- **Missing Values**: {y_info.null_count:,}")
        if y_info.numeric_range:
            st.write(f"- **Range**: {y_info.numeric_range[0]:.2f} to {y_info.numeric_range[1]:.2f}")
        if y_info.sample_values:
            st.write(f"- **Sample**: {', '.join(str(v)[:15] for v in y_info.sample_values[:3])}")

suggestions = ChartCompatibility.get_suggestions(x_info, y_info)
if suggestions["has_issues"]:
    st.warning("⚠️ Data Compatibility Issues Detected")
    for issue in suggestions["issues"]:
        st.write(issue)
    if suggestions["suggestions"]:
        st.markdown("**💡 Suggestions:**")
        for suggestion in suggestions["suggestions"]:
            st.write(suggestion)
else:
    st.success("✅ Data elements look good for analysis!")

# -----------------------------------------------------------------------------
# STEP 4 — CHART TYPE
# -----------------------------------------------------------------------------

st.markdown("---")
st.subheader("📊 Step 4: Select Chart Type")
compatible_charts = ChartCompatibility.get_compatible_charts(x_info, y_info)
fully_compatible = {
    name: details
    for name, details in compatible_charts.items()
    if details["is_compatible"]
}

if not fully_compatible:
    st.error("❌ No compatible chart types for these data elements. Please adjust your selection.")
    with st.expander("ℹ️ Compatibility reasons"):
        for chart_name, details in compatible_charts.items():
            st.write(f"- **{chart_name}**: {details['reason']}")
    st.stop()

chart_names = list(fully_compatible)
selected_chart = st.selectbox(
    "Select Chart Type",
    chart_names,
    format_func=lambda name: f"{fully_compatible[name]['requirements'].get('icon', '📊')} {name}",
    key="chart_type_select",
)

chart_cols = st.columns(min(3, len(chart_names)))
for idx, (chart_name, chart_info) in enumerate(fully_compatible.items()):
    with chart_cols[idx % len(chart_cols)]:
        st.button(
            f"{chart_info['requirements'].get('icon', '📊')} {chart_name}",
            use_container_width=True,
            key=f"chart_btn_{idx}",
            help=chart_info["requirements"].get("description", ""),
            disabled=True,
        )

with st.expander("ℹ️ Incompatible Chart Types (Why?)"):
    incompatible = {
        name: details
        for name, details in compatible_charts.items()
        if not details["is_compatible"]
    }
    if not incompatible:
        st.write("All configured chart types are compatible with the selected elements.")
    else:
        for chart_name, details in incompatible.items():
            st.write(f"- **{chart_name}**: {details['reason']}")

# Optional color and bubble-size elements are part of the chart generation contract.
element_names = [c for c in working_df.columns if c != "id"]
color_options = ["(None)"] + [c for c in element_names if c not in {x_element, y_col}]
color_selection = st.selectbox("Color / grouping (optional)", color_options, key="cb_color_element")
color_col = None if color_selection == "(None)" else color_selection
size_col = None
if selected_chart == "Bubble Chart":
    size_options = [c for c in element_names if c not in {x_element, y_col}]
    if size_options:
        size_col = st.selectbox("Bubble size", size_options, key="cb_size_element")

st.markdown("---")
st.subheader("📊 Step 5: Generate Chart")
if st.button("📊 Generate Chart", type="primary", width="stretch"):
    try:
        builder = ChartBuilder(working_df)
        title = None
        if selected_chart == "Scatter Plot":
            figure = builder.create_scatter_plot(x_element, y_col, color_col, size_col, f"{x_element} vs {y_col}")
        elif selected_chart == "Line Chart":
            figure = builder.create_line_chart(x_element, y_col, color_col, f"Trend of {y_col} over {x_element}")
        elif selected_chart == "Bar Chart":
            figure = builder.create_bar_chart(x_element, y_col, color_col, f"{y_col} by {x_element}")
        elif selected_chart == "Stacked Bar Chart":
            figure = builder.create_bar_chart(x_element, y_col, color_col, f"Stacked: {y_col} by {x_element}", stacked=True)
        elif selected_chart == "Histogram":
            figure = builder.create_histogram(x_element, color_col, 30, f"Distribution of {x_element}")
        elif selected_chart == "Box Plot":
            figure = builder.create_box_plot(x_element, y_col, color_col, f"Distribution of {y_col} by {x_element}")
        elif selected_chart == "Pie Chart":
            if working_df[x_element].nunique(dropna=True) > 10:
                st.warning("⚠️ Pie chart works best with ≤10 categories. Showing top 10.")
            figure = builder.create_pie_chart(x_element, y_col, f"Composition: {x_element}")
        elif selected_chart == "Bubble Chart":
            bubble_size = size_col or y_col
            st.info("💡 Bubble Chart uses the selected size element for bubble size.")
            figure = builder.create_bubble_chart(x_element, y_col, bubble_size, color_col, f"{x_element} vs {y_col}")
        else:
            raise ValueError(f"Unsupported chart type: {selected_chart}")

        st.plotly_chart(
            figure,
            width="stretch",
            key=f"chart_{selected_chart}",
            config={"displaylogo": False, "responsive": True},
        )
    except ValueError as exc:
        st.error(f"❌ Value Error: {exc}")
        st.info("💡 Tip: Make sure the selected elements contain compatible data.")
    except KeyError as exc:
        st.error(f"❌ Column '{exc}' not found in data")
    except Exception as exc:
        st.error(f"❌ Unexpected error: {exc}")
        with st.expander("Error details"):
            st.exception(exc)
else:
    st.info("👈 Select the data elements and chart type, then generate the visualization.")
