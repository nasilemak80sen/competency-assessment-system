"""Personnel-scoped dashboard for USER accounts."""
from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.navigation import render_header, render_navigation
from config import COMP_TYPES, COMPETENCY_FULLNAMES
from core.auth import ROLE_USER, current_user, personnel_id, require_roles
from core.bootstrap import get_master_data, open_session
from db_ops import update_personnel
from models import CVDocument, Personnel


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


def _controlled_value(workbook_value, db_value=None, fallback="Not available"):
    """Workbook-first for organisation-controlled analytical fields."""
    return _profile_value(workbook_value, db_value, fallback)


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
            records.append(
                {
                    "Type": info.get("label", ctype),
                    "Code": code,
                    "Competency": COMPETENCY_FULLNAMES.get(code, code),
                    "Actual": _numeric_score(person.get(code)),
                    "Target": _numeric_score(person.get(f"R-{code}")),
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
document_records = []
try:
    person_db = (
        session.query(Personnel)
        .filter(Personnel.id == linked_id, Personnel.is_deleted.is_(False))
        .first()
    )
    if person_db is not None:
        docs = (
            session.query(CVDocument)
            .filter(CVDocument.personnel_id == linked_id, CVDocument.is_deleted.is_(False))
            .order_by(CVDocument.modified_date.desc(), CVDocument.id.desc())
            .all()
        )
        document_records = [
            {
                "name": item.cv_file_name or "Document",
                "type": item.file_type or "N/A",
                "status": item.cv_status or "N/A",
                "modified": item.modified_date,
                "url": (item.sharepoint_url or "").strip(),
                "notes": getattr(item, "notes", None) or "",
            }
            for item in docs
        ]
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

assessment_level = _controlled_value(person.get("Assessment Level"), person_db.assessment_level)
last_assessment = person.get("Last Assesment Date") or person.get("Last Assessment Date") or person_db.last_assessment_date
chat_status = _controlled_value(person.get("Chat Status"), person_db.chat_status)
chat_date = person.get("Chat Date") or person_db.chat_date
potential = _controlled_value(person.get("Potential"), person_db.potential)
recommendation = _controlled_value(person.get("Recommendation"), person_db.recommendation)
sub_disciplines = _controlled_value(person.get("Sub-Disciplines"), person_db.sub_disciplines)
resource_sme = _controlled_value(person.get("Resource/SME"), person_db.resource_sme)
supervisor = _controlled_value(person.get("Supervisor"), person_db.supervisor)
contract_expiry = person.get("Contract Expire Date") or person_db.contract_expire_date
assignment_length = person.get("Length in Current Assignment") or person_db.assignment_length
years_in_grade = person.get("Years in Salary Grade") or person_db.sg_years

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

profile_tab, career_tab, documents_tab, edit_tab = st.tabs(
    ["👤 My Profile", "🎯 Career & Assessment", "📄 My Documents", "✏️ Edit Profile"]
)

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

    details_left, details_right = st.columns(2)
    with details_left:
        st.markdown("### 📌 Assessment Context")
        st.info(f"**Potential:** {potential}\n\n**Recommendation:** {recommendation}")
        st.info(f"**Supervisor:** {supervisor}\n\n**Sub-Disciplines:** {sub_disciplines}")
    with details_right:
        st.markdown("### 🏢 Employment Context")
        st.info(
            f"**Contract Expiry:** {_safe_date(contract_expiry)}\n\n"
            f"**Years in Grade:** {_profile_value(years_in_grade, fallback='Not available')}\n\n"
            f"**Current Assignment:** {_profile_value(person_db.current_assignment, person.get('Current Location:'))}\n\n"
            f"**Assignment Length:** {_profile_value(assignment_length, fallback='Not available')}"
        )

    parsed_last = pd.to_datetime(last_assessment, errors="coerce")
    if pd.notna(parsed_last):
        days_since = max(0, (date.today() - parsed_last.date()).days)
        st.caption(f"Assessment recency: **{days_since} day(s)** since the latest recorded assessment date.")

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

with documents_tab:
    st.subheader("📄 My CV & Supporting Documents")
    valid_documents = [item for item in document_records if item["url"].lower().startswith(("https://", "http://"))]
    invalid_documents = [item for item in document_records if item not in valid_documents]

    if not document_records:
        st.info("No CV or supporting document is currently registered for your personnel record.")
    elif not valid_documents:
        st.warning("Document records exist, but no valid SharePoint link is currently available.")
        st.dataframe(
            pd.DataFrame(document_records)[["name", "type", "status", "modified", "notes"]],
            width="stretch",
            hide_index=True,
        )
    else:
        latest = valid_documents[0]
        latest_cols = st.columns([2, 1, 1])
        latest_cols[0].metric("Latest Document", latest["name"])
        latest_cols[1].metric("File Type", latest["type"])
        latest_cols[2].metric("Last Modified", _safe_date(latest["modified"], "Date unavailable"))
        st.link_button("📄 Open Latest Document in SharePoint", latest["url"], width="stretch")
        st.caption(f"{len(valid_documents)} valid linked document(s) available.")

        with st.expander(f"🗂️ View all documents ({len(valid_documents)})", expanded=len(valid_documents) <= 3):
            for item in valid_documents:
                info_col, action_col = st.columns([4, 1])
                info_col.markdown(
                    f"**{item['name']}**  \n`{item['type']}` · {item['status']} · Modified {_safe_date(item['modified'], 'Date unavailable')}"
                )
                action_col.link_button("Open", item["url"], width="stretch")
                st.divider()

        if invalid_documents:
            with st.expander(f"⚠️ Records without valid links ({len(invalid_documents)})"):
                st.dataframe(
                    pd.DataFrame(invalid_documents)[["name", "type", "status", "modified", "notes"]],
                    width="stretch",
                    hide_index=True,
                )

with edit_tab:
    st.subheader("✏️ Edit My Profile")
    st.info("You can update your personal/contact information and career preferences here. Organisation-controlled fields and assessment results cannot be changed from USER access.")

    with st.form("user_edit_profile_form"):
        email = st.text_input("Email", value=_profile_value(person_db.email, person.get("Email Address"), ""))
        gender = st.text_input("Gender", value=_profile_value(person_db.gender, person.get("Gender"), ""))
        nationality = st.text_input("Nationality", value=_profile_value(person_db.nationality, person.get("Nationality"), ""))
        current_assignment = st.text_input(
            "Current Assignment",
            value=_profile_value(person_db.current_assignment, person.get("Current Location:"), ""),
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
