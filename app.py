"""
app.py - DPE | Reservoir Engineering Talent Profile
Run with: streamlit run app.py
"""

# =============================================================================
# STANDARD LIBRARY
# =============================================================================

from datetime import date, datetime
from pathlib import Path
import os
import re
import tempfile
import time
import config


# =============================================================================
# THIRD-PARTY PACKAGES
# =============================================================================

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pycountry
import streamlit as st
import streamlit.components.v1 as components

print("Streamlit:", st.__version__)

# =============================================================================
# APPLICATION CONFIGURATION
# =============================================================================

from config import (
    APP_TITLE,
    ASSESSMENT_LEVELS,
    CHAT_STATUS_OPTIONS,
    COMPETENCY_FULLNAMES,
    COMP_TYPES,
    COUNTRY_COORDINATES,
    CV_ALLOWED_FILE_TYPES,
    CV_COLUMNS_MAP,
    CV_LIST_SHEET,
    DATABASE_URL,
    DEPARTMENTS,
    EXCEL_PATH,
    GAP_COLS,
    GRADE_LABELS,
    HEATMAP_COLORSCALE,
    NATIONALITY_ALIASES,
    POSITIONS,
    PRIMARY,
    REQ_COLS,
    SCORE_COLS,
    SECONDARY,
    SUMMARY_GROUPS,
    USE_LIVE_EXCEL_SOURCE,POSITION_RANK, POSITION_TO_SG, SG_HIERARCHY, SG_RANK
)


# =============================================================================
# DATABASE AND DATA ACCESS
# =============================================================================

from models import (
    Assessment,
    Base,
    Personnel,
    SummaryScore,
    get_session,
    init_db,
)

from data_loader import (
    load_cv_list,
    load_master_data,
    load_ruler_and_tech_mapping,
)

import db_ops


# =============================================================================
# ANALYTICS AND VISUALIZATION MODULES
# =============================================================================

import analytics as an

from chart_builder import (
    ChartBuilder,
    ChartCompatibility,
    DataElementInfo,
)
# =============================================================================
# CAREER PROGRESSION CONFIGURATION
# =============================================================================

def _grade_rank(sg_value):
    """
    Convert a salary grade into a numeric rank.

    Examples:
        P1 -> 1
        P4 -> 4
        P10 -> 10
    """
    if sg_value is None:
        return None

    try:
        if pd.isna(sg_value):
            return None
    except (TypeError, ValueError):
        pass

    match = re.fullmatch(
        r"P(\d+)",
        str(sg_value).strip().upper(),
    )

    if match is None:
        return None

    return int(match.group(1))

def _safe_display_value(
    value,
    fallback="Not Applicable",
):
    """
    Convert missing profile values into a readable fallback.
    """
    if value is None:
        return fallback

    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass

    cleaned = str(value).strip()

    if cleaned.lower() in {
        "",
        "nan",
        "none",
        "nat",
    }:
        return fallback

    return cleaned

def _safe_integer_display(
    value,
    fallback="Not Applicable",
):
    """
    Display a numeric value as a rounded integer.
    """
    numeric_value = pd.to_numeric(
        value,
        errors="coerce",
    )

    if pd.isna(numeric_value):
        return fallback

    return int(round(float(numeric_value)))

def _safe_date_display(
    value,
    fallback="Not Applicable",
):
    """
    Format a date as 10 Aug 2026.
    """
    parsed_date = pd.to_datetime(
        value,
        errors="coerce",
    )

    if pd.isna(parsed_date):
        return fallback

    return parsed_date.strftime(
        "%d %b %Y"
    )

def _get_assessment_status(gap_value):
    """
    Classify a competency gap.
    """
    if pd.isna(gap_value):
        return "Not Assessed"

    if gap_value >= 0:
        return "✅ Met"

    if gap_value >= -1:
        return "🟡 Minor Gap"

    return "🔴 Major Gap"

def _build_target_gap_dataframe(
    person_row,
    target_sg,
    selected_ruler_requirements,
    tech_labels,
):
    """
    Compare actual competency scores against the selected
    target salary-grade requirements.
    """
    if not target_sg:
        return pd.DataFrame()

    target_requirements = (
        selected_ruler_requirements.get(
            target_sg,
            {},
        )
    )

    competency_groups = {
        "Base": [
            f"B{i}"
            for i in range(1, 13)
        ],
        "Key": [
            f"K{i}"
            for i in range(1, 6)
        ],
        "Pacing": [
            f"P{i}"
            for i in range(1, 6)
        ],
        "Emerging": [
            "E1",
            "E2",
        ],
    }

    records = []

    for category, competency_codes in (
        competency_groups.items()
    ):
        for competency_code in competency_codes:
            if (
                competency_code
                not in target_requirements
            ):
                continue

            actual_score = pd.to_numeric(
                person_row.get(
                    competency_code
                ),
                errors="coerce",
            )

            target_score = pd.to_numeric(
                target_requirements.get(
                    competency_code
                ),
                errors="coerce",
            )

            gap_score = (
                actual_score - target_score
                if (
                    pd.notna(actual_score)
                    and pd.notna(target_score)
                )
                else np.nan
            )

            records.append(
                {
                    "Category": category,
                    "Competency Code":
                        competency_code,
                    "Competency Name":
                        tech_labels.get(
                            competency_code,
                            COMPETENCY_FULLNAMES.get(
                                competency_code,
                                competency_code,
                            ),
                        ),
                    "Actual Score":
                        actual_score,
                    "Target Score":
                        target_score,
                    "Gap": gap_score,
                }
            )

    gap_dataframe = pd.DataFrame(
        records
    )

    if not gap_dataframe.empty:
        gap_dataframe["Status"] = (
            gap_dataframe["Gap"]
            .apply(
                _get_assessment_status
            )
        )

    return gap_dataframe

def _calculate_readiness_metrics(
    gap_dataframe,
):
    """
    Calculate strict, weighted, and category readiness.

    Strict readiness:
        Percentage of competencies meeting or exceeding target.

    Weighted readiness:
        Actual achievement capped at the required target.
    """
    if (
        gap_dataframe is None
        or gap_dataframe.empty
    ):
        return 0.0, 0.0, {}

    total_requirements = len(
        gap_dataframe
    )

    number_met = int(
        (
            gap_dataframe["Gap"]
            .fillna(-np.inf)
            >= 0
        ).sum()
    )

    strict_readiness = (
        number_met
        / total_requirements
        * 100
        if total_requirements > 0
        else 0.0
    )

    valid_targets = (
        gap_dataframe[
            "Target Score"
        ]
        .fillna(0)
        .clip(lower=0)
    )

    capped_actual = gap_dataframe.apply(
        lambda row: (
            min(
                float(row["Actual Score"]),
                float(row["Target Score"]),
            )
            if (
                pd.notna(
                    row["Actual Score"]
                )
                and pd.notna(
                    row["Target Score"]
                )
                and row["Target Score"] > 0
            )
            else 0.0
        ),
        axis=1,
    )

    total_possible_score = (
        valid_targets.sum()
    )

    weighted_readiness = (
        capped_actual.sum()
        / total_possible_score
        * 100
        if total_possible_score > 0
        else 0.0
    )

    category_readiness = {}

    for category in [
        "Base",
        "Key",
        "Pacing",
        "Emerging",
    ]:
        category_dataframe = (
            gap_dataframe[
                gap_dataframe["Category"]
                == category
            ]
        )

        if category_dataframe.empty:
            continue

        category_total = (
            category_dataframe[
                "Target Score"
            ]
            .fillna(0)
            .clip(lower=0)
            .sum()
        )

        category_achieved = (
            category_dataframe.apply(
                lambda row: (
                    min(
                        float(
                            row[
                                "Actual Score"
                            ]
                        ),
                        float(
                            row[
                                "Target Score"
                            ]
                        ),
                    )
                    if (
                        pd.notna(
                            row[
                                "Actual Score"
                            ]
                        )
                        and pd.notna(
                            row[
                                "Target Score"
                            ]
                        )
                        and row[
                            "Target Score"
                        ] > 0
                    )
                    else 0.0
                ),
                axis=1,
            )
            .sum()
        )

        category_readiness[
            category
        ] = (
            category_achieved
            / category_total
            * 100
            if category_total > 0
            else 0.0
        )

    return (
        strict_readiness,
        weighted_readiness,
        category_readiness,
    )

def _make_widget_safe_text(value):
    """
    Convert a value into text that is safe for Streamlit keys.
    """
    return re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        str(value).strip(),
    ).strip("_")

def _get_personnel_widget_key(
    person_row,
):
    """
    Build a stable identifier for person-specific widgets.
    """
    personnel_identifier = (
        person_row.get("id")
        or person_row.get("Staff ID")
        or person_row.get("Name")
        or "unknown"
    )

    return _make_widget_safe_text(
        personnel_identifier
    )

def _normalize_ruler_name(value):
    """
    Normalize career-ruler values.
    """
    if value is None:
        return "BASE"

    try:
        if pd.isna(value):
            return "BASE"
    except (TypeError, ValueError):
        pass

    cleaned = str(
        value
    ).strip().upper()

    aliases = {
        "": "BASE",
        "NO RULER ASSIGNED": "BASE",
        "BASE": "BASE",
        "RDP": "RDP",
        "RMS": "RMS",
        "RSS": "RSS",
    }

    return aliases.get(
        cleaned,
        cleaned,
    )

def _get_personnel_ruler(
    person_row,
):
    """
    Get the selected personnel's current career ruler.
    """
    ruler_value = (
        person_row.get("Ruler Type")
        or person_row.get("ruler_type")
    )

    if (
        ruler_value is None
        or (
            isinstance(
                ruler_value,
                float,
            )
            and pd.isna(ruler_value)
        )
    ):
        ruler_value = person_row.get(
            "Background"
        )

    return _normalize_ruler_name(
        ruler_value
    )

def _get_personnel_sg(
    person_row,
):
    """
    Get the selected personnel's current salary grade.
    """
    salary_grade = (
        person_row.get("SG")
        or person_row.get("sg")
        or ""
    )

    return str(
        salary_grade
    ).strip().upper()

def _render_ruler_target_filters(
    person_row,
    ruler_map,
    suffix="main",
):
    """
    Render one Career Ruler and Target Salary Grade filter pair.

    Defaults:
        Career Ruler -> selected person's current ruler.
        Target SG     -> selected person's current salary grade.

    Widget keys are person-specific, so selecting a new person
    automatically initializes that person's defaults.
    """
    ruler_column, target_column = (
        st.columns(2)
    )

    person_key = (
        _get_personnel_widget_key(
            person_row
        )
    )

    current_ruler = (
        _get_personnel_ruler(
            person_row
        )
    )

    current_sg = (
        _get_personnel_sg(
            person_row
        )
    )

    ruler_options = list(
        ruler_map.keys()
    )

    ruler_options = sorted(
        ruler_options,
        key=lambda value: (
            0
            if str(value).upper()
            == "BASE"
            else 1,
            str(value),
        ),
    )

    if not ruler_options:
        with ruler_column:
            st.warning(
                "No career-ruler data is available."
            )

        with target_column:
            st.warning(
                "No salary-grade data is available."
            )

        return None, None, {}

    ruler_lookup = {
        str(ruler).strip().upper():
            ruler
        for ruler in ruler_options
    }

    default_ruler = (
        ruler_lookup.get(
            current_ruler
        )
        or ruler_lookup.get(
            "BASE"
        )
        or ruler_options[0]
    )

    default_ruler_index = (
        ruler_options.index(
            default_ruler
        )
    )

    ruler_widget_key = (
        f"career_ruler_"
        f"{person_key}_"
        f"{suffix}"
    )

    with ruler_column:
        selected_ruler = (
            st.selectbox(
                "Career Ruler",
                options=ruler_options,
                index=default_ruler_index,
                key=ruler_widget_key,
                help=(
                    "Defaults to the selected "
                    "person's current career ruler."
                ),
            )
        )

    selected_ruler_requirements = (
        ruler_map.get(
            selected_ruler,
            {},
        )
    )

    available_salary_grades = list(
        selected_ruler_requirements.keys()
    )

    available_salary_grades = sorted(
        available_salary_grades,
        key=lambda salary_grade: (
            _grade_rank(
                salary_grade
            )
            if _grade_rank(
                salary_grade
            ) is not None
            else 999
        ),
    )

    current_rank = _grade_rank(
        current_sg
    )

    if current_rank is None:
        target_salary_grade_options = (
            available_salary_grades
        )
    else:
        target_salary_grade_options = [
            salary_grade
            for salary_grade
            in available_salary_grades
            if (
                _grade_rank(
                    salary_grade
                )
                is not None
                and _grade_rank(
                    salary_grade
                )
                >= current_rank
            )
        ]

    with target_column:
        if not target_salary_grade_options:
            st.warning(
                "No current or future salary grades "
                "are available for this career ruler."
            )

            return (
                selected_ruler,
                None,
                selected_ruler_requirements,
            )

        if (
            current_sg
            in target_salary_grade_options
        ):
            default_target_index = (
                target_salary_grade_options
                .index(
                    current_sg
                )
            )
        else:
            default_target_index = 0

        target_widget_key = (
            f"target_sg_"
            f"{person_key}_"
            f"{selected_ruler}_"
            f"{suffix}"
        )

        target_sg = st.selectbox(
            "Target Salary Grade",
            options=(
                target_salary_grade_options
            ),
            index=default_target_index,
            key=target_widget_key,
            help=(
                "Defaults to the selected person's "
                "current salary grade when available."
            ),
        )

    return (
        selected_ruler,
        target_sg,
        selected_ruler_requirements,
    )

def _load_personnel_database_details(
    person_row,
    engine,
):
    """
    Resolve the personnel ID and retrieve CV documents
    and the latest stored summary score in one session.
    """
    personnel_id = None
    cv_documents = pd.DataFrame()
    summary_score = None
    retrieval_error = None

    session = None

    try:
        session = get_session(
            engine
        )

        personnel_id = (
            db_ops.resolve_personnel_id(
                session=session,
                database_id=(
                    person_row.get("id")
                ),
                staff_id=(
                    person_row.get(
                        "Staff ID"
                    )
                ),
                name=(
                    person_row.get("Name")
                ),
            )
        )

        if personnel_id is not None:
            cv_documents = (
                db_ops.get_cv_documents(
                    session,
                    personnel_id,
                )
            )

            summary_score = (
                session.query(
                    SummaryScore
                )
                .filter_by(
                    personnel_id=(
                        personnel_id
                    )
                )
                .order_by(
                    SummaryScore
                    .updated_at
                    .desc()
                )
                .first()
            )

    except Exception as exc:
        retrieval_error = str(exc)

    finally:
        if session is not None:
            session.close()

    return (
        personnel_id,
        cv_documents,
        summary_score,
        retrieval_error,
    )

def _format_summary_metric(
    value,
):
    """
    Format a stored summary score.
    """
    if value is None:
        return "N/A"

    try:
        if pd.isna(value):
            return "N/A"
    except (TypeError, ValueError):
        pass

    numeric_value = pd.to_numeric(
        value,
        errors="coerce",
    )

    if pd.isna(numeric_value):
        return str(value)

    return f"{float(numeric_value):.2f}"

def _render_tech_class_reference():
    """
    Render one competency-definition reference expander.
    """
    with st.expander(
        "📚 Tech Class Reference - "
        "Competency Definitions",
        expanded=False,
    ):
        st.markdown(
            "**Understanding Competency Codes "
            "and Their Meanings**"
        )

        st.caption(
            "Use this reference to understand "
            "the competency codes shown in the "
            "assessment results."
        )

        reference_records = []

        for category_key in [
            "B",
            "K",
            "P",
            "E",
        ]:
            category_information = (
                COMP_TYPES.get(
                    category_key,
                    {},
                )
            )

            category_name = (
                category_information.get(
                    "label",
                    category_key,
                )
            )

            competency_codes = (
                category_information.get(
                    "cols",
                    [],
                )
            )

            for competency_code in (
                competency_codes
            ):
                reference_records.append(
                    {
                        "Category":
                            category_name,
                        "Code":
                            competency_code,
                        "Competency Name":
                            COMPETENCY_FULLNAMES.get(
                                competency_code,
                                competency_code,
                            ),
                    }
                )

        reference_dataframe = pd.DataFrame(
            reference_records
        )

        st.dataframe(
            reference_dataframe,
            width="stretch",
            hide_index=True,
            column_config={
                "Category":
                    st.column_config.TextColumn(
                        "Category",
                        width="medium",
                    ),
                "Code":
                    st.column_config.TextColumn(
                        "Code",
                        width="small",
                    ),
                "Competency Name":
                    st.column_config.TextColumn(
                        "Competency Name",
                        width="large",
                    ),
            },
        )

        st.markdown(
            "**Category Definitions**"
        )

        category_definitions = {
            "Base Competency":
                "Core technical competencies required "
                "for reservoir engineering work.",
            "Knowledge":
                "Specialized reservoir engineering "
                "and management knowledge.",
            "Pacing":
                "Advanced professional competencies "
                "for complex systems and work.",
            "Emerging":
                "Future-focused technologies and "
                "new technical capabilities.",
        }

        for category, description in (
            category_definitions.items()
        ):
            st.markdown(
                f"**{category}:** "
                f"{description}"
            )

def _build_gap_charts(
    gap_dataframe,
    target_sg,
):
    """
    Build the Actual vs Target and radar charts.
    """
    bar_figure = go.Figure()

    bar_figure.add_trace(
        go.Bar(
            x=gap_dataframe[
                "Competency Code"
            ],
            y=gap_dataframe[
                "Actual Score"
            ],
            name="Actual",
            marker_color="#20419A",
        )
    )

    bar_figure.add_trace(
        go.Scatter(
            x=gap_dataframe[
                "Competency Code"
            ],
            y=gap_dataframe[
                "Target Score"
            ],
            name="Target",
            mode="markers+lines",
            marker={
                "color": "#C62828",
                "size": 9,
                "symbol": "diamond",
            },
            line={
                "color": "#C62828",
                "dash": "dash",
            },
        )
    )

    bar_figure.update_layout(
        title=(
            f"Actual vs Target ({target_sg})"
        ),
        height=430,
        hovermode="x unified",
        barmode="group",
        margin={
            "l": 30,
            "r": 20,
            "t": 60,
            "b": 40,
        },
        legend={
            "orientation": "h",
            "y": 1.08,
            "x": 0,
        },
        xaxis_title="Competency",
        yaxis_title="Score",
        yaxis={
            "range": [0, 5],
            "dtick": 1,
        },
    )

    radar_dataframe = (
        gap_dataframe[
            gap_dataframe[
                "Actual Score"
            ].notna()
        ]
        .copy()
    )

    radar_figure = None

    if not radar_dataframe.empty:
        radar_actual = (
            radar_dataframe[
                "Actual Score"
            ]
            .astype(float)
            .tolist()
        )

        radar_target = (
            radar_dataframe[
                "Target Score"
            ]
            .astype(float)
            .tolist()
        )

        radar_names = (
            radar_dataframe[
                "Competency Code"
            ]
            .tolist()
        )

        closed_actual = (
            radar_actual
            + [radar_actual[0]]
        )

        closed_target = (
            radar_target
            + [radar_target[0]]
        )

        closed_names = (
            radar_names
            + [radar_names[0]]
        )

        radar_figure = go.Figure()

        radar_figure.add_trace(
            go.Scatterpolar(
                r=closed_actual,
                theta=closed_names,
                fill="toself",
                name="Actual",
                line={
                    "color": "#20419A",
                    "width": 2,
                },
                fillcolor=(
                    "rgba(0, 161, 156, 0.30)"
                ),
            )
        )

        radar_figure.add_trace(
            go.Scatterpolar(
                r=closed_target,
                theta=closed_names,
                fill="none",
                name=f"Target ({target_sg})",
                line={
                    "color": "#C62828",
                    "width": 2,
                    "dash": "dash",
                },
            )
        )

        radar_figure.update_layout(
            title="Competency Profile",
            height=430,
            showlegend=True,
            margin={
                "l": 40,
                "r": 40,
                "t": 60,
                "b": 40,
            },
            polar={
                "radialaxis": {
                    "visible": True,
                    "range": [0, 5],
                    "dtick": 1,
                    "gridcolor": "#D9E2E8",
                },
                "angularaxis": {
                    "tickfont": {
                        "size": 10,
                        "color": "#20419A",
                    },
                },
                "bgcolor": (
                    "rgba(248, 250, 252, 1)"
                ),
            },
        )

    return (
        bar_figure,
        radar_figure,
    )

def _gap_status_style(value):
    """
    Apply background colors to gap statuses.
    """
    if value == "✅ Met":
        return (
            "background-color: #C6EFCE; "
            "color: #006100;"
        )

    if value == "🟡 Minor Gap":
        return (
            "background-color: #FFF2CC; "
            "color: #7F6000;"
        )

    if value == "🔴 Major Gap":
        return (
            "background-color: #FFC7CE; "
            "color: #9C0006;"
        )

    if value == "Not Assessed":
        return (
            "background-color: #E7E6E6; "
            "color: #595959;"
        )

    return ""

def load_asset_text(relative_path: str) -> str:
    """Load a text asset from the project directory."""
    base_dir = Path(__file__).resolve().parent
    asset_path = base_dir / relative_path
    return asset_path.read_text(encoding="utf-8")

PETRONAS_CSS = load_asset_text("assets/css/petronas_theme.css")
PETRONAS_JS = load_asset_text("assets/js/petronas_theme.js")

POSITION_GRADE_MAP = {
    "Executive": ["P1", "P2"],
    "Senior Executive": ["P3", "P4"],
    "Staff": ["P5", "P6"],
    "Principal": ["P7", "P8"],
    "Custodian": ["P9", "P10"],
}

GRADE_POSITION_MAP = {
    grade: position
    for position, grades in POSITION_GRADE_MAP.items()
    for grade in grades
}

NATIONALITY_ALIASES = {
    "UK": "United Kingdom",
    "U.K.": "United Kingdom",
    "England": "United Kingdom",
    "Russia": "Russian Federation",
    "Iran": "Iran, Islamic Republic of",
    "Vietnam": "Viet Nam",
    "Venezuela": "Venezuela, Bolivarian Republic of",
    "South Korea": "Korea, Republic of",
    "Korea": "Korea, Republic of",
    "USA": "United States",
    "US": "United States",
    "U.S.": "United States",
}

