"""Personnel-scoped dashboard for USER accounts."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from components.competency_charts import render_actual_target_charts
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
db_assessment_dates = []
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
        db_assessment_dates = [
            assessment.assessment_date
            for assessment in person_db.assessments
            if assessment.assessment_date is not None
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

editable_profile_values = {
    "Email": _profile_value(person_db.email, person.get("Email Address"), ""),
    "Gender": _profile_value(person_db.gender, person.get("Gender"), ""),
    "Nationality": _profile_value(person_db.nationality, person.get("Nationality"), ""),
    "Current Assignment": _profile_value(person_db.current_assignment, person.get("Current Location:"), ""),
    "Interest": _profile_value(person_db.interest, person.get("Interest"), ""),
    "Preference": _profile_value(person_db.preference, person.get("Preference"), ""),
    "Strength": _profile_value(person_db.strength, person.get("Strength"), ""),
}
profile_completeness = (
    sum(bool(value.strip()) for value in editable_profile_values.values())
    / len(editable_profile_values)
    * 100
)
missing_profile_fields = [label for label, value in editable_profile_values.items() if not value.strip()]

assessment_level = _controlled_value(person.get("Assessment Level"), person_db.assessment_level)
potential = _controlled_value(person.get("Potential"), person_db.potential)
recommendation = _controlled_value(person.get("Recommendation"), person_db.recommendation)
sub_disciplines = _controlled_value(person.get("Sub-Disciplines"), person_db.sub_disciplines)
resource_sme = _controlled_value(person.get("Resource/SME"), person_db.resource_sme)
supervisor = _controlled_value(person.get("Supervisor"), person_db.supervisor)
comment = _controlled_value(person.get("Comment/Suggestion"), person_db.comment)
remarks = _controlled_value(person.get("Remarks"), person_db.remarks)
chat_status = _controlled_value(person.get("Chat Status"), person_db.chat_status)
chat_date = person.get("Chat Date") or person_db.chat_date
contract_expiry = person.get("Contract Expire Date") or person_db.contract_expire_date
assignment_length = person.get("Length in Current Assignment") or person_db.assignment_length
years_in_grade = person.get("Years in Salary Grade") or person_db.sg_years

metadata_last_assessment = person.get("Last Assesment Date") or person.get("Last Assessment Date")
assessment_dates = [pd.Timestamp(value) for value in db_assessment_dates if value is not None]
metadata_timestamp = pd.to_datetime(metadata_last_assessment, errors="coerce")
if pd.notna(metadata_timestamp):
    assessment_dates.append(metadata_timestamp)
last_assessment = max(assessment_dates) if assessment_dates else None

st.caption(f"Signed in as **{user.get('display_name') or user.get('username')}**")
st.subheader(f"Welcome, {person_db.name or person.get('Name')}")

re_years = pd.to_numeric(person.get("Years of RE Experience"), errors="coerce")
pet_years = pd.to_numeric(person.get("Years in PET"), errors="coerce")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Salary Grade", _profile_value(person.get("SG"), person_db.sg))
c2.metric("Position", _profile_value(person.get("Staff Position"), person_db.staff_position))
c3.metric("Department", _profile_value(person.get("Department"), person_db.department))
c4.metric("RE Experience", f"{re_years:.1f} yrs" if pd.notna(re_years) else "N/A")
c5.metric("PETRONAS Experience", f"{pet_years:.1f} yrs" if pd.notna(pet_years) else "N/A")

st.markdown("---")
summary_cols = st.columns(5)
summary_cols[0].metric("Assessment Coverage", f"{coverage:.0f}%")
summary_cols[1].metric("Average Competency", f"{average_score:.2f}/5")
summary_cols[2].metric("Profile Completeness", f"{profile_completeness:.0f}%")
summary_cols[3].metric("Last Assessment", _safe_date(last_assessment))
summary_cols[4].metric("Assessment Level", assessment_level)

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
                "Age": person.get("Age") if pd.notna(person.get("Age")) else person_db.age,
                "Email": editable_profile_values["Email"],
                "Gender": editable_profile_values["Gender"],
                "Nationality": editable_profile_values["Nationality"],
                "Position": _profile_value(person.get("Staff Position"), person_db.staff_position),
                "Salary Grade": _profile_value(person.get("SG"), person_db.sg),
                "Department": _profile_value(person.get("Department"), person_db.department),
                "Section": _profile_value(person.get("Section Name"), person_db.section_name),
                "Employment": _profile_value(person.get("Employment Category"), person_db.employment_category),
                "Current Assignment": editable_profile_values["Current Assignment"],
            }
        )
    with profile_right:
        st.subheader("🧭 Talent & Career Profile")
        background = _controlled_value(
            person.get("Background") or person.get("Sub-Disciplines"),
            person_db.sub_disciplines,
        )
        st.write(
            {
                "Strength": editable_profile_values["Strength"],
                "Interest": editable_profile_values["Interest"],
                "Preference": editable_profile_values["Preference"],
                "Background": background,
                "Sub-Disciplines": sub_disciplines,
                "Resource / SME": resource_sme,
                "Potential": potential,
            }
        )
        st.caption("Organisation-controlled competency scores, grade, position and assessment records remain admin-controlled.")

    st.subheader("📊 Competency Snapshot")
    type_summary = (
        score_df.groupby("Type", as_index=False)
        .agg(
            Competencies=("Code", "count"),
            Assessed=("Actual", lambda series: int(series.notna().sum())),
            Average=("Actual", "mean"),
        )
    )
    type_summary["Coverage"] = type_summary["Assessed"] / type_summary["Competencies"] * 100
    st.dataframe(
        type_summary,
        width="stretch",
        hide_index=True,
        column_config={
            "Average": st.column_config.NumberColumn("Average Score", format="%.2f"),
            "Coverage": st.column_config.NumberColumn("Coverage", format="%.0f%%"),
        },
    )
    with st.expander("📈 Detailed Actual vs Target + Radar", expanded=True):
        st.caption("Shared competency visualisation: PETRONAS emerald Actual bars and red Target line/radar.")
        render_actual_target_charts(score_df)

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
        st.info(
            f"**Potential:** {potential}\n\n"
            f"**Recommendation:** {recommendation}"
        )
        st.info(
            f"**Supervisor:** {supervisor}\n\n"
            f"**Sub-Disciplines:** {sub_disciplines}"
        )
        with st.expander("📝 Assessment Feedback & Remarks"):
            st.markdown(f"**Comment / Suggestion**\n\n{comment}")
            st.markdown(f"**Remarks**\n\n{remarks}")
    with details_right:
        st.markdown("### 🏢 Employment Context")
        st.info(
            f"**Age:** {_profile_value(person.get('Age'), person_db.age)}\n\n"
            f"**Contract Expiry:** {_safe_date(contract_expiry)}\n\n"
            f"**Years in Grade:** {_profile_value(years_in_grade, fallback='Not available')}\n\n"
            f"**Current Assignment:** {editable_profile_values['Current Assignment']}\n\n"
            f"**Assignment Length:** {_profile_value(assignment_length, fallback='Not available')}"
        )

    if missing_profile_fields:
        st.warning("Profile information is incomplete. Missing editable fields: " + ", ".join(missing_profile_fields) + ".")
        st.caption("Use **Edit Profile** on My Dashboard to complete these fields.")
    else:
        st.success("Your editable profile fields are complete.")

with documents_tab:
    st.subheader("📄 My CV & Supporting Documents")
    session = open_session()
    try:
        documents = (
            session.query(CVDocument)
            .filter(CVDocument.personnel_id == linked_id, CVDocument.is_deleted.is_(False))
            .order_by(CVDocument.modified_date.desc(), CVDocument.id.desc())
            .all()
        )
    finally:
        session.close()

    if not documents:
        st.info("No CV or supporting document is currently registered for your personnel record.")
    else:
        document_records = [
            {
                "name": item.cv_file_name or "Document",
                "type": item.file_type or "N/A",
                "status": item.cv_status or "N/A",
                "modified": item.modified_date,
                "url": (item.sharepoint_url or "").strip(),
                "notes": getattr(item, "notes", None) or "",
            }
            for item in documents
        ]
        valid_documents = [item for item in document_records if item["url"].lower().startswith(("https://", "http://"))]
        invalid_documents = [item for item in document_records if not item["url"].lower().startswith(("https://", "http://"))]

        if not valid_documents:
            st.warning("Document records exist, but no valid SharePoint link is currently available.")
        else:
            latest = valid_documents[0]
            latest_cols = st.columns([2, 1, 1])
            latest_cols[0].metric("Latest Document", latest["name"])
            latest_cols[1].metric("File Type", latest["type"])
            latest_cols[2].metric("Last Modified", _safe_date(latest["modified"], "Date unavailable"))
            st.link_button("📄 Open Latest Document in SharePoint", latest["url"], width="stretch")

            with st.expander(f"🗂️ View all documents ({len(valid_documents)})", expanded=len(valid_documents) <= 3):
                for item in valid_documents:
                    info_col, action_col = st.columns([4, 1])
                    info_col.markdown(
                        f"**{item['name']}**  \n`{item['type']}` · {item['status']} · Modified {_safe_date(item['modified'], 'Date unavailable')}"
                    )
                    if item["notes"]:
                        info_col.caption(item["notes"])
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
        email = st.text_input("Email", value=editable_profile_values["Email"])
        gender = st.text_input("Gender", value=editable_profile_values["Gender"])
        nationality = st.text_input("Nationality", value=editable_profile_values["Nationality"])
        current_assignment = st.text_input("Current Assignment", value=editable_profile_values["Current Assignment"])
        interest = st.text_area("Interest", value=editable_profile_values["Interest"], height=90)
        preference = st.text_area("Preference", value=editable_profile_values["Preference"], height=90)
        strength = st.text_area("Strength", value=editable_profile_values["Strength"], height=110)
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

st.caption("This page is intentionally restricted to your linked personnel record. Organisation-wide analytics are available only to administrators.")
