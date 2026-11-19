"""Import replacement SharePoint document links against exact personnel identities.

The mapping file is intentionally supplied at runtime. It contains internal
personnel details and private SharePoint URLs and must not be committed to the
public source repository.
"""
from __future__ import annotations

import io
import re
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from sqlalchemy.orm import Session

from models import CVDocument, Personnel


MAPPING_COLUMNS = [
    "Name",
    "Staff ID",
    "Staff Position",
    "Status",
    "CV File Name",
    "File Type",
    "Local File Path",
    "Old File URI",
    "Relative Path",
    "SharePoint URL",
    "Modified Date",
    "Match Result",
    "Action",
]

REQUIRED_MAPPING_COLUMNS = (
    "Name",
    "CV File Name",
    "File Type",
    "SharePoint URL",
)


def normalize_match_value(value: object) -> str:
    """Normalize names and filenames for conservative exact matching."""
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold().strip()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_staff_id(value: object) -> str:
    cleaned = _clean(value)
    if not cleaned:
        return ""
    cleaned = re.sub(r"\\.0$", "", cleaned)
    try:
        numeric = float(cleaned)
        if numeric.is_integer():
            return str(int(numeric))
    except ValueError:
        pass
    return cleaned.casefold()


def _excel_date(value: object):
    """Read Excel serial dates and ordinary date strings safely."""
    if value is None or value == "":
        return None
    try:
        numeric = float(value)
        if 20000 <= numeric <= 80000:
            return datetime(1899, 12, 30) + timedelta(days=numeric)
    except (TypeError, ValueError):
        pass
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.to_pydatetime()


def load_sharepoint_mapping(file_name: str, file_bytes: bytes) -> pd.DataFrame:
    """Load the 13-column Excel tab-delimited export or an equivalent XLSX."""
    suffix = Path(file_name or "").suffix.casefold()
    if suffix in {".xlsx", ".xlsm"}:
        raw = pd.read_excel(io.BytesIO(file_bytes), header=None, dtype=object)
    else:
        raw = pd.read_csv(
            io.BytesIO(file_bytes),
            sep="\t",
            header=None,
            dtype=str,
            keep_default_na=False,
            engine="python",
        )

    if raw.empty:
        return pd.DataFrame(columns=MAPPING_COLUMNS)

    # Accept a labelled export as well as the headerless Excel copy supplied.
    first_row = [str(value).strip().casefold() for value in raw.iloc[0].tolist()]
    if "name" in first_row and "sharepoint url" in first_row:
        raw.columns = [str(value).strip() for value in raw.iloc[0].tolist()]
        raw = raw.iloc[1:].reset_index(drop=True)
        for column in MAPPING_COLUMNS:
            if column not in raw.columns:
                raw[column] = ""
        mapped = raw[MAPPING_COLUMNS].copy()
    else:
        if raw.shape[1] < 10:
            raise ValueError(
                f"Expected at least 10 tab-separated columns; found {raw.shape[1]}."
            )
        mapped = raw.iloc[:, : len(MAPPING_COLUMNS)].copy()
        mapped.columns = MAPPING_COLUMNS[: mapped.shape[1]]
        for column in MAPPING_COLUMNS:
            if column not in mapped.columns:
                mapped[column] = ""
        mapped = mapped[MAPPING_COLUMNS]

    for column in MAPPING_COLUMNS:
        mapped[column] = mapped[column].map(_clean)

    mapped = mapped[
        mapped["Name"].ne("") & mapped["CV File Name"].ne("")
    ].copy()
    mapped["File Type"] = mapped["File Type"].str.upper().str.lstrip(".")
    mapped["Modified Date Parsed"] = mapped["Modified Date"].map(_excel_date)
    mapped["Normalized Name"] = mapped["Name"].map(normalize_match_value)
    mapped["Normalized File Name"] = mapped["CV File Name"].map(normalize_match_value)
    return mapped.reset_index(drop=True)


def _valid_replacement_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return (
        parsed.scheme == "https"
        and parsed.hostname == "petronas.sharepoint.com"
        and parsed.path.casefold().startswith("/sites/ecm_ups_coe/")
    )


