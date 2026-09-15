"""Personnel directory page."""
import streamlit as st

from core.bootstrap import initialise_session, get_master_data, set_selected_person
from components.navigation import render_header, render_navigation

initialise_session()
render_navigation()
render_header("👥 Personnel Directory", "Search and select a personnel record for downstream analysis.")

df = get_master_data().copy()

search = st.text_input("Search name / staff ID", placeholder="Type a name or staff ID…")
filtered = df
if search.strip():
    q = search.strip().lower()
    mask = (
        df.get("Name", "").astype(str).str.lower().str.contains(q, na=False)
        | df.get("Staff ID", "").astype(str).str.lower().str.contains(q, na=False)
    )
    filtered = df[mask]

left, right = st.columns([2, 1])
with left:
    st.dataframe(
        filtered[[c for c in ["Name", "Staff ID", "Department", "Staff Position", "SG"] if c in filtered.columns]],
        use_container_width=True,
        hide_index=True,
    )

with right:
    names = filtered["Name"].dropna().astype(str).tolist() if "Name" in filtered else []
    if not names:
        st.warning("No personnel match the current search.")
        st.stop()

    current = st.session_state.get("selected_person_name")
    index = names.index(current) if current in names else 0
    selected_name = st.selectbox("Select personnel", names, index=index, key="personnel_directory_selection")
    row = filtered[filtered["Name"].astype(str) == selected_name].iloc[0]

    if st.button("Set as active personnel", type="primary", use_container_width=True):
        set_selected_person(
            staff_id=row.get("Staff ID"),
            name=row.get("Name"),
        )
        st.success(f"Selected: {row.get('Name')}")
        st.page_link("pages/05_Individual_Assessment.py", label="Open Individual Assessment →")

    st.divider()
    for label in ["Department", "Section Name", "Unit Name", "Staff Position", "SG", "Employment Category"]:
        if label in row.index:
            st.caption(label)
            st.write(row.get(label) if row.get(label) not in [None, "nan"] else "—")
