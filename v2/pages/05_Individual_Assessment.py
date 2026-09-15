"""Individual assessment and talent profile page.

The page consumes shared context and analytics functions; it does not import
another Streamlit page.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from core.bootstrap import initialise_session, get_master_data, set_selected_person
from components.navigation import render_header, render_navigation
from config import SCORE_COLS, REQ_COLS, COMP_TYPES, COMPETENCY_FULLNAMES
import analytics as an

initialise_session()
render_navigation()
render_header("👤 Individual Assessment & Talent Profile", "One personnel view shared across the v2 application.")

df = get_master_data().copy()

names = df["Name"].dropna().astype(str).tolist() if "Name" in df else []
if not names:
    st.warning("No personnel records are available.")
    st.stop()

current = st.session_state.get("selected_person_name")
index = names.index(current) if current in names else 0
selected_name = st.selectbox("Personnel", names, index=index, key="individual_person_selection")
row = df[df["Name"].astype(str) == selected_name].iloc[0]
set_selected_person(staff_id=row.get("Staff ID"), name=row.get("Name"))

c1, c2, c3, c4 = st.columns(4)
with c1: st.metric("Staff ID", str(row.get("Staff ID", "—")))
with c2: st.metric("Department", str(row.get("Department", "—")))
with c3: st.metric("Position", str(row.get("Staff Position", "—")))
with c4: st.metric("SG", str(row.get("SG", "—")))

profile = an.add_category_averages(pd.DataFrame([row]))
cols = ["B_avg", "K_avg", "P_avg", "E_avg", "Overall_avg"]
labels = ["Base", "Knowledge", "Pacing", "Emerging", "Overall"]
metrics = profile.iloc[0]
mc = st.columns(5)
for container, col, label in zip(mc, cols, labels):
    with container:
        value = metrics.get(col)
        st.metric(label, f"{value:.1f}" if pd.notna(value) else "—")

st.divider()

available_scores = [c for c in SCORE_COLS if c in row.index]
score_records = []
for code in available_scores:
    actual = pd.to_numeric(row.get(code), errors="coerce")
    target = pd.to_numeric(row.get(f"R-{code}"), errors="coerce")
    if pd.isna(actual) and pd.isna(target):
        continue
    score_records.append({
        "Code": code,
        "Competency": COMPETENCY_FULLNAMES.get(code, code),
        "Actual": actual,
        "Target": target,
        "Gap": actual - target if pd.notna(actual) and pd.notna(target) else pd.NA,
    })

gaps = pd.DataFrame(score_records)
if gaps.empty:
    st.info("No competency scores are available for this personnel.")
else:
    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("Actual vs Target")
        fig = go.Figure()
        fig.add_trace(go.Bar(name="Actual", x=gaps["Code"], y=gaps["Actual"]))
        if gaps["Target"].notna().any():
            fig.add_trace(go.Scatter(name="Target", x=gaps["Code"], y=gaps["Target"], mode="lines+markers"))
        fig.update_layout(height=430, xaxis_title="Competency", yaxis_title="Score")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Gap summary")
        met = int((gaps["Gap"].dropna() >= 0).sum())
        minor = int(((gaps["Gap"] < 0) & (gaps["Gap"] >= -1)).sum())
        major = int((gaps["Gap"] < -1).sum())
        a, b, c = st.columns(3)
        with a: st.metric("Met", met)
        with b: st.metric("Minor", minor)
        with c: st.metric("Major", major)
        display = gaps.copy()
        display["Status"] = display["Gap"].apply(
            lambda x: "Met" if pd.notna(x) and x >= 0 else ("Minor Gap" if pd.notna(x) and x >= -1 else ("Major Gap" if pd.notna(x) else "N/A"))
        )
        st.dataframe(display, use_container_width=True, hide_index=True)

st.divider()
st.subheader("Talent context")
for field in ["Background", "Potential", "Strength", "Recommendation", "Resource/SME", "Interest", "Preference", "Supervisor"]:
    if field in row.index and pd.notna(row.get(field)):
        st.markdown(f"**{field}**  \n{row.get(field)}")
