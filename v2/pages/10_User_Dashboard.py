"""Personnel-scoped dashboard for USER accounts."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.navigation import render_header, render_navigation
from config import COMP_TYPES, COMPETENCY_FULLNAMES
from core.auth import ROLE_USER, current_user, personnel_id, require_roles
from core.bootstrap import get_master_data, open_session
from db_ops import update_personnel
from models import Personnel


require_roles(ROLE_USER)
render_navigation()
user = current_user()
render_header("🏠 My Dashboard", "Personal competency, career and assessment snapshot")


def _profile_value(db_value, workbook_value=None, fallback="Not available"):
    for value in (db_value, workbook_value):
        if value is None:
            continue
        try:
            if pd.isna(value):
                continue
        except (TypeError, ValueError):
            pass
        text = str(value).strip()
        if text and text.lower() not in {"nan", "none", "nat"}:
            return text
    return fallback


def _safe_date(value, fallback="Not available"):
    parsed = pd.to_datetime(value, errors="coerce")
    return fallback if pd.isna(parsed) else parsed.strftime("%d %b %Y")


def _numeric_score(value):
    score = pd.to_numeric(value, errors="coerce")
    if pd.isna(score):
        return None
    return float(score)


def _build_score_frame(person):
    records = []
    for ctype, info in COMP_TYPES.items():
        for code in info.get("cols", []):
            actual = _numeric_score(person.get(code))
            target = _numeric_score(person.get(f"R-{code}"))
            records.append(
                {
                    "Type": info.get("label", ctype),
                    "Code": code,
                    "Competency": COMPETENCY_FULLNAMES.get(code, code),
                    "Actual": actual,
                    "Target": target,
                }
            )
    frame = pd.DataFrame(records)
    frame["Gap"] = frame["Target"] - frame["Actual"]
    return frame


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
score_df = _build_score_frame(person)
assessed = score_df["Actual"].notna()
coverage = float(assessed.mean() * 100) if len(score_df) else 0.0
average_score = float(score_df.loc[assessed, "Actual"].mean()) if assessed.any() else 0.0

profile_fields = [
    _profile_value(person_db.email, person.get("Email Address"), ""),
    _profile_value(person_db.gender, person.get("Gender"), ""),
    _profile_value(person_db.nationality, person.get("Nationality"), ""),
    _profile_value(person_db.current_assignment, person.get("Current Location:"), ""),
    _profile_value(person_db.interest, person.get("Interest"), ""),
    _profile_value(person_db.preference, person.get("Preference"), ""),
    _profile_value(person_db.strength, person.get("Strength"), ""),
]
profile_completeness = sum(bool(value.strip()) for value in profile_fields) / len(profile_fields) * 100

assessment_level = _profile_value(person_db.assessment_level, person.get("Assessment Level"))
last_assessment = person_db.last_assessment_date or person.get("Last Assesment Date") or person.get("Last Assessment Date")
chat_status = _profile_value(person_db.chat_status, person.get("Chat Status"))
chat_date = person_db.chat_date or person.get("Chat Date")
potential = _profile_value(person_db.potential, person.get("Potential"))
recommendation = _profile_value(person_db.recommendation, person.get("Recommendation"))
sub_disciplines = _profile_value(person_db.sub_disciplines, person.get("Sub-Disciplines"))
resource_sme = _profile_value(person_db.resource_sme, person.get("Resource/SME"))

st.caption(f"Signed in as **{user.get('display_name') or user.get('username')}**")
st.subheader(f"Welcome, {person_db.name or person.get('Name')}")

re_years = pd.to_numeric(person.get("Years of RE Experience"), errors="coerce")
pet_years = pd.to_numeric(person.get("Years in PET"), errors="coerce")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Salary Grade", str(person.get("SG", "N/A")))
c2.metric("Position", str(person.get("Staff Position", "N/A")))
c3.metric("Department", str(person.get("Department", "N/A")))
c4.metric("RE Experience", f"{re_years:.1f} yrs" if pd.notna(re_years) else "N/A")
c5.metric("PETRONAS Experience", f"{pet_years:.1f} yrs" if pd.notna(pet_years) else "N/A")

st.markdown("---")
summary_cols = st.columns(4)
summary_cols[0].metric("Assessment Coverage", f"{coverage:.0f}%")
summary_cols[1].metric("Average Competency", f"{average_score:.2f}/5")
summary_cols[2].metric("Profile Completeness", f"{profile_completeness:.0f}%")
summary_cols[3].metric("Assessment Level", assessment_level)

profile_tab, career_tab, edit_tab = st.tabs(["👤 My Profile", "🎯 Career & Assessment", "✏️ Edit Profile"])

with profile_tab:
    profile_left, profile_right = st.columns(2)
    with profile_left:
        st.subheader("👤 My Profile")
        st.write(
            {
                "Name": person_db.name or person.get("Name"),
                "Staff ID": person_db.staff_id or person.get("Staff ID"),
                "Email": _profile_value(person_db.email, person.get("Email Address")),
                "Gender": _profile_value(person_db.gender, person.get("Gender")),
                "Nationality": _profile_value(person_db.nationality, person.get("Nationality")),
                "Position": person.get("Staff Position"),
                "Salary Grade": person.get("SG"),
                "Department": person.get("Department"),
                "Section": person.get("Section Name"),
                "Employment": person.get("Employment Category"),
                "Current Assignment": _profile_value(
                    person_db.current_assignment,
                    person.get("Current Location:"),
                ),
            }
        )
    with profile_right:
        st.subheader("🧭 Talent & Career Profile")
        st.write(
            {
                "Strength": _profile_value(person_db.strength, person.get("Strength")),
                "Interest": _profile_value(person_db.interest, person.get("Interest")),
                "Preference": _profile_value(person_db.preference, person.get("Preference")),
                "Sub-Disciplines": sub_disciplines,
                "Resource / SME": resource_sme,
                "Potential": potential,
            }
        )
        st.caption("Organisation-controlled competency scores, grade, position and assessment records remain admin-controlled.")

    st.subheader("📊 Competency Snapshot")
    type_summary = (
        score_df.groupby("Type", as_index=False)
        .agg(Actual=("Actual", "mean"), Target=("Target", "mean"))
    )
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=type_summary["Type"],
            y=type_summary["Actual"],
            name="Actual",
            marker_color="#00A651",
            text=type_summary["Actual"].map(lambda value: "—" if pd.isna(value) else f"{value:.2f}"),
            textposition="outside",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=type_summary["Type"],
            y=type_summary["Target"],
            name="Target",
            mode="lines+markers",
            line={"color": "#D62728", "width": 3},
            marker={"color": "#D62728", "size": 8},
        )
    )
    fig.update_layout(
        height=340,
        yaxis={"range": [0, 5], "dtick": 1, "title": "Average Score"},
        xaxis_title="",
        margin=dict(l=20, r=20, t=30, b=20),
        legend_title_text="",
    )
    st.plotly_chart(fig, width="stretch", config={"displaylogo": False})

with career_tab:
    st.subheader("🎯 Assessment & Career Snapshot")
    career_cols = st.columns(4)
    career_cols[0].metric("Assessment Level", assessment_level)
    career_cols[1].metric("Last Assessment", _safe_date(last_assessment))
    career_cols[2].metric("Chat Status", chat_status)
    career_cols[3].metric("Chat Date", _safe_date(chat_date))

    st.markdown("### 📌 Assessment Context")
    context_left, context_right = st.columns(2)
    with context_left:
        st.info(f"**Potential:** {potential}")
        st.info(f"**Recommendation:** {recommendation}")
    with context_right:
        st.info(f"**Supervisor:** {_profile_value(person_db.supervisor, person.get('Supervisor'))}")
        st.info(f"**Current Assignment:** {_profile_value(person_db.current_assignment, person.get('Current Location:'))}")

    gap_frame = score_df.dropna(subset=["Actual", "Target"]).copy()
    gap_frame["Gap"] = gap_frame["Target"] - gap_frame["Actual"]
    development = gap_frame[gap_frame["Gap"] > 0].sort_values("Gap", ascending=False).head(5)
    st.markdown("### 🔥 Top Development Gaps")
    if development.empty:
        st.success("No stored target gaps are currently recorded.")
    else:
        st.dataframe(
            development[["Type", "Code", "Competency", "Actual", "Target", "Gap"]],
            width="stretch",
            hide_index=True,
            column_config={
                "Actual": st.column_config.NumberColumn("Actual", format="%.1f"),
                "Target": st.column_config.NumberColumn("Target", format="%.1f"),
                "Gap": st.column_config.NumberColumn("Gap", format="%.1f"),
            },
        )
        st.caption("Open **My Assessment** for target-grade selection, readiness analysis and detailed development gaps.")

with edit_tab:
    st.subheader("✏️ Edit My Profile")
    st.info("You can update your personal/contact information and career preferences here. Organisation-controlled fields and assessment results cannot be changed from USER access.")

    with st.form("user_edit_profile_form"):
        email = st.text_input("Email", value=_profile_value(person_db.email, person.get("Email Address"), ""))
        gender = st.text_input("Gender", value=_profile_value(person_db.gender, person.get("Gender"), ""))
        nationality = st.text_input("Nationality", value=_profile_value(person_db.nationality, person.get("Nationality"), ""))
        current_assignment = st.text_input(
            "Current Assignment",
            value=_profile_value(
                person_db.current_assignment,
                person.get("Current Location:"),
                "",
            ),
        )
        interest = st.text_area("Interest", value=_profile_value(person_db.interest, person.get("Interest"), ""), height=90)
        preference = st.text_area("Preference", value=_profile_value(person_db.preference, person.get("Preference"), ""), height=90)
        strength = st.text_area("Strength", value=_profile_value(person_db.strength, person.get("Strength"), ""), height=110)
        saved = st.form_submit_button("💾 Save Profile", type="primary")

    if saved:
        payload = {
            "email": email.strip() or None,
            "gender": gender.strip() or None,
            "nationality": nationality.strip() or None,
            "current_assignment": current_assignment.strip() or None,
            "interest": interest.strip() or None,
            "preference": preference.strip() or None,
            "strength": strength.strip() or None,
        }
        update_session = open_session()
        try:
            ok, message = update_personnel(update_session, linked_id, payload)
        finally:
            update_session.close()

        if ok:
            st.success("Profile updated successfully.")
            st.rerun()
        else:
            st.error(message)

st.caption("This page is intentionally restricted to your own personnel record. Organisation-wide analytics are available only to administrators.")
