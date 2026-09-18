"""Dynamic Chart Builder page — Phase A-E architecture."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from chart_builder import ChartBuilder, ChartCompatibility, DataType
from components.navigation import render_navigation
from config import SCORE_COLS
from core.bootstrap import get_master_data


render_navigation()
st.title("📊 Dynamic Chart Builder")
st.caption("Build workforce analytics from dimensions, measures, aggregations, breakdowns and filters.")

df = get_master_data()
if df is None or df.empty:
    st.info("No personnel data is available. Import the master workbook first.")
    st.stop()

# -----------------------------------------------------------------------------
# Existing competency comparison — retained, but isolated from the dynamic
# analytical engine.
# -----------------------------------------------------------------------------
st.subheader("👥 Personnel Competency Comparison")
st.caption("Select up to 3 personnel to compare their competency profiles.")
personnel_names = sorted(df["Name"].dropna().astype(str).unique()) if "Name" in df.columns else []
selected_people = st.multiselect(
    "Personnel",
    personnel_names,
    max_selections=3,
    key="personnel_comparison_select",
)

if selected_people:
    competencies = [c for c in SCORE_COLS if c in df.columns]
    if competencies:
        comparison_cols = st.columns(len(selected_people))
        for idx, person_name in enumerate(selected_people):
            row = df[df["Name"].astype(str) == person_name].iloc[0]
            values = pd.to_numeric(row[competencies], errors="coerce").fillna(0).astype(float).tolist()
            figure = go.Figure(go.Scatterpolar(
                r=values + [values[0]],
                theta=competencies + [competencies[0]],
                fill="toself",
                name=person_name,
            ))
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

st.markdown("---")
st.subheader("📈 Self-Service Workforce Analytics")

builder = ChartBuilder(df)

# -----------------------------------------------------------------------------
# Phase E — dynamic filters
# -----------------------------------------------------------------------------
# Phase E — global filters live in a dedicated left-hand rail.
left_filters, main_canvas = st.columns([1, 3], gap="large")

with left_filters:
    st.markdown("### 🔎 Filters")
    filter_options = builder.get_filter_options()
    filter_columns = [
        c for c in filter_options
        if c not in {"Name", "Staff ID"} and c not in {"id", "ID", "Id"}
    ]
    selected_filter_columns = st.multiselect(
        "Categorical filters",
        filter_columns,
        default=[c for c in ("Department", "Staff Position", "SG") if c in filter_columns],
        key="cb_filter_columns",
    )
    filters = {}
    for column in selected_filter_columns:
        values = st.multiselect(
            "Salary Grade (SG)" if column == "SG" else column,
            filter_options[column],
            key=f"cb_dynamic_filter_{column}",
        )
        if values:
            filters[column] = values

    numeric_candidates = [
        c for c in builder.get_selectable_columns()
        if ChartCompatibility.analyze_data_element(df[c], c).data_type == DataType.NUMERIC
    ]
    numeric_filter = st.selectbox(
        "Numeric range",
        ["(None)"] + numeric_candidates,
        key="cb_numeric_filter_column",
    )
    numeric_ranges = {}
    if numeric_filter != "(None)":
        info = ChartCompatibility.analyze_data_element(df[numeric_filter], numeric_filter)
        low, high = info.numeric_range or (0.0, 1.0)
        if low != high:
            numeric_ranges[numeric_filter] = st.slider(
                f"{numeric_filter} range",
                min_value=float(low),
                max_value=float(high),
                value=(float(low), float(high)),
                key="cb_numeric_filter_range",
            )
    if st.button("↻ Reset filters", key="cb_reset_filters", width="stretch"):
        for key in list(st.session_state):
            if key.startswith("cb_dynamic_filter_") or key in {"cb_filter_columns", "cb_numeric_filter_column", "cb_numeric_filter_range"}:
                del st.session_state[key]
        st.rerun()

working_df = builder.apply_filters(filters, numeric_ranges)
if working_df.empty:
    st.warning("No records match the selected filters. Clear or broaden the filters.")
    st.stop()

st.info(f"Showing {len(working_df):,} of {len(df):,} records after filters.")

# Recreate builder around the filtered dataset so every downstream operation
# uses one authoritative dataframe.
builder = ChartBuilder(working_df)

main_canvas.__enter__()

# -----------------------------------------------------------------------------
# Phase C — dimension / measure / aggregation
# -----------------------------------------------------------------------------
selectable = builder.get_selectable_columns()
infos = {c: ChartCompatibility.analyze_data_element(working_df[c], c) for c in selectable}
numeric_cols = [c for c, info in infos.items() if info.data_type == DataType.NUMERIC]
categorical_cols = [c for c, info in infos.items() if info.data_type == DataType.CATEGORICAL]
datetime_cols = [c for c, info in infos.items() if info.data_type == DataType.DATETIME]

# X and Y intentionally use the same source column pool. Chart compatibility
# determines which visualisations are valid for the selected pair.
dimension_options = selectable

# Apply a pending axis swap before creating the widgets. This is the safe
# Streamlit pattern because widget keys must be initialised before instantiation.
pending_swap = st.session_state.pop("cb_swap_pending", None)
if pending_swap:
    st.session_state["cb_dimension"] = pending_swap["dimension"]
    st.session_state["cb_measure"] = pending_swap["measure"]
if not dimension_options:
    st.error("No suitable dimensions were found.")
    st.stop()

col1, swap_col, col2 = st.columns([10, 1, 10])
with col1:
    dimension = st.selectbox("Dimension / X-axis", dimension_options, key="cb_dimension")

with swap_col:
    st.markdown("<div style='height: 1.75rem'></div>", unsafe_allow_html=True)
    swap_clicked = st.button(
        "↔",
        help="Swap the X-axis and Y-axis parameters.",
        key="cb_swap_axes",
    )

with col2:
    measure_options = ["Count of rows"] + dimension_options
    measure_selection = st.selectbox(
        "Dimension / Measure / Y-axis",
        measure_options,
        key="cb_measure",
    )

# Streamlit locks a widget's keyed session-state value once the widget
# has been instantiated in the current run. Therefore the swap is applied
# through widget defaults on the *next* run, not by mutating those keys here.
if swap_clicked and measure_selection != "Count of rows":
    st.session_state["cb_swap_pending"] = {
        "dimension": measure_selection,
        "measure": dimension,
    }
    st.rerun()

measure = None if measure_selection == "Count of rows" else measure_selection
measure_info = infos.get(measure) if measure else None

if measure is None:
    aggregation_options = ["Count"]
elif measure_info and measure_info.data_type == DataType.NUMERIC:
    aggregation_options = list(ChartBuilder.AGGREGATIONS)
else:
    # A non-numeric Y can participate in row-count analysis, but not
    # Sum/Average/Median/Minimum/Maximum.
    aggregation_options = ["Count"]

if st.session_state.get("cb_aggregation") not in aggregation_options:
    st.session_state["cb_aggregation"] = aggregation_options[0]

aggregation = st.selectbox("Aggregation", aggregation_options, key="cb_aggregation")

breakdown_options = ["(None)"] + [
    c for c in categorical_cols
    if c not in {dimension, measure}
]
breakdown = st.selectbox("Breakdown / Color (optional)", breakdown_options, key="cb_breakdown")
color_col = None if breakdown == "(None)" else breakdown

# -----------------------------------------------------------------------------
# Phase D — smart recommendations
# -----------------------------------------------------------------------------
x_info = ChartCompatibility.analyze_data_element(working_df[dimension], dimension)
y_info = (
    None
    if measure is None
    else ChartCompatibility.analyze_data_element(working_df[measure], measure)
)

recommendations = ChartCompatibility.recommend(
    x_info,
    y_info,
    aggregation=aggregation,
    color_col=color_col,
)

st.markdown("### 💡 Recommended visualizations")
if recommendations:
    recommendation_names = [item["chart"] for item in recommendations]
    for item in recommendations[:3]:
        st.caption(f"**{item['chart']}** — {item['reason']}")
else:
    recommendation_names = []

compatible = ChartCompatibility.get_compatible_charts(
    x_info,
    y_info if y_info else ChartCompatibility.analyze_data_element(
        pd.Series([0] * len(working_df)), "Count"
    ),
)

available_charts = [
    name for name, details in compatible.items()
    if details["is_compatible"]
]

# Count-based grouped charts are valid even without a physical numeric Y column.
if measure is None:
    available_charts = [
        name for name in ("Bar Chart", "Stacked Bar Chart", "Pie Chart")
        if name in ChartCompatibility.CHART_TYPES
        and x_info.data_type == DataType.CATEGORICAL
    ]

if not available_charts:
    st.warning("No compatible visualization for the selected dimension and measure.")
    st.stop()

default_chart = next((name for name in recommendation_names if name in available_charts), available_charts[0])
selected_chart = st.selectbox(
    "Visualization",
    available_charts,
    index=available_charts.index(default_chart),
    format_func=lambda name: f"{ChartCompatibility.CHART_TYPES[name]['icon']} {name}",
    key="cb_chart_type",
)

# -----------------------------------------------------------------------------
# Phase E — Top-N / sorting
# -----------------------------------------------------------------------------
top_n_options = ["All", 5, 10, 20, 50]
top_n_selection = st.selectbox("Category limit", top_n_options, index=2, key="cb_top_n")
top_n = None if top_n_selection == "All" else int(top_n_selection)

if selected_chart in {"Scatter Plot", "Bubble Chart"}:
    size_col = st.selectbox(
        "Bubble size (optional)" if selected_chart == "Bubble Chart" else "Point size (optional)",
        ["(None)"] + numeric_cols,
        key="cb_size",
    )
    size_col = None if size_col == "(None)" else size_col
else:
    size_col = None

st.markdown("### 📊 Generate")
if st.button("📊 Generate Chart", type="primary", width="stretch"):
    try:
        title = (
            f"{aggregation} of {measure_selection} by {dimension}"
            if selected_chart not in {"Scatter Plot", "Bubble Chart", "Histogram"}
            else f"{selected_chart}: {dimension}"
        )
        figure = builder.create_chart(
            selected_chart,
            x_col=dimension,
            y_col=measure,
            color_col=color_col,
            size_col=size_col,
            title=title,
            aggregation=aggregation,
            top_n=top_n,
        )
        st.session_state["cb_last_chart"] = figure
        st.session_state["cb_last_chart_meta"] = {
            "chart_type": selected_chart,
            "dimension": dimension,
            "measure": measure_selection,
            "aggregation": aggregation,
            "breakdown": breakdown,
            "rows": len(working_df),
        }
    except (ValueError, KeyError) as exc:
        st.error(f"❌ {exc}")
    except Exception as exc:
        st.error(f"❌ Unexpected chart error: {exc}")
        with st.expander("Error details"):
            st.exception(exc)

if "cb_last_chart" in st.session_state:
    figure = st.session_state["cb_last_chart"]
    st.plotly_chart(
        figure,
        width="stretch",
        config={"displaylogo": False, "responsive": True},
    )

    # Phase F — export and presentation controls.
    with st.expander("🎨 Customise & export", expanded=False):
        custom_title = st.text_input(
            "Chart title",
            value=figure.layout.title.text or "Workforce chart",
            key="cb_custom_title",
        )
        x_label = st.text_input("X-axis label", value=str(dimension), key="cb_x_label")
        y_label = st.text_input(
            "Y-axis label",
            value="Count" if measure is None else f"{aggregation} of {measure}",
            key="cb_y_label",
        )
        chart_height = st.slider("Chart height", 400, 900, 600, 50, key="cb_chart_height")
        if st.button("Apply presentation settings", key="cb_apply_style"):
            figure.update_layout(
                title=custom_title.strip() or "Workforce chart",
                height=chart_height,
                xaxis_title=x_label,
                yaxis_title=y_label,
            )
            st.session_state["cb_last_chart"] = figure
            st.rerun()

        export_col1, export_col2 = st.columns(2)
        with export_col1:
            st.download_button(
                "⬇️ Download filtered data",
                data=working_df.to_csv(index=False).encode("utf-8"),
                file_name="chart_builder_filtered_data.csv",
                mime="text/csv",
                width="stretch",
            )
        with export_col2:
            st.download_button(
                "🌐 Download chart HTML",
                data=figure.to_html(include_plotlyjs="cdn").encode("utf-8"),
                file_name="chart_builder_chart.html",
                mime="text/html",
                width="stretch",
            )

    # Phase G — drill-down and competency intelligence.
    with st.expander("🔬 Drill-down / workforce intelligence", expanded=False):
        drill_columns = [dimension] + [c for c in categorical_cols if c != dimension]
        drill_dimension = st.selectbox("Drill-down dimension", drill_columns, key="cb_drill_dimension")
        drill_values = sorted(working_df[drill_dimension].dropna().astype(str).unique().tolist())
        drill_value = st.selectbox(
            "Drill-down value",
            ["(All)"] + drill_values,
            key="cb_drill_value",
        )
        drill_df = (
            working_df
            if drill_value == "(All)"
            else working_df[working_df[drill_dimension].astype(str) == drill_value]
        )
        st.caption(f"{len(drill_df):,} personnel records in this drill-down.")
        display_cols = [
            c for c in ("Name", "Staff ID", "Department", "Staff Position", "SG", "Nationality")
            if c in drill_df.columns
        ]
        st.dataframe(
            drill_df[display_cols] if display_cols else drill_df,
            width="stretch",
            hide_index=True,
        )

        competency_cols = [c for c in SCORE_COLS if c in drill_df.columns]
        if competency_cols and not drill_df.empty:
            score_frame = drill_df[competency_cols].apply(pd.to_numeric, errors="coerce")
            summary = pd.DataFrame({
                "Competency": competency_cols,
                "Average Score": score_frame.mean().round(2).values,
                "Assessed Personnel": score_frame.notna().sum().values,
            })
            st.dataframe(summary, width="stretch", hide_index=True)

else:
    st.info("Configure the dimension, measure and visualization, then generate the chart.")

main_canvas.__exit__(None, None, None)
