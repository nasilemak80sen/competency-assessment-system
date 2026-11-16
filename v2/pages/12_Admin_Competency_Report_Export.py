"""Admin-only export workspace for personnel competency reports."""
from __future__ import annotations

from datetime import datetime
import hashlib

import pandas as pd
import streamlit as st

from components.navigation import render_header, render_navigation
from config import COMPETENCY_FULLNAMES, EXCEL_PATH, SCORE_COLS
from core.auth import require_roles
from core.bootstrap import get_heatmap_data
from services.auth_service import ROLE_ADMIN
from services.heatmap_service import (
    ensure_employment_type_filter,
    get_configured_competency_max_scores,
)
from services.report_export_service import (
    build_competency_report_workbook,
    build_personnel_selection_keys,
    filter_personnel_for_export,
    get_sub_department_options,
    get_sub_unit_options,
    merge_visible_selection,
    set_visible_selection,
    resolve_organisation_columns,
)


require_roles(ROLE_ADMIN)
render_navigation()
render_header(
    "🧾 Admin: Competency Report Export",
    "Filter personnel, select records and export a structured Excel workbook.",
)

personnel = ensure_employment_type_filter(get_heatmap_data())
if personnel.empty:
    st.warning("No personnel data is available for export.")
    st.stop()

sub_department_column, sub_unit_column = resolve_organisation_columns(personnel)
if not sub_department_column or not sub_unit_column:
    st.error(
        "The personnel dataset must contain Sub-Department and Sub-Unit fields. "
        "The current master-data mapping is Unit Name and Sub Unit."
    )
    st.stop()

if sub_department_column == "Unit Name":
    st.caption(
        "Organisation mapping: **Sub-Department** uses the master-data field "
        "Unit Name; **Sub-Unit** uses Sub Unit."
    )

# Selection state is held independently of the active filters.
SELECTION_STATE_KEY = "report_export_selected_personnel_keys"
SELECTION_VERSION_KEY = "report_export_selection_version"
if SELECTION_STATE_KEY not in st.session_state:
    st.session_state[SELECTION_STATE_KEY] = []
if SELECTION_VERSION_KEY not in st.session_state:
    st.session_state[SELECTION_VERSION_KEY] = 0

all_personnel = personnel.copy().reset_index(drop=True)
all_personnel["__selection_key"] = build_personnel_selection_keys(all_personnel)
available_keys = set(all_personnel["__selection_key"].tolist())

# Clear stale choices if the underlying source no longer contains a person.
selected_keys = set(st.session_state[SELECTION_STATE_KEY]) & available_keys
st.session_state[SELECTION_STATE_KEY] = sorted(selected_keys)

# -----------------------------------------------------------------------------
# 01 · FILTER PERSONNEL
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("01 · Filter personnel")
st.caption("Combine filters to narrow the personnel list. Leave a filter empty to include all values.")

clear_col, search_col, department_col, unit_col, grade_col = st.columns([0.75, 2.0, 1.5, 1.5, 1.25])
with clear_col:
    st.write("")
    if st.button("Clear filters", key="report_export_clear_filters", help="Reset all filters"):
        st.session_state["report_export_search"] = ""
        st.session_state["report_export_sub_departments"] = []
        st.session_state["report_export_sub_units"] = []
        st.session_state["report_export_salary_grades"] = []
        st.rerun()

with search_col:
    personnel_search = st.text_input(
        "Personnel name / Staff ID",
        placeholder="Search name or Staff ID",
        key="report_export_search",
    )

with department_col:
    department_options = get_sub_department_options(all_personnel)
    selected_departments = st.multiselect(
        "Sub-Department",
        options=department_options,
        key="report_export_sub_departments",
        placeholder="All Sub-Departments",
        help="Select one or more Sub-Departments. Leave empty to include all.",
    )

with unit_col:
    unit_options = get_sub_unit_options(all_personnel, selected_departments or None)
    current_units = st.session_state.get("report_export_sub_units", [])
    valid_units = [value for value in current_units if value in unit_options]
    if valid_units != current_units:
        st.session_state["report_export_sub_units"] = valid_units
    selected_units = st.multiselect(
        "Sub-Unit",
        options=unit_options,
        key="report_export_sub_units",
        placeholder="All Sub-Units",
        help="Options automatically narrow to the selected Sub-Departments.",
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
                value for value in all_personnel["SG"].dropna().astype(str).str.strip().unique().tolist()
                if value
            ],
            key=_grade_sort,
        )
        if "SG" in all_personnel.columns
        else []
    )
    selected_grades = st.multiselect(
        "Salary Grade (SG)",
        options=grade_options,
        key="report_export_salary_grades",
        placeholder="All Salary Grades",
    )

