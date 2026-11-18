"""Phase 2 assessment management and transaction regression tests."""

import ast
from datetime import date

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from config import SCORE_COLS
from models import Assessment, Base, CompetencyScore, Personnel
from v2.services.assessment_service import (
    get_assessment_history,
    get_assessment_scores,
    save_assessment_transaction,
)


@pytest.fixture
def assessment_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    person = Personnel(
        staff_id="PHASE2-001",
        name="Assessment Test User",
        is_deleted=False,
        is_active=True,
    )
    session.add(person)
    session.commit()
    yield session, person.id
    session.close()
    engine.dispose()


def _valid_scores():
    return {
        code: {"actual": 3.5, "req": 4.0}
        for code in SCORE_COLS
    }


def _assessment_data():
    return {
        "assessment_date": date(2026, 11, 18),
        "assessment_level": "Staff",
        "assessor1": "Assessor A",
        "assessor2": "Assessor B",
        "supervisor": "Supervisor",
        "remarks": "Phase 2 test record",
    }


def test_assessment_header_and_all_competency_scores_commit_together(assessment_session):
    session, personnel_id = assessment_session

    ok, message, assessment_id = save_assessment_transaction(
        session, personnel_id, _assessment_data(), _valid_scores()
    )

    assert ok is True
    assert "24 competency scores" in message
    assert assessment_id is not None
    assessment = session.query(Assessment).filter_by(id=assessment_id).one()
    assert assessment.personnel_id == personnel_id
    assert len(assessment.scores) == len(SCORE_COLS)
    assert session.query(CompetencyScore).filter_by(assessment_id=assessment_id).count() == 24

    person = session.query(Personnel).filter_by(id=personnel_id).one()
    assert person.assessment_level == "Staff"
    assert person.last_assessment_date == date(2026, 11, 18)


def test_score_write_failure_rolls_back_header_scores_and_personnel_summary(assessment_session):
    session, personnel_id = assessment_session

    def reject_competency_scores(session_, flush_context, instances):
        if any(isinstance(item, CompetencyScore) for item in session_.new):
            raise RuntimeError("forced competency insert failure")

    event.listen(session, "before_flush", reject_competency_scores)
    try:
        ok, message, assessment_id = save_assessment_transaction(
            session, personnel_id, _assessment_data(), _valid_scores()
        )
    finally:
        event.remove(session, "before_flush", reject_competency_scores)

    assert ok is False
    assert assessment_id is None
    assert "Transaction rolled back" in message
    assert session.query(Assessment).filter_by(personnel_id=personnel_id).count() == 0
    assert session.query(CompetencyScore).count() == 0
    person = session.query(Personnel).filter_by(id=personnel_id).one()
    assert person.assessment_level is None
    assert person.last_assessment_date is None


def test_incomplete_matrix_is_rejected_before_any_database_write(assessment_session):
    session, personnel_id = assessment_session
    scores = _valid_scores()
    scores.pop(SCORE_COLS[-1])

    ok, message, assessment_id = save_assessment_transaction(
        session, personnel_id, _assessment_data(), scores
    )

    assert ok is False
    assert assessment_id is None
    assert "matrix is incomplete" in message
    assert session.query(Assessment).filter_by(personnel_id=personnel_id).count() == 0


def test_assessment_history_and_saved_matrix_are_readable(assessment_session):
    session, personnel_id = assessment_session
    ok, _, assessment_id = save_assessment_transaction(
        session, personnel_id, _assessment_data(), _valid_scores()
    )
    assert ok is True

    history = get_assessment_history(session, personnel_id)
    saved_scores = get_assessment_scores(session, assessment_id)

    assert len(history) == 1
    assert history[0]["id"] == assessment_id
    assert history[0]["score_count"] == len(SCORE_COLS)
    assert history[0]["assessment_level"] == "Staff"
    assert history[0]["average_actual"] == 3.5
    assert history[0]["average_target"] == 4.0
    assert history[0]["average_gap"] == 0.5
    assert len(saved_scores) == len(SCORE_COLS)
    assert saved_scores["B1"]["actual"] == 3.5
    assert saved_scores["B1"]["req"] == 4.0
    assert saved_scores["B1"]["gap"] == 0.5


def test_phase_two_admin_ui_has_matrix_history_and_one_transactional_save():
    page_path = (
        __file__
        .resolve()
        .parents[1]
        / "v2"
        / "pages"
        / "07_Admin.py"
    )
    source = page_path.read_text(encoding="utf-8")
    ast.parse(source)

    assert "Assessment Management" in source
    assert "Assessment history" in source
    assert "st.data_editor(" in source
    assert "COMPETENCY_FULLNAMES.get(code, code)" in source
    assert "save_assessment_transaction(" in source
    assert "add_assessment(" not in source
    assert "add_competency_scores(" not in source
