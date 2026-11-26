"""Personnel administration — directory-first CRUD workspace for v2."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import hashlib
import json

import pandas as pd
import streamlit as st

from components.navigation import render_navigation, render_header
from config import (
    ASSESSMENT_LEVELS,
    CHAT_STATUS_OPTIONS,
    COMP_TYPES,
    COMPETENCY_FULLNAMES,
    DEPARTMENTS,
    SCORE_COLS,
    POSITIONS,
    POSITION_TO_SG,
)
from core.auth import current_user
from core.bootstrap import get_master_data, open_session
from models import AssessmentImportBatch
from services.personnel_service import (
    add as add_personnel,
    all as get_all_personnel,
    delete as delete_personnel,
    update as update_personnel,
)
from services.assessment_service import (
    get_assessment_history,
    get_assessment_scores,
    save_assessment_transaction,
    create_reviewed_assessment_import,
    apply_reviewed_assessment_import,
)
from services.assessment_import_service import parse_assessment_upload


# ---------------------------------------------------------------------------
# Shared helpers. Persistence rules remain in the existing service/db_ops
# modules; this page only shapes the admin experience and calls those services.
# ---------------------------------------------------------------------------

def _current_admin_actor() -> str:
    actor = current_user() or {}
    return str(actor.get("username") or actor.get("display_name") or "system")[:100]


def _is_missing(value) -> bool:
    try:
        return value is None or bool(pd.isna(value))
    except (TypeError, ValueError):
        return value is None


def _text(row, key, default="") -> str:
    value = row.get(key, default) if row is not None else default
    if _is_missing(value):
        return default
    return str(value).strip()


def _normalise_staff_id(value) -> str:
    if _is_missing(value):
        return ""
    key = str(value).strip()
    if key.endswith(".0") and key[:-2].isdigit():
        key = key[:-2]
    return key.casefold()


def _safe_int(value, default=0, minimum=None, maximum=None) -> int:
    if _is_missing(value):
        return default
    if isinstance(value, (pd.Timestamp, datetime, date)):
        number = int(value.year)
    else:
        numeric = pd.to_numeric(value, errors="coerce")
        if pd.notna(numeric):
            number = int(round(float(numeric)))
        else:
            parsed = pd.to_datetime(value, errors="coerce")
            if pd.isna(parsed):
                return default
            number = int(parsed.year)
    if minimum is not None and number < minimum:
        return default
    if maximum is not None and number > maximum:
        return default
    return number


def _safe_birth_year(value, default=1980) -> int:
    if _is_missing(value):
        return default
    if isinstance(value, (pd.Timestamp, datetime, date)):
        year = int(value.year)
        return year if 1950 <= year <= 2010 else default
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.notna(numeric):
        number = float(numeric)
        if 1950 <= number <= 2010:
            return int(round(number))
        if 10000 <= number <= 60000:
            parsed = pd.to_datetime(number, unit="D", origin="1899-12-30", errors="coerce")
            if pd.notna(parsed) and 1950 <= parsed.year <= 2010:
                return int(parsed.year)
        if abs(number) > 1_000_000_000:
            parsed = pd.to_datetime(int(number), unit="ns", errors="coerce")
            if pd.notna(parsed) and 1950 <= parsed.year <= 2010:
                return int(parsed.year)
    parsed = pd.to_datetime(value, errors="coerce")
    return int(parsed.year) if pd.notna(parsed) and 1950 <= parsed.year <= 2010 else default


def _number(value, default=0.0, minimum=0.0, maximum=600.0) -> float:
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.notna(numeric) and minimum <= float(numeric) <= maximum:
        return float(numeric)
    return float(default)


def _numeric_widget_max(value, expected_max=60.0):
    """Keep valid legacy values visible without silently truncating them."""
    current = _number(value, minimum=0.0, maximum=600.0)
    return min(600.0, max(float(expected_max), current * 1.25))


def _optional_date(value):
    """Return a real date or None; never invent today's date for blank fields."""
    if _is_missing(value) or str(value).strip() in {"", "NaT", "nan", "None"}:
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.date()


def _first_optional_date(*values):
    """Return the first valid date, ignoring NaT and other blank values."""
    for value in values:
        parsed = _optional_date(value)
        if parsed is not None:
            return parsed
    return None


def _assessment_level_options(source_df, current_value=None):
    options = ["Not specified", *ASSESSMENT_LEVELS]
    seen = {str(value).casefold() for value in options}
    if source_df is not None and not source_df.empty and "Assessment Level" in source_df.columns:
        for raw in source_df["Assessment Level"].dropna():
            value = str(raw).strip()
            if value and value.casefold() not in seen:
                options.append(value)
                seen.add(value.casefold())
    if current_value:
        value = str(current_value).strip()
        if value and value.casefold() not in seen:
            options.append(value)
    return options


# Map database fields to the historical workbook headers used by the existing
# admin form and assessment-entry defaults. Database values win when populated.
_DB_TO_DISPLAY = {
    "Name": "name",
    "Staff ID": "staff_id",
    "Email Address": "email",
    "Gender": "gender",
    "Age": "age",
    "Birth Year": "birth_year",
    "Nationality": "nationality",
    "Employment Category": "employment_category",
    "Department": "department",
    "Section Name": "section_name",
    "Unit Name": "unit_name",
    "Sub Unit": "sub_unit",
    "Staff Position": "staff_position",
    "SG": "sg",
    "Joining Date": "joining_date",
    "Contract Expire Date": "contract_expire_date",
    "Years in PET": "years_in_pet",
    "Years of RE Experience": "years_re_experience",
    "Years in Salary Grade": "sg_years",
    "SG Start Date": "sg_start_date",
    "Date of Appointment to Current Grade": "sg_start_date",
    "Age Promoted to Staff or Principal": "age_promoted",
    "Current Assignment": "current_assignment",
    "Current Location:": "current_assignment",
    "Assignment Date": "assignment_date",
    "Date in Position": "assignment_date",
    "Length in Current Assignment": "assignment_length",
    "Chat Status": "chat_status",
    "Chat Date": "chat_date",
    "Assessment Level": "assessment_level",
    "Last Assessment Date": "last_assessment_date",
    "Last Assesment Date": "last_assessment_date",
    "Sub-Disciplines": "sub_disciplines",
    "Potential": "potential",
    "Strength": "strength",
    "Recommendation": "recommendation",
    "Resource/SME": "resource_sme",
    "Interest": "interest",
    "Preference": "preference",
    "Comment/Suggestion": "comment",
    "Comment": "comment",
    "Assesor1": "assessor1",
    "Assessor1": "assessor1",
    "Assessor2": "assessor2",
    "Supervisor": "supervisor",
    "Remarks": "remarks",
}


def _profile_row(person: dict, master_df: pd.DataFrame) -> dict:
    """Combine the DB profile with workbook score columns for legacy parity."""
    staff_key = _normalise_staff_id(person.get("staff_id"))
    profile = {}
    if (
        master_df is not None
        and not master_df.empty
        and "Staff ID" in master_df.columns
        and staff_key
    ):
        matches = master_df[
            master_df["Staff ID"].map(_normalise_staff_id) == staff_key
        ]
        if not matches.empty:
            profile = matches.iloc[0].to_dict()

    for display_column, db_column in _DB_TO_DISPLAY.items():
        value = person.get(db_column)
        # Assessment Level is intentionally nullable in SQLite and is already
        # treated as authoritative by the shared data reader.
        if db_column == "assessment_level":
            profile[display_column] = value
        elif not _is_missing(value) and not (
            isinstance(value, str) and not value.strip()
        ):
            profile[display_column] = value

    profile["id"] = person.get("id")
    profile["Staff ID"] = person.get("staff_id")
    profile["Name"] = person.get("name")
    return profile


def _load_people(include_deleted=True) -> pd.DataFrame:
    session = open_session()
    try:
        records = get_all_personnel(session, include_deleted=include_deleted)
        return records if records is not None else pd.DataFrame()
    finally:
        session.close()


