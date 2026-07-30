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
import config
import data_loader

from config import (
    APP_TITLE, DATABASE_URL, PRIMARY, SECONDARY,
    SCORE_COLS, REQ_COLS, GAP_COLS, COMP_TYPES,
    DEPARTMENTS, POSITIONS, CHAT_STATUS_OPTIONS, ASSESSMENT_LEVELS,
    GRADE_LABELS, HEATMAP_COLORSCALE, COMPETENCY_FULLNAMES,
    SUMMARY_GROUPS,
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
# 1. DATABASE & FILE PATH SETUP
# ─────────────────────────────────────────────────────────────────────────────
import data_loader
@st.cache_resource
def get_engine():
    return init_db(DATABASE_URL)

engine = get_engine()

if "data_version" not in st.session_state:
    st.session_state.data_version = 0

def bump_version():
    st.session_state.data_version += 1

# Excel Master Workbook Path
EXCEL_PATH = os.path.join(os.path.dirname(__file__), "C:\\Users\\mnabielizzuddin.radz\\competency-assessment-system\\RE Fraternity Jul2026_Master.xlsx")

# ─────────────────────────────────────────────────────────────────────────────
# 2. CACHED DATA LOADERS (USES YOUR DATA_LOADER.PY)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data
def load_wide_df(_version: int) -> pd.DataFrame:
    """Loads database personnel records (or falls back to Excel if DB empty)."""
    session = get_session(engine)
    try:
        df = db_ops.get_wide_dataframe(session)
    finally:
        session.close()
        
    if df is None or df.empty:
        # Fallback to loading directly from master Excel file via data_loader
        df = data_loader.load_master_data(EXCEL_PATH)
    else:
        df = an.add_category_averages(df)
        
    return df

@st.cache_data
def load_ruler_and_mappings():
    """Loads ruler requirements and tech competency labels from Excel."""
    return data_loader.load_ruler_and_tech_mapping(EXCEL_PATH)

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

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR NAVIGATION
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.title("📊 " + APP_TITLE)
page = st.sidebar.radio("Navigate", [
    "🏠 Dashboard Home",
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

# ═════════════════════════════════════════════════════════════════════════════
# PAGE: INDIVIDUAL ASSESSMENT
# ═════════════════════════════════════════════════════════════════════════════
elif page == "🔍 Individual Assessment":
    st.set_page_config(layout="wide")
    import streamlit as st
    import pandas as pd
    import numpy as np
    import plotly.graph_objects as go
    import plotly.express as px
    import os
    import re
    import analytics as an
    import db_ops as db_ops
    from models import get_session, init_db, Personnel, Assessment
    from data_loader import load_master_data, load_ruler_and_tech_mapping
    from datetime import datetime


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

    def export_to_pdf(person_row, target_sg, df_gap, metrics):
        """PDF Export stub preserving Code #2 UI pattern."""
        from io import BytesIO
        from reportlab.pdfgen import canvas
        pdf_buffer = BytesIO()
        c = canvas.Canvas(pdf_buffer)
        c.drawString(100, 750, f"Assessment Report: {person_row.get('Name', 'N/A')}")
        c.drawString(100, 730, f"Target Grade: {target_sg}")
        c.drawString(100, 710, f"Weighted Readiness: {metrics[1]:.1f}%")
        c.save()
        pdf_buffer.seek(0)
        return pdf_buffer

    # =========================================================================
    # PAGE SETUP (Code #2 Layout)
    # =========================================================================

    st.set_page_config(layout="wide", page_title="Individual Assessment")
    st.title("👤 Individual Assessment & Development Profile")
    st.markdown("---")

    

    # Personnel Selection (Code #2 Layout)
    if df.empty:
        st.error("No personnel data available.")
        st.stop()

    names = sorted(df["Name"].dropna().unique())
    col_select, col_refresh = st.columns([0.9, 0.1])

    with col_select:
        selected_name = st.selectbox("Select Personnel", names, key="personnel_select")
    with col_refresh:
        if st.button("🔄 Refresh"):
            st.rerun()

    person_row = df[df["Name"] == selected_name].iloc[0]

    # =========================================================================
    # SECTION 1: PERSONNEL PROFILE HEADER (Code #2 Card Style)
    # =========================================================================
    with st.container():
        st.markdown("### 📋 Personnel Profile")
        
        profile_col1, profile_col2, profile_col3, profile_col4 = st.columns(4)
        with profile_col1:
            st.metric("Position / Grade", f"{person_row.get('staff_position', 'N/A')} ({person_row.get('sg', 'N/A')})")
        with profile_col2:
            st.metric("Department", person_row.get("department", "N/A"))
        with profile_col3:
            st.metric("Current Assignment", person_row.get("current_assignment", "N/A"))
        with profile_col4:
            st.metric("Email", person_row.get("email", "N/A"))
            
        stats_col1, stats_col2, stats_col3, stats_col4 = st.columns(4)
        with stats_col1:
            st.metric("Age", int(person_row.get("age", 0)) if pd.notna(person_row.get("age")) else "N/A")
        with stats_col2:
            st.metric("Employment Type", person_row.get("employment_category", "N/A"))
        with stats_col3:
            st.metric("Contract Expiry", str(person_row.get("contract_expire_date", "N/A")))
        with stats_col4:
            st.metric("Length in Grade", "N/A") # Placeholder
    st.markdown("---")

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
    with st.expander("📚 Tech Class Reference", expanded=False):
        st.markdown("**Understanding Competency Codes**")
        st.markdown("B: Base | K: Key | P: Pacing | E: Emerging")
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

                fig_radar = go.Figure()
                # Actual Profile
                fig_radar.add_trace(
                    go.Scatterpolar(
                        r=radar_actual + [radar_actual[0]], theta=radar_names + [radar_names[0]], fill="toself", name="Actual", line=dict(color="#1f77b4", width=2, ),
                        fillcolor="rgba(31,119,180,0.30)"
                    )
                )
                # Target Profile (Dashed)
                fig_radar.add_trace(
                    go.Scatterpolar(
                        r=radar_target + [radar_target[0]],theta=radar_names + [radar_names[0]],fill="none", name=f"Target ({target_sg})", 
                        line=dict(color="red", width=2, dash="dash",),))
                fig_radar.update_layout(
                    title="Competency Profile", height=400, showlegend=True, polar=dict(
                        radialaxis=dict( visible=True, range=[0, 5],dtick=1,)),)
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

    with col_export:
        if target_sg and st.button("📥 Export as PDF", use_container_width=True):
            with st.spinner("Generating PDF..."):
                pdf = export_to_pdf(person_row, target_sg, df_gap, (strict_readiness, weighted_readiness))
                st.download_button(
                    label="⬇️ Download Report",
                    data=pdf,
                    file_name=f"Assessment_{selected_name}_{target_sg}.pdf",
                    mime="application/pdf"
                )
                st.success("Ready!")
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
        fig2 = px.scatter(
        fdf,
        x="Years in PET",
        y="Overall_avg",
        color="Staff Position",
        hover_data=["Name"],
        trendline=None,
    )
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
