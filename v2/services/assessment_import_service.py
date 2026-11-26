"""Upload parsing for individual Technology Inventory assessments.

The importer recognises the established SMA/Technology Inventory layout by
competency code (B1-E2) and exact canonical competency name. It does not
re-implement the old-to-new TI mapping; the Final Rating in the source file
is the mapped/current score to import.
"""
from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256
from io import BytesIO
import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd

from config import COMPETENCY_FULLNAMES, SCORE_COLS


CODE_PATTERN = re.compile(
    r"^\s*((?:B|K|P|E)\s*\d{1,2})\s*(?:[-–—:]\s*)?(.*?)\s*$",
    re.IGNORECASE,
)
RATING_PATTERN = re.compile(r"([0-5](?:\.\d+)?)")
NAME_ALIASES = {
    "B1": ("Fluid Characterisation", "Fluid Characterization"),
    "B2": ("Rock Properties",),
    "B3": ("Integrated Reservoir Characterisation", "Integrated Reservoir Characterization"),
    "B4": ("Oil & Gas Resource Estimation", "Oil and Gas Resource Estimation"),
    "B5": ("Reservoir Performance Analysis",),
    "B6": ("Numerical Simulation",),
    "B7": ("Depletion Strategy and Drive Mechanism",),
    "B8": ("Well Performance and Prediction",),
    "B9": ("Pressure Transient Analysis",),
    "B10": ("Production Operations",),
    "B11": ("Subsurface Development Planning and Execution",),
    "B12": (
        "Integrated Reservoir Management Principle & Practices",
        "Integrated Reservoir Management Principles and Practices",
        "Integrated Reservoir Management Principles & Practices",
    ),
    "K1": ("Petroleum Economics, Risk and Uncertainty Management", "Petroleum Economics, Risk & Uncertainty Management"),
    "K2": ("Integrated Field Development Planning",),
    "K3": ("Enhanced Oil Recovery", "EOR"),
    "K4": ("Advanced Reservoir Data Acquisition and Monitoring",),
    "K5": ("CO2 Sequestration and Disposal", "CO2 Sequestration & Disposal"),
    "P1": ("Complex Fluid System",),
    "P2": ("Complex Reservoir System",),
    "P3": ("Advanced Reservoir Modelling", "Advanced Reservoir Modeling"),
    "P4": ("Smart Fields Reservoir Development",),
    "P5": ("Unconventional Hydrocarbon Energy Sources",),
    "E1": ("Unconventional Hydrocarbon Energy Sources (methane hydrates)",),
    "E2": ("Advanced Technologies and Novel Solutions",),
}
VALID_CODES = set(SCORE_COLS)


