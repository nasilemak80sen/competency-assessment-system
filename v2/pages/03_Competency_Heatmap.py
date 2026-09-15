"""Competency Heatmap — faithful native-v2 reproduction of the golden app.py page."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.navigation import render_navigation, render_header
from config import COMP_TYPES, COMPETENCY_FULLNAMES, HEATMAP_COLORSCALE
from core.bootstrap import get_master_data


render_navigation()
render_header(
    "🌡️ Competency Heatmap",
    "Explore actual competency scores across personnel with filtering, ranking and summary analysis",
)

df = get_master_data()
if df is None or df.empty:
    st.warning("No personnel data is available.")
    st.stop()

# -----------------------------------------------------------------------------
# FILTERS
# -----------------------------------------------------------------------------

filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)

with filter_col1:
    f_dept = st.multiselect(
        "Department",
        options=sorted(df["Department"].dropna().astype(str).unique())
        if "Department" in df.columns
        else [],
        key="hm_dept",
    )

with filter_col2:
    f_pos = st.multiselect(
        "Position",
        options=sorted(df["Staff Position"].dropna().astype(str).unique())
        if "Staff Position" in df.columns
        else [],
        key="hm_pos",
    )

with filter_col3:
    def _grade_sort(value):
        value = str(value).strip().upper()
        if value.startswith("P") and value[1:].isdigit():
            return int(value[1:])
        if value.upper() == "UPTREX":
            return -1
        return 999

    f_sg = st.multiselect(
        "Salary Grade",
        options=sorted(
            df["SG"].dropna().astype(str).unique(),
            key=_grade_sort,
        )
        if "SG" in df.columns
        else [],
        key="hm_sg",
    )

with filter_col4:
    f_type = st.multiselect(
        "Competency Type",
        options=list(COMP_TYPES.keys()),
        default=list(COMP_TYPES.keys()),
        format_func=lambda code: COMP_TYPES.get(code, {}).get("label", code),
        key="hm_type",
    )

control_col1, control_col2, control_col3 = st.columns(3)

with control_col1:
    sort_option = st.selectbox(
        "Sort personnel by",
        options=[
            "Name",
            "Average score: high to low",
            "Average score: low to high",
            "Low-score cells: high to low",
            "Assessment coverage: low to high",
        ],
        key="hm_sort",
    )

with control_col2:
    show_score_labels = st.checkbox(
        "Show score inside cells",
        value=True,
        help=(
            "Score labels are automatically hidden when too many personnel are displayed."
        ),
        key="hm_show_labels",
    )

with control_col3:
    minimum_coverage = st.slider(
        "Minimum assessment coverage",
        min_value=0,
        max_value=100,
        value=0,
        step=5,
        format="%d%%",
        key="hm_min_coverage",
    )

# -----------------------------------------------------------------------------
# APPLY FILTERS
# -----------------------------------------------------------------------------

fdf = df.copy()

if f_dept:
    fdf = fdf[fdf["Department"].isin(f_dept)]
if f_pos:
    fdf = fdf[fdf["Staff Position"].isin(f_pos)]
if f_sg:
    fdf = fdf[fdf["SG"].isin(f_sg)]

value_cols: list[str] = []
for competency_type in f_type:
    configured_columns = COMP_TYPES.get(competency_type, {}).get("cols", [])
    value_cols.extend(column for column in configured_columns if column in fdf.columns)
value_cols = list(dict.fromkeys(value_cols))

if not value_cols:
    st.info("Select at least one competency type.")
    st.stop()

if fdf.empty:
    st.warning("No personnel match the selected filters.")
    st.stop()

# -----------------------------------------------------------------------------
# BUILD HEATMAP DATASET
# -----------------------------------------------------------------------------

heatmap_data = fdf.copy()
for competency in value_cols:
    heatmap_data[competency] = pd.to_numeric(heatmap_data[competency], errors="coerce")


def build_personnel_label(row: pd.Series) -> str:
    name = row.get("Name")
    staff_id = row.get("Staff ID")
    sg = row.get("SG")

    name_display = str(name).strip() if name is not None and pd.notna(name) else "Unknown"
    label_parts = [name_display]

    if staff_id is not None and pd.notna(staff_id) and str(staff_id).strip():
        label_parts.append(str(staff_id).strip())
    if sg is not None and pd.notna(sg) and str(sg).strip():
        label_parts.append(str(sg).strip())

    return " | ".join(label_parts)


heatmap_data["Heatmap Label"] = heatmap_data.apply(build_personnel_label, axis=1)
heatmap_data = heatmap_data[heatmap_data[value_cols].notna().any(axis=1)].copy()

if heatmap_data.empty:
    st.warning("No assessed personnel match the selected filters.")
    st.stop()

heatmap_data["Average Score"] = heatmap_data[value_cols].mean(axis=1)
heatmap_data["Assessed Competencies"] = heatmap_data[value_cols].notna().sum(axis=1)
heatmap_data["Missing Competencies"] = len(value_cols) - heatmap_data["Assessed Competencies"]
heatmap_data["Assessment Coverage %"] = (
    heatmap_data["Assessed Competencies"] / len(value_cols) * 100
)
heatmap_data["High Score Cells"] = heatmap_data[value_cols].ge(4).sum(axis=1)
heatmap_data["Low Score Cells"] = heatmap_data[value_cols].le(2).sum(axis=1)

heatmap_data = heatmap_data[
    heatmap_data["Assessment Coverage %"] >= minimum_coverage
].copy()

if heatmap_data.empty:
    st.warning("No personnel meet the selected minimum assessment coverage.")
    st.stop()

# -----------------------------------------------------------------------------
# SORT PERSONNEL
# -----------------------------------------------------------------------------

if sort_option == "Name":
    heatmap_data = heatmap_data.sort_values("Name", ascending=True, na_position="last")
elif sort_option == "Average score: high to low":
    heatmap_data = heatmap_data.sort_values("Average Score", ascending=False, na_position="last")
elif sort_option == "Average score: low to high":
    heatmap_data = heatmap_data.sort_values("Average Score", ascending=True, na_position="last")
elif sort_option == "Low-score cells: high to low":
    heatmap_data = heatmap_data.sort_values(
        ["Low Score Cells", "Average Score"],
        ascending=[False, True],
        na_position="last",
    )
elif sort_option == "Assessment coverage: low to high":
    heatmap_data = heatmap_data.sort_values(
        ["Assessment Coverage %", "Name"],
        ascending=[True, True],
        na_position="last",
    )

mat = heatmap_data.set_index("Heatmap Label")[value_cols]
score_values = mat.to_numpy(dtype=float)
valid_scores = score_values[~np.isnan(score_values)]
possible_cells = len(mat) * len(value_cols)
assessed_cells = len(valid_scores)
missing_cells = possible_cells - assessed_cells
coverage_pct = assessed_cells / possible_cells * 100 if possible_cells > 0 else 0.0
average_score = float(np.mean(valid_scores)) if assessed_cells > 0 else np.nan
high_score_cells = int((valid_scores >= 4).sum()) if assessed_cells > 0 else 0
low_score_cells = int((valid_scores <= 2).sum()) if assessed_cells > 0 else 0

# -----------------------------------------------------------------------------
# OVERALL METRICS
# -----------------------------------------------------------------------------

st.markdown("---")
metric1, metric2, metric3, metric4, metric5 = st.columns(5)
metric1.metric("Personnel Shown", len(mat))
metric2.metric("Average Score", f"{average_score:.2f}" if not np.isnan(average_score) else "N/A")
metric3.metric(
    "High Score Cells",
    high_score_cells,
    help="Number of individual competency scores that are 4 or higher.",
)
metric4.metric(
    "Low Score Cells",
    low_score_cells,
    help="Number of individual competency scores that are 2 or lower. This does not automatically mean there is a target gap.",
)
metric5.metric(
    "Assessment Coverage",
    f"{coverage_pct:.0f}%",
    help="Populated competency-score cells divided by all possible cells in the displayed matrix.",
)
st.caption(
    f"Showing {len(mat)} personnel × {len(value_cols)} competencies. "
    f"{assessed_cells:,} assessed cells and {missing_cells:,} missing cells."
)

# -----------------------------------------------------------------------------
# HEATMAP DISPLAY
# -----------------------------------------------------------------------------

st.subheader("Actual Competency Score Matrix")
st.caption(
    "Rows represent personnel and columns represent competencies. "
    "Borders separate each person and competency for easier reading. "
    "Blank cells indicate that no score is available."
)

competency_name_map = COMPETENCY_FULLNAMES.copy()
competency_full_names = [competency_name_map.get(competency, competency) for competency in value_cols]
hover_competency_names = np.tile(np.array(competency_full_names, dtype=object), (len(mat), 1))

display_cell_labels = show_score_labels and len(mat) <= 40 and len(value_cols) <= 24
if display_cell_labels:
    text_values = np.where(np.isnan(score_values), "", np.round(score_values).astype(object))
    text_values = np.vectorize(lambda value: "" if value == "" else str(int(value)))(text_values)
    text_template = "%{text}"
else:
    text_values = None
    text_template = None
    if show_score_labels:
        st.info(
            "Score labels were hidden automatically because the displayed matrix is too large. "
            "Hover over a cell to see its score."
        )

chart_height = min(max(500, 32 * len(mat) + 170), 1800)

fig = go.Figure(
    data=go.Heatmap(
        z=score_values,
        x=value_cols,
        y=mat.index.tolist(),
        text=text_values,
        texttemplate=text_template,
        textfont={"size": 11, "color": "white"},
        customdata=hover_competency_names,
        colorscale=HEATMAP_COLORSCALE,
        zmin=0,
        zmax=5,
        xgap=1.5,
        ygap=1.5,
        colorbar={
            "title": {"text": "Score"},
            "tickmode": "array",
            "tickvals": [0, 1, 2, 3, 4, 5],
            "ticktext": ["0", "1", "2", "3", "4", "5"],
            "len": 0.85,
        },
        hoverongaps=False,
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Competency: %{x}<br>"
            "Competency Name: %{customdata}<br>"
            "Actual Score: %{z:.0f}<extra></extra>"
        ),
    )
)

fig.update_layout(
    height=chart_height,
    plot_bgcolor="#30343F",
    paper_bgcolor="rgba(0,0,0,0)",
    margin={"l": 20, "r": 40, "t": 20, "b": 80},
    xaxis={
        "title": "Competency",
        "side": "top",
        "tickangle": 0,
        "tickmode": "array",
        "tickvals": value_cols,
        "ticktext": value_cols,
        "showgrid": False,
        "fixedrange": False,
    },
    yaxis={
        "title": "",
        "autorange": "reversed",
        "showgrid": False,
        "tickfont": {"size": 11},
        "automargin": True,
        "fixedrange": False,
    },
    hoverlabel={"bgcolor": "#FFFFFF", "font": {"color": "#1F2937", "size": 12}},
)

st.plotly_chart(
    fig,
    use_container_width=True,
    config={
        "displayModeBar": True,
        "displaylogo": False,
        "scrollZoom": True,
        "modeBarButtonsToRemove": ["lasso2d", "select2d"],
        "toImageButtonOptions": {
            "format": "png",
            "filename": "competency_heatmap",
            "height": chart_height,
            "width": 1800,
            "scale": 2,
        },
    },
)

# -----------------------------------------------------------------------------
# SUMMARY TABLES
# -----------------------------------------------------------------------------

st.markdown("---")
st.subheader("📋 Heatmap Analysis Summary")
st.caption(
    "Use the personnel summary to identify broad score patterns. "
    "Use the competency summary to identify common strengths, low-score concentrations, "
    "and assessment-data gaps."
)

personnel_tab, competency_tab, category_tab = st.tabs(
    ["Personnel Summary", "Competency Summary", "Category Summary"]
)

with personnel_tab:
    personnel_summary = heatmap_data[
        [
            "Name",
            "Staff ID",
            "Department",
            "Staff Position",
            "SG",
            "Assessed Competencies",
            "Missing Competencies",
            "Assessment Coverage %",
            "High Score Cells",
            "Low Score Cells",
        ]
    ].copy()
    personnel_summary["Assessment Coverage %"] = personnel_summary["Assessment Coverage %"].round(1)
    personnel_summary = personnel_summary.rename(
        columns={"High Score Cells": "Scores ≥4", "Low Score Cells": "Scores ≤2"}
    )
    st.dataframe(
        personnel_summary,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Assessment Coverage %": st.column_config.ProgressColumn(
                "Assessment Coverage", min_value=0, max_value=100, format="%.0f%%"
            ),
            "Assessed Competencies": st.column_config.NumberColumn("Assessed", format="%d"),
            "Missing Competencies": st.column_config.NumberColumn("Missing", format="%d"),
        },
    )
    st.download_button(
        "⬇️ Download Personnel Summary",
        data=personnel_summary.to_csv(index=False).encode("utf-8"),
        file_name="heatmap_personnel_summary.csv",
        mime="text/csv",
    )

with competency_tab:
    competency_records = []
    for competency in value_cols:
        competency_scores = pd.to_numeric(mat[competency], errors="coerce")
        valid_competency_scores = competency_scores.dropna()
        assessed_count = len(valid_competency_scores)
        missing_count = len(mat) - assessed_count
        competency_coverage = assessed_count / len(mat) * 100 if len(mat) > 0 else 0.0
        competency_records.append(
            {
                "Competency": competency,
                "Competency Name": competency_name_map.get(competency, competency),
                "Category": COMP_TYPES.get(competency[0], {}).get("label", competency[0]),
                "Average Score": valid_competency_scores.mean() if assessed_count > 0 else np.nan,
                "Minimum Score": valid_competency_scores.min() if assessed_count > 0 else np.nan,
                "Maximum Score": valid_competency_scores.max() if assessed_count > 0 else np.nan,
                "Assessed Personnel": assessed_count,
                "Missing Personnel": missing_count,
                "Coverage %": competency_coverage,
                "Scores ≥4": int((valid_competency_scores >= 4).sum()),
                "Scores ≤2": int((valid_competency_scores <= 2).sum()),
            }
        )

    competency_summary = pd.DataFrame(competency_records)
    competency_summary["Average Score"] = competency_summary["Average Score"].round(2)
    competency_summary["Minimum Score"] = competency_summary["Minimum Score"].round(0).astype("Int64")
    competency_summary["Maximum Score"] = competency_summary["Maximum Score"].round(0).astype("Int64")
    competency_summary["Coverage %"] = competency_summary["Coverage %"].round(1)
    competency_summary = competency_summary.sort_values(
        ["Average Score", "Scores ≤2"], ascending=[True, False], na_position="last"
    )
    st.dataframe(
        competency_summary,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Coverage %": st.column_config.ProgressColumn(
                "Assessment Coverage", min_value=0, max_value=100, format="%.0f%%"
            )
        },
    )
    st.download_button(
        "⬇️ Download Competency Summary",
        data=competency_summary.to_csv(index=False).encode("utf-8"),
        file_name="heatmap_competency_summary.csv",
        mime="text/csv",
    )

with category_tab:
    category_records = []
    for category_code in f_type:
        category_columns = [
            competency
            for competency in COMP_TYPES.get(category_code, {}).get("cols", [])
            if competency in mat.columns
        ]
        if not category_columns:
            continue
        category_values = mat[category_columns].to_numpy(dtype=float)
        valid_category_values = category_values[~np.isnan(category_values)]
        possible_category_cells = len(mat) * len(category_columns)
        assessed_category_cells = len(valid_category_values)
        category_coverage = (
            assessed_category_cells / possible_category_cells * 100
            if possible_category_cells > 0
            else 0.0
        )
        category_records.append(
            {
                "Category Code": category_code,
                "Category": COMP_TYPES.get(category_code, {}).get("label", category_code),
                "Competencies": len(category_columns),
                "Scores ≥4": int((valid_category_values >= 4).sum()),
                "Scores ≤2": int((valid_category_values <= 2).sum()),
                "Assessed Cells": assessed_category_cells,
                "Missing Cells": possible_category_cells - assessed_category_cells,
                "Coverage %": category_coverage,
            }
        )

    category_summary = pd.DataFrame(category_records)
    if category_summary.empty:
        st.info("No competency categories are available for the selected filters.")
    else:
        category_summary["Coverage %"] = category_summary["Coverage %"].round(1)
        st.dataframe(
            category_summary,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Coverage %": st.column_config.ProgressColumn(
                    "Assessment Coverage", min_value=0, max_value=100, format="%.0f%%"
                )
            },
        )
