"""Personnel-scoped assessment view for USER accounts."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from components.navigation import render_header, render_navigation
from core.auth import ROLE_USER, personnel_id, require_roles
from core.bootstrap import get_master_data
from config import COMP_TYPES, COMPETENCY_FULLNAMES

require_roles(ROLE_USER)
render_navigation()
render_header("👤 My Assessment", "Your competency scores, targets and development gaps")

df = get_master_data()
if df is None or df.empty or "id" not in df.columns:
    st.warning("Your personnel record is not available.")
    st.stop()

mine = df[pd.to_numeric(df["id"], errors="coerce") == personnel_id()].copy()
if mine.empty:
    st.error("Your account is not currently linked to a personnel record.")
    st.stop()
person = mine.iloc[0]

st.subheader(str(person.get("Name", "My Assessment")))
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
weighted = float(assessment_df.loc[assessed, "Actual"].mean()) if assessed.any() else 0.0
major_gaps = int(((assessment_df["Gap"] > 1) & assessed).sum())
minor_gaps = int(((assessment_df["Gap"] > 0) & (assessment_df["Gap"] <= 1) & assessed).sum())

c1, c2, c3, c4 = st.columns(4)
c1.metric("Assessment Coverage", f"{coverage:.0f}%")
c2.metric("Average Score", f"{weighted:.2f}/5")
c3.metric("Major Gaps", major_gaps)
c4.metric("Minor Gaps", minor_gaps)

st.markdown("---")
view_tab, gap_tab = st.tabs(["📊 Scorecard", "🎯 Development Gaps"])

with view_tab:
    st.dataframe(
        assessment_df,
        use_container_width=True,
        hide_index=True,
    )

with gap_tab:
    gaps = assessment_df[assessment_df["Gap"].fillna(0) > 0].sort_values("Gap", ascending=False)
    if gaps.empty:
        st.success("No recorded competency gaps against the stored targets.")
    else:
        st.dataframe(gaps, use_container_width=True, hide_index=True)

st.caption("This assessment view is restricted to your linked personnel record. Other personnel assessment data is not exposed to USER accounts.")