def _normalise(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold().replace("&", " and ")
    text = text.replace("co2", "carbon dioxide")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


_NAME_TO_CODE: dict[str, str] = {}
for _code, _name in COMPETENCY_FULLNAMES.items():
    _NAME_TO_CODE[_normalise(_name)] = _code
for _code, _names in NAME_ALIASES.items():
    for _name in _names:
        _NAME_TO_CODE[_normalise(_name)] = _code


def _clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.casefold() in {"nan", "none", "nat"} else text


def _parse_rating(value: Any) -> float | None:
    text = _clean(value)
    if not text:
        return None
    match = RATING_PATTERN.search(text)
    if not match:
        return None
    try:
        number = float(match.group(1))
    except ValueError:
        return None
    return number if 0.0 <= number <= 5.0 else None


def _resolve_heading(value: Any) -> tuple[str | None, str, str | None]:
    """Return (code, source label, issue); code tags take precedence."""
    text = _clean(value)
    match = CODE_PATTERN.match(text)
    if match:
        code = re.sub(r"\s+", "", match.group(1)).upper()
        label = match.group(2).strip(" -–—:")
        label = re.split(r"\bSelf\s*Rating\s*:?", label, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        if code not in VALID_CODES:
            return None, label, f"Unsupported competency tag: {code}"
        if label and _normalise(label) not in {
            _normalise(COMPETENCY_FULLNAMES.get(code, "")),
            *(_normalise(alias) for alias in NAME_ALIASES.get(code, ())),
        }:
            return code, label, (
                f"{code} is tagged with a competency name that differs from the "
                "registered catalogue. Verify this row before approval."
            )
        return code, label, None

    normalized = _normalise(text)
    code = _NAME_TO_CODE.get(normalized)
    if code:
        return code, text, None
    return None, "", None


def _label_value(row: list[str], label: str) -> str:
    target = _normalise(label)
    for index, value in enumerate(row):
        text = _clean(value)
        normalized = _normalise(text)
        if not text:
            continue
        if target in normalized:
            inline = re.search(
                re.escape(label) + r"\s*:?\s*([^\t]+)$",
                text,
                re.IGNORECASE,
            )
            if inline and inline.group(1).strip():
                return inline.group(1).strip()
            for candidate in row[index + 1:]:
                if _clean(candidate):
                    return _clean(candidate)
    return ""


def _date_value(value: Any) -> date | None:
    text = _clean(value)
    if not text:
        return None
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    return None if pd.isna(parsed) else parsed.date()


def _metadata_from_grid(rows: list[list[str]]) -> dict:
    metadata = {
        "person_name": "",
        "staff_id": "",
        "assessment_date": None,
        "assessment_type": "",
        "assessor1": "",
        "assessor2": "",
        "supervisor": "",
        "remarks": "",
    }
    for row in rows:
        joined = " ".join(_clean(value) for value in row if _clean(value))
        for index, value in enumerate(row):
            label = _normalise(value).rstrip()
            if label in {"name", "personnel name", "employee name"} and not metadata["person_name"]:
                metadata["person_name"] = next(
                    (_clean(v) for v in row[index + 1:] if _clean(v)), ""
                )
            elif label in {"staffid", "staff id", "employee id"} and not metadata["staff_id"]:
                metadata["staff_id"] = next(
                    (_clean(v) for v in row[index + 1:] if _clean(v)), ""
                )
            elif label.startswith("assessment date") and metadata["assessment_date"] is None:
                value_text = next(
                    (_clean(v) for v in row[index + 1:] if _clean(v)), ""
                )
                metadata["assessment_date"] = _date_value(value_text)
            elif label in {"assessor 1", "assessor name"} and not metadata["assessor1"]:
                metadata["assessor1"] = next(
                    (_clean(v) for v in row[index + 1:] if _clean(v)), ""
                )
            elif label == "assessor 2" and not metadata["assessor2"]:
                metadata["assessor2"] = next(
                    (_clean(v) for v in row[index + 1:] if _clean(v)), ""
                )
            elif label in {"supervisor", "superior name"} and not metadata["supervisor"]:
                metadata["supervisor"] = next(
                    (_clean(v) for v in row[index + 1:] if _clean(v)), ""
                )
        if not metadata["assessment_type"] and "sma 2025" in _normalise(joined):
            metadata["assessment_type"] = "SMA 2025"
    return metadata


def _parse_grid(rows: list[list[str]]) -> dict:
    metadata = _metadata_from_grid(rows)
    records: dict[str, dict] = {}
    issues: list[str] = []
    current_code: str | None = None
    current_record: dict | None = None

    duplicate_codes: set[str] = set()

    def finish_current():
        nonlocal current_code, current_record
        if current_code and current_record is not None:
            if current_code in duplicate_codes:
                pass
            elif current_code in records:
                issues.append(
                    f"Duplicate competency section {current_code}; neither duplicate will be imported automatically."
                )
                records.pop(current_code, None)
                duplicate_codes.add(current_code)
            else:
                records[current_code] = current_record
        current_code = None
        current_record = None

    for row_index, source_row in enumerate(rows):
        row = [_clean(value) for value in source_row]
        if not any(row):
            continue
        heading_index = next(
            (
                index for index, value in enumerate(row)
                if value and (CODE_PATTERN.match(value) or _normalise(value) in _NAME_TO_CODE)
            ),
            None,
        )
        if heading_index is not None:
            finish_current()
            code, source_label, issue = _resolve_heading(row[heading_index])
            if issue:
                issues.append(f"Row {row_index + 1}: {issue}")
            if code:
                current_code = code
                current_record = {
                    "code": code,
                    "competency_name": source_label or COMPETENCY_FULLNAMES.get(code, code),
                    "self_rating": _parse_rating(_label_value(row, "Self Rating")),
                    "final_rating": _parse_rating(_label_value(row, "Final Rating")),
                    "evidence": [],
                    "assessor_comments": [],
                    "superior_comments": [],
                    "assessor_approval": "",
                    "superior_approval": "",
                    "source_row": row_index + 1,
                }
                continue
        if current_record is None:
            continue

        # Evidence normally sits in the first column of continuation rows.
        first_cell = row[0] if row else ""
        if first_cell and first_cell.casefold() not in {"picture", "assessor approval", "superior approval"}:
            if not _normalise(first_cell).startswith(("assessor name", "superior s comments")):
                current_record["evidence"].append(first_cell.strip('"'))

        for index, value in enumerate(row[1:], start=1):
            if not value or value.casefold() == "picture":
                continue
            normalized = _normalise(value)
            if "assessor name rating comments" in normalized or normalized.startswith("assessor s comments"):
                current_record["assessor_comments"].append(value.strip('"'))
                assessor_match = re.search(
                    r"Assessor Name,\s*Rating\s*&?\s*Comments:\s*([^\.]+)",
                    value,
                    re.IGNORECASE,
                )
                if assessor_match and not metadata["assessor1"]:
                    metadata["assessor1"] = assessor_match.group(1).strip()
            elif normalized.startswith("superior s comments") or normalized.startswith("superiors comments"):
                current_record["superior_comments"].append(value.strip('"'))
            elif index >= 7 and value.casefold() not in {"assessor's approval", "superior's approval"}:
                key = "assessor_approval" if index == 7 else "superior_approval"
                if value.casefold() != "picture":
                    current_record[key] = value
            elif index >= 5:
                current_record["assessor_comments"].append(value.strip('"'))

    finish_current()

    competencies = []
    for code in SCORE_COLS:
        record = records.get(code)
        if record is None:
            continue
        if code in duplicate_codes:
            continue
        record["evidence"] = "\n".join(dict.fromkeys(record["evidence"])).strip()
        record["assessor_comments"] = "\n".join(dict.fromkeys(record["assessor_comments"])).strip()
        record["superior_comments"] = "\n".join(dict.fromkeys(record["superior_comments"])).strip()
        competencies.append(record)

    missing = [code for code in SCORE_COLS if code not in records]
    missing_final = [row["code"] for row in competencies if row["final_rating"] is None]
    if missing_final:
        issues.append(
            "Final Rating is missing or not numeric for: " + ", ".join(missing_final)
        )
    if not competencies:
        issues.append("No recognised B1-E2 competency sections were extracted.")
    metadata["remarks"] = metadata.get("remarks") or ""

    return {
        "metadata": metadata,
        "competencies": competencies,
        "missing_codes": missing,
        "missing_final_rating": missing_final,
        "issues": issues,
    }


def _grid_from_text(text: str) -> list[list[str]]:
    return [line.rstrip("\r\n").split("\t") for line in text.splitlines()]


def _parse_pdf_text(text: str) -> dict:
    """Parse text-extractable PDFs while preserving competency section boundaries."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if any("\t" in line for line in lines):
        return _parse_grid(_grid_from_text(text))

    metadata = _metadata_from_grid([[line] for line in lines])
    records: dict[str, dict] = {}
    duplicate_codes: set[str] = set()
    issues: list[str] = []
    current: dict | None = None

    def finish_current():
        nonlocal current
        if current is None:
            return
        code = current["code"]
        if code in duplicate_codes:
            current = None
        elif code in records:
            issues.append(
                f"Duplicate competency section {code}; neither duplicate will be imported automatically."
            )
            records.pop(code, None)
            duplicate_codes.add(code)
            current = None
        else:
            records[code] = current
            current = None

    for line_number, line in enumerate(lines, start=1):
        if CODE_PATTERN.match(line):
            finish_current()
            code, label, issue = _resolve_heading(line)
            if issue:
                issues.append(f"PDF line {line_number}: {issue}")
            if not code:
                continue
            current = {
                "code": code,
                "competency_name": label or COMPETENCY_FULLNAMES.get(code, code),
                "self_rating": None,
                "final_rating": None,
                "evidence": [],
                "assessor_comments": [],
                "superior_comments": [],
                "assessor_approval": "",
                "superior_approval": "",
                "source_row": line_number,
            }
            for rating_label, key in (
                ("Self Rating", "self_rating"),
                ("Final Rating", "final_rating"),
            ):
                match = re.search(
                    rf"{rating_label}\s*:?\s*([0-5](?:\.\d+)?)",
                    line,
                    re.IGNORECASE,
                )
                if match:
                    current[key] = _parse_rating(match.group(1))
            continue

        if current is None:
            continue
        for rating_label, key in (
            ("Self Rating", "self_rating"),
            ("Final Rating", "final_rating"),
        ):
            match = re.search(
                rf"{rating_label}\\s*:?\\s*([0-5](?:\\.\\d+)?)",
                line,
                re.IGNORECASE,
            )
            if match:
                current[key] = _parse_rating(match.group(1))

        if "assessor name" in line.casefold() or "assessor's comments" in line.casefold():
            current["assessor_comments"].append(line)
            assessor_match = re.search(
                r"Assessor Name,\s*Rating\s*&?\s*Comments:\s*([^\.]+)",
                line,
                re.IGNORECASE,
            )
            if assessor_match and not metadata["assessor1"]:
                metadata["assessor1"] = assessor_match.group(1).strip()
        elif "superior's comments" in line.casefold() or "superiors comments" in line.casefold():
            current["superior_comments"].append(line)
        elif "assessor approval" in line.casefold():
            current["assessor_approval"] = line
        elif "superior approval" in line.casefold():
            current["superior_approval"] = line
        elif line.casefold() != "picture":
            current["evidence"].append(line)

    finish_current()
    competencies = []
    for code in SCORE_COLS:
        record = records.get(code)
        if record is None or code in duplicate_codes:
            continue
        for field in ("evidence", "assessor_comments", "superior_comments"):
            record[field] = "\n".join(dict.fromkeys(record[field])).strip()
        competencies.append(record)
    missing = [code for code in SCORE_COLS if code not in records]
    missing_final = [row["code"] for row in competencies if row["final_rating"] is None]
    if missing_final:
        issues.append(
            "Final Rating is missing or not numeric for: " + ", ".join(missing_final)
        )
    if not competencies:
        issues.append("No recognised B1-E2 competency sections were extracted from PDF text.")
    return {
        "metadata": metadata,
        "competencies": competencies,
        "missing_codes": missing,
        "missing_final_rating": missing_final,
        "issues": issues,
    }


def parse_assessment_upload(file_name: str, file_bytes: bytes) -> dict:
    """Parse an assessment workbook, PDF, or tab-delimited text export."""
    suffix = Path(file_name or "").suffix.casefold()
    fingerprint = sha256(file_bytes).hexdigest()
    if suffix in {".xlsx", ".xlsm"}:
        from openpyxl import load_workbook
        workbook = load_workbook(BytesIO(file_bytes), data_only=True, read_only=True)
        rows = []
        try:
            for worksheet in workbook.worksheets:
                for row in worksheet.iter_rows(values_only=True):
                    values = [_clean(value) for value in row]
                    if any(values):
                        rows.append(values)
        finally:
            workbook.close()
        result = _parse_grid(rows)
    elif suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("PDF support requires pypdf. Install the project requirements and retry.") from exc
        reader = PdfReader(BytesIO(file_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if not text.strip():
            raise ValueError(
                "This PDF contains no extractable text. It may be scanned or image-only; "
                "a text-based PDF is required for this import workflow."
            )
        result = _parse_pdf_text(text)
    elif suffix in {".txt", ".tsv", ".csv"}:
        text = file_bytes.decode("utf-8-sig", errors="replace")
        result = _parse_grid(_grid_from_text(text))
    else:
        raise ValueError("Supported assessment formats are .xlsx, .xlsm, .pdf, .txt and .tsv.")

    metadata = result["metadata"]
    competencies = result["competencies"]
    if metadata.get("assessment_date") is not None:
        metadata["assessment_date"] = metadata["assessment_date"].isoformat()
    result.update({
        "source_filename": Path(file_name).name,
        "source_sha256": fingerprint,
        "recognized_count": len(competencies),
        "valid_final_count": sum(item["final_rating"] is not None for item in competencies),
        "missing_count": len(result["missing_codes"]),
    })
    return result
