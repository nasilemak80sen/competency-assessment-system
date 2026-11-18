"""Validated import and reconciliation service for the v2 admin workflow.

The existing db_ops importers remain the write engine. This service adds a
read-only planning layer, explicit row decisions, and CV/personnel resolution
before those existing import operations are called.
"""
from __future__ import annotations

from datetime import date, datetime
import math
import re
from typing import Any

import pandas as pd

import db_ops
from models import Personnel

PERSONNEL_FIELD_MAP = {
    "Name": "name",
    "Staff ID": "staff_id",
    "Email Address": "email",
    "Gender": "gender",
    "Age": "age",
    "Birth Year": "birth_year",
    "Nationality": "nationality",
    "Employment Category": "employment_category",
    "Department": "department",
    "Section Name": "section_name",
    "Unit Name": "unit_name",
    "Sub Unit": "sub_unit",
    "Staff Position": "staff_position",
    "SG": "sg",
    "Joining Date": "joining_date",
    "Contract Expire Date": "contract_expire_date",
    "Years in PET": "years_in_pet",
    "Years of RE Experience": "years_re_experience",
    "Years in Salary Grade": "sg_years",
    "Date of Appointment to Current Grade": "sg_start_date",
    "Age Promoted to Staff or Principal": "age_promoted",
    "Current Location:": "current_assignment",
    "Date in Position": "assignment_date",
    "Length in Current Assignment": "assignment_length",
    "Chat Status": "chat_status",
    "Chat Date": "chat_date",
    "Assessment Level": "assessment_level",
    "Last Assesment Date": "last_assessment_date",
    "Sub-Disciplines": "sub_disciplines",
    "Potential": "potential",
    "Strength": "strength",
    "Recommendation": "recommendation",
    "Resource/SME": "resource_sme",
    "Interest": "interest",
    "Preference": "preference",
    "Comment/Suggestion": "comment",
    "Assesor1": "assessor1",
    "Assessor2": "assessor2",
    "Supervisor": "supervisor",
    "Remarks": "remarks",
}

REQUIRED_PERSONNEL_COLUMNS = ("Name", "Staff ID")


