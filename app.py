"""
app.py - RE Fraternity Competency Assessment System v3.0
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
    USE_LIVE_EXCEL_SOURCE,
)


# =============================================================================
# DATABASE AND DATA ACCESS
# =============================================================================

from models import (
    Assessment,
    Base,
    Personnel,
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

def create_nationality_bubble_map(map_df: pd.DataFrame,):
    """
    Build a professional Plotly Express nationality bubble map.
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
        zoom=0.7,
        center={
            "lat": 15,
            "lon": 65,
        },
        color_continuous_scale=[
            [0.00, "#BFD730"],
            [0.35, "#00A19C"],
            [0.70, "#20419A"],
            [1.00, "#763F98"],
        ],
        map_style="carto-positron",
        opacity=0.82,
    )

    fig.update_traces(
        marker={
            "sizemin": 7,
        },
        hovertemplate=(
            "<b>%{customdata[0]}</b><br>"
            "Personnel: %{customdata,.0f}<br>"
            "Representation: %{customdata[2]}"
            "<extra></extra>"
        ),
    )

    fig.update_layout(
        title={
            "text": (""),
            "x": 0.01,
            "xanchor": "left",
            "y": 0.97,
            "yanchor": "top",
            "font": {
                "size": 20,
                "color": "#20419A",
            },
        },
        height=560,
        margin={
            "l": 0,
            "r": 0,
            "t": 80,
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
            "y": -0.03,
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
        hoverlabel={
            "bgcolor": "#FFFFFF",
            "bordercolor": "#00A19C",
            "font": {
                "family": "Arial, sans-serif",
                "size": 13,
                "color": "#263238",
            },
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

    match = re.match(
        r"^P(\d+)$",
        str(sg_value).strip().upper(),
    )

    if not match:
        return None

    return int(match.group(1))

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
    with c2: st.metric( "Male", int(male_count), )
    with c3: st.metric( "Female", int(female_count), )
    with c4: st.metric( "CDH Employees", int(cdh_count),)
    with c5: st.metric( "Permanent Employees", int(permanent_count),)

    st.markdown("---")

# =========================================================================
# NATIONALITY DISTRIBUTION
# =========================================================================

    st.markdown("---")
    st.subheader("🌏 RE Around The Globe")
    nationality_map_df, unmatched_nationalities = (prepare_nationality_map_data(df))

    if nationality_map_df.empty:
        st.info(
            "No valid nationality data is available "
            "for the geographical visualization.")
    else:
        nationality_fig = (
            create_nationality_bubble_map(
                nationality_map_df))

        st.plotly_chart( nationality_fig, use_container_width=True, config={
                "displaylogo": False,
                "scrollZoom": True,
                "responsive": True,
                "modeBarButtonsToRemove": [
                    "lasso2d",
                    "select2d",
                ],
                "toImageButtonOptions": {
                    "format": "png",
                    "filename": (
                        "RE_personnel_nationality_map"
                    ),
                    "height": 800,
                    "width": 1400,
                    "scale": 2,
                },
            },
        )

        st.caption(
            "Bubble size and color represent the number of "
            "personnel associated with each nationality. "
            "Markers use approximate country-centroid coordinates."
        )

    if unmatched_nationalities:
        with st.expander(
            "⚠️ Nationality values requiring mapping"
        ):
            st.write(
                unmatched_nationalities
            )
    
    # =========================================================================
    # ROW 1: POSITION & DEPARTMENT DISTRIBUTIONS
    # =========================================================================
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📊 Position Distribution")
        pos = df["Staff Position"].value_counts().reset_index()
        pos.columns = ["Staff Position", "Count"]
        fig = px.bar(pos, x="Staff Position", y="Count", color="Staff Position",
                     color_discrete_sequence=px.colors.sequential.Teal,
                     labels={"Count": "Number of Personnel"})
        fig.update_layout(showlegend=False, height=400, margin=dict(l=10, r=20, t=40, b=20), xaxis_title="Staff Position", yaxis_title="Number of Personnel")
        fig.update_traces(textposition="inside", texttemplate="%{y}",)
        st.plotly_chart(fig, use_container_width=True)
 
    with col2:
        st.subheader("🏢 Department Distribution")
        
        # 1. Count occurrences
        dept = df["Department"].value_counts().reset_index()
        dept.columns = ["Department", "Count"]
        
        # 2. Combine departments < 3% into "Others"
        total_count = dept["Count"].sum()
        threshold = 0.03  # 3% threshold
        
        dept["Department"] = dept.apply(
            lambda row: row["Department"] if (row["Count"] / total_count) >= threshold else "Others",
            axis=1
        )
        
        # Regroup and sum the counts for "Others"
        dept_grouped = dept.groupby("Department", as_index=False)["Count"].sum()
        # use list for 'by' to satisfy type checkers that expect Sequence[str]
        dept_grouped = dept_grouped.sort_values(by=["Count"], ascending=False)
        
        # 3. Create Donut Chart
        fig = px.pie(
            dept_grouped, 
            names="Department", 
            values="Count", 
            hole=0.2,
            color_discrete_sequence=px.colors.sequential.RdBu
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
    #=====================================================
    # SECTION NAME DISTRIBUTION
    # =====================================================
    col3, col4 = st.columns(2)
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
            x="Count",
            y="y_position",
            size="Count",
            color="Count",
            hover_name="Section Name",
            color_continuous_scale="Viridis",
            size_max=80
        )
        
        fig.update_traces(
            hovertemplate="<b>%{hovertext}</b><br>Personnel: %{x}<extra></extra>"
        )
        
        fig.update_layout(
            height=500,
            showlegend=False,
            coloraxis_showscale=False,
            margin=dict(l=10, r=20, t=40, b=20),
            xaxis_title="Number of Personnel",
            yaxis_title="",
            yaxis=dict(
                tickmode="array",
                tickvals=list(range(len(section_final))),  # ✅ Fixed
                ticktext=section_final["Section Name"].tolist(),  # ✅ Fixed
                showgrid=False
            ),
            hovermode="closest",
            
        )
        
        st.plotly_chart(fig, use_container_width=True)

    # =====================================================
    # CURRENT ASSIGNMENT DISTRIBUTION
    # =====================================================
    with col4:
        st.subheader("🌏 Current Assignment Distribution")

        assignment = df["Current Assignment / Loc:"].value_counts()

        top10 = assignment.head(10)
        others = assignment.iloc[10:].sum()

        assignment = pd.concat([ top10,  pd.Series({"Others": others}) ]).reset_index()
        assignment.columns = ["Current Assignment", "Count"]

        assignment = assignment.sort_values("Count", ascending=True)

        fig = px.bar( assignment, x="Count", y="Current Assignment", orientation="h",
            text="Count", color="Count", color_continuous_scale="Viridis",)

        fig.update_traces(
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Count: %{x}<extra></extra>"
        )

        fig.update_layout( height=500, showlegend=False, coloraxis_showscale=False,
                          margin=dict(l=10, r=20, t=40, b=20), xaxis_title="Number of Personnel", yaxis_title="",)
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
                color_discrete_map={"Male": "#1f77b4", "Female": "#ff7f0e"},  # Blue for Male, Orange for Female
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
            
            # Rename columns to readable labels
            sg_gender.columns = sg_gender.columns.map({"M": "Male", "F": "Female"})
            
            # Sort by numeric grade (P1-P10)
            sg_gender = sg_gender.reindex([f"P{i}" for i in range(1, 11) if f"P{i}" in sg_gender.index])
            
            # Create stacked bar chart
            fig = px.bar(
                sg_gender.reset_index(),x="SG", y=["Male", "Female"],
                barmode="stack", title="", labels={"SG": "Salary Grade", "value": "Number of Personnel", "variable": "Gender"},
                color_discrete_map={"Male": "#1f77b4", "Female": "#ff7f0e"})
            
            fig.update_layout(
                
                xaxis_title="Salary Grade", yaxis_title="Number of Personnel", height=400, hovermode="x unified",
                legend=dict( title="Gender", yanchor="top", y=0.99, xanchor="right", x=0.99)) 
            # Remove the text labels showing count (as requested)

            fig.update_traces(textposition="inside", texttemplate="%{y}")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Grade or Gender data not available")
 
        
    # =========================================================================
    # ROW 3: ADDITIONAL INSIGHTS (Optional)
    # =========================================================================

    st.subheader("📈 Age vs Salary Grade Analysis")

    c1, c2, c3 = st.columns(3)
    with c1: f_name = st.multiselect("Filter by Personnel", sorted(df["Name"].dropna().unique()), key="dash_name")
    with c2: f_unit = st.multiselect("Filter by Unit Name", sorted(df["Unit Name"].dropna().unique()), key="dash_unit1")
    with c3: f_pos = st.multiselect("Filter by Position", sorted(df["Staff Position"].dropna().unique()), key="dash_pos1")
    
    tab2d, tab3d = st.tabs([ "📊 Career Distribution (2D)", "🌐 Career Progression (3D)" ])
    
    fdf1 = df.copy()
    if f_name: fdf1 = fdf1[fdf1["Name"].isin(f_name)]
    if f_unit: fdf1 = fdf1[fdf1["Unit Name"].isin(f_unit)]
    if f_pos: fdf1 = fdf1[fdf1["Staff Position"].isin(f_pos)]
        
    sg_order = [ "UPTREX", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8","P9", "P10" ]
                
    scatter_df2 = an.scatter_age_vs_grade(fdf1)
        
    with tab2d:
        # 2D Scatter code
        st.info(
                """
                **Purpose**
                This chart compares **Age** against **Salary Grade (SG)**.
                It helps identify:
                • Employees progressing faster than peers
                • Senior employees remaining at lower grades
                • Overall distribution of grades across age groups
                """
            )
    
        fig = px.scatter(scatter_df2, x="Age", y="SG", color="Overall_avg", 
                         hover_data=[ "Name", "Staff Position", "Department", "Years in PET",],
                         category_orders={ "SG": [ "UPTREX", "P1","P2","P3","P4","P5", "P6","P7","P8","P9","P10" ]},
                         color_continuous_scale="Tealgrn", title="Age vs Salary Grade")
        fig.update_traces( marker=dict(size=10, opacity=0.75, line=dict(width=1,color="white") ))
        fig.update_layout( height=700, xaxis_title="Age", yaxis_title="Salary Grade", plot_bgcolor="white")
    
        st.plotly_chart(fig, use_container_width=True)

    with tab3d:
        # 3D Scatter code   
        fig = px.scatter_3d (scatter_df2, x="Age", y="SG", z="Years in PET", color="Overall_avg",
                             hover_data=[ "Name", "Staff Position", "Department", "Years in PET", "Overall_avg"],
                             category_orders={ "SG": [ "UPTREX", "P1","P2","P3","P4","P5", "P6","P7","P8","P9","P10" ]},
                             color_continuous_scale="Tealgrn", title="Career Progression Landscape")
        fig.update_traces( marker=dict(size=5, opacity=0.75, line=dict(width=1,color="white") ))
        fig.update_layout( height=800,scene=dict( xaxis=dict(title="Age"), 
                                                 yaxis=dict(title="Salary Grade", tickmode="array", 
                                                            tickvals=list(range(1, 11)), 
                                                            ticktext=[f"P{i}" for i in range(1, 11)] ),
                                                            zaxis=dict( title="Years in PET")))
        st.plotly_chart(fig, use_container_width=True)
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
                    "Age", "Chat Status", "Overall_avg"]
    display_cols = [c for c in display_cols if c in fdf.columns]
    show = fdf[display_cols].rename(columns={"Overall_avg": "Avg Score"})
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

# ═════════════════════════════════════════════════════════════════════════════
# PAGE: INDIVIDUAL ASSESSMENT
# ═════════════════════════════════════════════════════════════════════════════
elif page == "👤 Individual Assessment & Talent Profile":
    
    st.title("👤 Individual Assessment & Talent Profile")
    st.markdown("---")

    # Assume these backend modules exist in your environment
    # import analysis_engine as an
    # import db_operations as db_ops
    # from database import get_session, engine

    # =========================================================================
    # HELPER FUNCTIONS (From Code #1 & #2)
    # =========================================================================

    def _grade_rank(sg_value):
        """Parse SG to get numeric rank (P1→1, P2→2, etc.)."""
        if not sg_value or pd.isna(sg_value):
            return None
        match = re.match(r"^P(\d+)$", str(sg_value).strip().upper())
        return int(match.group(1)) if match else None

    def get_assessment_status(gap_value):
        """Determine assessment status based on gap."""
        if pd.isna(gap_value):
            return "Not Assessed"
        if gap_value >= 0:
            return "✅ Met"
        if gap_value >= -1:
            return "🟡 Minor Gap"
        return "🔴 Major Gap"

    # --- Code #1 Engine Functions ---
    def _build_target_gap_dataframe(person_row, target_sg, selected_ruler_requirements, tech_labels):
        """Builds the gap analysis dataframe matching actual scores against a specific Target SG."""
        target_reqs = selected_ruler_requirements.get(target_sg, {})
        
        data = []
        # Base Competencies (B1-B12)
        for i in range(1, 13):
            comp_code = f"B{i}"
            if comp_code in target_reqs:
                actual = pd.to_numeric(person_row.get(comp_code), errors='coerce')
                target = target_reqs[comp_code]
                data.append({
                    "Category": "Base",
                    "Competency Code": comp_code,
                    "Competency Name": tech_labels.get(comp_code, comp_code),
                    "Actual Score": actual,
                    "Target Score": target,
                    "Gap": actual - target if pd.notna(actual) else np.nan
                })
                
        # Key Competencies (K1-K5)
        for i in range(1, 6):
            comp_code = f"K{i}"
            if comp_code in target_reqs:
                actual = pd.to_numeric(person_row.get(comp_code), errors='coerce')
                target = target_reqs[comp_code]
                data.append({
                    "Category": "Key",
                    "Competency Code": comp_code,
                    "Competency Name": tech_labels.get(comp_code, comp_code),
                    "Actual Score": actual,
                    "Target Score": target,
                    "Gap": actual - target if pd.notna(actual) else np.nan
                })

        # Pacing Competencies (P1-P5)
        for i in range(1, 6):
            comp_code = f"P{i}"
            if comp_code in target_reqs:
                actual = pd.to_numeric(person_row.get(comp_code), errors='coerce')
                target = target_reqs[comp_code]
                data.append({
                    "Category": "Pacing",
                    "Competency Code": comp_code,
                    "Competency Name": tech_labels.get(comp_code, comp_code),
                    "Actual Score": actual,
                    "Target Score": target,
                    "Gap": actual - target if pd.notna(actual) else np.nan
                })

        # Emerging Competencies (E1-E2)
        for i in range(1, 3):
            comp_code = f"E{i}"
            if comp_code in target_reqs:
                actual = pd.to_numeric(person_row.get(comp_code), errors='coerce')
                target = target_reqs[comp_code]
                data.append({
                    "Category": "Emerging",
                    "Competency Code": comp_code,
                    "Competency Name": tech_labels.get(comp_code, comp_code),
                    "Actual Score": actual,
                    "Target Score": target,
                    "Gap": actual - target if pd.notna(actual) else np.nan
                })
                
        df_gap = pd.DataFrame(data)
        if not df_gap.empty:
            df_gap["Status"] = df_gap["Gap"].apply(get_assessment_status)
        return df_gap

    def _calculate_readiness_metrics(df_gap):
        """Calculates both strict (pass/fail) and weighted metrics from Code #1."""
        if df_gap.empty:
            return 0, 0, {}
            
        total_reqs = len(df_gap)
        met_strict = len(df_gap[df_gap["Gap"] >= 0])
        strict_readiness = (met_strict / total_reqs) * 100 if total_reqs > 0 else 0
        
        total_possible_score = df_gap["Target Score"].sum()
        actual_capped = df_gap.apply(lambda row: min(row["Actual Score"], row["Target Score"]) if pd.notna(row["Actual Score"]) else 0, axis=1)
        total_achieved_score = actual_capped.sum()
        weighted_readiness = (total_achieved_score / total_possible_score) * 100 if total_possible_score > 0 else 0
        
        # Calculate readiness by category
        cat_readiness = {}
        for cat in ["Base", "Key", "Pacing", "Emerging"]:
            cat_df = df_gap[df_gap["Category"] == cat]
            if not cat_df.empty:
                cat_total = cat_df["Target Score"].sum()
                cat_achieved = cat_df.apply(lambda row: min(row["Actual Score"], row["Target Score"]) if pd.notna(row["Actual Score"]) else 0, axis=1).sum()
                cat_readiness[cat] = (cat_achieved / cat_total) * 100 if cat_total > 0 else 0
                
        return strict_readiness, weighted_readiness, cat_readiness

    # =========================================================================
    # PAGE SETUP (Code #2 Layout)
    # =========================================================================

    # Personnel Selection (Code #2 Layout)
    if df.empty:
        st.error("No personnel data available.")
        st.stop()

    names = sorted(df["Name"].dropna().unique())
    col_select = st.columns(1)[0]
    with col_select:
        selected_name = st.selectbox("Select Personnel", names, key="personnel_select")
        person_row = df[df["Name"] == selected_name].iloc[0]

    col_refresh = st.columns(1)[0]
    with col_refresh:
            if st.button("🔄 Refresh", type="secondary"):
                st.rerun()
    # =========================================================================
    # SECTION 1: PERSONNEL PROFILE HEADER (Code #2 Card Style)
    # =========================================================================
    with st.container():
        st.markdown("### 📋 Personnel Profile")
        
        profile_col1, profile_col2, profile_col3, profile_col4 = st.columns(4)
        with profile_col1:
            st.metric("Position / Grade", f"{person_row.get('Staff Position')} ({person_row.get('SG')})")
        with profile_col2:
            st.metric("Department / Unit", f"{person_row.get('Department')} ({person_row.get('Section Name')})")
        with profile_col3:
            st.metric("Current Assignment", person_row.get("Current Assignment / Loc:"))
        with profile_col4:
            st.metric("Years in PETRONAS", int(person_row.get("Years in PET", 0)) if pd.notna(person_row.get("Years in PET")) else "Not Applicable")

        stats_col1, stats_col2, stats_col3, stats_col4 = st.columns(4)
        with stats_col1:
            st.metric("Age", int(person_row.get("Age", 0)) if pd.notna(person_row.get("Age")) else "N/A")
        with stats_col2:
            st.metric("Employment Type", person_row.get("Employment Category"))
        with stats_col3:
            contract_expiry = person_row.get("Contract Expire Date")
            st.metric( "Contract Expiry Date", pd.to_datetime(contract_expiry).strftime("%d %b %Y") if contract_expiry is not None and pd.notna(contract_expiry) else "Not Applicable",)
        with stats_col4:
            st.metric("Length in Grade", int(person_row.get("Years in Salary Grade", 0)) if pd.notna(person_row.get("Years in Salary Grade")) else "Not Applicable")

        st.markdown("### 💪🏼 Talent Profile")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.markdown("#### 💪 Strength")
            st.success(person_row.get("Strength"))

        with col2:
            st.markdown("#### ❤️ Interest")
            st.info(person_row.get("Interest"))

        with col3:
            st.markdown("#### 🎓 Background")
            st.warning(person_row.get("Background"))
    # =========================================================================
    # CURRICULUM VITAE AND SUPPORTING DOCUMENTS
    # =========================================================================

    st.markdown("---")
    st.subheader(
        "📄 Curriculum Vitae & Supporting Documents"
    )

    session = None
    cv_documents = pd.DataFrame()
    personnel_id = None

    try:
        session = get_session(engine)

        personnel_id = db_ops.resolve_personnel_id(
            session=session,
            database_id=person_row.get("id"),
            staff_id=person_row.get("Staff ID"),
            name=person_row.get("Name"),
        )

        if personnel_id is not None:
            cv_documents = (
                db_ops.get_cv_documents(
                    session,
                    personnel_id,
                )
            )

    except Exception as exc:
        st.error(
            f" ❌Unable to retrieve document records: {exc}"
        )

    finally:
        if session is not None:
            session.close()


    if personnel_id is None:
        st.warning(
            "⚠️ The selected personnel could not be matched to a "
            "database record. Check the Staff ID and personnel name."
        )

        with st.expander(
            "Personnel matching diagnostics"
        ):
            st.write(
                {
                    "Name": person_row.get("Name"),
                    "Staff ID": person_row.get("Staff ID"),
                    "DataFrame ID": person_row.get("id"),
                    "DataFrame has ID column":
                        "id" in df.columns,
                }
            )

    elif cv_documents.empty:
        st.info(
            " ❌ No CV or supporting document is registered "
            "for this personnel."
        )

        st.caption(
            "⚠️ The personnel record exists in the database, "
            "but no CV document has been linked to its database ID."
        )

    else:
        # Get CV documents from database
        session = get_session(engine)
        try:
            cv_documents = db_ops.get_cv_documents(session, int(personnel_id))  # ✅ Fixed
        finally:
            session.close()
        
        # Check if any documents exist
        if cv_documents.empty:
            st.info("No CV or supporting document is registered for this personnel.")

        else:
            # ─────────────────────────────────────────────────────────────────
            # VALIDATE URLS
            # ─────────────────────────────────────────────────────────────────
            
            cv_documents["SharePoint URL"] = (
                cv_documents["SharePoint URL"]
                .fillna("")
                .astype(str)
                .str.strip()
            )
            
            cv_documents["Valid SharePoint URL"] = (
                cv_documents["SharePoint URL"]
                .str.startswith(("https://", "http://"))
            )
            
            valid_documents = cv_documents[cv_documents["Valid SharePoint URL"]].copy()
            invalid_documents = cv_documents[~cv_documents["Valid SharePoint URL"]].copy()
            
            # ─────────────────────────────────────────────────────────────────
            # CHECK IF ANY VALID DOCUMENTS EXIST
            # ─────────────────────────────────────────────────────────────────
            
            if valid_documents.empty:
                st.warning(
                    "⚠️ Documents are registered, but none has a valid SharePoint HTTPS link. "
                    "Please verify the Excel file contains valid URLs."
                )
                with st.expander("Document import diagnostics"):
                    st.dataframe(
                        cv_documents[["CV File Name", "File Type", "SharePoint URL"]],
                        use_container_width=True,
                        hide_index=True,
                    )
            else:
                # ─────────────────────────────────────────────────────────────
                # SORT BY MODIFIED DATE
                # ─────────────────────────────────────────────────────────────
                
                valid_documents["Modified Date"] = pd.to_datetime(
                    valid_documents["Modified Date"], errors="coerce"
                )
                valid_documents = valid_documents.sort_values(
                    by=["Modified Date", "id"],
                    ascending=[False, False],
                    na_position="last",
                )
                
                # ─────────────────────────────────────────────────────────────
                # GET PRIMARY DOCUMENT (Most Recent)
                # ─────────────────────────────────────────────────────────────
                
                primary_document = valid_documents.iloc[0]
                primary_file = primary_document.get("CV File Name") or "CV document"
                primary_type = primary_document.get("File Type") or "N/A"
                primary_url = str(primary_document.get("SharePoint URL")).strip()
                primary_modified = primary_document.get("Modified Date")
                
                modified_display = (
                    primary_modified.strftime("%d %b %Y")
                    if pd.notna(primary_modified)
                    else "Date unavailable"
                )
                
                # ─────────────────────────────────────────────────────────────
                # DISPLAY PRIMARY DOCUMENT
                # ─────────────────────────────────────────────────────────────
                
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    st.metric("🗒️ Latest Document", primary_file)
                with col2:
                    st.metric("🗂️ File Type", primary_type)
                with col3:
                    st.metric("📂 Last Modified", modified_display)
                
                st.link_button(
                    "📄 Open Latest Document in SharePoint",
                    primary_url,
                    use_container_width=True,
                )
                
                st.caption(f"{len(valid_documents)} document link(s) available for this personnel.")
                
                # ─────────────────────────────────────────────────────────────
                # LOOP: DISPLAY ALL DOCUMENTS
                # ─────────────────────────────────────────────────────────────
                
                with st.expander(
                    f" 🗂️ View all documents ({len(valid_documents)})",
                    expanded=(len(valid_documents) <= 3),
                ):
                    # 🔄 LOOP STARTS HERE
                    for _, document in valid_documents.iterrows():
                        
                        # Extract document details
                        document_id = document.get("id")
                        document_name = document.get("CV File Name") or "Document"
                        document_type = document.get("File Type") or "Unknown"
                        document_url = str(document.get("SharePoint URL")).strip()
                        document_modified = document.get("Modified Date")
                        
                        # Format the modified date
                        modified_display = (
                            document_modified.strftime("%d %b %Y")
                            if pd.notna(document_modified)
                            else "Date unavailable"
                        )
                        
                        # Create two-column layout
                        doc_col, action_col = st.columns([4, 1])
                        
                        # Left column: Document info
                        with doc_col:
                            st.markdown(
                                f"**{document_name}**  \n"
                                f"`{document_type}` • Modified {modified_display}"
                            )
                        
                        # Right column: Open button
                        with action_col:
                            st.link_button(
                                "Open",
                                document_url,
                            )
                        
                        # Separator line
                        st.divider()
                    
                    # 🔄 LOOP ENDS HERE
                
                # ─────────────────────────────────────────────────────────────
                # SHOW INVALID DOCUMENTS (If any)
                # ─────────────────────────────────────────────────────────────
                
                if not invalid_documents.empty:
                    with st.expander(
                        f"⚠️ Documents without valid web links ({len(invalid_documents)})"
                    ):
                        st.dataframe(
                            invalid_documents[
                                ["CV File Name", "File Type", "SharePoint URL", "Notes"]
                            ],
                            use_container_width=True,
                            hide_index=True,
                        )
    # =========================================================================
    # SECTION 2: TARGET SELECTION & ENGINE (Code #1 Logic)
    # =========================================================================
    st.markdown("### 🎯 Target Definition & Career Progression")

    col_ruler, col_target = st.columns(2)

    with col_ruler:
        ruler_options = list(ruler_map.keys())
        default_ruler = person_row.get("ruler_type", "BASE")
        default_idx = ruler_options.index(default_ruler) if default_ruler in ruler_options else 0
        selected_ruler = st.selectbox("Career Ruler", ruler_options, index=default_idx)

    # Target SG Logic (Filter future grades based on current rank)
    selected_ruler_reqs = ruler_map.get(selected_ruler, {})
    available_sgs = list(selected_ruler_reqs.keys())

    current_sg = str(person_row.get("sg", "")).strip()
    current_rank = _grade_rank(current_sg)

    target_sg_options = []
    if current_rank is not None:
        for sg in available_sgs:
            rank = _grade_rank(sg)
            if rank and rank >= current_rank:
                target_sg_options.append(sg)
    else:
        target_sg_options = available_sgs

    with col_target:
        if target_sg_options:
            target_sg = st.selectbox("Target Salary Grade", target_sg_options)
        else:
            st.warning("No future grades found in ruler.")
            target_sg = None

    df_gap = pd.DataFrame()
    strict_readiness = 0.0
    weighted_readiness = 0.0
    cat_readiness = {}

    # Build Gap Dataframe (Code #1 Engine)
    if target_sg:
        df_gap = _build_target_gap_dataframe(person_row, target_sg, selected_ruler_reqs, tech_labels)
        strict_readiness, weighted_readiness, cat_readiness = _calculate_readiness_metrics(df_gap)

    # =========================================================================
    # SECTION 3: TECH CLASS REFERENCE (Code #2 Expander)
    # =========================================================================
    with st.expander("📚 Tech Class Reference - Competency Definitions", expanded=False):
        st.markdown("**Understanding Competency Codes and Their Meanings**")
        st.markdown("Reference this table to understand what each competency code (e.g., B1, K1, P1, E1) represents in the assessment.")
        st.markdown("")
        
        # Build reference data from config.COMP_TYPES and COMPETENCY_FULLNAMES
        # Sorted numerically: B1-B12, K1-K5, P1-P5, E1-E2
        
        ref_data = []
        
        # Process by category in order: B, K, P, E
        for category_key in ["B", "K", "P", "E"]:
            category_info = COMP_TYPES.get(category_key, {})
            category_name = category_info.get("label", "Unknown")
            codes = category_info.get("cols", [])
            
            for code in codes:
                full_name = COMPETENCY_FULLNAMES.get(code, f"Unknown - {code}")
                ref_data.append({
                    'Category': category_name,
                    'Code': code,
                    'Competency Name': full_name,
                })
        
        ref_df = pd.DataFrame(ref_data)
        
        # Display using Streamlit dataframe with custom column config
        st.dataframe(
            ref_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Category": st.column_config.TextColumn(
                    "Category",
                    width=140,
                    help="Type of competency"
                ),
                "Code": st.column_config.TextColumn(
                    "Code",
                    width=60,
                    help="Competency identifier (e.g., B1, K3, P2)"
                ),
                "Competency Name": st.column_config.TextColumn(
                    "Competency Name",
                    width=400,
                    help="Full name and description of the competency"
                ),
            }
        )
        
        # Add helpful notes
        st.markdown("---")
        st.markdown("**Category Definitions:**")
        category_defs = {
            "🔹 Base Competency (B1-B12)": "Core technical competencies required for reservoir engineering work",
            "🔹 Knowledge (K1-K5)": "Specialized knowledge areas in reservoir engineering and management",
            "🔹 Pacing (P1-P5)": "Professional competencies related to advanced complex systems",
            "🔹 Emerging (E1-E2)": "Emerging technologies and future-focused competencies",
        }
        
        for category, description in category_defs.items():
            st.markdown(f"**{category}:** {description}")
    
    st.markdown("---")
    # =========================================================================
    # SECTION 4: ASSESSMENT SUMMARY (Code #1 Metrics + Code #2 Layout)
    # =========================================================================
    if not df_gap.empty:
        st.markdown(f"### 📊 Assessment Summary vs Target ({target_sg})")
        
        # Gap counts
        n_met = len(df_gap[df_gap["Status"] == "✅ Met"])
        n_minor = len(df_gap[df_gap["Status"] == "🟡 Minor Gap"])
        n_major = len(df_gap[df_gap["Status"] == "🔴 Major Gap"])
        n_unassessed = len(df_gap[df_gap["Status"] == "Not Assessed"])
        
        metric_col1, metric_col2, metric_col3, metric_col4 = st.columns(4)
        with metric_col1:
            st.metric("Total Competencies", len(df_gap))
        with metric_col2:
            st.metric("Weighted Readiness", f"{weighted_readiness:.0f}%")
        with metric_col3:
            st.metric("Strict Readiness", f"{strict_readiness:.0f}%")
        with metric_col4:
            status = "Ready ✅" if weighted_readiness >= 80 else "On Track 🟡" if weighted_readiness >= 60 else "Needs Work 🔴"
            st.metric("Overall Status", status)
            
        # Category readiness breakdown (Code #1)
        if cat_readiness:
            st.markdown("**Category Completion Summary**")
            cat_cols = st.columns(len(cat_readiness))
            for i, (cat, val) in enumerate(cat_readiness.items()):
                cat_cols[i].metric(f"{cat} Competencies", f"{val:.0f}%")

        st.markdown("---")
        # =========================================================================
        # SECTION 5: VISUALIZATIONS (Code #2 Side-by-Side + Code #1 Dynamic Data)
        # =========================================================================
        st.markdown("### 📈 Gap Analysis Visualizations")
        chart_col1, chart_col2 = st.columns([0.6, 0.4])
        
        with chart_col1:
            # Actual vs Target Bar Chart
            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                x=df_gap["Competency Code"],
                y=df_gap["Actual Score"],
                    name="Actual",
                marker_color="#1f77b4"
            ))
            fig_bar.add_trace(go.Scatter(
                x=df_gap["Competency Code"],
                y=df_gap["Target Score"],
                name="Target",
                mode="markers+lines",
                marker=dict(color="red", size=10, symbol="diamond"),
                line=dict(dash="dash")
            ))
            fig_bar.update_layout(title=f"Actual vs Target ({target_sg})", hovermode="x unified", height=400)
            st.plotly_chart(fig_bar, use_container_width=True)

        with chart_col2:
            radar_df = df_gap[df_gap["Actual Score"].notna()].copy()
            if not radar_df.empty:
                radar_actual = radar_df["Actual Score"].tolist()
                radar_target = radar_df["Target Score"].tolist()
                radar_names = radar_df["Competency Code"].tolist()
        
                # Get theme-based colors from config
                from config import PRIMARY, SECONDARY, LIGHT_BG
                
                # Determine font color based on background brightness
                # If background is light, use dark font; if dark, use light font
                # For PETRONAS theme (#003D5C is dark), use white or light gray
                axis_font_color = "#20419a"  # Or use: "#F0F4F8" for light gray on dark
                
                fig_radar = go.Figure()
                
                # Actual Profile
                fig_radar.add_trace(
                    go.Scatterpolar(
                        r=radar_actual + [radar_actual[0]], 
                        theta=radar_names + [radar_names[0]], 
                        fill="toself", 
                        name="Actual", 
                        line=dict(color="#20419A", width=2),  # ← Use config color
                        fillcolor=f"rgba(0, 161, 156, 0.35)"  # ← PETRONAS blue with transparency
                    )
                )
                
                # Target Profile (Dashed)
                fig_radar.add_trace(
                    go.Scatterpolar(
                        r=radar_target + [radar_target[0]],
                        theta=radar_names + [radar_names[0]],
                        fill="none", 
                        name=f"Target ({target_sg})", 
                        line=dict(color="#FF0000", width=2),  # ← Red for contrast
                    )
                )
                
                # UPDATED: Automated font color
                fig_radar.update_layout(
                    title="Competency Profile", 
                    height=400, 
                    showlegend=True, 
                    polar=dict(
                        radialaxis=dict( visible=True, range=[0, 5],dtick=1, # ← AUTOMATED: Font adapts to background
                            tickfont=dict( size=11, color=axis_font_color, family="Arial",  # Dynamic color family="Arial"
                            ),
                            gridcolor="#2A2C2B",
                            gridwidth=1,
                            showline=True,
                            linecolor=axis_font_color,
                            linewidth=1,
                        ),
                        angularaxis=dict(
                            tickfont=dict( size=10, color="#008564",family="Arial")
                        ),
                        bgcolor="rgba(240, 240, 240, 0.5)"
                    ),
                )
                st.plotly_chart(fig_radar, use_container_width=True)

        st.markdown("---")
        # =========================================================================
        # SECTION 6: GAP ANALYSIS TABLES (Code #1 Sorting + Code #2 UI configs)
        # =========================================================================
        st.markdown("### 📋 Detailed Gap Analysis")
        
        # Custom sort logic (Code #1)
        status_order = {"🔴 Major Gap": 0, "🟡 Minor Gap": 1, "Not Assessed": 2, "✅ Met": 3}
        df_gap["sort_order"] = df_gap["Status"].map(status_order)
        df_sorted = df_gap.sort_values(by=["sort_order", "Competency Code"]).drop(columns=["sort_order"])

        for col in ["Actual Score", "Target Score", "Gap"]:
            if col in df_sorted.columns:
                df_sorted[col] = df_sorted[col].round().astype("Int64")

        # UI Coloring config
        def _color_status(val):
            if val == "✅ Met": return "background-color: #90EE90"
            elif val == "🟡 Minor Gap": return "background-color: #FFE4B5"
            elif val == "🔴 Major Gap": return "background-color: #FFB6C6"
            return ""

        # Priority Areas (Code #1 logic)
        df_priority = df_sorted[df_sorted["Status"].isin(["🔴 Major Gap", "🟡 Minor Gap"])]
        
        if not df_priority.empty:
            st.subheader("🔥 Priority Development Areas")
            st.caption("Focus on resolving these gaps to meet target requirements.")
            st.dataframe(
                df_priority.style.map(_color_status, subset=["Status"]),
                use_container_width=True, hide_index=True,
                column_config={
                    "Competency Code": st.column_config.TextColumn("Code", width=80),
                    "Competency Name": st.column_config.TextColumn("Competency", width=300),
                    "Gap": st.column_config.NumberColumn("Gap", width=80)
                }, 
            )
        else:
            st.success("🎉 No competency gaps identified for this Target SG!")

        st.subheader("Full Competency Breakdown")
        st.dataframe(
            df_sorted.style.map(_color_status, subset=["Status"]),
            use_container_width=True, hide_index=True,
            column_config={
                "Competency Code": st.column_config.TextColumn("Code", width=80),
                "Competency Name": st.column_config.TextColumn("Competency", width=300),
                "Actual Score": st.column_config.NumberColumn("Actual", width=80),
                "Target Score": st.column_config.NumberColumn("Target", width=80),
                "Gap": st.column_config.NumberColumn("Gap", width=80),
                "Status": st.column_config.TextColumn("Status", width=120),
            }
        )

        st.markdown("---")

    # =========================================================================
    # SECTION 7 & 8: HISTORY & EXPORT (Code #2 Layout)
    # =========================================================================
    
    st.markdown("### 📅 Assessment History & Export")
    col_hist, col_export = st.columns([0.8, 0.2])

    with col_hist:
        st.info("Trend visualization will appear here if historical data exists.")
        # fig_trend = px.line(...) # Restore DB call for history here
        fig_trend = px.line(title="Assessment Trend (Placeholder)")
        st.plotly_chart(fig_trend, use_container_width=True)

    with col_export:
        with col_export:
            if target_sg is None:
                st.info("Select a target salary grade before exporting.")

            elif df_gap.empty:
                st.info("No assessment results are available to export.")

            else:
                # Make the employee name safe for use in file names and widget keys.
                safe_name = re.sub(
                    r"[^A-Za-z0-9_-]+",
                    "_",
                    str(selected_name).strip(),
                ).strip("_")

                metrics = (
                    strict_readiness,
                    weighted_readiness,
                    cat_readiness,
                )

                try:
                    pdf_buffer = export_to_pdf(
                        person_row=person_row,
                        target_sg=target_sg,
                        df_gap=df_gap,
                        metrics=metrics,
                    )
                    pdf_bytes = pdf_buffer.getvalue()
                except Exception as exc:
                    st.error(f"❌ PDF export failed: {exc}")
                    pdf_bytes = None

                if pdf_bytes is not None:
                    st.download_button(
                        label="📥 Download PDF Report",
                        data=pdf_bytes,
                        file_name=(
                            f"Assessment_{safe_name}_{target_sg}_"
                            f"{datetime.now():%Y%m%d}.pdf"
                        ),
                        mime="application/pdf",
                        key=f"download_pdf_{safe_name}_{target_sg}",
                        use_container_width=True,
                    )
