"""Dashboard Home — faithful native-v2 reproduction of the golden app.py page."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import SG_HIERARCHY, SG_TO_POSITION_BRACKET, POSITION_HIERARCHY_ORDER
from core.bootstrap import get_master_data
from analytics.nationality import prepare_nationality_map_data
from components.openglobus import render_nationality_globe
from analytics.workforce import scatter_age_vs_grade
from components.navigation import render_navigation


render_navigation()

# =============================================================================
# PAGE: DASHBOARD HOME — GOLDEN APP PARITY
# =============================================================================

st.title("🏠 Dashboard Home")

df = get_master_data()

if df is None or df.empty:
    st.warning(
        "⚠️ No data in database yet. Go to **Admin: Import Data** "
        "to load the Excel master file."
    )
    st.stop()

# =============================================================================
# TOP METRICS ROW
# =============================================================================

c1, c2, c3, c4, c5 = st.columns(5)

total_personnel = len(df)
male_count = (
    df["Gender"].astype(str).str.strip().str.upper().eq("M").sum()
    if "Gender" in df.columns
    else 0
)
female_count = (
    df["Gender"].astype(str).str.strip().str.upper().eq("F").sum()
    if "Gender" in df.columns
    else 0
)
cdh_count = (
    df["Employment Category"].astype(str).str.strip().str.upper().eq("CDH").sum()
    if "Employment Category" in df.columns
    else 0
)
permanent_count = (
    df["Employment Category"].astype(str).str.strip().str.upper().eq("PERMANENT").sum()
    if "Employment Category" in df.columns
    else 0
)

with c1:
    st.metric("Total Personnel", int(total_personnel))
with c2:
    st.metric("Permanent Employees", int(permanent_count))
with c3:
    st.metric("CDH Employees", int(cdh_count))
with c4:
    st.metric("Male", int(male_count))
with c5:
    st.metric("Female", int(female_count))

# =============================================================================
# NATIONALITY DISTRIBUTION
# =============================================================================

st.markdown("---")
st.subheader("🌐 RE Nationalities")

nationality_map_df, unmatched_nationalities = prepare_nationality_map_data(df)

if not nationality_map_df.empty:
    top_nationalities = nationality_map_df.head(5)
    num_cols = min(len(top_nationalities), 5)
    if num_cols > 0:
        cols = st.columns(num_cols)
        for i, (_, row) in enumerate(top_nationalities.iterrows()):
            with cols[i]:
                st.metric(
                    label=row["Nationality"],
                    value=int(row["Personnel Count"]),
                    delta=row["Representation Display"],
                )

if nationality_map_df.empty:
    st.info(
        "No valid nationality data is available for the geographical visualization."
    )
else:
    render_nationality_globe(
        nationality_map_df,
        height=560,
    )
    st.caption(
        "OpenGlobus WebGL globe with interactive rotation, zoom and proportional "
        "nationality markers. Marker size represents personnel concentration; "
        "coordinates use approximate country centroids."
    )

if unmatched_nationalities:
    with st.expander("⚠️ Nationality values requiring mapping"):
        st.write(unmatched_nationalities)

# =============================================================================
# ROW 1: POSITION & SALARY GRADE DISTRIBUTIONS
# =============================================================================

col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Position Breakdown")

    if "SG" in df.columns and "Employment Category" in df.columns:
        df_chart = df.copy()
        df_chart["Position_Bracket"] = (
            df_chart["SG"].map(SG_TO_POSITION_BRACKET).fillna("Other")
        )
        df_chart["Clean_Emp_Category"] = (
            df_chart["Employment Category"]
            .astype(str)
            .str.strip()
            .str.upper()
            .map({"PERMANENT": "Permanent", "CDH": "CDH"})
            .fillna("Other")
        )

        pos_emp = (
            df_chart.groupby(["Position_Bracket", "Clean_Emp_Category"])
            .size()
            .unstack(fill_value=0)
        )
        present_pos = [
            p for p in POSITION_HIERARCHY_ORDER if p in pos_emp.index
        ]
        pos_emp = pos_emp.reindex(present_pos)

        for col_name in ["Permanent", "CDH"]:
            if col_name not in pos_emp.columns:
                pos_emp[col_name] = 0

        pos_emp["Total"] = pos_emp["Permanent"] + pos_emp["CDH"]
        plot_df = pos_emp.reset_index()

        fig = px.bar(
            plot_df,
            x="Position_Bracket",
            y=["Permanent", "CDH"],
            barmode="stack",
            title="",
            labels={
                "Position_Bracket": "Position",
                "value": "Personnel Count",
                "variable": "Type",
            },
            category_orders={"Position_Bracket": present_pos},
            color_discrete_map={"Permanent": "#20419A", "CDH": "#00A19C"},
        )
        fig.add_trace(
            go.Scatter(
                x=plot_df["Position_Bracket"],
                y=plot_df["Total"],
                text=plot_df["Total"],
                mode="text",
                textposition="top center",
                textfont=dict(size=12, color="black", family="sans-serif"),
                showlegend=False,
                hoverinfo="skip",
            )
        )
        fig.update_layout(
            height=380,
            margin=dict(l=10, r=10, t=30, b=20),
            xaxis_title="",
            yaxis_title="Count",
            legend=dict(
                orientation="h",
                y=1.1,
                x=0.5,
                xanchor="center",
                title_text="",
            ),
        )
        fig.update_traces(
            textposition="inside",
            texttemplate="%{y}",
            selector=dict(type="bar"),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Required data columns missing.")

with col2:
    st.subheader("📊 Salary Grade Distribution by Employment Type")

    if "SG" in df.columns and "Employment Category" in df.columns:
        df_chart = df.copy()
        df_chart["Clean_Emp_Category"] = (
            df_chart["Employment Category"]
            .astype(str)
            .str.strip()
            .str.upper()
            .map({"PERMANENT": "Permanent", "CDH": "CDH"})
            .fillna("Other")
        )
        sg_emp = (
            df_chart.groupby(["SG", "Clean_Emp_Category"])
            .size()
            .unstack(fill_value=0)
        )
        present_sgs = [g for g in SG_HIERARCHY if g in sg_emp.index]
        sg_emp = sg_emp.reindex(present_sgs)

        for col_name in ["Permanent", "CDH"]:
            if col_name not in sg_emp.columns:
                sg_emp[col_name] = 0

        sg_emp["Total"] = sg_emp["Permanent"] + sg_emp["CDH"]
        plot_df = sg_emp.reset_index()

        fig = px.bar(
            plot_df,
            x="SG",
            y=["Permanent", "CDH"],
            barmode="stack",
            title="",
            labels={
                "SG": "Salary Grade",
                "value": "Number of Personnel",
                "variable": "Employment Type",
            },
            category_orders={"SG": present_sgs},
            color_discrete_map={"Permanent": "#20419A", "CDH": "#00A19C"},
        )
        fig.add_trace(
            go.Scatter(
                x=plot_df["SG"],
                y=plot_df["Total"],
                text=plot_df["Total"],
                mode="text",
                textposition="top center",
                textfont=dict(size=12, color="black", family="sans-serif"),
                showlegend=False,
                hoverinfo="skip",
            )
        )
        fig.update_layout(
            height=400,
            margin=dict(l=10, r=20, t=40, b=20),
            xaxis_title="Salary Grade",
            yaxis_title="Number of Personnel",
            legend=dict(
                title="Employment Type",
                yanchor="top",
                y=0.99,
                xanchor="right",
                x=0.99,
            ),
            yaxis=dict(
                range=[0, plot_df["Total"].max() * 1.15]
                if not plot_df.empty
                else [0, 10]
            ),
        )
        fig.update_traces(
            textposition="inside",
            texttemplate="%{y}",
            selector=dict(type="bar"),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(
            "Salary Grade or Employment Category data not available for this visualization."
        )

# =============================================================================
# ROW 2: SECTION / OFFICE / DEPARTMENT DISTRIBUTIONS
# =============================================================================

col3, col4, col5 = st.columns(3)

with col5:
    st.subheader("🏢 Department Distribution")
    if "Department" in df.columns:
        dept = df["Department"].value_counts().reset_index()
        dept.columns = ["Department", "Count"]
        total_count = dept["Count"].sum()
        threshold = 0.027
        if total_count:
            dept["Department"] = dept.apply(
                lambda row: row["Department"]
                if (row["Count"] / total_count) >= threshold
                else "International",
                axis=1,
            )
        dept_grouped = dept.groupby("Department", as_index=False)["Count"].sum()
        dept_grouped = dept_grouped.sort_values(by=["Count"], ascending=False)

        fig = px.pie(
            dept_grouped,
            names="Department",
            values="Count",
            hole=0.2,
            color_discrete_sequence=px.colors.sequential.Plasma,
        )
        fig.update_traces(
            textposition="inside",
            textinfo="percent+label",
            hovertemplate=(
                "<b>%{label}</b><br>Count: %{value}<br>Share: %{percent}"
            ),
        )
        fig.update_layout(
            height=500,
            margin=dict(t=20, b=20, l=10, r=10),
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.1,
                xanchor="center",
                x=0.5,
                title_text="",
            ),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Department data not available")

with col3:
    st.subheader("🌏 Section Distribution")
    if "Section Name" in df.columns:
        section = df["Section Name"].value_counts().reset_index()
        section.columns = ["Section Name", "Count"]
        threshold = 4
        main_sections = section[section["Count"] >= threshold].copy()
        other_sections = section[section["Count"] < threshold].copy()

        if len(other_sections) > 0:
            other_row = pd.DataFrame(
                {"Section Name": ["Other"], "Count": [other_sections["Count"].sum()]}
            )
            section_final = pd.concat(
                [main_sections, other_row], ignore_index=True
            )
        else:
            section_final = main_sections

        section_final = section_final.sort_values(
            "Count", ascending=False
        ).reset_index(drop=True)
        section_final["y_position"] = range(len(section_final))

        fig = px.scatter(
            section_final,
            x="Count",
            y="y_position",
            size="Count",
            color="Count",
            hover_name="Section Name",
            color_discrete_sequence=px.colors.qualitative.G10,
            size_max=75,
        )
        fig.update_traces(
            hovertemplate="<b>%{hovertext}</b><br>Personnel: %{x}<extra></extra>"
        )
        fig.update_layout(
            height=500,
            showlegend=False,
            coloraxis_showscale=False,
            margin=dict(l=10, r=20, t=40, b=20),
            xaxis_title="Number of Personnel",
            yaxis_title="",
            yaxis=dict(
                tickmode="array",
                tickvals=list(range(len(section_final))),
                ticktext=section_final["Section Name"].tolist(),
                showgrid=False,
            ),
            hovermode="closest",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Section data not available")

with col4:
    st.subheader("🏢 Office Location Distribution")
    if "Current Location:" in df.columns:
        assignment_df = df["Current Location:"].value_counts().reset_index()
        assignment_df.columns = ["Current Assignment", "Count"]
        assignment_df = assignment_df.sort_values("Count", ascending=True)
        chart_height = max(500, len(assignment_df) * 25)

        fig = px.bar(
            assignment_df,
            x="Count",
            y="Current Assignment",
            orientation="h",
            text="Count",
            color="Count",
            color_continuous_scale="Emrld",
        )
        fig.update_traces(
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Count: %{x}<extra></extra>",
        )
        fig.update_layout(
            height=chart_height,
            showlegend=False,
            coloraxis_showscale=False,
            margin=dict(l=10, r=30, t=40, b=20),
            xaxis_title="Number of Personnel",
            yaxis_title="",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Office location data not available")

# =============================================================================
# ROW 3: GENDER DISTRIBUTION & GRADE DISTRIBUTION BY GENDER
# =============================================================================

col3, col4 = st.columns(2)

with col3:
    st.subheader("👥 Gender Distribution")
    if "Gender" in df.columns:
        gender_counts = df["Gender"].value_counts().reset_index()
        gender_counts.columns = ["Gender", "Count"]
        gender_counts["Gender"] = gender_counts["Gender"].map(
            {"M": "Male", "F": "Female"}
        )
        fig = px.pie(
            gender_counts,
            names="Gender",
            values="Count",
            hole=0.35,
            color_discrete_map={"Male": "#20419a", "Female": "#763f98"},
            labels={"Count": "Number"},
        )
        fig.update_traces(textposition="inside", textinfo="label+percent")
        fig.update_layout(height=400, showlegend=True)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Gender data not available")

with col4:
    st.subheader("📈 Grade (SG) Distribution by Gender")
    if "SG" in df.columns and "Gender" in df.columns:
        sg_gender = pd.crosstab(df["SG"], df["Gender"])
        rename_dict = {}
        if "M" in sg_gender.columns:
            rename_dict["M"] = "Male"
        if "F" in sg_gender.columns:
            rename_dict["F"] = "Female"
        sg_gender = sg_gender.rename(columns=rename_dict)

        order = ["UPTREX"] + [f"P{i}" for i in range(1, 11)]
        present = [g for g in order if g in sg_gender.index]
        sg_gender = sg_gender.reindex(present)

        age_by_grade = (
            df.groupby("SG").agg(avg_age=("Age", "mean")).reset_index()
        )
        age_by_grade = age_by_grade[age_by_grade["SG"].isin(present)]
        age_by_grade = (
            age_by_grade.set_index("SG").reindex(present).reset_index()
        )

        available_gender_cols = [
            col for col in ["Male", "Female"] if col in sg_gender.columns
        ]

        fig = px.bar(
            sg_gender.reset_index(),
            x="SG",
            y=available_gender_cols,
            barmode="stack",
            title="",
            labels={
                "SG": "Salary Grade",
                "value": "Number of Personnel",
                "variable": "Gender",
            },
            color_discrete_map={"Male": "#20419a", "Female": "#763f98"},
        )
        fig.add_trace(
            go.Scatter(
                x=age_by_grade["SG"],
                y=age_by_grade["avg_age"],
                name="Average Age",
                mode="lines+markers",
                marker=dict(color="#bfd730", size=8),
                yaxis="y2",
            )
        )
        fig.update_layout(
            xaxis_title="Salary Grade",
            yaxis_title="Number of Personnel",
            height=400,
            hovermode="x unified",
            legend=dict(
                orientation="h",
                yanchor="top",
                y=-0.1,
                xanchor="center",
                x=0.1,
                title_text="",
            ),
            yaxis2=dict(
                title="Average Age",
                overlaying="y",
                side="right",
                showgrid=False,
            ),
        )
        fig.update_traces(
            textposition="auto",
            texttemplate="%{y}",
            selector=dict(type="bar"),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Grade or Gender data not available")

# =============================================================================
# ROW 4: AGE VS SALARY GRADE / CAREER LANDSCAPE
# =============================================================================

st.subheader("📈 Age vs Salary Grade Analysis")


def create_hover_text(row):
    html = f"<b>{row.get('Name', 'Unknown')}</b><br>"
    html += f"<i>{row.get('Staff Position', 'N/A')}</i><br>"
    html += (
        f"<span style='color: gray;'>{row.get('Department', 'N/A')}</span><br>"
    )

    age = row.get("Age", "N/A")
    try:
        age_display = f"{float(age):.0f}" if pd.notna(age) else "N/A"
    except (ValueError, TypeError):
        age_display = age

    html += (
        f"<b>Age:</b> {age_display} | "
        f"<b>Salary Grade:</b> {row.get('SG', 'N/A')}<br>"
    )

    if pd.notna(row.get("Years of RE Experience")):
        html += (
            f"<b>RE Experience:</b> "
            f"{float(row['Years of RE Experience']):.2f} Years<br>"
        )
    if pd.notna(row.get("Years in PET")):
        html += (
            f"<b>PET Experience:</b> "
            f"{float(row['Years in PET']):.2f} Years<br>"
        )

    return html

min_pet = float(pd.to_numeric(df["Years in PET"], errors="coerce").fillna(0).min())
max_pet = float(pd.to_numeric(df["Years in PET"], errors="coerce").fillna(0).max())
min_re = float(
    pd.to_numeric(df["Years of RE Experience"], errors="coerce").fillna(0).min()
)
max_re = float(
    pd.to_numeric(df["Years of RE Experience"], errors="coerce").fillna(0).max()
)

c1, c2, c3 = st.columns(3)
with c1:
    f_name = st.multiselect(
        "Filter by Personnel",
        sorted(df["Name"].dropna().unique()),
        key="dash_name",
    )
with c2:
    f_unit = st.multiselect(
        "Filter by Unit Name",
        sorted(df["Unit Name"].dropna().unique()),
        key="dash_unit1",
    )
with c3:
    f_pos = st.multiselect(
        "Filter by Position",
        sorted(df["Staff Position"].dropna().unique()),
        key="dash_pos1",
    )

c4, c5 = st.columns(2)
with c4:
    f_pet_range = st.slider(
        "Filter by Years in PETRONAS: ",
        min_value=min_pet,
        max_value=max_pet,
        value=(min_pet, max_pet),
        step=1.0,
        key="dash_pet_range",
    )
with c5:
    f_re_range = st.slider(
        "Filter by Years in RE Experience",
        min_value=min_re,
        max_value=max_re,
        value=(min_re, max_re),
        step=1.0,
        key="dash_re_range",
    )

tab2d, tab3d = st.tabs(
    ["📊 Career Distribution (2D)", "🌐 Career Progression (3D)"]
)

fdf1 = df.copy()
if f_name:
    fdf1 = fdf1[fdf1["Name"].isin(f_name)]
if f_unit:
    fdf1 = fdf1[fdf1["Unit Name"].isin(f_unit)]
if f_pos:
    fdf1 = fdf1[fdf1["Staff Position"].isin(f_pos)]

fdf1 = fdf1[
    (pd.to_numeric(fdf1["Years in PET"], errors="coerce").fillna(0) >= f_pet_range[0])
    & (pd.to_numeric(fdf1["Years in PET"], errors="coerce").fillna(0) <= f_pet_range[1])
]
fdf1 = fdf1[
    (
        pd.to_numeric(
            fdf1["Years of RE Experience"], errors="coerce"
        ).fillna(0)
        >= f_re_range[0]
    )
    & (
        pd.to_numeric(
            fdf1["Years of RE Experience"], errors="coerce"
        ).fillna(0)
        <= f_re_range[1]
    )
]

sg_order = ["UPTREX"] + [f"P{i}" for i in range(1, 11)]
scatter_df2 = scatter_age_vs_grade(fdf1)

re_exp_col = "Years of RE Experience"
color_col = None
size_col = None

if re_exp_col in scatter_df2.columns:
    scatter_df2[re_exp_col] = pd.to_numeric(
        scatter_df2[re_exp_col], errors="coerce"
    )
    bins = [-float("inf"), 2, 5, 10, 15, float("inf")]
    labels = ["< 2 Yrs", "2 - 5 Yrs", "5 - 10 Yrs", "10 - 15 Yrs", "15+ Yrs"]
    scatter_df2["RE Experience Tier"] = pd.cut(
        scatter_df2[re_exp_col], bins=bins, labels=labels, right=False
    )
    scatter_df2["RE Experience Tier"] = (
        scatter_df2["RE Experience Tier"]
        .astype(object)
        .where(scatter_df2[re_exp_col].notna(), "Unknown / Unspecified")
    )
    color_col = "RE Experience Tier"
    scatter_df2["RE Experience Bubble Size"] = (
        scatter_df2[re_exp_col].fillna(0).clip(lower=0)
    )
    size_col = "RE Experience Bubble Size"
else:
    st.warning(
        f"'{re_exp_col}' is not available in the scatter dataset. "
        "RE Experience cannot be used for colour or bubble size."
    )

if not scatter_df2.empty:
    scatter_df2["Beautiful_Hover"] = scatter_df2.apply(create_hover_text, axis=1)

with tab2d:
    st.info(
        """
        **Purpose**
        This chart compares **Age** against **Salary Grade (SG)**. 
        Each color in the legend represents **Years in RE Experience**.
        """
    )
    if scatter_df2.empty:
        st.info("No personnel match the selected career filters.")
    else:
        fig = px.scatter(
            scatter_df2,
            x="Age",
            y="SG",
            color=color_col,
            size=size_col,
            size_max=40,
            custom_data=["Beautiful_Hover"],
            category_orders={
                "SG": sg_order,
                "RE Experience Tier": [
                    "< 2 Yrs",
                    "2 - 5 Yrs",
                    "5 - 10 Yrs",
                    "10 - 15 Yrs",
                    "15+ Yrs",
                    "Unknown / Unspecified",
                ],
            },
            color_discrete_sequence=px.colors.qualitative.Bold,
            title="Age vs Salary Grade",
        )
        fig.update_traces(
            hovertemplate="%{customdata[0]}<extra></extra>",
            marker=dict(opacity=0.85, line=dict(width=1, color="white")),
        )
        fig.update_layout(
            height=700,
            xaxis_title="Age",
            yaxis_title="Salary Grade",
            plot_bgcolor="#FFFFFF",
            legend_title_text="RE Experience",
        )
        st.plotly_chart(fig, use_container_width=True, key="scatter_2d_age_sg")

with tab3d:
    if scatter_df2.empty:
        st.info("No personnel match the selected career filters.")
    else:
        fig_3d = px.scatter_3d(
            scatter_df2,
            x="Age",
            y="SG",
            z="Years of RE Experience",
            color=color_col,
            size=size_col,
            custom_data=["Beautiful_Hover"],
            category_orders={
                "SG": sg_order,
                "RE Experience Tier": [
                    "< 2 Yrs",
                    "2 - 5 Yrs",
                    "5 - 10 Yrs",
                    "10 - 15 Yrs",
                    "15+ Yrs",
                    "Unknown / Unspecified",
                ],
            },
            color_discrete_sequence=px.colors.qualitative.Bold,
            title="Career Progression Landscape",
        )
        fig_3d.update_traces(
            hovertemplate="%{customdata[0]}<extra></extra>",
            marker=dict(opacity=0.85, line=dict(width=1, color="white")),
        )
        fig_3d.update_layout(
            height=800,
            legend_title_text="RE Experience",
            scene=dict(
                xaxis=dict(title="Age"),
                yaxis=dict(
                    title="Salary Grade",
                    tickmode="array",
                    tickvals=list(range(len(sg_order))),
                    ticktext=sg_order,
                ),
                zaxis=dict(title="Years in PET"),
            ),
        )
        st.plotly_chart(
            fig_3d,
            use_container_width=True,
            key="scatter_3d_career_landscape",
        )

st.markdown("---")
