"""Phase A migration ledger for the legacy app.py function inventory.

The root app.py remains the behavioural reference implementation during the
migration. A function is counted as migrated only when v2 owns a callable
boundary for it and the boundary delegates to the existing implementation
without changing arguments, defaults, validation, persistence semantics, or
return values.
"""

from __future__ import annotations

from dataclasses import dataclass


TOTAL_LEGACY_FUNCTIONS = 75


@dataclass(frozen=True)
class MigrationItem:
    """One function-level migration boundary."""

    legacy: str
    v2_boundary: str
    phase: str = "A"
    status: str = "boundary"
    parity: str = "delegates unchanged"


# Phase A / Batch 1: persistence-facing boundaries already extracted into v2.
# These are intentionally adapters, not rewrites. The legacy implementation
# remains the source of truth until parity tests prove a replacement safe.
PHASE_A_BATCH_1: tuple[MigrationItem, ...] = (
    MigrationItem("add_personnel", "v2.services.personnel_service.add"),
    MigrationItem("update_personnel", "v2.services.personnel_service.update"),
    MigrationItem("delete_personnel", "v2.services.personnel_service.delete"),
    MigrationItem("get_all_personnel", "v2.services.personnel_service.all"),
    MigrationItem("get_personnel_by_id", "v2.services.personnel_service.by_id"),
    MigrationItem("search_personnel", "v2.services.personnel_service.search"),
    MigrationItem("add_assessment", "v2.services.assessment_service.add_assessment"),
    MigrationItem(
        "add_competency_scores",
        "v2.services.assessment_service.add_competency_scores",
    ),
    MigrationItem(
        "bulk_import_from_df",
        "v2.services.import_service.bulk_import_from_dataframe",
    ),
    MigrationItem(
        "bulk_import_cv_list",
        "v2.services.import_service.bulk_import_cv_list",
    ),
)


PHASE_A_MIGRATED_COUNT = len(PHASE_A_BATCH_1)


if PHASE_A_MIGRATED_COUNT > TOTAL_LEGACY_FUNCTIONS:
    raise RuntimeError("Phase A migration count exceeds the legacy inventory")
