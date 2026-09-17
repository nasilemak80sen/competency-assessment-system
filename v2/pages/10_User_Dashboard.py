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
    return _profile_value(workbook_value, db_value, fallback)


def _safe_date(value, fallback="Not available"):
    parsed = pd.to_datetime(value, errors="coerce")
    return fallback if pd.isna(parsed) else parsed.strftime("%d %b %Y")


def _numeric_score(value):
    score = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(score) else float(score)


def _build_score_frame(person):
    records = []
    for ctype, info in COMP_TYPES.items():
        for code in info.get("cols", []):
            records.append({
                "Type": info.get("label", ctype),
                "Code": code,
                "Competency": COMPETENCY_FULLNAMES.get(code, code),
                "Actual": _numeric_score(person.get(code)),
                "Target": _numeric_score(person.get(f"R-{code}")),
            })
    frame = pd.DataFrame(records)
    frame["Gap"] = frame["Target"] - frame["Actual"]
    return frame


def _display_age(person, person_db):
    age = person.get("Age")
    if pd.notna(age):
        try:
            return f"{float(age):.0f} years"
        except (TypeError, ValueError):
            pass
    return _profile_value(person_db.age, fallback="Not available")


def _field_row(label, value, icon="•"):
    safe = _profile_value(value, fallback="Not available")
    return f"<div class='profile-field'><span class='profile-label'>{icon} {label}</span><span class='profile-value'>{safe}</span></div>"


