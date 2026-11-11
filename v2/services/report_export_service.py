"""Admin competency-report export helpers.

The personnel master export preserves the source workbook's original All-sheet
header row and column order. Current values are reconciled from the same
workbook/database dataframe used by the heatmap.
"""
from __future__ import annotations

from copy import copy
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from config import SCORE_COLS
from data_loader import _normalize_summary_column_name


SUB_DEPARTMENT_COLUMNS = ("Sub-Department", "Sub Department", "Subdepartment", "Unit Name")
SUB_UNIT_COLUMNS = ("Sub Unit", "Sub-Unit", "Sub Unit Name")

# The current workbook has a few legacy spelling variants. These aliases let
# the export overlay current database values without renaming source columns.
SOURCE_COLUMN_ALIASES = {
    "Last Assesment Date": ("Last Assesment Date", "Last Assessment Date"),
    "Assesor1": ("Assesor1", "Assessor 1"),
    "Assessor2": ("Assessor2", "Assessor 2"),
    "Resource/SME": ("Resource/SME", "Resource / SME"),
    "Comment/Suggestion": ("Comment/Suggestion", "Comment / Suggestion"),
}


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    try:
        return not bool(pd.isna(value))
    except (TypeError, ValueError):
        return bool(str(value).strip())


def _clean_text(value: Any) -> str:
    if not _has_value(value):
        return ""
    return str(value).strip()