def normalize_staff_id(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    cleaned = str(value).strip()
    if cleaned.casefold() in {"", "nan", "none", "null"}:
        return ""
    return re.sub(r"\.0$", "", cleaned).casefold()


def _normalise_name(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    value = str(value).strip().casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _empty(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _comparison_value(value: Any, field: str):
    if _empty(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(value).date().isoformat()
    if field in {
        "age", "birth_year", "years_in_pet", "years_re_experience",
        "sg_years", "age_promoted", "assignment_length",
    }:
        numeric = pd.to_numeric(value, errors="coerce")
        return None if pd.isna(numeric) else round(float(numeric), 4)
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "nat", "none"}:
        return None
    parsed = pd.to_datetime(value, errors="coerce") if field.endswith("_date") else pd.NaT
    if pd.notna(parsed):
        return parsed.date().isoformat()
    return text.casefold()


def _display_value(value: Any) -> str:
    if _empty(value):
        return "—"
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(value).strftime("%d %b %Y")
    return str(value).strip()


def build_personnel_import_preview(session, raw_df: pd.DataFrame) -> dict:
    """Build a dry-run plan and field-level diff without writing to the database."""
    if raw_df is None:
        raw_df = pd.DataFrame()
    raw_df = raw_df.copy()
    missing_columns = [
        column for column in REQUIRED_PERSONNEL_COLUMNS
        if column not in raw_df.columns
    ]

    people = (
        session.query(Personnel)
        .order_by(Personnel.name.asc(), Personnel.staff_id.asc())
        .all()
    )
    active_by_id: dict[str, list[Personnel]] = {}
    all_by_id: dict[str, list[Personnel]] = {}
    active_by_name: dict[str, list[Personnel]] = {}
    for person in people:
        sid = normalize_staff_id(person.staff_id)
        if sid:
            all_by_id.setdefault(sid, []).append(person)
            if not bool(person.is_deleted):
                active_by_id.setdefault(sid, []).append(person)
        name = _normalise_name(person.name)
        if name and not bool(person.is_deleted):
            active_by_name.setdefault(name, []).append(person)

    source_id_counts: dict[str, int] = {}
    source_id_name_counts: dict[tuple[str, str], int] = {}
    if "Staff ID" in raw_df.columns:
        for _, source_row in raw_df.iterrows():
            sid = normalize_staff_id(source_row.get("Staff ID"))
            name_key = _normalise_name(source_row.get("Name"))
            if sid:
                source_id_counts[sid] = source_id_counts.get(sid, 0) + 1
                pair = (sid, name_key)
                source_id_name_counts[pair] = source_id_name_counts.get(pair, 0) + 1

    plan_rows = []
    diff_rows = []
    for source_index, (_, source) in enumerate(raw_df.iterrows()):
        name = "" if _empty(source.get("Name")) else str(source.get("Name")).strip()
        staff_id = normalize_staff_id(source.get("Staff ID"))
        issues = []
        if missing_columns:
            issues.append("Missing required column(s): " + ", ".join(missing_columns))
        if not name:
            issues.append("Name is blank")
        if not staff_id:
            issues.append("Staff ID is blank")
        # UPTREX is an established shared placeholder in the source workbook.
        # Different names are separate people; only repeated same-name UPTREX
        # rows are duplicate source records.
        duplicate_source = bool(
            staff_id
            and (
                (staff_id != "uptrex" and source_id_counts.get(staff_id, 0) > 1)
                or (
                    staff_id == "uptrex"
                    and source_id_name_counts.get((staff_id, _normalise_name(name)), 0) > 1
                )
            )
        )
        if duplicate_source:
            issues.append("Duplicate Staff ID within uploaded workbook")

        id_matches = all_by_id.get(staff_id, []) if staff_id else []
        archived_matches = [person for person in id_matches if bool(person.is_deleted)]
        active_matches = [person for person in id_matches if not bool(person.is_deleted)]
        matched_person = None
        outcome = "Add new personnel"
        match_method = "No database match"
        match_staff_id = ""
        changed_fields = []
        if len(id_matches) > 1:
            outcome = "Ambiguous database ID"
            match_method = "Multiple normalized Staff ID matches"
            issues.append("More than one database record has this normalized Staff ID")
        elif archived_matches:
            outcome = "Archived database match"
            match_method = "Archived Staff ID match"
            issues.append("Matching database record is archived; restore it before importing")
        elif len(active_matches) == 1:
            candidate = active_matches[0]
            if staff_id == "uptrex" and _normalise_name(candidate.name) != _normalise_name(name):
                outcome = "Shared UPTREX placeholder; add separate personnel"
                match_method = "Legacy shared placeholder"
            else:
                matched_person = candidate
                match_staff_id = matched_person.staff_id
                outcome = "Update existing personnel"
                match_method = "Staff ID"
        elif not active_matches and name:
            name_matches = active_by_name.get(_normalise_name(name), [])
            if len(name_matches) == 1:
                matched_person = name_matches[0]
                match_staff_id = matched_person.staff_id
                outcome = "Potential update by name"
                match_method = "Unique exact name"
            elif len(name_matches) > 1:
                outcome = "Ambiguous name match"
                match_method = "Multiple exact name matches"
                issues.append(
                    "Name matches multiple personnel records; choose a Staff ID to reconcile"
                )

        if matched_person is not None:
            for source_column, db_field in PERSONNEL_FIELD_MAP.items():
                if source_column not in raw_df.columns:
                    continue
                incoming = source.get(source_column)
                existing = getattr(matched_person, db_field, None)
                if _comparison_value(incoming, db_field) != _comparison_value(existing, db_field):
                    changed_fields.append(source_column)
                    diff_rows.append(
                        {
                            "Source row": source_index + 1,
                            "Staff ID": staff_id,
                            "Name": name,
                            "Field": source_column,
                            "Database value": _display_value(existing),
                            "Workbook value": _display_value(incoming),
                        }
                    )

        invalid = bool(missing_columns or not name or not staff_id)
        blocked = invalid or duplicate_source or bool(archived_matches) or len(id_matches) > 1
        action_blocked = invalid or bool(archived_matches) or len(id_matches) > 1
        action = "Skip" if action_blocked or outcome == "Ambiguous name match" else (
            "Update" if matched_person is not None else "Add"
        )
        include = not blocked and outcome != "Ambiguous name match"
        plan_rows.append(
            {
                "Source index": source_index,
                "Source row": source_index + 1,
                "Include": include,
                "Action": action,
                "Name": name or "—",
                "Staff ID": str(source.get("Staff ID", "") or ""),
                "Outcome": outcome,
                "Match method": match_method,
                "Match Staff ID": match_staff_id,
                "Changed fields": len(changed_fields),
                "Changed field names": ", ".join(changed_fields) or "—",
                "Issues": "; ".join(issues) or "—",
            }
        )

    plan_df = pd.DataFrame(
        plan_rows,
        columns=[
            "Source index", "Source row", "Include", "Action", "Name",
            "Staff ID", "Outcome", "Match method", "Match Staff ID",
            "Changed fields", "Changed field names", "Issues",
        ],
    )
    diff_df = pd.DataFrame(
        diff_rows,
        columns=[
            "Source row", "Staff ID", "Name", "Field",
            "Database value", "Workbook value",
        ],
    )
    counts = {
        "source_rows": len(raw_df),
        "new_records": int((plan_df["Outcome"] == "Add new personnel").sum()) if not plan_df.empty else 0,
        "matched_records": int(plan_df["Outcome"].isin(
            ["Update existing personnel", "Potential update by name"]
        ).sum()) if not plan_df.empty else 0,
        "duplicate_rows": int(plan_df["Issues"].str.contains("Duplicate Staff ID", regex=False).sum()) if not plan_df.empty else 0,
        "invalid_rows": int(plan_df["Issues"].str.contains("blank|Missing required", case=False, regex=True).sum()) if not plan_df.empty else 0,
        "ambiguous_rows": int(plan_df["Outcome"].isin(
            ["Ambiguous database ID", "Ambiguous name match"]
        ).sum()) if not plan_df.empty else 0,
        "changed_fields": len(diff_df),
    }
    return {
        "plan": plan_df,
        "field_differences": diff_df,
        "missing_columns": missing_columns,
        "counts": counts,
        "all_staff_ids": [
            normalize_staff_id(person.staff_id)
            for person in people if normalize_staff_id(person.staff_id)
        ],
        "active_people": [
            {
                "id": int(person.id),
                "staff_id": person.staff_id,
                "name": person.name,
                "label": f"{person.name} · {person.staff_id}",
            }
            for person in people if not bool(person.is_deleted)
        ],
    }


def resolve_personnel_import(
    raw_df: pd.DataFrame,
    edited_plan: pd.DataFrame,
    *,
    active_people: list[dict],
    all_staff_ids: list[str] | None = None,
) -> tuple[pd.DataFrame, list[str], dict]:
    """Validate row decisions and return a filtered import dataframe."""
    errors = []
    by_id: dict[str, list[dict]] = {}
    for person in active_people:
        sid = normalize_staff_id(person.get("staff_id"))
        if sid:
            by_id.setdefault(sid, []).append(person)
    reserved_ids = set(all_staff_ids or by_id.keys())
    selected = edited_plan[
        edited_plan["Include"].fillna(False).astype(bool)
        & edited_plan["Action"].astype(str).str.strip().ne("Skip")
    ].copy()

    selected_keys = selected.apply(
        lambda row: (
            normalize_staff_id(row.get("Staff ID")),
            _normalise_name(row.get("Name"))
            if normalize_staff_id(row.get("Staff ID")) == "uptrex"
            else "",
        ),
        axis=1,
    )
    selected_counts = selected_keys.value_counts()
    duplicated_selected = [
        f"{sid} ({name})" if name else sid
        for (sid, name), count in selected_counts.items()
        if sid and count > 1
    ]
    if duplicated_selected:
        errors.append(
            "Select only one source row for each duplicated Staff ID: "
            + ", ".join(duplicated_selected)
        )
    update_targets = (
        selected[selected["Action"].astype(str).str.strip().eq("Update")]
        ["Match Staff ID"].map(normalize_staff_id).value_counts()
    )
    repeated_targets = [
        staff_id for staff_id, count in update_targets.items()
        if staff_id and count > 1
    ]
    if repeated_targets:
        errors.append(
            "Multiple source rows cannot update the same database personnel record: "
            + ", ".join(repeated_targets)
        )

    result_rows = []
    result_indices = []
    decisions = {}
    for _, decision in selected.iterrows():
        source_index = int(decision["Source index"])
        if source_index < 0 or source_index >= len(raw_df):
            errors.append(f"Invalid source row reference: {source_index + 1}.")
            continue
        action = str(decision["Action"]).strip()
        source = raw_df.iloc[source_index].copy()
        source_id = normalize_staff_id(source.get("Staff ID"))
        match_id = normalize_staff_id(decision.get("Match Staff ID"))
        if action == "Update":
            candidates = by_id.get(match_id, [])
            if len(candidates) != 1:
                errors.append(
                    f"Source row {source_index + 1}: select one unambiguous active database Staff ID to update."
                )
                continue
            match = candidates[0]
            matched_staff_id = normalize_staff_id(match["staff_id"])
            if source_id and source_id != matched_staff_id and source_id in reserved_ids:
                errors.append(
                    f"Source row {source_index + 1}: the workbook Staff ID '{source_id}' "
                    "is already assigned to another active or archived database record."
                )
                continue
            # Carry the database primary key through the approved plan. This
            # lets the existing writer update a matched person even when the
            # workbook contains a legitimate new Staff ID.
            source["__matched_personnel_id"] = int(match["id"])
            if source_id:
                source["Staff ID"] = re.sub(
                    r"\.0$", "", str(source.get("Staff ID", "")).strip()
                )
            else:
                source["Staff ID"] = match["staff_id"]
            decisions[source_index] = {
                "action": "update",
                "matched_staff_id": match["staff_id"],
                "matched_personnel_id": int(match["id"]),
                "source_staff_id": source_id or match["staff_id"],
            }
        elif action == "Add":
            if source_id in reserved_ids and source_id != "uptrex":
                errors.append(
                    f"Source row {source_index + 1}: Staff ID is already reserved by an active or archived database record. Choose Update or Skip."
                )
                continue
            if not source_id:
                errors.append(f"Source row {source_index + 1}: Staff ID is required.")
                continue
            source["Staff ID"] = re.sub(
                r"\.0$", "", str(source.get("Staff ID", "")).strip()
            )
            decisions[source_index] = {"action": "add", "matched_staff_id": None}
        else:
            errors.append(f"Source row {source_index + 1}: unsupported action '{action}'.")
            continue
        if not str(source.get("Name", "")).strip():
            errors.append(f"Source row {source_index + 1}: Name is required.")
            continue
        result_rows.append(source)
        result_indices.append(raw_df.index[source_index])

    result_df = (
        pd.DataFrame(result_rows, index=result_indices)
        if result_rows else raw_df.iloc[0:0].copy()
    )
    return result_df, errors, decisions


def build_cv_import_preview(session, cv_df: pd.DataFrame) -> dict:
    """Match CV rows conservatively; ambiguous or unmatched rows require review."""
    people = (
        session.query(Personnel)
        .filter(Personnel.is_deleted.is_(False))
        .order_by(Personnel.name.asc(), Personnel.staff_id.asc())
        .all()
    )
    by_id: dict[str, list[Personnel]] = {}
    by_name: dict[str, list[Personnel]] = {}
    for person in people:
        sid = normalize_staff_id(person.staff_id)
        if sid:
            by_id.setdefault(sid, []).append(person)
        name = _normalise_name(person.name)
        if name:
            by_name.setdefault(name, []).append(person)

    rows = []
    for source_index, (_, source) in enumerate((cv_df if cv_df is not None else pd.DataFrame()).iterrows()):
        name = "" if _empty(source.get("Name")) else str(source.get("Name")).strip()
        staff_id = normalize_staff_id(source.get("Staff ID"))
        file_name = "" if _empty(source.get("CV File Name")) else str(source.get("CV File Name")).strip()
        candidates = []
        selected_person = None
        method = "Unmatched"
        issues = []
        if not file_name:
            method = "Missing CV file name"
            issues.append("CV file name is required")
        elif staff_id and len(by_id.get(staff_id, [])) == 1:
            selected_person = by_id[staff_id][0]
            method = "Staff ID"
        elif not staff_id and name and len(by_name.get(_normalise_name(name), [])) == 1:
            selected_person = by_name[_normalise_name(name)][0]
            method = "Unique exact name"
        else:
            if staff_id and staff_id in by_id:
                candidates.extend(by_id[staff_id])
            if name:
                candidates.extend(by_name.get(_normalise_name(name), []))
            # A partial name is a suggestion only, never an automatic match.
            if name and not candidates:
                key = _normalise_name(name)
                candidates.extend([
                    person for person in people
                    if key and (
                        key in _normalise_name(person.name)
                        or _normalise_name(person.name) in key
                    )
                ])
            unique = {int(person.id): person for person in candidates}
            candidates = list(unique.values())
            if len(candidates) > 1:
                method = "Ambiguous; administrator resolution required"
            else:
                method = "Unmatched; administrator resolution required"

        rows.append(
            {
                "Source index": source_index,
                "Source row": source_index + 1,
                "Name": name or "—",
                "Source Staff ID": staff_id or "—",
                "CV file": file_name or "—",
                "Match method": method,
                "Suggested Staff ID": selected_person.staff_id if selected_person else "",
                "Candidate matches": "; ".join(
                    f"{person.name} · {person.staff_id}" for person in candidates
                ) or "—",
                "Issues": "; ".join(issues) or "—",
            }
        )
    preview = pd.DataFrame(rows)
    auto_matches = {
        int(row["Source index"]): row["Suggested Staff ID"]
        for _, row in preview.iterrows()
        if str(row["Suggested Staff ID"]).strip()
    } if not preview.empty else {}
    return {
        "preview": preview,
        "auto_matches": auto_matches,
        "unmatched": preview[
            preview["Suggested Staff ID"].astype(str).str.strip().eq("")
            & preview["CV file"].astype(str).ne("—")
        ].copy() if not preview.empty else preview,
        "active_people": [
            {"staff_id": person.staff_id, "label": f"{person.name} · {person.staff_id}"}
            for person in people
        ],
    }


def resolve_cv_import(
    cv_df: pd.DataFrame,
    cv_preview: dict,
    manual_resolutions: dict[int, str],
) -> tuple[pd.DataFrame, list[str], dict]:
    """Apply explicit Staff ID resolutions to unmatched CV records."""
    errors = []
    valid_ids: dict[str, list[str]] = {}
    for person in cv_preview["active_people"]:
        normalized = normalize_staff_id(person.get("staff_id"))
        if normalized:
            valid_ids.setdefault(normalized, []).append(person["staff_id"])
    matches = dict(cv_preview["auto_matches"])
    for source_index, staff_id in manual_resolutions.items():
        if staff_id is None or not str(staff_id).strip():
            continue
        normalized = normalize_staff_id(staff_id)
        candidates = valid_ids.get(normalized, [])
        if len(candidates) != 1:
            errors.append(
                f"CV source row {int(source_index) + 1}: '{staff_id}' is not an unambiguous active database Staff ID."
            )
            continue
        matches[int(source_index)] = candidates[0]

    rows = []
    for source_index, target_staff_id in matches.items():
        if source_index < 0 or source_index >= len(cv_df):
            errors.append(f"Invalid CV source row reference: {source_index + 1}.")
            continue
        row = cv_df.iloc[source_index].copy()
        if _empty(row.get("CV File Name")):
            continue
        row["Staff ID"] = target_staff_id
        rows.append(row)
    result_df = pd.DataFrame(rows, columns=cv_df.columns) if rows else cv_df.iloc[0:0].copy()
    summary = {
        "source_rows": len(cv_df),
        "matched_rows": len(result_df),
        "unmatched_rows": max(len(cv_df) - len(matches), 0),
        "manual_resolutions": len(manual_resolutions),
    }
    return result_df, errors, summary


def bulk_import_from_dataframe(session, raw_df, *, ruler_map=None):
    """Delegate the established personnel, assessment, and score write path."""
    return db_ops.bulk_import_from_df(session, raw_df, ruler_map=ruler_map)


def bulk_import_cv_list(session, cv_df):
    """Delegate the established CV document write path."""
    return db_ops.bulk_import_cv_list(session, cv_df)