def _profile_css():
    st.markdown(
        """
        <style>
        .profile-card {
            border: 1px solid rgba(128,128,128,.25);
            border-radius: 12px;
            padding: 18px 20px;
            margin-bottom: 12px;
            background: rgba(128,128,128,.035);
        }
        .profile-field {
            padding: 8px 0;
            border-bottom: 1px solid rgba(128,128,128,.14);
        }
        .profile-field:last-child { border-bottom: 0; }
        .profile-label {
            display: inline-block;
            width: 38%;
            font-size: .82rem;
            color: rgba(128,128,128,.95);
            vertical-align: top;
        }
        .profile-value {
            display: inline-block;
            width: 62%;
            font-weight: 600;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .profile-hero {
            border-radius: 14px;
            padding: 20px 22px;
            margin: 6px 0 18px 0;
            border: 1px solid rgba(128,128,128,.22);
            background: linear-gradient(135deg, rgba(0,128,96,.08), rgba(128,128,128,.035));
        }
        .profile-hero-name { font-size: 1.45rem; font-weight: 700; margin-bottom: 3px; }
        .profile-hero-meta { color: rgba(128,128,128,.95); font-size: .9rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


linked_id = personnel_id()
if linked_id is None:
    st.error("Your account is not linked to a personnel record.")
    st.stop()

session = open_session()
person_db = None
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
    st.error(f"Your personnel record ({person_db.name} · {staff_id}) is not present in the current master dataset.")
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
profile_completeness = sum(bool(value.strip()) for value in editable_profile_values.values()) / len(editable_profile_values) * 100
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

assessment_dates = []
for assessment in getattr(person_db, "assessments", []):
    parsed = pd.to_datetime(assessment.assessment_date, errors="coerce")
    if pd.notna(parsed):
        assessment_dates.append(parsed)
for candidate in (person.get("Last Assesment Date"), person.get("Last Assessment Date")):
    parsed = pd.to_datetime(candidate, errors="coerce")
    if pd.notna(parsed):
        assessment_dates.append(parsed)
last_assessment = max(assessment_dates) if assessment_dates else None

re_years = pd.to_numeric(person.get("Years of RE Experience"), errors="coerce")
pet_years = pd.to_numeric(person.get("Years in PET"), errors="coerce")
sg = _profile_value(person.get("SG"), person_db.sg)
position = _profile_value(person.get("Staff Position"), person_db.staff_position)
department = _profile_value(person.get("Department"), person_db.department)
section = _profile_value(person.get("Section Name"), person_db.section_name)
employment = _profile_value(person.get("Employment Category"), person_db.employment_category)

_profile_css()
user_name = person_db.name or person.get("Name") or user.get("display_name") or user.get("username")

st.markdown(
    f"""
    <div class='profile-hero'>
        <div class='profile-hero-name'>👋 Welcome, {user_name}</div>
        <div class='profile-hero-meta'>{position} · {department} · {section} · Salary Grade {sg}</div>
    </div>
    """,
    unsafe_allow_html=True,
)

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Assessment Coverage", f"{coverage:.0f}%")
k2.metric("Average Competency", f"{average_score:.2f} / 5")
k3.metric("Profile Completeness", f"{profile_completeness:.0f}%")
k4.metric("Last Assessment", _safe_date(last_assessment))
k5.metric("Current Level", assessment_level)

st.markdown("### 👤 My Profile")
profile_tab, career_tab, documents_tab, edit_tab = st.tabs(
    ["Overview", "🎯 Career & Assessment", "📄 My Documents", "✏️ Edit Profile"]
)

with profile_tab:
    identity_col, work_col = st.columns(2)
    with identity_col:
        st.markdown("#### Personal Information")
        st.markdown(
            "<div class='profile-card'>"
            + _field_row("Name", user_name, "👤")
            + _field_row("Staff ID", person_db.staff_id, "🪪")
            + _field_row("Age", _display_age(person, person_db), "🎂")
            + _field_row("Email", editable_profile_values["Email"], "✉️")
            + _field_row("Gender", editable_profile_values["Gender"], "⚥")
            + _field_row("Nationality", editable_profile_values["Nationality"], "🌏")
            + "</div>",
            unsafe_allow_html=True,
        )

    with work_col:
        st.markdown("#### Organisation & Assignment")
        st.markdown(
            "<div class='profile-card'>"
            + _field_row("Position", position, "💼")
            + _field_row("Salary Grade", sg, "📈")
            + _field_row("Department", department, "🏢")
            + _field_row("Section", section, "📂")
            + _field_row("Employment", employment, "📋")
            + _field_row("Current Assignment", editable_profile_values["Current Assignment"], "📍")
            + "</div>",
            unsafe_allow_html=True,
        )

    st.markdown("#### 🧭 Talent Profile")
    talent_left, talent_right = st.columns(2)
    with talent_left:
        st.markdown(
            "<div class='profile-card'>"
            + _field_row("Strength", editable_profile_values["Strength"], "💪")
            + _field_row("Interest", editable_profile_values["Interest"], "🔎")
            + _field_row("Preference", editable_profile_values["Preference"], "⭐")
            + "</div>",
            unsafe_allow_html=True,
        )
    with talent_right:
        background = _controlled_value(person.get("Background") or person.get("Sub-Disciplines"), person_db.sub_disciplines)
        st.markdown(
            "<div class='profile-card'>"
            + _field_row("Background", background, "🧩")
            + _field_row("Sub-Disciplines", sub_disciplines, "🛠️")
            + _field_row("Resource / SME", resource_sme, "🎓")
            + _field_row("Potential", potential, "🚀")
            + "</div>",
            unsafe_allow_html=True,
        )

    st.markdown("#### 📊 Competency Snapshot")
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
        render_actual_target_charts(score_df)

with career_tab:
    st.subheader("🎯 Assessment & Career Snapshot")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Assessment Level", assessment_level)
    c2.metric("Last Assessment", _safe_date(last_assessment))
    c3.metric("Chat Status", chat_status)
    c4.metric("Chat Date", _safe_date(chat_date))

    context_left, context_right = st.columns(2)
    with context_left:
        st.markdown("#### 📌 Assessment Context")
        st.info(f"**Potential**\n\n{potential}")
        st.info(f"**Recommendation**\n\n{recommendation}")
        st.info(f"**Supervisor**\n\n{supervisor}")
        with st.expander("📝 Assessment Feedback & Remarks"):
            st.markdown(f"**Comment / Suggestion**\n\n{comment}")
            st.markdown(f"**Remarks**\n\n{remarks}")
    with context_right:
        st.markdown("#### 🏢 Employment Context")
        re_text = f"{re_years:.1f} yrs" if pd.notna(re_years) else "Not available"
        pet_text = f"{pet_years:.1f} yrs" if pd.notna(pet_years) else "Not available"
        st.info(
            f"**RE Experience:** {re_text}\n\n"
            f"**PETRONAS Experience:** {pet_text}\n\n"
            f"**Contract Expiry:** {_safe_date(contract_expiry)}\n\n"
            f"**Years in Grade:** {_profile_value(years_in_grade)}\n\n"
            f"**Current Assignment:** {editable_profile_values['Current Assignment']}\n\n"
            f"**Assignment Length:** {_profile_value(assignment_length)}"
        )

    if missing_profile_fields:
        st.warning("Profile information still needs attention: " + ", ".join(missing_profile_fields) + ".")
        st.caption("Use **Edit Profile** to complete your personal/contact information.")
    else:
        st.success("Your editable profile information is complete.")

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
        valid_documents = [
            item for item in documents
            if (item.sharepoint_url or "").strip().lower().startswith(("https://", "http://"))
        ]
        invalid_documents = [item for item in documents if item not in valid_documents]
        if not valid_documents:
            st.warning("Document records exist, but no valid SharePoint link is currently available.")
        else:
            latest = valid_documents[0]
            a, b, c = st.columns([2, 1, 1])
            a.metric("Latest Document", latest.cv_file_name or "Document")
            b.metric("File Type", latest.file_type or "N/A")
            c.metric("Last Modified", _safe_date(latest.modified_date, "Date unavailable"))
            st.link_button("📄 Open Latest Document in SharePoint", latest.sharepoint_url.strip(), width="stretch")
            with st.expander(f"🗂️ View all documents ({len(valid_documents)})", expanded=len(valid_documents) <= 3):
                for item in valid_documents:
                    left, right = st.columns([4, 1])
                    left.markdown(
                        f"**{item.cv_file_name or 'Document'}**  \n`{item.file_type or 'N/A'}` · {item.cv_status or 'N/A'} · Modified {_safe_date(item.modified_date, 'Date unavailable')}"
                    )
                    notes = getattr(item, "notes", None) or ""
                    if notes:
                        left.caption(notes)
                    right.link_button("Open", item.sharepoint_url.strip(), width="stretch")
                    st.divider()
        if invalid_documents:
            with st.expander(f"⚠️ Records without valid links ({len(invalid_documents)})"):
                st.dataframe(
                    pd.DataFrame([
                        {
                            "Document": item.cv_file_name or "Document",
                            "Type": item.file_type or "N/A",
                            "Status": item.cv_status or "N/A",
                            "Modified": item.modified_date,
                        }
                        for item in invalid_documents
                    ]),
                    width="stretch",
                    hide_index=True,
                )

with edit_tab:
    st.subheader("✏️ Edit My Profile")
    st.info("Update your personal/contact information and career preferences here. Organisation-controlled fields and assessment results cannot be changed from USER access.")
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

st.caption("Your dashboard is restricted to your linked personnel record. Organisation-wide analytics and administration remain available only to authorised administrators.")