def _save_personnel_form(form_key: str, prefix: str, row: dict | None, master_df):
    """Render a structured create/edit form and return (submitted, payload)."""
    source = row or {}
    is_add = row is None
    if is_add and st.session_state.pop("_reset_add_personnel_form_next_run", False):
        for state_key in list(st.session_state.keys()):
            if state_key.startswith(f"{prefix}_"):
                st.session_state.pop(state_key, None)

    gender_value = _text(source, "Gender", "Not specified") or "Not specified"
    gender_options = ["Not specified", "M", "F", "Other"]
    if gender_value not in gender_options:
        gender_options.append(gender_value)

    employment_value = _text(source, "Employment Category", "Not specified") or "Not specified"
    employment_options = ["Not specified", "Permanent", "CDH"]
    if employment_value not in employment_options:
        employment_options.append(employment_value)

    department_options = list(DEPARTMENTS[:-1]) or ["Not specified"]
    department_value = _text(source, "Department", department_options[0]) or department_options[0]
    if department_value and department_value not in department_options:
        department_options.append(department_value)

    position_options = list(POSITIONS[:-1]) or ["Not specified"]
    position_value = _text(source, "Staff Position", position_options[0]) or position_options[0]
    if position_value and position_value not in position_options:
        position_options.append(position_value)

    chat_options = list(CHAT_STATUS_OPTIONS)
    chat_value = _text(source, "Chat Status", "No Need") or "No Need"
    if chat_value not in chat_options:
        chat_options.append(chat_value)

    assessment_options = _assessment_level_options(
        master_df, _text(source, "Assessment Level")
    )
    assessment_value = _text(source, "Assessment Level", "Not specified") or "Not specified"
    if assessment_value not in assessment_options:
        assessment_options.append(assessment_value)

    with st.form(form_key, clear_on_submit=False):
        st.caption("Fields marked * are required. Dates remain blank until a date is deliberately entered.")

        with st.expander("1 · Personal identity", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input("Full name *", _text(source, "Name"), key=f"{prefix}_name")
                staff_id = st.text_input("Staff ID *", _text(source, "Staff ID"), key=f"{prefix}_staff_id")
                email = st.text_input("Email address", _text(source, "Email Address"), key=f"{prefix}_email")
            with c2:
                gender = st.selectbox(
                    "Gender", gender_options,
                    index=gender_options.index(gender_value),
                    key=f"{prefix}_gender",
                )
                nationality = st.text_input(
                    "Nationality", _text(source, "Nationality", "Malaysia"),
                    key=f"{prefix}_nationality",
                )
                age = st.number_input(
                    "Age", min_value=18, max_value=100,
                    value=_safe_int(source.get("Age"), 30, 18, 100),
                    step=1, format="%d", key=f"{prefix}_age",
                )
                birth_year = st.number_input(
                    "Birth year", min_value=1950, max_value=2010,
                    value=_safe_birth_year(source.get("Birth Year")),
                    step=1, format="%d", key=f"{prefix}_birth_year",
                )

        with st.expander("2 · Employment placement", expanded=True):
            c1, c2 = st.columns(2)
            with c1:
                employment_category = st.selectbox(
                    "Employment category", employment_options,
                    index=employment_options.index(employment_value),
                    key=f"{prefix}_employment_category",
                    help="Use Permanent or CDH so dashboard filters remain consistent.",
                )
                department = st.selectbox(
                    "Department", department_options,
                    index=department_options.index(department_value),
                    key=f"{prefix}_department",
                )
                section_name = st.text_input(
                    "Section", _text(source, "Section Name"),
                    key=f"{prefix}_section",
                )
                unit_name = st.text_input(
                    "Unit", _text(source, "Unit Name"),
                    key=f"{prefix}_unit",
                )
                sub_unit = st.text_input(
                    "Sub-unit", _text(source, "Sub Unit"),
                    key=f"{prefix}_subunit",
                )
            with c2:
                staff_position = st.selectbox(
                    "Staff position", position_options,
                    index=position_options.index(position_value),
                    key=f"{prefix}_position",
                )
                sg_default = _text(source, "SG") or POSITION_TO_SG.get(staff_position, "")
                sg = st.text_input("Salary grade (SG)", sg_default, key=f"{prefix}_sg")
                current_assignment = st.text_input(
                    "Current assignment / location",
                    _text(source, "Current Assignment") or _text(source, "Current Location:"),
                    key=f"{prefix}_assignment",
                )
                joining_date = st.date_input(
                    "Joining date", value=_optional_date(source.get("Joining Date")),
                    format="DD/MM/YYYY", key=f"{prefix}_joining",
                )
                contract_expire_date = st.date_input(
                    "Contract expiry date", value=_optional_date(source.get("Contract Expire Date")),
                    format="DD/MM/YYYY", key=f"{prefix}_contract",
                )

        with st.expander("3 · Career and assessment profile", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                years_in_pet_value = _number(source.get("Years in PET"))
                years_re_experience_value = _number(source.get("Years of RE Experience"))
                sg_years_value = _number(source.get("Years in Salary Grade"))
                years_in_pet = st.number_input(
                    "Years in PET", min_value=0.0,
                    max_value=_numeric_widget_max(source.get("Years in PET")),
                    value=years_in_pet_value, step=0.5,
                    key=f"{prefix}_pet",
                )
                years_re_experience = st.number_input(
                    "Years of RE experience", min_value=0.0,
                    max_value=_numeric_widget_max(source.get("Years of RE Experience")),
                    value=years_re_experience_value, step=0.5,
                    key=f"{prefix}_re",
                )
                sg_years = st.number_input(
                    "Years in salary grade", min_value=0.0,
                    max_value=_numeric_widget_max(source.get("Years in Salary Grade")),
                    value=sg_years_value, step=0.5,
                    key=f"{prefix}_sgyears",
                )
                unusual_tenure = {
                    "Years in PET": years_in_pet_value,
                    "Years of RE experience": years_re_experience_value,
                    "Years in salary grade": sg_years_value,
                }
                unusual_tenure = {
                    label: value for label, value in unusual_tenure.items()
                    if value > 60.0
                }
                if unusual_tenure:
                    details = ", ".join(
                        f"{label}: {value:g}" for label, value in unusual_tenure.items()
                    )
                    st.warning(
                        "This record contains tenure values above 60 years "
                        f"({details}). Existing values are preserved for review; "
                        "they have not been automatically changed."
                    )
                age_promoted = st.number_input(
                    "Age promoted to Staff / Principal", 18.0, 100.0,
                    _number(source.get("Age Promoted to Staff or Principal"), 30, 18, 100),
                    1.0, key=f"{prefix}_ageprom",
                )
            with c2:
                assignment_length = st.number_input(
                    "Length in current assignment (months)", 0.0, 600.0,
                    _number(source.get("Length in Current Assignment")), 1.0,
                    key=f"{prefix}_assignlen",
                )
                assignment_date = st.date_input(
                    "Assignment start date",
                    value=_first_optional_date(source.get("Assignment Date"), source.get("Date in Position")),
                    format="DD/MM/YYYY", key=f"{prefix}_assignmentdate",
                )
                sg_start_date = st.date_input(
                    "Salary grade start date",
                    value=_first_optional_date(source.get("SG Start Date"), source.get("Date of Appointment to Current Grade")),
                    format="DD/MM/YYYY", key=f"{prefix}_sgstart",
                )
                chat_status = st.selectbox(
                    "Career chat status", chat_options,
                    index=chat_options.index(chat_value), key=f"{prefix}_chat",
                )
                chat_date = st.date_input(
                    "Career chat date", value=_optional_date(source.get("Chat Date")),
                    format="DD/MM/YYYY", key=f"{prefix}_chatdate",
                )
                assessment_level = st.selectbox(
                    "Assessment level", assessment_options,
                    index=assessment_options.index(assessment_value),
                    key=f"{prefix}_level",
                )
                last_assessment_date = st.date_input(
                    "Last assessment date",
                    value=_first_optional_date(source.get("Last Assessment Date"), source.get("Last Assesment Date")),
                    format="DD/MM/YYYY", key=f"{prefix}_lastdate",
                )

        with st.expander("4 · Development notes and contacts", expanded=False):
            c1, c2 = st.columns(2)
            with c1:
                sub_disciplines = st.text_input(
                    "Sub-disciplines", _text(source, "Sub-Disciplines"),
                    key=f"{prefix}_subdisc",
                )
                potential = st.text_input(
                    "Potential", _text(source, "Potential"),
                    key=f"{prefix}_potential",
                )
                resource_sme = st.text_input(
                    "Resource / SME", _text(source, "Resource/SME"),
                    key=f"{prefix}_resource",
                )
                interest = st.text_input(
                    "Interest", _text(source, "Interest"),
                    key=f"{prefix}_interest",
                )
                preference = st.text_input(
                    "Preference", _text(source, "Preference"),
                    key=f"{prefix}_preference",
                )
            with c2:
                assessor1 = st.text_input(
                    "Assessor 1", _text(source, "Assesor1") or _text(source, "Assessor1"),
                    key=f"{prefix}_assessor1",
                )
                assessor2 = st.text_input(
                    "Assessor 2", _text(source, "Assessor2"),
                    key=f"{prefix}_assessor2",
                )
                supervisor = st.text_input(
                    "Supervisor", _text(source, "Supervisor"),
                    key=f"{prefix}_supervisor",
                )
                strength = st.text_area(
                    "Strengths", _text(source, "Strength"),
                    height=100, key=f"{prefix}_strength",
                )
                recommendation = st.text_area(
                    "Recommendations", _text(source, "Recommendation"),
                    height=100, key=f"{prefix}_recommendation",
                )
                comment = st.text_area(
                    "Comments / suggestions",
                    _text(source, "Comment/Suggestion") or _text(source, "Comment"),
                    height=100, key=f"{prefix}_comment",
                )
                remarks = st.text_area(
                    "Remarks", _text(source, "Remarks"),
                    height=100, key=f"{prefix}_remarks",
                )

        submitted = st.form_submit_button(
            "Create personnel record" if is_add else "Save profile changes",
            type="primary", use_container_width=True,
        )

    payload = {
        "name": name.strip(),
        "staff_id": staff_id.strip(),
        "email": email.strip() or None,
        "gender": None if gender == "Not specified" else gender,
        "age": int(age) if age is not None else None,
        "birth_year": int(birth_year) if birth_year is not None else None,
        "nationality": nationality.strip() or None,
        "employment_category": None if employment_category == "Not specified" else employment_category,
        "department": department,
        "section_name": section_name.strip() or None,
        "unit_name": unit_name.strip() or None,
        "sub_unit": sub_unit.strip() or None,
        "staff_position": staff_position,
        "sg": sg.strip() or POSITION_TO_SG.get(staff_position, ""),
        "joining_date": joining_date,
        "contract_expire_date": contract_expire_date,
        "years_in_pet": float(years_in_pet),
        "years_re_experience": float(years_re_experience),
        "sg_years": float(sg_years),
        "sg_start_date": sg_start_date,
        "age_promoted": float(age_promoted),
        "current_assignment": current_assignment.strip() or None,
        "assignment_date": assignment_date,
        "assignment_length": float(assignment_length),
        "chat_status": chat_status,
        "chat_date": chat_date,
        "assessment_level": None if assessment_level == "Not specified" else assessment_level,
        "last_assessment_date": last_assessment_date,
        "sub_disciplines": sub_disciplines.strip() or None,
        "potential": potential.strip() or None,
        "strength": strength.strip() or None,
        "recommendation": recommendation.strip() or None,
        "resource_sme": resource_sme.strip() or None,
        "interest": interest.strip() or None,
        "preference": preference.strip() or None,
        "comment": comment.strip() or None,
        "assessor1": assessor1.strip() or None,
        "assessor2": assessor2.strip() or None,
        "supervisor": supervisor.strip() or None,
        "remarks": remarks.strip() or None,
    }
    return submitted, payload


# ---------------------------------------------------------------------------
# Page and data loading
# ---------------------------------------------------------------------------

render_navigation()
render_header(
    "👥 Personnel & Database Management",
    "Maintain personnel profiles separately from competency assessments, with a dedicated assessment history.",
)

# Workbook data is used only as a supplementary source for score/assessment
# defaults. The directory and CRUD identity come from the existing DB service.
master_df = pd.DataFrame()
master_data_error = None
try:
    loaded = get_master_data()
    if isinstance(loaded, pd.DataFrame):
        master_df = loaded
except Exception as exc:
    master_data_error = str(exc)

try:
    all_people = _load_people(include_deleted=True)
except Exception as exc:
    st.error(f"Unable to load personnel records from the database: {exc}")
    st.stop()

if all_people.empty:
    all_people = pd.DataFrame(
        columns=[
            "id", "staff_id", "name", "department", "section_name", "sg",
            "employment_category", "staff_position", "is_deleted", "is_active",
            "updated_at",
        ]
    )

for column, default in {
    "is_deleted": False,
    "is_active": True,
    "staff_id": "",
    "name": "",
    "department": "",
    "section_name": "",
    "sg": "",
    "employment_category": "",
    "staff_position": "",
}.items():
    if column not in all_people.columns:
        all_people[column] = default

all_people["is_deleted"] = all_people["is_deleted"].fillna(False).astype(bool)
all_people["is_active"] = all_people["is_active"].fillna(True).astype(bool)
active_people = all_people[~all_people["is_deleted"]].copy()
archived_people = all_people[all_people["is_deleted"]].copy()

available_count = len(active_people)
permanent_count = int(
    active_people["employment_category"].astype(str).str.strip().str.casefold().eq("permanent").sum()
)
cdh_count = int(
    active_people["employment_category"].astype(str).str.strip().str.casefold().eq("cdh").sum()
)

metric_cols = st.columns(4)
metric_cols[0].metric("Available records", f"{available_count:,}")
metric_cols[1].metric("Permanent", f"{permanent_count:,}")
metric_cols[2].metric("CDH", f"{cdh_count:,}")
metric_cols[3].metric("Archived", f"{len(archived_people):,}")

st.caption(
    "The directory is database-backed. Workbook data is used only to supplement "
    "historical competency and assessment values where available."
)
if master_data_error:
    st.info(
        "Workbook-based score prefill is unavailable. Personnel CRUD remains "
        "available from the database. Details: " + master_data_error
    )

directory_tab, add_tab, edit_tab, assessment_tab, archive_tab = st.tabs(
    [
        "📋 Personnel Directory",
        "➕ Add Personnel",
        "✏️ Edit Profile",
        "🧾 Assessment Management",
        "🗄️ Archive & Restore",
    ]
)


# ---------------------------------------------------------------------------
# Personnel Directory
# ---------------------------------------------------------------------------

with directory_tab:
    st.subheader("Personnel Directory")
    st.caption("Search and filter active database records. Select a row to carry that employee into Edit Profile.")

    f1, f2, f3, f4 = st.columns([2.4, 1.3, 1.3, 1.0])
    with f1:
        search_term = st.text_input(
            "Search personnel",
            placeholder="Name, Staff ID or department",
            key="personnel_directory_search",
        ).strip().casefold()
    with f2:
        departments = sorted(
            value for value in active_people["department"].dropna().astype(str).unique()
            if value.strip()
        )
        department_filter = st.selectbox(
            "Department", ["All departments", *departments],
            key="personnel_directory_department",
        )
    with f3:
        employment_values = sorted(
            value for value in active_people["employment_category"].dropna().astype(str).unique()
            if value.strip()
        )
        employment_filter = st.selectbox(
            "Employment", ["All types", *employment_values],
            key="personnel_directory_employment",
        )
    with f4:
        grades = sorted(
            value for value in active_people["sg"].dropna().astype(str).unique()
            if value.strip()
        )
        grade_filter = st.selectbox(
            "Salary grade", ["All grades", *grades],
            key="personnel_directory_grade",
        )

    filtered_people = active_people.copy()
    if search_term:
        searchable = (
            filtered_people[["name", "staff_id", "department", "section_name", "email"]]
            if "email" in filtered_people.columns
            else filtered_people[["name", "staff_id", "department", "section_name"]]
        )
        mask = searchable.fillna("").astype(str).apply(
            lambda column: column.str.casefold().str.contains(search_term, regex=False)
        ).any(axis=1)
        filtered_people = filtered_people[mask]
    if department_filter != "All departments":
        filtered_people = filtered_people[
            filtered_people["department"].astype(str) == department_filter
        ]
    if employment_filter != "All types":
        filtered_people = filtered_people[
            filtered_people["employment_category"].astype(str) == employment_filter
        ]
    if grade_filter != "All grades":
        filtered_people = filtered_people[filtered_people["sg"].astype(str) == grade_filter]

    directory_display = pd.DataFrame(
        {
            "Name": filtered_people["name"].fillna(""),
            "Staff ID": filtered_people["staff_id"].fillna(""),
            "Position": filtered_people["staff_position"].fillna(""),
            "Department": filtered_people["department"].fillna(""),
            "Section": filtered_people["section_name"].fillna(""),
            "Employment": filtered_people["employment_category"].fillna(""),
            "SG": filtered_people["sg"].fillna(""),
            "Status": filtered_people["is_active"].map(
                lambda value: "Active" if bool(value) else "Inactive"
            ),
        },
        index=filtered_people.index,
    )

    st.caption(f"Showing {len(filtered_people):,} of {available_count:,} available records.")
    if filtered_people.empty:
        st.info("No personnel match the current search and filters. Clear a filter or add a new record.")
    else:
        directory_key = hashlib.sha1(
            ",".join(str(value) for value in filtered_people["id"].tolist()).encode("utf-8")
        ).hexdigest()[:12]
        selection_event = st.dataframe(
            directory_display,
            width="stretch",
            hide_index=True,
            height=420,
            on_select="rerun",
            selection_mode="single-row",
            key=f"personnel_directory_{directory_key}",
        )
        selected_rows = list(selection_event.selection.rows)
        if selected_rows:
            selected_index = int(selected_rows[0])
            selected_person = filtered_people.iloc[selected_index]
            selected_id = int(selected_person["id"])
            st.session_state["admin_selected_person_id"] = selected_id

        selected_id = st.session_state.get("admin_selected_person_id")
        selected_record = (
            active_people[active_people["id"] == selected_id]
            if selected_id is not None and "id" in active_people.columns
            else pd.DataFrame()
        )
        if not selected_record.empty:
            person = selected_record.iloc[0]
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.markdown(f"**{person.get('name', 'Unnamed personnel')}**")
                    st.caption(
                        f"Staff ID: {person.get('staff_id', '—')} · "
                        f"{person.get('staff_position', 'Position not specified')} · "
                        f"{person.get('department', 'Department not specified')}"
                    )
                with c2:
                    st.info("Selected")
                st.caption("This employee is selected for the Edit Profile and Assessment Entry sections.")
        else:
            st.info("Select a row in the directory to choose an employee.")

    if archived_people.empty:
        st.caption("There are no archived personnel records.")


# ---------------------------------------------------------------------------
# Add Personnel — available even when the database is empty
# ---------------------------------------------------------------------------

with add_tab:
    st.subheader("Add a new personnel record")
    st.caption(
        "Register one employee directly in the database. For large batches, "
        "use Admin: Import Data instead."
    )
    submitted, payload = _save_personnel_form(
        "add_personnel_form_v2", "add_personnel", None, master_df
    )
    if submitted:
        if not payload["name"]:
            st.error("Full name is required.")
        elif not payload["staff_id"]:
            st.error("Staff ID is required.")
        else:
            session = open_session()
            try:
                ok, message, new_id = add_personnel(
                    session, payload, changed_by=_current_admin_actor()
                )
                if ok:
                    st.success(f"Personnel record created: {payload['name']} (Staff ID {payload['staff_id']}).")
                    st.cache_data.clear()
                    st.session_state["admin_selected_person_id"] = new_id
                    st.session_state["_reset_add_personnel_form_next_run"] = True
                    st.rerun()
                else:
                    st.error(message)
            except Exception as exc:
                session.rollback()
                st.error(f"Unable to create personnel record: {exc}")
            finally:
                session.close()


# ---------------------------------------------------------------------------
# Edit Personnel — separate from creation
# ---------------------------------------------------------------------------

with edit_tab:
    st.subheader("Edit personnel profile")
    if active_people.empty:
        st.info("There are no active database records to edit yet. Use Add Personnel to create the first record.")
    else:
        edit_id = st.session_state.get("admin_selected_person_id")
        selected_record = (
            active_people[active_people["id"] == edit_id]
            if edit_id is not None
            else pd.DataFrame()
        )
        if selected_record.empty:
            st.info("Choose an employee in the Personnel Directory first, then open this section to edit their profile.")
        else:
            db_row = selected_record.iloc[0].to_dict()
            profile = _profile_row(db_row, master_df)
            with st.container(border=True):
                c1, c2, c3 = st.columns(3)
                c1.metric("Staff ID", str(db_row.get("staff_id") or "—"))
                c2.metric("Department", str(db_row.get("department") or "—"))
                c3.metric("Salary grade", str(db_row.get("sg") or "—"))
                updated_at = db_row.get("updated_at")
                if not _is_missing(updated_at):
                    st.caption(f"Last updated: {pd.to_datetime(updated_at).strftime('%d %b %Y, %H:%M')}")

            st.caption("You are editing the employee selected in the Personnel Directory.")
            submitted, payload = _save_personnel_form(
                f"edit_personnel_form_{edit_id}",
                f"edit_personnel_{edit_id}",
                profile,
                master_df,
            )
            if submitted:
                if not payload["name"]:
                    st.error("Full name is required.")
                elif not payload["staff_id"]:
                    st.error("Staff ID is required.")
                else:
                    session = open_session()
                    try:
                        ok, message = update_personnel(
                            session, edit_id, payload,
                            changed_by=_current_admin_actor(),
                        )
                        if ok:
                            st.success(f"Profile updated for {payload['name']}.")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error(message)
                    except Exception as exc:
                        session.rollback()
                        st.error(f"Unable to update personnel profile: {exc}")
                    finally:
                        session.close()


# ---------------------------------------------------------------------------
# Assessment Management — entry, competency matrix, and assessment history
# ---------------------------------------------------------------------------

with assessment_tab:
    st.subheader("Assessment Management")
    st.caption(
        "Assessment records are maintained separately from employee profiles. "
        "Each submission stores one dated assessment and its complete 24-competency matrix."
    )

    saved_notice = st.session_state.pop("_assessment_saved_notice", None)
    if saved_notice:
        st.success(saved_notice)

    if active_people.empty:
        st.info("Add or import personnel before creating an assessment.")
    else:
        assessment_labels = {
            int(record["id"]): (
                f"{record['name']} · {record['staff_id']} · "
                f"{record.get('department') or 'Department not specified'}"
            )
            for _, record in active_people.sort_values(["name", "staff_id"]).iterrows()
        }
        assessment_label_to_id = {
            label: person_id for person_id, label in assessment_labels.items()
        }
        current_assessment_id = st.session_state.get("admin_selected_person_id")
        assessment_options = list(assessment_label_to_id)
        assessment_default = (
            assessment_options.index(assessment_labels[current_assessment_id])
            if current_assessment_id in assessment_labels
            else 0
        )
        assessment_person_label = st.selectbox(
            "Employee being assessed",
            assessment_options,
            index=assessment_default,
            key="admin_assessment_person_picker",
            help="Choose the employee whose assessment you are recording or reviewing.",
        )
        assessment_person_id = assessment_label_to_id[assessment_person_label]
        assessment_person = active_people[
            active_people["id"] == assessment_person_id
        ].iloc[0].to_dict()
        assessment_row = _profile_row(assessment_person, master_df)

        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f"**{assessment_person.get('name', 'Unnamed')}**")
            c2.metric("Staff position", assessment_person.get("staff_position") or "—")
            c3.metric("Department", assessment_person.get("department") or "—")
            c4.metric("Salary grade", assessment_person.get("sg") or "—")

        history = []
        latest_scores = {}
        history_load_error = None
        history_session = open_session()
        try:
            history = get_assessment_history(history_session, assessment_person_id)
            if history:
                latest_scores = get_assessment_scores(
                    history_session, history[0]["id"]
                )
        except Exception as exc:
            history_load_error = str(exc)
        finally:
            history_session.close()

        if history_load_error:
            st.warning(
                "Assessment history could not be loaded. New assessment entry remains "
                f"available, but database prefill may be incomplete. Details: {history_load_error}"
            )

        entry_tab, import_tab, history_tab = st.tabs(
            [
                "➕ New Assessment",
                "📥 Upload Assessment",
                f"🕘 Assessment History ({len(history)})",
            ]
        )

        with entry_tab:
            st.markdown("#### Assessment details")
            st.caption(
                "Enter the assessment metadata, then complete the competency matrix below. "
                "The save operation validates and commits the full record as one transaction."
            )

            latest_history = history[0] if history else {}
            assessment_nonce = int(
                st.session_state.get(f"assessment_form_nonce_{assessment_person_id}", 0)
            )
            assessment_form_key = (
                f"assessment_entry_form_{assessment_person_id}_{assessment_nonce}"
            )
            with st.form(assessment_form_key, clear_on_submit=False):
                c1, c2 = st.columns(2)
                with c1:
                    assessment_date = st.date_input(
                        "Assessment date *",
                        value=date.today(),
                        format="DD/MM/YYYY",
                        key=f"admin_assessment_date_{assessment_person_id}_{assessment_nonce}",
                    )
                    level_options = _assessment_level_options(
                        master_df, _text(assessment_row, "Assessment Level")
                    )
                    current_level = _text(assessment_row, "Assessment Level") or "Not specified"
                    if current_level not in level_options:
                        level_options.append(current_level)
                    level = st.selectbox(
                        "Assessment level",
                        level_options,
                        index=level_options.index(current_level),
                        key=f"admin_assessment_level_{assessment_person_id}_{assessment_nonce}",
                    )
                with c2:
                    assessor1_entry = st.text_input(
                        "Assessor 1",
                        value=str(latest_history.get("assessor1") or _text(assessment_row, "Assessor1")),
                        key=f"admin_assessor1_{assessment_person_id}_{assessment_nonce}",
                    )
                    assessor2_entry = st.text_input(
                        "Assessor 2",
                        value=str(latest_history.get("assessor2") or _text(assessment_row, "Assessor2")),
                        key=f"admin_assessor2_{assessment_person_id}_{assessment_nonce}",
                    )
                    supervisor_entry = st.text_input(
                        "Supervisor",
                        value=str(latest_history.get("supervisor") or _text(assessment_row, "Supervisor")),
                        key=f"admin_supervisor_{assessment_person_id}_{assessment_nonce}",
                    )
                remarks_entry = st.text_area(
                    "Assessment remarks",
                    value=str(latest_history.get("remarks") or _text(assessment_row, "Remarks")),
                    height=90,
                    key=f"admin_assessment_remarks_{assessment_person_id}_{assessment_nonce}",
                )

                matrix_rows = []
                for competency_type, info in COMP_TYPES.items():
                    for code in info["cols"]:
                        previous = latest_scores.get(code, {})
                        workbook_actual = pd.to_numeric(
                            assessment_row.get(code), errors="coerce"
                        )
                        workbook_target = pd.to_numeric(
                            assessment_row.get(f"R-{code}"), errors="coerce"
                        )
                        previous_actual = previous.get("actual")
                        previous_target = previous.get("req")
                        if (
                            previous_actual is not None
                            and pd.notna(previous_actual)
                            and 0.0 <= float(previous_actual) <= 5.0
                        ):
                            actual_default = float(previous_actual)
                        elif pd.notna(workbook_actual) and 0.0 <= float(workbook_actual) <= 5.0:
                            actual_default = float(workbook_actual)
                        else:
                            actual_default = 0.0
                        if (
                            previous_target is not None
                            and pd.notna(previous_target)
                            and 0.0 <= float(previous_target) <= 5.0
                        ):
                            target_default = float(previous_target)
                        elif pd.notna(workbook_target) and 0.0 <= float(workbook_target) <= 5.0:
                            target_default = float(workbook_target)
                        else:
                            target_default = 3.0

                        matrix_rows.append(
                            {
                                "Code": code,
                                "Competency": COMPETENCY_FULLNAMES.get(code, code),
                                "Group": info["label"],
                                "Actual": actual_default,
                                "Target": target_default,
                            }
                        )

                score_matrix = pd.DataFrame(
                    matrix_rows,
                    columns=["Code", "Competency", "Group", "Actual", "Target"],
                )
                st.markdown("#### Competency matrix")
                st.caption(
                    "Edit Actual and Target scores from 0 to 5. Values are prefilled from "
                    "the latest saved assessment, then the master workbook where available."
                )
                edited_matrix = st.data_editor(
                    score_matrix,
                    key=f"admin_assessment_matrix_{assessment_person_id}_{assessment_nonce}",
                    width="stretch",
                    height=690,
                    hide_index=True,
                    num_rows="fixed",
                    disabled=["Code", "Competency", "Group"],
                    column_config={
                        "Code": st.column_config.TextColumn("Code", width="small"),
                        "Competency": st.column_config.TextColumn("Competency", width="large"),
                        "Group": st.column_config.TextColumn("Group", width="medium"),
                        "Actual": st.column_config.NumberColumn(
                            "Actual", min_value=0.0, max_value=5.0, step=0.5,
                            format="%.1f", required=True,
                        ),
                        "Target": st.column_config.NumberColumn(
                            "Target", min_value=0.0, max_value=5.0, step=0.5,
                            format="%.1f", required=True,
                        ),
                    },
                )
                save_assessment = st.form_submit_button(
                    "Save assessment and all 24 scores",
                    type="primary",
                    use_container_width=True,
                )

            if save_assessment:
                score_inputs = {}
                matrix_valid = True
                try:
                    if len(edited_matrix) != len(SCORE_COLS):
                        raise ValueError(
                            f"The matrix must contain exactly {len(SCORE_COLS)} competencies."
                        )
                    for _, score_row in edited_matrix.iterrows():
                        code = str(score_row["Code"])
                        actual = pd.to_numeric(score_row["Actual"], errors="coerce")
                        target = pd.to_numeric(score_row["Target"], errors="coerce")
                        if (
                            code not in SCORE_COLS
                            or pd.isna(actual)
                            or pd.isna(target)
                            or not 0.0 <= float(actual) <= 5.0
                            or not 0.0 <= float(target) <= 5.0
                        ):
                            raise ValueError(
                                f"{code} must have valid Actual and Target scores from 0 to 5."
                            )
                        if code in score_inputs:
                            raise ValueError(f"Duplicate competency row detected: {code}.")
                        score_inputs[code] = {
                            "actual": float(actual),
                            "req": float(target),
                            "gap": round(max(float(target) - float(actual), 0.0), 2),
                        }
                    if set(score_inputs) != set(SCORE_COLS):
                        raise ValueError("One or more competency rows are missing.")
                except (KeyError, TypeError, ValueError) as exc:
                    matrix_valid = False
                    st.error(f"Assessment validation failed: {exc}")

                if matrix_valid:
                    save_session = open_session()
                    try:
                        ok, message, new_assessment_id = save_assessment_transaction(
                            save_session,
                            assessment_person_id,
                            {
                                "assessment_date": assessment_date,
                                "assessment_level": None if level == "Not specified" else level,
                                "assessor1": assessor1_entry.strip() or None,
                                "assessor2": assessor2_entry.strip() or None,
                                "supervisor": supervisor_entry.strip() or None,
                                "remarks": remarks_entry.strip() or None,
                            },
                            score_inputs,
                            actor=current_user(),
                        )
                        if ok:
                            st.cache_data.clear()
                            st.session_state["_assessment_saved_notice"] = (
                                f"Assessment #{new_assessment_id} saved for "
                                f"{assessment_person.get('name')} on "
                                f"{assessment_date:%d %b %Y}. All 24 competency scores were committed."
                            )
                            st.session_state[
                                f"assessment_form_nonce_{assessment_person_id}"
                            ] = assessment_nonce + 1
                            st.rerun()
                        else:
                            st.error(message)
                            st.info(
                                "No partial assessment was saved. Correct the issue and submit again."
                            )
                    except Exception as exc:
                        save_session.rollback()
                        st.error(
                            "Assessment was not saved. The transaction was rolled back. "
                            f"Details: {exc}"
                        )
                    finally:
                        save_session.close()

        with import_tab:
            st.markdown("#### Upload assessment working file")
            st.caption(
                "Upload the established SMA / Technology Inventory assessment workbook or a "
                "text-extractable PDF. The importer identifies B1-E2 competencies by their "
                "class tag or exact registered competency name and reads the Final Rating as "
                "the current assessment score. It does not recreate the old-to-new TI mapping."
            )

            import_notice = st.session_state.pop("_assessment_import_saved_notice", None)
            if import_notice:
                st.success(import_notice)

            import_upload = st.file_uploader(
                "Upload Excel or PDF assessment",
                type=["xlsx", "xlsm", "pdf", "txt", "tsv"],
                key=f"individual_assessment_upload_{assessment_person_id}",
                help="Excel is read from cell values. PDF must contain selectable text; scanned-image PDF is not OCR processed.",
            )

            parsed_import = None
            if import_upload is not None:
                try:
                    parsed_import = parse_assessment_upload(
                        import_upload.name,
                        import_upload.getvalue(),
                    )
                except Exception as exc:
                    st.error(f"Unable to read the assessment file: {exc}")

            if parsed_import is not None:
                source_meta = parsed_import.get("metadata", {})
                source_person_name = str(source_meta.get("person_name") or "").strip()
                source_staff_id = str(source_meta.get("staff_id") or "").strip()
                selected_person_name = str(assessment_person.get("name") or "").strip()
                selected_staff_id = str(assessment_person.get("staff_id") or "").strip()

                def _identity_key(value):
                    return "".join(char.casefold() for char in str(value or "") if char.isalnum())

                identity_issues = []
                if source_person_name and _identity_key(source_person_name) != _identity_key(selected_person_name):
                    identity_issues.append(
                        f"The uploaded file identifies {source_person_name}, but the selected personnel is {selected_person_name}."
                    )
                if source_staff_id and _normalise_staff_id(source_staff_id) != _normalise_staff_id(selected_staff_id):
                    identity_issues.append(
                        f"The uploaded Staff ID ({source_staff_id}) does not match the selected personnel Staff ID ({selected_staff_id})."
                    )

                parser_issues = parsed_import.get("issues", [])
                duplicate_issues = [
                    issue for issue in parser_issues
                    if "Duplicate competency section" in issue
                ]
                label_issues = [
                    issue for issue in parser_issues
                    if "differs from the registered catalogue" in issue
                ]
                fatal_issues = [
                    issue for issue in parser_issues
                    if "No recognised B1-E2" in issue
                ]

                overview_cols = st.columns(4)
                overview_cols[0].metric("Competencies found", f"{parsed_import['recognized_count']}/24")
                overview_cols[1].metric("Final Ratings", parsed_import["valid_final_count"])
                overview_cols[2].metric("Missing from source", parsed_import["missing_count"])
                overview_cols[3].metric("Source file", Path(import_upload.name).suffix.upper())

                if identity_issues:
                    for issue in identity_issues:
                        st.error(issue)
                elif source_person_name or source_staff_id:
                    st.success("The uploaded personnel identity matches the selected database record.")
                else:
                    st.info(
                        "No personnel identity was found in the source sheet. The import will be bound "
                        "to the employee selected above; verify the document belongs to this employee."
                    )

                if parser_issues:
                    with st.expander("Parser notes and extraction warnings", expanded=True):
                        for issue in parser_issues:
                            st.warning(issue)
                if parsed_import.get("missing_codes"):
                    with st.expander(
                        f"Competencies not present in source ({len(parsed_import['missing_codes'])})"
                    ):
                        st.caption(
                            "Missing sections are not treated as zero. When creating a new assessment "
                            "they remain unassessed; when revising an existing assessment their current "
                            "saved values are preserved."
                        )
                        st.write(", ".join(parsed_import["missing_codes"]))

                operation_label = st.radio(
                    "What should happen after approval?",
                    ["Create a new assessment record", "Revise an existing assessment"],
                    horizontal=True,
                    key=f"assessment_import_operation_{assessment_person_id}",
                    disabled=not history,
                    help=(
                        "Create preserves assessment history. Revise updates the selected assessment "
                        "record and retains an audit of its previous values."
                    ),
                )
                operation = "revise" if operation_label.startswith("Revise") else "create"
                target_assessment_id = None
                target_scores = latest_scores.copy()

                if operation == "revise":
                    history_labels = {}
                    for history_record in history:
                        history_date = (
                            history_record["assessment_date"].strftime("%d %b %Y")
                            if history_record.get("assessment_date") is not None
                            else "Undated"
                        )
                        level_label = history_record.get("assessment_level") or "Level not specified"
                        type_label = history_record.get("assessment_type") or "Assessment"
                        label = (
                            f"#{history_record['id']} · {history_date} · "
                            f"{level_label} · {type_label}"
                        )
                        history_labels[label] = int(history_record["id"])
                    target_label = st.selectbox(
                        "Assessment record to revise",
                        list(history_labels),
                        key=f"assessment_import_target_{assessment_person_id}",
                    )
                    target_assessment_id = history_labels[target_label]
                    target_session = open_session()
                    try:
                        target_scores = get_assessment_scores(
                            target_session, target_assessment_id
                        )
                    finally:
                        target_session.close()

                parsed_by_code = {
                    item["code"]: item
                    for item in parsed_import.get("competencies", [])
                }
                mapping_import = (
                    str(source_meta.get("assessment_type") or "").casefold()
                    == "technology inventory mapping"
                )
                staff_position_label = str(
                    assessment_person.get("staff_position") or ""
                ).casefold()
                salary_grade = str(assessment_person.get("sg") or "").strip().upper()
                if salary_grade in {"P7", "P8"} or "principal" in staff_position_label:
                    selected_grade_group = "Principal"
                elif salary_grade in {"P9", "P10"} or "custodian" in staff_position_label:
                    selected_grade_group = "Custodian"
                elif salary_grade in {"P5", "P6"} or "staff" in staff_position_label or "specialist" in staff_position_label:
                    selected_grade_group = "Staff"
                else:
                    selected_grade_group = "G03"

                matrix_rows = []
                grade_comparison_rows = []
                for competency_type, info in COMP_TYPES.items():
                    for code in info["cols"]:
                        source_row = parsed_by_code.get(code, {})
                        existing_row = target_scores.get(code, {})
                        comparisons = source_row.get("grade_comparisons") or {}
                        selected_comparison = comparisons.get(selected_grade_group) or {}
                        target_value = (
                            selected_comparison.get("target")
                            if mapping_import else None
                        )
                        if target_value is None:
                            target_value = existing_row.get("req")
                        if target_value is None or pd.isna(target_value):
                            workbook_target = pd.to_numeric(
                                assessment_row.get(f"R-{code}"), errors="coerce"
                            )
                            target_value = (
                                None if pd.isna(workbook_target) else float(workbook_target)
                            )
                        current_actual = existing_row.get("actual")
                        if current_actual is not None and pd.isna(current_actual):
                            current_actual = None
                        matrix_rows.append({
                            "Code": code,
                            "Competency": COMPETENCY_FULLNAMES.get(code, code),
                            "Source": (
                                "Map Result (Column G)" if mapping_import and source_row
                                else "Final Rating" if source_row
                                else "Not in file"
                            ),
                            "Current Score": current_actual,
                            "Old TI Score": source_row.get("old_ti_score"),
                            "Self Rating": source_row.get("self_rating"),
                            "Imported Result": source_row.get("final_rating"),
                            "Target": target_value,
                            "Mapping Guideline": source_row.get("mapping_guideline", ""),
                            "Evidence": source_row.get("evidence", ""),
                            "Assessor Comments": source_row.get("assessor_comments", ""),
                            "Superior Comments": source_row.get("superior_comments", ""),
                            "Assessor Approval": source_row.get("assessor_approval", ""),
                            "Superior Approval": source_row.get("superior_approval", ""),
                        })
                        for group, comparison in comparisons.items():
                            grade_comparison_rows.append({
                                "Code": code,
                                "Competency": COMPETENCY_FULLNAMES.get(code, code),
                                "Grade Group": group,
                                "% Close": comparison.get("percent_close"),
                                "Target": comparison.get("target"),
                                "Source Gap": comparison.get("gap"),
                                "Status": comparison.get("status"),
                            })

                default_date = None
                if source_meta.get("assessment_date"):
                    try:
                        default_date = date.fromisoformat(str(source_meta["assessment_date"])[:10])
                    except ValueError:
                        default_date = None

                st.markdown("#### Assessment information")
                st.caption(
                    "The source date is used when available. Leave the date unset when the source "
                    "does not state one. Assessment level and assessment type are separate fields."
                )

                import_form_key = (
                    f"assessment_import_review_form_{assessment_person_id}_"
                    f"{parsed_import['source_sha256'][:10]}_{operation}"
                )
                with st.form(import_form_key, clear_on_submit=False):
                    date_cols = st.columns(2)
                    with date_cols[0]:
                        use_assessment_date = st.checkbox(
                            "Record assessment date",
                            value=default_date is not None,
                            key=f"assessment_import_use_date_{assessment_person_id}_{parsed_import['source_sha256'][:8]}",
                        )
                        assessment_date_value = st.date_input(
                            "Assessment date",
                            value=default_date or date.today(),
                            disabled=not use_assessment_date,
                            format="DD/MM/YYYY",
                            key=f"assessment_import_date_{assessment_person_id}_{parsed_import['source_sha256'][:8]}",
                        )
                    with date_cols[1]:
                        assessment_level_value = st.text_input(
                            "Assessment level",
                            value=str(_text(assessment_row, "Assessment Level") or ""),
                            key=f"assessment_import_level_{assessment_person_id}_{parsed_import['source_sha256'][:8]}",
                        )
                        assessment_type_value = st.text_input(
                            "Assessment type",
                            value=str(source_meta.get("assessment_type") or "SMA"),
                            key=f"assessment_import_type_{assessment_person_id}_{parsed_import['source_sha256'][:8]}",
                        )

                    assessor_cols = st.columns(3)
                    with assessor_cols[0]:
                        assessor1_value = st.text_input(
                            "Assessor 1",
                            value=str(source_meta.get("assessor1") or ""),
                            key=f"assessment_import_assessor1_{assessment_person_id}_{parsed_import['source_sha256'][:8]}",
                        )
                    with assessor_cols[1]:
                        assessor2_value = st.text_input(
                            "Assessor 2",
                            value=str(source_meta.get("assessor2") or ""),
                            key=f"assessment_import_assessor2_{assessment_person_id}_{parsed_import['source_sha256'][:8]}",
                        )
                    with assessor_cols[2]:
                        supervisor_value = st.text_input(
                            "Supervisor / Superior",
                            value=str(source_meta.get("supervisor") or ""),
                            key=f"assessment_import_supervisor_{assessment_person_id}_{parsed_import['source_sha256'][:8]}",
                        )

                    edited_import_matrix = st.data_editor(
                        pd.DataFrame(matrix_rows),
                        key=f"assessment_import_matrix_{assessment_person_id}_{parsed_import['source_sha256'][:10]}_{operation}",
                        width="stretch",
                        height=760,
                        hide_index=True,
                        num_rows="fixed",
                        disabled=[
                            "Code", "Competency", "Source", "Current Score",
                            "Old TI Score", "Target", "Mapping Guideline",
                        ],
                        column_config={
                            "Code": st.column_config.TextColumn("Code", width="small"),
                            "Competency": st.column_config.TextColumn("Competency", width="large"),
                            "Source": st.column_config.TextColumn("Source", width="small"),
                            "Current Score": st.column_config.NumberColumn("Current", format="%.1f"),
                            "Old TI Score": st.column_config.NumberColumn("Old TI", format="%.1f"),
                            "Self Rating": st.column_config.NumberColumn(
                                "Self Rating", min_value=0.0, max_value=5.0, step=0.5, format="%.1f"
                            ),
                            "Imported Result": st.column_config.NumberColumn(
                                "Mapped / Final Result", min_value=0.0, max_value=5.0, step=0.5, format="%.1f"
                            ),
                            "Mapping Guideline": st.column_config.TextColumn("Mapping Guideline", width="large"),
                            "Target": st.column_config.NumberColumn("Target", format="%.1f"),
                            "Evidence": st.column_config.TextColumn("Evidence", width="large"),
                            "Assessor Comments": st.column_config.TextColumn("Assessor Comments", width="large"),
                            "Superior Comments": st.column_config.TextColumn("Superior Comments", width="large"),
                            "Assessor Approval": st.column_config.TextColumn("Assessor Approval"),
                            "Superior Approval": st.column_config.TextColumn("Superior Approval"),
                        },
                    )

                    if mapping_import:
                        st.caption(
                            f"Imported Result is Map Result (Column G). Old TI scores and mapping "
                            f"guidelines are retained. The main Target column uses the {selected_grade_group} "
                            "comparison; all four grade-group comparisons are shown below."
                        )
                    else:
                        st.caption(
                            "Imported Result is the source Final Rating. Self Rating is retained separately. "
                            "Target is shown from the selected saved assessment or the master workbook."
                        )
                    if grade_comparison_rows:
                        with st.expander("All grade-group target, gap and status comparisons", expanded=True):
                            st.dataframe(
                                pd.DataFrame(grade_comparison_rows),
                                width="stretch",
                                hide_index=True,
                                column_config={
                                    "% Close": st.column_config.NumberColumn(format="%.0f%%"),
                                    "Target": st.column_config.NumberColumn(format="%.1f"),
                                    "Source Gap": st.column_config.NumberColumn(format="%.1f"),
                                },
                            )

                    gap_preview = edited_import_matrix.copy()
                    gap_preview["Proposed Gap"] = gap_preview.apply(
                        lambda row: (
                            round(
                                max(
                                    float(pd.to_numeric(row["Target"], errors="coerce"))
                                    - float(pd.to_numeric(row["Imported Result"], errors="coerce")),
                                    0.0,
                                ),
                                2,
                            )
                            if pd.notna(pd.to_numeric(row["Target"], errors="coerce"))
                            and pd.notna(pd.to_numeric(row["Imported Result"], errors="coerce"))
                            else None
                        ),
                        axis=1,
                    )
                    st.markdown("#### Proposed score and gap preview")
                    st.dataframe(
                        gap_preview[["Code", "Current Score", "Old TI Score", "Imported Result", "Target", "Proposed Gap"]],
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "Current Score": st.column_config.NumberColumn(format="%.1f"),
                            "Old TI Score": st.column_config.NumberColumn(format="%.1f"),
                            "Imported Result": st.column_config.NumberColumn(format="%.1f"),
                            "Target": st.column_config.NumberColumn(format="%.1f"),
                            "Proposed Gap": st.column_config.NumberColumn(format="%.2f"),
                        },
                    )
                    confirm_name_mapping = True
                    if label_issues:
                        confirm_name_mapping = st.checkbox(
                            "I have checked the competency code/name differences shown above.",
                            value=False,
                            key=f"assessment_import_confirm_labels_{assessment_person_id}_{parsed_import['source_sha256'][:8]}",
                        )
                    review_button = st.form_submit_button(
                        "Mark as Reviewed",
                        type="primary",
                        use_container_width=True,
                        disabled=bool(identity_issues or duplicate_issues or fatal_issues),
                    )

                if review_button:
                    review_scores = {}
                    for _, matrix_row in edited_import_matrix.iterrows():
                        code = str(matrix_row.get("Code") or "")
                        if code not in SCORE_COLS:
                            continue
                        final_value = pd.to_numeric(
                            matrix_row.get("Imported Result"), errors="coerce"
                        )
                        self_value = pd.to_numeric(
                            matrix_row.get("Self Rating"), errors="coerce"
                        )
                        target_value = pd.to_numeric(
                            matrix_row.get("Target"), errors="coerce"
                        )
                        narrative = {
                            "evidence": _text(matrix_row, "Evidence"),
                            "assessor_comments": _text(matrix_row, "Assessor Comments"),
                            "superior_comments": _text(matrix_row, "Superior Comments"),
                            "assessor_approval": _text(matrix_row, "Assessor Approval"),
                            "superior_approval": _text(matrix_row, "Superior Approval"),
                        }
                        if (
                            pd.notna(final_value) or pd.notna(self_value)
                            or pd.notna(target_value) or any(narrative.values())
                        ):
                            review_scores[code] = {
                                "final_rating": None if pd.isna(final_value) else float(final_value),
                                "self_rating": None if pd.isna(self_value) else float(self_value),
                                "req": None if pd.isna(target_value) else float(target_value),
                                "old_ti_score": (
                                    None if pd.isna(pd.to_numeric(matrix_row.get("Old TI Score"), errors="coerce"))
                                    else float(pd.to_numeric(matrix_row.get("Old TI Score"), errors="coerce"))
                                ),
                                "mapping_guideline": _text(matrix_row, "Mapping Guideline"),
                                "grade_comparisons": (
                                    parsed_by_code.get(code, {}).get("grade_comparisons") or {}
                                ),
                                **narrative,
                            }

                    if not review_scores or not any(
                        value.get("final_rating") is not None
                        for value in review_scores.values()
                    ):
                        st.error(
                            "At least one valid Final Rating is required before the assessment can be reviewed."
                        )
                    elif label_issues and not confirm_name_mapping:
                        st.error(
                            "Please acknowledge the competency code/name differences before marking this import as reviewed."
                        )
                    else:
                        payload = {
                            "metadata": {
                                "assessment_date": (
                                    assessment_date_value.isoformat()
                                    if use_assessment_date else None
                                ),
                                "assessment_level": assessment_level_value.strip() or None,
                                "assessment_type": assessment_type_value.strip() or None,
                                "assessor1": assessor1_value.strip() or None,
                                "assessor2": assessor2_value.strip() or None,
                                "supervisor": supervisor_value.strip() or None,
                                "remarks": "",
                            },
                            "scores": review_scores,
                            "missing_codes": parsed_import.get("missing_codes", []),
                            "parser_issues": parser_issues,
                        }
                        review_session = open_session()
                        try:
                            batch_id = create_reviewed_assessment_import(
                                review_session,
                                personnel_id=assessment_person_id,
                                operation=operation,
                                target_assessment_id=target_assessment_id,
                                source_filename=import_upload.name,
                                source_sha256=parsed_import["source_sha256"],
                                payload=payload,
                                actor=current_user(),
                            )
                            st.session_state[
                                f"assessment_import_batch_{assessment_person_id}"
                            ] = batch_id
                            st.success(
                                f"Assessment import #{batch_id} marked as reviewed. "
                                "The live assessment records have not been changed."
                            )
                            st.rerun()
                        except Exception as exc:
                            review_session.rollback()
                            st.error(f"Unable to save the reviewed assessment: {exc}")
                        finally:
                            review_session.close()

            batch_state_key = f"assessment_import_batch_{assessment_person_id}"
            pending_batch_id = st.session_state.get(batch_state_key)
            batch_session = open_session()
            try:
                pending_batches = (
                    batch_session.query(AssessmentImportBatch)
                    .filter_by(
                        personnel_id=int(assessment_person_id),
                        status="reviewed",
                    )
                    .order_by(
                        AssessmentImportBatch.created_at.desc(),
                        AssessmentImportBatch.id.desc(),
                    )
                    .limit(10)
                    .all()
                )
                pending_options = {
                    (
                        f"Import #{batch.id} · {batch.source_filename} · "
                        f"{batch.created_at:%d %b %Y %H:%M}"
                    ): int(batch.id)
                    for batch in pending_batches
                }
                if pending_batches:
                    pending_ids = {int(batch.id) for batch in pending_batches}
                    if pending_batch_id not in pending_ids:
                        pending_batch_id = int(pending_batches[0].id)
                    if len(pending_batches) > 1:
                        pending_label = st.selectbox(
                            "Select a reviewed import awaiting approval",
                            list(pending_options),
                            index=list(pending_options.values()).index(int(pending_batch_id)),
                            key=f"pending_assessment_import_picker_{assessment_person_id}",
                        )
                        pending_batch_id = pending_options[pending_label]
                    st.session_state[batch_state_key] = pending_batch_id
                else:
                    pending_batch_id = None
                    st.session_state.pop(batch_state_key, None)

                reviewed_batch = (
                    batch_session.query(AssessmentImportBatch)
                    .filter_by(
                        id=int(pending_batch_id),
                        personnel_id=int(assessment_person_id),
                        status="reviewed",
                    )
                    .first()
                    if pending_batch_id else None
                )
                if reviewed_batch is not None:
                st.divider()
                st.markdown("#### Approval")
                st.caption(
                    f"Import #{reviewed_batch.id} · {reviewed_batch.source_filename} · "
                    f"Status: {reviewed_batch.status.title()}"
                )
                if reviewed_batch.status == "reviewed":
                    st.warning(
                        "This import has been reviewed. Approval will write the selected "
                        "assessment and its competency evidence to the database in one transaction."
                    )
                    approval_ack = st.checkbox(
                        "I approve these assessment results for database update.",
                        key=f"assessment_import_approval_ack_{reviewed_batch.id}",
                    )
                    approve_col, discard_col = st.columns(2)
                    with approve_col:
                        approve_import = st.button(
                            "Approve & Apply Assessment",
                            type="primary",
                            use_container_width=True,
                            disabled=not approval_ack,
                            key=f"approve_assessment_import_{reviewed_batch.id}",
                        )
                    with discard_col:
                        discard_import = st.button(
                            "Discard Review",
                            type="secondary",
                            use_container_width=True,
                            key=f"discard_assessment_import_{reviewed_batch.id}",
                        )
                    if approve_import:
                        approval_session = open_session()
                        try:
                            ok, message, applied_assessment_id = apply_reviewed_assessment_import(
                                approval_session,
                                int(reviewed_batch.id),
                                actor=current_user(),
                            )
                            if ok:
                                st.session_state["_assessment_import_saved_notice"] = message
                                st.session_state.pop(batch_state_key, None)
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error(message)
                                finally:
                                    approval_session.close()
                            if discard_import:
                                discard_session = open_session()
                                try:
                                    discard_batch = discard_session.get(
                                        AssessmentImportBatch, int(reviewed_batch.id)
                                    )
                                    if discard_batch is not None and discard_batch.status == "reviewed":
                                        discard_batch.status = "rejected"
                                        discard_session.commit()
                                    st.session_state.pop(batch_state_key, None)
                                    st.rerun()
                                finally:
                                    discard_session.close()
                        elif reviewed_batch.status == "approved":
                            st.success("This assessment import has already been approved and applied.")
                        elif reviewed_batch.status == "rejected":
                            st.info("This reviewed import was discarded.")
            finally:
                batch_session.close()

            if pending_batch_id is None and import_upload is None:
                st.info("Upload an assessment workbook or PDF to begin.")

        with history_tab:
            st.markdown("#### Assessment history")
            if not history:
                st.info("No assessment history is recorded for this employee yet.")
            else:
                history_rows = []
                history_labels = {}
                for record in history:
                    recorded_date = (
                        record["assessment_date"].strftime("%d %b %Y")
                        if record["assessment_date"] is not None
                        else "Undated"
                    )
                    level_label = record["assessment_level"] or "Level not specified"
                    label = f"#{record['id']} · {recorded_date} · {level_label}"
                    history_labels[label] = record["id"]
                    assessor_names = " / ".join(
                        value for value in (
                            record.get("assessor1"),
                            record.get("assessor2"),
                        ) if value
                    ) or "—"
                    history_rows.append(
                        {
                            "Assessment": f"#{record['id']}",
                            "Date": recorded_date,
                            "Level": level_label,
                            "Type": record.get("assessment_type") or "—",
                            "Assessors": assessor_names,
                            "Supervisor": record.get("supervisor") or "—",
                            "Score coverage": f"{record['score_count']}/{len(SCORE_COLS)}",
                            "Mean actual": record["average_actual"],
                            "Mean target": record["average_target"],
                            "Mean gap": record["average_gap"],
                        }
                    )

                st.dataframe(
                    pd.DataFrame(history_rows),
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Mean actual": st.column_config.NumberColumn(format="%.2f"),
                        "Mean target": st.column_config.NumberColumn(format="%.2f"),
                        "Mean gap": st.column_config.NumberColumn(format="%.2f"),
                    },
                )
                chosen_history_label = st.selectbox(
                    "Inspect a saved assessment",
                    list(history_labels),
                    key=f"admin_assessment_history_picker_{assessment_person_id}",
                )
                chosen_history_id = history_labels[chosen_history_label]
                detail_session = open_session()
                try:
                    chosen_scores = get_assessment_scores(
                        detail_session, chosen_history_id
                    )
                except Exception as exc:
                    chosen_scores = {}
                    st.error(f"Unable to load this assessment's scores: {exc}")
                finally:
                    detail_session.close()

                if chosen_scores:
                    detail_rows = []
                    for competency_type, info in COMP_TYPES.items():
                        for code in info["cols"]:
                            saved_score = chosen_scores.get(code, {})
                            detail_rows.append(
                                {
                                    "Code": code,
                                    "Competency": COMPETENCY_FULLNAMES.get(code, code),
                                    "Group": info["label"],
                                    "Old TI Score": saved_score.get("old_ti_score"),
                                    "Self Rating": saved_score.get("self_rating"),
                                    "Actual / Mapped Result": saved_score.get("actual"),
                                    "Target": saved_score.get("req"),
                                    "Gap": saved_score.get("gap"),
                                    "Achievement %": saved_score.get("achievement_pct"),
                                    "Mapping Guideline": saved_score.get("mapping_guideline"),
                                }
                            )
                    st.markdown("#### Saved competency matrix")
                    st.dataframe(
                        pd.DataFrame(detail_rows),
                        width="stretch",
                        hide_index=True,
                        column_config={
                            "Old TI Score": st.column_config.NumberColumn(format="%.1f"),
                            "Self Rating": st.column_config.NumberColumn(format="%.1f"),
                            "Actual / Mapped Result": st.column_config.NumberColumn(format="%.1f"),
                            "Target": st.column_config.NumberColumn(format="%.1f"),
                            "Gap": st.column_config.NumberColumn(format="%.2f"),
                            "Achievement %": st.column_config.NumberColumn(
                                format="%.1f%%"
                            ),
                        },
                    )

                    comparison_history_rows = []
                    for code in SCORE_COLS:
                        saved_score = chosen_scores.get(code, {})
                        for group, comparison in (saved_score.get("grade_comparisons") or {}).items():
                            comparison_history_rows.append({
                                "Code": code,
                                "Competency": COMPETENCY_FULLNAMES.get(code, code),
                                "Grade Group": group,
                                "% Close": comparison.get("percent_close"),
                                "Target": comparison.get("target"),
                                "Source Gap": comparison.get("gap"),
                                "Status": comparison.get("status"),
                            })
                    if comparison_history_rows:
                        with st.expander("Historical Technology Inventory grade comparisons"):
                            st.dataframe(
                                pd.DataFrame(comparison_history_rows),
                                width="stretch",
                                hide_index=True,
                                column_config={
                                    "% Close": st.column_config.NumberColumn(format="%.0f%%"),
                                    "Target": st.column_config.NumberColumn(format="%.1f"),
                                    "Source Gap": st.column_config.NumberColumn(format="%.1f"),
                                },
                            )

                    narrative_rows = []
                    for code in SCORE_COLS:
                        saved_score = chosen_scores.get(code, {})
                        for title, field in (
                            ("Evidence", "evidence"),
                            ("Assessor comments", "assessor_comments"),
                            ("Superior comments", "superior_comments"),
                            ("Assessor approval", "assessor_approval"),
                            ("Superior approval", "superior_approval"),
                        ):
                            value = saved_score.get(field)
                            if value:
                                narrative_rows.append({
                                    "Code": code,
                                    "Competency": COMPETENCY_FULLNAMES.get(code, code),
                                    "Information": title,
                                    "Details": value,
                                })
                    if narrative_rows:
                        with st.expander("Evidence, assessor comments and approvals"):
                            st.dataframe(
                                pd.DataFrame(narrative_rows),
                                width="stretch",
                                hide_index=True,
                            )
                else:
                    st.info(
                        "This assessment has no saved competency-score rows. "
                        "It may be a legacy header-only record."
                    )


