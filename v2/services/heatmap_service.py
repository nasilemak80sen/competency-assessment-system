"""Data reconciliation helpers for the competency heatmap.

The workbook remains the baseline for broad competency history. Database
personnel records are reconciled by Staff ID so DB-only staff are not lost,
and current non-empty database metadata / latest-assessment scores are used
where available.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

import pandas as pd


PERSONNEL_COLUMN_MAP = {
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
    "SG Start Date": "sg_start_date",
    "Age Promoted": "age_promoted",
    "Current Assignment": "current_assignment",
    "Assignment Date": "assignment_date",
    "Length in Current Assignment": "assignment_length",
    "Chat Status": "chat_status",
    "Chat Date": "chat_date",
    "Assessment Level": "assessment_level",
    "Last Assessment Date": "last_assessment_date",
    "Sub-disciplines": "sub_disciplines",
    "Potential": "potential",
    "Strength": "strength",
    "Recommendation": "recommendation",
    "Resource / SME": "resource_sme",
    "Interest": "interest",
    "Preference": "preference",
    "Comment / Suggestion": "comment",
    "Assessor 1": "assessor1",
    "Assessor 2": "assessor2",
    "Supervisor": "supervisor",
    "Remarks": "remarks",
}

SCORE_KEY = "db_scores"


def normalise_personnel_key(value: Any) -> str | None:
    """Normalise Staff IDs/names for safe joins across Excel and SQLite."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    key = str(value).strip()
    if not key or key.casefold() in {"nan", "none", "nat", "<na>"}:
        return None
    if key.endswith(".0") and key[:-2].isdigit():
        key = key[:-2]
    return key.casefold()


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(str(value).strip())


def classify_employment_type(value: Any) -> str:
    """Group common spelling variants into CDH/Permanent while retaining others."""
    if not _has_value(value):
        return "Not specified"
    raw = " ".join(str(value).strip().split())
    upper = raw.upper()
    if "CDH" in upper:
        return "CDH"
    if "PERMANENT" in upper or upper in {"PERM", "PERM STAFF"}:
        return "Permanent"
    return raw


def merge_database_personnel_for_heatmap(
    workbook_df: pd.DataFrame | None,
    database_records: Iterable[Mapping[str, Any]],
) -> pd.DataFrame:
    """Keep workbook rows and reconcile every non-deleted DB person into them.

    Staff ID is the primary join key. A unique name is used only as a fallback
    for older workbook rows that lack a Staff ID. Non-empty DB metadata wins
    for matched people; non-null DB score values overlay workbook score values.
    Database-only people are appended even when they have no scores, so their
    row remains visible when minimum assessment coverage is zero.
    """
    out = workbook_df.copy() if isinstance(workbook_df, pd.DataFrame) else pd.DataFrame()
    records = list(database_records)

    required_columns = list(PERSONNEL_COLUMN_MAP)
    score_columns = []
    for record in records:
        scores = record.get(SCORE_KEY) or {}
        for code in scores:
            if code not in score_columns:
                score_columns.append(str(code))
    for column in required_columns + score_columns:
        if column not in out.columns:
            out[column] = pd.NA

    if "Staff ID" not in out.columns:
        out["Staff ID"] = pd.NA
    if "Name" not in out.columns:
        out["Name"] = pd.NA

    by_staff_id: dict[str, list[Any]] = defaultdict(list)
    by_name: dict[str, list[Any]] = defaultdict(list)
    for index, row in out.iterrows():
        staff_key = normalise_personnel_key(row.get("Staff ID"))
        name_key = normalise_personnel_key(row.get("Name"))
        if staff_key:
            by_staff_id[staff_key].append(index)
        if name_key:
            by_name[name_key].append(index)

    for record in records:
        staff_key = normalise_personnel_key(record.get("staff_id"))
        name_key = normalise_personnel_key(record.get("name"))
        target_indexes = by_staff_id.get(staff_key, []) if staff_key else []
        if not target_indexes and name_key and len(by_name.get(name_key, [])) == 1:
            target_indexes = by_name[name_key]

        is_new = not target_indexes
        if is_new:
            row_data = {column: pd.NA for column in out.columns}
            for column, db_field in PERSONNEL_COLUMN_MAP.items():
                if db_field in record:
                    row_data[column] = record.get(db_field)
            for code, score in (record.get(SCORE_KEY) or {}).items():
                if code in out.columns and _has_value(score):
                    row_data[code] = pd.to_numeric(score, errors="coerce")
            out = pd.concat([out, pd.DataFrame([row_data], columns=out.columns)], ignore_index=True)
            new_index = out.index[-1]
            if staff_key:
                by_staff_id[staff_key].append(new_index)
            if name_key:
                by_name[name_key].append(new_index)
            continue

        for index in target_indexes:
            for column, db_field in PERSONNEL_COLUMN_MAP.items():
                value = record.get(db_field)
                if db_field in record and _has_value(value):
                    out.at[index, column] = value
            for code, score in (record.get(SCORE_KEY) or {}).items():
                if code in out.columns and _has_value(score):
                    out.at[index, code] = pd.to_numeric(score, errors="coerce")

    # Canonical labels drive the dropdown; keep the original category intact
    # for audit/export purposes and so unusual employment values remain usable.
    out["Employment Type Filter"] = out["Employment Category"].map(classify_employment_type)
    return out.reset_index(drop=True)
