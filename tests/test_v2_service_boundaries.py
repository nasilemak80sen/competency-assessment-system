"""Phase A regression tests for v2 service boundaries.

These tests intentionally verify delegation rather than re-testing db_ops.
The point of Phase A is to move the call boundary without changing the
underlying business rules.
"""

from unittest.mock import Mock

from v2.core.migration_manifest import (
    PHASE_A_BATCH_1,
    PHASE_A_MIGRATED_COUNT,
    TOTAL_LEGACY_FUNCTIONS,
)
from v2.services import assessment_service, import_service, personnel_service


def test_phase_a_batch_is_explicit_and_within_inventory():
    assert TOTAL_LEGACY_FUNCTIONS == 75
    assert PHASE_A_MIGRATED_COUNT == 10
    assert len(PHASE_A_BATCH_1) == PHASE_A_MIGRATED_COUNT
    assert len({item.legacy for item in PHASE_A_BATCH_1}) == PHASE_A_MIGRATED_COUNT


def test_personnel_service_delegates_without_reimplementing_rules(monkeypatch):
    session = object()
    payload = {"staff_id": "123"}
    expected = (True, "ok", 7)
    delegate = Mock(return_value=expected)
    monkeypatch.setattr(personnel_service.db_ops, "add_personnel", delegate)

    assert personnel_service.add(session, payload) == expected
    delegate.assert_called_once_with(session, payload)


def test_assessment_service_delegates_without_reimplementing_rules(monkeypatch):
    session = object()
    expected = (True, "ok")
    delegate = Mock(return_value=expected)
    monkeypatch.setattr(assessment_service.db_ops, "add_competency_scores", delegate)

    scores = {"B1": {"score": 3}}
    assert assessment_service.add_competency_scores(session, 4, 9, scores) == expected
    delegate.assert_called_once_with(session, 4, 9, scores)


def test_import_service_delegates_without_reimplementing_rules(monkeypatch):
    session = object()
    raw_df = object()
    ruler_map = object()
    expected = {"imported": 10}
    delegate = Mock(return_value=expected)
    monkeypatch.setattr(import_service, "db_ops", Mock(bulk_import_from_df=delegate))

    assert (
        import_service.bulk_import_from_dataframe(
            session,
            raw_df,
            ruler_map=ruler_map,
        )
        == expected
    )
    delegate.assert_called_once_with(session, raw_df, ruler_map=ruler_map)
