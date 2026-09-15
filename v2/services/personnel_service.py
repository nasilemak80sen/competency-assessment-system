"""Personnel service boundary.

This adapter deliberately delegates to the existing db_ops implementation.
No validation, defaults, soft-delete rules, or persistence semantics are
changed during the first migration pass.
"""

from typing import Any, Dict, Optional, Tuple

import pandas as pd

import db_ops


def add(session, data: Dict[str, Any]) -> Tuple[bool, str, Optional[int]]:
    return db_ops.add_personnel(session, data)


def update(session, personnel_id: int, data: Dict[str, Any]) -> Tuple[bool, str]:
    return db_ops.update_personnel(session, personnel_id, data)


def delete(session, personnel_id: int) -> Tuple[bool, str]:
    return db_ops.delete_personnel(session, personnel_id)


def all(session, include_deleted: bool = False) -> pd.DataFrame:
    return db_ops.get_all_personnel(session, include_deleted=include_deleted)


def by_id(session, personnel_id: int):
    return db_ops.get_personnel_by_id(session, personnel_id)


def search(session, term: str):
    return db_ops.search_personnel(session, term)