# ---------------------------------------------------------------------------
# Archive and Restore — soft-delete semantics are unchanged
# ---------------------------------------------------------------------------

with archive_tab:
    st.subheader("Archive and restore personnel")
    st.caption(
        "Archiving hides a record from active directory views. It does not hard-delete "
        "the personnel row or its historical assessment records."
    )

    archive_column, restore_column = st.columns(2)

    with archive_column:
        st.markdown("#### Archive active personnel")
        if active_people.empty:
            st.info("There are no active personnel records to archive.")
        else:
            archive_options = {
                f"{record['name']} · {record['staff_id']}": int(record["id"])
                for _, record in active_people.sort_values(["name", "staff_id"]).iterrows()
            }
            archive_label = st.selectbox(
                "Select record to archive",
                list(archive_options),
                key="admin_archive_picker",
            )
            archive_id = archive_options[archive_label]
            archive_person = active_people[active_people["id"] == archive_id].iloc[0]
            archive_staff_id = str(archive_person["staff_id"])
            st.warning(
                f"Archive **{archive_person['name']}** (Staff ID: **{archive_staff_id}**)? "
                "The record will disappear from active views but remain recoverable."
            )
            confirmation = st.text_input(
                "Type the Staff ID to confirm",
                key=f"admin_archive_confirm_{archive_id}",
            )
            archive_clicked = st.button(
                "Archive personnel",
                type="primary",
                disabled=(confirmation.strip() != archive_staff_id),
                key=f"admin_archive_button_{archive_id}",
                use_container_width=True,
            )
            if archive_clicked:
                session = open_session()
                try:
                    ok, message = delete_personnel(
                        session, archive_id, changed_by=_current_admin_actor()
                    )
                    if ok:
                        st.success(f"Archived {archive_person['name']}.")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(message)
                except Exception as exc:
                    session.rollback()
                    st.error(f"Unable to archive personnel: {exc}")
                finally:
                    session.close()

    with restore_column:
        st.markdown("#### Restore archived personnel")
        if archived_people.empty:
            st.info("There are no archived records to restore.")
        else:
            restore_options = {
                f"{record['name']} · {record['staff_id']}": int(record["id"])
                for _, record in archived_people.sort_values(["name", "staff_id"]).iterrows()
            }
            restore_label = st.selectbox(
                "Select archived record",
                list(restore_options),
                key="admin_restore_picker",
            )
            restore_id = restore_options[restore_label]
            restore_person = archived_people[archived_people["id"] == restore_id].iloc[0]
            st.info(
                f"Restore **{restore_person['name']}** (Staff ID: **{restore_person['staff_id']}**) "
                "to the active personnel directory?"
            )
            restore_confirmed = st.checkbox(
                "I confirm this personnel record should be restored.",
                key=f"admin_restore_confirm_{restore_id}",
            )
            if st.button(
                "Restore personnel",
                type="primary",
                disabled=not restore_confirmed,
                key=f"admin_restore_button_{restore_id}",
                use_container_width=True,
            ):
                session = open_session()
                try:
                    # Reuse the existing generic update service. No DB service,
                    # model, schema or backend implementation is changed.
                    ok, message = update_personnel(
                        session, restore_id, {"is_deleted": False, "is_active": True},
                        changed_by=_current_admin_actor(),
                    )
                    if ok:
                        st.success(f"Restored {restore_person['name']} to the active directory.")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(message)
                except Exception as exc:
                    session.rollback()
                    st.error(f"Unable to restore personnel: {exc}")
                finally:
                    session.close()

