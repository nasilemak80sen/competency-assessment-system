"""
app.py – RE Fraternity Competency Assessment System v3.0
Run with: streamlit run app.py
"""

from datetime import date, datetime
import os
import re
import tempfile
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from config import (
    APP_TITLE, DATABASE_URL, PRIMARY, SECONDARY,
    SCORE_COLS, REQ_COLS, GAP_COLS, COMP_TYPES,
    DEPARTMENTS, POSITIONS, CHAT_STATUS_OPTIONS, ASSESSMENT_LEVELS,
    GRADE_LABELS, HEATMAP_COLORSCALE, COMPETENCY_FULLNAMES,
)
from models import init_db, get_session, Personnel, Assessment
from data_loader import load_master_data, load_ruler_and_tech_mapping
import db_ops
import analytics as an
# =============================================================================
# CAREER PROGRESSION CONFIGURATION
# =============================================================================

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
                    initial_sidebar_state="expanded")

st.markdown(f"""
<style>
.block-container {{ padding-top: 1.2rem; }}
h1, h2, h3 {{ color: {PRIMARY}; }}
.metric-box {{
    background:#F0F4F8; border-radius:10px; padding:14px 18px;
    border-left:5px solid {SECONDARY};
}}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# DB INIT
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_engine():
    return init_db(DATABASE_URL)

engine = get_engine()

if "data_version" not in st.session_state:
    st.session_state.data_version = 0


def bump_version():
    st.session_state.data_version += 1


@st.cache_data
def load_wide_df(_version: int) -> pd.DataFrame:
    session = get_session(engine)
    try:
        df = db_ops.get_wide_dataframe(session)
    finally:
        session.close()
    if df.empty:
        return df
    df = an.add_category_averages(df)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR NAVIGATION
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.title("📊 " + APP_TITLE)
page = st.sidebar.radio("Navigate", [
    "🏠 Dashboard Home",
    "👥 Personnel Directory",
    "🌡️ Competency Heatmap",
    "🔍 Individual Assessment",
    "🎯 Readiness & Gaps",
    "📈 Trends (Age vs Grade)",
    "⚙️ Admin: Import Data",
    "⚙️ Admin: Personnel CRUD",
    "⚙️ Admin: Assessment Entry",
])

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

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Personnel", stats["total"])
    with c2:
        assessed = df[SCORE_COLS].notna().any(axis=1).sum() if any(c in df.columns for c in SCORE_COLS) else 0
        st.metric("Assessed", int(assessed), f"{assessed/stats['total']*100:.0f}%" if stats['total'] else "")
    with c3:
        st.metric("Chat Status: Yes", stats["chat_yes"])
    with c4:
        st.metric("Chat Status: No (Pending)", stats["chat_no"])

    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Position Distribution")
        pos = df["Staff Position"].value_counts().reset_index()
        pos.columns = ["Staff Position", "Count"]
        fig = px.bar(pos, x="Staff Position", y="Count", color="Staff Position",
                     color_discrete_sequence=px.colors.sequential.Teal)
        fig.update_layout(showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Department Distribution")
        dept = df["Department"].value_counts().reset_index()
        dept.columns = ["Department", "Count"]
        fig = px.pie(dept, names="Department", values="Count", hole=0.4,
                     color_discrete_sequence=px.colors.sequential.RdBu)
        st.plotly_chart(fig, use_container_width=True)

    col3, col4 = st.columns(2)

    with col3:
        st.subheader("Chat Status Breakdown")
        cs = df["Chat Status"].fillna("No Need").value_counts().reset_index()
        cs.columns = ["Chat Status", "Count"]
        fig = px.bar(cs, x="Chat Status", y="Count", color="Chat Status",
                     color_discrete_map={"Yes": "#2E7D32", "No": "#C62828", "No Need": "#9E9E9E"})
        st.plotly_chart(fig, use_container_width=True)

    with col4:
        st.subheader("Assessment Completion by Department")
        comp = an.assessment_completion_by_dept(df)
        fig = px.bar(comp, x="Department", y="completion_pct", text="completion_pct",
                     color="completion_pct", color_continuous_scale="Tealgrn",
                     labels={"completion_pct": "Completion %"})
        fig.update_traces(texttemplate="%{text:.0f}%", textposition="outside")
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Grade (SG) Distribution")
    sg = df["SG"].value_counts().reset_index()
    sg.columns = ["SG", "Count"]
    sg["Label"] = sg["SG"].map(GRADE_LABELS).fillna(sg["SG"])
    fig = px.bar(sg.sort_values("SG"), x="SG", y="Count", text="Label",
                 color="Count", color_continuous_scale="Blues")
    st.plotly_chart(fig, use_container_width=True)


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


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: COMPETENCY HEATMAP
# ═════════════════════════════════════════════════════════════════════════════
elif page == "🌡️ Competency Heatmap":
    st.title("🌡️ Competency Heatmap")

    if df.empty:
        st.stop()

    c1, c2, c3 = st.columns(3)
    with c1:
        f_dept = st.multiselect("Department", sorted(df["Department"].dropna().unique()), key="hm_dept")
    with c2:
        f_pos = st.multiselect("Position", sorted(df["Staff Position"].dropna().unique()), key="hm_pos")
    with c3:
        f_type = st.multiselect("Competency Type", list(COMP_TYPES.keys()),
                                default=list(COMP_TYPES.keys()), key="hm_type")

    fdf = df.copy()
    if f_dept:
        fdf = fdf[fdf["Department"].isin(f_dept)]
    if f_pos:
        fdf = fdf[fdf["Staff Position"].isin(f_pos)]

    value_cols = []
    for t in f_type:
        value_cols += [c for c in COMP_TYPES[t]["cols"] if c in fdf.columns]

    if not value_cols:
        st.info("Select at least one competency type.")
        st.stop()

    mat = an.build_heatmap_matrix(fdf, value_cols)

    if mat.empty:
        st.warning("No assessed personnel match these filters.")
        st.stop()

    st.caption(f"Showing {len(mat)} assessed personnel × {len(value_cols)} competencies")

    fig = go.Figure(data=go.Heatmap(
        z=mat.values,
        x=mat.columns,
        y=mat.index,
        colorscale=HEATMAP_COLORSCALE,
        zmin=0, zmax=5,
        colorbar=dict(title="Score"),
        hovertemplate="Person: %{y}<br>Competency: %{x}<br>Score: %{z}<extra></extra>"
    ))
    fig.update_layout(height=max(400, 20 * len(mat)), xaxis_nticks=len(value_cols))
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Summary Statistics")
    s1, s2, s3, s4 = st.columns(4)
    flat = mat.values.flatten()
    flat = flat[~np.isnan(flat)]
    with s1:
        st.metric("Average Score", f"{flat.mean():.2f}" if len(flat) else "N/A")
    with s2:
        st.metric("High Performers (≥4)", int((flat >= 4).sum()))
    with s3:
        st.metric("Needs Development (≤2)", int((flat <= 2).sum()))
    with s4:
        st.metric("Total Data Points", len(flat))

# =============================================================================
# PAGE: INDIVIDUAL ASSESSMENT
# =============================================================================

elif page == "🔍 Individual Assessment":
    st.title("🔍 Individual Assessment")

    if df.empty:
        st.warning("No personnel data is available.")
        st.stop()

    # -------------------------------------------------------------------------
    # PERSONNEL SELECTION
    # -------------------------------------------------------------------------

    names = sorted(
        df["Name"].dropna().unique()
    )

    selected = st.selectbox(
        "Select Personnel",
        names,
    )

    matching_rows = df[df["Name"] == selected]

    if matching_rows.empty:
        st.error("The selected personnel record could not be found.")
        st.stop()

    person_row = matching_rows.iloc[0]

    current_sg = str(person_row.get("SG") or "").strip().upper()

    current_rank = grade_rank(current_sg)

    current_position = (
        person_row.get("Staff Position")
        or GRADE_POSITION_MAP.get(current_sg, "Not Available")
    )

    # -------------------------------------------------------------------------
    # PERSONNEL SUMMARY
    # -------------------------------------------------------------------------

    st.subheader("👤 Personnel Summary")

    row1_col1, row1_col2, row1_col3 = st.columns(3)

    with row1_col1:
        st.metric("Position / Grade", f"{current_position} ({current_sg})")

    with row1_col2:
        department_section = " / ".join(
            str(v).strip()
            for v in [
                person_row.get("Department"),
                person_row.get("Section Name"),
            ]
            if pd.notna(v) and str(v).strip()
        ) or "N/A"

        st.metric("Department / Section", department_section)

    with row1_col3:
        st.metric(
            "Current Assignment",
            person_row.get("Current Assignment / Loc:") or "N/A",
        )

    row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)

    with row2_col1:
        age_value = person_row.get("Age")

        st.metric("Age", int(age_value) if pd.notna(age_value) else "N/A")

    with row2_col2:
        st.metric("Employment", person_row.get("Employment Category") or "N/A")

    with row2_col3:
        st.metric("Contract Expiry", person_row.get("Contract Expire Date") or "N/A")

    with row2_col4:
        yearsval = person_row.get("Years in Salary Grade")

        if pd.notna(yearsval):
            total_months = round(float(yearsval) * 12)

            years = total_months // 12
            months = total_months % 12

            salary_grade_display = f"{years}y {months}m"
        else:
            salary_grade_display = "N/A"

        st.metric("Length in Grade", salary_grade_display)

    # -------------------------------------------------------------------------
    # LOAD RULER DATA
    # -------------------------------------------------------------------------

    # Prefer the ruler uploaded through the Admin page.
    if "ruler_map" in st.session_state:
        ruler_map = st.session_state["ruler_map"]

        tech_labels = st.session_state.get("competency_names", {})

        ruler_source = st.session_state.get("ruler_source_file", "Uploaded workbook")

    else:
        # Fallback workbook used when Streamlit has restarted and the
        # uploaded workbook is no longer stored in session state.
        workbook_path = os.path.join(os.path.dirname(__file__), "RE Fraternity Jul2026_Master.xlsx")

        if not os.path.exists(workbook_path):
            st.error(
                "Ruler data is not available. Upload the Excel master workbook through Admin: Import Data."
            )
            st.stop()

        try:
            ruler_map, tech_labels = load_ruler_and_tech_mapping(workbook_path)
        except Exception as exc:
            st.error(f"Unable to load ruler data: {exc}")
            st.stop()

        st.session_state["ruler_map"] = ruler_map
        st.session_state["competency_names"] = tech_labels

        ruler_source = os.path.basename(workbook_path)

    if not ruler_map:
        st.error("No ruler requirements are available.")
        st.stop()

    competency_names = (
        st.session_state.get("competency_names", {}) or tech_labels or COMPETENCY_FULLNAMES
    )

    # -------------------------------------------------------------------------
    # NORMALISE RULER KEYS
    # -------------------------------------------------------------------------

    normalized_ruler_map = {}

    for raw_ruler_type, grades in ruler_map.items():
        normalized_type = normalize_ruler_type(raw_ruler_type)

        normalized_ruler_map.setdefault(normalized_type, {}).update(grades)

    ruler_map = normalized_ruler_map

    # -------------------------------------------------------------------------
    # DETERMINE EMPLOYEE RULER
    # -------------------------------------------------------------------------

    employee_ruler = normalize_ruler_type(person_row.get("Ruler Type") or person_row.get("Background"))

    career_rulers = [ruler for ruler in ["RDP", "RMS", "RSS"] if ruler in ruler_map]

    if not career_rulers:
        st.error(
            "The ruler workbook does not contain any RDP, RMS, or RSS progression requirements."
        )
        st.stop()

    if employee_ruler in career_rulers:
        ruler_default_index = career_rulers.index(employee_ruler)
    else:
        ruler_default_index = 0

    # -------------------------------------------------------------------------
    # TARGET SELECTION
    # -------------------------------------------------------------------------

    st.subheader("🎯 Select Career Target")

    st.caption(
        "Select the career ruler and the salary grade that the employee is working towards. The application compares the employee's current competency scores directly against the selected target-grade requirements."
    )

    target_col1, target_col2 = st.columns(2)

    with target_col1:
        selected_ruler = st.selectbox(
            "Career Ruler",
            options=career_rulers,
            index=ruler_default_index,
            help=(
                "Choose the applicable technical career path. P1 and P2 employees must still select the intended RDP, RMS, or RSS path before progression to P3."
            ),
        )

    available_grades = sort_grades(
        ruler_map.get(
            selected_ruler,
            {},
        ).keys()
    )

    if current_rank is not None:
        higher_grades = [
            grade
            for grade in available_grades
            if (
                grade_rank(grade) is not None
                and grade_rank(grade) > current_rank
            )
        ]
    else:
        higher_grades = available_grades

    if not higher_grades:
        st.info(
            f"No higher salary-grade requirements are "
            f"available after {current_sg} under the "
            f"{selected_ruler} ruler."
        )
        st.stop()

    with target_col2:
        target_sg = st.selectbox(
            "Target Salary Grade",
            options=higher_grades,
            index=0,
            format_func=lambda grade: (
                f"{grade} - "
                f"{GRADE_POSITION_MAP.get(grade, 'Position not mapped')}"
            ),
            help=(
                "Select the exact salary grade to assess. "
                "Different grades under the same position may have "
                "different competency requirements."
            ),
        )

    target_rank = grade_rank(target_sg)

    target_position = GRADE_POSITION_MAP.get(
        target_sg,
        "Position not mapped",
    )

    target_requirements = (
        ruler_map
        .get(selected_ruler, {})
        .get(target_sg, {})
    )

    if not target_requirements:
        st.error(
            f"No requirements were found for "
            f"{selected_ruler} {target_sg}."
        )
        st.stop()

    # -------------------------------------------------------------------------
    # TARGET SUMMARY
    # -------------------------------------------------------------------------

    progression_steps = None

    if (
        current_rank is not None
        and target_rank is not None
    ):
        progression_steps = (
            target_rank - current_rank
        )

    summary1, summary2, summary3, summary4 = (
        st.columns(4)
    )

    summary1.metric(
        "Current Grade",
        current_sg or "Unknown",
    )

    summary2.metric(
        "Target Grade",
        target_sg,
    )

    summary3.metric(
        "Target Position",
        target_position,
    )

    summary4.metric(
        "Career Ruler",
        selected_ruler,
    )

    if progression_steps is not None:
        if progression_steps == 1:
            st.info(
                f"Assessing the immediate next-grade progression: "
                f"**{current_sg} → {target_sg}**."
            )
        else:
            st.info(
                f"Assessing a {progression_steps}-grade progression: "
                f"**{current_sg} → {target_sg}**. "
                f"For formal promotion readiness, consider reviewing "
                f"each intermediate grade separately."
            )

    st.caption(
        f"Ruler source: {ruler_source}"
    )

    # -------------------------------------------------------------------------
    # BUILD TARGET-GRADE GAP ANALYSIS
    # -------------------------------------------------------------------------

    target_gap_df = build_target_gap_dataframe(
        person_row=person_row,
        target_requirements=target_requirements,
        current_sg=current_sg,
        target_sg=target_sg,
        target_position=target_position,
        ruler_type=selected_ruler,
        competency_names=competency_names,
    )

    if target_gap_df.empty:
        st.warning(
            f"No applicable competency requirements were found "
            f"for {selected_ruler} {target_sg}."
        )
        st.stop()

    readiness = calculate_readiness_metrics(
        target_gap_df
    )

    # -------------------------------------------------------------------------
    # READINESS METRICS
    # -------------------------------------------------------------------------

    st.markdown("---")
    st.subheader(
        f"📊 Readiness for "
        f"{target_position} ({target_sg})"
    )

    metric1, metric2, metric3, metric4, metric5 = (
        st.columns(5)
    )

    metric1.metric(
        "Weighted Readiness",
        f"{readiness['weighted_readiness']:.0f}%",
        help=(
            "Total competency achievement divided by the total "
            "target requirement. Achievement is capped at the "
            "target for each competency."
        ),
    )

    metric2.metric(
        "Fully Met",
        readiness["met"],
    )

    metric3.metric(
        "Minor Gaps",
        readiness["minor"],
    )

    metric4.metric(
        "Major Gaps",
        readiness["major"],
    )

    metric5.metric(
        "Not Assessed",
        readiness["not_assessed"],
    )

    st.progress(
        min(
            max(
                readiness["weighted_readiness"] / 100,
                0.0,
            ),
            1.0,
        ),
        text=(
            f"Weighted readiness: "
            f"{readiness['weighted_readiness']:.1f}%"
        ),
    )

    st.caption(
        f"Strict readiness: "
        f"{readiness['strict_readiness']:.1f}% of assessed "
        f"competencies fully meet the selected target."
    )

    # -------------------------------------------------------------------------
    # ACTUAL VERSUS TARGET CHART
    # -------------------------------------------------------------------------

    st.markdown("---")
    st.subheader(
        f"Actual vs Target: "
        f"{target_position} ({target_sg})"
    )

    chart_df = target_gap_df.dropna(
        subset=["Actual", "Target"]
    ).copy()

    if chart_df.empty:
        st.info(
            "No assessed competency scores are available "
            "for charting."
        )
    else:
        fig = go.Figure()

        fig.add_trace(
            go.Bar(
                x=chart_df["Competency"],
                y=chart_df["Actual"],
                name="Actual Score",
                marker_color=SECONDARY,
                customdata=chart_df[
                    "Competency Name"
                ],
                hovertemplate=(
                    "<b>%{customdata}</b><br>"
                    "Competency: %{x}<br>"
                    "Actual: %{y}<extra></extra>"
                ),
            )
        )

        fig.add_trace(
            go.Scatter(
                x=chart_df["Competency"],
                y=chart_df["Target"],
                name=f"{target_sg} Target",
                mode="markers",
                marker={
                    "color": "#C62828",
                    "size": 10,
                    "symbol": "diamond",
                },
                customdata=chart_df[
                    "Competency Name"
                ],
                hovertemplate=(
                    "<b>%{customdata}</b><br>"
                    "Competency: %{x}<br>"
                    "Target: %{y}<extra></extra>"
                ),
            )
        )

        fig.update_layout(
            height=500,
            barmode="group",
            xaxis={
                "title": "Competency",
                "categoryorder": "array",
                "categoryarray": SCORE_COLS,
            },
            yaxis={
                "title": "Competency Level",
                "range": [0, 5.5],
                "dtick": 1,
            },
            legend={
                "orientation": "h",
                "yanchor": "bottom",
                "y": 1.02,
                "xanchor": "right",
                "x": 1,
            },
            margin={
                "l": 40,
                "r": 30,
                "t": 50,
                "b": 60,
            },
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )

    # -------------------------------------------------------------------------
    # GAP DETAIL
    # -------------------------------------------------------------------------

    st.markdown("---")
    st.subheader(
        f"🎯 Gap to {target_position} ({target_sg})"
    )

    st.caption(
        "Gap represents the additional competency level required "
        "to meet the selected target. A zero gap means the target "
        "has already been met or exceeded."
    )

    display_df = target_gap_df[
        [
            "Competency",
            "Competency Name",
            "Actual",
            "Target",
            "Gap",
            "Status",
        ]
    ].copy()

    display_df["Actual"] = (
        display_df["Actual"]
        .astype(str)
        .str.split(".")
        .str[0]
    )

    display_df["Target"] = (
        display_df["Target"]
        .astype(str)
        .str.split(".")
        .str[0]
    )

    display_df["Gap"] = (
        display_df["Gap"]
        .astype(str)
        .str.split(".")
        .str[0]
    )
    

    status_order = {
        "Major Gap": 1,
        "Minor Gap": 2,
        "Not Assessed": 3,
        "Met": 4,
    }

    display_df["_status_order"] = (
        display_df["Status"]
        .map(status_order)
        .fillna(99)
    )

    display_df = (
        display_df
        .sort_values(
            by=[
                "_status_order",
                "Gap",
                "Competency",
            ],
            ascending=[
                True,
                False,
                True,
            ],
        )
        .drop(
            columns=["_status_order"]
        )
    )

    def color_gap_status(value):
        colors = {
            "Met": (
                "background-color:#C8E6C9;"
                "color:#1B5E20"
            ),
            "Minor Gap": (
                "background-color:#FFF9C4;"
                "color:#795548"
            ),
            "Major Gap": (
                "background-color:#FFCDD2;"
                "color:#B71C1C"
            ),
            "Not Assessed": (
                "background-color:#E0E0E0;"
                "color:#424242"
            ),
        }

        return colors.get(value, "")

    styled_display = display_df.style.map(
        color_gap_status,
        subset=["Status"],
    )

    st.dataframe(
        styled_display,
        use_container_width=True,
        hide_index=True,
    )

    # -------------------------------------------------------------------------
    # PRIORITY DEVELOPMENT AREAS
    # -------------------------------------------------------------------------

    priority_df = target_gap_df[
        target_gap_df["Status"].isin(
            ["Minor Gap", "Major Gap"]
        )
    ].copy()

    priority_df = priority_df.sort_values(
        by=["Gap", "Competency"],
        ascending=[False, True],
    )

    st.subheader("🚩 Priority Development Areas")

    if priority_df.empty:
        if readiness["not_assessed"] > 0:
            st.success(
                "All assessed competencies meet the selected target. "
                "However, some competencies have not been assessed."
            )
        else:
            st.success(
                f"All applicable competencies meet or exceed the "
                f"{selected_ruler} {target_sg} requirements."
            )
    else:
        priority_display = priority_df[
            [
                "Competency",
                "Competency Name",
                "Actual",
                "Target",
                "Gap",
                "Status",
            ]
        ].copy()

        numeric_cols = ["Actual", "Target", "Gap"]
        priority_display[numeric_cols] = (
            priority_display[numeric_cols]
            .round(0)
            .astype("Int64"))
        priority_display["Priority"] = np.where(
            priority_display["Status"] == "Major Gap",
            "High",
            "Medium",
        )

        priority_display = priority_display[
            [
                "Priority",
                "Competency",
                "Competency Name",
                "Actual",
                "Target",
                "Gap",
                "Status",
            ]
        ]

        priority_styled = (
            priority_display.style.map(
                color_gap_status,
                subset=["Status"],
            )
        )

        st.dataframe(
            priority_styled,
            use_container_width=True,
            hide_index=True,
        )

    # -------------------------------------------------------------------------
    # CATEGORY SUMMARY
    # -------------------------------------------------------------------------

    st.subheader("Competency Category Summary")

    category_names = {
        "B": "Base Competencies",
        "K": "Key Competencies",
        "P": "Pacing Competencies",
        "E": "Emerging Competencies",
    }

    category_df = target_gap_df.copy()

    category_df["Category Code"] = (
        category_df["Competency"]
        .str[0]
    )

    category_df["Category"] = (
        category_df["Category Code"]
        .map(category_names)
        .fillna("Other")
    )

    category_records = []

    for category, group in category_df.groupby(
        "Category"
    ):
        assessed_group = group[
            group["Status"] != "Not Assessed"
        ].copy()

        if assessed_group.empty:
            weighted_category_readiness = 0.0
            category_met = 0
        else:
            achieved = np.minimum(
                assessed_group["Actual"].astype(float),
                assessed_group["Target"].astype(float),
            ).sum()

            required = (
                assessed_group["Target"]
                .astype(float)
                .sum()
            )

            weighted_category_readiness = (
                achieved / required * 100
                if required > 0
                else 0.0
            )

            category_met = int(
                (
                    assessed_group["Status"]
                    == "Met"
                ).sum()
            )

        category_records.append(
            {
                "Category": category,
                "Applicable Competencies": len(group),
                "Assessed": len(assessed_group),
                "Met": category_met,
                "Minor Gaps": int(
                    (
                        group["Status"]
                        == "Minor Gap"
                    ).sum()
                ),
                "Major Gaps": int(
                    (
                        group["Status"]
                        == "Major Gap"
                    ).sum()
                ),
                "Readiness %": round(
                    weighted_category_readiness,
                    1,
                ),
            }
        )

    category_summary_df = pd.DataFrame(
        category_records
    )

    st.dataframe(
        category_summary_df,
        use_container_width=True,
        hide_index=True,
    )

    # -------------------------------------------------------------------------
    # CURRENT COMPETENCY RADAR
    # -------------------------------------------------------------------------

    st.markdown("---")
    st.subheader("Current Competency Profile")

    radar_order = (
        [f"B{i}" for i in range(1, 13)]
        + [f"K{i}" for i in range(1, 6)]
        + [f"P{i}" for i in range(1, 6)]
        + ["E1", "E2"]
    )

    radar_values = []
    radar_targets = []
    radar_labels = []

    for competency in radar_order:
        matching_competency = target_gap_df[
            target_gap_df["Competency"]
            == competency
        ]

        if matching_competency.empty:
            continue

        competency_row = (
            matching_competency.iloc[0]
        )

        if pd.isna(
            competency_row["Actual"]
        ):
            continue

        radar_values.append(
            float(
                competency_row["Actual"]
            )
        )

        radar_targets.append(
            float(
                competency_row["Target"]
            )
        )

        radar_labels.append(
            competency
        )

    if radar_values:
        radar_figure = go.Figure()

        radar_figure.add_trace(
            go.Scatterpolar(
                r=radar_values + [radar_values[0]],
                theta=radar_labels + [radar_labels[0]],
                fill="toself",
                name="Actual",
                line_color=PRIMARY,
            )
        )

        radar_figure.add_trace(
            go.Scatterpolar(
                r=radar_targets + [radar_targets[0]],
                theta=radar_labels + [radar_labels[0]],
                fill="none",
                name=f"{target_sg} Target",
                line={
                    "color": "#C62828",
                    "dash": "dash",
                },
            )
        )

        radar_figure.update_layout(
            polar={
                "radialaxis": {
                    "visible": True,
                    "range": [0, 5],
                    "dtick": 1,
                }
            },
            height=550,
            showlegend=True,
        )

        st.plotly_chart(
            radar_figure,
            use_container_width=True,
        )
    else:
        st.info(
            "No assessed competencies are available "
            "for the radar chart."
        )

    # -------------------------------------------------------------------------
    # ASSESSMENT HISTORY
    # -------------------------------------------------------------------------

    st.markdown("---")
    st.subheader("Assessment History / Trend")

    person_id = person_row.get("id")

    if person_id is None or pd.isna(person_id):
        st.info(
            "No database personnel ID is available "
            "for assessment history."
        )
    else:
        session = get_session(engine)

        try:
            history_df = (
                db_ops.get_assessment_history(
                    session,
                    int(person_id),
                )
            )
        finally:
            session.close()

        if history_df.empty:
            st.info(
                "No historical assessment trend is available."
            )
        else:
            trend = (
                history_df
                .groupby(
                    [
                        "date",
                        "competency_type",
                    ],
                    as_index=False,
                )["actual_score"]
                .mean()
            )

            trend_figure = px.line(
                trend,
                x="date",
                y="actual_score",
                color="competency_type",
                markers=True,
                labels={
                    "actual_score": "Average Score",
                    "date": "Assessment Date",
                    "competency_type": (
                        "Competency Category"
                    ),
                },
            )

            trend_figure.update_layout(
                yaxis={
                    "range": [0, 5],
                    "dtick": 1,
                },
                height=450,
            )

            st.plotly_chart(
                trend_figure,
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
# PAGE: TRENDS (AGE VS GRADE SCATTER)
# ═════════════════════════════════════════════════════════════════════════════
elif page == "📈 Trends (Age vs Grade)":
    st.title("📈 Age vs Grade Analysis")

    if df.empty:
        st.stop()

    c1, c2 = st.columns(2)
    with c1:
        f_dept = st.multiselect("Filter by Department", sorted(df["Department"].dropna().unique()), key="sc_dept")
    with c2:
        f_pos = st.multiselect("Filter by Position", sorted(df["Staff Position"].dropna().unique()), key="sc_pos")

    fdf = df.copy()
    if f_dept:
        fdf = fdf[fdf["Department"].isin(f_dept)]
    if f_pos:
        fdf = fdf[fdf["Staff Position"].isin(f_pos)]

    scatter_df = an.scatter_age_vs_grade(fdf)

    if scatter_df.empty:
        st.warning("No data available for the selected filters.")
        st.stop()

    color_col = "Overall_avg" if "Overall_avg" in scatter_df.columns else None

    fig = px.scatter(
        scatter_df, x="Age", y="SG", color=color_col, hover_data=["Name", "Staff Position", "Department"],
        category_orders={"SG": sorted(df["SG"].dropna().unique())},
        color_continuous_scale="Tealgrn", title="Age vs Salary Grade (colored by Overall Avg Score)"
    )
    fig.update_layout(height=600)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Years in PET vs Overall Score")
    if "Years in PET" in fdf.columns and "Overall_avg" in fdf.columns:
        fig2 = px.scatter(fdf, x="Years in PET", y="Overall_avg", color="Staff Position",
                          hover_data=["Name"], trendline="ols")
        st.plotly_chart(fig2, use_container_width=True)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: ADMIN - IMPORT DATA
# ═════════════════════════════════════════════════════════════════════════════
elif page == "⚙️ Admin: Import Data":
    st.title("⚙️ Admin: Import Data from Excel")

    st.info("""
    Upload the RE Fraternity Master Excel file (the 'All' tab will be used).
    The importer reads:
    - Header row 3, data from row 4 onward
    - Personnel demographics & employment info
    - Competency scores (B1-B12, K1-K5, P1-P5, E1-E2) + targets (R-...) + gaps (G--...)
    - Summary scores (Staff/Principal/Custodian Base/Keys/Pacing/Emerging/CTI)

    **Re-importing updates existing records** (matched by Staff ID) and adds new assessments
    if the assessment date differs from any existing record.
    """)

    uploaded = st.file_uploader("Upload Excel file (.xlsx)", type=["xlsx"])

    if uploaded:
        tmp_path = None
        try:
            # Use NamedTemporaryFile for cross-platform temp file handling
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp.write(uploaded.getbuffer())
                tmp_path = tmp.name

            raw_df = load_master_data(tmp_path)
            ruler_map, tech_labels = load_ruler_and_tech_mapping(tmp_path)
            st.session_state["competency_names"] = tech_labels
            st.session_state["ruler_map"] = ruler_map
            st.session_state["competency_names"] = tech_labels
            st.session_state["ruler_source_file"] = uploaded.name

            st.success(f"✅ Loaded {len(raw_df)} personnel records from '{uploaded.name}'")
            st.info(f"Loaded {len(ruler_map)} ruler types from the workbook.")
            if tech_labels:
                st.info(f"Loaded {len(tech_labels)} competency full-name mappings from Tab Separator.")

            st.subheader("Preview (first 10 rows)")
            preview_cols = ["Name", "Staff ID", "Staff Position", "SG", "Department",
                            "Chat Status", "B1", "K1", "P1", "E1"]
            preview_cols = [c for c in preview_cols if c in raw_df.columns]
            st.dataframe(raw_df[preview_cols].head(10), use_container_width=True)

            if st.button("✅ Confirm Import to Database", type="primary"):
                session = get_session(engine)
                with st.spinner("Importing... this may take a minute for 200+ records"):
                    result = db_ops.bulk_import_from_df(session, raw_df, ruler_map=ruler_map)
                session.close()
                st.success(f"Import complete — Added: {result['added']}, "
                          f"Updated: {result['updated']}, Errors: {result['errors']}")
                bump_version()
                st.cache_data.clear()
                
            # Clean up temp file
            if tmp_path is not None and os.path.exists(tmp_path):
                os.remove(tmp_path)
                st.rerun()

        except Exception as e:
            st.error(f"❌ Error reading file: {e}")
            st.exception(e)
            # Clean up temp file on error
            if 'tmp_path' in locals() and tmp_path is not None and os.path.exists(tmp_path):
                os.remove(tmp_path)

    st.markdown("---")
    st.subheader("Current Database Status")
    session = get_session(engine)
    n_personnel = session.query(Personnel).filter_by(is_deleted=False).count()
    n_assessments = session.query(Assessment).count()
    session.close()
    c1, c2 = st.columns(2)
    c1.metric("Personnel Records", n_personnel)
    c2.metric("Assessment Records", n_assessments)

    if st.button("🗑️ Reset Database (delete all data)"):
        if st.session_state.get("confirm_reset"):
            from models import Base
            Base.metadata.drop_all(engine)
            Base.metadata.create_all(engine)
            bump_version()
            st.cache_data.clear()
            st.success("Database reset.")
            st.session_state.confirm_reset = False
            st.rerun()
        else:
            st.session_state.confirm_reset = True
            st.warning("Click again to confirm reset. This deletes ALL data permanently.")


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
            pid = int(row["id"])

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
            pid = int(row["id"])

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
    pid = int(row["id"])

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