def prepare_nationality_map_data(
    personnel_df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Prepare personnel nationality data for a Plotly bubble map.

    Returns:
        map_df:
            One row per country, including personnel count and
            representative country-centroid coordinates.

        unmatched:
            Nationality values that do not have configured coordinates.
    """
    required_column = "Nationality"

    if (
        personnel_df is None
        or personnel_df.empty
        or required_column not in personnel_df.columns
    ):
        return pd.DataFrame(), []

    nationality_df = personnel_df[
        [required_column]
    ].copy()

    nationality_df[required_column] = (
        nationality_df[required_column]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # Remove blank and invalid text values.
    nationality_df = nationality_df[
        ~nationality_df[required_column].str.lower().isin(
            {
                "",
                "nan",
                "none",
                "n/a",
                "na",
                "not applicable",
            }
        )
    ].copy()

    # Handle combined nationalities such as UK/India.
    nationality_df[required_column] = (
        nationality_df[required_column]
        .str.split("/")
    )

    nationality_df = nationality_df.explode(
        required_column
    )

    nationality_df[required_column] = (
        nationality_df[required_column]
        .astype(str)
        .str.strip()
    )

    # Apply aliases such as UK -> United Kingdom.
    nationality_df[required_column] = (
        nationality_df[required_column]
        .replace(NATIONALITY_ALIASES)
    )

    nationality_summary = (
        nationality_df
        .groupby(
            required_column,
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size": "Personnel Count",
            }
        )
    )

    nationality_summary["Latitude"] = (
        nationality_summary[required_column]
        .map(
            lambda country: (
                COUNTRY_COORDINATES.get(
                    country,
                    {},
                ).get("latitude")
            )
        )
    )

    nationality_summary["Longitude"] = (
        nationality_summary[required_column]
        .map(
            lambda country: (
                COUNTRY_COORDINATES.get(
                    country,
                    {},
                ).get("longitude")
            )
        )
    )

    unmatched = (
        nationality_summary.loc[
            nationality_summary[
                ["Latitude", "Longitude"]
            ].isna().any(axis=1),
            required_column,
        ]
        .dropna()
        .sort_values()
        .unique()
        .tolist()
    )

    map_df = (
        nationality_summary
        .dropna(
            subset=[
                "Latitude",
                "Longitude",
            ]
        )
        .sort_values(
            "Personnel Count",
            ascending=False,
        )
        .reset_index(drop=True)
    )

    total_records = map_df[
        "Personnel Count"
    ].sum()

    if total_records > 0:
        map_df["Representation"] = (
            map_df["Personnel Count"]
            / total_records
            * 100
        )
    else:
        map_df["Representation"] = 0.0

    map_df["Representation Display"] = (
        map_df["Representation"]
        .map(lambda value: f"{value:.1f}%")
    )

    return map_df, unmatched

def create_nationality_bubble_map(map_df: pd.DataFrame):
    """
    Build a professional Plotly Express nationality bubble map using OpenStreetMap tiles.
    """
    fig = px.scatter_map(
        map_df,
        lat="Latitude",
        lon="Longitude",
        size="Personnel Count",
        color="Personnel Count",
        hover_name="Nationality",
        hover_data={
            "Latitude": False,
            "Longitude": False,
            "Personnel Count": True,
            "Representation Display": True,
        },
        custom_data=[
            "Nationality",
            "Personnel Count",
            "Representation Display",
        ],
        size_max=42,
        zoom=2.0,
        center={
            "lat": 15,
            "lon": 65,
        },
        color_continuous_scale=[
            [0.00, "#BFD730"],
            [0.01, "#00A19C"],
            [0.04, "#20419A"],
            [1.00, "#763F98"],
        ],
        # 🗺️ Change map_style to "open-street-map" or "carto-voyager"
        map_style="carto-voyager", 
        opacity=0.75,
    )

    fig.update_traces(
        marker={
            "sizemin": 7,
        },
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Personnel: %{customdata[1]:.0f}<br>"
            "Representation: %{customdata[2]}"
            "<extra></extra>"
        ),
    )

    fig.update_layout(
        height=560,
        margin={
            "l": 0,
            "r": 0,
            "t": 40,
            "b": 0,
        },
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        coloraxis_colorbar={
            "title": {
                "text": "Personnel",
            },
            "orientation": "h",
            "x": 0.5,
            "xanchor": "center",
            "y": -0.05,
            "yanchor": "top",
            "len": 0.45,
            "thickness": 12,
            "tickfont": {
                "size": 11,
            },
        },
        font={
            "family": "Arial, sans-serif",
            "color": "#263238",
        },
    )

    return fig

def nationality_to_iso3(nationality):
    """
    Convert a nationality or country name into an ISO-3 code.

    Examples:
        Malaysia -> MYS
        India -> IND
        UK -> GBR
    """
    if nationality is None or pd.isna(nationality):
        return None

    nationality = str(nationality).strip()

    if not nationality:
        return None

    nationality = NATIONALITY_ALIASES.get(
        nationality,
        nationality,
    )

    try:
        country = pycountry.countries.lookup(
            nationality
        )

        return country.alpha_3

    except LookupError:
        return None

def grade_rank(sg_value):
    """
    Convert salary grade into a numeric rank.

    Examples:
        P1  -> 1
        P5  -> 5
        P10 -> 10

    Returns None for invalid values.
    """
    if sg_value is None or pd.isna(sg_value):
        return None

    text = str(sg_value).strip().upper()
    text = str(sg_value).strip().upper()
    text = str(sg_value).strip().upper()

    # Put UPTREX first (rank 0), then P1..P10
    if text == "UPTREX":
        return 0
    # Put UPTREX first (rank 0), then P1..P10
    if text == "UPTREX":
        return 0
    # Put UPTREX first (rank 0), then P1..P10
    if text == "UPTREX":
        return 0

    match = re.match(r"^P(\d+)$", text)
    if match:
        try:
            return int(match.group(1))
        except Exception:
            return None

def normalize_ruler_type(value):
    """
    Normalise ruler names so dictionary lookups remain consistent.
    """
    if value is None or pd.isna(value):
        return "BASE"

    normalized = str(value).strip().upper()

    aliases = {
        "": "BASE",
        "BASE": "BASE",
        "NO RULER ASSIGNED": "BASE",
        "RDP": "RDP",
        "RMS": "RMS",
        "RSS": "RSS",
    }

    return aliases.get(normalized, normalized)

def sort_grades(grades):
    """
    Sort salary grades numerically.

    Correct:
        P1, P2, P3, ..., P9, P10

    Instead of alphabetically:
        P1, P10, P2, P3, ...
    """
    return sorted(
        grades,
        key=lambda grade: grade_rank(grade) or 999,
    )

def build_target_gap_dataframe(
    person_row,
    target_requirements,
    current_sg,
    target_sg,
    target_position,
    ruler_type,
    competency_names,
):
    """
    Compare the employee's actual scores against one selected
    target salary grade.

    Gap is stored as a positive shortfall:

        Gap = max(Target - Actual, 0)

    Blank and zero ruler requirements are treated as not applicable.
    """
    records = []

    for competency in SCORE_COLS:
        actual_value = person_row.get(competency)
        target_value = target_requirements.get(competency)

        # Blank ruler cell means not applicable.
        if target_value is None or pd.isna(target_value):
            continue

        try:
            target = float(target_value)
        except (TypeError, ValueError):
            continue

        # Zero means there is no competency requirement.
        if target <= 0:
            continue

        if actual_value is None or pd.isna(actual_value):
            actual = np.nan
            gap = np.nan
            status = "Not Assessed"
        else:
            try:
                actual = float(actual_value)
            except (TypeError, ValueError):
                actual = np.nan

            if pd.isna(actual):
                gap = np.nan
                status = "Not Assessed"
            else:
                gap = max(target - actual, 0)

                if gap == 0:
                    status = "Met"
                elif gap <= 1:
                    status = "Minor Gap"
                else:
                    status = "Major Gap"

        records.append(
            {
                "Competency": competency,
                "Competency Name": competency_names.get(
                    competency,
                    COMPETENCY_FULLNAMES.get(
                        competency,
                        competency,
                    ),
                ),
                "Current Grade": current_sg,
                "Target Grade": target_sg,
                "Target Position": target_position,
                "Ruler Type": ruler_type,
                "Actual": actual,
                "Target": target,
                "Gap": gap,
                "Status": status,
            }
        )

    return pd.DataFrame(records)

def calculate_readiness_metrics(gap_df):
    """
    Calculate both strict and weighted readiness.

    Strict readiness:
        Percentage of assessed competencies fully meeting target.

    Weighted readiness:
        Actual achievement relative to total target requirement,
        capped at 100% for each competency.
    """
    if gap_df.empty:
        return {
            "total": 0,
            "assessed": 0,
            "not_assessed": 0,
            "met": 0,
            "minor": 0,
            "major": 0,
            "strict_readiness": 0.0,
            "weighted_readiness": 0.0,
        }

    assessed_df = gap_df[
        gap_df["Status"] != "Not Assessed"
    ].copy()

    total = len(gap_df)
    assessed = len(assessed_df)
    not_assessed = total - assessed

    met = int(
        (gap_df["Status"] == "Met").sum()
    )
    minor = int(
        (gap_df["Status"] == "Minor Gap").sum()
    )
    major = int(
        (gap_df["Status"] == "Major Gap").sum()
    )

    if assessed > 0:
        strict_readiness = met / assessed * 100

        achieved = np.minimum(
            assessed_df["Actual"].astype(float),
            assessed_df["Target"].astype(float),
        ).sum()

        total_target = (
            assessed_df["Target"]
            .astype(float)
            .sum()
        )

        weighted_readiness = (
            achieved / total_target * 100
            if total_target > 0
            else 0.0
        )
    else:
        strict_readiness = 0.0
        weighted_readiness = 0.0

    return {
        "total": total,
        "assessed": assessed,
        "not_assessed": not_assessed,
        "met": met,
        "minor": minor,
        "major": major,
        "strict_readiness": strict_readiness,
        "weighted_readiness": weighted_readiness,
    }

def scatter_age_vs_grade(df: pd.DataFrame) -> pd.DataFrame:
    """
    Data for Age vs SG scatter, including Overall_avg for color/size.
    Returns only columns that exist in the input dataframe.
    """
    # Define ideal columns in order of preference
    size_cols = ["Years in RE Experience", "Years in PET"]
    
    # Find which size column actually exists
    size_col_available = None
    for col in size_cols:
        if col in df.columns:
            size_col_available = col
            break
    
    # Build column list with only columns that exist
    cols = [
        "Name", 
        "Age", 
        "SG", 
        "Staff Position", 
        "Department", 
        "Overall_avg"
    ]
    
    # Only include size column if it exists
    if size_col_available:
        cols.append(size_col_available)
    
    # Filter to only existing columns
    cols = [c for c in cols if c in df.columns]
    
    # Create output
    out = df[cols].copy()
    
    # Fill NaN values
    if "Years in RE Experience" in out.columns:
        out["Years in RE Experience"] = out["Years in RE Experience"].fillna(0)
    if "Years in PET" in out.columns:
        out["Years in PET"] = out["Years in PET"].fillna(0)
    
    # Remove rows missing Age or SG
    return out.dropna(subset=["Age", "SG"])

# =============================================================================
# READINESS AND GAP ANALYSIS CONFIGURATION
# =============================================================================

READINESS_STATUS_ORDER = [
    "Ready",
    "Near Ready",
    "Development Required",
    "Not Assessed",
]

READINESS_STATUS_COLORS = {
    "Ready": "#00A19C",
    "Near Ready": "#BFD730",
    "Development Required": "#FDB924",
    "Not Assessed": "#9E9E9E",
}

GAP_SEVERITY_ORDER = [
    "Met",
    "Minor Gap",
    "Major Gap",
    "Not Assessed",
]

GAP_SEVERITY_COLORS = {
    "Met": "#00A19C",
    "Minor Gap": "#FDB924",
    "Major Gap": "#C62828",
    "Not Assessed": "#9E9E9E",
}

CATEGORY_ORDER = [
    "Base",
    "Key",
    "Pacing",
    "Emerging",
]


# =============================================================================
# GENERAL HELPERS
# =============================================================================

def _rg_clean_value(
    value,
    fallback=None,
):
    """
    Clean values used by the Readiness and Gaps page.
    """
    if value is None:
        return fallback

    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass

    cleaned = str(value).strip()

    if cleaned.casefold() in {
        "",
        "none",
        "nan",
        "nat",
    }:
        return fallback

    return cleaned


def _rg_grade_rank(
    salary_grade,
):
    """
    Convert P1 through P10 into numeric ranks.
    """
    cleaned_grade = _rg_clean_value(
        salary_grade
    )

    if cleaned_grade is None:
        return None

    match = re.fullmatch(
        r"P(\d+)",
        cleaned_grade.upper(),
    )

    if match is None:
        return None

    return int(match.group(1))


def _rg_sort_salary_grades(
    salary_grades,
):
    """
    Sort salary grades numerically.
    """
    unique_grades = {
        str(grade).strip().upper()
        for grade in salary_grades
        if _rg_clean_value(grade) is not None
    }

    return sorted(
        unique_grades,
        key=lambda grade: (
            _rg_grade_rank(grade)
            if _rg_grade_rank(grade) is not None
            else 999
        ),
    )


def _rg_normalize_ruler(
    ruler_value,
):
    """
    Normalize career-ruler values.
    """
    cleaned_ruler = _rg_clean_value(
        ruler_value,
        "BASE",
    ).upper()

    aliases = {
        "NO RULER ASSIGNED": "BASE",
        "BASE": "BASE",
        "RDP": "RDP",
        "RMS": "RMS",
        "RSS": "RSS",
    }

    return aliases.get(
        cleaned_ruler,
        cleaned_ruler,
    )


def _rg_get_person_ruler(
    person_row,
    ruler_map,
):
    """
    Retrieve a person's ruler and ensure the ruler exists.
    """
    ruler_value = (
        person_row.get("Ruler Type")
        or person_row.get("ruler_type")
    )

    if _rg_clean_value(ruler_value) is None:
        ruler_value = (
            person_row.get("Background")
        )

    ruler_name = _rg_normalize_ruler(
        ruler_value
    )

    ruler_lookup = {
        str(key).strip().upper(): key
        for key in ruler_map.keys()
    }

    if ruler_name in ruler_lookup:
        return ruler_lookup[ruler_name]

    if "BASE" in ruler_lookup:
        return ruler_lookup["BASE"]

    return next(
        iter(ruler_map.keys()),
        None,
    )


def _rg_get_competency_category(
    competency_code,
):
    """
    Map competency codes into analytical categories.
    """
    prefix = str(
        competency_code
    ).strip().upper()[:1]

    category_map = {
        "B": "Base",
        "K": "Key",
        "P": "Pacing",
        "E": "Emerging",
    }

    return category_map.get(
        prefix,
        "Other",
    )


def _rg_gap_severity(
    gap_value,
    is_assessed,
):
    """
    Classify one competency gap.

    Gap equals Actual Score minus Target Score.
    """
    if not is_assessed:
        return "Not Assessed"

    if pd.isna(gap_value):
        return "Not Assessed"

    if gap_value >= 0:
        return "Met"

    if gap_value >= -1:
        return "Minor Gap"

    return "Major Gap"


def _rg_determine_target_sg(
    current_sg,
    ruler_requirements,
    target_mode,
    selected_target_sg=None,
):
    """
    Determine the target SG for one person.

    Modes:
        Current requirement
        Next salary grade
        Selected target grade
    """
    available_grades = _rg_sort_salary_grades(
        ruler_requirements.keys()
    )

    if not available_grades:
        return None

    current_sg = str(
        current_sg or ""
    ).strip().upper()

    if target_mode == "Current requirement":
        if current_sg in available_grades:
            return current_sg

        return None

    if target_mode == "Selected target grade":
        if selected_target_sg in available_grades:
            return selected_target_sg

        return None

    current_rank = _rg_grade_rank(
        current_sg
    )

    if current_rank is None:
        return available_grades[0]

    future_grades = [
        grade
        for grade in available_grades
        if (
            _rg_grade_rank(grade)
            is not None
            and _rg_grade_rank(grade)
            > current_rank
        )
    ]

    if future_grades:
        return future_grades[0]

    return None


# =============================================================================
# GRANULAR READINESS DATASET
# =============================================================================

def _build_readiness_detail_dataframe(
    personnel_dataframe,
    ruler_map,
    target_mode,
    selected_target_sg=None,
):
    """
    Build one row per personnel per required competency.

    This granular dataset is the single analytical source for:
        Personnel readiness
        Category readiness
        Competency gap severity
        Gap-risk analysis
        Department heatmaps
    """
    detail_records = []

    if (
        personnel_dataframe is None
        or personnel_dataframe.empty
        or not ruler_map
    ):
        return pd.DataFrame()

    for dataframe_index, person_row in (
        personnel_dataframe.iterrows()
    ):
        person_name = _rg_clean_value(
            person_row.get("Name"),
            "Unknown Personnel",
        )

        staff_id = _rg_clean_value(
            person_row.get("Staff ID")
        )

        personnel_id = person_row.get("id")

        department = _rg_clean_value(
            person_row.get("Department"),
            "Not Specified",
        )

        position = _rg_clean_value(
            person_row.get("Staff Position"),
            "Not Specified",
        )

        employment_category = _rg_clean_value(
            person_row.get(
                "Employment Category"
            ),
            "Not Specified",
        )

        current_sg = _rg_clean_value(
            person_row.get("SG"),
            "",
        ).upper()

        years_in_grade = pd.to_numeric(
            person_row.get(
                "Years in Salary Grade"
            ),
            errors="coerce",
        )

        career_ruler = _rg_get_person_ruler(
            person_row=person_row,
            ruler_map=ruler_map,
        )

        if career_ruler is None:
            continue

        ruler_requirements = ruler_map.get(
            career_ruler,
            {},
        )

        target_sg = _rg_determine_target_sg(
            current_sg=current_sg,
            ruler_requirements=(
                ruler_requirements
            ),
            target_mode=target_mode,
            selected_target_sg=(
                selected_target_sg
            ),
        )

        if target_sg is None:
            continue

        target_requirements = (
            ruler_requirements.get(
                target_sg,
                {},
            )
        )

        for competency_code in SCORE_COLS:
            if (
                competency_code
                not in target_requirements
            ):
                continue

            target_score = pd.to_numeric(
                target_requirements.get(
                    competency_code
                ),
                errors="coerce",
            )

            if pd.isna(target_score):
                continue

            actual_score = pd.to_numeric(
                person_row.get(
                    competency_code
                ),
                errors="coerce",
            )

            is_assessed = pd.notna(
                actual_score
            )

            gap_value = (
                float(actual_score)
                - float(target_score)
                if is_assessed
                else np.nan
            )

            capped_actual = (
                min(
                    float(actual_score),
                    float(target_score),
                )
                if (
                    is_assessed
                    and target_score > 0
                )
                else 0.0
            )

            negative_gap_burden = (
                abs(min(gap_value, 0))
                if pd.notna(gap_value)
                else 0.0
            )

            gap_severity = _rg_gap_severity(
                gap_value=gap_value,
                is_assessed=is_assessed,
            )

            detail_records.append(
                {
                    "Personnel ID":
                        personnel_id,
                    "DataFrame Index":
                        dataframe_index,
                    "Name":
                        person_name,
                    "Staff ID":
                        staff_id,
                    "Department":
                        department,
                    "Staff Position":
                        position,
                    "Employment Category":
                        employment_category,
                    "Current SG":
                        current_sg,
                    "Career Ruler":
                        career_ruler,
                    "Target SG":
                        target_sg,
                    "Years in Grade":
                        years_in_grade,
                    "Competency Code":
                        competency_code,
                    "Competency Name":
                        COMPETENCY_FULLNAMES.get(
                            competency_code,
                            competency_code,
                        ),
                    "Category":
                        _rg_get_competency_category(
                            competency_code
                        ),
                    "Actual Score":
                        actual_score,
                    "Target Score":
                        float(target_score),
                    "Capped Actual":
                        capped_actual,
                    "Gap":
                        gap_value,
                    "Gap Burden":
                        negative_gap_burden,
                    "Gap Severity":
                        gap_severity,
                    "Is Assessed":
                        bool(is_assessed),
                    "Is Met":
                        bool(
                            is_assessed
                            and gap_value >= 0
                        ),
                    "Is Major Gap":
                        bool(
                            is_assessed
                            and gap_value < -1
                        ),
                    "Is Minor Gap":
                        bool(
                            is_assessed
                            and -1 <= gap_value < 0
                        ),
                }
            )

    return pd.DataFrame(
        detail_records
    )
# =============================================================================
# PERSONNEL READINESS SUMMARY
# =============================================================================

def _classify_readiness_status(
    weighted_readiness,
    strict_readiness,
    coverage,
    major_gap_count,
):
    """
    Apply transparent readiness-status rules.
    """
    if coverage < 40:
        return "Not Assessed"

    if (
        weighted_readiness >= 80
        and strict_readiness >= 75
        and coverage >= 90
        and major_gap_count == 0
    ):
        return "Ready"

    if (
        weighted_readiness >= 65
        and coverage >= 75
        and major_gap_count <= 2
    ):
        return "Near Ready"

    return "Development Required"

def _recommend_readiness_action(
    readiness_status,
    coverage,
    major_gap_count,
    minor_gap_count,
):
    """
    Generate transparent rule-based actions.
    """
    if coverage < 40:
        return "Complete Assessment"

    if readiness_status == "Ready":
        return "Ready for Assessment"

    if (
        readiness_status == "Near Ready"
        and major_gap_count == 0
        and minor_gap_count <= 2
    ):
        return "Close 1-2 Minor Gaps"

    if major_gap_count >= 3:
        return "Leadership Review Required"

    if major_gap_count > 0:
        return "Targeted Technical Development"

    return "Focused Development Plan"

def _find_top_personnel_gap(
    person_detail_dataframe,
):
    """
    Return the largest negative competency gap for one person.
    """
    assessed_gaps = person_detail_dataframe[
        person_detail_dataframe[
            "Gap"
        ].notna()
        & (
            person_detail_dataframe[
                "Gap"
            ] < 0
        )
    ]

    if assessed_gaps.empty:
        return "None"

    worst_gap_row = (
        assessed_gaps.sort_values(
            "Gap",
            ascending=True,
        )
        .iloc[0]
    )

    return (
        f"{worst_gap_row['Competency Code']} - "
        f"{worst_gap_row['Competency Name']}"
    )

def _build_personnel_readiness_summary(
    detail_dataframe,
):
    """
    Aggregate granular competency rows into one row per person.
    """
    if (
        detail_dataframe is None
        or detail_dataframe.empty
    ):
        return pd.DataFrame()

    personnel_records = []

    grouping_columns = [
        "DataFrame Index",
        "Name",
        "Staff ID",
        "Department",
        "Staff Position",
        "Employment Category",
        "Current SG",
        "Career Ruler",
        "Target SG",
    ]

    for group_values, person_detail in (
        detail_dataframe.groupby(
            grouping_columns,
            dropna=False,
        )
    ):
        group_record = dict(
            zip(
                grouping_columns,
                group_values,
            )
        )

        total_required = len(
            person_detail
        )

        assessed_count = int(
            person_detail[
                "Is Assessed"
            ].sum()
        )

        met_count = int(
            person_detail[
                "Is Met"
            ].sum()
        )

        major_gap_count = int(
            person_detail[
                "Is Major Gap"
            ].sum()
        )

        minor_gap_count = int(
            person_detail[
                "Is Minor Gap"
            ].sum()
        )

        coverage = (
            assessed_count
            / total_required
            * 100
            if total_required > 0
            else 0.0
        )

        strict_readiness = (
            met_count
            / total_required
            * 100
            if total_required > 0
            else 0.0
        )

        total_target_score = (
            person_detail[
                "Target Score"
            ]
            .fillna(0)
            .clip(lower=0)
            .sum()
        )

        weighted_readiness = (
            person_detail[
                "Capped Actual"
            ].sum()
            / total_target_score
            * 100
            if total_target_score > 0
            else 0.0
        )

        gap_burden = (
            person_detail[
                "Gap Burden"
            ].sum()
        )

        readiness_status = (
            _classify_readiness_status(
                weighted_readiness=(
                    weighted_readiness
                ),
                strict_readiness=(
                    strict_readiness
                ),
                coverage=coverage,
                major_gap_count=(
                    major_gap_count
                ),
            )
        )

        recommended_action = (
            _recommend_readiness_action(
                readiness_status=(
                    readiness_status
                ),
                coverage=coverage,
                major_gap_count=(
                    major_gap_count
                ),
                minor_gap_count=(
                    minor_gap_count
                ),
            )
        )

        category_readiness = {}

        for category in CATEGORY_ORDER:
            category_detail = (
                person_detail[
                    person_detail["Category"]
                    == category
                ]
            )

            category_target = (
                category_detail[
                    "Target Score"
                ]
                .fillna(0)
                .clip(lower=0)
                .sum()
            )

            category_readiness[
                category
            ] = (
                category_detail[
                    "Capped Actual"
                ].sum()
                / category_target
                * 100
                if category_target > 0
                else np.nan
            )

        years_in_grade = (
            person_detail[
                "Years in Grade"
            ]
            .dropna()
        )

        personnel_records.append(
            {
                **group_record,
                "Required Competencies":
                    total_required,
                "Assessed Competencies":
                    assessed_count,
                "Assessment Coverage %":
                    coverage,
                "Weighted Readiness %":
                    weighted_readiness,
                "Strict Readiness %":
                    strict_readiness,
                "Met Competencies":
                    met_count,
                "Minor Gaps":
                    minor_gap_count,
                "Major Gaps":
                    major_gap_count,
                "Gap Burden":
                    gap_burden,
                "Readiness Status":
                    readiness_status,
                "Recommended Action":
                    recommended_action,
                "Top Gap":
                    _find_top_personnel_gap(
                        person_detail
                    ),
                "Years in Grade":
                    (
                        float(
                            years_in_grade.iloc[0]
                        )
                        if not years_in_grade.empty
                        else np.nan
                    ),
                "Base Readiness %":
                    category_readiness.get(
                        "Base"
                    ),
                "Key Readiness %":
                    category_readiness.get(
                        "Key"
                    ),
                "Pacing Readiness %":
                    category_readiness.get(
                        "Pacing"
                    ),
                "Emerging Readiness %":
                    category_readiness.get(
                        "Emerging"
                    ),
            }
        )

    return pd.DataFrame(
        personnel_records
    )


# =============================================================================
# READINESS PAGE FILTERS
# =============================================================================

def _apply_readiness_personnel_filters(
    personnel_dataframe,
    search_text,
    departments,
    positions,
    salary_grades,
    employment_categories,
):
    """
    Apply filters that exist before readiness calculations.
    """
    filtered_dataframe = (
        personnel_dataframe.copy()
    )

    if search_text:
        search_text = str(
            search_text
        ).strip().casefold()

        name_series = (
            filtered_dataframe[
                "Name"
            ]
            .fillna("")
            .astype(str)
            .str.casefold()
        )

        staff_id_series = (
            filtered_dataframe.get(
                "Staff ID",
                pd.Series(
                    "",
                    index=(
                        filtered_dataframe.index
                    ),
                ),
            )
            .fillna("")
            .astype(str)
            .str.casefold()
        )

        filtered_dataframe = (
            filtered_dataframe[
                name_series.str.contains(
                    search_text,
                    na=False,
                    regex=False,
                )
                | staff_id_series.str.contains(
                    search_text,
                    na=False,
                    regex=False,
                )
            ]
        )

    if departments:
        filtered_dataframe = (
            filtered_dataframe[
                filtered_dataframe[
                    "Department"
                ].isin(departments)
            ]
        )

    if positions:
        filtered_dataframe = (
            filtered_dataframe[
                filtered_dataframe[
                    "Staff Position"
                ].isin(positions)
            ]
        )

    if salary_grades:
        filtered_dataframe = (
            filtered_dataframe[
                filtered_dataframe[
                    "SG"
                ].isin(salary_grades)
            ]
        )

    if (
        employment_categories
        and "Employment Category"
        in filtered_dataframe.columns
    ):
        filtered_dataframe = (
            filtered_dataframe[
                filtered_dataframe[
                    "Employment Category"
                ].isin(
                    employment_categories
                )
            ]
        )

    return filtered_dataframe.copy()

def _build_filter_options(
    dataframe,
    column_name,
):
    """
    Safely build sorted filter options.
    """
    if (
        dataframe is None
        or dataframe.empty
        or column_name
        not in dataframe.columns
    ):
        return []

    return sorted(
        dataframe[
            column_name
        ]
        .dropna()
        .astype(str)
        .str.strip()
        .loc[
            lambda values:
                values.ne("")
        ]
        .unique()
        .tolist()
    )

def _reset_readiness_filters():
    """
    Clear all Readiness and Gaps page widget state.
    """
    readiness_filter_keys = [
        "rg_search",
        "rg_department",
        "rg_position",
        "rg_sg",
        "rg_ruler",
        "rg_employment",
        "rg_target_mode",
        "rg_selected_target_sg",
        "rg_target_sg_disabled",
        "rg_coverage",
        "rg_status",
        "rg_ranking_metric",
        "rg_heatmap_scope",
        "rg_priority_person",
    ]

    for filter_key in readiness_filter_keys:
        if filter_key in st.session_state:
            del st.session_state[
                filter_key
            ]


# =============================================================================
# READINESS VISUAL HELPERS
# =============================================================================

def _create_readiness_status_chart(
    summary_dataframe,
):
    """
    Build the readiness-status horizontal bar chart.
    """
    status_counts = (
        summary_dataframe[
            "Readiness Status"
        ]
        .value_counts()
        .reindex(
            READINESS_STATUS_ORDER,
            fill_value=0,
        )
        .rename_axis(
            "Readiness Status"
        )
        .reset_index(
            name="Personnel"
        )
    )

    figure = px.bar(
        status_counts,
        x="Personnel",
        y="Readiness Status",
        orientation="h",
        text="Personnel",
        color="Readiness Status",
        color_discrete_map=(
            READINESS_STATUS_COLORS
        ),
        category_orders={
            "Readiness Status":
                READINESS_STATUS_ORDER,
        },
    )

    figure.update_traces(
        textposition="outside",
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Personnel: %{x:,.0f}"
            "<extra></extra>"
        ),
    )

    figure.update_layout(
        title="Competency Readiness Status",
        height=390,
        showlegend=False,
        xaxis_title="Personnel",
        yaxis_title=None,
        margin={
            "l": 10,
            "r": 40,
            "t": 60,
            "b": 40,
        },
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
    )

    figure.update_xaxes(
        showgrid=True,
        gridcolor="#E8EDF2",
        zeroline=False,
    )

    return figure

def _create_department_readiness_chart(
    summary_dataframe,
):
    """
    Build readiness by department with population context.
    """
    department_summary = (
        summary_dataframe
        .groupby(
            "Department",
            as_index=False,
        )
        .agg(
            Median_Readiness=(
                "Weighted Readiness %",
                "median",
            ),
            Personnel=(
                "Name",
                "count",
            ),
            Median_Coverage=(
                "Assessment Coverage %",
                "median",
            ),
            Personnel_With_Major_Gaps=(
                "Major Gaps",
                lambda values: int(
                    (values > 0).sum()
                ),
            ),
        )
    )

    department_summary[
        "Major Gap Rate %"
    ] = (
        department_summary[
            "Personnel_With_Major_Gaps"
        ]
        / department_summary[
            "Personnel"
        ]
        * 100
    )

    department_summary = (
        department_summary.sort_values(
            "Median_Readiness",
            ascending=True,
        )
    )

    figure = px.scatter(
        department_summary,
        x="Median_Readiness",
        y="Department",
        size="Personnel",
        color="Median_Coverage",
        custom_data=[
            "Personnel",
            "Median_Coverage",
            "Major Gap Rate %",
        ],
        color_continuous_scale=[
            [0.0, "#FDB924"],
            [0.5, "#BFD730"],
            [1.0, "#00A19C"],
        ],
        size_max=35,
    )

    figure.update_traces(
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Median readiness: %{x:.1f}%<br>"
            "Personnel: %{customdata,.0f}<br>"
            "Median coverage: "
            "%{customdata.1f}%<br>"
            "Major-gap rate: "
            "%{customdata.1f}%"
            "<extra></extra>"
        ),
    )

    figure.add_vline(
        x=80,
        line_dash="dash",
        line_color="#00A19C",
        annotation_text="80% readiness",
        annotation_position="top",
    )

    figure.update_layout(
        title=(
            "Median Readiness by Department"
        ),
        height=390,
        xaxis_title=(
            "Median Weighted Readiness (%)"
        ),
        yaxis_title=None,
        coloraxis_colorbar={
            "title": "Coverage %",
        },
        margin={
            "l": 10,
            "r": 20,
            "t": 60,
            "b": 40,
        },
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
    )

    figure.update_xaxes(
        range=[0, 105],
        showgrid=True,
        gridcolor="#E8EDF2",
    )

    return figure

def _create_readiness_box_plot(
    summary_dataframe,
):
    """
    Build readiness distribution by current salary grade.
    """
    salary_grade_order = (
        _rg_sort_salary_grades(
            summary_dataframe[
                "Current SG"
            ].dropna()
        )
    )

    figure = px.box(
        summary_dataframe,
        x="Current SG",
        y="Weighted Readiness %",
        color="Current SG",
        points="all",
        hover_name="Name",
        hover_data={
            "Current SG": False,
            "Department": True,
            "Staff Position": True,
            "Assessment Coverage %": ":.1f",
            "Major Gaps": True,
            "Target SG": True,
        },
        category_orders={
            "Current SG":
                salary_grade_order,
        },
    )

    figure.add_hline(
        y=80,
        line_dash="dash",
        line_color="#00A19C",
        annotation_text=(
            "Ready threshold"
        ),
        annotation_position="top left",
    )

    figure.update_layout(
        title=(
            "Weighted Readiness Distribution "
            "by Current Salary Grade"
        ),
        height=480,
        showlegend=False,
        xaxis_title="Current Salary Grade",
        yaxis_title="Weighted Readiness (%)",
        margin={
            "l": 20,
            "r": 20,
            "t": 70,
            "b": 40,
        },
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
    )

    figure.update_yaxes(
        range=[0, 105],
        showgrid=True,
        gridcolor="#E8EDF2",
    )

    return figure

def _create_readiness_coverage_scatter(
    summary_dataframe,
):
    """
    Build the readiness versus coverage quadrant.
    """
    scatter_dataframe = (
        summary_dataframe.copy()
    )

    scatter_dataframe[
        "Bubble Size"
    ] = (
        scatter_dataframe[
            "Major Gaps"
        ]
        .fillna(0)
        + 1
    )

    figure = px.scatter(
        scatter_dataframe,
        x="Assessment Coverage %",
        y="Weighted Readiness %",
        size="Bubble Size",
        color="Readiness Status",
        hover_name="Name",
        hover_data={
            "Bubble Size": False,
            "Department": True,
            "Staff Position": True,
            "Current SG": True,
            "Target SG": True,
            "Strict Readiness %": ":.1f",
            "Major Gaps": True,
        },
        color_discrete_map=(
            READINESS_STATUS_COLORS
        ),
        size_max=32,
    )

    figure.add_vline(
        x=90,
        line_dash="dash",
        line_color="#20419A",
        annotation_text=(
            "90% coverage"
        ),
        annotation_position="top",
    )

    figure.add_hline(
        y=80,
        line_dash="dash",
        line_color="#00A19C",
        annotation_text=(
            "80% readiness"
        ),
        annotation_position="top left",
    )

    figure.update_layout(
        title=(
            "Readiness versus Assessment Coverage"
        ),
        height=520,
        xaxis_title="Assessment Coverage (%)",
        yaxis_title="Weighted Readiness (%)",
        legend_title="Readiness Status",
        margin={
            "l": 20,
            "r": 20,
            "t": 70,
            "b": 40,
        },
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
    )

    figure.update_xaxes(
        range=[0, 105],
        showgrid=True,
        gridcolor="#E8EDF2",
    )

    figure.update_yaxes(
        range=[0, 105],
        showgrid=True,
        gridcolor="#E8EDF2",
    )

    return figure

def _create_category_readiness_heatmap(
    summary_dataframe,
):
    """
    Build position by category readiness heatmap.
    """
    category_columns = {
        "Base Readiness %": "Base",
        "Key Readiness %": "Key",
        "Pacing Readiness %": "Pacing",
        "Emerging Readiness %": "Emerging",
    }

    available_columns = [
        column
        for column in category_columns
        if column
        in summary_dataframe.columns
    ]

    heatmap_dataframe = (
        summary_dataframe
        .groupby(
            "Staff Position"
        )[
            available_columns
        ]
        .median()
        .rename(
            columns=category_columns
        )
        .reindex(
            columns=CATEGORY_ORDER
        )
    )

    heatmap_dataframe = (
        heatmap_dataframe.dropna(
            how="all"
        )
    )

    figure = go.Figure(
        data=go.Heatmap(
            z=heatmap_dataframe.values,
            x=heatmap_dataframe.columns,
            y=heatmap_dataframe.index,
            colorscale=[
                [0.0, "#C62828"],
                [0.5, "#FDB924"],
                [0.8, "#BFD730"],
                [1.0, "#00A19C"],
            ],
            zmin=0,
            zmax=100,
            text=np.round(
                heatmap_dataframe.values,
                1,
            ),
            texttemplate="%{text:.1f}%",
            customdata=np.round(
                heatmap_dataframe.values,
                1,
            ),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Category: %{x}<br>"
                "Median readiness: "
                "%{customdata:.1f}%"
                "<extra></extra>"
            ),
            colorbar={
                "title": "Readiness %",
            },
        )
    )

    figure.update_layout(
        title=(
            "Median Category Readiness "
            "by Staff Position"
        ),
        height=450,
        xaxis_title="Competency Category",
        yaxis_title="Staff Position",
        margin={
            "l": 20,
            "r": 20,
            "t": 70,
            "b": 40,
        },
        paper_bgcolor="#FFFFFF",
    )

    return figure

def _create_category_gap_distribution(
    detail_dataframe,
):
    """
    Build a 100 percent category severity chart.
    """
    category_status_counts = (
        detail_dataframe
        .groupby(
            [
                "Category",
                "Gap Severity",
            ]
        )
        .size()
        .reset_index(
            name="Competencies"
        )
    )

    category_totals = (
        category_status_counts
        .groupby(
            "Category"
        )[
            "Competencies"
        ]
        .transform("sum")
    )

    category_status_counts[
        "Percentage"
    ] = (
        category_status_counts[
            "Competencies"
        ]
        / category_totals
        * 100
    )

    figure = px.bar(
        category_status_counts,
        x="Percentage",
        y="Category",
        color="Gap Severity",
        orientation="h",
        barmode="stack",
        text="Percentage",
        custom_data=[
            "Competencies",
        ],
        category_orders={
            "Category":
                CATEGORY_ORDER,
            "Gap Severity":
                GAP_SEVERITY_ORDER,
        },
        color_discrete_map=(
            GAP_SEVERITY_COLORS
        ),
    )

    figure.update_traces(
        texttemplate="%{x:.0f}%",
        textposition="inside",
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Status: %{fullData.name}<br>"
            "Percentage: %{x:.1f}%<br>"
            "Competency records: "
            "%{customdata,.0f}"
            "<extra></extra>"
        ),
    )

    figure.update_layout(
        title=(
            "Gap Severity Distribution "
            "by Competency Category"
        ),
        height=430,
        xaxis_title="Share of Required Competencies (%)",
        yaxis_title=None,
        legend_title="Gap Severity",
        legend={
            "orientation": "h",
            "y": 1.12,
            "x": 0.5,
            "xanchor": "center",
        },
        margin={
            "l": 20,
            "r": 20,
            "t": 90,
            "b": 40,
        },
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
    )

    figure.update_xaxes(
        range=[0, 100],
    )

    return figure

def _build_competency_risk_summary(
    detail_dataframe,
):
    """
    Aggregate competency prevalence and severity.
    """
    risk_records = []

    for (
        competency_code,
        competency_detail,
    ) in detail_dataframe.groupby(
        "Competency Code"
    ):
        assessed_detail = (
            competency_detail[
                competency_detail[
                    "Is Assessed"
                ]
            ]
        )

        assessed_personnel = (
            assessed_detail[
                "Name"
            ]
            .nunique()
        )

        gap_detail = (
            assessed_detail[
                assessed_detail[
                    "Gap"
                ] < 0
            ]
        )

        affected_personnel = (
            gap_detail[
                "Name"
            ]
            .nunique()
        )

        prevalence = (
            affected_personnel
            / assessed_personnel
            * 100
            if assessed_personnel > 0
            else 0.0
        )

        average_severity = (
            gap_detail[
                "Gap Burden"
            ].mean()
            if not gap_detail.empty
            else 0.0
        )

        risk_records.append(
            {
                "Competency Code":
                    competency_code,
                "Competency Name":
                    competency_detail[
                        "Competency Name"
                    ].iloc[0],
                "Category":
                    competency_detail[
                        "Category"
                    ].iloc[0],
                "Assessed Personnel":
                    assessed_personnel,
                "Affected Personnel":
                    affected_personnel,
                "Gap Prevalence %":
                    prevalence,
                "Average Gap Severity":
                    average_severity,
                "Gap Burden":
                    gap_detail[
                        "Gap Burden"
                    ].sum(),
                "Major Gap Count":
                    int(
                        gap_detail[
                            "Is Major Gap"
                        ].sum()
                    ),
            }
        )

    return pd.DataFrame(
        risk_records
    )

def _create_competency_risk_matrix(
    risk_dataframe,
):
    """
    Build prevalence versus severity bubble chart.
    """
    plot_dataframe = (
        risk_dataframe[
            risk_dataframe[
                "Affected Personnel"
            ] > 0
        ]
        .copy()
    )

    figure = px.scatter(
        plot_dataframe,
        x="Gap Prevalence %",
        y="Average Gap Severity",
        size="Affected Personnel",
        color="Category",
        hover_name="Competency Code",
        hover_data={
            "Competency Name": True,
            "Category": True,
            "Affected Personnel": True,
            "Assessed Personnel": True,
            "Gap Burden": ":.1f",
            "Major Gap Count": True,
        },
        color_discrete_map={
            "Base": "#00A19C",
            "Key": "#20419A",
            "Pacing": "#763F98",
            "Emerging": "#FDB924",
        },
        size_max=45,
    )

    if not plot_dataframe.empty:
        prevalence_median = (
            plot_dataframe[
                "Gap Prevalence %"
            ].median()
        )

        severity_median = (
            plot_dataframe[
                "Average Gap Severity"
            ].median()
        )

        figure.add_vline(
            x=prevalence_median,
            line_dash="dot",
            line_color="#64748B",
        )

        figure.add_hline(
            y=severity_median,
            line_dash="dot",
            line_color="#64748B",
        )

    figure.update_layout(
        title="Competency Risk Matrix",
        height=540,
        xaxis_title=(
            "Personnel with a Gap (%)"
        ),
        yaxis_title=(
            "Average Gap Severity"
        ),
        legend_title="Category",
        margin={
            "l": 20,
            "r": 20,
            "t": 70,
            "b": 40,
        },
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
    )

    figure.update_xaxes(
        range=[0, 105],
        showgrid=True,
        gridcolor="#E8EDF2",
    )

    figure.update_yaxes(
        rangemode="tozero",
        showgrid=True,
        gridcolor="#E8EDF2",
    )

    return figure

def _create_top_competency_gap_chart(
    risk_dataframe,
    ranking_metric,
):
    """
    Build ranked competency-gap chart.
    """
    ranking_map = {
        "Affected personnel":
            "Affected Personnel",
        "Average gap severity":
            "Average Gap Severity",
        "Total gap burden":
            "Gap Burden",
        "Major-gap count":
            "Major Gap Count",
    }

    metric_column = ranking_map[
        ranking_metric
    ]

    plot_dataframe = (
        risk_dataframe.sort_values(
            metric_column,
            ascending=False,
        )
        .head(12)
        .sort_values(
            metric_column,
            ascending=True,
        )
        .copy()
    )

    plot_dataframe[
        "Competency Label"
    ] = (
        plot_dataframe[
            "Competency Code"
        ]
        + " - "
        + plot_dataframe[
            "Competency Name"
        ]
    )

    figure = px.bar(
        plot_dataframe,
        x=metric_column,
        y="Competency Label",
        orientation="h",
        color="Category",
        text=metric_column,
        color_discrete_map={
            "Base": "#00A19C",
            "Key": "#20419A",
            "Pacing": "#763F98",
            "Emerging": "#FDB924",
        },
        custom_data=[
            "Affected Personnel",
            "Gap Prevalence %",
            "Average Gap Severity",
            "Gap Burden",
            "Major Gap Count",
        ],
    )

    figure.update_traces(
        texttemplate="%{x:.1f}",
        textposition="outside",
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Affected personnel: "
            "%{customdata,.0f}<br>"
            "Gap prevalence: "
            "%{customdata.1f}%<br>"
            "Average severity: "
            "%{customdata.2f}<br>"
            "Gap burden: "
            "%{customdata.1f}<br>"
            "Major gaps: "
            "%{customdata,.0f}"
            "<extra></extra>"
        ),
    )

    figure.update_layout(
        title=(
            f"Top Competency Gaps by "
            f"{ranking_metric}"
        ),
        height=540,
        xaxis_title=ranking_metric.title(),
        yaxis_title=None,
        legend_title="Category",
        margin={
            "l": 10,
            "r": 50,
            "t": 70,
            "b": 40,
        },
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
    )

    figure.update_xaxes(
        showgrid=True,
        gridcolor="#E8EDF2",
    )

    return figure

def _create_department_competency_heatmap(
    detail_dataframe,
    top_n,
):
    """
    Build department by competency gap-rate heatmap.
    """
    assessed_detail = (
        detail_dataframe[
            detail_dataframe[
                "Is Assessed"
            ]
        ]
        .copy()
    )

    if assessed_detail.empty:
        return None

    assessed_detail[
        "Has Gap"
    ] = (
        assessed_detail[
            "Gap"
        ] < 0
    )

    competency_gap_rates = (
        assessed_detail
        .groupby(
            "Competency Code"
        )[
            "Has Gap"
        ]
        .mean()
        .sort_values(
            ascending=False
        )
    )

    if top_n != "All":
        selected_competencies = (
            competency_gap_rates
            .head(int(top_n))
            .index
            .tolist()
        )
    else:
        selected_competencies = (
            competency_gap_rates
            .index
            .tolist()
        )

    heatmap_source = (
        assessed_detail[
            assessed_detail[
                "Competency Code"
            ].isin(
                selected_competencies
            )
        ]
    )

    heatmap_dataframe = (
        heatmap_source
        .groupby(
            [
                "Department",
                "Competency Code",
            ]
        )[
            "Has Gap"
        ]
        .mean()
        .mul(100)
        .unstack(
            "Competency Code"
        )
        .reindex(
            columns=selected_competencies
        )
    )

    heatmap_dataframe = (
        heatmap_dataframe.dropna(
            how="all"
        )
    )

    if heatmap_dataframe.empty:
        return None

    figure = go.Figure(
        data=go.Heatmap(
            z=heatmap_dataframe.values,
            x=heatmap_dataframe.columns,
            y=heatmap_dataframe.index,
            zmin=0,
            zmax=100,
            colorscale=[
                [0.0, "#E8F5F3"],
                [0.5, "#FDB924"],
                [1.0, "#C62828"],
            ],
            text=np.round(
                heatmap_dataframe.values,
                0,
            ),
            texttemplate="%{text:.0f}%",
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Competency: %{x}<br>"
                "Personnel below target: "
                "%{z:.1f}%"
                "<extra></extra>"
            ),
            colorbar={
                "title": "Below Target %",
            },
        )
    )

    figure.update_layout(
        title=(
            "Department by Competency Gap Rate"
        ),
        height=max(
            420,
            40
            * len(
                heatmap_dataframe.index
            )
            + 160,
        ),
        xaxis_title="Competency Code",
        yaxis_title="Department",
        margin={
            "l": 20,
            "r": 20,
            "t": 70,
            "b": 40,
        },
        paper_bgcolor="#FFFFFF",
    )

    return figure

def _create_personnel_priority_scatter(
    summary_dataframe: pd.DataFrame,
) -> go.Figure | None:
    """
    Create the personnel readiness-versus-gap-burden chart.

    X-axis:
        Weighted readiness percentage

    Y-axis:
        Total gap burden

    Bubble size:
        Years in grade, with a minimum size of 1

    Bubble color:
        Readiness status
    """
    required_columns = [
        "Name",
        "Weighted Readiness %",
        "Gap Burden",
        "Readiness Status",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in summary_dataframe.columns
    ]

    if missing_columns:
        return None

    plot_dataframe = (
        summary_dataframe[
            summary_dataframe[
                "Weighted Readiness %"
            ].notna()
            & summary_dataframe[
                "Gap Burden"
            ].notna()
        ]
        .copy()
    )

    if plot_dataframe.empty:
        return None

    # Plotly requires positive bubble sizes.
    if "Years in Grade" in plot_dataframe.columns:
        years_in_grade = pd.to_numeric(
            plot_dataframe["Years in Grade"],
            errors="coerce",
        )
    else:
        years_in_grade = pd.Series(
            0.0,
            index=plot_dataframe.index,
        )

    plot_dataframe["Bubble Size"] = (
        years_in_grade
        .fillna(0)
        .clip(lower=0)
        .add(1)
    )

    # Ensure quantitative fields are numeric.
    plot_dataframe[
        "Weighted Readiness %"
    ] = pd.to_numeric(
        plot_dataframe[
            "Weighted Readiness %"
        ],
        errors="coerce",
    )

    plot_dataframe[
        "Gap Burden"
    ] = pd.to_numeric(
        plot_dataframe[
            "Gap Burden"
        ],
        errors="coerce",
    )

    plot_dataframe = plot_dataframe.dropna(
        subset=[
            "Weighted Readiness %",
            "Gap Burden",
        ]
    )

    if plot_dataframe.empty:
        return None

    # Include only hover columns that actually exist.
    optional_hover_columns = {
        "Staff ID": True,
        "Department": True,
        "Staff Position": True,
        "Current SG": True,
        "Career Ruler": True,
        "Target SG": True,
        "Assessment Coverage %": ":.1f",
        "Strict Readiness %": ":.1f",
        "Major Gaps": True,
        "Minor Gaps": True,
        "Recommended Action": True,
        "Bubble Size": False,
    }

    hover_data = {
        column: formatting
        for column, formatting
        in optional_hover_columns.items()
        if column in plot_dataframe.columns
    }

    figure = px.scatter(
        plot_dataframe,
        x="Weighted Readiness %",
        y="Gap Burden",
        size="Bubble Size",
        color="Readiness Status",
        hover_name="Name",
        hover_data=hover_data,
        color_discrete_map=(
            READINESS_STATUS_COLORS
        ),
        category_orders={
            "Readiness Status":
                READINESS_STATUS_ORDER,
        },
        size_max=36,
        opacity=0.82,
    )

    readiness_median = (
        plot_dataframe[
            "Weighted Readiness %"
        ].median()
    )

    gap_burden_median = (
        plot_dataframe[
            "Gap Burden"
        ].median()
    )

    if pd.notna(readiness_median):
        figure.add_vline(
            x=float(readiness_median),
            line_dash="dot",
            line_color="#64748B",
            annotation_text="Median readiness",
            annotation_position="top",
        )

    if pd.notna(gap_burden_median):
        figure.add_hline(
            y=float(gap_burden_median),
            line_dash="dot",
            line_color="#64748B",
            annotation_text="Median gap burden",
            annotation_position="top left",
        )

    # Add the formal readiness threshold separately.
    figure.add_vline(
        x=80,
        line_dash="dash",
        line_color="#00A19C",
        annotation_text="80% readiness threshold",
        annotation_position="bottom right",
    )

    figure.update_traces(
        marker={
            "line": {
                "width": 1,
                "color": "#FFFFFF",
            },
        },
    )

    figure.update_layout(
        title={
            "text": (
                "<b>Personnel Readiness versus Gap Burden</b>"
                "<br>"
                "<sup>Bubble size represents years in grade</sup>"
            ),
            "x": 0.01,
            "xanchor": "left",
        },
        height=560,
        xaxis_title="Weighted Readiness (%)",
        yaxis_title="Gap Burden",
        legend_title="Readiness Status",
        margin={
            "l": 30,
            "r": 20,
            "t": 80,
            "b": 50,
        },
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        hoverlabel={
            "bgcolor": "#FFFFFF",
            "font": {
                "color": "#0F172A",
            },
        },
    )

    figure.update_xaxes(
        range=[0, 105],
        showgrid=True,
        gridcolor="#E8EDF2",
        zeroline=False,
    )

    figure.update_yaxes(
        rangemode="tozero",
        showgrid=True,
        gridcolor="#E8EDF2",
        zeroline=False,
    )

    # This return must remain inside the function.
    return figure
# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(page_title=APP_TITLE, page_icon="📊", layout="wide",
                    initial_sidebar_state="collapsed", menu_items=None)
st.markdown(f"<style>{PETRONAS_CSS}</style>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# 1. DATABASE & FILE PATH SETUP
# ─────────────────────────────────────────────────────────────────────────────
import data_loader

@st.cache_resource
def get_engine():
    engine = init_db(DATABASE_URL)
    Base.metadata.create_all(engine)
    return engine
engine = get_engine()

if "data_version" not in st.session_state:
    st.session_state.data_version = 0

def bump_version():
    st.session_state.data_version += 1

# Excel Master Workbook Path (live source by default)
EXCEL_PATH = EXCEL_PATH

# ─────────────────────────────────────────────────────────────────────────────
# 2. CACHED DATA LOADERS (USES YOUR DATA_LOADER.PY)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner= True)
def _load_wide_df_cached(_version: int) -> pd.DataFrame:
    """Cached internal loader for the wide dataframe."""
    if not USE_LIVE_EXCEL_SOURCE:
        session = get_session(engine)
        try:
            df = db_ops.get_wide_dataframe(session)
        finally:
            session.close()
        return an.add_category_averages(df) if df is not None and not df.empty else pd.DataFrame()

    if not EXCEL_PATH or not os.path.exists(EXCEL_PATH):
        raise FileNotFoundError(f"Excel workbook not found: {EXCEL_PATH}")

    df = data_loader.load_master_data(EXCEL_PATH)
    return an.add_category_averages(df)

def load_wide_df(_version: int) -> pd.DataFrame:
    """Wrapper that times the cached loader and records timings in session state."""
    start = time.time()
    try:
        df = _load_wide_df_cached(_version)
    except Exception:
        duration = time.time() - start
        st.session_state.setdefault("timings", {})["load_wide_df"] = duration
        raise
    duration = time.time() - start
    st.session_state.setdefault("timings", {})["load_wide_df"] = duration
    return df

@st.cache_data(show_spinner=True)
def _load_ruler_and_mappings_cached():
    """Cached loader for ruler maps and tech labels."""
    if not EXCEL_PATH or not os.path.exists(EXCEL_PATH):
        raise FileNotFoundError(f"Excel workbook not found: {EXCEL_PATH}")

    r_map, t_labels = data_loader.load_ruler_and_tech_mapping(EXCEL_PATH)
    return r_map,COMPETENCY_FULLNAMES

def load_ruler_and_mappings():
    """Wrapper that times the ruler/tech mapping load and records timings."""
    start = time.time()
    try:
        r_map, t_labels = _load_ruler_and_mappings_cached()
    except Exception:
        duration = time.time() - start
        st.session_state.setdefault("timings", {})["ruler_map"] = duration
        raise
    duration = time.time() - start
    st.session_state.setdefault("timings", {})["ruler_map"] = duration
    return r_map, t_labels

def export_to_pdf(person_row, target_sg, df_gap, metrics, filename="individual_assessment_report.pdf"):
    """Create a PDF report for the selected competency assessment."""
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    if not isinstance(metrics, (tuple, list)) or len(metrics) < 2:
        strict_readiness = 0.0
        weighted_readiness = 0.0
        category_readiness = {}
    else:
        strict_readiness = float(metrics[0]) if metrics[0] is not None else 0.0
        weighted_readiness = float(metrics[1]) if metrics[1] is not None else 0.0
        category_readiness = metrics[2] if len(metrics) > 2 else {}

    if df_gap is None:
        df_gap = pd.DataFrame(columns=["Status"])

    pdf_buffer = BytesIO()
    document = SimpleDocTemplate(
        pdf_buffer,
        pagesize=landscape(A4),
        rightMargin=12 * mm,
        leftMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    styles = getSampleStyleSheet()
    elements = []

    employee_name = person_row.get("Name") or "Not Available"
    staff_id = person_row.get("Staff ID") or "Not Available"
    current_sg = person_row.get("SG") or "Not Available"
    staff_position = person_row.get("Staff Position") or "Not Available"
    department = person_row.get("Department") or "Not Available"
    ruler_type = person_row.get("Ruler Type") or "Not Available"

    elements.append(Paragraph("Individual Competency Assessment Report", styles["Title"]))
    elements.append(Spacer(1, 8))

    personnel_data = [
        ["Employee", str(employee_name), "Staff ID", str(staff_id)],
        ["Position", str(staff_position), "Current Grade", str(current_sg)],
        ["Department", str(department), "Target Grade", str(target_sg)],
        ["Career Ruler", str(ruler_type), "Report Date", datetime.now().strftime("%d %b %Y")],
    ]

    personnel_table = Table(personnel_data, colWidths=[32 * mm, 70 * mm, 32 * mm, 70 * mm])
    personnel_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#00A19C")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#00A19C")),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
                ("TEXTCOLOR", (2, 0), (2, -1), colors.white),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(personnel_table)
    elements.append(Spacer(1, 12))

    elements.append(Paragraph("Readiness Summary", styles["Heading2"]))

    met_count = int((df_gap["Status"] == "✅ Met").sum()) if "Status" in df_gap.columns else 0
    minor_count = int((df_gap["Status"] == "🟡 Minor Gap").sum()) if "Status" in df_gap.columns else 0
    major_count = int((df_gap["Status"] == "🔴 Major Gap").sum()) if "Status" in df_gap.columns else 0
    unassessed_count = int((df_gap["Status"] == "Not Assessed").sum()) if "Status" in df_gap.columns else 0

    readiness_data = [
        ["Weighted Readiness", "Strict Readiness", "Met", "Minor Gaps", "Major Gaps", "Not Assessed"],
        [f"{weighted_readiness:.1f}%", f"{strict_readiness:.1f}%", str(met_count), str(minor_count), str(major_count), str(unassessed_count)],
    ]

    readiness_table = Table(readiness_data, repeatRows=1)
    readiness_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#20419A")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    elements.append(readiness_table)
    elements.append(Spacer(1, 12))

    elements.append(Paragraph(f"Competency Gap Analysis to {target_sg}", styles["Heading2"]))

    gap_table_data: list[list[object]] = [["Category", "Code", "Competency", "Actual", "Target", "Gap", "Status"]]
    for _, row in df_gap.iterrows():
        actual_value = row.get("Actual Score")
        target_value = row.get("Target Score")
        gap_value = row.get("Gap")

        actual_display = str(int(round(float(actual_value)))) if pd.notna(actual_value) else "-"
        target_display = str(int(round(float(target_value)))) if pd.notna(target_value) else "-"
        gap_display = str(int(round(float(gap_value)))) if pd.notna(gap_value) else "-"

        gap_table_data.append(
            [
                str(row.get("Category", "")),
                str(row.get("Competency Code", "")),
                Paragraph(str(row.get("Competency Name", "")), styles["BodyText"]),
                actual_display,
                target_display,
                gap_display,
                str(row.get("Status", "")),
            ]
        )

    gap_table = Table(gap_table_data, repeatRows=1, colWidths=[25 * mm, 16 * mm, 90 * mm, 18 * mm, 18 * mm, 18 * mm, 30 * mm])
    gap_table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003D5C")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (1, -1), "CENTER"),
        ("ALIGN", (3, 1), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]

    for table_row_number, (_, row) in enumerate(df_gap.iterrows(), start=1):
        status = row.get("Status")
        if status == "✅ Met":
            background = colors.HexColor("#C8E6C9")
        elif status == "🟡 Minor Gap":
            background = colors.HexColor("#FFF9C4")
        elif status == "🔴 Major Gap":
            background = colors.HexColor("#FFCDD2")
        else:
            background = colors.HexColor("#E0E0E0")
        gap_table_style.append(("BACKGROUND", (6, table_row_number), (6, table_row_number), background))

    gap_table.setStyle(TableStyle(gap_table_style))
    elements.append(gap_table)

    if category_readiness:
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Category Readiness", styles["Heading2"]))
        summary_lines = [f"{name}: {value:.1f}%" for name, value in category_readiness.items()]
        elements.append(Paragraph(", ".join(summary_lines), styles["BodyText"]))

    document.build(elements)
    pdf_buffer.seek(0)
    return pdf_buffer
# ─────────────────────────────────────────────────────────────────────────────
# 3. INITIALIZE SESSION STATE SAFELY
# ─────────────────────────────────────────────────────────────────────────────

# Load Dataframe
st.session_state.df = load_wide_df(st.session_state.data_version)

# Load Ruler Map & Tech Labels using your data_loader module
if "ruler_map" not in st.session_state or "tech_labels" not in st.session_state:
    r_map, t_labels = load_ruler_and_mappings()
    st.session_state.ruler_map = r_map
    st.session_state.tech_labels = t_labels

# Assign local variables for the rest of app.py to use
df = st.session_state.df
ruler_map = st.session_state.ruler_map
tech_labels = st.session_state.tech_labels

# Hide the PETRONAS loader now that initial data is loaded
st.markdown(
    """
    <script>
    (function(){
      const l = document.getElementById('petronas-loader');
      if(l) l.classList.add('is-hidden');
      const s = document.getElementById('petronas-shell');
      if(s) s.classList.add('is-hidden');
      document.body.classList.add('petronas-ready');
    })();
    </script>
    """,
    unsafe_allow_html=True,
)

# Display timing diagnostics in the sidebar for debugging/optimization
timings = st.session_state.get('timings', {})
if timings:
    with st.sidebar.expander('Load timings (debug)'):
        for key, val in timings.items():
            st.write(f"- {key}: {val:.2f}s")

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR NAVIGATION
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.title("📊 " + APP_TITLE)
page = st.sidebar.radio("User Menu", [
    "🏠 Dashboard Home",
    "🌡️ Competency Heatmap",
    "👤 Individual Assessment & Talent Profile",
    "🎯 Readiness & Gaps",
    "📊 Chart Builder & Depth Analysis",
    "⚙️ Admin: Import Data",
    "⚙️ Admin: Personnel CRUD",
    "⚙️ Admin: Assessment Entry",
])

from navigation import render_navigation
page = render_navigation()

df = load_wide_df(st.session_state.data_version)

if df.empty and not page.startswith("⚙️ Admin: Import"):
    st.warning("⚠️ No data in database yet. Go to **Admin: Import Data** to load the Excel master file.")

# ═════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD HOME
# ═════════════════════════════════════════════════════════════════════════════
if page == "🏠 Dashboard Home":
    st.title("🏠 Dashboard Home")

    if df.empty:
        st.stop()

    session = get_session(engine)
    stats = db_ops.get_stats_overview(session)
    session.close()

    # =========================================================================
    # TOP METRICS ROW
    # =========================================================================
    c1, c2, c3, c4, c5 = st.columns(5)

    # Total personnel
    total_personnel = len(df)
    # Male personnel
    male_count = ( df["Gender"] .astype(str) .str.strip() .str.upper() .eq("M") .sum() if "Gender" in df.columns else 0)
    # Female personnel
    female_count = ( df["Gender"] .astype(str) .str.strip() .str.upper() .eq("F") .sum() if "Gender" in df.columns else 0 )
    # CDH employees
    cdh_count = ( df["Employment Category"] .astype(str) .str.strip() .str.upper() .eq("CDH") .sum() if "Employment Category" in df.columns else 0)
    # Permanent employees
    permanent_count = ( df["Employment Category"] .astype(str) .str.strip() .str.upper() .eq("PERMANENT") .sum() if "Employment Category" in df.columns else 0 )

    with c1: st.metric( "Total Personnel", int(total_personnel),)
    with c3: st.metric( "CDH Employees", int(cdh_count),)
    with c2: st.metric( "Permanent Employees", int(permanent_count),)
    with c4: st.metric( "Male", int(male_count), )
    with c5: st.metric( "Female", int(female_count), )

# =========================================================================
# NATIONALITY DISTRIBUTION
# =========================================================================

    st.markdown("---")
    st.subheader("🌐 RE Around The Globe")
    
    nationality_map_df, unmatched_nationalities = prepare_nationality_map_data(df)

    # --- TOP 5 NATIONALITIES METRIC CARDS ---
    if not nationality_map_df.empty:
        # Get the top 5 sorted by Personnel Count
        top_nationalities = nationality_map_df.head(5)
        
        # Create dynamic columns based on how many top nationalities exist (up to 5)
        num_cols = min(len(top_nationalities), 5)
        if num_cols > 0:
            cols = st.columns(num_cols)
            for i, (_, row) in enumerate(top_nationalities.iterrows()):
                with cols[i]:
                    st.metric(
                        label=row["Nationality"], 
                        value=int(row["Personnel Count"]),
                        delta=row["Representation Display"] # Shows percentage representation as a neat subtitle delta
                    )
    # ----------------------------------------

    if nationality_map_df.empty:
        st.info("No valid nationality data is available for the geographical visualization.")
    else:
        nationality_fig = create_nationality_bubble_map(nationality_map_df)
        
        st.plotly_chart(
            nationality_fig, 
            use_container_width=True, 
            config={
                "displaylogo": True,
                "scrollZoom": True,
                "responsive": True,
                "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                "toImageButtonOptions": {
                    "format": "png",
                    "filename": "RE_personnel_nationality_map",
                    "height": 800,
                    "width": 1400,
                    "scale": 2,
                },
            },
        )

        st.caption(
            "Bubble size and color represent the number of personnel associated with each nationality. "
            "Markers use approximate country-centroid coordinates."
        )

    if unmatched_nationalities:
        with st.expander("⚠️ Nationality values requiring mapping"):
            st.write(unmatched_nationalities)
    
    # =========================================================================
    # ROW 1: POSITION & DEPARTMENT DISTRIBUTIONS
    # =========================================================================
    col1, col2,= st.columns(2)

    with col1:
        st.subheader("📊 Position Breakdown")
        
        if "SG" in df.columns and "Employment Category" in df.columns:
            df_chart = df.copy()
            
            # Map SG to Position Bracket using your config dictionary
            df_chart["Position_Bracket"] = df_chart["SG"].map(config.SG_TO_POSITION_BRACKET).fillna("Other")
            
            # Clean employment category
            df_chart["Clean_Emp_Category"] = (
                df_chart["Employment Category"]
                .astype(str)
                .str.strip()
                .str.upper()
                .map({"PERMANENT": "Permanent", "CDH": "CDH"})
                .fillna("Other")
            )
            
            # Group by Position Bracket and Employment Category
            pos_emp = (
                df_chart.groupby(["Position_Bracket", "Clean_Emp_Category"])
                .size()
                .unstack(fill_value=0)
            )
            
            # Reindex using the official hierarchy order from config
            present_pos = [p for p in config.POSITION_HIERARCHY_ORDER if p in pos_emp.index]
            pos_emp = pos_emp.reindex(present_pos)

            for col_name in ["Permanent", "CDH"]:
                if col_name not in pos_emp.columns:
                    pos_emp[col_name] = 0

            # Calculate total sum per position bracket for the top label
            pos_emp["Total"] = pos_emp["Permanent"] + pos_emp["CDH"]

            plot_df = pos_emp.reset_index()

            fig = px.bar(
                plot_df, 
                x="Position_Bracket", 
                y=["Permanent", "CDH"],
                barmode="stack", 
                title="", 
                labels={"Position_Bracket": "Position", "value": "Personnel Count", "variable": "Type"},
                category_orders={"Position_Bracket": present_pos},
                color_discrete_map={"Permanent": "#20419A", "CDH": "#00A19C"}
            )

            fig.add_trace(
                go.Scatter(
                    x=plot_df["Position_Bracket"],
                    y=plot_df["Total"],
                    text=plot_df["Total"],
                    mode="text",
                    textposition="top center",
                    textfont=dict(size=12, color="black", family="sans-serif"),
                    showlegend=False,
                    hoverinfo="skip"
                )
            )
            
            fig.update_layout(
                height=380, 
                margin=dict(l=10, r=10, t=30, b=20), 
                xaxis_title="", 
                yaxis_title="Count",
                legend=dict(orientation="h", y=1.1, x=0.5, xanchor="center", title_text="")
            )
            # Show individual segment counts inside the bars
            fig.update_traces(textposition="inside", texttemplate="%{y}", selector=dict(type="bar"))
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Required data columns missing.")

    with col2:
        st.subheader("📊 Salary Grade Distribution by Employment Type")
        
        if "SG" in df.columns and "Employment Category" in df.columns:
            # 1. Clean and normalize the employment category column
            df_chart = df.copy()
            df_chart["Clean_Emp_Category"] = (
                df_chart["Employment Category"]
                .astype(str)
                .str.strip()
                .str.upper()
                .map({"PERMANENT": "Permanent", "CDH": "CDH"})
                .fillna("Other")
            )
            
            # 2. Use groupby and unstack to guarantee "SG" is kept explicitly as a column name
            sg_emp = (
                df_chart.groupby(["SG", "Clean_Emp_Category"])
                .size()
                .unstack(fill_value=0)
            )
            
            # 3. Sort using your official SG hierarchy from config
            official_sg_order = config.SG_HIERARCHY
            present_sgs = [g for g in official_sg_order if g in sg_emp.index]
            
            sg_emp = sg_emp.reindex(present_sgs)

            # Ensure both Permanent and CDH columns exist FIRST to prevent crashes
            for col_name in ["Permanent", "CDH"]:
                if col_name not in sg_emp.columns:
                    sg_emp[col_name] = 0

            # Calculate total sum per salary grade AFTER columns are guaranteed to exist
            sg_emp["Total"] = sg_emp["Permanent"] + sg_emp["CDH"]

            # Reset index safely so "SG" is guaranteed to be a column name
            plot_df = sg_emp.reset_index()

            # 4. Build stacked bar chart
            fig = px.bar(
                plot_df, 
                x="SG", 
                y=["Permanent", "CDH"],
                barmode="stack", 
                title="", 
                labels={"SG": "Salary Grade", "value": "Number of Personnel", "variable": "Employment Type"},
                category_orders={"SG": present_sgs},
                color_discrete_map={"Permanent": "#20419A", "CDH": "#00A19C"}
            )

            # Fixed: Changed "Position_Bracket" to "SG" to match the x-axis column
            fig.add_trace(
                go.Scatter(
                    x=plot_df["SG"],
                    y=plot_df["Total"],
                    text=plot_df["Total"],
                    mode="text",
                    textposition="top center",
                    textfont=dict(size=12, color="black", family="sans-serif"),
                    showlegend=False,
                    hoverinfo="skip"
                )
            )
            
            fig.update_layout(
                height=400, 
                margin=dict(l=10, r=20, t=40, b=20), 
                xaxis_title="Salary Grade", 
                yaxis_title="Number of Personnel",
                legend=dict(title="Employment Type", yanchor="top", y=0.99, xanchor="right", x=0.99),
                yaxis=dict(range=[0, plot_df["Total"].max() * 1.15] if not plot_df.empty else [0, 10]) # Adds headroom for top totals
            )
            
            # Show stacked counts inside the bars
            fig.update_traces(textposition="inside", texttemplate="%{y}", selector=dict(type="bar")) 
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Salary Grade or Employment Category data not available for this visualization.")
    #=====================================================
    # SECTION NAME DISTRIBUTION
    # =====================================================
    col3, col4, col5 = st.columns(3)

    with col5:
            st.subheader("🏢 Department Distribution")
            
            # 1. Count occurrences
            dept = df["Department"].value_counts().reset_index()
            dept.columns = ["Department", "Count"]
            
            # 2. Combine departments < threshold into "Others"
            total_count = dept["Count"].sum()
            threshold = 0.02  # 2% threshold
            
            dept["Department"] = dept.apply(
                lambda row: row["Department"] if (row["Count"] / total_count) >= threshold else "Others",
                axis=1
            )
            
            # Regroup and sum the counts for "Others"
            dept_grouped = dept.groupby("Department", as_index=False)["Count"].sum()
            dept_grouped = dept_grouped.sort_values(by=["Count"], ascending=False)
            
            # 3. Create Donut Chart
            fig = px.pie(
                dept_grouped, 
                names="Department", 
                values="Count", 
                hole=0.2,
                color_discrete_sequence=px.colors.sequential.Plasma
            )
            
            # 4. Format labels inside slices
            fig.update_traces(
                textposition="inside",
                textinfo="percent+label",
                hovertemplate="<b>%{label}</b><br>Count: %{value}<br>Share: %{percent}"
            )
            
            # 5. Clean layout & margins
            fig.update_layout(
                height=400,
                margin=dict(t=20, b=20, l=10, r=10),
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.1,
                    xanchor="center",
                    x=0.5,
                    title_text=""
                )
            )
            
            st.plotly_chart(fig, use_container_width=True)

    with col3:
        st.subheader("🌏 Section Distribution")
        
        section = df["Section Name"].value_counts().reset_index()
        section.columns = ["Section Name", "Count"]
        
        # Consolidate < 4 into "Other"
        threshold = 4
        main_sections = section[section["Count"] >= threshold].copy()
        other_sections = section[section["Count"] < threshold].copy()
        
        if len(other_sections) > 0:
            other_row = pd.DataFrame({
                "Section Name": ["Other"],
                "Count": [other_sections["Count"].sum()]
            })
            section_final = pd.concat([main_sections, other_row], ignore_index=True)
        else:
            section_final = main_sections
        
        section_final = section_final.sort_values("Count", ascending=False).reset_index(drop=True)
        section_final["y_position"] = range(len(section_final))
        
        fig = px.scatter(
            section_final,
            x="Count", y="y_position", size="Count", color="Count",
            hover_name="Section Name", color_discrete_sequence=px.colors.qualitative.G10, size_max=75)
        
        fig.update_traces(
            hovertemplate="<b>%{hovertext}</b><br>Personnel: %{x}<extra></extra>"
        )
        
        fig.update_layout(
            height=500,
            showlegend=False, coloraxis_showscale=False, margin=dict(l=10, r=20, t=40, b=20), xaxis_title="Number of Personnel", yaxis_title="",
            yaxis=dict( tickmode="array", tickvals=list(range(len(section_final))), ticktext=section_final["Section Name"].tolist(), showgrid=False),hovermode="closest",)
        
        st.plotly_chart(fig, use_container_width=True)

    # =====================================================
    # CURRENT ASSIGNMENT DISTRIBUTION
    # =====================================================
    with col4:
        st.subheader("🏢 Office Location Distribution")

        # 1. Count all values and reset index directly
        assignment_df = df["Current Location:"].value_counts().reset_index()

        # 2. Rename columns and sort (ascending puts the largest bar at the top)
        assignment_df.columns = ["Current Assignment", "Count"]
        assignment_df = assignment_df.sort_values("Count", ascending=True)

        # 3. Dynamic height to prevent squishing (Minimum 500px, adds 25px per row)
        chart_height = max(500, len(assignment_df) * 25)

        # 4. Build the chart
        fig = px.bar(
            assignment_df, 
            x="Count", 
            y="Current Assignment", orientation="h", text="Count",  color="Count", color_continuous_scale="Emrld")

        fig.update_traces(
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Count: %{x}<extra></extra>"
        )

        fig.update_layout(
            height=chart_height,  # Applied dynamic height here
            showlegend=False, coloraxis_showscale=False, margin=dict(l=10, r=30, t=40, b=20), xaxis_title="Number of Personnel",  yaxis_title="")
        
        st.plotly_chart(fig, use_container_width=True)
 
    # =========================================================================
    # ROW 2: GENDER DISTRIBUTION & GRADE DISTRIBUTION
    # =========================================================================
    col3, col4 = st.columns(2)
    # ─────────────────────────────────────────────────────────────────────────
    # Gender Distribution (Pie Chart)
    # ─────────────────────────────────────────────────────────────────────────
    with col3:
        st.subheader("👥 Gender Distribution")
        
        if "Gender" in df.columns:
            # Count by gender
            gender_counts = df["Gender"].value_counts().reset_index()
            gender_counts.columns = ["Gender", "Count"]
            
            # Map M/F to readable labels
            gender_map = {"M": "Male", "F": "Female"}
            gender_counts["Gender"] = gender_counts["Gender"].map(gender_map)
            
            # Create pie chart
            fig = px.pie(
                gender_counts,
                names="Gender",
                values="Count",
                hole=0.35,
                color_discrete_map={"Male": "#20419a", "Female": "#763f98"},  # Blue for Male, Orange for Female
                labels={"Count": "Number"}
            )
            fig.update_traces(
                textposition="inside",
                textinfo="label+percent"
            )
            fig.update_layout(height=400, showlegend=True)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Gender data not available")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Grade (SG) Distribution by Gender (Stacked Bar)
    # ─────────────────────────────────────────────────────────────────────────
    with col4:
        st.subheader("📈 Grade (SG) Distribution by Gender")
        
        if "SG" in df.columns and "Gender" in df.columns:
            # Create pivot table: grades × gender
            sg_gender = pd.crosstab(df["SG"], df["Gender"])
            
            # Rename columns to readable labels if they exist
            rename_dict = {}
            if "M" in sg_gender.columns:
                rename_dict["M"] = "Male"
            if "F" in sg_gender.columns:
                rename_dict["F"] = "Female"
            sg_gender = sg_gender.rename(columns=rename_dict)
            
            # Sort by numeric grade including UPTREX then P1..P10
            order = ["UPTREX"] + [f"P{i}" for i in range(1, 11)]
            present = [g for g in order if g in sg_gender.index]
            sg_gender = sg_gender.reindex(present)

            # Compute average age per grade for overlay
            age_by_grade = df.groupby("SG").agg(avg_age=("Age", "mean")).reset_index()
            age_by_grade = age_by_grade[age_by_grade["SG"].isin(present)]
            age_by_grade = age_by_grade.set_index("SG").reindex(present).reset_index()

            # Identify which gender columns actually exist to prevent errors in px.bar
            available_gender_cols = [col for col in ["Male", "Female"] if col in sg_gender.columns]

            # Create stacked bar chart
            fig = px.bar(
                sg_gender.reset_index(), 
                x="SG", 
                y=available_gender_cols,
                barmode="stack", 
                title="", 
                labels={"SG": "Salary Grade", "value": "Number of Personnel", "variable": "Gender"},
                color_discrete_map={"Male": "#20419a", "Female": "#763f98"}
            )

            # Add average age as a line on secondary y-axis
            fig.add_trace(
                go.Scatter(
                    x=age_by_grade["SG"],
                    y=age_by_grade["avg_age"],
                    name="Average Age",
                    mode="lines+markers",
                    marker=dict(color="#bfd730", size=8),
                    yaxis="y2",
                )
            )

            fig.update_layout(
                xaxis_title="Salary Grade",
                yaxis_title="Number of Personnel",
                height=400,
                hovermode="x unified",
                legend=dict(title="Gender", yanchor="top", y=0.99, xanchor="right", x=0.99),
                yaxis2=dict(
                    title="Average Age",
                    overlaying="y",
                    side="right",
                    showgrid=False, # Keeps secondary gridlines from cluttering the chart
                ),
            )

            # Show stacked counts inside bars
            fig.update_traces(textposition="auto", texttemplate="%{y}", selector=dict(type="bar"))
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Grade or Gender data not available")
        
    # =========================================================================
    # ROW 3: ADDITIONAL INSIGHTS (Optional)
    # =========================================================================

    st.subheader("📈 Age vs Salary Grade Analysis")



    # 1. Custom Hover Card Generator (No Overall_avg)
    def create_hover_text(row):
        html = f"<b>{row.get('Name', 'Unknown')}</b><br>"
        html += f"<i>{row.get('Staff Position', 'N/A')}</i><br>"
        html += (
            f"<span style='color: gray;'>{row.get('Department', 'N/A')}</span><br>"
        )

        # Age formatting (whole number)
        age = row.get("Age", "N/A")
        try:
            age_display = f"{float(age):.0f}" if pd.notna(age) else "N/A"
        except (ValueError, TypeError):
            age_display = age

        html += f"<b>Age:</b> {age_display} | <b>Salary Grade:</b> {row.get('SG', 'N/A')}<br>"

        # Experience formatting (2 decimal places)
        if pd.notna(row.get("Years in RE Experience")):
            html += f"<b>RE Experience:</b> {float(row['Years in RE Experience']):.2f} Years<br>"
        if pd.notna(row.get("Years in PET")):
            html += f"<b>PET Experience:</b> {float(row['Years in PET']):.2f} Years<br>"

        return html

    # --- STREAMLIT UI ---

    #draggble ui 

    min_pet = float(df["Years in PET"].fillna(0).min())
    max_pet = float(df["Years in PET"].fillna(0).max())
    min_re = float(df["Years of RE Experience"].fillna(0).min())
    max_re = float(df["Years of RE Experience"].fillna(0).max())

    # Filter Section
    c1, c2, c3 = st.columns(3)
    with c1:
        f_name = st.multiselect(
            "Filter by Personnel",
            sorted(df["Name"].dropna().unique()),
            key="dash_name",
        )
    with c2:
        f_unit = st.multiselect(
            "Filter by Unit Name",
            sorted(df["Unit Name"].dropna().unique()),
            key="dash_unit1",
        )
    with c3:
        f_pos = st.multiselect(
            "Filter by Position",
            sorted(df["Staff Position"].dropna().unique()),
            key="dash_pos1",
        )

    c4, c5 = st.columns(2)

    with c4 : 
            f_pet_range = st.slider("Filter by Years in PETRONAS: ", 
                                    min_value=min_pet,max_value=max_pet, 
                                    value =(min_pet, max_pet), 
                                    step=1.0, 
                                    key="dash_pet_range")
    with c5: 
            f_re_range = st.slider("Filter by Years in RE Experience", 
                                   min_value=min_re, 
                                   max_value=max_re, 
                                   value=(min_re, max_re), 
                                   step = 1.0, 
                                   key="dash_re_range")

    tab2d, tab3d = st.tabs(
        ["📊 Career Distribution (2D)", "🌐 Career Progression (3D)"]
    )

    # Apply Filters
    fdf1 = df.copy()
    if f_name:
        fdf1 = fdf1[fdf1["Name"].isin(f_name)]
    if f_unit:
        fdf1 = fdf1[fdf1["Unit Name"].isin(f_unit)]
    if f_pos:
        fdf1 = fdf1[fdf1["Staff Position"].isin(f_pos)]

    fdf1 = fdf1[
        (fdf1["Years in PET"].fillna(0) >= f_pet_range[0]) & 
        (fdf1["Years in PET"].fillna(0) <= f_pet_range[1])]

    fdf1 = fdf1[
        (fdf1["Years of RE Experience"].fillna(0) >= f_re_range[0]) & 
        (fdf1["Years of RE Experience"].fillna(0) <= f_re_range[1])]

    sg_order = [ "UPTREX", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10"]
    scatter_df2 = an.scatter_age_vs_grade(fdf1)

    # Create Colorful Legend for 'Years in RE Experience'
    color_col = None
    
    if "Years in RE Experience" in scatter_df2.columns:
            # Ensure numeric type
            scatter_df2["Years in RE Experience"] = pd.to_numeric(scatter_df2["Years in RE Experience"], errors='coerce')
            
            # 1. Define Bin Ranges & Labels
            bins = [-1, 2, 5, 10, 15, 100]
            labels = ["< 2 Yrs", "2 - 5 Yrs", "5 - 10 Yrs", "10 - 15 Yrs", "15+ Yrs"]
            
            # 2. Categorize data into distinct groups
            scatter_df2["RE Experience Tier"] = pd.cut(
                scatter_df2["Years in RE Experience"], 
                bins=bins, 
                labels=labels
            ).astype(str)
            
            # Clean up any NaNs/Missing data
            scatter_df2["RE Experience Tier"] = scatter_df2["RE Experience Tier"].replace({"nan": "Unknown / Unspecified"})
            
            color_col = "RE Experience Tier"
    
        # Define explicit color mapping so each tier ALWAYS gets a distinct solid color
    # Determine size column
    size_col = None
    if "Years in RE Experience" in scatter_df2.columns:
        size_col = "Years in RE Experience"
    elif "Years in PET" in scatter_df2.columns:
        size_col = "Years in PET"

    # Attach HTML Hover String
    scatter_df2["Beautiful_Hover"] = scatter_df2.apply(create_hover_text, axis=1)


    # --- 2D TAB ---
    with tab2d:
        st.info(
            """
            **Purpose**
            This chart compares **Age** against **Salary Grade (SG)**. 
            Each color in the legend represents **Years in RE Experience**.
            """
        )

        fig = px.scatter(
            scatter_df2,
            x="Age",
            y="SG",
            color=color_col,
            size=size_col,
            custom_data=["Beautiful_Hover"],  # Custom HTML injection
            category_orders={
            "SG": sg_order,
            "RE Experience Tier": ["< 2 Yrs", "2 - 5 Yrs", "5 - 10 Yrs", "10 - 15 Yrs", "15+ Yrs", "Unknown / Unspecified"]},
            color_discrete_sequence=px.colors.qualitative.Bold,  # High-contrast colorful legend palette
            title="Age vs Salary Grade",
        )

        fig.update_traces(
            hovertemplate="%{customdata[0]}<extra></extra>",  # Replaces messy hover with formatted HTML card
            marker=dict(opacity=0.85, line=dict(width=1, color="white")),
        )
        fig.update_layout(
            height=700,
            xaxis_title="Age",
            yaxis_title="Salary Grade",
            plot_bgcolor="#FFFFFF",
            legend_title_text="RE Experience",
        )
        st.plotly_chart(fig, use_container_width=True, key="scatter_2d_age_sg")


    # --- 3D TAB ---
    with tab3d:
        fig_3d = px.scatter_3d(
            scatter_df2,
            x="Age",
            y="SG",
            z="Years in PET",
            color=color_col,
            size=size_col,
            custom_data=["Beautiful_Hover"],  # Custom HTML injection
            category_orders={
                        "SG": sg_order,
                        "RE Experience Tier": ["< 2 Yrs", "2 - 5 Yrs", "5 - 10 Yrs", "10 - 15 Yrs", "15+ Yrs", "Unknown / Unspecified"]},
            color_discrete_sequence=px.colors.qualitative.Bold,
            title="Career Progression Landscape",
        )

        fig_3d.update_traces(
            hovertemplate="%{customdata[0]}<extra></extra>",
            marker=dict(opacity=0.85, line=dict(width=1, color="white")),
        )
        fig_3d.update_layout(
            height=800,
            legend_title_text="RE Experience",
            scene=dict(
                xaxis=dict(title="Age"),
                yaxis=dict(
                    title="Salary Grade",
                    tickmode="array",
                    tickvals=list(range(len(sg_order))),
                    ticktext=sg_order,
                ),
                zaxis=dict(title="Years in PET"),
            ),
        )

        st.plotly_chart(
            fig_3d, use_container_width=True, key="scatter_3d_career_landscape"
        )
    st.markdown("---")
# ═════════════════════════════════════════════════════════════════════════════
# PAGE: PERSONNEL DIRECTORY
# ═════════════════════════════════════════════════════════════════════════════
elif page == "👥 Personnel Directory":
    st.title("👥 Personnel Directory")

    if df.empty:
        st.stop()

    c1, c2, c3 = st.columns(3)
    with c1:
        f_dept = st.multiselect("Department", sorted(df["Department"].dropna().unique()))
    with c2:
        f_pos = st.multiselect("Position", sorted(df["Staff Position"].dropna().unique()))
    with c3:
        f_chat = st.multiselect("Chat Status", CHAT_STATUS_OPTIONS)

    search = st.text_input("🔎 Search by Name or Staff ID")

    fdf = df.copy()
    if f_dept:
        fdf = fdf[fdf["Department"].isin(f_dept)]
    if f_pos:
        fdf = fdf[fdf["Staff Position"].isin(f_pos)]
    if f_chat:
        fdf = fdf[fdf["Chat Status"].isin(f_chat)]
    if search:
        mask = fdf["Name"].str.contains(search, case=False, na=False) | \
               fdf["Staff ID"].astype(str).str.contains(search, case=False, na=False)
        fdf = fdf[mask]

    st.caption(f"Showing {len(fdf)} of {len(df)} personnel")
    display_cols = ["Name", "Staff ID", "Staff Position", "SG", "Department",
                    "Age", "Chat Status", "Years in RE Experience"]

    display_cols = [c for c in display_cols if c in fdf.columns]
    show = fdf[display_cols].rename(columns={"Years in RE Experience": "Avg Score"})
    show = fdf[display_cols].rename(columns={"Years in RE Experience": "Avg Score"})
    show = fdf[display_cols].rename(columns={"Years in RE Experience": "Avg Score"})
    if "Avg Score" in show.columns:
        show["Avg Score"] = show["Avg Score"].round(2)
    st.dataframe(show, use_container_width=True, hide_index=True)

    # CSV export
    csv = show.to_csv(index=False).encode()
    st.download_button("⬇️ Download as CSV", csv, "personnel_directory.csv", "text/csv")

# =============================================================================
# PAGE: COMPETENCY HEATMAP
# =============================================================================

elif page == "🌡️ Competency Heatmap":
    st.title("🌡️ Competency Heatmap")
    st.markdown("---")
    st.caption(
        "Explore actual competency scores across personnel. "
        "Each row represents one person and each column represents "
        "one competency."
    )

    if df.empty:
        st.warning("No personnel data is available.")
        st.stop()

    # -------------------------------------------------------------------------
    # FILTERS
    # -------------------------------------------------------------------------

    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)

    with filter_col1:
        f_dept = st.multiselect(
            "Department",
            options=sorted(
                df["Department"]
                .dropna()
                .astype(str)
                .unique()
            ),
            key="hm_dept",
        )

    with filter_col2:
        f_pos = st.multiselect(
            "Position",
            options=sorted(
                df["Staff Position"]
                .dropna()
                .astype(str)
                .unique()
            ),
            key="hm_pos",
        )

    with filter_col3:
        f_sg = st.multiselect(
            "Salary Grade",
            options=sorted(
                df["SG"]
                .dropna()
                .astype(str)
                .unique(),
                key=lambda grade: grade_rank(grade) or 999,
            ),
            key="hm_sg",
        )

    with filter_col4:
        f_type = st.multiselect(
            "Competency Type",
            options=list(COMP_TYPES.keys()),
            default=list(COMP_TYPES.keys()),
            format_func=lambda code: (
                COMP_TYPES.get(code, {}).get(
                    "label",
                    code,
                )
            ),
            key="hm_type",
        )

    control_col1, control_col2, control_col3 = st.columns(3)

    with control_col1:
        sort_option = st.selectbox(
            "Sort personnel by",
            options=[
                "Name",
                "Average score: high to low",
                "Average score: low to high",
                "Low-score cells: high to low",
                "Assessment coverage: low to high",
            ],
            key="hm_sort",
        )

    with control_col2:
        show_score_labels = st.checkbox(
            "Show score inside cells",
            value=True,
            help=(
                "Score labels are automatically hidden when too many "
                "personnel are displayed."
            ),
            key="hm_show_labels",
        )

    with control_col3:
        minimum_coverage = st.slider(
            "Minimum assessment coverage",
            min_value=0,
            max_value=100,
            value=0,
            step=5,
            format="%d%%",
            key="hm_min_coverage",
        )

    # -------------------------------------------------------------------------
    # APPLY FILTERS
    # -------------------------------------------------------------------------

    fdf = df.copy()

    if f_dept:
        fdf = fdf[
            fdf["Department"].isin(f_dept)
        ]

    if f_pos:
        fdf = fdf[
            fdf["Staff Position"].isin(f_pos)
        ]

    if f_sg:
        fdf = fdf[
            fdf["SG"].isin(f_sg)
        ]

    # -------------------------------------------------------------------------
    # SELECT COMPETENCY COLUMNS
    # -------------------------------------------------------------------------

    value_cols = []

    for competency_type in f_type:
        configured_columns = COMP_TYPES.get(
            competency_type,
            {},
        ).get(
            "cols",
            [],
        )

        value_cols.extend(
            column
            for column in configured_columns
            if column in fdf.columns
        )

    # Remove accidental duplicates while preserving order.
    value_cols = list(
        dict.fromkeys(value_cols)
    )

    if not value_cols:
        st.info(
            "Select at least one competency type."
        )
        st.stop()

    if fdf.empty:
        st.warning(
            "No personnel match the selected filters."
        )
        st.stop()

    # -------------------------------------------------------------------------
    # BUILD HEATMAP MATRIX
    # -------------------------------------------------------------------------

    heatmap_data = fdf.copy()

    # Convert competency scores to numeric values.
    for competency in value_cols:
        heatmap_data[competency] = pd.to_numeric(
            heatmap_data[competency],
            errors="coerce",
        )

    # Create a readable and unique personnel label.
    def build_personnel_label(row):
        name = row.get("Name")
        staff_id = row.get("Staff ID")
        sg = row.get("SG")

        name_display = (
            str(name).strip()
            if name is not None and pd.notna(name)
            else "Unknown"
        )

        label_parts = [name_display]

        if (
            staff_id is not None
            and pd.notna(staff_id)
            and str(staff_id).strip()
        ):
            label_parts.append(
                str(staff_id).strip()
            )

        if (
            sg is not None
            and pd.notna(sg)
            and str(sg).strip()
        ):
            label_parts.append(
                str(sg).strip()
            )

        return " | ".join(label_parts)

    heatmap_data["Heatmap Label"] = (
        heatmap_data.apply(
            build_personnel_label,
            axis=1,
        )
    )

    # Remove personnel with no scores in the selected competencies.
    heatmap_data = heatmap_data[
        heatmap_data[value_cols]
        .notna()
        .any(axis=1)
    ].copy()

    if heatmap_data.empty:
        st.warning(
            "No assessed personnel match the selected filters."
        )
        st.stop()

    # -------------------------------------------------------------------------
    # PERSONNEL-LEVEL STATISTICS
    # -------------------------------------------------------------------------

    heatmap_data["Average Score"] = (
        heatmap_data[value_cols]
        .mean(axis=1)
    )

    heatmap_data["Assessed Competencies"] = (
        heatmap_data[value_cols]
        .notna()
        .sum(axis=1)
    )

    heatmap_data["Missing Competencies"] = (
        len(value_cols)
        - heatmap_data["Assessed Competencies"]
    )

    heatmap_data["Assessment Coverage %"] = (
        heatmap_data["Assessed Competencies"]
        / len(value_cols)
        * 100
    )

    heatmap_data["High Score Cells"] = (
        heatmap_data[value_cols]
        .ge(4)
        .sum(axis=1)
    )

    heatmap_data["Low Score Cells"] = (
        heatmap_data[value_cols]
        .le(2)
        .sum(axis=1)
    )

    # Apply assessment coverage filter.
    heatmap_data = heatmap_data[
        heatmap_data["Assessment Coverage %"]
        >= minimum_coverage
    ].copy()

    if heatmap_data.empty:
        st.warning(
            "No personnel meet the selected minimum "
            "assessment coverage."
        )
        st.stop()

    # -------------------------------------------------------------------------
    # SORT PERSONNEL
    # -------------------------------------------------------------------------

    if sort_option == "Name":
        heatmap_data = heatmap_data.sort_values(
            by="Name",
            ascending=True,
            na_position="last",
        )

    elif sort_option == "Average score: high to low":
        heatmap_data = heatmap_data.sort_values(
            by="Average Score",
            ascending=False,
            na_position="last",
        )

    elif sort_option == "Average score: low to high":
        heatmap_data = heatmap_data.sort_values(
            by="Average Score",
            ascending=True,
            na_position="last",
        )

    elif sort_option == "Low-score cells: high to low":
        heatmap_data = heatmap_data.sort_values(
            by=[
                "Low Score Cells",
                "Average Score",
            ],
            ascending=[
                False,
                True,
            ],
            na_position="last",
        )

    elif sort_option == "Assessment coverage: low to high":
        heatmap_data = heatmap_data.sort_values(
            by=[
                "Assessment Coverage %",
                "Name",
            ],
            ascending=[
                True,
                True,
            ],
            na_position="last",
        )

    mat = heatmap_data.set_index(
        "Heatmap Label"
    )[value_cols]

    # -------------------------------------------------------------------------
    # OVERALL METRICS
    # -------------------------------------------------------------------------

    score_values = mat.to_numpy(
        dtype=float
    )

    valid_scores = score_values[
        ~np.isnan(score_values)
    ]

    possible_cells = (
        len(mat) * len(value_cols)
    )

    assessed_cells = len(valid_scores)

    missing_cells = (
        possible_cells - assessed_cells
    )

    coverage_pct = (
        assessed_cells / possible_cells * 100
        if possible_cells > 0
        else 0.0
    )

    average_score = (
        float(np.mean(valid_scores))
        if assessed_cells > 0
        else np.nan
    )

    high_score_cells = (
        int((valid_scores >= 4).sum())
        if assessed_cells > 0
        else 0
    )

    low_score_cells = (
        int((valid_scores <= 2).sum())
        if assessed_cells > 0
        else 0
    )

    st.markdown("---")

    metric1, metric2, metric3, metric4, metric5 = st.columns(5)

    metric1.metric(
        "Personnel Shown",
        len(mat),
    )

    metric2.metric(
        "Average Score",
        (
            f"{average_score:.2f}"
            if not np.isnan(average_score)
            else "N/A"
        ),
    )

    metric3.metric(
        "High Score Cells",
        high_score_cells,
        help=(
            "Number of individual competency scores "
            "that are 4 or higher."
        ),
    )

    metric4.metric(
        "Low Score Cells",
        low_score_cells,
        help=(
            "Number of individual competency scores "
            "that are 2 or lower. This does not "
            "automatically mean there is a target gap."
        ),
    )

    metric5.metric(
        "Assessment Coverage",
        f"{coverage_pct:.1f}%",
        help=(
            "Populated competency-score cells divided "
            "by all possible cells in the displayed matrix."
        ),
    )

    st.caption(
        f"Showing {len(mat)} personnel × "
        f"{len(value_cols)} competencies. "
        f"{assessed_cells:,} assessed cells and "
        f"{missing_cells:,} missing cells."
    )

    # -------------------------------------------------------------------------
    # HEATMAP DISPLAY
    # -------------------------------------------------------------------------

    st.subheader("Actual Competency Score Matrix")

    st.caption(
        "Rows represent personnel and columns represent competencies. "
        "Borders separate each person and competency for easier reading. "
        "Blank cells indicate that no score is available."
    )

    # Competency full names for hover information.
    competency_name_map = (
        st.session_state.get(
            "competency_names",
            {},
        )
        or COMPETENCY_FULLNAMES
    )

    competency_full_names = [
        competency_name_map.get(
            competency,
            competency,
        )
        for competency in value_cols
    ]

    # Repeat competency names for every heatmap row.
    hover_competency_names = np.tile(
        np.array(
            competency_full_names,
            dtype=object,
        ),
        (
            len(mat),
            1,
        ),
    )

    # Show numeric values only when the matrix remains readable.
    display_cell_labels = (
        show_score_labels
        and len(mat) <= 40
        and len(value_cols) <= 24
    )

    if display_cell_labels:
        text_values = np.where(
            np.isnan(score_values),
            "",
            np.round(score_values).astype(
                object
            ),
        )

        # Convert numeric objects to readable strings.
        text_values = np.vectorize(
            lambda value: (
                ""
                if value == ""
                else str(int(value))
            )
        )(text_values)

        text_template = "%{text}"
    else:
        text_values = None
        text_template = None

        if show_score_labels:
            st.info(
                "Score labels were hidden automatically because "
                "the displayed matrix is too large. Hover over a "
                "cell to see its score."
            )

    # Allocate enough vertical space for readable personnel rows,
    # while avoiding an excessively tall page.
    chart_height = min(
        max(
            500,
            32 * len(mat) + 170,
        ),
        1800,
    )

    fig = go.Figure(
        data=go.Heatmap(
            z=score_values,
            x=value_cols,
            y=mat.index.tolist(),
            text=text_values,
            texttemplate=text_template,
            textfont={
                "size": 11,
                "color": "white",
            },
            customdata=hover_competency_names,
            colorscale=HEATMAP_COLORSCALE,
            zmin=0,
            zmax=5,

            # These gaps create visible borders around cells.
            xgap=1.5,
            ygap=1.5,

            colorbar={
                "title": {
                    "text": "Score",
                },
                "tickmode": "array",
                "tickvals": [0, 1, 2, 3, 4, 5],
                "ticktext": ["0", "1", "2", "3", "4", "5"],
                "len": 0.85,
            },
            hoverongaps=False,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Competency: %{x}<br>"
                "Competency Name: %{customdata}<br>"
                "Actual Score: %{z:.0f}"
                "<extra></extra>"
            ),
        )
    )

    fig.update_layout(
        height=chart_height,
        plot_bgcolor="#30343F",
        paper_bgcolor="rgba(0,0,0,0)",
        margin={
            "l": 20,
            "r": 40,
            "t": 20,
            "b": 80,
        },
        xaxis={
            "title": "Competency",
            "side": "top",
            "tickangle": 0,
            "tickmode": "array",
            "tickvals": value_cols,
            "ticktext": value_cols,
            "showgrid": False,
            "fixedrange": False,
        },
        yaxis={
            "title": "",
            "autorange": "reversed",
            "showgrid": False,
            "tickfont": {
                "size": 11,
            },
            "automargin": True,
            "fixedrange": False,
        },
        hoverlabel={
            "bgcolor": "#FFFFFF",
            "font": {
                "color": "#1F2937",
                "size": 12,
            },
        },
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        config={
            "displayModeBar": True,
            "displaylogo": False,
            "scrollZoom": True,
            "modeBarButtonsToRemove": [
                "lasso2d",
                "select2d",
            ],
            "toImageButtonOptions": {
                "format": "png",
                "filename": "competency_heatmap",
                "height": chart_height,
                "width": 1800,
                "scale": 2,
            },
        },
    )

    # -------------------------------------------------------------------------
    # SUMMARY TABLES
    # -------------------------------------------------------------------------

    st.markdown("---")
    st.subheader("📋 Heatmap Analysis Summary")

    st.caption(
        "Use the personnel summary to identify broad score patterns. "
        "Use the competency summary to identify common strengths, "
        "low-score concentrations, and assessment-data gaps."
    )

    personnel_tab, competency_tab, category_tab = st.tabs(
        [
            "Personnel Summary",
            "Competency Summary",
            "Category Summary",
        ]
    )

    # -------------------------------------------------------------------------
    # PERSONNEL SUMMARY TABLE
    # -------------------------------------------------------------------------

    with personnel_tab:
        personnel_summary = heatmap_data[
            [
                "Name",
                "Staff ID",
                "Department",
                "Staff Position",
                "SG",
                "Assessed Competencies",
                "Missing Competencies",
                "Assessment Coverage %",
                "High Score Cells",
                "Low Score Cells",
            ]
        ].copy()
        
        personnel_summary["Assessment Coverage %"] = (
            personnel_summary[
                "Assessment Coverage %"
            ]
            .round(1)
        )

        personnel_summary = personnel_summary.rename(
            columns={
                "High Score Cells": "Scores ≥4",
                "Low Score Cells": "Scores ≤2",
            }
        )

        st.dataframe(
            personnel_summary,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Average Score": st.column_config.NumberColumn(
                    "Average Score",
                    format="%.2f",
                ),
                "Assessment Coverage %":
                    st.column_config.ProgressColumn(
                        "Assessment Coverage",
                        min_value=0,
                        max_value=100,
                        format="%.1f%%",
                    ),
                "Assessed Competencies":
                    st.column_config.NumberColumn(
                        "Assessed",
                        format="%d",
                    ),
                "Missing Competencies":
                    st.column_config.NumberColumn(
                        "Missing",
                        format="%d",
                    ),
            },
        )

        st.download_button(
            "⬇️ Download Personnel Summary",
            data=personnel_summary.to_csv(
                index=False
            ).encode("utf-8"),
            file_name=(
                "heatmap_personnel_summary.csv"
            ),
            mime="text/csv",
        )

    # -------------------------------------------------------------------------
    # COMPETENCY SUMMARY TABLE
    # -------------------------------------------------------------------------

    with competency_tab:
        competency_records = []

        for competency in value_cols:
            competency_scores = pd.to_numeric(
                mat[competency],
                errors="coerce",
            )

            valid_competency_scores = (
                competency_scores.dropna()
            )

            assessed_count = len(
                valid_competency_scores
            )

            missing_count = (
                len(mat) - assessed_count
            )

            competency_coverage = (
                assessed_count / len(mat) * 100
                if len(mat) > 0
                else 0.0
            )

            competency_records.append(
                {
                    "Competency": competency,
                    "Competency Name":
                        competency_name_map.get(
                            competency,
                            competency,
                        ),
                    "Category":
                        COMP_TYPES.get(
                            competency[0],
                            {},
                        ).get(
                            "label",
                            competency[0],
                        ),
                    "Average Score": (
                        valid_competency_scores.mean()
                        if assessed_count > 0
                        else np.nan
                    ),
                    "Minimum Score": (
                        valid_competency_scores.min()
                        if assessed_count > 0
                        else np.nan
                    ),
                    "Maximum Score": (
                        valid_competency_scores.max()
                        if assessed_count > 0
                        else np.nan
                    ),
                    "Assessed Personnel":
                        assessed_count,
                    "Missing Personnel":
                        missing_count,
                    "Coverage %":
                        competency_coverage,
                    "Scores ≥4": int(
                        (
                            valid_competency_scores
                            >= 4
                        ).sum()
                    ),
                    "Scores ≤2": int(
                        (
                            valid_competency_scores
                            <= 2
                        ).sum()
                    ),
                }
            )

        competency_summary = pd.DataFrame(
            competency_records
        )

        competency_summary["Average Score"] = (
            competency_summary["Average Score"]
            .round(2)
        )

        competency_summary["Minimum Score"] = (
            competency_summary["Minimum Score"]
            .round(0)
            .astype("Int64")
        )

        competency_summary["Maximum Score"] = (
            competency_summary["Maximum Score"]
            .round(0)
            .astype("Int64")
        )

        competency_summary["Coverage %"] = (
            competency_summary["Coverage %"]
            .round(1)
        )

        competency_summary = (
            competency_summary.sort_values(
                by=[
                    "Average Score",
                    "Scores ≤2",
                ],
                ascending=[
                    True,
                    False,
                ],
                na_position="last",
            )
        )

        st.dataframe(
            competency_summary,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Coverage %":
                    st.column_config.ProgressColumn(
                        "Assessment Coverage",
                        min_value=0,
                        max_value=100,
                        format="%.1f%%",
                    ),
            },
        )

        st.download_button(
            "⬇️ Download Competency Summary",
            data=competency_summary.to_csv(
                index=False
            ).encode("utf-8"),
            file_name=(
                "heatmap_competency_summary.csv"
            ),
            mime="text/csv",
        )

    # -------------------------------------------------------------------------
    # CATEGORY SUMMARY TABLE
    # -------------------------------------------------------------------------

    with category_tab:
        category_records = []

        for category_code in f_type:
            category_columns = [
                competency
                for competency in COMP_TYPES.get(
                    category_code,
                    {},
                ).get(
                    "cols",
                    [],
                )
                if competency in mat.columns
            ]

            if not category_columns:
                continue

            category_values = (
                mat[category_columns]
                .to_numpy(dtype=float)
            )

            valid_category_values = (
                category_values[
                    ~np.isnan(category_values)
                ]
            )

            possible_category_cells = (
                len(mat)
                * len(category_columns)
            )

            assessed_category_cells = len(
                valid_category_values
            )

            category_coverage = (
                assessed_category_cells
                / possible_category_cells
                * 100
                if possible_category_cells > 0
                else 0.0
            )

            category_records.append(
                {
                    "Category Code": category_code,
                    "Category":
                        COMP_TYPES.get(
                            category_code,
                            {},
                        ).get(
                            "label",
                            category_code,
                        ),
                    "Competencies":
                        len(category_columns),
                    "Scores ≥4": int(
                        (
                            valid_category_values
                            >= 4
                        ).sum()
                    ),
                    "Scores ≤2": int(
                        (
                            valid_category_values
                            <= 2
                        ).sum()
                    ),
                    "Assessed Cells":
                        assessed_category_cells,
                    "Missing Cells": (
                        possible_category_cells
                        - assessed_category_cells
                    ),
                    "Coverage %":
                        category_coverage,
                }
            )

        category_summary = pd.DataFrame(
            category_records
        )

        if category_summary.empty:
            st.info(
                "No competency categories are available "
                "for the selected filters."
            )
        else:
            category_summary["Coverage %"] = (
                category_summary["Coverage %"]
                .round(1)
            )

            st.dataframe(
                category_summary,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Coverage %":
                        st.column_config.ProgressColumn(
                            "Assessment Coverage",
                            min_value=0,
                            max_value=100,
                            format="%.1f%%",
                        ),
                },
            )

elif page == "👤 Individual Assessment & Talent Profile":

    # =========================================================================
    # PAGE HEADER
    # =========================================================================

    st.title(
        "👤 Individual Assessment & Talent Profile"
    )

    st.caption(
        "Review personnel information, CV documents, "
        "career progression targets, competency readiness, "
        "and development gaps."
    )

    st.markdown("---")

    # =========================================================================
    # DATA VALIDATION
    # =========================================================================

    if df is None or df.empty:
        st.error(
            "No personnel data is available."
        )

        st.stop()

    if "Name" not in df.columns:
        st.error(
            "The personnel dataset does not contain "
            "the required Name column."
        )

        st.stop()

    personnel_names = sorted(
        df["Name"]
        .dropna()
        .astype(str)
        .str.strip()
        .loc[
            lambda series: series.ne("")
        ]
        .unique()
        .tolist()
    )

    if not personnel_names:
        st.error(
            "No valid personnel names are available."
        )

        st.stop()

    # =========================================================================
    # PERSONNEL SELECTION
    # =========================================================================

    selection_column, refresh_column = (
        st.columns(
            [5, 1],
            vertical_alignment="bottom",
        )
    )

    with selection_column:
        selected_name = st.selectbox(
            "Select Personnel",
            options=personnel_names,
            key="personnel_select",
        )

    with refresh_column:
        if st.button(
            "🔄 Refresh",
            type="secondary",
            width="stretch",
        ):
            st.cache_data.clear()
            st.rerun()

    selected_personnel_rows = df[
        df["Name"].astype(str).str.strip()
        == str(selected_name).strip()
    ]

    if selected_personnel_rows.empty:
        st.error(
            "The selected personnel record "
            "could not be found."
        )

        st.stop()

    if len(selected_personnel_rows) > 1:
        st.warning(
            "More than one record has the selected name. "
            "The first record is being displayed. "
            "Use Staff ID as the selector in a future update "
            "to eliminate name ambiguity."
        )

    person_row = (
        selected_personnel_rows.iloc[0]
    )

    # =========================================================================
    # DATABASE DETAILS
    # =========================================================================

    (
        personnel_id,
        cv_documents,
        summary_score,
        profile_retrieval_error,
    ) = _load_personnel_database_details(
        person_row=person_row,
        engine=engine,
    )

    # =========================================================================
    # PROFILE AND CV TABS
    # =========================================================================

    overview_tab, documents_tab = st.tabs(
        [
            "👤 Personnel Overview",
            "📄 CV & Documents",
        ]
    )

    # -------------------------------------------------------------------------
    # PERSONNEL OVERVIEW
    # -------------------------------------------------------------------------

    with overview_tab:
        st.subheader(
            "📋 Personnel Profile"
        )

        (
            profile_position_col,
            profile_department_col,
            profile_assignment_col,
            profile_service_col,
        ) = st.columns(4)

        with profile_position_col:
            staff_position = (
                _safe_display_value(
                    person_row.get(
                        "Staff Position"
                    ),
                    "Position unavailable",
                )
            )

            salary_grade = (
                _safe_display_value(
                    person_row.get("SG"),
                    "SG unavailable",
                )
            )

            st.metric(
                "Position / Grade",
                (
                    f"{staff_position} "
                    f"({salary_grade})"
                ),
            )

        with profile_department_col:
            department = (
                _safe_display_value(
                    person_row.get(
                        "Department"
                    ),
                    "Department unavailable",
                )
            )

            section_name = (
                _safe_display_value(
                    person_row.get(
                        "Section Name"
                    ),
                    "Section unavailable",
                )
            )

            st.metric(
                "Department / Section",
                (
                    f"{department} "
                    f"({section_name})"
                ),
            )

        with profile_assignment_col:
            st.metric(
                "Current Assignment",
                _safe_display_value(
                    person_row.get(
                        "Current Location:"
                    ),
                    "Not available",
                ),
            )

        with profile_service_col:
            st.metric(
                "Years in PETRONAS",
                _safe_integer_display(
                    person_row.get(
                        "Years in PET"
                    )
                ),
            )

        (
            profile_age_col,
            profile_employment_col,
            profile_expiry_col,
            profile_grade_length_col,
        ) = st.columns(4)

        with profile_age_col:
            st.metric(
                "Age",
                _safe_integer_display(
                    person_row.get("Age"),
                    "N/A",
                ),
            )

        with profile_employment_col:
            st.metric(
                "Employment Type",
                _safe_display_value(
                    person_row.get(
                        "Employment Category"
                    )
                ),
            )

        with profile_expiry_col:
            st.metric(
                "Contract Expiry Date",
                _safe_date_display(
                    person_row.get(
                        "Contract Expire Date"
                    )
                ),
            )

        with profile_grade_length_col:
            st.metric(
                "Length in Grade",
                _safe_integer_display(
                    person_row.get(
                        "Years in Salary Grade"
                    )
                ),
            )

        st.markdown(
            "### 💪 Talent Profile"
        )

        (
            talent_strength_col,
            talent_interest_col,
            talent_background_col,
        ) = st.columns(3)

        with talent_strength_col:
            st.markdown(
                "#### 💪 Strength"
            )

            st.markdown(
                _safe_display_value(
                    person_row.get(
                        "Strength"
                    ),
                    "No strength information available.",
                )
            )

        with talent_interest_col:
            st.markdown(
                "#### ❤️ Interest"
            )

            st.markdown(
                _safe_display_value(
                    person_row.get(
                        "Interest"
                    ),
                    "No interest information available.",
                )
            )

        with talent_background_col:
            st.markdown(
                "#### 🎓 Background"
            )

            st.markdown(
                _safe_display_value(
                    person_row.get(
                        "Background"
                    )
                    or person_row.get(
                        "Sub-Disciplines"
                    ),
                    "No background information available.",
                )
            )

    # -------------------------------------------------------------------------
    # CV DOCUMENTS
    # -------------------------------------------------------------------------

    with documents_tab:
        st.subheader(
            "📄 Curriculum Vitae & Supporting Documents"
        )

        if profile_retrieval_error:
            st.error(
                "Unable to retrieve document records: "
                f"{profile_retrieval_error}"
            )

        elif personnel_id is None:
            st.warning(
                "The selected personnel could not be matched "
                "to a database record."
            )

            with st.expander(
                "Personnel matching diagnostics"
            ):
                st.write(
                    {
                        "Name":
                            person_row.get(
                                "Name"
                            ),
                        "Staff ID":
                            person_row.get(
                                "Staff ID"
                            ),
                        "DataFrame ID":
                            person_row.get(
                                "id"
                            ),
                        "DataFrame has ID column":
                            "id" in df.columns,
                    }
                )

        elif (
            cv_documents is None
            or cv_documents.empty
        ):
            st.info(
                "No CV or supporting document is registered "
                "for this personnel."
            )

            st.caption(
                f"Database personnel ID: {personnel_id}"
            )

        elif (
            "SharePoint URL"
            not in cv_documents.columns
        ):
            st.error(
                "The CV query did not return a "
                "SharePoint URL column."
            )

        else:
            cv_documents = (
                cv_documents.copy()
            )

            cv_documents[
                "SharePoint URL"
            ] = (
                cv_documents[
                    "SharePoint URL"
                ]
                .fillna("")
                .astype(str)
                .str.strip()
            )

            cv_documents[
                "Valid SharePoint URL"
            ] = (
                cv_documents[
                    "SharePoint URL"
                ]
                .str.lower()
                .str.startswith(
                    (
                        "https://",
                        "http://",
                    )
                )
            )

            valid_documents = (
                cv_documents[
                    cv_documents[
                        "Valid SharePoint URL"
                    ]
                ]
                .copy()
            )

            invalid_documents = (
                cv_documents[
                    ~cv_documents[
                        "Valid SharePoint URL"
                    ]
                ]
                .copy()
            )

            if valid_documents.empty:
                st.warning(
                    "Document records exist, but none has "
                    "a valid SharePoint HTTPS link."
                )

                diagnostic_columns = [
                    column
                    for column in [
                        "CV File Name",
                        "File Type",
                        "SharePoint URL",
                        "Match Method",
                        "Notes",
                    ]
                    if column
                    in cv_documents.columns
                ]

                with st.expander(
                    "Document import diagnostics",
                    expanded=True,
                ):
                    st.dataframe(
                        cv_documents[
                            diagnostic_columns
                        ],
                        width="stretch",
                        hide_index=True,
                    )

            else:
                valid_documents[
                    "Modified Date"
                ] = pd.to_datetime(
                    valid_documents.get(
                        "Modified Date"
                    ),
                    errors="coerce",
                )

                sort_columns = [
                    column
                    for column in [
                        "Modified Date",
                        "id",
                    ]
                    if column
                    in valid_documents.columns
                ]

                if sort_columns:
                    valid_documents = (
                        valid_documents.sort_values(
                            by=sort_columns,
                            ascending=[
                                False
                                for _
                                in sort_columns
                            ],
                            na_position="last",
                        )
                    )

                primary_document = (
                    valid_documents.iloc[0]
                )

                primary_file = (
                    primary_document.get(
                        "CV File Name"
                    )
                    or "CV document"
                )

                primary_file_type = (
                    primary_document.get(
                        "File Type"
                    )
                    or "N/A"
                )

                primary_url = str(
                    primary_document.get(
                        "SharePoint URL"
                    )
                ).strip()

                primary_modified = (
                    primary_document.get(
                        "Modified Date"
                    )
                )

                primary_modified_display = (
                    primary_modified.strftime(
                        "%d %b %Y"
                    )
                    if pd.notna(
                        primary_modified
                    )
                    else "Date unavailable"
                )

                (
                    cv_latest_col,
                    cv_type_col,
                    cv_modified_col,
                ) = st.columns(
                    [2, 1, 1]
                )

                with cv_latest_col:
                    st.metric(
                        "Latest Document",
                        primary_file,
                    )

                with cv_type_col:
                    st.metric(
                        "File Type",
                        primary_file_type,
                    )

                with cv_modified_col:
                    st.metric(
                        "Last Modified",
                        primary_modified_display,
                    )

                st.link_button(
                    "📄 Open Latest Document in SharePoint",
                    primary_url,
                    width="stretch",
                )

                st.caption(
                    f"{len(valid_documents)} valid document "
                    "link(s) available."
                )

                with st.expander(
                    f"🗂️ View all documents "
                    f"({len(valid_documents)})",
                    expanded=(
                        len(valid_documents)
                        <= 3
                    ),
                ):
                    for _, document in (
                        valid_documents.iterrows()
                    ):
                        document_name = (
                            document.get(
                                "CV File Name"
                            )
                            or "Document"
                        )

                        document_type = (
                            document.get(
                                "File Type"
                            )
                            or "Unknown"
                        )

                        document_url = str(
                            document.get(
                                "SharePoint URL"
                            )
                        ).strip()

                        document_modified = (
                            document.get(
                                "Modified Date"
                            )
                        )

                        document_date_display = (
                            document_modified.strftime(
                                "%d %b %Y"
                            )
                            if pd.notna(
                                document_modified
                            )
                            else "Date unavailable"
                        )

                        (
                            document_info_col,
                            document_action_col,
                        ) = st.columns(
                            [4, 1],
                            vertical_alignment=(
                                "center"
                            ),
                        )

                        with document_info_col:
                            st.markdown(
                                f"**{document_name}**  \n"
                                f"`{document_type}` • "
                                f"Modified "
                                f"{document_date_display}"
                            )

                        with document_action_col:
                            st.link_button(
                                "Open",
                                document_url,
                                width="stretch",
                            )

                        st.divider()

                if not invalid_documents.empty:
                    diagnostic_columns = [
                        column
                        for column in [
                            "CV File Name",
                            "File Type",
                            "SharePoint URL",
                            "Match Method",
                            "Notes",
                        ]
                        if column
                        in invalid_documents.columns
                    ]

                    with st.expander(
                        "⚠️ Documents without valid links "
                        f"({len(invalid_documents)})"
                    ):
                        st.dataframe(
                            invalid_documents[
                                diagnostic_columns
                            ],
                            width="stretch",
                            hide_index=True,
                        )

    # =========================================================================
    # TARGET DEFINITION
    # =========================================================================

    st.markdown("---")

    st.subheader(
        "🎯 Target Definition & Career Progression"
    )

    (
        selected_ruler,
        target_sg,
        selected_ruler_requirements,
    ) = _render_ruler_target_filters(
        person_row=person_row,
        ruler_map=ruler_map,
        suffix="main",
    )

    # =========================================================================
    # BUILD GAP ANALYSIS ONCE
    # =========================================================================

    gap_dataframe = pd.DataFrame()
    strict_readiness = 0.0
    weighted_readiness = 0.0
    category_readiness = {}

    if target_sg is not None:
        gap_dataframe = (
            _build_target_gap_dataframe(
                person_row=person_row,
                target_sg=target_sg,
                selected_ruler_requirements=(
                    selected_ruler_requirements
                ),
                tech_labels=tech_labels,
            )
        )

        (
            strict_readiness,
            weighted_readiness,
            category_readiness,
        ) = _calculate_readiness_metrics(
            gap_dataframe
        )

    

    # =========================================================================
    # ASSESSMENT RESULTS
    # =========================================================================

    if gap_dataframe.empty:
        st.info(
            "No competency requirements are available "
            "for the selected Career Ruler and Target SG."
        )

    else:
        st.markdown("---")

        st.subheader(
            f"📊 Assessment Summary vs Target "
            f"({target_sg})"
        )

        number_met = int(
            (
                gap_dataframe["Status"]
                == "✅ Met"
            ).sum()
        )

        number_minor = int(
            (
                gap_dataframe["Status"]
                == "🟡 Minor Gap"
            ).sum()
        )

        number_major = int(
            (
                gap_dataframe["Status"]
                == "🔴 Major Gap"
            ).sum()
        )

        number_unassessed = int(
            (
                gap_dataframe["Status"]
                == "Not Assessed"
            ).sum()
        )

        if weighted_readiness >= 80:
            overall_status = "Ready ✅"
        elif weighted_readiness >= 60:
            overall_status = "On Track 🟡"
        else:
            overall_status = "Needs Work 🔴"

        (
            assessment_total_col,
            assessment_weighted_col,
            assessment_strict_col,
            assessment_status_col,
        ) = st.columns(4)

        assessment_total_col.metric(
            "Total Competencies",
            len(gap_dataframe),
        )

        assessment_weighted_col.metric(
            "Weighted Readiness",
            f"{weighted_readiness:.0f}%",
        )

        assessment_strict_col.metric(
            "Strict Readiness",
            f"{strict_readiness:.0f}%",
        )

        assessment_status_col.metric(
            "Overall Status",
            overall_status,
        )

        (
            status_met_col,
            status_minor_col,
            status_major_col,
            status_unassessed_col,
        ) = st.columns(4)

        status_met_col.metric(
            "Met",
            number_met,
        )

        status_minor_col.metric(
            "Minor Gaps",
            number_minor,
        )

        status_major_col.metric(
            "Major Gaps",
            number_major,
        )

        status_unassessed_col.metric(
            "Not Assessed",
            number_unassessed,
        )



        # ---------------------------------------------------------------------
        # STORED SUMMARY SCORE, ONCE
        # ---------------------------------------------------------------------
        if summary_score is not None:
                with st.expander(
                    (
                        "📊 Summary Personnel Scores and Competencies "
                        "for Staff, Principal, and Custodian"
                    ),
                    expanded=False,
                ):
                    summary_groups = {
                        "Staff": {
                            "Base": "staff_base",
                            "Keys": "staff_keys",
                            "Pacing": "staff_pacing",
                            "Emerging": "staff_emerging",
                            "CTI": "staff_cti",
                        },
                        "Principal": {
                            "Base": "principal_base",
                            "Keys": "principal_keys",
                            "Pacing": "principal_pacing",
                            "Emerging": "principal_emerging",
                            "CTI": "principal_cti",
                        },
                        "Custodian": {
                            "Base": "custodian_base",
                            "Keys": "custodian_keys",
                            "Pacing": "custodian_pacing",
                            "Emerging": "custodian_emerging",
                            "CTI": "custodian_cti",
                        },
                    }

                    staff_tab, principal_tab, custodian_tab = st.tabs(
                        [
                            "Staff",
                            "Principal",
                            "Custodian",
                        ]
                    )

                    group_tabs = {
                        "Staff": staff_tab,
                        "Principal": principal_tab,
                        "Custodian": custodian_tab,
                    }

                    for group_name, score_fields in summary_groups.items():
                        with group_tabs[group_name]:
                            st.markdown(
                                f"✨Talent's Summary Scores and Readiness"
                            )

                            metric_columns = st.columns(5)

                            for (
                                metric_column,
                                (
                                    metric_name,
                                    field_name,
                                ),
                            ) in zip(
                                metric_columns,
                                score_fields.items(),
                            ):
                                raw_value = getattr(
                                    summary_score,
                                    field_name,
                                    None,
                                )

                                with metric_column:
                                    st.metric(
                                        metric_name,
                                        _format_summary_metric(
                                            raw_value
                                        ),
                                    )

        else:
                st.caption(
                    "No stored competency summary scores are "
                    "available for this personnel."
                )
        # ---------------------------------------------------------------------
        # CATEGORY READINESS
        # ---------------------------------------------------------------------

        if category_readiness:
            st.markdown(
                "#### Category Readiness"
            )

            ordered_categories = [
                category
                for category in [
                    "Base",
                    "Key",
                    "Pacing",
                    "Emerging",
                ]
                if category
                in category_readiness
            ]

            category_columns = st.columns(
                len(ordered_categories)
            )

            for column, category in zip(
                category_columns,
                ordered_categories,
            ):
                column.metric(
                    f"{category} Competencies",
                    (
                        f"{category_readiness[category]:.0f}%"
                    ),
                )

        # =========================================================================
        # VISUALIZATIONS
        # =========================================================================

        st.markdown("---")

        st.subheader(
            "📈 Gap Analysis Visualizations"
        )

        (
            actual_target_figure,
            radar_figure,
        ) = _build_gap_charts(
            gap_dataframe=gap_dataframe,
            target_sg=target_sg,
        )

        chart_left_col, chart_right_col = (
            st.columns(
                [3, 2]
            )
        )

        with chart_left_col:
            st.plotly_chart(
                actual_target_figure,
                width="stretch",
                config={
                    "displaylogo": False,
                    "responsive": True,
                },
            )

        with chart_right_col:
            if radar_figure is not None:
                st.plotly_chart(
                    radar_figure,
                    width="stretch",
                    config={
                        "displaylogo": False,
                        "responsive": True,
                    },
                )
            else:
                st.info(
                    "No assessed competency scores "
                    "are available for the radar chart."
                )

        _render_tech_class_reference()
        # =========================================================================
        # DETAILED GAP ANALYSIS
        # =========================================================================

        st.markdown("---")

        st.subheader(
            "📋 Detailed Gap Analysis"
        )

        status_order = {
            "🔴 Major Gap": 0,
            "🟡 Minor Gap": 1,
            "Not Assessed": 2,
            "✅ Met": 3,
        }

        sorted_gap_dataframe = (
            gap_dataframe.copy()
        )

        sorted_gap_dataframe[
            "_status_order"
        ] = (
            sorted_gap_dataframe[
                "Status"
            ]
            .map(status_order)
            .fillna(99)
        )

        sorted_gap_dataframe = (
            sorted_gap_dataframe.sort_values(
                by=[
                    "_status_order",
                    "Category",
                    "Competency Code",
                ],
                ascending=True,
            )
            .drop(
                columns=[
                    "_status_order"
                ]
            )
        )

        for numeric_column in [
            "Actual Score",
            "Target Score",
            "Gap",
        ]:
            if (
                numeric_column
                in sorted_gap_dataframe.columns
            ):
                sorted_gap_dataframe[
                    numeric_column
                ] = (
                    sorted_gap_dataframe[
                        numeric_column
                    ]
                    .round(2)
                )

        priority_dataframe = (
            sorted_gap_dataframe[
                sorted_gap_dataframe[
                    "Status"
                ].isin(
                    [
                        "🔴 Major Gap",
                        "🟡 Minor Gap",
                    ]
                )
            ]
            .copy()
        )

        if priority_dataframe.empty:
            st.success(
                "🎉 No competency gaps were identified "
                "for the selected Target SG."
            )

        else:
            st.markdown(
                "#### 🔥 Priority Development Areas"
            )

            st.caption(
                "Focus on the following competencies "
                "to close the largest gaps first."
            )

            priority_styler = (
                priority_dataframe.style.map(
                    _gap_status_style,
                    subset=["Status"],
                )
            )

            st.dataframe(
                priority_styler,
                width="stretch",
                hide_index=True,
                column_config={
                    "Category":
                        st.column_config.TextColumn(
                            "Category",
                            width="small",
                        ),
                    "Competency Code":
                        st.column_config.TextColumn(
                            "Code",
                            width="small",
                        ),
                    "Competency Name":
                        st.column_config.TextColumn(
                            "Competency",
                            width="large",
                        ),
                    "Actual Score":
                        st.column_config.NumberColumn(
                            "Actual",
                            format="%.2f",
                        ),
                    "Target Score":
                        st.column_config.NumberColumn(
                            "Target",
                            format="%.2f",
                        ),
                    "Gap":
                        st.column_config.NumberColumn(
                            "Gap",
                            format="%.2f",
                        ),
                },
            )

        st.markdown(
            "#### Full Competency Breakdown"
        )

        full_styler = (
            sorted_gap_dataframe.style.map(
                _gap_status_style,
                subset=["Status"],
            )
        )

        st.dataframe(
            full_styler,
            width="stretch",
            hide_index=True,
            column_config={
                "Category":
                    st.column_config.TextColumn(
                        "Category",
                        width="small",
                    ),
                "Competency Code":
                    st.column_config.TextColumn(
                        "Code",
                        width="small",
                    ),
                "Competency Name":
                    st.column_config.TextColumn(
                        "Competency",
                        width="large",
                    ),
                "Actual Score":
                    st.column_config.NumberColumn(
                        "Actual",
                        format="%.2f",
                    ),
                "Target Score":
                    st.column_config.NumberColumn(
                        "Target",
                        format="%.2f",
                    ),
                "Gap":
                    st.column_config.NumberColumn(
                        "Gap",
                        format="%.2f",
                    ),
                "Status":
                    st.column_config.TextColumn(
                        "Status",
                        width="medium",
                    ),
            },
        )

    # =========================================================================
    # HISTORY AND EXPORT
    # =========================================================================

    st.markdown("---")

    st.subheader(
        "📅 Assessment History & Export"
    )

    history_column, export_column = (
        st.columns(
            [3, 1],
            vertical_alignment="top",
        )
    )

    with history_column:
        history_dataframe = pd.DataFrame()

        if personnel_id is not None:
            history_session = None

            try:
                history_session = (
                    get_session(engine)
                )

                history_dataframe = (
                    db_ops.get_assessment_history(
                        history_session,
                        personnel_id,
                    )
                )

            except Exception as exc:
                st.warning(
                    "Unable to retrieve assessment "
                    f"history: {exc}"
                )

            finally:
                if (
                    history_session
                    is not None
                ):
                    history_session.close()

        if (
            history_dataframe is None
            or history_dataframe.empty
        ):
            st.info(
                "No historical assessment records "
                "are available for this personnel."
            )

        else:
            history_dataframe = (
                history_dataframe.copy()
            )

            history_dataframe["date"] = (
                pd.to_datetime(
                    history_dataframe[
                        "date"
                    ],
                    errors="coerce",
                )
            )

            history_summary = (
                history_dataframe
                .groupby(
                    [
                        "date",
                        "competency_type",
                    ],
                    as_index=False,
                )[
                    "actual_score"
                ]
                .mean()
            )

            history_figure = go.Figure()

            for competency_type in (
                history_summary[
                    "competency_type"
                ]
                .dropna()
                .unique()
            ):
                type_dataframe = (
                    history_summary[
                        history_summary[
                            "competency_type"
                        ]
                        == competency_type
                    ]
                )

                history_figure.add_trace(
                    go.Scatter(
                        x=type_dataframe[
                            "date"
                        ],
                        y=type_dataframe[
                            "actual_score"
                        ],
                        mode="lines+markers",
                        name=str(
                            competency_type
                        ),
                    )
                )

            history_figure.update_layout(
                title=(
                    "Average Competency Score "
                    "by Assessment Date"
                ),
                height=350,
                xaxis_title=(
                    "Assessment Date"
                ),
                yaxis_title=(
                    "Average Score"
                ),
                yaxis={
                    "range": [0, 5],
                    "dtick": 1,
                },
                margin={
                    "l": 30,
                    "r": 20,
                    "t": 60,
                    "b": 40,
                },
            )

            st.plotly_chart(
                history_figure,
                width="stretch",
                config={
                    "displaylogo": False,
                    "responsive": True,
                },
            )

    with export_column:
        st.markdown(
            "#### Export"
        )

        if target_sg is None:
            st.info(
                "Select a target salary grade "
                "before exporting."
            )

        elif gap_dataframe.empty:
            st.info(
                "No assessment results are "
                "available to export."
            )

        else:
            safe_person_name = (
                _make_widget_safe_text(
                    selected_name
                )
                or "personnel"
            )

            export_metrics = (
                strict_readiness,
                weighted_readiness,
                category_readiness,
            )

            try:
                pdf_buffer = export_to_pdf(
                    person_row=person_row,
                    target_sg=target_sg,
                    df_gap=gap_dataframe,
                    metrics=export_metrics,
                )

                pdf_bytes = (
                    pdf_buffer.getvalue()
                )

            except Exception as exc:
                st.error(
                    f"PDF export failed: {exc}"
                )

                pdf_bytes = None

            if pdf_bytes is not None:
                st.download_button(
                    label=(
                        "📥 Download PDF Report"
                    ),
                    data=pdf_bytes,
                    file_name=(
                        f"Assessment_"
                        f"{safe_person_name}_"
                        f"{target_sg}_"
                        f"{datetime.now():%Y%m%d}"
                        f".pdf"
                    ),
                    mime="application/pdf",
                    key=(
                        f"download_pdf_"
                        f"{safe_person_name}_"
                        f"{target_sg}"
                    ),
                    width="stretch",
                )

# ═════════════════════════════════════════════════════════════════════════════
# PAGE: READINESS & GAPS
# ═════════════════════════════════════════════════════════════════════════════

elif page == "🎯 Readiness & Gaps":

    # =========================================================================
    # PAGE HEADER
    # =========================================================================

    st.title(
        "🎯 Readiness & Gaps Deep Dive"
    )

    st.caption(
        "Understand competency readiness, capability constraints, "
        "assessment coverage, and personnel development priorities."
    )

    if df is None or df.empty:
        st.warning(
            "No personnel data is available."
        )
        st.stop()

    required_columns = [
        "Name",
        "Department",
        "Staff Position",
        "SG",
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df.columns
    ]

    if missing_columns:
        st.error(
            "The personnel dataset is missing required columns: "
            f"{missing_columns}"
        )
        st.stop()

    if not ruler_map:
        st.error(
            "No Career Ruler requirements are available."
        )
        st.stop()

    # =========================================================================
    # GLOBAL FILTER OPTIONS
    # =========================================================================

    department_options = _build_filter_options(
        df,
        "Department",
    )

    position_options = _build_filter_options(
        df,
        "Staff Position",
    )

    salary_grade_options = _rg_sort_salary_grades(
        _build_filter_options(
            df,
            "SG",
        )
    )

    employment_options = _build_filter_options(
        df,
        "Employment Category",
    )

    ruler_options = sorted(
        [
            str(ruler).strip()
            for ruler in ruler_map.keys()
        ]
    )

    all_target_grades = _rg_sort_salary_grades(
        [
            grade
            for ruler_requirements in ruler_map.values()
            for grade in ruler_requirements.keys()
        ]
    )

    # =========================================================================
    # GLOBAL FILTERS
    # =========================================================================

    st.subheader(
        "🔎 Global Filters"
    )

    (
        search_filter_col,
        department_filter_col,
        position_filter_col,
        sg_filter_col,
        ruler_filter_col,
    ) = st.columns(
        [2.2, 1.2, 1.2, 1, 1.1]
    )

    with search_filter_col:
        search_text = st.text_input(
            "Search Personnel",
            placeholder="Search by name or Staff ID",
            key="rg_search",
        )

    with department_filter_col:
        selected_departments = st.multiselect(
            "Department",
            options=department_options,
            key="rg_department",
        )

    with position_filter_col:
        selected_positions = st.multiselect(
            "Staff Position",
            options=position_options,
            key="rg_position",
        )

    with sg_filter_col:
        selected_salary_grades = st.multiselect(
            "Current SG",
            options=salary_grade_options,
            key="rg_sg",
        )

    with ruler_filter_col:
        selected_rulers = st.multiselect(
            "Career Ruler",
            options=ruler_options,
            key="rg_ruler",
        )

    (
        employment_filter_col,
        target_mode_filter_col,
        target_sg_filter_col,
        reset_filter_col,
    ) = st.columns(
        [1.4, 1.6, 1.4, 0.8],
        vertical_alignment="bottom",
    )

    with employment_filter_col:
        selected_employment_categories = st.multiselect(
            "Employment Category",
            options=employment_options,
            key="rg_employment",
        )

    with target_mode_filter_col:
        target_mode = st.selectbox(
            "Target Requirement",
            options=[
                "Next salary grade",
                "Current requirement",
                "Selected target grade",
            ],
            index=0,
            key="rg_target_mode",
            help=(
                "Next salary grade compares each personnel member "
                "against the next available grade in the assigned "
                "Career Ruler."
            ),
        )

    with target_sg_filter_col:
        if target_mode == "Selected target grade":
            selected_target_sg = st.selectbox(
                "Selected Target SG",
                options=all_target_grades,
                key="rg_selected_target_sg",
            )
        else:
            selected_target_sg = None

            st.text_input(
                "Selected Target SG",
                value="Automatically determined",
                disabled=True,
                key="rg_target_sg_disabled",
            )

    with reset_filter_col:
        if st.button(
            "Reset",
            type="secondary",
            width="stretch",
            key="rg_reset_filters",
        ):
            _reset_readiness_filters()

            if "rg_ruler" in st.session_state:
                del st.session_state["rg_ruler"]

            if "rg_ranking_metric" in st.session_state:
                del st.session_state[
                    "rg_ranking_metric"
                ]

            if "rg_heatmap_scope" in st.session_state:
                del st.session_state[
                    "rg_heatmap_scope"
                ]

            if "rg_priority_person" in st.session_state:
                del st.session_state[
                    "rg_priority_person"
                ]

            st.rerun()

    # =========================================================================
    # APPLY PRE-CALCULATION FILTERS
    # =========================================================================

    filtered_personnel_df = (
        _apply_readiness_personnel_filters(
            personnel_dataframe=df,
            search_text=search_text,
            departments=selected_departments,
            positions=selected_positions,
            salary_grades=selected_salary_grades,
            employment_categories=(
                selected_employment_categories
            ),
        )
    )

    if selected_rulers:
        ruler_series = filtered_personnel_df.apply(
            lambda person_row: str(
                _rg_get_person_ruler(
                    person_row=person_row,
                    ruler_map=ruler_map,
                )
            ),
            axis=1,
        )

        filtered_personnel_df = (
            filtered_personnel_df[
                ruler_series.isin(
                    selected_rulers
                )
            ]
        )

    if filtered_personnel_df.empty:
        st.warning(
            "No personnel match the selected filters."
        )
        st.stop()

    # =========================================================================
    # BUILD ANALYTICAL DATASETS
    # =========================================================================

    with st.spinner(
        "Calculating readiness and competency gaps..."
    ):
        readiness_detail_df = (
            _build_readiness_detail_dataframe(
                personnel_dataframe=(
                    filtered_personnel_df
                ),
                ruler_map=ruler_map,
                target_mode=target_mode,
                selected_target_sg=(
                    selected_target_sg
                ),
            )
        )

        readiness_summary_df = (
            _build_personnel_readiness_summary(
                readiness_detail_df
            )
        )

    if readiness_detail_df is None or readiness_detail_df.empty:
        st.warning(
            "No target requirements could be matched to the "
            "selected personnel and target mode."
        )

        with st.expander(
            "Readiness calculation diagnostics"
        ):
            st.write(
                {
                    "Filtered personnel":
                        len(filtered_personnel_df),
                    "Target mode":
                        target_mode,
                    "Selected target SG":
                        selected_target_sg,
                    "Available rulers":
                        list(ruler_map.keys()),
                }
            )

        st.stop()

    if readiness_summary_df is None or readiness_summary_df.empty:
        st.warning(
            "The competency data was loaded, but personnel-level "
            "readiness could not be summarized."
        )
        st.stop()

    # =========================================================================
    # RESULT FILTERS
    # =========================================================================

    st.markdown(
        "#### Readiness Result Filters"
    )

    (
        coverage_filter_col,
        readiness_status_filter_col,
        result_count_col,
    ) = st.columns(
        [2, 2, 1],
        vertical_alignment="bottom",
    )

    with coverage_filter_col:
        coverage_range = st.slider(
            "Assessment Coverage (%)",
            min_value=0,
            max_value=100,
            value=(0, 100),
            step=5,
            key="rg_coverage",
        )

    with readiness_status_filter_col:
        selected_readiness_statuses = (
            st.multiselect(
                "Readiness Status",
                options=READINESS_STATUS_ORDER,
                key="rg_status",
            )
        )

    filtered_summary_df = (
        readiness_summary_df[
            readiness_summary_df[
                "Assessment Coverage %"
            ].between(
                coverage_range[0],
                coverage_range[1],
                inclusive="both",
            )
        ]
        .copy()
    )

    if selected_readiness_statuses:
        filtered_summary_df = (
            filtered_summary_df[
                filtered_summary_df[
                    "Readiness Status"
                ].isin(
                    selected_readiness_statuses
                )
            ]
        )

    with result_count_col:
        st.metric(
            "Filtered Personnel",
            len(filtered_summary_df),
        )

    if filtered_summary_df.empty:
        st.info(
            "No readiness results match the selected coverage "
            "and readiness-status filters."
        )
        st.stop()

    selected_dataframe_indices = (
        filtered_summary_df[
            "DataFrame Index"
        ]
        .dropna()
        .tolist()
    )

    filtered_detail_df = (
        readiness_detail_df[
            readiness_detail_df[
                "DataFrame Index"
            ].isin(
                selected_dataframe_indices
            )
        ]
        .copy()
    )

    # =========================================================================
    # KPI SUMMARY
    # =========================================================================

    total_personnel = len(
        filtered_summary_df
    )

    fully_assessed_count = int(
        (
            filtered_summary_df[
                "Assessment Coverage %"
            ] >= 90
        ).sum()
    )

    ready_count = int(
        (
            filtered_summary_df[
                "Readiness Status"
            ] == "Ready"
        ).sum()
    )

    near_ready_count = int(
        (
            filtered_summary_df[
                "Readiness Status"
            ] == "Near Ready"
        ).sum()
    )

    major_gap_personnel_count = int(
        (
            filtered_summary_df[
                "Major Gaps"
            ] > 0
        ).sum()
    )

    median_readiness = (
        filtered_summary_df[
            "Weighted Readiness %"
        ]
        .median()
    )

    (
        total_kpi_col,
        assessed_kpi_col,
        ready_kpi_col,
        near_ready_kpi_col,
        major_gap_kpi_col,
        median_kpi_col,
    ) = st.columns(6)

    total_kpi_col.metric(
        "Personnel",
        total_personnel,
    )

    assessed_kpi_col.metric(
        "Fully Assessed",
        fully_assessed_count,
        (
            f"{fully_assessed_count / total_personnel * 100:.0f}%"
            if total_personnel > 0
            else None
        ),
    )

    ready_kpi_col.metric(
        "Ready",
        ready_count,
    )

    near_ready_kpi_col.metric(
        "Near Ready",
        near_ready_count,
    )

    major_gap_kpi_col.metric(
        "With Major Gaps",
        major_gap_personnel_count,
    )

    median_kpi_col.metric(
        "Median Readiness",
        (
            f"{median_readiness:.1f}%"
            if pd.notna(
                median_readiness
            )
            else "N/A"
        ),
    )

    st.caption(
        "Competency readiness is a decision-support indicator. "
        "Assessment and progression decisions should also consider "
        "experience, performance evidence, assignment exposure, "
        "business needs, and leadership judgment."
    )

    # =========================================================================
    # ANALYTICAL TABS
    # =========================================================================

    (
        overview_tab,
        distribution_tab,
        gap_deep_dive_tab,
        personnel_priority_tab,
    ) = st.tabs(
        [
            "📊 Overview",
            "📈 Readiness Distribution",
            "🔍 Gap Deep Dive",
            "🎯 Personnel Prioritization",
        ]
    )

    # =========================================================================
    # TAB 1: OVERVIEW
    # =========================================================================

    with overview_tab:
        st.subheader(
            "Fraternity Readiness Overview"
        )

        overview_left_col, overview_right_col = (
            st.columns(2)
        )

        with overview_left_col:
            readiness_status_figure = (
                _create_readiness_status_chart(
                    filtered_summary_df
                )
            )

            st.plotly_chart(
                readiness_status_figure,
                width="stretch",
                config={
                    "displaylogo": False,
                    "responsive": True,
                },
            )

        with overview_right_col:
            department_readiness_figure = (
                _create_department_readiness_chart(
                    filtered_summary_df
                )
            )

            st.plotly_chart(
                department_readiness_figure,
                width="stretch",
                config={
                    "displaylogo": False,
                    "responsive": True,
                },
            )

        st.subheader(
            "Personnel Ready for Assessment"
        )

        ready_personnel_df = (
            filtered_summary_df[
                filtered_summary_df[
                    "Readiness Status"
                ] == "Ready"
            ]
            .sort_values(
                by=[
                    "Weighted Readiness %",
                    "Strict Readiness %",
                ],
                ascending=[
                    False,
                    False,
                ],
            )
        )

        if ready_personnel_df.empty:
            st.info(
                "No personnel currently satisfy all competency "
                "readiness requirements."
            )

        else:
            ready_display_columns = [
                "Name",
                "Staff ID",
                "Department",
                "Staff Position",
                "Current SG",
                "Career Ruler",
                "Target SG",
                "Assessment Coverage %",
                "Weighted Readiness %",
                "Strict Readiness %",
                "Major Gaps",
                "Recommended Action",
            ]

            ready_display_columns = [
                column
                for column in ready_display_columns
                if column in ready_personnel_df.columns
            ]

            st.dataframe(
                ready_personnel_df[
                    ready_display_columns
                ],
                width="stretch",
                hide_index=True,
                column_config={
                    "Assessment Coverage %":
                        st.column_config.ProgressColumn(
                            "Coverage",
                            min_value=0,
                            max_value=100,
                            format="%.1f%%",
                        ),
                    "Weighted Readiness %":
                        st.column_config.ProgressColumn(
                            "Weighted Readiness",
                            min_value=0,
                            max_value=100,
                            format="%.1f%%",
                        ),
                    "Strict Readiness %":
                        st.column_config.ProgressColumn(
                            "Strict Readiness",
                            min_value=0,
                            max_value=100,
                            format="%.1f%%",
                        ),
                },
            )

        with st.expander(
            "Full Personnel Readiness Table"
        ):
            overview_table_columns = [
                "Name",
                "Staff ID",
                "Department",
                "Staff Position",
                "Employment Category",
                "Current SG",
                "Career Ruler",
                "Target SG",
                "Required Competencies",
                "Assessed Competencies",
                "Assessment Coverage %",
                "Weighted Readiness %",
                "Strict Readiness %",
                "Met Competencies",
                "Minor Gaps",
                "Major Gaps",
                "Gap Burden",
                "Readiness Status",
                "Recommended Action",
            ]

            overview_table_columns = [
                column
                for column in overview_table_columns
                if column in filtered_summary_df.columns
            ]

            st.dataframe(
                filtered_summary_df[
                    overview_table_columns
                ].sort_values(
                    "Weighted Readiness %",
                    ascending=False,
                ),
                width="stretch",
                hide_index=True,
            )

    # =========================================================================
    # TAB 2: READINESS DISTRIBUTION
    # =========================================================================

    with distribution_tab:
        st.subheader(
            "Readiness Distribution and Assessment Coverage"
        )

        readiness_box_figure = (
            _create_readiness_box_plot(
                filtered_summary_df
            )
        )

        st.plotly_chart(
            readiness_box_figure,
            width="stretch",
            config={
                "displaylogo": False,
                "responsive": True,
            },
        )

        (
            distribution_heatmap_col,
            distribution_scatter_col,
        ) = st.columns(2)

        with distribution_heatmap_col:
            category_heatmap_figure = (
                _create_category_readiness_heatmap(
                    filtered_summary_df
                )
            )

            st.plotly_chart(
                category_heatmap_figure,
                width="stretch",
                config={
                    "displaylogo": False,
                    "responsive": True,
                },
            )

        with distribution_scatter_col:
            coverage_scatter_figure = (
                _create_readiness_coverage_scatter(
                    filtered_summary_df
                )
            )

            st.plotly_chart(
                coverage_scatter_figure,
                width="stretch",
                config={
                    "displaylogo": False,
                    "responsive": True,
                },
            )

        with st.expander(
            "How to interpret the coverage quadrant"
        ):
            st.markdown(
                """
                - **Upper right:** High measured readiness and sufficient assessment coverage.
                - **Lower right:** Sufficiently assessed, but competency development is required.
                - **Upper left:** Strong measured results, but insufficient assessment evidence.
                - **Lower left:** Both under-assessed and below readiness expectations.
                """
            )

    # =========================================================================
    # TAB 3: GAP DEEP DIVE
    # =========================================================================

    with gap_deep_dive_tab:
        st.subheader(
            "Competency Gap Deep Dive"
        )

        category_gap_figure = (
            _create_category_gap_distribution(
                filtered_detail_df
            )
        )

        st.plotly_chart(
            category_gap_figure,
            width="stretch",
            config={
                "displaylogo": False,
                "responsive": True,
            },
        )

        competency_risk_df = (
            _build_competency_risk_summary(
                filtered_detail_df
            )
        )

        if competency_risk_df.empty:
            st.info(
                "No assessed competency gaps are available "
                "for risk analysis."
            )

        else:
            risk_matrix_col, ranking_chart_col = (
                st.columns(2)
            )

            with risk_matrix_col:
                competency_risk_figure = (
                    _create_competency_risk_matrix(
                        competency_risk_df
                    )
                )

                st.plotly_chart(
                    competency_risk_figure,
                    width="stretch",
                    config={
                        "displaylogo": False,
                        "responsive": True,
                    },
                )

            with ranking_chart_col:
                ranking_metric = st.selectbox(
                    "Rank competency gaps by",
                    options=[
                        "Affected personnel",
                        "Average gap severity",
                        "Total gap burden",
                        "Major-gap count",
                    ],
                    key="rg_ranking_metric",
                )

                top_gap_figure = (
                    _create_top_competency_gap_chart(
                        risk_dataframe=(
                            competency_risk_df
                        ),
                        ranking_metric=(
                            ranking_metric
                        ),
                    )
                )

                st.plotly_chart(
                    top_gap_figure,
                    width="stretch",
                    config={
                        "displaylogo": False,
                        "responsive": True,
                    },
                )

            st.subheader(
                "Department by Competency Gap Rate"
            )

            heatmap_scope = st.radio(
                "Competencies shown",
                options=[
                    "Top 10",
                    "Top 15",
                    "All",
                ],
                horizontal=True,
                key="rg_heatmap_scope",
            )

            heatmap_top_n = {
                "Top 10": 10,
                "Top 15": 15,
                "All": "All",
            }[heatmap_scope]

            department_heatmap_figure = (
                _create_department_competency_heatmap(
                    detail_dataframe=(
                        filtered_detail_df
                    ),
                    top_n=heatmap_top_n,
                )
            )

            if department_heatmap_figure is None:
                st.info(
                    "No assessed competency data is available "
                    "for the department heatmap."
                )

            else:
                st.plotly_chart(
                    department_heatmap_figure,
                    width="stretch",
                    config={
                        "displaylogo": False,
                        "responsive": True,
                    },
                )

            with st.expander(
                "Competency Risk Detail"
            ):
                risk_display_df = (
                    competency_risk_df.sort_values(
                        by=[
                            "Gap Burden",
                            "Affected Personnel",
                        ],
                        ascending=[
                            False,
                            False,
                        ],
                    )
                )

                st.dataframe(
                    risk_display_df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Gap Prevalence %":
                            st.column_config.ProgressColumn(
                                "Gap Prevalence",
                                min_value=0,
                                max_value=100,
                                format="%.1f%%",
                            ),
                        "Average Gap Severity":
                            st.column_config.NumberColumn(
                                "Average Severity",
                                format="%.2f",
                            ),
                        "Gap Burden":
                            st.column_config.NumberColumn(
                                "Gap Burden",
                                format="%.1f",
                            ),
                    },
                )

    # =========================================================================
    # TAB 4: PERSONNEL PRIORITIZATION
    # =========================================================================

    with personnel_priority_tab:
        st.subheader("Personnel Development Prioritization")

        personnel_priority_figure = (_create_personnel_priority_scatter(filtered_summary_df))

        if isinstance(
            personnel_priority_figure,
            go.Figure,
        ):
            st.plotly_chart(
                personnel_priority_figure,
                width="stretch",
                config={
                    "displaylogo": False,
                    "responsive": True,
                },
            )

        else:
            st.info(
                "The personnel prioritization chart cannot be displayed "
                "because no valid readiness and gap-burden data is")

            st.subheader("Priority Personnel Table")

        priority_order = {
            "Leadership Review Required": 0,
            "Targeted Technical Development": 1,
            "Focused Development Plan": 2,
            "Close 1-2 Minor Gaps": 3,
            "Complete Assessment": 4,
            "Ready for Assessment": 5,
        }

        priority_dataframe = (
            filtered_summary_df.copy()
        )

        priority_dataframe[
            "_Priority Order"
        ] = (
            priority_dataframe[
                "Recommended Action"
            ]
            .map(priority_order)
            .fillna(99)
        )

        priority_dataframe = (
            priority_dataframe.sort_values(
                by=[
                    "_Priority Order",
                    "Major Gaps",
                    "Gap Burden",
                ],
                ascending=[
                    True,
                    False,
                    False,
                ],
            )
            .drop(
                columns=[
                    "_Priority Order"
                ]
            )
        )

        priority_display_columns = [
            "Name",
            "Staff ID",
            "Department",
            "Staff Position",
            "Current SG",
            "Career Ruler",
            "Target SG",
            "Assessment Coverage %",
            "Weighted Readiness %",
            "Strict Readiness %",
            "Major Gaps",
            "Minor Gaps",
            "Gap Burden",
            "Top Gap",
            "Years in Grade",
            "Readiness Status",
            "Recommended Action",
        ]

        priority_display_columns = [
            column
            for column in priority_display_columns
            if column in priority_dataframe.columns
        ]

        st.dataframe(
            priority_dataframe[
                priority_display_columns
            ],
            width="stretch",
            hide_index=True,
            column_config={
                "Assessment Coverage %":
                    st.column_config.ProgressColumn(
                        "Coverage",
                        min_value=0,
                        max_value=100,
                        format="%.1f%%",
                    ),
                "Weighted Readiness %":
                    st.column_config.ProgressColumn(
                        "Weighted Readiness",
                        min_value=0,
                        max_value=100,
                        format="%.1f%%",
                    ),
                "Strict Readiness %":
                    st.column_config.ProgressColumn(
                        "Strict Readiness",
                        min_value=0,
                        max_value=100,
                        format="%.1f%%",
                    ),
                "Gap Burden":
                    st.column_config.NumberColumn(
                        "Gap Burden",
                        format="%.1f",
                    ),
                "Years in Grade":
                    st.column_config.NumberColumn(
                        "Years in Grade",
                        format="%.1f",
                    ),
            },
        )

        st.markdown(
            "#### Selected Personnel Detail"
        )

        priority_person_options = (
            priority_dataframe[
                "Name"
            ]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        if not priority_person_options:
            st.info(
                "No personnel are available for detailed review."
            )

        else:
            selected_priority_person = st.selectbox(
                "Select personnel for gap detail",
                options=priority_person_options,
                key="rg_priority_person",
            )

            selected_person_rows = (
                priority_dataframe[
                    priority_dataframe[
                        "Name"
                    ] == selected_priority_person
                ]
            )

            if selected_person_rows.empty:
                st.info(
                    "The selected personnel summary "
                    "could not be found."
                )

            else:
                selected_person_summary = (
                    selected_person_rows.iloc[0]
                )

                selected_dataframe_index = (
                    selected_person_summary[
                        "DataFrame Index"
                    ]
                )

                person_detail_dataframe = (
                    filtered_detail_df[
                        filtered_detail_df[
                            "DataFrame Index"
                        ] == selected_dataframe_index
                    ]
                    .copy()
                )

                severity_order = {
                    "Major Gap": 0,
                    "Minor Gap": 1,
                    "Not Assessed": 2,
                    "Met": 3,
                }

                person_detail_dataframe[
                    "_Severity Order"
                ] = (
                    person_detail_dataframe[
                        "Gap Severity"
                    ]
                    .map(severity_order)
                    .fillna(99)
                )

                person_detail_dataframe = (
                    person_detail_dataframe.sort_values(
                        by=[
                            "_Severity Order",
                            "Gap",
                            "Competency Code",
                        ],
                        ascending=[
                            True,
                            True,
                            True,
                        ],
                        na_position="last",
                    )
                    .drop(
                        columns=[
                            "_Severity Order"
                        ]
                    )
                )

                (
                    person_readiness_col,
                    person_coverage_col,
                    person_major_gap_col,
                    person_action_col,
                ) = st.columns(4)

                person_readiness_col.metric(
                    "Weighted Readiness",
                    (
                        f"{selected_person_summary['Weighted Readiness %']:.1f}%"
                    ),
                )

                person_coverage_col.metric(
                    "Assessment Coverage",
                    (
                        f"{selected_person_summary['Assessment Coverage %']:.1f}%"
                    ),
                )

                person_major_gap_col.metric(
                    "Major Gaps",
                    int(
                        selected_person_summary[
                            "Major Gaps"
                        ]
                    ),
                )

                person_action_col.metric(
                    "Recommended Action",
                    selected_person_summary[
                        "Recommended Action"
                    ],
                )

                person_detail_columns = [
                    "Category",
                    "Competency Code",
                    "Competency Name",
                    "Actual Score",
                    "Target Score",
                    "Gap",
                    "Gap Severity",
                ]

                person_detail_columns = [
                    column
                    for column in person_detail_columns
                    if column
                    in person_detail_dataframe.columns
                ]

                st.dataframe(
                    person_detail_dataframe[
                        person_detail_columns
                    ],
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Actual Score":
                            st.column_config.NumberColumn(
                                "Actual",
                                format="%.2f",
                            ),
                        "Target Score":
                            st.column_config.NumberColumn(
                                "Target",
                                format="%.2f",
                            ),
                        "Gap":
                            st.column_config.NumberColumn(
                                "Gap",
                                format="%.2f",
                            ),
                    },
                )

# ═════════════════════════════════════════════════════════════════════════════
# PAGE: CHART BUILDER - DYNAMIC CHART CREATION WITH DATA ELEMENT SELECTION
# ═════════════════════════════════════════════════════════════════════════════
elif page == "📊 Chart Builder & Depth Analysis":
    st.title("📊 Dynamic Chart Builder")
    
    st.markdown("""
    Create custom charts by selecting data elements from your dataset.
    The system will:
    - Analyze data types automatically
    - Recommend compatible chart types
    - Show warnings if data elements aren't suitable for analysis
    - Apply filters to focus on specific data subsets
    """)

    st.markdown("---")
    st.subheader("👥 Personnel Competency Comparison")
    st.markdown("Select 1 to 3 personnel to compare their competency profiles using radar charts.")

    if "Name" in df.columns:
        personnel_names = sorted(df["Name"].dropna().unique())
    else:
        personnel_names = []

    selected_comparison_people = st.multiselect(
        "Select up to 3 personnel",
        personnel_names,
        max_selections=3,
        key="personnel_comparison_select",
    )

    if selected_comparison_people:
        comparison_competencies = [col for col in SCORE_COLS if col in df.columns]
        if comparison_competencies:
            comparison_cols = st.columns(len(selected_comparison_people))
            for idx, person_name in enumerate(selected_comparison_people):
                person_row = df[df["Name"] == person_name].iloc[0]
                values = []
                for competency in comparison_competencies:
                    raw_value = person_row.get(competency)
                    try:
                        numeric_value = float(raw_value)
                    except (TypeError, ValueError):
                        numeric_value = 0.0
                    values.append(numeric_value)

                fig_compare = go.Figure()
                fig_compare.add_trace(
                    go.Scatterpolar(
                        r=values + [values[0]],
                        theta=comparison_competencies + [comparison_competencies[0]],
                        fill="toself",
                        name=person_name,
                        line=dict(color="#00a19c", width=2),
                        fillcolor=f"rgba(0, 161, 156, 0.35)",
                    )
                )
                fig_compare.update_layout(
                    title=f"{person_name}",
                    height=320,
                    polar=dict(
                        radialaxis=dict(visible=True, range=[0, 5], dtick=1),
                        bgcolor="rgba(240, 240, 240, 0.15)",
                    ),
                    margin=dict(l=30, r=30, t=50, b=30),
                )
                with comparison_cols[idx]:
                    st.plotly_chart(fig_compare, use_container_width=True)
        else:
            st.info("No competency score columns are available for comparison.")
    else:
        st.info("Choose 1 to 3 personnel to view their competency radar profiles.")

    st.markdown("---")
    
    # Initialize session state for chart builder
    if "cb_filters" not in st.session_state:
        st.session_state.cb_filters = {}
    if "cb_x_element" not in st.session_state:
        st.session_state.cb_x_element = None
    if "cb_y_element" not in st.session_state:
        st.session_state.cb_y_element = None
    if "cb_chart_type" not in st.session_state:
        st.session_state.cb_chart_type = None
    
    # ─────────────────────────────────────────────────────────────────────
    # STEP 1: Select and Apply Filters
    # ─────────────────────────────────────────────────────────────────────
    with st.expander("🔽 Step 1: Apply Filters (Optional)", expanded=False):
        st.markdown("Filter your data to focus on specific personnel or criteria")
        
        filter_cols = st.columns(3)
        filters = {}
        
        # Create filter options
        with filter_cols[0]:
            dept_filter = st.multiselect(
                "Department",
                sorted(df["Department"].dropna().unique()),
                key="chart_dept_filter"
            )
            if dept_filter:
                filters["Department"] = dept_filter
        
        with filter_cols[1]:
            pos_filter = st.multiselect(
                "Staff Position",
                sorted(df["Staff Position"].dropna().unique()),
                key="chart_pos_filter"
            )
            if pos_filter:
                filters["Staff Position"] = pos_filter
        
        with filter_cols[2]:
            sg_filter = st.multiselect(
                "Salary Grade (SG)",
                sorted(df["SG"].dropna().unique()),
                key="chart_sg_filter"
            )
            if sg_filter:
                filters["SG"] = sg_filter
        
        # Apply filters
        if filters:
            filtered_df = df.copy()
            for col, values in filters.items():
                filtered_df = filtered_df[filtered_df[col].isin(values)]

            if filtered_df.empty:
                st.warning("⚠️ Filters resulted in no records. Please adjust your filters.")
                filtered_df = df.copy()
                st.session_state.cb_filters = {}
            else:
                st.session_state.cb_filters = filters
                st.info(f"✅ Filters applied: Showing {len(filtered_df)} of {len(df)} records")
        else:
            filtered_df = df.copy()
            st.session_state.cb_filters = {}
            st.info(f"📊 No filters applied: Using all {len(df)} records")
    
    # Apply filters to working dataframe
    working_df = df.copy()
    if st.session_state.cb_filters:
        for col, values in st.session_state.cb_filters.items():
            working_df = working_df[working_df[col].isin(values)]
    
    # ─────────────────────────────────────────────────────────────────────
    # STEP 2: Select Data Elements for X and Y Axes
    # ─────────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📈 Step 2: Select Data Elements")
    
    # Get available numeric and categorical columns
    numeric_cols = []
    categorical_cols = []
    
    for col in working_df.select_dtypes(include=[np.number]).columns:
        if col not in ["id"]:
            numeric_cols.append(col)
    
    for col in working_df.select_dtypes(include=[object]).columns:
        unique_count = working_df[col].nunique()
        if 1 < unique_count <= 50:  # Reasonable number for categorical
            categorical_cols.append(col)
    
    # Also consider datetime columns
    datetime_cols = []
    for col in working_df.select_dtypes(include=['datetime64']).columns:
        datetime_cols.append(col)
    
    all_selectable = numeric_cols + categorical_cols + datetime_cols
    
    if not all_selectable:
        st.error("❌ No suitable data elements found for charting.")
        st.stop()
    
    col_select1, col_select2 = st.columns(2)
    
    with col_select1:
        x_element = st.selectbox(
            "🔴 X-Axis Data Element",
            all_selectable,
            index=0,
            key="chart_x_select"
        )
        st.session_state.cb_x_element = x_element
    
    with col_select2:
        y_element = st.selectbox(
            "🔵 Y-Axis Data Element (optional, for paired charts)",
            ["— No Y-Axis —"] + [col for col in all_selectable if col != x_element],
            key="chart_y_select"
        )
        st.session_state.cb_y_element = None if y_element == "— No Y-Axis —" else y_element
    
    # ─────────────────────────────────────────────────────────────────────
    # STEP 3: Analyze Data Elements and Check Compatibility
    # ─────────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🔍 Step 3: Data Analysis & Compatibility Check")
    
    # Analyze X element
    x_info = ChartCompatibility.analyze_data_element(working_df[x_element], x_element)
    
    # Analyze Y element if selected
    y_info = None
    if st.session_state.cb_y_element:
        y_info = ChartCompatibility.analyze_data_element(
            working_df[st.session_state.cb_y_element],
            st.session_state.cb_y_element
        )
    
    # Display data element info
    info_col1, info_col2 = st.columns(2)
    
    with info_col1:
        st.markdown(f"#### 🔴 X-Axis: **{x_element}**")
        st.write(f"- **Type**: {x_info.data_type.value}")
        st.write(f"- **Unique Values**: {x_info.unique_count}")
        st.write(f"- **Missing Values**: {x_info.null_count}")
        if x_info.numeric_range:
            st.write(f"- **Range**: {x_info.numeric_range[0]:.2f} to {x_info.numeric_range[1]:.2f}")
        if x_info.sample_values:
            st.write(f"- **Sample**: {', '.join(str(v)[:15] for v in x_info.sample_values[:3])}")
    
    if y_info:
        with info_col2:
            st.markdown(f"#### 🔵 Y-Axis: **{st.session_state.cb_y_element}**")
            st.write(f"- **Type**: {y_info.data_type.value}")
            st.write(f"- **Unique Values**: {y_info.unique_count}")
            st.write(f"- **Missing Values**: {y_info.null_count}")
            if y_info.numeric_range:
                st.write(f"- **Range**: {y_info.numeric_range[0]:.2f} to {y_info.numeric_range[1]:.2f}")
            if y_info.sample_values:
                st.write(f"- **Sample**: {', '.join(str(v)[:15] for v in y_info.sample_values[:3])}")
    
    # ─────────────────────────────────────────────────────────────────────
    # STEP 4: Check for Data Issues and Provide Suggestions
    # ─────────────────────────────────────────────────────────────────────
    suggestions = ChartCompatibility.get_suggestions(x_info, y_info)
    
    if suggestions["has_issues"]:
        with st.warning("⚠️ Data Compatibility Issues Detected"):
            for issue in suggestions["issues"]:
                st.write(f"  {issue}")
            st.markdown("---")
            if suggestions["suggestions"]:
                st.write("**💡 Suggestions:**")
                for suggestion in suggestions["suggestions"]:
                    st.write(f"  {suggestion}")
    else:
        st.success("✅ Data elements look good for analysis!")
    
    # ─────────────────────────────────────────────────────────────────────
    # STEP 5: Get Compatible Chart Types
    # ─────────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📊 Step 4: Select Chart Type")
    
    compatible_charts = ChartCompatibility.get_compatible_charts(x_info, y_info)
    
    # Filter to only compatible charts
    fully_compatible = {
        name: info for name, info in compatible_charts.items()
        if info["is_compatible"]
    }
    
    if not fully_compatible:
        st.error("❌ No compatible chart types for these data elements. Please adjust your selection.")
        st.stop()
    
    # Display compatible charts with descriptions
    st.markdown("**Available Chart Types:**")
    chart_cols = st.columns(min(3, len(fully_compatible)))
    
    selected_chart = st.selectbox("Select Chart Type", list(fully_compatible.keys()), 
                                  format_func=lambda x: f"{fully_compatible[x].get('icon', '📊')} {x}", 
                                  key="chart_type_select")
    chart_buttons = {}
    
    for idx, (chart_name, chart_info) in enumerate(fully_compatible.items()):
        with chart_cols[idx % len(chart_cols)]:
            # Create a nice button/card for each chart
            if st.button(
                f"{chart_info['requirements']['icon']} {chart_name}",
                use_container_width=True,
                key=f"chart_btn_{chart_name}",
                help=chart_info['requirements']['description']
            ):
                selected_chart = chart_name
                st.session_state.cb_chart_type = chart_name
    
    # Display incompatible charts for reference
    incompatible_charts = {
        name: info for name, info in compatible_charts.items()
        if not info["is_compatible"]
    }
    
    if incompatible_charts:
        with st.expander("ℹ️ Incompatible Chart Types (Why?)"):
            for chart_name, chart_info in incompatible_charts.items():
                st.write(f"- **{chart_name}**: {chart_info['reason']}")
    
    # Use stored chart type if no button was clicked
    if st.session_state.cb_chart_type and not selected_chart:
        if st.session_state.cb_chart_type in fully_compatible:
            selected_chart = st.session_state.cb_chart_type
    
    # ─────────────────────────────────────────────────────────────────────
    # STEP 6: Generate Chart
    # ─────────────────────────────────────────────────────────────────────
    if selected_chart or st.session_state.cb_chart_type in fully_compatible:
        chart_type = selected_chart or st.session_state.cb_chart_type
        
        st.markdown("---")
        st.subheader(f"📊 {chart_type}")
        
        try:
            # Initialize chart builder
            builder = ChartBuilder(working_df)
            
            # Create the appropriate chart
            if chart_type == "Scatter Plot":
                fig = builder.create_scatter_plot(
                    x_col=x_element,
                    y_col=st.session_state.cb_y_element,
                    color_col=None,
                    title=f"{x_element} vs {st.session_state.cb_y_element}"
                )
            
            elif chart_type == "Line Chart":
                fig = builder.create_line_chart(
                    x_col=x_element,
                    y_col=st.session_state.cb_y_element,
                    title=f"Trend of {st.session_state.cb_y_element} over {x_element}"
                )
            
            elif chart_type == "Bar Chart":
                fig = builder.create_bar_chart(
                    x_col=x_element,
                    y_col=st.session_state.cb_y_element,
                    title=f"{st.session_state.cb_y_element} by {x_element}"
                )
            
            elif chart_type == "Stacked Bar Chart":
                fig = builder.create_bar_chart(
                    x_col=x_element,
                    y_col=st.session_state.cb_y_element,
                    stacked=True,
                    title=f"Stacked: {st.session_state.cb_y_element} by {x_element}"
                )
            
            elif chart_type == "Histogram":
                fig = builder.create_histogram(
                    x_col=x_element,
                    title=f"Distribution of {x_element}",
                    nbins=30
                )
            
            elif chart_type == "Box Plot":
                fig = builder.create_box_plot(
                    x_col=x_element,
                    y_col=st.session_state.cb_y_element,
                    title=f"Distribution of {st.session_state.cb_y_element} by {x_element}"
                )
            
            elif chart_type == "Pie Chart":
                if len(working_df[x_element].unique()) > 10:
                    st.warning("⚠️ Pie chart works best with ≤10 categories. Showing top 10.")
                fig = builder.create_pie_chart(
                    x_col=x_element,
                    y_col=st.session_state.cb_y_element,
                    title=f"Composition: {x_element}"
                )
            
            elif chart_type == "Bubble Chart":
                st.info("💡 Bubble Chart uses the Y-axis value for bubble size")
                fig = builder.create_bubble_chart(
                    x_col=x_element,
                    y_col=st.session_state.cb_y_element,
                    size_col=st.session_state.cb_y_element,
                    title=f"{x_element} vs {st.session_state.cb_y_element}"
                )
            
            # Display the chart
            st.plotly_chart(fig, use_container_width=True, key=f"chart_{chart_type}")
            
            # Display summary statistics
            
        except ValueError as e:
            st.error(f"❌ Value Error: {str(e)}")
            st.info("💡 Tip: Make sure both axes have valid numeric values")
        except KeyError as e:
            st.error(f"❌ Column '{str(e)}' not found in data")
        except Exception as e:
            st.error(f"❌ Unexpected error: {str(e)}")
            with st.expander("Error details"):
                st.exception(e)
    else:
        st.info("👈 Select a chart type above to generate your visualization")

# ═════════════════════════════════════════════════════════════════════════════
# PAGE: ADMIN - IMPORT DATA
# ═════════════════════════════════════════════════════════════════════════════
elif page == "⚙️ Admin: Import Data":
    st.title("⚙️ Admin: Import Data from Excel")

    uploaded_file = st.file_uploader(
        "Upload the RE Fraternity master workbook",
        type=[
            "xlsx",
            "xlsm",
        ],
        key="master_workbook_upload",
    )

    if uploaded_file is None:
        st.info(
            "Upload the master workbook to preview and "
            "import personnel, ruler, assessment, and CV data."
        )

    else:
        tmp_path = None

        try:
            file_suffix = (
                Path(uploaded_file.name).suffix
                or ".xlsx"
            )

            with tempfile.NamedTemporaryFile(
                suffix=file_suffix,
                delete=False,
            ) as temporary_file:
                temporary_file.write(
                    uploaded_file.getbuffer()
                )

                tmp_path = temporary_file.name

            # -------------------------------------------------------------
            # LOAD ALL WORKBOOK DATA
            # -------------------------------------------------------------

            raw_df = load_master_data(
                tmp_path
            )

            st.dataframe(
                    (
                        df[
                            [
                                "Staff Position",
                                "SG",
                                "Canonical Position",
                                "Canonical SG",
                            ]
                        ]
                        .value_counts()
                        .reset_index(name="Count")
                        .sort_values(["Canonical SG", "Canonical Position"])
                    )
                )
            
            st.dataframe(
                    (
                        df[
                            [
                                "Staff Position",
                                "SG",
                                "Canonical Position",
                                "Canonical SG",
                            ]
                        ]
                        .value_counts()
                        .reset_index(name="Count")
                        .sort_values(["Canonical SG", "Canonical Position"])
                    )
                )

            ruler_map_import, tech_labels_import = (
                load_ruler_and_tech_mapping(
                    tmp_path
                )
            )

            cv_df = load_cv_list(
                tmp_path,
                verbose=True,
            )

            # -------------------------------------------------------------
            # PREVIEW
            # -------------------------------------------------------------

            st.success(
                f"Loaded {len(raw_df):,} personnel records."
            )

            st.success(
                f"Loaded {len(cv_df):,} CV and "
                "supporting-document records."
            )

            valid_cv_links = 0

            if (
                not cv_df.empty
                and "SharePoint URL" in cv_df.columns
            ):
                valid_cv_links = int(
                    cv_df["SharePoint URL"]
                    .fillna("")
                    .astype(str)
                    .str.lower()
                    .str.startswith(
                        (
                            "https://",
                            "http://",
                        )
                    )
                    .sum()
                )

            st.info(
                f"Valid SharePoint links detected: "
                f"{valid_cv_links:,}"
            )

            personnel_tab, cv_tab = st.tabs(
                [
                    "Personnel Preview",
                    "CV List Preview",
                ]
            )

            with personnel_tab:
                st.dataframe(
                    raw_df.head(20),
                    width="stretch",
                    hide_index=True,
                )

            with cv_tab:
                if cv_df.empty:
                    st.warning(
                        "No CV records were detected."
                    )

                else:
                    cv_preview_columns = [
                        column
                        for column in [
                            "Name",
                            "Staff ID",
                            "Staff Position",
                            "CV File Name",
                            "File Type",
                            "SharePoint URL",
                            "Match Method",
                        ]
                        if column in cv_df.columns
                    ]

                    st.dataframe(
                        cv_df[
                            cv_preview_columns
                        ].head(20),
                        width="stretch",
                        hide_index=True,
                    )

            # -------------------------------------------------------------
            # DATABASE IMPORT
            # -------------------------------------------------------------

            if st.button(
                "✅ Confirm Import to Database",
                type="primary",
                width="stretch",
            ):
                session = None

                try:
                    session = get_session(
                        engine
                    )

                    with st.spinner(
                        "Importing personnel, assessments, "
                        "ruler requirements, and CV links..."
                    ):
                        personnel_result = (
                            db_ops.bulk_import_from_df(
                                session,
                                raw_df,
                                ruler_map=(
                                    ruler_map_import
                                ),
                            )
                        )

                        # Personnel must be imported before CV records.
                        cv_result = (
                            db_ops.bulk_import_cv_list(
                                session,
                                cv_df,
                            )
                        )

                    st.success(
                        "Personnel import complete. "
                        f"Added: "
                        f"{personnel_result.get('added', 0)}, "
                        f"Updated: "
                        f"{personnel_result.get('updated', 0)}, "
                        f"Errors: "
                        f"{personnel_result.get('errors', 0)}"
                    )

                    st.success(
                        "CV import complete. "
                        f"Added: {cv_result.get('added', 0)}, "
                        f"Updated: {cv_result.get('updated', 0)}, "
                        f"Unmatched: "
                        f"{cv_result.get('unmatched', 0)}, "
                        f"Skipped: "
                        f"{cv_result.get('skipped', 0)}, "
                        f"Errors: "
                        f"{cv_result.get('errors', 0)}"
                    )

                    if cv_result.get(
                        "unmatched",
                        0,
                    ) > 0:
                        st.warning(
                            "Some CV records could not be matched "
                            "uniquely to personnel. Populate Staff ID "
                            "in the CV list worksheet for those rows."
                        )

                    st.session_state.ruler_map = (
                        ruler_map_import
                    )

                    st.session_state.tech_labels = (
                        tech_labels_import
                    )

                    bump_version()
                    st.cache_data.clear()

                except Exception as exc:
                    if session is not None:
                        session.rollback()

                    st.error(
                        f"Import failed: {exc}"
                    )

                finally:
                    if session is not None:
                        session.close()

        except Exception as exc:
            st.error(
                f"Unable to read the uploaded workbook: {exc}"
            )

        finally:
            if (
                tmp_path is not None
                and os.path.exists(tmp_path)
            ):
                try:
                    os.remove(
                        tmp_path
                    )
                except OSError:
                    pass
# ═════════════════════════════════════════════════════════════════════════════
# PAGE: ADMIN - PERSONNEL CRUD
# ═════════════════════════════════════════════════════════════════════════════
elif page == "⚙️ Admin: Personnel CRUD":
    st.title("⚙️ Admin: Personnel CRUD")

    tab1, tab2, tab3 = st.tabs(["➕ Add", "✏️ Edit", "🗑️ Delete"])

    with tab1:
        with st.form("add_form"):
            c1, c2, c3 = st.columns(3)
            with c1:
                name = st.text_input("Name *")
                staff_id = st.text_input("Staff ID *")
                email = st.text_input("Email")
            with c2:
                gender = st.selectbox("Gender", ["M", "F"])
                age = st.number_input("Age", 18, 70, 30)
                nationality = st.text_input("Nationality", "Malaysia")
            with c3:
                department = st.selectbox("Department", DEPARTMENTS[:-1])
                position = st.selectbox("Staff Position", POSITIONS[:-1])
                chat_status = st.selectbox("Chat Status", CHAT_STATUS_OPTIONS)

            if st.form_submit_button("Add Personnel", type="primary"):
                if not name or not staff_id:
                    st.error("Name and Staff ID are required.")
                else:
                    session = get_session(engine)
                    ok, msg, pid = db_ops.add_personnel(session, {
                        "name": name, "staff_id": staff_id, "email": email,
                        "gender": gender, "age": age, "nationality": nationality,
                        "department": department, "staff_position": position,
                        "chat_status": chat_status,
                    })
                    session.close()
                    if ok:
                        st.success(msg)
                        bump_version()
                        st.cache_data.clear()
                    else:
                        st.error(msg)

    with tab2:
        if df.empty:
            st.info("No personnel to edit.")
        else:
            names = sorted(df["Name"].dropna().unique())
            sel = st.selectbox("Select person", names, key="edit_sel")
            row = df[df["Name"] == sel].iloc[0]
            pid = None
            if "id" in row.index and pd.notna(row["id"]):
                pid = int(row["id"])
            else:
                session = get_session(engine)
                try:
                    person = None
                    staff_id = row.get("Staff ID")
                    if staff_id is not None and not pd.isna(staff_id):
                        person = session.query(Personnel).filter(Personnel.staff_id == str(staff_id)).first()
                    if person is None:
                        person = session.query(Personnel).filter(Personnel.name == row.get("Name")).first()
                    if person:
                        pid = person.id
                finally:
                    session.close()

            if pid is None:
                st.info("No database personnel ID for this person. Import data to enable editing.")
                st.stop()

            with st.form("edit_form"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    name = st.text_input("Name", row["Name"])
                    age = st.number_input("Age", 18, 70, int(row["Age"]) if pd.notna(row["Age"]) else 30)
                with c2:
                    department = st.text_input("Department", row.get("Department") or "")
                    position = st.text_input("Staff Position", row.get("Staff Position") or "")
                with c3:
                    sg = st.text_input("SG (Grade)", row.get("SG") or "")
                    chat_status = st.selectbox("Chat Status", CHAT_STATUS_OPTIONS,
                                              index=CHAT_STATUS_OPTIONS.index(row["Chat Status"])
                                              if row["Chat Status"] in CHAT_STATUS_OPTIONS else 2)

                if st.form_submit_button("Update", type="primary"):
                    session = get_session(engine)
                    ok, msg = db_ops.update_personnel(session, pid, {
                        "name": name, "age": age, "department": department,
                        "staff_position": position, "sg": sg, "chat_status": chat_status,
                    })
                    session.close()
                    if ok:
                        st.success(msg)
                        bump_version()
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(msg)

    with tab3:
        if df.empty:
            st.info("No personnel to delete.")
        else:
            names = sorted(df["Name"].dropna().unique())
            sel = st.selectbox("Select person to delete", names, key="del_sel")
            row = df[df["Name"] == sel].iloc[0]
            pid = None
            if "id" in row.index and pd.notna(row["id"]):
                pid = int(row["id"])
            else:
                session = get_session(engine)
                try:
                    person = None
                    staff_id = row.get("Staff ID")
                    if staff_id is not None and not pd.isna(staff_id):
                        person = session.query(Personnel).filter(Personnel.staff_id == str(staff_id)).first()
                    if person is None:
                        person = session.query(Personnel).filter(Personnel.name == row.get("Name")).first()
                    if person:
                        pid = person.id
                finally:
                    session.close()

            if pid is None:
                st.info("No database personnel ID for this person. Import data to enable deletion.")
                st.stop()

            st.warning(f"⚠️ This will soft-delete **{sel}** (Staff ID: {row['Staff ID']})")
            if st.button("Confirm Delete", type="primary"):
                session = get_session(engine)
                ok, msg = db_ops.delete_personnel(session, pid)
                session.close()
                if ok:
                    st.success(msg)
                    bump_version()
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error(msg)

# ═════════════════════════════════════════════════════════════════════════════
# PAGE: ADMIN - ASSESSMENT ENTRY
# ═════════════════════════════════════════════════════════════════════════════
elif page == "⚙️ Admin: Assessment Entry":
    st.title("⚙️ Admin: New Assessment Entry")

    if df.empty:
        st.info("No personnel available. Import data first.")
        st.stop()

    names = sorted(df["Name"].dropna().unique())
    sel = st.selectbox("Select Personnel", names)
    row = df[df["Name"] == sel].iloc[0]
    pid = None
    if "id" in row.index and pd.notna(row["id"]):
        pid = int(row["id"])
    else:
        session = get_session(engine)
        try:
            person = None
            staff_id = row.get("Staff ID")
            if staff_id is not None and not pd.isna(staff_id):
                person = session.query(Personnel).filter(Personnel.staff_id == str(staff_id)).first()
            if person is None:
                person = session.query(Personnel).filter(Personnel.name == row.get("Name")).first()
            if person:
                pid = person.id
        finally:
            session.close()

    if pid is None:
        st.info("No database personnel ID for this person. Import data to enable assessment entry.")
        st.stop()

    st.markdown(f"**{sel}** — {row.get('Staff Position')} ({row.get('SG')}) — {row.get('Department')}")

    with st.form("assessment_form"):
        c1, c2 = st.columns(2)
        with c1:
            adate = st.date_input("Assessment Date", value=date.today())
            level = st.selectbox("Assessment Level", ASSESSMENT_LEVELS)
        with c2:
            assessor1 = st.text_input("Assessor 1")
            supervisor = st.text_input("Supervisor")

        st.markdown("### Competency Scores (Actual / Target — leave Target as previous if unsure)")

        score_inputs = {}
        for ctype, info in COMP_TYPES.items():
            with st.expander(f"{info['label']} ({ctype})", expanded=(ctype == "B")):
                for code in info["cols"]:
                    prev_actual = row.get(code)
                    prev_req = row.get(f"R-{code}")
                    cc1, cc2 = st.columns(2)
                    with cc1:
                        actual = st.number_input(
                            f"{code} Actual", 0.0, 5.0,
                            float(prev_actual) if pd.notna(prev_actual) else 0.0,
                            step=0.5, key=f"act_{code}"
                        )
                    with cc2:
                        req = st.number_input(
                            f"{code} Target", 0.0, 5.0,
                            float(prev_req) if pd.notna(prev_req) else 3.0,
                            step=0.5, key=f"req_{code}"
                        )
                    score_inputs[code] = {"actual": actual, "req": req, "gap": round(max(req - actual, 0), 2)}

        submitted = st.form_submit_button("💾 Save Assessment", type="primary")

        if submitted:
            session = get_session(engine)
            ok, msg, aid = db_ops.add_assessment(session, pid, {
                "assessment_date": adate, "assessment_level": level,
                "assessor1": assessor1, "supervisor": supervisor,
            })
            if ok:
                ok2, msg2 = db_ops.add_competency_scores(session, aid, pid, score_inputs)
                session.close()
                if ok2:
                    st.success(f"✅ Assessment saved for {sel} on {adate}")
                    bump_version()
                    st.cache_data.clear()
                else:
                    st.error(msg2)
            else:
                session.close()
                st.error(msg)

# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.caption(f"DB: `{DATABASE_URL}` · v3.0 · {datetime.now().strftime('%Y-%m-%d')}")
