"""Personnel-scoped assessment view for USER accounts."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from components.navigation import render_header, render_navigation
from core.auth import ROLE_USER, personnel_id, require_roles
from core.bootstrap import get_master_data, open_session
from config import COMP_TYPES, COMPETENCY_FULLNAMES
from models import Personnel

require_roles(ROLE_USER)
render_navigation()
render_header("👤 My Assessment", "Your competency scores, targets and development gaps")

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

st.subheader(str(person.get("Name") or person_db.name))
st.caption(f"{person.get('Staff Position', 'N/A')} · {person.get('SG', 'N/A')} · {person.get('Department', 'N/A')}")

records = []
for ctype, info in COMP_TYPES.items():
    for code in info["cols"]:
        actual = pd.to_numeric(person.get(code), errors="coerce")
        target = pd.to_numeric(person.get(f"R-{code}"), errors="coerce")
        records.append({
            "Type": info["label"],
            "Code": code,
            "Competency": COMPETENCY_FULLNAMES.get(code, code),
            "Actual": actual,
            "Target": target,
            "Gap": target - actual if pd.notna(actual) and pd.notna(target) else pd.NA,
        })
assessment_df = pd.DataFrame(records)

assessed = assessment_df["Actual"].notna()
coverage = float(assessed.mean() * 100) if len(assessment_df) else 0.0
average_score = float(assessment_df.loc[assessed, "Actual"].mean()) if assessed.any() else 0.0
major_gaps = int(((assessment_df["Gap"] > 1) & assessed).sum())
minor_gaps = int(((assessment_df["Gap"] > 0) & (assessment_df["Gap"] <= 1) & assessed).sum())

c1, c2, c3, c4 = st.columns(4)
c1.metric("Assessment Coverage", f"{coverage:.0f}%")
c2.metric("Average Score", f"{average_score:.2f}/5")
c3.metric("Major Gaps", major_gaps)
c4.metric("Minor Gaps", minor_gaps)

st.markdown("---")
view_tab, gap_tab = st.tabs(["📊 Scorecard", "🎯 Development Gaps"])

with view_tab:
    st.dataframe(assessment_df, use_container_width=True, hide_index=True)

with gap_tab:
    gaps = assessment_df[assessment_df["Gap"].fillna(0) > 0].sort_values("Gap", ascending=False)
    if gaps.empty:
        st.success("No recorded competency gaps against the stored targets.")
    else:
        st.dataframe(gaps, use_container_width=True, hide_index=True)

st.caption("This assessment view is restricted to your linked personnel record. Other personnel assessment data is not exposed to USER accounts.")
