"""User-owned saved chart configurations.

Saved configurations contain only chart and filter settings; they never store
personnel rows or assessment data. Ownership is enforced in every query.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import ChartConfiguration


def _json_default(value: Any):
    """Convert common pandas/numpy scalar wrappers to JSON-native values."""
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"Unsupported chart configuration value: {type(value).__name__}")


def _serialize_configuration(configuration: dict) -> str:
    if not isinstance(configuration, dict):
        raise ValueError("A chart configuration must be a dictionary.")
    try:
        return json.dumps(
            configuration,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
            default=_json_default,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Could not save this chart configuration: {exc}") from exc


def list_chart_configurations(session: Session, owner_user_id: int) -> list[dict]:
    """List configurations owned by one authenticated user, newest first."""
    if owner_user_id is None:
        return []
    records = (
        session.query(ChartConfiguration)
        .filter(ChartConfiguration.owner_user_id == int(owner_user_id))
        .order_by(
            ChartConfiguration.updated_at.desc(),
            ChartConfiguration.name.asc(),
        )
        .all()
    )
    return [
        {
            "id": record.id,
            "name": record.name,
            "description": record.description or "",
            "updated_at": record.updated_at,
        }
        for record in records
    ]


def get_chart_configuration(
    session: Session,
    owner_user_id: int,
    configuration_id: int,
) -> dict | None:
    """Load one configuration only when it belongs to the requesting user."""
    record = (
        session.query(ChartConfiguration)
        .filter(
            ChartConfiguration.id == int(configuration_id),
            ChartConfiguration.owner_user_id == int(owner_user_id),
        )
        .one_or_none()
    )
    if record is None:
        return None
    try:
        configuration = json.loads(record.configuration_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("The saved chart configuration contains invalid JSON.") from exc
    if not isinstance(configuration, dict):
        raise ValueError("The saved chart configuration is not a valid object.")
    return {
        "id": record.id,
        "name": record.name,
        "description": record.description or "",
        "configuration": configuration,
        "updated_at": record.updated_at,
    }


def save_chart_configuration(
    session: Session,
    owner_user_id: int,
    owner_username: str,
    name: str,
    configuration: dict,
    description: str = "",
) -> dict:
    """Create or update a user's configuration by case-insensitive name."""
    if owner_user_id is None:
        raise ValueError("Sign in before saving a chart configuration.")
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("Enter a name for this chart configuration.")
    if len(clean_name) > 100:
        raise ValueError("Configuration names must be 100 characters or fewer.")
    clean_description = str(description or "").strip()
    if len(clean_description) > 500:
        raise ValueError("Descriptions must be 500 characters or fewer.")

    payload = _serialize_configuration(configuration)
    record = (
        session.query(ChartConfiguration)
        .filter(
            ChartConfiguration.owner_user_id == int(owner_user_id),
            func.lower(ChartConfiguration.name) == clean_name.casefold(),
        )
        .one_or_none()
    )
    created = record is None
    if created:
        record = ChartConfiguration(
            owner_user_id=int(owner_user_id),
            owner_username=str(owner_username or "").strip()[:120] or "unknown",
            name=clean_name,
        )

    record.owner_username = str(owner_username or "").strip()[:120] or "unknown"
    record.name = clean_name
    record.description = clean_description or None
    record.configuration_json = payload
    session.add(record)
    try:
        session.commit()
        session.refresh(record)
    except IntegrityError as exc:
        session.rollback()
        raise ValueError(
            "A configuration with that name already exists for your account."
        ) from exc

    return {
        "id": record.id,
        "name": record.name,
        "description": record.description or "",
        "created": created,
    }


def delete_chart_configuration(
    session: Session,
    owner_user_id: int,
    configuration_id: int,
) -> bool:
    """Delete a saved configuration only when it belongs to the user."""
    record = (
        session.query(ChartConfiguration)
        .filter(
            ChartConfiguration.id == int(configuration_id),
            ChartConfiguration.owner_user_id == int(owner_user_id),
        )
        .one_or_none()
    )
    if record is None:
        return False
    session.delete(record)
    session.commit()
    return True
