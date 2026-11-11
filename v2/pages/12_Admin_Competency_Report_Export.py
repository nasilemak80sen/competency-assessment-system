"""Admin-only export page for personnel competency reports."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json

import pandas as pd
import streamlit as st

from components.navigation import render_header, render_navigation
from config import COMPETENCY_FULLNAMES, EXCEL_PATH, SCORE_COLS
from core.auth import require_roles
from core.bootstrap import get_heatmap_data, get_ruler_data
from services.auth_service import ROLE_ADMIN
from services.heatmap_service import derive_competency_max_scores, ensure_employment_type_filter
from services.report_export_service import (
    build_competency_report_workbook,
    filter_personnel_for_export,
    get_sub_department_options,
    get_sub_unit_options,
    resolve_organisation_columns,
)

require_roles(ROLE_ADMIN)
render_navigation()
render_header(
    "🧾 Admin: Competency Report Export",
    "Filter personnel, select individuals and export their competency reports to Excel.",
)

personnel = ensure_employment_type_filter(get_heatmap_data())
if personnel.empty:
    st.warning("No personnel data is available for export.")
    st.stop()

sub_department_column, sub_unit_column = resolve_organisation_columns(personnel)
if not sub_department_column:
    st.error(
        "The personnel dataset does not contain a Sub-Department field. "
        "The expected current source is Unit Name."
    )
    st.stop()

if sub_department_column == "Unit Name":
    st.caption("Sub-Department is mapped to the existing master-data field Unit Name; Sub-Unit uses Sub Unit.")

# ---------------------------------------------------------------------------
# FILTERS
# ---------------------------------------------------------------------------
st.subheader("1. Filter personnel")
search_col, department_col, unit_col, grade_col = st.columns([2.2, 1.4, 1.4, 1.2])

with search_col:
    personnel_search = st.text_input(
        "Personnel Name / Staff ID",
        placeholder="Search by name or staff ID",
        key="report_export_search",
    )

with department_col:
    department_options = ["All", *get_sub_department_options(personnel)]
    selected_department = st.selectbox(
        "Sub-Department",
        options=department_options,
        key="report_export_sub_department",
    )

with unit_col:
    unit_options = ["All", *get_sub_unit_options(
        personnel,
        None if selected_department == "All" else selected_department,
    )]
    if st.session_state.get("report_export_sub_unit") not in unit_options:
        st.session_state["report_export_sub_unit"] = "All"
    selected_unit = st.selectbox(
        "Sub-Unit",
        options=unit_options,
        key="report_export_sub_unit",
        help="Options are narrowed by the selected Sub-Department.",
    )

with grade_col:
    def _grade_sort(value: str) -> tuple[int, str]:
        upper = str(value).strip().upper()
        if upper == "UPTREX":
            return (-1, upper)
        if upper.startswith("P") and upper[1:].isdigit():
            return (int(upper[1:]), upper)
        return (999, upper)

    grade_options = (
        sorted(
            [
                value for value in personnel["SG"].dropna().astype(str).str.strip().unique().tolist()
                if value
            ],
            key=_grade_sort,
        )
        if "SG" in personnel.columns
        else []
    )
    selected_grades = st.multiselect(
        "Salary Grade (SG)",
        options=grade_options,
        key="report_export_salary_grades",
    )

filtered_personnel = filter_personnel_for_export(
    personnel,
    search=personnel_search,
    sub_department=selected_department,
    sub_unit=selected_unit,
    salary_grades=selected_grades,
).reset_index(drop=True)

st.caption(
    f"{len(filtered_personnel):,} personnel match the current filters "
    f"out of {len(personnel):,} available records."
)

if filtered_personnel.empty:
    st.info("No personnel match these filters. Adjust the search or organisational filters.")
    st.stop()

preview_columns = [
    column for column in [
        "Name", "Staff ID", "Department", sub_department_column,
        sub_unit_column, "SG", "Employment Category",
    ]
    if column and column in filtered_personnel.columns
]
preview = filtered_personnel[preview_columns].copy()
preview = preview.rename(columns={
    sub_department_column: "Sub-Department",
    sub_unit_column: "Sub-Unit",
})
st.dataframe(preview, use_container_width=True, hide_index=True, height=300)

# ---------------------------------------------------------------------------
# PERSONNEL SELECTION
# ---------------------------------------------------------------------------
st.subheader("2. Select personnel")
person_labels: list[str] = []
label_to_position: dict[str, int] = {}
for position, (_, row) in enumerate(filtered_personnel.iterrows()):
    name_value = row.get("Name")
    name = "Unknown" if pd.isna(name_value) else str(name_value).strip()
    staff_id_value = row.get("Staff ID")
    staff_id = "" if pd.isna(staff_id_value) else str(staff_id_value).strip()
    label = f"{name or 'Unknown'} · {staff_id or 'No Staff ID'}"
    if label in label_to_position:
        label = f"{label} · record {position + 1}"
    person_labels.append(label)
    label_to_position[label] = position

selection_signature = hashlib.sha1(
    json.dumps(person_labels, ensure_ascii=False).encode("utf-8")
).hexdigest()[:12]

select_all = st.checkbox(
    "Select all filtered personnel",
    key=f"report_export_select_all_{selection_signature}",
)
selected_labels = st.multiselect(
    "Choose individual personnel",
    options=person_labels,
    default=[],
    disabled=select_all,
    key=f"report_export_selected_{selection_signature}",
    help="Choose one or more personnel, or use Select all filtered personnel.",
)

selected_positions = (
    list(range(len(filtered_personnel)))
    if select_all
    else [label_to_position[label] for label in selected_labels]
)
selected_personnel = filtered_personnel.iloc[selected_positions].copy()

metric_col, action_col = st.columns([1, 3])
with metric_col:
    st.metric("Selected Personnel", len(selected_personnel))
with action_col:
    st.caption("The export includes the original Personnel Master structure, a competency-level breakdown, assessment summaries and report metadata.")

if selected_personnel.empty:
    st.info("Select at least one person to prepare the Excel report.")
    st.stop()

# ---------------------------------------------------------------------------
# EXPORT
# ---------------------------------------------------------------------------
try:
    ruler_map, workbook_competency_names = get_ruler_data()
    maximum_scores = derive_competency_max_scores(ruler_map)
except Exception as exc:
    st.error(f"Unable to read the competency scoring reference from the master workbook: {exc}")
    st.stop()

missing_maxima = [code for code in SCORE_COLS if code not in maximum_scores]
if missing_maxima:
    st.error(
        "The scoring reference does not define a maximum level for: "
        + ", ".join(missing_maxima)
        + ". Export is stopped rather than inventing score limits."
    )
    st.stop()

competency_names = dict(COMPETENCY_FULLNAMES)
competency_names.update({
    code: name for code, name in workbook_competency_names.items() if name
})
export_filters = {
    "search": personnel_search,
    "sub_department": selected_department,
    "sub_unit": selected_unit,
    "salary_grades": selected_grades,
}

try:
    workbook_bytes = build_competency_report_workbook(
        source_workbook_path=EXCEL_PATH,
        personnel=selected_personnel,
        filters=export_filters,
        competency_names=competency_names,
        maximum_scores=maximum_scores,
    )
except Exception as exc:
    st.error(f"Unable to generate the competency report: {exc}")
    st.stop()

filename_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
st.download_button(
    "⬇️ Download Competency Reports (.xlsx)",
    data=workbook_bytes,
    file_name=f"competency_reports_{filename_timestamp}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
    use_container_width=True,
)
