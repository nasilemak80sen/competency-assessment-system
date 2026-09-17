"""Personnel-scoped assessment workspace for USER accounts.

This page borrows the relevant capabilities from the Admin Individual Assessment
page while keeping every view and calculation scoped to the authenticated user.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analytics.readiness import (
    _rg_determine_target_sg,
    _rg_get_person_ruler,
    _rg_sort_salary_grades,
    build_target_gap_dataframe,
    calculate_readiness_metrics,
)
from components.competency_charts import render_actual_target_charts
from components.navigation import render_header, render_navigation
from config import COMPETENCY_FULLNAMES, COMP_TYPES
from core.auth import ROLE_USER, current_user, personnel_id, require_roles
from core.bootstrap import get_master_data, get_ruler_data, open_session
from models import Personnel, SummaryScore


require_roles(ROLE_USER)
render_navigation()
user = current_user()
render_header(
    "👤 My Assessment",
    "Your readiness, competency gaps, targets, strengths and assessment history",
)


def _text(value, fallback="Not Available"):
    if value is None:
        return fallback
    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return text if text and text.lower() not in {"nan", "none", "nat"} else fallback


def _date(value, fallback="Not Available"):
    parsed = pd.to_datetime(value, errors="coerce")
    return fallback if pd.isna(parsed) else parsed.strftime("%d %b %Y")


def _strength_frame(person, competency_type):
    records = []
    for code in COMP_TYPES.get(competency_type, {}).get("cols", []):
        score = pd.to_numeric(person.get(code), errors="coerce")
        if pd.notna(score):
            target = pd.to_numeric(person.get(f"R-{code}"), errors="coerce")
            records.append(
                {
                    "Code": code,
                    "Competency": COMPETENCY_FULLNAMES.get(code, code),
                    "Score": float(score),
                    "Target": float(target) if pd.notna(target) else pd.NA,
                }
            )

    if not records:
        return pd.DataFrame(
            columns=["Rank", "Code", "Competency", "Score", "Target", "Gap", "Status"]
        )

    frame = pd.DataFrame(records)
    frame["Gap"] = frame["Score"] - frame["Target"]
    frame["Status"] = frame["Gap"].apply(
        lambda gap: (
            "Target unavailable"
            if pd.isna(gap)
            else "Above Target"
            if gap > 0
            else "Target Met"
            if gap == 0
            else "Gap Remaining"
        )
    )
    frame = frame.sort_values(["Score", "Competency"], ascending=[False, True]).reset_index(drop=True)
    frame.insert(0, "Rank", range(1, len(frame) + 1))
    return frame


def _render_strength_section(person):
    st.subheader("💪 Competency Strengths")
    st.caption("Your strongest assessed competencies within each competency class.")
    tabs = st.tabs(["🟢 Base", "🔵 Key", "🟠 Pace", "🟣 Emerging"])

    for tab, code in zip(tabs, ["B", "K", "P", "E"]):
        with tab:
            class_config = COMP_TYPES.get(code, {})
            class_label = class_config.get("label", code)
            strength_df = _strength_frame(person, code)
            if strength_df.empty:
                st.info(f"No assessed {class_label.lower()} competencies are available.")
                continue

            top3 = strength_df.head(3)
            cards = st.columns(len(top3))
            medals = ["🥇", "🥈", "🥉"]
            for index, (_, row) in enumerate(top3.iterrows()):
                with cards[index]:
                    st.markdown(f"### {medals[index]}")
                    st.markdown(f"**{row['Competency']}**")
                    st.metric("Score", f"{row['Score']:.1f}/5")
                    if pd.notna(row["Target"]):
                        st.caption(f"Target: **{float(row['Target']):.1f}**")
                    else:
                        st.caption("Target: **Not available**")
                    if row["Status"] == "Above Target":
                        st.success(f"+{row['Gap']:.1f} above target")
                    elif row["Status"] == "Target Met":
                        st.success("Target met")
                    elif row["Status"] == "Gap Remaining":
                        st.warning(f"{abs(row['Gap']):.1f} below target")
                    else:
                        st.info("Target unavailable")

            with st.expander(f"📋 Full {class_label} ranking"):
                st.dataframe(
                    strength_df,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Score": st.column_config.NumberColumn("Score", format="%.1f"),
                        "Target": st.column_config.NumberColumn("Target", format="%.1f"),
                        "Gap": st.column_config.NumberColumn("Gap", format="%.1f"),
                    },
                )


linked_id = personnel_id()
if linked_id is None:
    st.error("Your account is not linked to a personnel record.")
    st.stop()

session = open_session()
try:
    person_db = (
        session.query(Personnel)
        .filter(Personnel.id == linked_id, Personnel.is_deleted.is_(False))
        .first()
    )
finally:
    session.close()

if person_db is None:
    st.error("Your linked personnel record could not be found or is inactive.")
    st.stop()

df = get_master_data()
ruler_map, _tech_labels = get_ruler_data()

if df is None or df.empty or "Staff ID" not in df.columns:
    st.warning("The master dataset is not available for your personnel record.")
    st.stop()

staff_id = str(person_db.staff_id).strip()
mine = df[df["Staff ID"].astype(str).str.strip() == staff_id].copy()
if mine.empty:
    st.error(
        f"Your personnel record ({person_db.name} · {staff_id}) is not present "
        "in the current master dataset."
    )
    st.stop()

person = mine.iloc[0]

st.caption(f"Signed in as **{user.get('display_name') or user.get('username')}**")
st.subheader(f"{person_db.name or person.get('Name')}")
st.caption(
    f"{person.get('Staff Position', 'N/A')} · {person.get('SG', 'N/A')} · "
    f"{person.get('Department', 'N/A')} · Staff ID: {staff_id}"
)

assessment_records = []
for ctype, info in COMP_TYPES.items():
    for code in info.get("cols", []):
        actual = pd.to_numeric(person.get(code), errors="coerce")
        stored_target = pd.to_numeric(person.get(f"R-{code}"), errors="coerce")
        assessment_records.append(
            {
                "Type": info.get("label", ctype),
                "Code": code,
                "Competency": COMPETENCY_FULLNAMES.get(code, code),
                "Actual": actual,
                "Stored Target": stored_target,
            }
        )
assessment_df = pd.DataFrame(assessment_records)
assessment_df["Gap"] = assessment_df["Stored Target"] - assessment_df["Actual"]

assessed = assessment_df["Actual"].notna()
coverage = float(assessed.mean() * 100) if len(assessment_df) else 0.0
average_score = float(assessment_df.loc[assessed, "Actual"].mean()) if assessed.any() else 0.0
stored_gap_count = int(((assessment_df["Gap"] > 0) & assessed).sum())

session = open_session()
history = []
summary = None
try:
    summary = (
        session.query(SummaryScore)
        .filter(SummaryScore.personnel_id == linked_id)
        .order_by(SummaryScore.updated_at.desc())
        .first()
    )
    db_person = session.query(Personnel).filter(Personnel.id == linked_id).first()
    if db_person:
        for assessment in sorted(
            db_person.assessments,
            key=lambda value: value.assessment_date or datetime.min,
        ):
            for score in assessment.scores:
                history.append(
                    {
                        "date": assessment.assessment_date,
                        "type": score.competency_type,
                        "code": score.competency_code,
                        "actual": score.actual_score,
                        "requirement": score.requirement_score,
                        "gap": score.gap_score,
                    }
                )
finally:
    session.close()

history_dates = [item["date"] for item in history if item.get("date")]
metadata_last_assessment = person_db.last_assessment_date or person.get("Last Assesment Date") or person.get("Last Assessment Date")
metadata_last_assessment = pd.to_datetime(metadata_last_assessment, errors="coerce")
all_assessment_dates = [date for date in history_dates if date is not None]
if pd.notna(metadata_last_assessment):
    all_assessment_dates.append(metadata_last_assessment.date() if hasattr(metadata_last_assessment, "date") else metadata_last_assessment)
last_assessment = max(all_assessment_dates) if all_assessment_dates else None

metric_cols = st.columns(5)
metric_cols[0].metric("Assessment Coverage", f"{coverage:.0f}%")
metric_cols[1].metric("Average Score", f"{average_score:.2f}/5")
metric_cols[2].metric("Stored Target Gaps", stored_gap_count)
metric_cols[3].metric("Last Assessment", _date(last_assessment))
metric_cols[4].metric(
    "Assessment Level",
    _text(person_db.assessment_level or person.get("Assessment Level")),
)

st.markdown("---")
st.subheader("📌 My Assessment Context")
context_cols = st.columns(4)
context_cols[0].info(f"**Potential**\n\n{_text(person_db.potential or person.get('Potential'))}")
context_cols[1].info(f"**Recommendation**\n\n{_text(person_db.recommendation or person.get('Recommendation'))}")
context_cols[2].info(f"**Supervisor**\n\n{_text(person_db.supervisor or person.get('Supervisor'))}")
context_cols[3].info(f"**Sub-Disciplines**\n\n{_text(person_db.sub_disciplines or person.get('Sub-Disciplines'))}")

st.markdown("---")
st.subheader("🎯 Career Target & Readiness")
rulers = list(ruler_map.keys())
personal_ruler = _rg_get_person_ruler(person, ruler_map) if rulers else None

target_cols = st.columns([1.3, 1.4, 1])
with target_cols[0]:
    ruler = (
        st.selectbox(
            "Career Ruler",
            rulers,
            index=rulers.index(personal_ruler) if personal_ruler in rulers else 0,
            key="user_target_ruler",
        )
        if rulers
        else None
    )

requirements = ruler_map.get(ruler, {}) if ruler else {}
grades = _rg_sort_salary_grades(requirements.keys())

with target_cols[1]:
    mode = st.selectbox(
        "Target Requirement",
        ["Next salary grade", "Current requirement", "Selected target grade"],
        key="user_target_mode",
    )

with target_cols[2]:
    target = (
        st.selectbox("Selected Target SG", grades, key="user_target_sg")
        if mode == "Selected target grade" and grades
        else _rg_determine_target_sg(person.get("SG"), requirements, mode)
    )
    st.caption(f"Target SG: **{target or 'Not available'}**")

gap_df = (
    build_target_gap_dataframe(
        person,
        requirements.get(target, {}),
        person.get("SG"),
        target,
        person.get("Staff Position"),
        ruler,
        COMPETENCY_FULLNAMES,
    )
    if target in requirements
    else pd.DataFrame()
)
metrics = calculate_readiness_metrics(gap_df)

if gap_df.empty:
    st.info("No competency requirements could be matched to the selected target mode.")
else:
    readiness_cols = st.columns(5)
    readiness_cols[0].metric("Weighted Readiness", f"{metrics['weighted_readiness']:.0f}%")
    readiness_cols[1].metric("Strict Readiness", f"{metrics['strict_readiness']:.0f}%")
    readiness_cols[2].metric("Met", metrics["met"])
    readiness_cols[3].metric("Minor Gaps", metrics["minor"])
    readiness_cols[4].metric("Major Gaps", metrics["major"])

    readiness_status = (
        "Ready ✅"
        if metrics["weighted_readiness"] >= 80
        else "On Track 🟡"
        if metrics["weighted_readiness"] >= 60
        else "Needs Work 🔴"
    )
    st.info(f"**Readiness status:** {readiness_status} · Target: **{target}**")

    priority = gap_df[gap_df["Status"].isin(["Major Gap", "Minor Gap"])].copy()
    st.markdown("### 🔥 Priority Development Areas")
    if priority.empty:
        st.success("No competency gaps were identified for this target.")
    else:
        st.dataframe(
            priority[["Competency", "Competency Name", "Actual", "Target", "Gap", "Status"]],
            width="stretch",
            hide_index=True,
            column_config={
                "Actual": st.column_config.NumberColumn("Actual", format="%.1f"),
                "Target": st.column_config.NumberColumn("Target", format="%.1f"),
                "Gap": st.column_config.NumberColumn("Gap", format="%.1f"),
            },
        )

    with st.expander("📋 Full Competency Breakdown", expanded=False):
        st.dataframe(
            gap_df[
                [
                    "Competency",
                    "Competency Name",
                    "Current Grade",
                    "Target Grade",
                    "Actual",
                    "Target",
                    "Gap",
                    "Status",
                ]
            ],
            width="stretch",
            hide_index=True,
            column_config={
                "Actual": st.column_config.NumberColumn("Actual", format="%.1f"),
                "Target": st.column_config.NumberColumn("Target", format="%.1f"),
                "Gap": st.column_config.NumberColumn("Gap", format="%.1f"),
            },
        )

    st.markdown("### 📈 Readiness Visualizations")
    render_actual_target_charts(gap_df)

    download_df = gap_df.copy()
    csv_data = download_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Download My Target Gap Analysis (CSV)",
        csv_data,
        file_name=f"My_Assessment_Gaps_{staff_id}_{target or 'target'}.csv",
        mime="text/csv",
    )

st.markdown("---")
st.subheader("📊 My Competency Scorecard")
scorecard_tabs = st.tabs(["Overview", "Strengths", "Stored Targets"])

with scorecard_tabs[0]:
    overview_df = (
        assessment_df.groupby("Type", as_index=False)
        .agg(
            Competencies=("Code", "count"),
            Assessed=("Actual", lambda series: int(series.notna().sum())),
            Average=("Actual", "mean"),
        )
    )
    overview_df["Coverage"] = overview_df["Assessed"] / overview_df["Competencies"] * 100
    st.dataframe(
        overview_df,
        width="stretch",
        hide_index=True,
        column_config={
            "Average": st.column_config.NumberColumn("Average Score", format="%.2f"),
            "Coverage": st.column_config.NumberColumn("Coverage", format="%.0f%%"),
        },
    )

with scorecard_tabs[1]:
    _render_strength_section(person)

with scorecard_tabs[2]:
    stored_target_df = assessment_df.dropna(subset=["Stored Target"]).copy()
    stored_target_df["Stored Gap"] = stored_target_df["Stored Target"] - stored_target_df["Actual"]
    stored_target_df["Status"] = stored_target_df.apply(
        lambda row: (
            "Not Assessed"
            if pd.isna(row["Actual"])
            else "Met / Above"
            if row["Actual"] >= row["Stored Target"]
            else "Gap"
        ),
        axis=1,
    )
    if stored_target_df.empty:
        st.info("No stored competency targets are available.")
    else:
        st.dataframe(
            stored_target_df[
                ["Type", "Code", "Competency", "Actual", "Stored Target", "Stored Gap", "Status"]
            ],
            width="stretch",
            hide_index=True,
            column_config={
                "Actual": st.column_config.NumberColumn("Actual", format="%.1f"),
                "Stored Target": st.column_config.NumberColumn("Target", format="%.1f"),
                "Stored Gap": st.column_config.NumberColumn("Gap", format="%.1f"),
            },
        )

st.markdown("---")
st.subheader("📅 My Assessment History")
if history:
    history_df = pd.DataFrame(history)
    history_df["date"] = pd.to_datetime(history_df["date"], errors="coerce")
    history_df = history_df.dropna(subset=["date"]).sort_values(["date", "type", "code"])
    history_summary = history_df.groupby(["date", "type"], as_index=False)["actual"].mean()

    history_fig = go.Figure()
    for assessment_type in history_summary["type"].dropna().unique():
        subset = history_summary[history_summary["type"] == assessment_type]
        history_fig.add_trace(
            go.Scatter(
                x=subset["date"],
                y=subset["actual"],
                mode="lines+markers",
                name=str(assessment_type),
            )
        )
    history_fig.update_layout(
        title="Average Competency Score by Assessment Date",
        height=360,
        yaxis={"range": [0, 5], "dtick": 1, "title": "Average Score"},
        xaxis={"title": "Assessment Date"},
        margin=dict(l=20, r=20, t=55, b=20),
        legend_title_text="Competency Class",
    )
    st.plotly_chart(history_fig, width="stretch", config={"displaylogo": False})

    history_table = history_df.rename(
        columns={
            "date": "Assessment Date",
            "type": "Competency Type",
            "code": "Competency Code",
            "actual": "Actual Score",
            "requirement": "Requirement",
            "gap": "Recorded Gap",
        }
    )
    st.dataframe(
        history_table[
            ["Assessment Date", "Competency Type", "Competency Code", "Actual Score", "Requirement", "Recorded Gap"]
        ],
        width="stretch",
        hide_index=True,
        column_config={
            "Assessment Date": st.column_config.DateColumn("Assessment Date"),
            "Actual Score": st.column_config.NumberColumn("Actual Score", format="%.1f"),
            "Requirement": st.column_config.NumberColumn("Requirement", format="%.1f"),
            "Recorded Gap": st.column_config.NumberColumn("Recorded Gap", format="%.1f"),
        },
    )
else:
    st.info("No assessment history is available for your personnel record.")

if summary:
    st.markdown("---")
    with st.expander("📌 Existing Assessment Summary Scores", expanded=False):
        groups = {
            "Next Grade": ["next_grade_base", "next_grade_keys", "next_grade_pacing", "next_grade_emerging", "next_grade_cti"],
            "Staff": ["staff_base", "staff_keys", "staff_pacing", "staff_emerging", "staff_cti"],
            "Principal": ["principal_base", "principal_keys", "principal_pacing", "principal_emerging", "principal_cti"],
            "Custodian": ["custodian_base", "custodian_keys", "custodian_pacing", "custodian_emerging", "custodian_cti"],
        }
        for group_name, fields in groups.items():
            st.markdown(f"**{group_name}**")
            cols = st.columns(5)
            for column, label, field in zip(cols, ["Base", "Keys", "Pacing", "Emerging", "CTI"], fields):
                number = pd.to_numeric(getattr(summary, field, None), errors="coerce")
                column.metric(label, "N/A" if pd.isna(number) else f"{float(number):.0f}%")

st.caption(
    "This assessment workspace is intentionally limited to your linked personnel record. "
    "Organisation-wide personnel selection, administration, document management and assessment editing remain admin-only."
)
