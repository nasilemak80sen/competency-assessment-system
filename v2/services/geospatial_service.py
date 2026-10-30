"""Renderer-independent geospatial data preparation for workforce maps."""
from __future__ import annotations
import math
import re
from typing import Any
import pandas as pd
from config import NATIONALITY_ALIASES

GEOSPATIAL_SCHEMA_VERSION = 1
GEOSPATIAL_DATASET_TYPE = "nationality-distribution"
PERSONNEL_DISPLAY_FIELDS = {
    "Name": "name", "Staff Position": "staffPosition", "Department": "department",
    "SG": "salaryGrade", "Employment Category": "employmentCategory",
    "Section Name": "sectionName",
}
_REQUIRED_MAP_COLUMNS = {"Nationality", "Personnel Count", "Latitude", "Longitude"}


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        result = pd.isna(value)
        return bool(result) if not hasattr(result, "__len__") else False
    except (TypeError, ValueError):
        return False


def _clean_text(value: Any, fallback: str = "") -> str:
    if _is_missing(value):
        return fallback
    value = str(value).strip()
    return fallback if value.casefold() in {"nan", "none", "nat", "<na>"} else value


def _canonical_nationality(value: Any) -> str:
    text = _clean_text(value)
    return str(NATIONALITY_ALIASES.get(text, text)).strip()


def _finite_number(value: Any, field: str, nationality: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field} for nationality {nationality!r}: {value!r}") from exc
    if not math.isfinite(number):
        raise ValueError(f"Non-finite {field} for nationality {nationality!r}")
    return number


def _personnel_records(personnel_df: pd.DataFrame | None, valid: set[str]) -> list[dict[str, str]]:
    """Return only the personnel fields rendered by the globe details panel."""
    if personnel_df is None or personnel_df.empty or "Nationality" not in personnel_df.columns:
        return []
    output = []
    for _, row in personnel_df.iterrows():
        raw = _clean_text(row.get("Nationality"))
        if not raw:
            continue
        memberships = dict.fromkeys(
            _canonical_nationality(part) for part in raw.split("/") if _clean_text(part)
        )
        for nationality in memberships:
            if nationality in valid:
                output.append({
                    "nationality": nationality,
                    **{target: _clean_text(row.get(source, "")) for source, target in PERSONNEL_DISPLAY_FIELDS.items()},
                })
    return output


def build_nationality_dataset(
    map_df: pd.DataFrame, personnel_df: pd.DataFrame | None = None
) -> dict[str, Any]:
    """Build a renderer-neutral, versioned nationality dataset.

    Aggregate personnelCount is authoritative without filters. The people
    detail list is used to calculate browser-side filtered counts.
    """
    if map_df is None or map_df.empty:
        raise ValueError("Nationality map data cannot be empty.")
    missing = _REQUIRED_MAP_COLUMNS.difference(map_df.columns)
    if missing:
        raise ValueError(f"Nationality map data is missing columns: {sorted(missing)}")

    records = []
    seen = set()
    for _, row in map_df.iterrows():
        nationality = _canonical_nationality(row.get("Nationality"))
        if not nationality:
            continue
        key = nationality.casefold()
        if key in seen:
            raise ValueError(f"Duplicate nationality after alias normalisation: {nationality!r}")
        seen.add(key)

        raw_count = _finite_number(row.get("Personnel Count"), "Personnel Count", nationality)
        if raw_count <= 0 or not raw_count.is_integer():
            raise ValueError(f"Personnel Count must be a positive integer for {nationality!r}")
        latitude = _finite_number(row.get("Latitude"), "Latitude", nationality)
        longitude = _finite_number(row.get("Longitude"), "Longitude", nationality)
        if not -90 <= latitude <= 90:
            raise ValueError(f"Latitude out of range for {nationality!r}: {latitude}")
        if not -180 <= longitude <= 180:
            raise ValueError(f"Longitude out of range for {nationality!r}: {longitude}")

        raw_pct = row.get("Representation")
        pct = 0.0 if _is_missing(raw_pct) else _finite_number(raw_pct, "Representation", nationality)
        if not 0 <= pct <= 100:
            raise ValueError(f"Representation must be between 0 and 100 for {nationality!r}")
        slug = re.sub(r"[^a-z0-9]+", "-", key).strip("-") or "nationality"
        records.append({
            "id": slug,
            "nationality": nationality,
            "personnelCount": int(raw_count),
            "latitude": latitude,
            "longitude": longitude,
            "representationPct": pct,
            "representationDisplay": _clean_text(row.get("Representation Display"), f"{pct:.1f}%"),
            "people": [],
        })

    if not records:
        raise ValueError("Nationality map data has no valid positive-count records.")
    if len({record["id"] for record in records}) != len(records):
        raise ValueError("Nationality labels produce duplicate geospatial record IDs.")

    by_nationality = {record["nationality"]: record for record in records}
    valid = set(by_nationality)
    for person in _personnel_records(personnel_df, valid):
        by_nationality[person["nationality"]]["people"].append({
            key: value for key, value in person.items() if key != "nationality"
        })

    dataset = {
        "schemaVersion": GEOSPATIAL_SCHEMA_VERSION,
        "datasetType": GEOSPATIAL_DATASET_TYPE,
        "summary": {
            "nationalityCount": len(records),
            "personnelMembershipCount": sum(record["personnelCount"] for record in records),
        },
        "records": records,
    }
    validate_nationality_dataset(dataset)
    return dataset


