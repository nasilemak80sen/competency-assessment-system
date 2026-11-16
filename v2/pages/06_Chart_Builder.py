"""Guided chart builder for the approved workforce and competency data elements."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from chart_builder import ChartBuilder, ChartCompatibility, DataType
from components.navigation import render_navigation
from config import GAP_COLS, REQ_COLS, SCORE_COLS
from core.auth import current_user
from core.bootstrap import get_master_data, open_session
from services.chart_configuration_service import (
    delete_chart_configuration,
    get_chart_configuration,
    list_chart_configurations,
    save_chart_configuration,
)


# Keep this page tolerant of a local chart_builder.py that has not yet been
# updated. The approved data contract belongs to the page's v2 workflow; the
# root engine still supplies the reusable chart classes and calculations.
CHART_BUILDER_FIELDS = tuple(
    [
        "Name", "Staff ID", "Age", "Birth Year", "Gender", "Nationality",
        "Department", "Section Name", "Unit Name", "Sub Unit", "Staff Position",
        "Email Address", "Employment Category",
        "Years in PET", "Years of RE Experience", "SG",
        "Age Promoted to Staff or Principal", "Years in Salary Grade",
        "Length in Current Assignment",
        "Assessment Level", "Last Assesment Date", "Ruler Type",
    ]
    + list(SCORE_COLS)
    + list(REQ_COLS)
    + list(GAP_COLS)
)
CHART_BUILDER_FIELD_LABELS = {
    column: column.replace("G--", "G-", 1)
    for column in GAP_COLS
}

CHART_FIELD_GROUPS = {
    "Personnel & demographics": [
        "Name", "Staff ID", "Age", "Birth Year", "Gender", "Nationality",
    ],
    "Organisation & employment": [
        "Department", "Section Name", "Unit Name", "Sub Unit",
        "Staff Position", "Email Address", "Employment Category",
    ],
    "Career progression": [
        "Years in PET", "Years of RE Experience", "SG",
        "Age Promoted to Staff or Principal", "Years in Salary Grade",
        "Length in Current Assignment",
    ],
    "Assessment profile": [
        "Assessment Level", "Last Assesment Date", "Ruler Type",
    ],
    "Actual competency scores": list(SCORE_COLS),
    "Required competency levels": list(REQ_COLS),
    "Competency gaps": list(GAP_COLS),
}


def get_chart_builder_fields(dataframe: pd.DataFrame) -> list[str]:
    """List only approved fields that exist and contain non-null values."""
    if dataframe is None or dataframe.empty:
        return []
    return [
        column for column in CHART_BUILDER_FIELDS
        if column in dataframe.columns and dataframe[column].notna().any()
    ]


def get_chart_builder_field_label(column: str) -> str:
    """Map canonical gap storage names to the workbook-facing display name."""
    return CHART_BUILDER_FIELD_LABELS.get(column, column)


def _values_matching_dataframe(
    dataframe: pd.DataFrame,
    column: str,
    saved_values,
) -> list:
    """Restore saved filter values using the current dataframe's native types."""
    if column not in dataframe.columns or not isinstance(saved_values, (list, tuple)):
        return []
    candidates = dataframe[column].dropna().unique().tolist()
    lookup = {str(value): value for value in candidates}
    return [lookup[str(value)] for value in saved_values if str(value) in lookup]