def _normalise_key(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text.casefold()


def _normalise_column_name(value: Any) -> str | None:
    if value is None:
        return None
    normalized = _normalize_summary_column_name(value)
    if normalized is None:
        return None
    return str(normalized).strip() or None


def resolve_organisation_columns(frame: pd.DataFrame) -> tuple[str | None, str | None]:
    """Resolve Sub-Department and Sub-Unit to existing source columns.

    In the current master workbook, Unit Name is the field used for the
    Sub-Department filter, while Sub Unit is the Sub-Unit field. Explicitly
    named columns take precedence if a future workbook adds them.
    """
    columns = set(frame.columns)
    sub_department = next((name for name in SUB_DEPARTMENT_COLUMNS if name in columns), None)
    sub_unit = next((name for name in SUB_UNIT_COLUMNS if name in columns), None)
    return sub_department, sub_unit


def _distinct_values(frame: pd.DataFrame, column: str | None) -> list[str]:
    if not column or column not in frame.columns:
        return []
    values = {
        _clean_text(value)
        for value in frame[column].tolist()
        if _clean_text(value)
    }
    return sorted(values, key=str.casefold)


def get_sub_department_options(frame: pd.DataFrame) -> list[str]:
    column, _ = resolve_organisation_columns(frame)
    return _distinct_values(frame, column)


def get_sub_unit_options(
    frame: pd.DataFrame,
    sub_department: str | None = None,
) -> list[str]:
    sub_department_column, sub_unit_column = resolve_organisation_columns(frame)
    if not sub_unit_column:
        return []
    scoped = frame
    selected_department = _clean_text(sub_department)
    if selected_department and selected_department.casefold() != "all" and sub_department_column:
        scoped = scoped[
            scoped[sub_department_column].map(_clean_text).str.casefold()
            == selected_department.casefold()
        ]
    return _distinct_values(scoped, sub_unit_column)


def filter_personnel_for_export(
    frame: pd.DataFrame,
    *,
    search: str = "",
    sub_department: str | None = None,
    sub_unit: str | None = None,
    salary_grades: list[str] | tuple[str, ...] | None = None,
) -> pd.DataFrame:
    """Apply name/Staff ID, Sub-Department, Sub-Unit and SG filters."""
    filtered = frame.copy()
    sub_department_column, sub_unit_column = resolve_organisation_columns(filtered)

    query = _clean_text(search).casefold()
    if query:
        name_values = (
            filtered["Name"].fillna("").astype(str)
            if "Name" in filtered.columns
            else pd.Series("", index=filtered.index)
        )
        staff_values = (
            filtered["Staff ID"].fillna("").astype(str)
            if "Staff ID" in filtered.columns
            else pd.Series("", index=filtered.index)
        )
        mask = (
            name_values.str.casefold().str.contains(query, regex=False)
            | staff_values.str.casefold().str.contains(query, regex=False)
        )
        filtered = filtered.loc[mask]

    selected_department = _clean_text(sub_department)
    if selected_department and selected_department.casefold() != "all" and sub_department_column:
        mask = filtered[sub_department_column].map(_clean_text).str.casefold() == selected_department.casefold()
        filtered = filtered.loc[mask]

    selected_unit = _clean_text(sub_unit)
    if selected_unit and selected_unit.casefold() != "all" and sub_unit_column:
        mask = filtered[sub_unit_column].map(_clean_text).str.casefold() == selected_unit.casefold()
        filtered = filtered.loc[mask]

    grades = {_clean_text(value).casefold() for value in (salary_grades or []) if _clean_text(value)}
    if grades and "SG" in filtered.columns:
        filtered = filtered[
            filtered["SG"].map(_clean_text).str.casefold().isin(grades)
        ]

    return filtered.copy()


def _row_value(row: Mapping[str, Any], candidates: tuple[str, ...] | list[str]) -> Any:
    for candidate in candidates:
        value = row.get(candidate)
        if _has_value(value):
            return value
    return None


def _organization_value(row: Mapping[str, Any], candidates: tuple[str, ...]) -> Any:
    return _row_value(row, candidates)


def _safe_excel_value(value: Any) -> Any:
    """Convert pandas/numpy values and prevent formula injection in text cells."""
    if not _has_value(value):
        return None
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if hasattr(value, "item") and not isinstance(value, (str, bytes, datetime)):
        try:
            value = value.item()
        except (ValueError, TypeError):
            pass
    if isinstance(value, datetime) and value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    if isinstance(value, str) and value[:1] in {"=", "+", "-", "@"}:
        return "'" + value
    return value


def _detect_header_row(source_ws) -> int:
    for row_number in range(1, min(source_ws.max_row, 8) + 1):
        values = {
            str(source_ws.cell(row_number, column_number).value).strip().casefold()
            for column_number in range(1, source_ws.max_column + 1)
            if source_ws.cell(row_number, column_number).value is not None
        }
        if {"name", "staff id"}.issubset(values) or {"name", "staff_id"}.issubset(values):
            return row_number
    raise ValueError("Could not locate the original All-sheet header row containing Name and Staff ID.")


def _copy_source_row(source_ws, target_ws, source_row: int, target_row: int, max_column: int) -> None:
    for column_number in range(1, max_column + 1):
        source_cell = source_ws.cell(source_row, column_number)
        target_cell = target_ws.cell(target_row, column_number, _safe_excel_value(source_cell.value))
        if source_cell.has_style:
            target_cell._style = copy(source_cell._style)
        if source_cell.number_format:
            target_cell.number_format = source_cell.number_format
        if source_cell.alignment:
            target_cell.alignment = copy(source_cell.alignment)
        if source_cell.protection:
            target_cell.protection = copy(source_cell.protection)
        if source_cell.hyperlink:
            target_cell._hyperlink = copy(source_cell.hyperlink)


def _source_row_indexes(source_ws, headers: list[Any], header_row: int) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    normalized_headers = [_normalise_column_name(value) for value in headers]
    try:
        staff_id_index = normalized_headers.index("Staff ID") + 1
    except ValueError:
        staff_id_index = None
    try:
        name_index = normalized_headers.index("Name") + 1
    except ValueError:
        name_index = None

    by_staff_id: dict[str, list[int]] = {}
    by_name: dict[str, list[int]] = {}
    for row_number in range(header_row + 1, source_ws.max_row + 1):
        staff_key = _normalise_key(source_ws.cell(row_number, staff_id_index).value) if staff_id_index else None
        name_key = _normalise_key(source_ws.cell(row_number, name_index).value) if name_index else None
        if staff_key:
            by_staff_id.setdefault(staff_key, []).append(row_number)
        if name_key:
            by_name.setdefault(name_key, []).append(row_number)
    return by_staff_id, by_name


def _find_source_row(
    record: Mapping[str, Any],
    by_staff_id: Mapping[str, list[int]],
    by_name: Mapping[str, list[int]],
) -> int | None:
    staff_key = _normalise_key(record.get("Staff ID"))
    name_key = _normalise_key(record.get("Name"))
    matches = by_staff_id.get(staff_key, []) if staff_key else []
    if len(matches) > 1:
        raise ValueError(f"Duplicate Staff ID {record.get('Staff ID')!r} in the source All worksheet; export stopped to avoid selecting the wrong row.")
    if matches:
        return matches[0]
    name_matches = by_name.get(name_key, []) if name_key else []
    if len(name_matches) == 1:
        return name_matches[0]
    if len(name_matches) > 1:
        raise ValueError(f"Personnel name {record.get('Name')!r} is not unique in the source workbook and has no matching Staff ID.")
    return None


def _overlay_record_on_source_row(
    target_ws,
    target_row: int,
    headers: list[Any],
    record: Mapping[str, Any],
) -> None:
    for column_number, raw_header in enumerate(headers, start=1):
        canonical = _normalise_column_name(raw_header)
        if not canonical:
            continue
        candidates = SOURCE_COLUMN_ALIASES.get(canonical, (canonical,))
        value = _row_value(record, candidates)
        if value is not None:
            target_ws.cell(target_row, column_number).value = _safe_excel_value(value)


def _style_report_table(worksheet, header_row: int = 1, *, freeze_at: str | None = None) -> None:
    header_fill = PatternFill("solid", fgColor="20419A")
    header_font = Font(bold=True, color="FFFFFF")
    for cell in worksheet[header_row]:
        if cell.value is not None:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(vertical="center", wrap_text=True)
    worksheet.row_dimensions[header_row].height = 32
    worksheet.freeze_panes = freeze_at or f"A{header_row + 1}"
    last_row = worksheet.max_row
    last_column = worksheet.max_column
    if last_row > header_row and last_column:
        worksheet.auto_filter.ref = (
            f"A{header_row}:{get_column_letter(last_column)}{last_row}"
        )
    for column_number in range(1, last_column + 1):
        letter = get_column_letter(column_number)
        header_value = worksheet.cell(header_row, column_number).value
        header_length = len(str(header_value)) if header_value is not None else 10
        max_length = header_length
        for row_number in range(header_row + 1, min(last_row, header_row + 25) + 1):
            value = worksheet.cell(row_number, column_number).value
            if value is not None:
                max_length = max(max_length, min(len(str(value)), 42))
        worksheet.column_dimensions[letter].width = min(max(max_length + 2, 12), 38)


def _build_personnel_master_sheet(
    workbook: Workbook,
    source_workbook_path: str | Path,
    personnel: pd.DataFrame,
) -> None:
    source_path = Path(source_workbook_path).expanduser()
    if not source_path.is_file():
        raise FileNotFoundError(f"Master workbook not found: {source_path}")

    source_wb = load_workbook(source_path, data_only=True, read_only=False)
    try:
        if "All" not in source_wb.sheetnames:
            raise ValueError("The source master workbook does not contain an 'All' worksheet.")
        source_ws = source_wb["All"]
        header_row = _detect_header_row(source_ws)
        max_column = source_ws.max_column
        headers = [source_ws.cell(header_row, column_number).value for column_number in range(1, max_column + 1)]
        by_staff_id, by_name = _source_row_indexes(source_ws, headers, header_row)

        target_ws = workbook.create_sheet("Personnel Master")
        # Retain the source workbook's preamble and exact header-row position.
        for row_number in range(1, header_row + 1):
            _copy_source_row(source_ws, target_ws, row_number, row_number, max_column)
        for letter, dimension in source_ws.column_dimensions.items():
            target_ws.column_dimensions[letter].width = dimension.width
            target_ws.column_dimensions[letter].hidden = dimension.hidden
        for row_number, dimension in source_ws.row_dimensions.items():
            if row_number <= header_row:
                target_ws.row_dimensions[row_number].height = dimension.height

        next_row = header_row + 1
        template_row = header_row + 1 if source_ws.max_row >= header_row + 1 else header_row
        for _, series in personnel.iterrows():
            record = series.to_dict()
            source_row = _find_source_row(record, by_staff_id, by_name)
            if source_row is not None:
                _copy_source_row(source_ws, target_ws, source_row, next_row, max_column)
                source_style_row = source_row
            else:
                _copy_source_row(source_ws, target_ws, template_row, next_row, max_column)
                for column_number in range(1, max_column + 1):
                    target_ws.cell(next_row, column_number).value = None
                source_style_row = template_row
            _overlay_record_on_source_row(target_ws, next_row, headers, record)
            source_height = source_ws.row_dimensions[source_style_row].height
            if source_height is not None:
                target_ws.row_dimensions[next_row].height = source_height
            next_row += 1

        target_ws.freeze_panes = f"A{header_row + 1}"
        target_ws.auto_filter.ref = (
            f"A{header_row}:{get_column_letter(max_column)}{max(header_row, next_row - 1)}"
        )
        # Preserve useful source widths; apply a restrained width where absent.
        for column_number, header in enumerate(headers, start=1):
            letter = get_column_letter(column_number)
            if target_ws.column_dimensions[letter].width is None:
                target_ws.column_dimensions[letter].width = min(max(len(str(header or "")) + 2, 12), 32)
    finally:
        source_wb.close()


def _build_competency_breakdown(
    personnel: pd.DataFrame,
    competency_names: Mapping[str, str],
    maximum_scores: Mapping[str, float],
) -> list[list[Any]]:
    headers = [
        "Name", "Staff ID", "Department", "Sub-Department", "Sub-Unit", "SG",
        "Competency Code", "Competency Name", "Actual Score", "Maximum Score",
        "Target Score", "Gap Score", "Assessment Status",
    ]
    rows: list[list[Any]] = [headers]
    for _, series in personnel.iterrows():
        person = series.to_dict()
        for code in SCORE_COLS:
            actual = pd.to_numeric(person.get(code), errors="coerce")
            target = pd.to_numeric(person.get(f"R-{code}"), errors="coerce")
            gap = pd.to_numeric(person.get(f"G--{code}"), errors="coerce")
            if pd.isna(gap):
                gap = pd.to_numeric(person.get(f"G-{code}"), errors="coerce")
            rows.append([
                person.get("Name"),
                person.get("Staff ID"),
                person.get("Department"),
                _organization_value(person, SUB_DEPARTMENT_COLUMNS),
                _organization_value(person, SUB_UNIT_COLUMNS),
                person.get("SG"),
                code,
                competency_names.get(code, code),
                float(actual) if pd.notna(actual) else None,
                maximum_scores.get(code),
                float(target) if pd.notna(target) else None,
                float(gap) if pd.notna(gap) else None,
                "Assessed" if pd.notna(actual) else "Not assessed",
            ])
    return rows


def _build_assessment_summary(
    personnel: pd.DataFrame,
    competency_names: Mapping[str, str],
    maximum_scores: Mapping[str, float],
) -> list[list[Any]]:
    person_headers = [
        "Name", "Staff ID", "Department", "Sub-Department", "Sub-Unit", "SG",
        "Assessed Competencies", "Missing Competencies", "Assessment Coverage %", "Average Score",
    ]
    rows: list[list[Any]] = [["PERSONNEL ASSESSMENT SUMMARY"], person_headers]
    for _, series in personnel.iterrows():
        person = series.to_dict()
        scores = pd.to_numeric(pd.Series({code: person.get(code) for code in SCORE_COLS}), errors="coerce")
        assessed = int(scores.notna().sum())
        missing = len(SCORE_COLS) - assessed
        average = float(scores.mean()) if assessed else None
        rows.append([
            person.get("Name"),
            person.get("Staff ID"),
            person.get("Department"),
            _organization_value(person, SUB_DEPARTMENT_COLUMNS),
            _organization_value(person, SUB_UNIT_COLUMNS),
            person.get("SG"),
            assessed,
            missing,
            round(assessed / len(SCORE_COLS) * 100, 1) if SCORE_COLS else 0,
            round(average, 2) if average is not None else None,
        ])

    rows.extend([[], ["COMPETENCY COVERAGE SUMMARY"], [
        "Competency Code", "Competency Name", "Maximum Score", "Assessed Personnel",
        "Missing Personnel", "Coverage %", "Average Score", "Lowest Score", "Highest Score",
    ]])
    for code in SCORE_COLS:
        scores = pd.to_numeric(personnel[code], errors="coerce") if code in personnel.columns else pd.Series(dtype=float)
        valid = scores.dropna()
        assessed_count = int(valid.count())
        total = len(personnel)
        rows.append([
            code,
            competency_names.get(code, code),
            maximum_scores.get(code),
            assessed_count,
            total - assessed_count,
            round(assessed_count / total * 100, 1) if total else 0,
            round(float(valid.mean()), 2) if assessed_count else None,
            float(valid.min()) if assessed_count else None,
            float(valid.max()) if assessed_count else None,
        ])
    return rows


def _build_metadata_sheet(
    workbook: Workbook,
    personnel: pd.DataFrame,
    filters: Mapping[str, Any] | None,
    exported_at: datetime,
) -> None:
    worksheet = workbook.create_sheet("Report Metadata")
    filter_values = dict(filters or {})
    rows = [
        ["Competency Report Export"],
        ["Exported At", exported_at.strftime("%Y-%m-%d %H:%M:%S %Z").strip()],
        ["Selected Personnel", len(personnel)],
        ["Sub-Department", filter_values.get("sub_department") or "All"],
        ["Sub-Unit", filter_values.get("sub_unit") or "All"],
        ["Salary Grade", ", ".join(map(str, filter_values.get("salary_grades") or [])) or "All"],
        ["Name / Staff ID Search", filter_values.get("search") or "None"],
        [],
        ["SELECTED PERSONNEL"],
        ["Name", "Staff ID", "Department", "Sub-Department", "Sub-Unit", "SG"],
    ]
    for _, series in personnel.iterrows():
        person = series.to_dict()
        rows.append([
            person.get("Name"),
            person.get("Staff ID"),
            person.get("Department"),
            _organization_value(person, SUB_DEPARTMENT_COLUMNS),
            _organization_value(person, SUB_UNIT_COLUMNS),
            person.get("SG"),
        ])
    for row in rows:
        worksheet.append([_safe_excel_value(value) for value in row])
    worksheet["A1"].font = Font(size=16, bold=True, color="20419A")
    worksheet["A9"].font = Font(bold=True, color="20419A")
    _style_report_table(worksheet, header_row=10, freeze_at="A11")


def build_competency_report_workbook(
    *,
    source_workbook_path: str | Path,
    personnel: pd.DataFrame,
    filters: Mapping[str, Any] | None = None,
    competency_names: Mapping[str, str] | None = None,
    maximum_scores: Mapping[str, float] | None = None,
    exported_at: datetime | None = None,
) -> bytes:
    """Build a multi-sheet XLSX for the selected personnel and return its bytes."""
    if personnel is None or personnel.empty:
        raise ValueError("Select at least one personnel record before exporting.")
    required_columns = {"Name", "Staff ID"}
    missing = required_columns - set(personnel.columns)
    if missing:
        raise ValueError(f"Personnel data is missing required columns: {sorted(missing)}")

    names = dict(competency_names or {})
    maxima = dict(maximum_scores or {})
    timestamp = exported_at or datetime.now().astimezone().replace(tzinfo=None)

    workbook = Workbook()
    default_sheet = workbook.active
    workbook.remove(default_sheet)

    _build_personnel_master_sheet(workbook, source_workbook_path, personnel)

    breakdown_rows = _build_competency_breakdown(personnel, names, maxima)
    breakdown_ws = workbook.create_sheet("Competency Breakdown")
    for row in breakdown_rows:
        breakdown_ws.append([_safe_excel_value(value) for value in row])
    _style_report_table(breakdown_ws, header_row=1)

    summary_rows = _build_assessment_summary(personnel, names, maxima)
    summary_ws = workbook.create_sheet("Assessment Summary")
    for row in summary_rows:
        summary_ws.append([_safe_excel_value(value) for value in row])
    _style_report_table(summary_ws, header_row=2)
    personnel_last_row = 2 + len(personnel)
    summary_ws.auto_filter.ref = f"A2:J{personnel_last_row}"
    competency_title_row = 4 + len(personnel)
    competency_header_row = competency_title_row + 1
    for cell in summary_ws[competency_title_row]:
        cell.fill = PatternFill("solid", fgColor="20419A")
        cell.font = Font(bold=True, color="FFFFFF")
    for cell in summary_ws[competency_header_row]:
        cell.fill = PatternFill("solid", fgColor="20419A")
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    summary_ws.row_dimensions[competency_title_row].height = 24
    summary_ws.row_dimensions[competency_header_row].height = 32
    summary_ws.freeze_panes = "A3"

    _build_metadata_sheet(workbook, personnel, filters, timestamp)

    workbook.properties.title = "Competency Assessment Report"
    workbook.properties.subject = "Selected personnel competency assessment export"
    workbook.properties.creator = "RE Fraternity Competency Assessment System"

    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()