# ═════════════════════════════════════════════════════════════════════════════
# PAGE: READINESS & GAPS
# ═════════════════════════════════════════════════════════════════════════════
elif page == "🎯 Readiness & Gaps":
    st.title("🎯 Readiness & Gaps Analysis")

    if df.empty:
        st.stop()

    tab1, tab2 = st.tabs(["Readiness Tiers", "Gap Status"])

    with tab1:
        ready_df = an.readiness_table(df)

        c1, c2, c3, c4 = st.columns(4)
        for col, tier in zip([c1, c2, c3, c4],
                             ["Tier 1 (<50%)", "Tier 2 (50-80%)", "Tier 3 (80-99%)", "Tier 4 (≥100%)"]):
            col.metric(tier, int((ready_df["Readiness Tier"] == tier).sum()))

        st.markdown("---")

        fig = px.histogram(ready_df.dropna(subset=["Achievement %"]),
                           x="SG", color="Readiness Tier", barmode="stack",
                           category_orders={"SG": sorted(ready_df["SG"].dropna().unique())},
                           color_discrete_sequence=px.colors.sequential.Greens)
        fig.update_layout(title="Readiness Tier by Grade (SG)")
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Personnel Ready for Next Assessment")
        ready_only = ready_df[ready_df["Ready for Assessment"] == "Ready"]
        st.dataframe(ready_only.sort_values("Achievement %", ascending=False),
                     use_container_width=True, hide_index=True)

        st.subheader("Full Readiness Table")
        st.dataframe(ready_df, use_container_width=True, hide_index=True)

    with tab2:
        gap_df = an.gap_summary(df)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("No Gap", int((gap_df["Gap Status"] == "No Gap").sum()))
        c2.metric("1 Gap", int((gap_df["Gap Status"] == "1 Gap").sum()))
        c3.metric(">1 Gap", int((gap_df["Gap Status"] == ">1 Gap").sum()))
        c4.metric("Not Assessed", int((gap_df["Gap Status"] == "Not Assessed").sum()))

        fig = px.pie(gap_df, names="Gap Status", hole=0.4,
                     color="Gap Status",
                     color_discrete_map={"No Gap": "#2E7D32", "1 Gap": "#FDD835",
                                        ">1 Gap": "#C62828", "Not Assessed": "#9E9E9E"})
        st.plotly_chart(fig, use_container_width=True)

        st.dataframe(gap_df, use_container_width=True, hide_index=True)

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