filtered_personnel = filter_personnel_for_export(
    all_personnel,
    search=personnel_search,
    sub_department=selected_departments,
    sub_unit=selected_units,
    salary_grades=selected_grades,
).reset_index(drop=True)

st.caption(
    f"**{len(filtered_personnel):,} matching personnel** out of "
    f"{len(all_personnel):,} available records."
)

# -----------------------------------------------------------------------------
# 02 · SELECT PERSONNEL
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("02 · Select personnel")
st.caption(
    "Tick the first column to add people to the export. Your selection is retained "
    "when you change filters."
)

visible_keys = filtered_personnel["__selection_key"].astype(str).tolist()
editor_action_col, bulk_action_col = st.columns([3.4, 1.6])
with bulk_action_col:
    st.write("")
    st.write("")
    action_left, action_right = st.columns(2)
    with action_left:
        if st.button(
            "Select all",
            key="report_export_select_all_visible",
            disabled=not visible_keys,
            use_container_width=True,
        ):
            st.session_state[SELECTION_STATE_KEY] = set_visible_selection(
                st.session_state[SELECTION_STATE_KEY], visible_keys, selected=True
            )
            st.session_state[SELECTION_VERSION_KEY] += 1
            st.rerun()
    with action_right:
        if st.button(
            "Clear visible",
            key="report_export_clear_visible",
            disabled=not visible_keys,
            use_container_width=True,
        ):
            st.session_state[SELECTION_STATE_KEY] = set_visible_selection(
                st.session_state[SELECTION_STATE_KEY], visible_keys, selected=False
            )
            st.session_state[SELECTION_VERSION_KEY] += 1
            st.rerun()

selected_keys = set(st.session_state[SELECTION_STATE_KEY])
selection_view = pd.DataFrame({
    "Select": [key in selected_keys for key in visible_keys],
    "Name": filtered_personnel.get("Name", pd.Series("", index=filtered_personnel.index)).fillna(""),
    "Staff ID": filtered_personnel.get("Staff ID", pd.Series("", index=filtered_personnel.index)).fillna(""),
    "Department": filtered_personnel.get("Department", pd.Series("", index=filtered_personnel.index)).fillna(""),
    "Sub-Department": filtered_personnel[sub_department_column].fillna(""),
    "Sub-Unit": filtered_personnel[sub_unit_column].fillna(""),
    "SG": filtered_personnel.get("SG", pd.Series("", index=filtered_personnel.index)).fillna(""),
})

visible_signature = hashlib.sha1("\n".join(visible_keys).encode("utf-8")).hexdigest()[:12]
editor_key = (
    f"report_export_personnel_editor_{visible_signature}_"
    f"{st.session_state[SELECTION_VERSION_KEY]}"
)
edited_selection = st.data_editor(
    selection_view,
    key=editor_key,
    hide_index=True,
    use_container_width=True,
    height=460,
    num_rows="fixed",
    disabled=["Name", "Staff ID", "Department", "Sub-Department", "Sub-Unit", "SG"],
    column_config={
        "Select": st.column_config.CheckboxColumn(
            "Select",
            help="Select this person for the export.",
            default=False,
        ),
        "Name": st.column_config.TextColumn("Personnel"),
        "Staff ID": st.column_config.TextColumn("Staff ID"),
        "Department": st.column_config.TextColumn("Department"),
        "Sub-Department": st.column_config.TextColumn("Sub-Department"),
        "Sub-Unit": st.column_config.TextColumn("Sub-Unit"),
        "SG": st.column_config.TextColumn("SG"),
    },
)

selected_before_edit = list(st.session_state[SELECTION_STATE_KEY])
selected_after_edit = merge_visible_selection(
    selected_before_edit,
    visible_keys,
    edited_selection["Select"].fillna(False).astype(bool).tolist(),
)
if selected_after_edit != selected_before_edit:
    st.session_state[SELECTION_STATE_KEY] = selected_after_edit
    # Remount the editor with the canonical selected-key set. This prevents a
    # cached editor state from reviving an older selection after filter changes.
    st.session_state[SELECTION_VERSION_KEY] += 1
    st.rerun()

selected_keys = set(st.session_state[SELECTION_STATE_KEY])
selected_personnel = all_personnel[
    all_personnel["__selection_key"].isin(selected_keys)
].copy()