def _restore_chart_configuration(configuration: dict, dataframe: pd.DataFrame) -> None:
    """Restore filter and chart widget state before those widgets are rendered."""
    filters = configuration.get("filters", {}) or {}
    chart = configuration.get("chart", {}) or {}

    for key in list(st.session_state):
        if key.startswith((
            "cb_primary_filter_v2_",
            "cb_extra_filter_v2_",
            "cb_dynamic_filter_v2_",
        )):
            st.session_state.pop(key, None)

    st.session_state["cb_personnel_search_v2"] = str(filters.get("search") or "")
    primary_values = filters.get("primary", {}) or {}
    for column in ("Department", "Staff Position", "SG"):
        st.session_state[f"cb_primary_filter_v2_{column}"] = _values_matching_dataframe(
            dataframe, column, primary_values.get(column, [])
        )

    extra_values = filters.get("extra", {}) or {}
    available_extra = [
        column for column in (filters.get("extra_columns", []) or [])
        if column in dataframe.columns
    ]
    st.session_state["cb_extra_filter_columns_v2"] = available_extra
    for column in available_extra:
        st.session_state[f"cb_extra_filter_v2_{column}"] = _values_matching_dataframe(
            dataframe, column, extra_values.get(column, [])
        )

    numeric_field = filters.get("numeric_field")
    numeric_available = (
        numeric_field in dataframe.columns
        and pd.to_numeric(dataframe[numeric_field], errors="coerce").notna().any()
    )
    st.session_state["cb_numeric_filter_column_v2"] = (
        numeric_field if numeric_available else "(None)"
    )
    numeric_range = filters.get("numeric_range")
    if numeric_available and isinstance(numeric_range, (list, tuple)) and len(numeric_range) == 2:
        numeric_values = pd.to_numeric(dataframe[numeric_field], errors="coerce").dropna()
        low, high = float(numeric_values.min()), float(numeric_values.max())
        saved_low = max(low, min(high, float(numeric_range[0])))
        saved_high = max(saved_low, min(high, float(numeric_range[1])))
        st.session_state["cb_numeric_filter_range_v2"] = (saved_low, saved_high)
    else:
        st.session_state.pop("cb_numeric_filter_range_v2", None)

    widget_values = {
        "cb_measure_mode_v2": chart.get("measure_mode", "Numeric data element"),
        "cb_x_group_v2": chart.get("x_group"),
        "cb_dimension_v2": chart.get("dimension"),
        "cb_y_group_v2": chart.get("y_group"),
        "cb_measure_v2": chart.get("measure"),
        "cb_breakdown_v2": chart.get("breakdown", "(None)"),
        "cb_chart_type_v2": chart.get("chart_type"),
        "cb_aggregation_v2": chart.get("aggregation", "Average"),
        "cb_size_v2": chart.get("size", "(None)"),
        "cb_top_n_v2": chart.get("top_n", 10),
        "cb_custom_title_v2": chart.get("custom_title"),
        "cb_x_label_v2": chart.get("x_label"),
        "cb_y_label_v2": chart.get("y_label"),
        "cb_chart_height_v2": chart.get("chart_height"),
    }
    for key, value in widget_values.items():
        if value is not None:
            st.session_state[key] = value

    # Saved analyses are user-defined setups, even when originally started
    # from a built-in template.
    st.session_state["cb_template_v2"] = "Custom setup"
    st.session_state["cb_template_last_applied_v2"] = "Custom setup"
    st.session_state["cb_loaded_saved_configuration"] = True


def _field_group_for(column: str) -> str | None:
    return next(
        (group_name for group_name, columns in CHART_FIELD_GROUPS.items() if column in columns),
        None,
    )


def _build_chart_templates(
    numeric_fields: list[str],
    categorical_fields: list[str],
) -> dict[str, dict]:
    """Build guided examples only when their required fields exist."""
    templates: dict[str, dict] = {}

    def first_available(candidates, available, excluded=()):
        return next(
            (
                column for column in candidates
                if column in available and column not in excluded
            ),
            None,
        )

    category = first_available(
        ["Department", "Staff Position", "Section Name", "Unit Name", "SG"],
        categorical_fields,
    )
    colour = first_available(
        ["Department", "Staff Position", "Employment Category", "Gender"],
        categorical_fields,
        excluded=(category,),
    )
    scatter_x = first_available(
        ["Age", "Years of RE Experience", "Years in PET", "Years in Salary Grade"],
        numeric_fields,
    )
    scatter_y = first_available(
        ["Years of RE Experience", "Years in PET", "Years in Salary Grade", "Age"],
        numeric_fields,
        excluded=(scatter_x,),
    )
    bubble_x = first_available(
        ["Years of RE Experience", "Years in PET", "Age"],
        numeric_fields,
    )
    competency = first_available(
        ["B1", *SCORE_COLS, "R-B1", *REQ_COLS, "G--B1", *GAP_COLS],
        numeric_fields,
    )
    bubble_size = first_available(
        ["Years in PET", "Years in Salary Grade", "Age", "Years of RE Experience"],
        numeric_fields,
        excluded=(bubble_x, competency),
    )

    if scatter_x and scatter_y:
        templates["Scatter · Age and experience"] = {
            "description": (
                "Explore the relationship between age and RE experience. "
                "Each point represents one personnel record; colour can distinguish departments."
            ),
            "chart_type": "Scatter Plot",
            "dimension": scatter_x,
            "measure": scatter_y,
            "color": colour,
            "size": None,
            "aggregation": "Average",
            "measure_mode": "Numeric data element",
        }

    if bubble_x and competency and bubble_size:
        templates["Bubble · Experience and competency"] = {
            "description": (
                "Compare RE experience against a competency score. Bubble size adds a third "
                "numeric measure, while colour can distinguish departments."
            ),
            "chart_type": "Bubble Chart",
            "dimension": bubble_x,
            "measure": competency,
            "color": colour,
            "size": bubble_size,
            "aggregation": "Average",
            "measure_mode": "Numeric data element",
        }

    if category and competency:
        templates["Box plot · Competency distribution"] = {
            "description": (
                "Compare the spread of a competency score across departments or position groups. "
                "The box shows the median and quartiles; individual points reveal outliers."
            ),
            "chart_type": "Box Plot",
            "dimension": category,
            "measure": competency,
            "color": colour,
            "size": None,
            "aggregation": "Average",
            "measure_mode": "Numeric data element",
        }

    return templates


