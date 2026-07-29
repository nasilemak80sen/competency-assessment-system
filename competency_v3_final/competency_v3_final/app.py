"""
app.py – RE Fraternity Competency Assessment System v3.0
Run with: streamlit run app.py
"""

import os
import tempfile
from datetime import date, datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import (
    APP_TITLE, DATABASE_URL, PRIMARY, SECONDARY,
    SCORE_COLS, REQ_COLS, GAP_COLS, COMP_TYPES,
    DEPARTMENTS, POSITIONS, CHAT_STATUS_OPTIONS, ASSESSMENT_LEVELS,
    GRADE_LABELS, HEATMAP_COLORSCALE, SUMMARY_GROUPS,
)
from models import init_db, get_session, Personnel, Assessment
from data_loader import load_master_data
import db_ops
import analytics as an
from chart_builder import ChartBuilder, ChartCompatibility, DataElementInfo


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
# SIDEBAR NAVIGATION - SEPARATED USER vs ADMIN
# ─────────────────────────────────────────────────────────────────────────────
st.sidebar.title("📊 " + APP_TITLE)

# User Pages
user_pages = [
    "🏠 Dashboard Home",
    "👥 Personnel Directory",
    "🌡️ Competency Heatmap",
    "🔍 Individual Assessment",
    "🎯 Readiness & Gaps",
    "📊 Chart Builder",
]

# Admin Pages
admin_pages = [
    "⚙️ Admin: Import Data",
    "⚙️ Admin: Personnel CRUD",
    "⚙️ Admin: Assessment Entry",
]

# Combine pages into single selectbox
all_pages = user_pages + ["─────"] + admin_pages
page = st.sidebar.selectbox("SELECT PAGE", all_pages, key="page_select")

df = load_wide_df(st.session_state.data_version)