# -----------------------------------------------------------------------------
# 03 · SELECTION BASKET
# -----------------------------------------------------------------------------
st.markdown("---")
summary_col, clear_selection_col = st.columns([3, 1])
with summary_col:
    st.subheader("03 · Export selection")
    st.metric("Selected personnel", len(selected_personnel))
with clear_selection_col:
    st.write("")
    if st.button(
        "Clear all selected",
        key="report_export_clear_all_selection",
        disabled=selected_personnel.empty,
        use_container_width=True,
    ):
        st.session_state[SELECTION_STATE_KEY] = []
        st.session_state[SELECTION_VERSION_KEY] += 1
        st.rerun()

if not selected_personnel.empty:
    selected_preview_columns = [
        column for column in [
            "Name", "Staff ID", "Department", sub_department_column,
            sub_unit_column, "SG",
        ]
        if column in selected_personnel.columns
    ]
    selected_preview = selected_personnel[selected_preview_columns].rename(
        columns={
            sub_department_column: "Sub-Department",
            sub_unit_column: "Sub-Unit",
        }
    )
    with st.expander(f"Review selected personnel ({len(selected_personnel)})", expanded=False):
        st.dataframe(
            selected_preview,
            use_container_width=True,
            hide_index=True,
            height=min(360, 38 + 35 * len(selected_preview)),
        )

        selected_labels: list[str] = []
        selected_label_to_key: dict[str, str] = {}
        for _, row in selected_personnel.iterrows():
            name_value = row.get("Name")
            staff_value = row.get("Staff ID")
            name = "Unknown" if pd.isna(name_value) else str(name_value).strip()
            staff_id = "" if pd.isna(staff_value) else str(staff_value).strip()
            label = f"{name or 'Unknown'} · {staff_id or 'No Staff ID'}"
            if label in selected_label_to_key:
                label = f"{label} · {len(selected_labels) + 1}"
            selected_labels.append(label)
            selected_label_to_key[label] = str(row["__selection_key"])

        remove_labels = st.multiselect(
            "Remove individual people from this export",
            options=selected_labels,
            key=f"report_export_remove_people_{hashlib.sha1('|'.join(selected_labels).encode('utf-8')).hexdigest()[:10]}",
            placeholder="Choose people to remove",
        )
        if st.button(
            "Remove selected people",
            key="report_export_remove_people_action",
            disabled=not remove_labels,
        ):
            removed_keys = {selected_label_to_key[label] for label in remove_labels}
            st.session_state[SELECTION_STATE_KEY] = sorted(
                set(st.session_state[SELECTION_STATE_KEY]) - removed_keys
            )
            st.session_state[SELECTION_VERSION_KEY] += 1
            st.rerun()
else:
    st.info("No personnel selected yet. Select individual rows above or use Select all.")

# -----------------------------------------------------------------------------
# 04 · EXPORT WORKBOOK
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("04 · Export Excel report")
st.caption(
    "One workbook will contain the original Personnel Master layout plus separate "
    "competency, assessment and export-metadata worksheets. Retained selections are "
    "included even when they are outside the current filter results."
)

if selected_personnel.empty:
    st.info("Select at least one person to enable the Excel export.")
else:
    try:
        maximum_scores = get_configured_competency_max_scores()
    except (TypeError, ValueError) as exc:
        st.error(f"Invalid competency maximum-score configuration: {exc}")
        st.stop()

    if len(maximum_scores) < len(SCORE_COLS):
        st.info(
            "Some competency maximum scores are not configured from an approved rubric. "
            "Those Maximum Score cells will remain blank; career-ruler targets will not "
            "be treated as maximum attainable scores."
        )

    export_filters = {
        "search": personnel_search,
        "sub_department": selected_departments,
        "sub_unit": selected_units,
        "salary_grades": selected_grades,
    }

    export_personnel = selected_personnel.drop(columns=["__selection_key"], errors="ignore")
    try:
        workbook_bytes = build_competency_report_workbook(
            source_workbook_path=EXCEL_PATH,
            personnel=export_personnel,
            filters=export_filters,
            competency_names=dict(COMPETENCY_FULLNAMES),
            maximum_scores=maximum_scores,
        )
    except Exception as exc:
        st.error(f"Unable to generate the competency report: {exc}")
    else:
        filename_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_col, note_col = st.columns([1.35, 2.65])
        with export_col:
            st.download_button(
                "⬇️ Download Excel report (.xlsx)",
                data=workbook_bytes,
                file_name=f"competency_reports_{filename_timestamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )
        with note_col:
            st.caption(
                f"Ready to export **{len(export_personnel):,} personnel** across four worksheets."
            )