def _attach_aggregation_diagnostics(
    chart_data: pd.DataFrame,
    dataframe: pd.DataFrame,
    dimension: str,
    measure: str | None,
    aggregation: str,
    color_col: str | None,
) -> pd.DataFrame:
    """Add sample sizes when running against an older chart_builder module."""
    if {"Records", "Valid Values"}.issubset(chart_data.columns):
        return chart_data
    group_cols = [dimension] + (
        [color_col] if color_col and color_col in dataframe.columns and color_col != dimension else []
    )
    grouped = dataframe.groupby(group_cols, dropna=False)
    if aggregation == "Count" or measure is None:
        diagnostics = grouped.size().rename("Records").reset_index()
        diagnostics["Valid Values"] = diagnostics["Records"]
    else:
        numeric = pd.to_numeric(dataframe[measure], errors="coerce")
        numeric_frame = dataframe[group_cols].copy()
        numeric_frame["__measure"] = numeric
        numeric_grouped = numeric_frame.groupby(group_cols, dropna=False)["__measure"]
        diagnostics = numeric_frame.groupby(
            group_cols, dropna=False
        ).agg(
            Records=("__measure", "size"),
            **{"Valid Values": ("__measure", "count")},
        ).reset_index()
    return chart_data.merge(
        diagnostics, on=group_cols, how="left", validate="one_to_one"
    )


render_navigation()

