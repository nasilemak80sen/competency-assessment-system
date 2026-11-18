"""Admin import workspace with validation, reconciliation and dry-run gating."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from components.navigation import render_navigation, render_header
from core.bootstrap import open_session
from core.auth import current_user
from data_loader import load_master_data, load_ruler_and_tech_mapping, load_cv_list
from services.import_service import (
    build_personnel_import_preview,
    build_cv_import_preview,
    resolve_personnel_import,
    resolve_cv_import,
    bulk_import_from_dataframe,
    bulk_import_cv_list,
)
from services.auth_service import record_admin_action

render_navigation()
render_header(
    "⚙️ Admin: Import & Reconciliation",
    "Validate workbook data, compare it with the database, resolve duplicates and CV matches, then commit a reviewed import.",
)


def _show_last_report():
    report = st.session_state.get("_last_import_report")
    if not report:
        return
    st.subheader("Latest import report")
    st.caption(
        f"Source: {report['filename']} · Completed: {report['completed_at']} · "
        f"Workbook fingerprint: {report['fingerprint']}"
    )
    p = report["personnel"]
    c = report["cv"]
    metric_cols = st.columns(4)
    metric_cols[0].metric("Personnel added", p.get("added", 0))
    metric_cols[1].metric("Personnel updated", p.get("updated", 0))
    metric_cols[2].metric("CV records added", c.get("added", 0))
    metric_cols[3].metric("CV records updated", c.get("updated", 0))
    st.write(
        f"Personnel import errors: **{p.get('errors', 0)}** · "
        f"Personnel source rows skipped: **{report.get('personnel_rows_skipped', 0)}** · "
        f"CV unmatched / skipped: **{c.get('unmatched', 0)} / {c.get('skipped', 0)}** · "
        f"CV unresolved before import: **{report.get('cv_unresolved', 0)}** · "
        f"CV errors: **{c.get('errors', 0)}**"
    )
    if report.get("audit_ok"):
        st.success("Administrator activity was recorded in the access audit log.")
    else:
        st.warning(
            "The import result was saved, but the administrator audit event was not recorded: "
            + str(report.get("audit_message") or "Unknown audit error")
        )
    if report.get("field_differences"):
        with st.expander("Field-level comparison used for this import"):
            st.dataframe(
                pd.DataFrame(report["field_differences"]),
                width="stretch",
                hide_index=True,
            )
    if report.get("selected_rows") is not None:
        st.caption(
            f"Personnel source rows selected: {report['selected_rows']} · "
            f"CV rows matched for import: {report.get('cv_rows_selected', 0)}"
        )


uploaded_file = st.file_uploader(
    "Upload the RE Fraternity master workbook",
    type=["xlsx", "xlsm"],
    key="master_workbook_upload_phase34",
)
if uploaded_file is None:
    st.info("Upload the master workbook to begin the read-only validation and reconciliation preview.")
    _show_last_report()
    st.stop()

file_bytes = uploaded_file.getvalue()
file_signature = hashlib.sha256(file_bytes).hexdigest()
temporary_path = None
try:
    suffix = Path(uploaded_file.name).suffix or ".xlsx"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temporary_file:
        temporary_file.write(file_bytes)
        temporary_path = temporary_file.name

    with st.spinner("Reading workbook sheets and preparing a read-only database comparison…"):
        raw_df = load_master_data(temporary_path)
        ruler_map, tech_labels = load_ruler_and_tech_mapping(temporary_path)
        cv_df = load_cv_list(temporary_path, verbose=False)

    st.success(
        f"Workbook loaded: {len(raw_df):,} personnel rows, "
        f"{len(cv_df):,} CV/document rows."
    )

    preview_session = open_session()
    try:
        personnel_preview = build_personnel_import_preview(preview_session, raw_df)
        cv_preview = build_cv_import_preview(preview_session, cv_df)
    finally:
        preview_session.close()

    counts = personnel_preview["counts"]
    metrics = st.columns(5)
    metrics[0].metric("Workbook rows", counts["source_rows"])
    metrics[1].metric("New", counts["new_records"])
    metrics[2].metric("Matched", counts["matched_records"])
    metrics[3].metric("Duplicate IDs", counts["duplicate_rows"])
    metrics[4].metric("Validation issues", counts["invalid_rows"] + counts["ambiguous_rows"])

    if personnel_preview["missing_columns"]:
        st.error(
            "The workbook is missing required columns: "
            + ", ".join(personnel_preview["missing_columns"])
            + ". This file cannot be imported until its schema is corrected."
        )

    personnel_tab, comparison_tab, cv_tab = st.tabs(
        ["👥 Personnel Reconciliation", "🔎 Field Comparison", "📄 CV Matching"]
    )

    with personnel_tab:
        st.subheader("Personnel row decisions")
        st.caption(
            "Review each row before import. Duplicate source Staff IDs are excluded by default. "
            "For an ambiguous name match, choose Update and enter the exact existing Staff ID, "
            "or choose Add only when it is genuinely a different person."
        )
        edited_plan = st.data_editor(
            personnel_preview["plan"],
            key=f"personnel_import_plan_{file_signature[:12]}",
            width="stretch",
            hide_index=True,
            num_rows="fixed",
            disabled=[
                "Source index", "Source row", "Name", "Staff ID", "Outcome",
                "Match method", "Changed fields", "Changed field names", "Issues",
            ],
            column_config={
                "Include": st.column_config.CheckboxColumn(
                    "Include", help="Include this source row in the import."
                ),
                "Action": st.column_config.SelectboxColumn(
                    "Action", options=["Add", "Update", "Skip"], required=True
                ),
                "Match Staff ID": st.column_config.TextColumn(
                    "Match Staff ID",
                    help="For Update, use the active database Staff ID to reconcile this source row.",
                ),
            },
        )
        if counts["duplicate_rows"]:
            st.warning(
                "Duplicate Staff IDs were found within the workbook. Select at most one row "
                "for each duplicate ID. The dry-run will reject multiple selected copies."
            )
        if counts["ambiguous_rows"]:
            st.warning(
                "Some names have multiple database matches. These rows remain excluded until "
                "you explicitly choose an active database Staff ID and set Action to Update."
            )

    with comparison_tab:
        st.subheader("Field-level comparison")
        differences = personnel_preview["field_differences"]
        if differences.empty:
            st.info(
                "No field-level differences were detected for automatically matched personnel. "
                "New rows and ambiguous matches do not appear in this comparison."
            )
        else:
            st.caption(
                f"{len(differences):,} changed field values across matched personnel records. "
                "The workbook value will replace the current database value when that row is imported."
            )
            st.dataframe(
                differences,
                width="stretch",
                hide_index=True,
                height=520,
            )

    manual_cv_resolutions = {}
    with cv_tab:
        st.subheader("CV and document matching")
        cv_all = cv_preview["preview"]
        if cv_all.empty:
            st.info("No CV/document rows were detected.")
        else:
            matched_count = len(cv_preview["auto_matches"])
            unmatched_count = len(cv_preview["unmatched"])
            c1, c2, c3 = st.columns(3)
            c1.metric("CV rows", len(cv_all))
            c2.metric("Automatically matched", matched_count)
            c3.metric("Needs resolution", unmatched_count)
            st.dataframe(cv_all, width="stretch", hide_index=True, height=320)

            if unmatched_count:
                st.warning(
                    "Unmatched or ambiguous CV rows are never attached automatically. "
                    "Resolve each row to an active personnel record or leave it as Skip."
                )
                personnel_choices = {
                    item["label"]: item["staff_id"]
                    for item in cv_preview["active_people"]
                }
                for _, row in cv_preview["unmatched"].iterrows():
                    source_index = int(row["Source index"])
                    label = (
                        f"CV row {int(row['Source row'])}: "
                        f"{row['Name']} · {row['CV file']}"
                    )
                    choice = st.selectbox(
                        label,
                        ["Skip this CV", *sorted(personnel_choices)],
                        key=f"cv_resolution_{file_signature[:12]}_{source_index}",
                        help=f"Source Staff ID: {row['Source Staff ID']}. "
                             f"Candidate matches: {row['Candidate matches']}",
                    )
                    if choice != "Skip this CV":
                        manual_cv_resolutions[source_index] = personnel_choices[choice]

    personnel_import_df, personnel_errors, personnel_decisions = resolve_personnel_import(
        raw_df,
        edited_plan,
        active_people=personnel_preview["active_people"],
        all_staff_ids=personnel_preview["all_staff_ids"],
    )
    cv_import_df, cv_errors, cv_summary = resolve_cv_import(
        cv_df,
        cv_preview,
        manual_cv_resolutions,
    )

    decision_payload = {
        "personnel": edited_plan[
            ["Source index", "Include", "Action", "Match Staff ID"]
        ].to_dict(orient="records") if not edited_plan.empty else [],
        "cv": sorted(
            (int(index), str(staff_id))
            for index, staff_id in manual_cv_resolutions.items()
        ),
    }
    decision_token = hashlib.sha256(
        json.dumps(decision_payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()
    dry_run_key = f"{file_signature}:{decision_token}"

    st.divider()
    st.subheader("Dry-run validation")
    st.caption(
        "Dry run performs no database writes. It revalidates row decisions and reports the exact "
        "personnel and CV rows that would be submitted to the existing import routines."
    )

    hard_errors = list(personnel_errors) + list(cv_errors)
    if personnel_preview["missing_columns"]:
        hard_errors.append(
            "Required workbook columns are missing: "
            + ", ".join(personnel_preview["missing_columns"])
        )

    if hard_errors:
        for error in hard_errors:
            st.error(error)
    else:
        dry_cols = st.columns(4)
        update_count = sum(
            1 for decision in personnel_decisions.values()
            if decision["action"] == "update"
        )
        add_count = sum(
            1 for decision in personnel_decisions.values()
            if decision["action"] == "add"
        )
        dry_cols[0].metric("Rows to add", add_count)
        dry_cols[1].metric("Rows to update", update_count)
        dry_cols[2].metric("CV rows to attach", len(cv_import_df))
        dry_cols[3].metric(
            "CV rows to skip",
            max(len(cv_df) - len(cv_import_df), 0),
        )
        st.write(
            f"Selected personnel rows: **{len(personnel_import_df)}** · "
            f"Field-level changes: **{len(personnel_preview['field_differences'])}** · "
            f"Ruler mappings available: **{len(ruler_map or {})}**"
        )

    dry_run_clicked = st.button(
        "🧪 Run Dry Run",
        type="secondary",
        disabled=bool(hard_errors),
        key=f"run_import_dry_run_{file_signature[:12]}",
        use_container_width=True,
    )
    if dry_run_clicked:
        st.session_state["_import_dry_run_key"] = dry_run_key
        st.session_state["_import_dry_run_summary"] = {
            "personnel_rows": len(personnel_import_df),
            "personnel_add": add_count,
            "personnel_update": update_count,
            "cv_rows": len(cv_import_df),
            "cv_skipped": max(len(cv_df) - len(cv_import_df), 0),
        }
        st.success("Dry run passed. No database records have been changed.")

    dry_run_passed = (
        st.session_state.get("_import_dry_run_key") == dry_run_key
        and not hard_errors
    )
    if dry_run_passed:
        st.success(
            "The current workbook and row decisions match the validated dry run. "
            "The commit button is enabled."
        )
    else:
        st.info(
            "Run the dry run after making your final row and CV-link decisions. "
            "Any change to the workbook or reconciliation choices invalidates the previous dry run."
        )

    st.warning(
        "Import execution uses the established database import routines. Personnel rows may be "
        "committed incrementally by that legacy routine, so this import is not an all-or-nothing "
        "database transaction. Review the detailed result report after committing."
    )
    commit_clicked = st.button(
        "✅ Commit Reviewed Import",
        type="primary",
        disabled=not dry_run_passed,
        key=f"commit_import_{file_signature[:12]}",
        use_container_width=True,
    )
    if commit_clicked:
        import_session = open_session()
        personnel_result = {"added": 0, "updated": 0, "errors": 0}
        cv_result = {"added": 0, "updated": 0, "unmatched": 0, "skipped": 0, "errors": 0}
        try:
            with st.spinner("Applying the reviewed personnel, assessment, ruler and CV imports…"):
                personnel_result = bulk_import_from_dataframe(
                    import_session,
                    personnel_import_df,
                    ruler_map=ruler_map,
                )
                cv_result = bulk_import_cv_list(import_session, cv_import_df)
            st.cache_data.clear()
            audit_ok, audit_message = record_admin_action(
                current_user(),
                "DATA_IMPORT_COMPLETED_WITH_ERRORS"
                if int(personnel_result.get("errors", 0)) or int(cv_result.get("errors", 0))
                else "DATA_IMPORT_COMPLETED",
                target_username=None,
                details={
                    "filename": uploaded_file.name,
                    "workbook_fingerprint": file_signature[:12],
                    "personnel_rows_selected": len(personnel_import_df),
                    "cv_rows_selected": len(cv_import_df),
                    "personnel_result": personnel_result,
                    "cv_result": cv_result,
                },
            )
            st.session_state["_last_import_report"] = {
                "filename": uploaded_file.name,
                "completed_at": pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                "fingerprint": file_signature[:12],
                "personnel": personnel_result,
                "cv": cv_result,
                "field_differences": differences.to_dict(orient="records"),
                "selected_rows": len(personnel_import_df),
                "cv_rows_selected": len(cv_import_df),
                "cv_unresolved": max(len(cv_preview["unmatched"]) - len(manual_cv_resolutions), 0),
                "personnel_rows_skipped": max(len(raw_df) - len(personnel_import_df), 0),
                "audit_ok": audit_ok,
                "audit_message": audit_message,
            }
            st.session_state.pop("_import_dry_run_key", None)
            st.success("Import processing completed. Review the result report below.")
            if not audit_ok:
                st.error(f"Import completed, but its administrator audit event could not be recorded: {audit_message}")
        except Exception as exc:
            import_session.rollback()
            st.error(
                "Import execution stopped with an error. Earlier personnel rows may already "
                f"have been committed by the existing importer. Details: {exc}"
            )
        finally:
            import_session.close()

    _show_last_report()

finally:
    if temporary_path and os.path.exists(temporary_path):
        try:
            os.remove(temporary_path)
        except OSError:
            pass
