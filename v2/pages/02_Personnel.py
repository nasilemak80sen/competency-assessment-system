"""Personnel Directory — native v2 page."""
from __future__ import annotations

import streamlit as st

from components.navigation import render_navigation, render_header
from core.bootstrap import get_master_data

render_navigation()
render_header("👥 Personnel Directory", "Search, filter and export the Reservoir Engineering workforce")

df = get_master_data()
if df is None or df.empty:
    st.info("No personnel available. Import data first.")
    st.stop()

filter_cols = st.columns(3)
with filter_cols[0]:
    departments = st.multiselect("Department", sorted(df["Department"].dropna().astype(str).unique()) if "Department" in df else [], key="personnel_dept")
with filter_cols[1]:
    positions = st.multiselect("Position", sorted(df["Staff Position"].dropna().astype(str).unique()) if "Staff Position" in df else [], key="personnel_pos")
with filter_cols[2]:
    statuses = sorted(df["Chat Status"].dropna().astype(str).unique()) if "Chat Status" in df else []
    chat_status = st.multiselect("Chat Status", statuses, key="personnel_chat")

search = st.text_input("🔎 Search by Name or Staff ID", key="personnel_search")
filtered = df.copy()
if departments: filtered = filtered[filtered["Department"].astype(str).isin(departments)]
if positions: filtered = filtered[filtered["Staff Position"].astype(str).isin(positions)]
if chat_status and "Chat Status" in filtered: filtered = filtered[filtered["Chat Status"].astype(str).isin(chat_status)]
if search:
    term = search.strip().casefold()
    mask = filtered["Name"].fillna("").astype(str).str.casefold().str.contains(term, na=False, regex=False)
    if "Staff ID" in filtered:
        mask |= filtered["Staff ID"].fillna("").astype(str).str.casefold().str.contains(term, na=False, regex=False)
    filtered = filtered[mask]

st.caption(f"Showing {len(filtered):,} of {len(df):,} personnel")
display_cols = ["Name", "Staff ID", "Staff Position", "SG", "Department", "Age", "Chat Status", "Years in RE Experience"]
display_cols = [c for c in display_cols if c in filtered.columns]
show = filtered[display_cols].copy()
st.dataframe(show, width="stretch", hide_index=True)
st.download_button("⬇️ Download as CSV", show.to_csv(index=False).encode(), "personnel_directory.csv", "text/csv")