def import_sharepoint_mapping(session: Session, mapping_df: pd.DataFrame) -> dict:
    """Upsert document links using exact personnel name and exact filename.

    Staff ID is used as a cross-check when present. No partial-name matching
    is performed. New document rows are created when a valid personnel match
    exists but that exact filename is not yet registered.
    """
    result = {
        "updated": 0,
        "added": 0,
        "unmatched": 0,
        "ambiguous": 0,
        "skipped": 0,
        "errors": 0,
        "issues": [],
    }
    active_people = (
        session.query(Personnel)
        .filter(Personnel.is_deleted.is_(False))
        .all()
    )
    people_by_staff_id: dict[str, list[Personnel]] = {}
    for person in active_people:
        staff_id = _normalize_staff_id(person.staff_id)
        if staff_id:
            people_by_staff_id.setdefault(staff_id, []).append(person)

    seen_rows: dict[tuple[str, str], str] = {}

    for row_number, row in mapping_df.iterrows():
        source_name = _clean(row.get("Name"))
        source_filename = _clean(row.get("CV File Name"))
        source_staff_id = _normalize_staff_id(row.get("Staff ID"))
        url = _clean(row.get("SharePoint URL"))
        file_type = _clean(row.get("File Type")).upper().lstrip(".")

        def issue(bucket: str, reason: str):
            result[bucket] += 1
            result["issues"].append({
                "Row": int(row_number) + 1,
                "Personnel": source_name,
                "Document": source_filename,
                "Reason": reason,
            })

        if not source_name or not source_filename:
            issue("skipped", "Missing personnel name or document filename")
            continue
        if not _valid_replacement_url(url):
            issue("skipped", "Replacement URL is not an ecm_ups_coe SharePoint HTTPS link")
            continue
        if file_type not in {"PDF", "DOC", "DOCX"}:
            issue("skipped", f"Unsupported document type: {file_type or 'blank'}")
            continue

        normalized_name = normalize_match_value(source_name)
        normalized_filename = normalize_match_value(source_filename)
        mapping_key = (normalized_name, normalized_filename)
        previous_url = seen_rows.get(mapping_key)
        if previous_url is not None:
            if previous_url == url:
                result["skipped"] += 1
                continue
            issue("ambiguous", "Duplicate personnel/document mapping has conflicting URLs")
            continue
        seen_rows[mapping_key] = url

        person = None
        match_method = "Exact normalized personnel name"
        if source_staff_id:
            staff_matches = people_by_staff_id.get(source_staff_id, [])
            if len(staff_matches) > 1:
                issue("ambiguous", "Staff ID matches multiple active personnel records")
                continue
            if len(staff_matches) == 1:
                candidate = staff_matches[0]
                if normalize_match_value(candidate.name) != normalized_name:
                    issue("ambiguous", "Staff ID and personnel name identify different records")
                    continue
                person = candidate
                match_method = "Staff ID + exact normalized personnel name"

        if person is None:
            exact_people = [
                candidate for candidate in active_people
                if normalize_match_value(candidate.name) == normalized_name
            ]
            if len(exact_people) == 0:
                issue("unmatched", "No exact personnel-name match")
                continue
            if len(exact_people) > 1:
                issue("ambiguous", "Personnel name matches multiple active records")
                continue
            person = exact_people[0]
            if source_staff_id:
                match_method = "Exact normalized personnel name (Staff ID not found)"

        existing_documents = (
            session.query(CVDocument)
            .filter(
                CVDocument.personnel_id == person.id,
                CVDocument.is_deleted.is_(False),
            )
            .all()
        )
        exact_documents = [
            document for document in existing_documents
            if normalize_match_value(document.cv_file_name) == normalized_filename
        ]
        if len(exact_documents) > 1:
            issue("ambiguous", "Multiple existing document rows have the same filename for this person")
            continue

        try:
            if exact_documents:
                document = exact_documents[0]
                document.sharepoint_url = url
                document.file_type = file_type
                document.cv_status = _clean(row.get("Status")) or "Found"
                document.match_method = match_method
                document.notes = _clean(row.get("Action")) or _clean(row.get("Match Result"))
                document.modified_date = row.get("Modified Date Parsed")
                result["updated"] += 1
            else:
                session.add(CVDocument(
                    personnel_id=person.id,
                    cv_file_name=source_filename,
                    file_type=file_type,
                    local_file_path=_clean(row.get("Local File Path")) or None,
                    sharepoint_url=url,
                    cv_status=_clean(row.get("Status")) or "Found",
                    match_method=match_method,
                    notes=_clean(row.get("Action")) or _clean(row.get("Match Result")),
                    modified_date=row.get("Modified Date Parsed"),
                    is_deleted=False,
                ))
                result["added"] += 1
        except Exception as exc:
            issue("errors", f"Could not stage document update: {type(exc).__name__}")

    try:
        session.flush()
    except Exception:
        session.rollback()
        raise
    return result
