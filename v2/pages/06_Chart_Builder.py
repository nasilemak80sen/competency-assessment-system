"""Guided chart builder for the approved workforce and competency data elements."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from chart_builder import (
    ChartBuilder,
    ChartCompatibility,
    DataType,
    get_chart_builder_field_label,
    get_chart_builder_fields,
)
from components.navigation import render_navigation
from config import SCORE_COLS
from core.bootstrap import get_master_data


render_navigation()
st.title("📊 Workforce Chart Builder")
st.caption(
    "Choose an approved workforce or competency field for each axis. "
    "Numeric values are charted directly; record counts are an explicit alternative."
)

df = get_master_data()
if df is None or df.empty:
    st.info("No personnel data is available. Import the master workbook first.")
    st.stop()

# Keep the existing individual competency comparison, but place it behind an
# expander so the data-builder workflow remains the primary task.
with st.expander("👥 Compare individual competency profiles", expanded=False):
    st.caption("Select up to three personnel to compare their actual competency scores.")
    personnel_names = (
        sorted(df["Name"].dropna().astype(str).unique())
        if "Name" in df.columns else []
    )
    selected_people = st.multiselect(
        "Personnel",
        personnel_names,
        max_selections=3,
        key="personnel_comparison_select",
    )
    if selected_people:
        competencies = [column for column in SCORE_COLS if column in df.columns]
        if competencies:
            comparison_cols = st.columns(len(selected_people))
            for idx, person_name in enumerate(selected_people):
                row = df[df["Name"].astype(str) == person_name].iloc[0]
                values = pd.to_numeric(row[competencies], errors="coerce").astype(float).tolist()
                figure = go.Figure(go.Scatterpolar(
                    r=values + [values[0]],
                    theta=competencies + [competencies[0]],
                    fill="toself",
                    name=person_name,
                    connectgaps=False,
                ))
                figure.update_layout(
                    title=person_name,
                    height=320,
                    polar=dict(radialaxis=dict(visible=True, range=[0, 5], dtick=1)),
                    showlegend=False,
                    template="plotly_white",
                )
                with comparison_cols[idx]:
                    st.plotly_chart(
                        figure,
                        width="stretch",
                        config={"displaylogo": False, "responsive": True},
                    )

st.markdown("---")
st.subheader("Build a workforce chart")
st.caption(
    "The field list is restricted to the personnel, career, assessment, actual-score, "
    "required-level and gap columns from the approved data dictionary. Workbook helper "
    "columns and unrelated fields are excluded."
)

available_source_fields = get_chart_builder_fields(df)
if not available_source_fields:
    st.warning("None of the approved chart-builder fields contain data in the loaded workbook.")
    st.stop()

filter_builder = ChartBuilder(df)
source_infos = {
    column: ChartCompatibility.analyze_data_element(df[column], column)
    for column in available_source_fields
}
filter_columns = [
    column for column, info in source_infos.items()
    if info.data_type == DataType.CATEGORICAL
    and column not in {"Name", "Staff ID", "Email Address"}
    and info.unique_count <= 100
]
numeric_filter_columns = [
    column for column, info in source_infos.items()
    if info.data_type == DataType.NUMERIC
]

left_filters, main_canvas = st.columns([1, 3], gap="large")

with left_filters:
    st.markdown("### 🔎 Filter personnel")
    filter_defaults = [
        column for column in ("Department", "Staff Position", "SG")
        if column in filter_columns
    ]
    selected_filter_columns = st.multiselect(
        "Filter by",
        filter_columns,
        default=filter_defaults,
        format_func=get_chart_builder_field_label,
        key="cb_filter_columns_v2",
        help="Only approved categorical data elements with manageable value lists are shown.",
    )
    filters = {}
    for column in selected_filter_columns:
        values = st.multiselect(
            get_chart_builder_field_label(column),
            sorted(df[column].dropna().unique().tolist(), key=lambda value: str(value)),
            key=f"cb_dynamic_filter_v2_{column}",
        )
        if values:
            filters[column] = values

    numeric_filter = st.selectbox(
        "Numeric range filter",
        ["(None)"] + numeric_filter_columns,
        format_func=lambda value: (
            "No numeric filter" if value == "(None)" else get_chart_builder_field_label(value)
        ),
        key="cb_numeric_filter_column_v2",
    )
    numeric_ranges = {}
    if numeric_filter != "(None)":
        numeric_values = pd.to_numeric(df[numeric_filter], errors="coerce").dropna()
        if not numeric_values.empty:
            low, high = float(numeric_values.min()), float(numeric_values.max())
            if low < high:
                numeric_ranges[numeric_filter] = st.slider(
                    f"{get_chart_builder_field_label(numeric_filter)} range",
                    min_value=low,
                    max_value=high,
                    value=(low, high),
                    key="cb_numeric_filter_range_v2",
                )

    if st.button("↻ Reset filters", key="cb_reset_filters_v2", width="stretch"):
        for key in list(st.session_state):
            if key.startswith("cb_dynamic_filter_v2_") or key in {
                "cb_filter_columns_v2",
                "cb_numeric_filter_column_v2",
                "cb_numeric_filter_range_v2",
            }:
                del st.session_state[key]
        st.rerun()

    if st.button("Clear previous chart", key="cb_clear_chart", width="stretch"):
        for key in ("cb_last_chart", "cb_last_chart_meta", "cb_last_chart_data"):
            st.session_state.pop(key, None)
        st.rerun()

working_df = filter_builder.apply_filters(filters, numeric_ranges)
if working_df.empty:
    st.warning("No personnel records match these filters. Clear or broaden the filters.")
    st.stop()

st.info(f"**{len(working_df):,} personnel records** included from {len(df):,} total records.")

# Rebuild against the filtered frame so every axis, preview and chart reads
# exactly the same rows.
builder = ChartBuilder(working_df)
available_fields = get_chart_builder_fields(working_df)
infos = {
    column: ChartCompatibility.analyze_data_element(working_df[column], column)
    for column in available_fields
}
axis_fields = [
    column for column in available_fields
    if infos[column].data_type in {
        DataType.CATEGORICAL, DataType.NUMERIC, DataType.DATETIME
    }
]
numeric_fields = [
    column for column in available_fields
    if infos[column].data_type == DataType.NUMERIC
]
categorical_fields = [
    column for column in available_fields
    if infos[column].data_type == DataType.CATEGORICAL
]
if not axis_fields:
    st.warning("No usable approved axis fields remain after filtering.")
    st.stop()

with main_canvas:
    with st.container(border=True):
        st.markdown("### 1 · Choose what the chart should show")
        measure_mode = st.radio(
            "Y-axis calculation",
            ["Numeric data element", "Number of personnel records"],
            horizontal=True,
            key="cb_measure_mode_v2",
            help=(
                "Numeric data element plots actual workbook values. "
                "Record count is an explicit count-only option."
            ),
        )

        if measure_mode == "Number of personnel records":
            selectable_x = categorical_fields
            if not selectable_x:
                st.error("Record counts need a categorical X-axis field.")
                st.stop()
            st.caption(
                "Y-axis: Personnel records. Choose a category such as Department, "
                "Staff Position, Assessment Level or Ruler Type."
            )
        else:
            selectable_x = axis_fields
            if not numeric_fields:
                st.error("No numeric measures are available in the selected personnel records.")
                st.stop()

        preferred_x = "Department" if "Department" in selectable_x else selectable_x[0]
        if st.session_state.get("cb_dimension_v2") not in selectable_x:
            st.session_state.pop("cb_dimension_v2", None)
        dimension = st.selectbox(
            "X-axis · Group, category or explanatory variable",
            selectable_x,
            index=selectable_x.index(preferred_x),
            format_func=get_chart_builder_field_label,
            key="cb_dimension_v2",
            help="Choose what you want to compare across, such as Department or Salary Grade.",
        )

        measure = None
        if measure_mode == "Numeric data element":
            measure_options = [column for column in numeric_fields if column != dimension]
            if not measure_options:
                st.error("Choose a different X-axis field. A numeric Y-axis measure is also required.")
                st.stop()
            preferred_y = (
                "Age" if "Age" in measure_options
                else next((column for column in measure_options if column in SCORE_COLS), measure_options[0])
            )
            if st.session_state.get("cb_measure_v2") not in measure_options:
                st.session_state.pop("cb_measure_v2", None)
            measure = st.selectbox(
                "Y-axis · Numeric measure",
                measure_options,
                index=measure_options.index(preferred_y),
                format_func=get_chart_builder_field_label,
                key="cb_measure_v2",
                help="Only fields stored as numeric values are listed. Text, email and identifier fields are excluded.",
            )

        breakdown_options = [
            column for column in categorical_fields
            if column not in {dimension, measure, "Name", "Staff ID", "Email Address"}
            and infos[column].unique_count <= 30
        ]
        breakdown_selection = st.selectbox(
            "Break down by / colour (optional)",
            ["(None)"] + breakdown_options,
            format_func=lambda value: (
                "No additional breakdown" if value == "(None)" else get_chart_builder_field_label(value)
            ),
            key="cb_breakdown_v2",
        )
        color_col = None if breakdown_selection == "(None)" else breakdown_selection

    x_info = infos[dimension]
    y_info = None if measure is None else infos[measure]

    st.markdown("### 2 · Check the selected data")
    x_valid = int(working_df[dimension].notna().sum())
    x_unique = int(working_df[dimension].nunique(dropna=True))
    stat_cols = st.columns(4)
    stat_cols[0].metric("Filtered records", f"{len(working_df):,}")
    stat_cols[1].metric("X valid values", f"{x_valid:,}")
    stat_cols[2].metric("X distinct values", f"{x_unique:,}")
    if measure is not None:
        y_numeric = pd.to_numeric(working_df[measure], errors="coerce")
        y_valid = int(y_numeric.notna().sum())
        stat_cols[3].metric("Y valid values", f"{y_valid:,}")
        numeric_range = (
            f"{y_numeric.min():,.2f} to {y_numeric.max():,.2f}"
            if y_valid else "No numeric values"
        )
        st.caption(
            f"**X:** {get_chart_builder_field_label(dimension)} "
            f"({x_info.data_type.value}, {x_info.null_count:,} missing). "
            f"**Y:** {get_chart_builder_field_label(measure)} "
            f"({y_info.data_type.value}, {y_info.null_count:,} missing). "
            f"Observed Y range: {numeric_range}."
        )
    else:
        stat_cols[3].metric("Categories", f"{x_unique:,}")
        st.caption(
            f"**X:** {get_chart_builder_field_label(dimension)} "
            f"({x_info.data_type.value}, {x_info.null_count:,} missing). "
            "The Y-axis will show the number of personnel records in each category."
        )

    if measure is None:
        available_charts = ["Bar Chart", "Stacked Bar Chart", "Pie Chart"]
        recommendation_names = ["Bar Chart", "Stacked Bar Chart", "Pie Chart"]
        aggregation = "Count"
        aggregated_chart_types = set(available_charts)
    elif x_info.data_type == DataType.CATEGORICAL:
        available_charts = ["Bar Chart", "Stacked Bar Chart", "Box Plot", "Pie Chart"]
        recommendations = ChartCompatibility.recommend(
            x_info, y_info, aggregation="Average", color_col=color_col
        )
        recommendation_names = [item["chart"] for item in recommendations]
        aggregated_chart_types = {"Bar Chart", "Stacked Bar Chart", "Pie Chart"}
    elif x_info.data_type == DataType.DATETIME:
        available_charts = ["Line Chart"]
        recommendation_names = ["Line Chart"]
        aggregated_chart_types = set()
    else:
        available_charts = ["Scatter Plot", "Line Chart", "Bubble Chart"]
        recommendations = ChartCompatibility.recommend(
            x_info, y_info, aggregation="Average", color_col=color_col
        )
        recommendation_names = [item["chart"] for item in recommendations]
        aggregated_chart_types = set()

    # Record-count charts are intentionally count-only and need no numeric Y.
    # For all other modes, apply the shared axis/chart compatibility contract.
    if measure is None:
        compatible_names = {"Bar Chart", "Stacked Bar Chart", "Pie Chart"}
    else:
        compatibility = ChartCompatibility.get_compatible_charts(x_info, y_info)
        compatible_names = {
            chart for chart, details in compatibility.items()
            if details["is_compatible"]
        }
    available_charts = [chart for chart in available_charts if chart in compatible_names]
    if not available_charts:
        st.error(
            "These axes are not compatible with a supported chart. "
            "Choose a categorical or date field for X, and a numeric measure for Y."
        )
        st.stop()

    st.markdown("### 3 · Select the chart")
    default_chart = next(
        (chart for chart in recommendation_names if chart in available_charts),
        available_charts[0],
    )
    selected_chart = st.selectbox(
        "Chart type",
        available_charts,
        index=available_charts.index(default_chart),
        format_func=lambda chart: (
            f"{ChartCompatibility.CHART_TYPES[chart]['icon']} {chart}"
        ),
        key="cb_chart_type_v2",
    )

    if selected_chart in aggregated_chart_types and measure is not None:
        aggregation_options = ["Average", "Median", "Sum", "Minimum", "Maximum"]
        if st.session_state.get("cb_aggregation_v2") not in aggregation_options:
            st.session_state.pop("cb_aggregation_v2", None)
        aggregation = st.selectbox(
            "How should the Y values be summarised?",
            aggregation_options,
            index=0,
            key="cb_aggregation_v2",
            help=(
                "Average is the default for fair comparisons across groups. "
                "Sum adds values; Median shows the middle value."
            ),
        )
        if aggregation == "Average":
            aggregation_note = "Average of the selected numeric measure within each X-axis group."
        elif aggregation == "Median":
            aggregation_note = "Median of the selected numeric measure within each X-axis group."
        elif aggregation == "Sum":
            aggregation_note = "Sum of the selected numeric measure within each X-axis group."
        elif aggregation == "Minimum":
            aggregation_note = "Lowest valid numeric value within each X-axis group."
        else:
            aggregation_note = "Highest valid numeric value within each X-axis group."
        st.caption(aggregation_note)
    elif selected_chart not in aggregated_chart_types:
        aggregation = "Average"
        st.caption("Individual observations are plotted. No group aggregation is applied.")

    if selected_chart in {"Scatter Plot", "Bubble Chart"}:
        size_options = [
            column for column in numeric_fields if column not in {dimension, measure}
        ]
        if selected_chart == "Bubble Chart" and not size_options:
            st.warning("Bubble Chart needs a third numeric field for bubble size.")
            st.stop()
        size_selection = st.selectbox(
            "Bubble size" if selected_chart == "Bubble Chart" else "Point size (optional)",
            ["(None)"] + size_options,
            format_func=lambda value: (
                "No point-size encoding" if value == "(None)" else get_chart_builder_field_label(value)
            ),
            key="cb_size_v2",
        )
        size_col = None if size_selection == "(None)" else size_selection
        if selected_chart == "Bubble Chart" and size_col is None:
            st.info("Select a numeric bubble-size field to continue.")
            st.stop()
    else:
        size_col = None

    if selected_chart in {"Bar Chart", "Stacked Bar Chart", "Pie Chart"}:
        top_n_options = ["All", 5, 10, 20, 50]
        top_n_selection = st.selectbox(
            "Category limit",
            top_n_options,
            index=2,
            key="cb_top_n_v2",
            help="Limits the chart to the largest categories by the plotted value.",
        )
        top_n = None if top_n_selection == "All" else int(top_n_selection)
    else:
        top_n = None

    st.markdown("### 4 · Generate and inspect")
    if st.button("📊 Generate chart", type="primary", use_container_width=True, key="cb_generate_v2"):
        try:
            if measure is None:
                chart_title = f"Personnel records by {get_chart_builder_field_label(dimension)}"
            elif selected_chart in aggregated_chart_types:
                chart_title = (
                    f"{aggregation} {get_chart_builder_field_label(measure)} "
                    f"by {get_chart_builder_field_label(dimension)}"
                )
            else:
                chart_title = (
                    f"{get_chart_builder_field_label(measure)} "
                    f"by {get_chart_builder_field_label(dimension)}"
                )

            # Pie charts represent one value per X category. A second
            # breakdown would otherwise create subgroup slices that are later
            # summed, which can distort non-additive statistics such as averages.
            chart_color_col = None if selected_chart == "Pie Chart" else color_col
            figure = builder.create_chart(
                selected_chart,
                x_col=dimension,
                y_col=measure,
                color_col=chart_color_col,
                size_col=size_col,
                title=chart_title,
                aggregation=aggregation,
                top_n=top_n,
            )

            if selected_chart in aggregated_chart_types:
                chart_data = builder.aggregate(
                    dimension,
                    measure,
                    aggregation,
                    chart_color_col,
                    top_n,
                )
                is_aggregated = True
            else:
                required = [dimension, measure]
                if size_col:
                    required.append(size_col)
                plotted_columns = list(required)
                if chart_color_col and chart_color_col not in plotted_columns:
                    plotted_columns.append(chart_color_col)
                chart_data = working_df.dropna(subset=required)[plotted_columns].copy()
                is_aggregated = False

            st.session_state["cb_last_chart"] = figure
            st.session_state["cb_last_chart_data"] = chart_data
            st.session_state["cb_last_chart_source_data"] = working_df.copy()
            st.session_state["cb_last_chart_meta"] = {
                "chart_type": selected_chart,
                "dimension": dimension,
                "measure": measure,
                "aggregation": aggregation,
                "breakdown": breakdown_selection,
                "measure_mode": measure_mode,
                "size_col": size_col,
                "is_aggregated": is_aggregated,
                "rows": len(working_df),
            }
        except (ValueError, KeyError) as exc:
            st.error(f"Chart could not be generated: {exc}")
        except Exception as exc:
            st.error(f"Unexpected chart error: {exc}")
            with st.expander("Technical details"):
                st.exception(exc)

    if "cb_last_chart" in st.session_state:
        figure = st.session_state["cb_last_chart"]
        meta = st.session_state.get("cb_last_chart_meta", {})
        chart_data = st.session_state.get("cb_last_chart_data")
        chart_source_data = st.session_state.get("cb_last_chart_source_data", working_df)

        current_config = {
            "chart_type": selected_chart,
            "dimension": dimension,
            "measure": measure,
            "aggregation": aggregation,
            "breakdown": breakdown_selection,
            "rows": len(working_df),
        }
        if any(meta.get(key) != value for key, value in current_config.items()):
            st.warning(
                "This is the last generated chart. Your current selections or filters have changed; "
                "generate the chart again to refresh it."
            )

        st.plotly_chart(
            figure,
            width="stretch",
            config={"displaylogo": False, "responsive": True},
        )
        if meta.get("measure") is None:
            st.caption(
                "The table below shows the personnel-record count for each X-axis category. "
                "Records is the number of personnel rows included in that category."
            )
        elif meta.get("is_aggregated"):
            st.caption(
                "The table below shows the exact statistic plotted for each group. "
                "Records is the group size; Valid Values is the number of non-empty numeric "
                "observations used to calculate that statistic."
            )
        else:
            st.caption("The table below shows the individual observations used to draw the chart.")

        if isinstance(chart_data, pd.DataFrame) and not chart_data.empty:
            if meta.get("is_aggregated"):
                display_data = chart_data.rename(columns={
                    meta.get("dimension"): get_chart_builder_field_label(meta.get("dimension")),
                    "value": (
                        "Personnel records"
                        if meta.get("measure") is None
                        else f"{meta.get('aggregation')} of {get_chart_builder_field_label(meta.get('measure'))}"
                    ),
                }).copy()
                value_column = (
                    "Personnel records"
                    if meta.get("measure") is None
                    else f"{meta.get('aggregation')} of {get_chart_builder_field_label(meta.get('measure'))}"
                )
                if value_column in display_data.columns:
                    display_data[value_column] = pd.to_numeric(
                        display_data[value_column], errors="coerce"
                    ).round(2)
                st.dataframe(display_data, width="stretch", hide_index=True)
            else:
                display_data = chart_data.rename(columns={
                    column: get_chart_builder_field_label(column)
                    for column in chart_data.columns
                })
                st.dataframe(
                    display_data.head(100),
                    width="stretch",
                    hide_index=True,
                )
                if len(display_data) > 100:
                    st.caption(f"Showing the first 100 of {len(display_data):,} plotted observations.")

        with st.expander("🎨 Customise & export", expanded=False):
            custom_title = st.text_input(
                "Chart title",
                value=figure.layout.title.text or "Workforce chart",
                key="cb_custom_title_v2",
            )
            x_label = st.text_input(
                "X-axis label",
                value=get_chart_builder_field_label(meta.get("dimension", dimension)),
                key="cb_x_label_v2",
            )
            default_y_label = (
                "Personnel records"
                if meta.get("measure") is None
                else (
                    f"{meta.get('aggregation')} of "
                    f"{get_chart_builder_field_label(meta.get('measure'))}"
                    if meta.get("is_aggregated")
                    else get_chart_builder_field_label(meta.get("measure"))
                )
            )
            y_label = st.text_input(
                "Y-axis label",
                value=default_y_label,
                key="cb_y_label_v2",
            )
            chart_height = st.slider(
                "Chart height", 400, 900, 600, 50, key="cb_chart_height_v2"
            )
            if st.button("Apply presentation settings", key="cb_apply_style_v2"):
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
                    data=chart_source_data.to_csv(index=False).encode("utf-8"),
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

        with st.expander("🔬 Drill down to personnel", expanded=False):
            drill_columns = [
                column for column in categorical_fields
                if column not in {"Email Address"} and infos[column].unique_count <= 100
            ]
            if drill_columns:
                preferred_drill = meta.get("dimension")
                drill_index = (
                    drill_columns.index(preferred_drill)
                    if preferred_drill in drill_columns else 0
                )
                drill_dimension = st.selectbox(
                    "Drill-down field",
                    drill_columns,
                    index=drill_index,
                    format_func=get_chart_builder_field_label,
                    key="cb_drill_dimension_v2",
                )
                drill_values = sorted(
                    working_df[drill_dimension].dropna().unique().tolist(),
                    key=lambda value: str(value),
                )
                drill_value = st.selectbox(
                    "Drill-down value",
                    ["(All)"] + drill_values,
                    key="cb_drill_value_v2",
                )
                drill_df = (
                    working_df
                    if drill_value == "(All)"
                    else working_df[working_df[drill_dimension] == drill_value]
                )
                st.caption(f"{len(drill_df):,} personnel records in this drill-down.")
                display_columns = [
                    column for column in (
                        "Name", "Staff ID", "Department", "Staff Position", "SG", "Nationality"
                    )
                    if column in drill_df.columns
                ]
                st.dataframe(
                    drill_df[display_columns].rename(columns={
                        column: get_chart_builder_field_label(column)
                        for column in display_columns
                    }),
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.caption("No suitable categorical drill-down fields are available.")
    else:
        st.info("Choose your axes and chart type, then generate the chart.")
