"""Dashboard Home — native v2 page."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import POSITION_HIERARCHY_ORDER, SG_HIERARCHY, SG_TO_POSITION_BRACKET
from core.bootstrap import get_master_data
from analytics.nationality import prepare_nationality_map_data, create_nationality_bubble_map
from analytics.readiness import scatter_age_vs_grade
from components.navigation import render_navigation, render_header

render_navigation()
render_header("🏠 Dashboard Home", "DPE Reservoir Engineering workforce overview")

df = get_master_data()
if df is None or df.empty:
    st.warning("⚠️ No personnel data is available. Go to Admin: Import Data to load the master workbook.")
    st.stop()

# Top metrics
metric_cols = st.columns(5)
total = len(df)
gender = df.get("Gender", pd.Series(dtype=object)).astype(str).str.strip().str.upper()
employment = df.get("Employment Category", pd.Series(dtype=object)).astype(str).str.strip().str.upper()
metric_cols[0].metric("Total Personnel", int(total))
metric_cols[1].metric("Permanent Employees", int(employment.eq("PERMANENT").sum()))
metric_cols[2].metric("CDH Employees", int(employment.eq("CDH").sum()))
metric_cols[3].metric("Male", int(gender.eq("M").sum()))
metric_cols[4].metric("Female", int(gender.eq("F").sum()))

# Nationality distribution
st.markdown("---")
st.subheader("🌐 RE Nationalities")
nationality_df, unmatched = prepare_nationality_map_data(df)
if not nationality_df.empty:
    top = nationality_df.head(5); cols = st.columns(min(5, len(top)))
    for index, (_, row) in enumerate(top.iterrows()): cols[index].metric(row["Nationality"], int(row["Personnel Count"]), row["Representation Display"])
    st.plotly_chart(create_nationality_bubble_map(nationality_df), width="stretch", config={"displaylogo": True, "scrollZoom": True, "responsive": True, "modeBarButtonsToRemove": ["lasso2d", "select2d"], "toImageButtonOptions": {"format": "png", "filename": "RE_personnel_nationality_map", "height": 800, "width": 1400, "scale": 2}})
    st.caption("Bubble size and color represent the number of personnel associated with each nationality. Markers use approximate country-centroid coordinates.")
else: st.info("No valid nationality data is available for the geographical visualization.")
if unmatched:
    with st.expander("⚠️ Nationality values requiring mapping"): st.write(unmatched)

# Workforce distributions
st.markdown("---")
filter_cols = st.columns(3)
with filter_cols[0]: selected_units = st.multiselect("Filter by Unit Name", sorted(df["Unit Name"].dropna().astype(str).unique()) if "Unit Name" in df else [], key="dash_unit1")
with filter_cols[1]: selected_positions = st.multiselect("Filter by Position", sorted(df["Staff Position"].dropna().astype(str).unique()) if "Staff Position" in df else [], key="dash_pos1")
with filter_cols[2]: selected_people = st.multiselect("Filter by Personnel", sorted(df["Name"].dropna().astype(str).unique()) if "Name" in df else [], key="dash_name")
filtered = df.copy()
if selected_units: filtered = filtered[filtered["Unit Name"].astype(str).isin(selected_units)]
if selected_positions: filtered = filtered[filtered["Staff Position"].astype(str).isin(selected_positions)]
if selected_people: filtered = filtered[filtered["Name"].astype(str).isin(selected_people)]

chart_cols = st.columns(2)
with chart_cols[0]:
    st.subheader("📊 Position Breakdown")
    if "SG" in filtered and "Employment Category" in filtered:
        chart = filtered.copy(); chart["Position"] = chart["SG"].map(SG_TO_POSITION_BRACKET).fillna("Other"); chart["Employment Type"] = chart["Employment Category"].astype(str).str.strip().str.upper().map({"PERMANENT":"Permanent","CDH":"CDH"}).fillna("Other")
        grouped = chart.groupby(["Position","Employment Type"]).size().reset_index(name="Personnel")
        st.plotly_chart(px.bar(grouped, x="Position", y="Personnel", color="Employment Type", barmode="stack", category_orders={"Position": [p for p in POSITION_HIERARCHY_ORDER if p in grouped["Position"].unique()]}), width="stretch", config={"displaylogo": False, "responsive": True})
with chart_cols[1]:
    st.subheader("📊 Salary Grade Distribution")
    if "SG" in filtered and "Employment Category" in filtered:
        chart = filtered.copy(); chart["Employment Type"] = chart["Employment Category"].astype(str).str.strip().str.upper().map({"PERMANENT":"Permanent","CDH":"CDH"}).fillna("Other")
        grouped = chart.groupby(["SG","Employment Type"]).size().reset_index(name="Personnel"); order = [g for g in SG_HIERARCHY if g in grouped["SG"].unique()]
        st.plotly_chart(px.bar(grouped, x="SG", y="Personnel", color="Employment Type", barmode="stack", category_orders={"SG": order}), width="stretch", config={"displaylogo": False, "responsive": True})

# Legacy dashboard row: gender and office location distribution
st.markdown("---")
row2 = st.columns(2)
with row2[0]:
    st.subheader("👥 Gender Distribution")
    if "Gender" in df.columns:
        counts = df["Gender"].astype(str).str.strip().replace({"M":"Male","F":"Female"}).value_counts().reset_index(); counts.columns=["Gender","Count"]
        st.plotly_chart(px.pie(counts, names="Gender", values="Count", hole=0.35), width="stretch", config={"displaylogo": False, "responsive": True})
    else: st.info("Gender data not available")
with row2[1]:
    st.subheader("🏢 Office Location Distribution")
    location_column = "Current Location:" if "Current Location:" in df.columns else ("Current Assignment / Loc:" if "Current Assignment / Loc:" in df.columns else None)
    if location_column:
        locations = df[location_column].fillna("Not Specified").astype(str).str.strip().replace("", "Not Specified").value_counts().reset_index(); locations.columns=["Current Assignment","Count"]; locations=locations.sort_values("Count",ascending=True)
        fig=px.bar(locations,x="Count",y="Current Assignment",orientation="h",text="Count",color="Count",color_continuous_scale="Emrld")
        fig.update_traces(textposition="outside",hovertemplate="<b>%{y}</b><br>Count: %{x}<extra></extra>"); fig.update_layout(height=max(500,len(locations)*25),showlegend=False)
        st.plotly_chart(fig,width="stretch",config={"displaylogo":False,"responsive":True})
    else: st.info("Office location data not available")

# Legacy dashboard row: age vs salary grade
st.markdown("---")
st.subheader("📈 Age vs Salary Grade Analysis")
scatter_df = scatter_age_vs_grade(df)
if not scatter_df.empty:
    filter_area = st.columns(4)
    with filter_area[0]: age_units = st.multiselect("Unit Name", sorted(df["Unit Name"].dropna().astype(str).unique()) if "Unit Name" in df else [], key="dash_age_unit")
    with filter_area[1]: age_positions = st.multiselect("Staff Position", sorted(df["Staff Position"].dropna().astype(str).unique()) if "Staff Position" in df else [], key="dash_age_position")
    with filter_area[2]:
        pet_values=pd.to_numeric(df.get("Years in PET",pd.Series([0])),errors="coerce").fillna(0); pet_min,pet_max=float(pet_values.min()),float(pet_values.max())
        pet_range=st.slider("Years in PETRONAS",pet_min,pet_max,(pet_min,pet_max),step=1.0,key="dash_pet_range")
    with filter_area[3]:
        re_values=pd.to_numeric(df.get("Years of RE Experience",pd.Series([0])),errors="coerce").fillna(0); re_min,re_max=float(re_values.min()),float(re_values.max())
        re_range=st.slider("Years of RE Experience",re_min,re_max,(re_min,re_max),step=1.0,key="dash_re_range")
    career_filtered=df.copy()
    if age_units: career_filtered=career_filtered[career_filtered["Unit Name"].astype(str).isin(age_units)]
    if age_positions: career_filtered=career_filtered[career_filtered["Staff Position"].astype(str).isin(age_positions)]
    if "Years in PET" in career_filtered.columns: career_filtered=career_filtered[pd.to_numeric(career_filtered["Years in PET"],errors="coerce").fillna(0).between(*pet_range)]
    if "Years of RE Experience" in career_filtered.columns: career_filtered=career_filtered[pd.to_numeric(career_filtered["Years of RE Experience"],errors="coerce").fillna(0).between(*re_range)]
    plot_df=scatter_age_vs_grade(career_filtered)
    if not plot_df.empty:
        fig=px.scatter(plot_df,x="Age",y="SG",color="SG",hover_name="Name",hover_data={c:True for c in ["Department","Staff Position","Years of RE Experience","Years in PET"] if c in plot_df.columns},category_orders={"SG":SG_HIERARCHY},height=520)
        st.plotly_chart(fig,width="stretch",config={"displaylogo":False,"responsive":True})
    else: st.info("No personnel match the selected career filters.")
else: st.info("Age or salary grade data not available")

# Legacy dashboard career landscape
st.markdown("---")
st.subheader("🌐 3D Career Landscape")
required_3d={"Age","SG","Years in PET","Years of RE Experience"}
if required_3d.issubset(df.columns):
    career=df[list(required_3d|({"Name","Department","Staff Position"} & set(df.columns)))].copy()
    career["Age"]=pd.to_numeric(career["Age"],errors="coerce"); career["Years in PET"]=pd.to_numeric(career["Years in PET"],errors="coerce").fillna(0); career["Years of RE Experience"]=pd.to_numeric(career["Years of RE Experience"],errors="coerce").fillna(0); career=career.dropna(subset=["Age","SG"])
    if not career.empty:
        sg_order=[g for g in SG_HIERARCHY if g in career["SG"].astype(str).unique()]
        career["SG Rank"]=career["SG"].astype(str).map({g:i for i,g in enumerate(sg_order)})
        fig3d=px.scatter_3d(career,x="Years of RE Experience",y="Age",z="Years in PET",color="SG",hover_name="Name",hover_data={c:True for c in ["Department","Staff Position"] if c in career.columns},category_orders={"SG":sg_order},height=650)
        fig3d.update_layout(scene={"xaxis_title":"Years of RE Experience","yaxis_title":"Age","zaxis_title":"Years in PET"},margin={"l":0,"r":0,"t":50,"b":0})
        st.plotly_chart(fig3d,width="stretch",config={"displaylogo":False,"responsive":True})
    else: st.info("No valid personnel records are available for the career landscape.")
else: st.info("Age, salary grade and experience fields are required for the 3D career landscape.")
