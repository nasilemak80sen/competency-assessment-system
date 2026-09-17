"""Personnel-scoped dashboard for USER accounts."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from components.navigation import render_header, render_navigation
from core.auth import ROLE_USER, current_user, personnel_id, require_roles
from core.bootstrap import get_master_data, open_session
from models import Personnel

require_roles(ROLE_USER)
render_navigation()
user = current_user()
render_header("🏠 My Dashboard", "Personal competency and career snapshot")

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

# Auth personnel_id is the SQLAlchemy Personnel.id. The workbook dataframe
# does not contain that DB primary key, so join the two sources by Staff ID.
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
st.subheader(f"Welcome, {person.get('Name') or person_db.name}")

re_years = pd.to_numeric(person.get("Years of RE Experience"), errors="coerce")
pet_years = pd.to_numeric(person.get("Years in PET"), errors="coerce")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Salary Grade", str(person.get("SG", "N/A")))
c2.metric("Position", str(person.get("Staff Position", "N/A")))
c3.metric("Department", str(person.get("Department", "N/A")))
c4.metric("RE Experience", f"{re_years:.1f} yrs" if pd.notna(re_years) else "N/A")
c5.metric("PETRONAS Experience", f"{pet_years:.1f} yrs" if pd.notna(pet_years) else "N/A")

st.markdown("---")
profile_left, profile_right = st.columns(2)
with profile_left:
    st.subheader("👤 My Profile")
    st.write({
        "Name": person.get("Name") or person_db.name,
        "Staff ID": person.get("Staff ID") or person_db.staff_id,
        "Position": person.get("Staff Position"),
        "Salary Grade": person.get("SG"),
        "Department": person.get("Department"),
        "Section": person.get("Section Name"),
        "Current Assignment": person.get("Current Location:") or person.get("Current Assignment"),
        "Employment": person.get("Employment Category"),
    })
with profile_right:
    st.subheader("📊 My Competency Snapshot")
    score_columns = [
        c for c in [
            *[f"B{i}" for i in range(1, 13)],
            *[f"K{i}" for i in range(1, 6)],
            *[f"P{i}" for i in range(1, 6)],
            "E1", "E2",
        ]
        if c in mine.columns
    ]
    records = []
    for group, prefix in [("Base", "B"), ("Key", "K"), ("Pacing", "P"), ("Emerging", "E")]:
        cols = [c for c in score_columns if c.startswith(prefix)]
        values = pd.to_numeric(person[cols], errors="coerce") if cols else pd.Series(dtype=float)
        records.append({"Competency Type": group, "Average Score": float(values.mean()) if values.notna().any() else 0.0})
    chart_df = pd.DataFrame(records)
    fig = px.bar(chart_df, x="Competency Type", y="Average Score", range_y=[0, 5], text="Average Score")
    fig.update_traces(texttemplate="%{text:.2f}", textposition="outside")
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10), yaxis_title="Average Score", xaxis_title="")
    st.plotly_chart(fig, use_container_width=True)

st.subheader("🎯 My Assessment Status")
assessment_date = person.get("Last Assesment Date") or person.get("Last Assessment Date")
assessment_level = person.get("Assessment Level")
st.info(f"Assessment Level: **{assessment_level or 'Not set'}** · Last Assessment: **{assessment_date or 'Not available'}**")

st.caption("This page is intentionally restricted to your own personnel record. Organisation-wide analytics are available only to administrators.")