# Page styling follows the shared PETRONAS theme: restrained teal/blue accents,
# soft surfaces and clear hierarchy without fighting the global stylesheet.
st.markdown(
    """
    <style>
    .cb-hero {
        padding: 1.15rem 1.35rem;
        border: 1px solid rgba(32, 65, 154, 0.10);
        border-radius: 18px;
        background: linear-gradient(115deg, rgba(0, 161, 156, 0.10), rgba(32, 65, 154, 0.06));
        margin: 0.2rem 0 1rem 0;
    }
    .cb-hero-kicker {
        color: #008b86;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.11em;
        text-transform: uppercase;
        margin-bottom: 0.35rem;
    }
    .cb-hero-title {
        color: #20419A;
        font-size: 1.55rem;
        font-weight: 800;
        line-height: 1.2;
        margin: 0;
    }
    .cb-hero-copy {
        color: #475569;
        font-size: 0.94rem;
        margin: 0.45rem 0 0 0;
        max-width: 920px;
    }
    .cb-section-label {
        color: #20419A;
        font-size: 0.76rem;
        letter-spacing: 0.08em;
        font-weight: 800;
        text-transform: uppercase;
        margin-bottom: 0.25rem;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-color: rgba(32, 65, 154, 0.12);
        border-radius: 16px;
    }
    </style>
    <div class="cb-hero">
      <div class="cb-hero-kicker">Reservoir Engineering · Workforce Intelligence</div>
      <p class="cb-hero-title">Workforce Chart Builder</p>
      <p class="cb-hero-copy">Explore personnel, career and competency data. Start with your workforce filters, choose what belongs on each axis, then inspect the values behind your chart.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

df = get_master_data()
if df is None or df.empty:
    st.info("No personnel data is available. Import the master workbook first.")
    st.stop()

# -----------------------------------------------------------------------------
# SAVED CHART CONFIGURATIONS
# -----------------------------------------------------------------------------
auth_user = current_user() or {}
try:
    chart_owner_id = int(auth_user.get("id")) if auth_user.get("id") is not None else None
except (TypeError, ValueError):
    chart_owner_id = None
chart_owner_name = str(auth_user.get("username") or auth_user.get("display_name") or "unknown")

saved_chart_rows = []
saved_chart_load_error = None
if chart_owner_id is not None:
    db_session = None
    try:
        db_session = open_session()
        saved_chart_rows = list_chart_configurations(db_session, chart_owner_id)
    except Exception as exc:
        saved_chart_load_error = str(exc)
    finally:
        if db_session is not None:
            db_session.close()

with st.container(border=True):
    saved_heading, saved_hint = st.columns([1.3, 2.7], vertical_alignment="center")
    with saved_heading:
        st.markdown("### Saved chart setups")
    with saved_hint:
        st.caption(
            "Load a previous analysis to restore its filters, axes, chart type and display settings. "
            "Saved setups are private to your account."
        )

    if chart_owner_id is None:
        st.info("Sign in with an application account to save and load personal chart configurations.")
    elif saved_chart_load_error:
        st.warning(f"Saved configurations could not be loaded: {saved_chart_load_error}")
    else:
        saved_label_to_id = {}
        saved_labels = ["Choose a saved setup"]
        for row in saved_chart_rows:
            timestamp = row.get("updated_at")
            updated_label = (
                timestamp.strftime("%d %b %Y")
                if hasattr(timestamp, "strftime") else "Saved"
            )
            label = f"{row['name']} · {updated_label}"
            saved_label_to_id[label] = row["id"]
            saved_labels.append(label)

        saved_col, load_col, delete_col = st.columns([3.2, 1, 1])
        with saved_col:
            selected_saved_label = st.selectbox(
                "Your saved configurations",
                saved_labels,
                key="cb_saved_configuration_v2",
                help="Each saved setup is visible only to the account that created it.",
            )
        selected_saved_id = saved_label_to_id.get(selected_saved_label)
        with load_col:
            st.write("")
            if st.button(
                "Load setup",
                key="cb_load_saved_configuration_v2",
                disabled=selected_saved_id is None,
                use_container_width=True,
            ):
                db_session = open_session()
                try:
                    saved_record = get_chart_configuration(
                        db_session, chart_owner_id, selected_saved_id
                    )
                finally:
                    db_session.close()
                if saved_record is None:
                    st.error("That saved configuration is no longer available.")
                else:
                    _restore_chart_configuration(saved_record["configuration"], df)
                    st.session_state["_cb_loaded_config_notice"] = saved_record["name"]
                    st.rerun()
        with delete_col:
            st.write("")
            if st.button(
                "Delete",
                key="cb_delete_saved_configuration_v2",
                disabled=selected_saved_id is None,
                use_container_width=True,
            ):
                db_session = open_session()
                try:
                    deleted = delete_chart_configuration(
                        db_session, chart_owner_id, selected_saved_id
                    )
                finally:
                    db_session.close()
                if deleted:
                    st.success("Saved configuration deleted.")
                    st.rerun()
                else:
                    st.warning("The selected configuration could not be found.")

        loaded_notice = st.session_state.pop("_cb_loaded_config_notice", None)
        if loaded_notice:
            st.success(f"Loaded **{loaded_notice}**. Review the restored filters and chart settings below.")

    st.caption(
        f"{len(saved_chart_rows):,} saved setup(s) available"
        if chart_owner_id is not None and not saved_chart_load_error
        else "Create a saved setup after choosing your filters and chart settings."
    )

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
st.subheader("Chart workspace")
st.caption(
    "Only the approved personnel, career, assessment, actual-score, requirement and gap fields "
    "are available. Workbook helper columns are kept out of the chart controls."
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

# -----------------------------------------------------------------------------
# FILTER WORKSPACE
# -----------------------------------------------------------------------------
primary_filter_columns = [
    column for column in ("Department", "Staff Position", "SG")
    if column in filter_columns
]
secondary_filter_columns = [
    column for column in filter_columns
    if column not in primary_filter_columns
]

with st.container(border=True):
    filter_heading, filter_actions = st.columns([4, 1], vertical_alignment="center")
    with filter_heading:
        st.markdown("### 01 · Define your workforce")
        st.caption("Start with a name or Staff ID search, then narrow the workforce using the common filters.")
    with filter_actions:
        if st.button("↺ Reset filters", key="cb_reset_filters_v2", use_container_width=True):
            for key in list(st.session_state):
                if key.startswith((
                    "cb_primary_filter_v2_",
                    "cb_extra_filter_v2_",
                    "cb_dynamic_filter_v2_",
                )) or key in {
                    "cb_personnel_search_v2",
                    "cb_extra_filter_columns_v2",
                    "cb_numeric_filter_column_v2",
                    "cb_numeric_filter_range_v2",
                    "cb_filter_columns_v2",
                }:
                    st.session_state.pop(key, None)
            st.rerun()

    search_col, department_col, position_col, grade_col = st.columns([1.8, 1.2, 1.35, 0.9])
    with search_col:
        personnel_search = st.text_input(
            "Quick search",
            placeholder="Personnel name or Staff ID",
            key="cb_personnel_search_v2",
            help="Search by part of a person's name or Staff ID.",
        )
    filters = {}
    primary_columns = [department_col, position_col, grade_col]
    for container, column in zip(primary_columns, primary_filter_columns):
        with container:
            options = sorted(
                df[column].dropna().unique().tolist(),
                key=lambda value: str(value),
            )
            values = st.multiselect(
                get_chart_builder_field_label(column),
                options,
                key=f"cb_primary_filter_v2_{column}",
                placeholder=f"All {get_chart_builder_field_label(column)}",
            )
            if values:
                filters[column] = values

    with st.expander("More filters · Organisation, people and assessment", expanded=False):
        st.caption(
            "Add optional filters for section, unit, gender, nationality, employment category, "
            "assessment level or ruler type. Empty filters include all values."
        )
        selected_extra_columns = st.multiselect(
            "Additional filter fields",
            secondary_filter_columns,
            format_func=get_chart_builder_field_label,
            key="cb_extra_filter_columns_v2",
            placeholder="Choose additional fields",
        )
        if selected_extra_columns:
            extra_filter_columns = st.columns(min(3, len(selected_extra_columns)))
            for index, column in enumerate(selected_extra_columns):
                with extra_filter_columns[index % len(extra_filter_columns)]:
                    options = sorted(
                        df[column].dropna().unique().tolist(),
                        key=lambda value: str(value),
                    )
                    values = st.multiselect(
                        get_chart_builder_field_label(column),
                        options,
                        key=f"cb_extra_filter_v2_{column}",
                        placeholder=f"All {get_chart_builder_field_label(column)}",
                    )
                    if values:
                        filters[column] = values

    with st.expander("Advanced · Numeric range", expanded=False):
        numeric_filter = st.selectbox(
            "Choose a numeric field",
            ["(None)"] + numeric_filter_columns,
            format_func=lambda value: (
                "No numeric range filter"
                if value == "(None)" else get_chart_builder_field_label(value)
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
                        f"Keep {get_chart_builder_field_label(numeric_filter)} within",
                        min_value=low,
                        max_value=high,
                        value=(low, high),
                        key="cb_numeric_filter_range_v2",
                    )
                else:
                    st.caption(f"All available {get_chart_builder_field_label(numeric_filter)} values are {low:g}.")

    working_df = filter_builder.apply_filters(filters, numeric_ranges)
    if personnel_search.strip():
        search_value = personnel_search.strip()
        search_mask = pd.Series(False, index=working_df.index)
        for search_column in ("Name", "Staff ID"):
            if search_column in working_df.columns:
                search_mask |= working_df[search_column].astype("string").str.contains(
                    search_value, case=False, regex=False, na=False
                )
        working_df = working_df.loc[search_mask].copy()

    active_filter_labels = []
    if personnel_search.strip():
        active_filter_labels.append(f"Search: {personnel_search.strip()}")
    for column, values in filters.items():
        active_filter_labels.append(
            f"{get_chart_builder_field_label(column)}: {', '.join(map(str, values))}"
        )
    if numeric_ranges:
        for column, bounds in numeric_ranges.items():
            active_filter_labels.append(
                f"{get_chart_builder_field_label(column)}: {bounds[0]:g}–{bounds[1]:g}"
            )

    summary_col, clear_chart_col = st.columns([4, 1])
    with summary_col:
        st.metric(
            "Matching personnel",
            f"{len(working_df):,}",
            delta=f"of {len(df):,} total records",
        )
        if active_filter_labels:
            st.caption("Active filters · " + "  |  ".join(active_filter_labels))
        else:
            st.caption("No filters applied. The full workforce is included.")
    with clear_chart_col:
        if st.button("Clear chart", key="cb_clear_chart", use_container_width=True):
            for key in (
                "cb_last_chart", "cb_last_chart_meta", "cb_last_chart_data",
                "cb_last_chart_source_data",
            ):
                st.session_state.pop(key, None)
            st.rerun()

main_canvas = st.container()
if working_df.empty:
    st.warning("No personnel records match these filters. Clear or broaden the filters.")
    st.stop()


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

chart_templates = _build_chart_templates(numeric_fields, categorical_fields)

with main_canvas:
    st.markdown('<div class="cb-section-label">02 · Build your chart</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("### Start with a chart template")
        template_options = ["Custom setup"] + list(chart_templates)
        if st.session_state.get("cb_template_v2") not in template_options:
            st.session_state.pop("cb_template_v2", None)
        selected_template = st.selectbox(
            "Template examples",
            template_options,
            key="cb_template_v2",
            help="Choose a guided example to prefill the X-axis, Y-axis, chart type and optional breakdown. You can customise every setting afterwards.",
        )
        previous_template = st.session_state.get("cb_template_last_applied_v2")
        if selected_template != "Custom setup" and selected_template != previous_template:
            template = chart_templates[selected_template]
            dimension_value = template["dimension"]
            measure_value = template["measure"]
            size_value = template.get("size")
            st.session_state["cb_measure_mode_v2"] = template["measure_mode"]
            st.session_state["cb_x_group_v2"] = _field_group_for(dimension_value)
            st.session_state["cb_dimension_v2"] = dimension_value
            st.session_state["cb_y_group_v2"] = _field_group_for(measure_value)
            st.session_state["cb_measure_v2"] = measure_value
            st.session_state["cb_breakdown_v2"] = template.get("color") or "(None)"
            st.session_state["cb_chart_type_v2"] = template["chart_type"]
            st.session_state["cb_aggregation_v2"] = template.get("aggregation", "Average")
            st.session_state["cb_size_v2"] = size_value or "(None)"
            st.session_state["cb_template_last_applied_v2"] = selected_template
            st.session_state["cb_top_n_v2"] = 10
            st.rerun()
        if selected_template == "Custom setup":
            st.session_state["cb_template_last_applied_v2"] = "Custom setup"
            st.caption("Build from scratch, or choose an example above to see how a chart type is configured.")
        else:
            st.info(chart_templates[selected_template]["description"])

    with st.container(border=True):
        st.markdown("### Choose the data elements")
        st.caption(
            "Fields are grouped by their purpose so you can find the right column quickly. "
            "X defines the groups or horizontal values; Y supplies the numeric values to compare."
        )

        measure_mode = st.radio(
            "What should the Y-axis display?",
            ["Numeric data element", "Number of personnel records"],
            horizontal=True,
            key="cb_measure_mode_v2",
            help=(
                "Choose a numeric field to analyse real data values, or switch to personnel "
                "records when you specifically want a headcount."
            ),
        )

        x_groups = {}
        for group_name, group_fields in CHART_FIELD_GROUPS.items():
            valid_fields = [
                column for column in group_fields
                if column in axis_fields
                and (
                    measure_mode != "Number of personnel records"
                    or infos[column].data_type == DataType.CATEGORICAL
                )
            ]
            if valid_fields:
                x_groups[group_name] = valid_fields

        if not x_groups:
            st.error("No suitable X-axis fields are available for this data selection.")
            st.stop()

        preferred_x_group = (
            "Organisation & employment"
            if "Organisation & employment" in x_groups
            else next(iter(x_groups))
        )
        x_group_options = list(x_groups)
        if st.session_state.get("cb_x_group_v2") not in x_group_options:
            st.session_state["cb_x_group_v2"] = preferred_x_group

        if measure_mode == "Number of personnel records":
            st.info(
                "Headcount mode is active. Select a categorical field such as Department, "
                "Staff Position, Salary Grade or Assessment Level."
            )

        x_col, y_col = st.columns(2, gap="large")
        with x_col:
            st.markdown("**X-axis · What do you want to compare across?**")
            x_group = st.selectbox(
                "Field group",
                x_group_options,
                key="cb_x_group_v2",
                help="Choose the type of data first, then select a field from that group.",
            )
            x_options = x_groups[x_group]
            preferred_x = "Department" if "Department" in x_options else x_options[0]
            if st.session_state.get("cb_dimension_v2") not in x_options:
                st.session_state.pop("cb_dimension_v2", None)
            dimension = st.selectbox(
                "X-axis · Group, category or explanatory variable",
                x_options,
                index=x_options.index(preferred_x),
                format_func=get_chart_builder_field_label,
                key="cb_dimension_v2",
                help="Examples: Department, Salary Grade, Age or a competency score.",
            )
            st.caption(
                f"Selected: **{get_chart_builder_field_label(dimension)}** "
                f"· {infos[dimension].data_type.value.title()}"
            )

        measure = None
        if measure_mode == "Numeric data element":
            y_groups = {}
            for group_name, group_fields in CHART_FIELD_GROUPS.items():
                numeric_group_fields = [
                    column for column in group_fields
                    if column in numeric_fields and column != dimension
                ]
                if numeric_group_fields:
                    y_groups[group_name] = numeric_group_fields

            if not y_groups:
                st.error("No numeric measures are available. Choose a different X-axis field.")
                st.stop()

            preferred_y_group = (
                "Actual competency scores"
                if "Actual competency scores" in y_groups
                else next(iter(y_groups))
            )
            y_group_options = list(y_groups)
            if st.session_state.get("cb_y_group_v2") not in y_group_options:
                st.session_state["cb_y_group_v2"] = preferred_y_group

            with y_col:
                st.markdown("**Y-axis · Which numeric value should be analysed?**")
                y_group = st.selectbox(
                    "Measure group",
                    y_group_options,
                    key="cb_y_group_v2",
                    help="Choose between workforce metrics, actual competency scores, requirements or gaps.",
                )
                measure_options = y_groups[y_group]
                preferred_y = (
                    "B1" if "B1" in measure_options
                    else "Age" if "Age" in measure_options
                    else measure_options[0]
                )
                if st.session_state.get("cb_measure_v2") not in measure_options:
                    st.session_state.pop("cb_measure_v2", None)
                measure = st.selectbox(
                    "Y-axis · Numeric measure",
                    measure_options,
                    index=measure_options.index(preferred_y),
                    format_func=get_chart_builder_field_label,
                    key="cb_measure_v2",
                    help="Only numeric fields are shown. These are the actual values used to calculate the chart.",
                )
                st.caption(
                    f"Selected: **{get_chart_builder_field_label(measure)}** "
                    f"· {infos[measure].data_type.value.title()}"
                )
        else:
            with y_col:
                st.markdown("**Y-axis · Personnel records**")
                st.markdown(
                    "<div style='padding:0.85rem 1rem;border-radius:12px;"
                    "background:rgba(0,161,156,0.08);border:1px solid rgba(0,161,156,0.18);'>"
                    "<strong style='color:#008b86;'>Count of personnel</strong><br>"
                    "<span style='color:#64748b;font-size:0.88rem;'>Each bar represents the number of records in an X-axis group.</span>"
                    "</div>",
                    unsafe_allow_html=True,
                )

        breakdown_options = [
            column for column in categorical_fields
            if column not in {dimension, measure, "Name", "Staff ID", "Email Address"}
            and infos[column].unique_count <= 30
        ]
        breakdown_options = ["(None)"] + breakdown_options
        if st.session_state.get("cb_breakdown_v2") not in breakdown_options:
            st.session_state.pop("cb_breakdown_v2", None)
        breakdown_selection = st.selectbox(
            "Optional breakdown · Compare groups within each category",
            ["(None)"] + breakdown_options,
            format_func=lambda value: (
                "No additional breakdown"
                if value == "(None)" else get_chart_builder_field_label(value)
            ),
            key="cb_breakdown_v2",
        )
        color_col = None if breakdown_selection == "(None)" else breakdown_selection

    with st.container(border=True):
        st.markdown("### Data check")
        x_info = infos[dimension]
        y_info = None if measure is None else infos[measure]
        x_valid = int(working_df[dimension].notna().sum())
        x_unique = int(working_df[dimension].nunique(dropna=True))
        stat_cols = st.columns(4)
        stat_cols[0].metric("Personnel in scope", f"{len(working_df):,}")
        stat_cols[1].metric("X values available", f"{x_valid:,}")
        stat_cols[2].metric("Distinct X values", f"{x_unique:,}")
        if measure is not None:
            y_numeric = pd.to_numeric(working_df[measure], errors="coerce")
            y_valid = int(y_numeric.notna().sum())
            stat_cols[3].metric("Valid Y values", f"{y_valid:,}")
            numeric_range = (
                f"{y_numeric.min():,.2f} to {y_numeric.max():,.2f}"
                if y_valid else "No numeric values"
            )
            st.caption(
                f"**X:** {get_chart_builder_field_label(dimension)} "
                f"({x_info.null_count:,} missing). "
                f"**Y:** {get_chart_builder_field_label(measure)} "
                f"({y_info.null_count:,} missing). Observed range: {numeric_range}."
            )
        else:
            stat_cols[3].metric("X categories", f"{x_unique:,}")
            st.caption(
                f"Headcount by **{get_chart_builder_field_label(dimension)}**. "
                f"{x_info.null_count:,} records do not have an X-axis value and are excluded from the grouped chart."
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

    st.markdown('<div class="cb-section-label">03 · Choose how to visualise</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("### Select a chart style")
        st.caption("The list only includes chart types that work with the data elements you selected.")
        default_chart = next(
            (chart for chart in recommendation_names if chart in available_charts),
            available_charts[0],
        )
        if st.session_state.get("cb_chart_type_v2") not in available_charts:
            st.session_state.pop("cb_chart_type_v2", None)
        selected_chart = st.selectbox(
            "Chart type",
            available_charts,
            index=available_charts.index(default_chart),
            format_func=lambda chart: (
                f"{ChartCompatibility.CHART_TYPES[chart]['icon']} {chart}"
            ),
            key="cb_chart_type_v2",
        )
        st.caption(ChartCompatibility.CHART_TYPES[selected_chart]["description"])
        if selected_chart == "Scatter Plot":
            st.info("Scatter plot tip: choose two numeric fields to explore whether they move together.")
        elif selected_chart == "Bubble Chart":
            st.info("Bubble chart tip: choose a third numeric field for bubble size to add another dimension.")
        elif selected_chart == "Box Plot":
            st.info("Box plot tip: use a categorical X-axis and a numeric Y-axis to compare score distributions.")
    
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

    with st.expander("💾 Save or update this chart setup", expanded=False):
        st.caption(
            "Save the current workforce filters, X/Y fields, chart type and display options. "
            "Using an existing name updates that setup in your account."
        )
        with st.form("cb_save_chart_configuration_form", clear_on_submit=False):
            saved_name = st.text_input(
                "Configuration name",
                placeholder="e.g. Department B1 competency distribution",
                max_chars=100,
            )
            saved_description = st.text_input(
                "Description (optional)",
                placeholder="What question does this chart help answer?",
                max_chars=500,
            )
            save_submitted = st.form_submit_button(
                "💾 Save configuration",
                type="primary",
                use_container_width=True,
                disabled=chart_owner_id is None,
            )
        if save_submitted:
            configuration_payload = {
                "version": 1,
                "filters": {
                    "search": personnel_search,
                    "primary": {
                        column: list(st.session_state.get(f"cb_primary_filter_v2_{column}", []))
                        for column in primary_filter_columns
                    },
                    "extra_columns": list(selected_extra_columns),
                    "extra": {
                        column: list(st.session_state.get(f"cb_extra_filter_v2_{column}", []))
                        for column in selected_extra_columns
                    },
                    "numeric_field": (
                        numeric_filter if numeric_filter != "(None)" else None
                    ),
                    "numeric_range": (
                        list(numeric_ranges[numeric_filter])
                        if numeric_filter in numeric_ranges else None
                    ),
                },
                "chart": {
                    "template": st.session_state.get("cb_template_v2", "Custom setup"),
                    "measure_mode": measure_mode,
                    "x_group": x_group,
                    "dimension": dimension,
                    "y_group": st.session_state.get("cb_y_group_v2"),
                    "measure": measure,
                    "breakdown": breakdown_selection,
                    "chart_type": selected_chart,
                    "aggregation": aggregation,
                    "size": size_col,
                    "top_n": st.session_state.get("cb_top_n_v2", 10),
                    "custom_title": st.session_state.get("cb_custom_title_v2"),
                    "x_label": st.session_state.get("cb_x_label_v2"),
                    "y_label": st.session_state.get("cb_y_label_v2"),
                    "chart_height": st.session_state.get("cb_chart_height_v2"),
                },
            }
            db_session = open_session()
            try:
                saved_record = save_chart_configuration(
                    db_session,
                    chart_owner_id,
                    chart_owner_name,
                    saved_name,
                    configuration_payload,
                    saved_description,
                )
                action_text = "updated" if not saved_record["created"] else "saved"
                st.success(
                    f"**{saved_record['name']}** {action_text}. "
                    "It will be available in Saved chart setups the next time you open this page."
                )
            except ValueError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Could not save this chart setup: {exc}")
            finally:
                db_session.close()

    st.markdown('<div class="cb-section-label">04 · Create your chart</div>', unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("### Generate chart")
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
                    if not {"Records", "Valid Values"}.issubset(chart_data.columns):
                        chart_data = _attach_aggregation_diagnostics(
                            chart_data,
                            working_df,
                            dimension,
                            measure,
                            aggregation,
                            chart_color_col,
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
                    "top_n": top_n,
                    "filter_signature": tuple(active_filter_labels),
                }
            except (ValueError, KeyError) as exc:
                st.error(f"Chart could not be generated: {exc}")
            except Exception as exc:
                st.error(f"Unexpected chart error: {exc}")
                with st.expander("Technical details"):
                    st.exception(exc)
    
    st.markdown('<div class="cb-section-label">05 · Review your results</div>', unsafe_allow_html=True)
    with st.container(border=True):
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
                "measure_mode": measure_mode,
                "size_col": size_col,
                "top_n": top_n,
                "filter_signature": tuple(active_filter_labels),
                "rows": len(working_df),
            }
            if any(meta.get(key) != value for key, value in current_config.items()):
                st.warning(
                    "This is the last generated chart. Your current selections or filters have changed; "
                    "generate the chart again to refresh it."
                )
    
            result_title = (
                f"{meta.get('chart_type', 'Workforce chart')} · "
                f"{get_chart_builder_field_label(meta.get('dimension', dimension))}"
            )
            result_measure = (
                "Personnel records"
                if meta.get("measure") is None
                else get_chart_builder_field_label(meta.get("measure"))
            )
            st.markdown(f"### {result_title}")
            st.caption(
                f"Source: {meta.get('rows', 0):,} personnel records · "
                f"Y-axis: {result_measure}"
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
    
            with st.expander("Inspect the values behind this chart", expanded=False):
                st.caption(
                    "Use this table to verify the exact values plotted. Grouped charts include "
                    "the record count and the number of valid values used in the calculation."
                )
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