def validate_nationality_dataset(dataset: Any) -> None:
    """Validate the Python-to-browser contract before HTML serialization."""
    if not isinstance(dataset, dict):
        raise TypeError("Geospatial dataset must be a dictionary.")
    if dataset.get("schemaVersion") != GEOSPATIAL_SCHEMA_VERSION:
        raise ValueError(f"Unsupported geospatial schemaVersion: {dataset.get('schemaVersion')!r}")
    if dataset.get("datasetType") != GEOSPATIAL_DATASET_TYPE:
        raise ValueError(f"Unsupported geospatial datasetType: {dataset.get('datasetType')!r}")
    summary, records = dataset.get("summary"), dataset.get("records")
    if not isinstance(summary, dict) or not isinstance(records, list) or not records:
        raise ValueError("Geospatial dataset requires summary metadata and non-empty records.")

    required = {
        "id", "nationality", "personnelCount", "latitude", "longitude",
        "representationPct", "representationDisplay", "people",
    }
    ids = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict) or required.difference(record):
            raise ValueError(f"Geospatial record {index} is missing required fields.")
        record_id = record["id"]
        if not isinstance(record_id, str) or not record_id.strip() or record_id in ids:
            raise ValueError(f"Geospatial record {index} has an invalid or duplicate id.")
        ids.add(record_id)
        if not isinstance(record["nationality"], str) or not record["nationality"].strip():
            raise ValueError(f"Geospatial record {index} has an invalid nationality.")
        count = record["personnelCount"]
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise ValueError(f"Geospatial record {index} has an invalid personnelCount.")
        lat, lon, pct = record["latitude"], record["longitude"], record["representationPct"]
        if not isinstance(lat, (int, float)) or not math.isfinite(lat) or not -90 <= lat <= 90:
            raise ValueError(f"Geospatial record {index} has an invalid latitude.")
        if not isinstance(lon, (int, float)) or not math.isfinite(lon) or not -180 <= lon <= 180:
            raise ValueError(f"Geospatial record {index} has an invalid longitude.")
        if not isinstance(pct, (int, float)) or not math.isfinite(pct) or not 0 <= pct <= 100:
            raise ValueError(f"Geospatial record {index} has an invalid representationPct.")
        if not isinstance(record["representationDisplay"], str) or not isinstance(record["people"], list):
            raise ValueError(f"Geospatial record {index} has invalid display/detail fields.")
        for person in record["people"]:
            if not isinstance(person, dict) or any(not isinstance(value, str) for value in person.values()):
                raise ValueError(f"Geospatial record {index} has an invalid personnel detail record.")

    if summary.get("nationalityCount") != len(records):
        raise ValueError("Geospatial summary nationalityCount does not match records.")
    expected = sum(record["personnelCount"] for record in records)
    if summary.get("personnelMembershipCount") != expected:
        raise ValueError("Geospatial summary personnelMembershipCount does not match records.")


__all__ = [
    "GEOSPATIAL_SCHEMA_VERSION", "GEOSPATIAL_DATASET_TYPE",
    "build_nationality_dataset", "validate_nationality_dataset",
]