if df.empty and not page.startswith("⚙️ Admin: Import"):
    st.warning("⚠️ No data in database yet. Go to **Admin: Import Data** to load the Excel master file.")


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD HOME (EXPANDED with Age vs Grade + Length in Position)
# ═════════════════════════════════════════════════════════════════════════════
if page == "🏠 Dashboard Home":
    st.title("🏠 Dashboard Home")

    if df.empty:
        st.stop()

    session = get_session(engine)
    stats = db_ops.get_stats_overview(session)
    session.close()

    # Key Metrics Row
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
        st.plotly_chart(fig, use_container_width=True, key="chart_pos_dist")

    with col2:
        st.subheader("Department Distribution")
        dept = df["Department"].value_counts().reset_index()
        dept.columns = ["Department", "Count"]
        fig = px.pie(dept, names="Department", values="Count", hole=0.4,
                     color_discrete_sequence=px.colors.sequential.RdBu)
        st.plotly_chart(fig, use_container_width=True, key="chart_dept_dist")

    col3, col4 = st.columns(2)

    with col3:
        st.subheader("Chat Status Breakdown")
        cs = df["Chat Status"].fillna("No Need").value_counts().reset_index()
        cs.columns = ["Chat Status", "Count"]
        fig = px.bar(cs, x="Chat Status", y="Count", color="Chat Status",
                     color_discrete_map={"Yes": "#00a19c", "No": "#C62828", "No Need": "#763f98"})
        st.plotly_chart(fig, use_container_width=True, key="chart_chat_status")

    with col4:
        st.subheader("Assessment Completion by Department")
        comp = an.assessment_completion_by_dept(df)
        fig = px.bar(comp, x="Department", y="completion_pct", text="completion_pct",
                     color="completion_pct", color_continuous_scale="Viridis",
                     labels={"completion_pct": "Completion %"})
        fig.update_traces(texttemplate="%{text:.0f}%", textposition="outside")
        st.plotly_chart(fig, use_container_width=True, key="chart_completion")

    st.subheader("Grade (SG) Distribution")
    sg = df["SG"].value_counts().reset_index()
    sg.columns = ["SG", "Count"]
    sg["Label"] = sg["SG"].map(GRADE_LABELS).fillna(sg["SG"])
    fig = px.bar(sg.sort_values("SG"), x="SG", y="Count", text="Label",
                 color="Count", color_continuous_scale="Blues")
    st.plotly_chart(fig, use_container_width=True, key="chart_sg_dist")

    # ── NEW: Age vs Grade Analysis with Unit Name Filter ──────────────────────
    st.markdown("---")
    st.subheader("📈 Age vs Salary Grade Analysis")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        f_unit = st.multiselect("Filter by Unit Name", sorted(df["Unit Name"].dropna().unique()), key="dash_unit")
    with c2:
        f_dept = st.multiselect("Filter by Department", sorted(df["Department"].dropna().unique()), key="dash_dept")
    with c3:
        f_pos = st.multiselect("Filter by Position", sorted(df["Staff Position"].dropna().unique()), key="dash_pos")

    fdf = df.copy()
    if f_unit:
        fdf = fdf[fdf["Unit Name"].isin(f_unit)]
    if f_dept:
        fdf = fdf[fdf["Department"].isin(f_dept)]
    if f_pos:
        fdf = fdf[fdf["Staff Position"].isin(f_pos)]

    scatter_df = an.scatter_age_vs_grade(fdf)
    if not scatter_df.empty:
        color_col = "Overall_avg" if "Overall_avg" in scatter_df.columns else None
        fig = px.scatter(
            scatter_df, x="Age", y="SG", color=color_col,
            hover_data=["Name", "Staff Position", "Department", "Unit Name"],
            category_orders={"SG": sorted(df["SG"].dropna().unique())},
            color_continuous_scale="Tealgrn", title="Age vs Salary Grade (colored by Overall Avg Score)"
        )
        fig.update_layout(
            height=700,
            xaxis_title="Age (years)",
            yaxis_title="Salary Grade (SG)",
            xaxis_range=[20, 70],
            xaxis_dtick=5,
            margin=dict(l=100, r=100, t=120, b=100),
            font=dict(size=12, family="Arial"),
            title_font_size=18,
            hovermode="closest",
            plot_bgcolor="rgba(232, 248, 247, 0.8)",
            xaxis=dict(showgrid=True, gridwidth=1, gridcolor="rgba(221, 221, 221, 0.8)"),
            yaxis=dict(showgrid=True, gridwidth=1, gridcolor="rgba(221, 221, 221, 0.8)"),
        )
        fig.update_traces(marker=dict(size=9, opacity=0.7, line=dict(width=1, color="white")))
        st.plotly_chart(fig, use_container_width=True, key="chart_age_vs_grade")
    else:
        st.info("No data available for selected filters.")

    # ── NEW: Length in Position vs Age (TPCP Assessment Status) ──────────────
    st.markdown("---")
    st.subheader("⏰ Length in Position vs Age (TPCP Assessment Status)")
    st.caption("This shows how long personnel have been in their current position relative to age. Helps identify who hasn't undergone TPCP assessment.")

    # Apply same filters as Age vs Grade section
    c1, c2, c3 = st.columns(3)
    with c1:
        f_unit_len = st.multiselect("Filter by Unit Name", sorted(df["Unit Name"].dropna().unique()), key="len_unit")
    with c2:
        f_dept_len = st.multiselect("Filter by Department", sorted(df["Department"].dropna().unique()), key="len_dept")
    with c3:
        f_pos_len = st.multiselect("Filter by Position", sorted(df["Staff Position"].dropna().unique()), key="len_pos")

    if "assignment_length" in df.columns and "Age" in df.columns:
        assess_df = df[["Name", "Age", "assignment_length", "Staff Position", "Department", "Unit Name", "Chat Status"]].copy()
        
        # Apply filters
        if f_unit_len:
            assess_df = assess_df[assess_df["Unit Name"].isin(f_unit_len)]
        if f_dept_len:
            assess_df = assess_df[assess_df["Department"].isin(f_dept_len)]
        if f_pos_len:
            assess_df = assess_df[assess_df["Staff Position"].isin(f_pos_len)]
        
        assess_df = assess_df.dropna(subset=["Age", "assignment_length"])
        if not assess_df.empty:
            # Convert decimal years to "X year(s) Y month(s)" format for hover display
            def format_years(decimal_years):
                years = int(decimal_years)
                months = int((decimal_years - years) * 12)
                if months == 0:
                    return f"{years} year{'s' if years != 1 else ''}"
                else:
                    return f"{years} year{'s' if years != 1 else ''} {months} month{'s' if months != 1 else ''}"
            
            assess_df["assignment_length_formatted"] = assess_df["assignment_length"].apply(format_years)
            
            fig = px.scatter(
                assess_df, x="Age", y="assignment_length",
                color="Chat Status",
                hover_data={"Age": True, "assignment_length": ":.1f", "assignment_length_formatted": True, "Name": True, "Staff Position": True, "Department": True},
                color_discrete_map={"Yes": "#00a19c", "No": "#C62828", "No Need": "#763f98"},
                title="Length in Current Assignment vs Age (TPCP Assessment Readiness)"
            )
            fig.add_hline(y=assess_df["assignment_length"].median(), line_dash="dash",
                         annotation_text=f"Median: {format_years(assess_df['assignment_length'].median())}", annotation_position="right")
            fig.update_layout(
                height=700,
                xaxis_title="Age (years)",
                yaxis_title="Length in Current Assignment (years)",
                legend_title="Chat Status",
                xaxis_range=[20, 70],
                yaxis_range=[-1, 10],
                xaxis_dtick=5,
                yaxis_dtick=1,
                margin=dict(l=100, r=100, t=120, b=100),
                font=dict(size=12, family="Arial"),
                title_font_size=18,
                hovermode="closest",
                plot_bgcolor="rgba(232, 248, 247, 0.8)",
                xaxis=dict(showgrid=True, gridwidth=1, gridcolor="rgba(221, 221, 221, 0.8)"),
                yaxis=dict(showgrid=True, gridwidth=1, gridcolor="rgba(221, 221, 221, 0.8)"),
            )
            fig.update_traces(marker=dict(size=9, opacity=0.7, line=dict(width=1, color="white")))
            st.plotly_chart(fig, use_container_width=True, key="chart_length_vs_age")
        else:
            st.info("No data available.")
    else:
        st.info("Assignment length data not available.")


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: PERSONNEL DIRECTORY
# ═════════════════════════════════════════════════════════════════════════════
elif page == "👥 Personnel Directory":
    st.title("👥 Personnel Directory")

    if df.empty:
        st.stop()

    c1, c2, c3 = st.columns(3)
    with c1:
        f_dept = st.multiselect("Department", sorted(df["Department"].dropna().unique()), key="pd_dept")
    with c2:
        f_pos = st.multiselect("Position", sorted(df["Staff Position"].dropna().unique()), key="pd_pos")
    with c3:
        f_chat = st.multiselect("Chat Status", CHAT_STATUS_OPTIONS, key="pd_chat")

    search = st.text_input("🔎 Search by Name or Staff ID", key="pd_search")

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
                    "Unit Name", "Age", "Chat Status", "Overall_avg"]
    display_cols = [c for c in display_cols if c in fdf.columns]
    show = fdf[display_cols].rename(columns={"Overall_avg": "Avg Score"})
    if "Avg Score" in show.columns:
        show["Avg Score"] = show["Avg Score"].round(2)
    st.dataframe(show, use_container_width=True, hide_index=True)

    # CSV export
    csv = show.to_csv(index=False).encode()
    st.download_button("⬇️ Download as CSV", csv, "personnel_directory.csv", "text/csv")


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: COMPETENCY HEATMAP (WITH SEARCH)
# ═════════════════════════════════════════════════════════════════════════════
elif page == "🌡️ Competency Heatmap":
    st.title("🌡️ Competency Heatmap")

    if df.empty:
        st.stop()

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        f_dept = st.multiselect("Department", sorted(df["Department"].dropna().unique()), key="hm_dept")
    with c2:
        f_pos = st.multiselect("Position", sorted(df["Staff Position"].dropna().unique()), key="hm_pos")
    with c3:
        f_type = st.multiselect("Competency Type", list(COMP_TYPES.keys()),
                                default=list(COMP_TYPES.keys()), key="hm_type")
    with c4:
        search = st.text_input("🔎 Search Name/ID", key="hm_search")

    fdf = df.copy()
    if f_dept:
        fdf = fdf[fdf["Department"].isin(f_dept)]
    if f_pos:
        fdf = fdf[fdf["Staff Position"].isin(f_pos)]
    if search:
        mask = fdf["Name"].str.contains(search, case=False, na=False) | \
               fdf["Staff ID"].astype(str).str.contains(search, case=False, na=False)
        fdf = fdf[mask]

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
    st.plotly_chart(fig, use_container_width=True, key="chart_heatmap")

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
# PAGE: INDIVIDUAL ASSESSMENT (EXPANDED with Competency Type Breakdown)
# ═════════════════════════════════════════════════════════════════════════════
elif page == "🔍 Individual Assessment":
    st.title("🔍 Individual Assessment")

    if df.empty:
        st.stop()

    # Combined search + selectbox approach
    search = st.text_input("🔎 Search by Name or Staff ID", key="ia_search")
    
    # Filter personnel based on search
    if search:
        mask = df["Name"].str.contains(search, case=False, na=False) | \
               df["Staff ID"].astype(str).str.contains(search, case=False, na=False)
        filtered_df = df[mask]
    else:
        filtered_df = df

    # Get filtered names for selectbox
    filtered_names = sorted(filtered_df["Name"].dropna().unique())
    
    # Show count of matches
    if search:
        st.caption(f"📌 Found {len(filtered_names)} matching personnel")
    
    # Selectbox with filtered options
    if filtered_names:
        selected = st.selectbox(
            "Select Personnel", 
            options=filtered_names,
            key="personnel_select"
        )
    else:
        st.warning("❌ No personnel match your search.")
        st.stop()

    # Get the selected person from ORIGINAL df (not filtered)
    person_row = df[df["Name"] == selected].iloc[0]

    # Display metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Position / Grade", f"{person_row.get('Staff Position')} ({person_row.get('SG')})")
    with c2:
        st.metric("Department", person_row.get("Department"))
    with c3:
        st.metric("Age", int(person_row["Age"]) if pd.notna(person_row.get("Age")) else "N/A")
    with c4:
        st.metric("Unit Name", person_row.get("Unit Name", "N/A"))

    st.markdown("---")

    gap_df = an.gap_analysis_individual(person_row)

    if gap_df.empty:
        st.info("No assessment scores recorded yet for this person.")
    else:
        col1, col2 = st.columns([1, 1])

        with col1:
            st.subheader("Actual vs Target")
            fig = go.Figure()
            fig.add_trace(go.Bar(x=gap_df["Competency"], y=gap_df["Actual"], name="Actual",
                                 marker_color=SECONDARY))
            fig.add_trace(go.Scatter(x=gap_df["Competency"], y=gap_df["Target"], name="Target",
                                     mode="markers", marker=dict(color="red", size=8, symbol="diamond")))
            fig.update_layout(yaxis_range=[0, 5], height=400)
            st.plotly_chart(fig, use_container_width=True, key="chart_ia_actual_vs_target")

        with col2:
            st.subheader("Category Radar")
            cat_vals = []
            cat_names = []
            for ctype, info in COMP_TYPES.items():
                avg_col = f"{ctype}_avg"
                if avg_col in person_row.index and pd.notna(person_row[avg_col]):
                    cat_vals.append(person_row[avg_col])
                    cat_names.append(info["label"])
            if cat_vals:
                fig2 = go.Figure(data=go.Scatterpolar(
                    r=cat_vals + [cat_vals[0]],
                    theta=cat_names + [cat_names[0]],
                    fill="toself", line_color=PRIMARY
                ))
                fig2.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 5])),
                                  height=400, showlegend=False)
                st.plotly_chart(fig2, use_container_width=True, key="chart_ia_radar")

        # ── NEW: Summary Scores & CTI Section ──────────────────────────────
        st.markdown("---")
        st.subheader("📈 Summary Scores & CTI Performance")
        
        summary_metrics = []
        for role, cols in SUMMARY_GROUPS.items():
            for col in cols:
                if col in person_row.index and pd.notna(person_row[col]):
                    score = person_row[col]
                    summary_metrics.append({"Role": role, "Category": col, "Score": score})
        
        if summary_metrics:
            summary_df = pd.DataFrame(summary_metrics)
            
            # Create columns for summary display
            for role in summary_df["Role"].unique():
                with st.expander(f"🎯 {role} Summary Scores", expanded=True):
                    role_df = summary_df[summary_df["Role"] == role].copy()
                    role_df["Score"] = role_df["Score"].round(2)
                    
                    # Display in grid format
                    cols_grid = st.columns(5)
                    for idx, (_, row) in enumerate(role_df.iterrows()):
                        with cols_grid[idx % 5]:
                            cat_name = row["Category"].replace(f"{role} ", "")
                            score_val = row["Score"]
                            
                            # Color code based on score
                            if score_val >= 4:
                                color = "🟢"
                            elif score_val >= 3:
                                color = "🟡"
                            else:
                                color = "🔴"
                            
                            st.metric(f"{color} {cat_name}", f"{score_val:.2f}")
        else:
            st.info("No summary scores recorded yet.")

        st.subheader("Gap Analysis Detail")
        def _color_status(val):
            colors = {"Met": "background-color:#C8E6C9; color:#1B5E20; font-weight:bold",
        "Minor Gap": "background-color:#FFF9C4; color:#F57F17; font-weight:bold",
        "Major Gap": "background-color:#FFCDD2; color:#B71C1C; font-weight:bold"}
            return colors.get(val, "")
        styled = gap_df.style.map(_color_status, subset=["Status"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

        # Gap counts
        n_met = (gap_df["Status"] == "Met").sum()
        n_minor = (gap_df["Status"] == "Minor Gap").sum()
        n_major = (gap_df["Status"] == "Major Gap").sum()
        g1, g2, g3 = st.columns(3)
        g1.metric("✅ Met Target", int(n_met))
        g2.metric("🟡 Minor Gaps", int(n_minor))
        g3.metric("🔴 Major Gaps", int(n_major))

        # ── NEW: Competency Type Breakdown ──────────────────────────────────
        st.markdown("---")
        st.subheader("📊 Competency Type Breakdown (B, K, P, E)")
        
        comp_type_tabs = st.tabs([f"{t} - {COMP_TYPES[t]['label']}" for t in COMP_TYPES.keys()])
        
        for tab_idx, (ctype, info) in enumerate(COMP_TYPES.items()):
            with comp_type_tabs[tab_idx]:
                type_df = gap_df[gap_df["Type"] == ctype].copy()
                
                if type_df.empty:
                    st.info(f"No {ctype} competencies recorded.")
                else:
                    # Metrics for this type
                    type_met = (type_df["Status"] == "Met").sum()
                    type_minor = (type_df["Status"] == "Minor Gap").sum()
                    type_major = (type_df["Status"] == "Major Gap").sum()
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        avg_actual = type_df["Actual"].mean()
                        st.metric(f"Avg Actual", f"{avg_actual:.2f}" if pd.notna(avg_actual) else "N/A")
                    with col2:
                        avg_target = type_df["Target"].mean()
                        st.metric(f"Avg Target", f"{avg_target:.2f}" if pd.notna(avg_target) else "N/A")
                    with col3:
                        readiness_pct = (type_met / len(type_df) * 100) if len(type_df) > 0 else 0
                        st.metric("Readiness %", f"{readiness_pct:.0f}%")
                    with col4:
                        ready = "✅ Ready" if readiness_pct >= 80 else "⚠️ Not Ready"
                        st.metric("Status", ready)
                    
                    # Chart for this competency type
                    fig_type = go.Figure()
                    fig_type.add_trace(go.Bar(x=type_df["Competency"], y=type_df["Actual"], name="Actual",
                                             marker_color=SECONDARY))
                    fig_type.add_trace(go.Scatter(x=type_df["Competency"], y=type_df["Target"], name="Target",
                                                 mode="markers", marker=dict(color="red", size=8, symbol="diamond")))
                    fig_type.update_layout(yaxis_range=[0, 5], height=350, title=f"{ctype} Competency Details")
                    st.plotly_chart(fig_type, use_container_width=True, key=f"chart_ia_type_{ctype}")
                    
                    # Table for this type
                    st.dataframe(type_df, use_container_width=True, hide_index=True)

    # ── Trend history ───────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Assessment History / Trend")
    session = get_session(engine)
    pid = int(person_row["id"])
    hist = db_ops.get_assessment_history(session, pid)
    session.close()

    if hist.empty:
        st.info("No historical assessment trend data available (only one assessment on record).")
    else:
        trend = hist.groupby(["date", "competency_type"])["actual_score"].mean().reset_index()
        fig3 = px.line(trend, x="date", y="actual_score", color="competency_type",
                       markers=True, labels={"actual_score": "Avg Score", "date": "Assessment Date"})
        st.plotly_chart(fig3, use_container_width=True, key="chart_ia_trend")

    # ── NEW: Professional Profile Database Section ──────────────────────────
    st.markdown("---")
    st.subheader("👤 Employee Profile Database")
    
    profile_data = {
        "💪 Strengths": person_row.get("Strength", "Not recorded"),
        "🎯 Potential": person_row.get("Potential", "Not recorded"),
        "📋 Sub-Disciplines": person_row.get("Sub-Disciplines", "Not recorded"),
        "👨‍💼 Resource/SME": person_row.get("Resource/SME", "Not recorded"),
        "❤️ Interest": person_row.get("Interest", "Not recorded"),
        "🔄 Preference": person_row.get("Preference", "Not recorded"),
    }
    
    # Create expandable cards for profile information
    prof_col1, prof_col2 = st.columns(2)
    
    with prof_col1:
        with st.expander("💪 Strengths & Potential", expanded=True):
            st.write("**Strengths:**")
            strengths = person_row.get("Strength", "Not recorded")
            if pd.notna(strengths) and strengths:
                st.info(strengths)
            else:
                st.write("_No strengths recorded_")
            
            st.write("**Potential:**")
            potential = person_row.get("Potential", "Not recorded")
            if pd.notna(potential) and potential:
                st.info(potential)
            else:
                st.write("_No potential recorded_")
    
    with prof_col2:
        with st.expander("📚 Specialization & Interest", expanded=True):
            st.write("**Sub-Disciplines:**")
            sub_disc = person_row.get("Sub-Disciplines", "Not recorded")
            if pd.notna(sub_disc) and sub_disc:
                st.success(sub_disc)
            else:
                st.write("_No sub-disciplines recorded_")
            
            st.write("**Interest Areas:**")
            interest = person_row.get("Interest", "Not recorded")
            if pd.notna(interest) and interest:
                st.success(interest)
            else:
                st.write("_No interests recorded_")
    
    # Recommendations and Suggestions
    st.markdown("---")
    
    rec_col1, rec_col2 = st.columns(2)
    
    with rec_col1:
        with st.expander("📌 Recommendations", expanded=True):
            recommendation = person_row.get("Recommendation", "Not recorded")
            if pd.notna(recommendation) and recommendation:
                st.warning(recommendation)
            else:
                st.write("_No recommendations recorded_")
    
    with rec_col2:
        with st.expander("💬 Comments & Suggestions", expanded=True):
            suggestion = person_row.get("Comment/Suggestion", "Not recorded")
            if pd.notna(suggestion) and suggestion:
                st.warning(suggestion)
            else:
                st.write("_No comments or suggestions recorded_")
    
    # Resource and Preference Summary
    st.markdown("---")
    with st.expander("🔧 Resource & Preference Summary", expanded=False):
        res_col1, res_col2 = st.columns(2)
        
        with res_col1:
            st.write("**Resource/SME Status:**")
            resource = person_row.get("Resource/SME", "Not recorded")
            if pd.notna(resource) and resource:
                st.info(f"ℹ️ {resource}")
            else:
                st.write("_Not classified_")
        
        with res_col2:
            st.write("**Career Preference:**")
            preference = person_row.get("Preference", "Not recorded")
            if pd.notna(preference) and preference:
                st.info(f"📍 {preference}")
            else:
                st.write("_Not specified_")
    
    # Assessment Metadata
    st.markdown("---")
    st.subheader("📋 Assessment Metadata")
    
    meta_cols = st.columns(3)
    with meta_cols[0]:
        st.metric("Last Assessment", person_row.get("Last Assesment Date", "N/A"))
    with meta_cols[1]:
        st.metric("Assessment Level", person_row.get("Assessment Level", "N/A"))
    with meta_cols[2]:
        st.metric("Chat Status", person_row.get("Chat Status", "N/A"))


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: READINESS & GAPS (WITH SEARCH)
# ═════════════════════════════════════════════════════════════════════════════
elif page == "🎯 Readiness & Gaps":
    st.title("🎯 Readiness & Gaps Analysis")

    if df.empty:
        st.stop()

    # Search and filters
    c1, c2 = st.columns(2)
    with c1:
        search = st.text_input("🔎 Search by Name or Staff ID", key="rg_search")
    with c2:
        f_dept = st.multiselect("Filter by Department", sorted(df["Department"].dropna().unique()), key="rg_dept")

    fdf = df.copy()
    if f_dept:
        fdf = fdf[fdf["Department"].isin(f_dept)]
    if search:
        mask = fdf["Name"].str.contains(search, case=False, na=False) | \
               fdf["Staff ID"].astype(str).str.contains(search, case=False, na=False)
        fdf = fdf[mask]

    tab1, tab2 = st.tabs(["Readiness Tiers", "Gap Status"])

    with tab1:
        ready_df = an.readiness_table(fdf)

        c1, c2, c3, c4 = st.columns(4)
        for col, tier in zip([c1, c2, c3, c4],
                             ["Tier 1 (<50%)", "Tier 2 (50-80%)", "Tier 3 (80-99%)", "Tier 4 (≥100%)"]):
            col.metric(tier, int((ready_df["Readiness Tier"] == tier).sum()))

        st.markdown("---")

        fig = px.histogram(ready_df.dropna(subset=["Achievement %"]),
                           x="SG", color="Readiness Tier", barmode="stack",
                           category_orders={"SG": sorted(ready_df["SG"].dropna().unique())},
                           color_discrete_sequence=px.colors.sequential.Viridis)
        fig.update_layout(title="Readiness Tier by Grade (SG)")
        st.plotly_chart(fig, use_container_width=True, key="chart_rg_readiness_tier")

        st.subheader("Personnel Ready for Next Assessment")
        ready_only = ready_df[ready_df["Ready for Assessment"] == "Ready"]
        st.dataframe(ready_only.sort_values("Achievement %", ascending=False),
                     use_container_width=True, hide_index=True)

        st.subheader("Full Readiness Table")
        st.dataframe(ready_df, use_container_width=True, hide_index=True)

    with tab2:
        gap_df = an.gap_summary(fdf)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("No Gap", int((gap_df["Gap Status"] == "No Gap").sum()))
        c2.metric("1 Gap", int((gap_df["Gap Status"] == "1 Gap").sum()))
        c3.metric(">1 Gap", int((gap_df["Gap Status"] == ">1 Gap").sum()))
        c4.metric("Not Assessed", int((gap_df["Gap Status"] == "Not Assessed").sum()))

        fig = px.pie(gap_df, names="Gap Status", hole=0.4,
                     color="Gap Status",
                     color_discrete_map={"No Gap": "#2E7D32", "1 Gap": "#FDD835",
                                        ">1 Gap": "#C62828", "Not Assessed": "#9E9E9E"})
        st.plotly_chart(fig, use_container_width=True, key="chart_rg_gap_pie")

        st.dataframe(gap_df, use_container_width=True, hide_index=True)


# ═════════════════════════════════════════════════════════════════════════════
# PAGE: CHART BUILDER - DYNAMIC CHART CREATION WITH DATA ELEMENT SELECTION
# ═════════════════════════════════════════════════════════════════════════════
elif page == "📊 Chart Builder":
    st.title("📊 Dynamic Chart Builder")
    
    st.markdown("""
    Create custom charts by selecting data elements from your dataset.
    The system will:
    - Analyze data types automatically
    - Recommend compatible chart types
    - Show warnings if data elements aren't suitable for analysis
    - Apply filters to focus on specific data subsets
    """)
    
    if df.empty:
        st.stop()
    
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
    
    selected_chart = None
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
            st.markdown("---")
            st.subheader("📋 Data Summary")
            
            summary_cols = st.columns(4)
            
            with summary_cols[0]:
                st.metric("Records Displayed", len(working_df))
            
            with summary_cols[1]:
                st.metric("X-Axis Unique Values", x_info.unique_count)
            
            if y_info:
                with summary_cols[2]:
                    st.metric("Y-Axis Unique Values", y_info.unique_count)
                with summary_cols[3]:
                    st.metric("Complete Pairs", len(working_df[[x_element, st.session_state.cb_y_element]].dropna()))
            else:
                with summary_cols[2]:
                    st.metric("Non-null Values", len(working_df[x_element].dropna()))
            
        except Exception as e:
            st.error(f"❌ Error generating chart: {str(e)}")
            st.exception(e)
    else:
        st.info("👈 Select a chart type above to generate your visualization")


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
        try:
            # Use NamedTemporaryFile for cross-platform temp file handling
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp.write(uploaded.getbuffer())
                tmp_path = tmp.name

            raw_df = load_master_data(tmp_path)
            st.success(f"✅ Loaded {len(raw_df)} personnel records from '{uploaded.name}'")

            st.subheader("Preview (first 10 rows)")
            preview_cols = ["Name", "Staff ID", "Staff Position", "SG", "Department",
                            "Chat Status", "B1", "K1", "P1", "E1"]
            preview_cols = [c for c in preview_cols if c in raw_df.columns]
            st.dataframe(raw_df[preview_cols].head(10), use_container_width=True)

            if st.button("✅ Confirm Import to Database", type="primary"):
                session = get_session(engine)
                with st.spinner("Importing... this may take a minute for 200+ records"):
                    result = db_ops.bulk_import_from_df(session, raw_df)
                session.close()
                st.success(f"Import complete — Added: {result['added']}, "
                          f"Updated: {result['updated']}, Errors: {result['errors']}")
                bump_version()
                st.cache_data.clear()
                st.rerun()

        except Exception as e:
            st.error(f"❌ Error reading file: {e}")
            st.exception(e)

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
                    score_inputs[code] = {"actual": actual, "req": req, "gap": round(actual - req, 2)}

        submitted = st.form_submit_button("💾 Save Assessment", type="primary")

        if submitted:
            session = get_session(engine)
            ok, msg, aid = db_ops.add_assessment(session, pid, {
                "assessment_date": adate, "assessment_level": level,
                "assessor1": assessor1, "supervisor": supervisor,
            })
            if ok:
                if aid is None:
                    session.close()
                    st.error("Failed to create assessment (no id returned)")
                else:
                    ok2, msg2 = db_ops.add_competency_scores(session, int(aid), pid, score_inputs)
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