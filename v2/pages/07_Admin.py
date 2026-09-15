"""Administration — native v2 CRUD and assessment entry page."""
from __future__ import annotations

from datetime import date, datetime
import pandas as pd
import streamlit as st

from components.navigation import render_navigation, render_header
from core.bootstrap import get_master_data, open_session
from models import Personnel
from services.personnel_service import update as update_personnel, delete as delete_personnel
from services.assessment_service import add_assessment, add_competency_scores
from config import SCORE_COLS, ASSESSMENT_LEVELS

render_navigation()
render_header("⚙️ Admin: Personnel Database Settings", "Maintain personnel records and enter competency assessments")


def _safe_int(value, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    """Safely convert Excel/database values to an integer within widget bounds."""
    try:
        if value is None or pd.isna(value):
            return default
    except (TypeError, ValueError):
        return default

    # Date-like values must be handled before numeric conversion. Pandas may
    # expose Excel dates as Timestamp/datetime objects.
    if isinstance(value, (pd.Timestamp, datetime, date)):
        candidate = int(value.year)
    else:
        numeric = pd.to_numeric(value, errors="coerce")
        if pd.notna(numeric):
            candidate = int(round(float(numeric)))
        else:
            parsed = pd.to_datetime(value, errors="coerce")
            if pd.isna(parsed):
                return default
            candidate = int(parsed.year)

    if minimum is not None and candidate < minimum:
        return default
    if maximum is not None and candidate > maximum:
        return default
    return candidate


def _safe_birth_year(value, default: int = 1990) -> int:
    """Normalize birth-year values, including Excel serial/date representations."""
    try:
        if value is None or pd.isna(value):
            return default
    except (TypeError, ValueError):
        return default

    if isinstance(value, (pd.Timestamp, datetime, date)):
        year = int(value.year)
        return year if 1950 <= year <= 2010 else default

    numeric = pd.to_numeric(value, errors="coerce")
    if pd.notna(numeric):
        numeric_value = float(numeric)
        # A normal year should already be in the widget range.
        if 1950 <= numeric_value <= 2010:
            return int(round(numeric_value))
        # Excel's date serial range (roughly 1950–2010) is around 18k–40k.
        if 10000 <= numeric_value <= 60000:
            parsed = pd.to_datetime(numeric_value, unit="D", origin="1899-12-30", errors="coerce")
            if pd.notna(parsed) and 1950 <= parsed.year <= 2010:
                return int(parsed.year)
        # Very large values can be pandas datetime nanoseconds.
        if abs(numeric_value) > 1_000_000_000:
            parsed = pd.to_datetime(int(numeric_value), unit="ns", errors="coerce")
            if pd.notna(parsed) and 1950 <= parsed.year <= 2010:
                return int(parsed.year)

    parsed = pd.to_datetime(value, errors="coerce")
    if pd.notna(parsed) and 1950 <= parsed.year <= 2010:
        return int(parsed.year)
    return default


df = get_master_data()
if df is None or df.empty:
    st.info("No personnel available. Import data first.")
    st.stop()

names = sorted(df["Name"].dropna().astype(str).unique())
selected_name = st.selectbox("Select Personnel", names, key="personnel_db_selector")
row = df[df["Name"].astype(str) == selected_name].iloc[0]

pid = None
if "id" in row.index and pd.notna(row["id"]):
    pid = _safe_int(row["id"], 0, 1)
else:
    session = open_session()
    try:
        staff_id = row.get("Staff ID")
        person = session.query(Personnel).filter(Personnel.staff_id == str(staff_id)).first() if pd.notna(staff_id) else None
        if person is None:
            person = session.query(Personnel).filter(Personnel.name == selected_name).first()
        pid = person.id if person else None
    finally:
        session.close()

if pid is None:
    st.warning("No database personnel ID found for this person. Import data to enable editing.")
    st.stop()

st.caption(f"Editing: **{selected_name}** · Database ID: {pid}")
personnel_tab, assessment_tab, delete_tab = st.tabs(["✏️ Edit Personnel Info", "🧾 Assessment Entry", "🗑️ Delete Personnel"])

with personnel_tab:
    with st.form(f"personnel_database_form_{pid}"):
        col1, col2, col3 = st.columns(3)
        with col1:
            name = st.text_input("Name", str(row.get("Name") or ""))
            staff_id = st.text_input("Staff ID", str(row.get("Staff ID") or ""))
            email = st.text_input("Email", str(row.get("Email Address") or ""))
        with col2:
            gender_options = ["M", "F", "Other"]
            current_gender = str(row.get("Gender") or "M")
            gender = st.selectbox("Gender", gender_options, index=gender_options.index(current_gender) if current_gender in gender_options else 0)
            age = st.number_input("Age", min_value=18, max_value=100, value=_safe_int(row.get("Age"), 30, 18, 100), step=1, format="%d")
            birth_year = st.number_input("Birth Year", min_value=1950, max_value=2010, value=_safe_birth_year(row.get("Birth Year")), step=1, format="%d")
        with col3:
            department = st.text_input("Department", str(row.get("Department") or ""))
            position = st.text_input("Staff Position", str(row.get("Staff Position") or ""))
            sg = st.text_input("Salary Grade", str(row.get("SG") or ""))
        submitted = st.form_submit_button("💾 Save Personnel Changes", type="primary", width="stretch")
    if submitted:
        session = open_session()
        try:
            ok, message = update_personnel(session, pid, {"name": name, "staff_id": staff_id, "email": email, "gender": gender,
                                                          "age": age, "birth_year": birth_year, "department": department,
                                                          "staff_position": position, "sg": sg})
            if ok:
                st.success(message)
                st.cache_data.clear()
            else:
                st.error(message)
        except Exception as exc:
            session.rollback()
            st.error(f"Unable to update personnel: {exc}")
        finally:
            session.close()

with assessment_tab:
    st.markdown("### New Assessment")
    with st.form(f"assessment_entry_form_{pid}"):
        assessment_date = st.date_input("Assessment Date", value=date.today(), format="DD MMM YYYY")
        level_options = list(ASSESSMENT_LEVELS) if ASSESSMENT_LEVELS else ["Technical"]
        assessment_level = st.selectbox("Assessment Level", level_options)
        assessor1 = st.text_input("Assessor 1")
        assessor2 = st.text_input("Assessor 2")
        supervisor = st.text_input("Supervisor")
        remarks = st.text_area("Remarks")
        st.markdown("#### Competency Scores")
        scores = {}
        score_cols = st.columns(4)
        for index, code in enumerate(SCORE_COLS):
            with score_cols[index % 4]:
                scores[code] = {"actual": st.number_input(code, min_value=0.0, max_value=5.0, step=0.5, value=0.0, format="%.1f", key=f"score_{pid}_{code}")}
        save_assessment = st.form_submit_button("✅ Save Assessment", type="primary", width="stretch")
    if save_assessment:
        session = open_session()
        try:
            ok, message, assessment_id = add_assessment(session, pid, {"assessment_date": assessment_date, "assessment_level": assessment_level,
                                                                       "assessor1": assessor1, "assessor2": assessor2, "supervisor": supervisor, "remarks": remarks})
            if not ok:
                st.error(message)
            else:
                score_ok, score_message = add_competency_scores(session, assessment_id, pid, scores)
                if not score_ok:
                    st.error(score_message)
                else:
                    session.commit()
                    st.success("Assessment and competency scores saved.")
                    st.cache_data.clear()
        except Exception as exc:
            session.rollback()
            st.error(f"Unable to save assessment: {exc}")
        finally:
            session.close()

with delete_tab:
    st.warning("Deleting a personnel record is destructive. Use this only when the record should no longer exist in the database.")
    confirm = st.checkbox("I understand this will delete the selected personnel record and related database records.", key=f"confirm_delete_{pid}")
    if st.button("🗑️ Delete Personnel", type="secondary", disabled=not confirm, key=f"delete_personnel_{pid}"):
        session = open_session()
        try:
            ok, message = delete_personnel(session, pid)
            if ok:
                st.success(message)
                st.cache_data.clear()
            else:
                st.error(message)
        except Exception as exc:
            session.rollback()
            st.error(f"Unable to delete personnel: {exc}")
        finally:
            session.close()
