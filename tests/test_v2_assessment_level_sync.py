"""Regression coverage for assessment-level CRUD synchronization."""
from datetime import date

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db_ops
from models import Assessment, Base, Personnel
from v2.core.bootstrap import _overlay_database_assessment_levels


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_database_assessment_level_overlays_workbook_value_by_staff_id():
    workbook = pd.DataFrame(
        [
            {"Staff ID": "1001", "Name": "Person One", "Assessment Level": "UPE"},
            {"Staff ID": "1002", "Name": "Person Two", "Assessment Level": "Staff"},
            {"Staff ID": "1003", "Name": "Person Three", "Assessment Level": "Principal"},
        ]
    )
    stored = [
        ("1001", "Person One", "Staff"),
        ("1002", "Person Two", None),
    ]

    result = _overlay_database_assessment_levels(workbook, stored)

    assert result.loc[0, "Assessment Level"] == "Staff"
    # A database NULL is a saved "Not specified" value, not a reason to fall
    # back to an older workbook value.
    assert pd.isna(result.loc[1, "Assessment Level"])
    # Records not yet present in SQLite continue to use the workbook baseline.
    assert result.loc[2, "Assessment Level"] == "Principal"
    assert workbook.loc[0, "Assessment Level"] == "UPE"


def test_update_personnel_keeps_latest_assessment_level_and_date_in_sync():
    session = _session()
    try:
        person = Personnel(staff_id="1001", name="Person One", assessment_level="UPE")
        person.assessments = [
            Assessment(
                assessment_date=date(2025, 1, 1),
                assessment_level="Staff",
            ),
            Assessment(
                assessment_date=date(2026, 1, 1),
                assessment_level="UPE",
            ),
        ]
        session.add(person)
        session.commit()

        ok, _ = db_ops.update_personnel(
            session,
            person.id,
            {
                "assessment_level": "Principal",
                "last_assessment_date": date(2026, 2, 15),
            },
        )

        session.refresh(person)
        latest = (
            session.query(Assessment)
            .filter_by(personnel_id=person.id)
            .order_by(Assessment.assessment_date.desc(), Assessment.id.desc())
            .first()
        )
        older = (
            session.query(Assessment)
            .filter_by(personnel_id=person.id, assessment_date=date(2025, 1, 1))
            .one()
        )

        assert ok
        assert person.assessment_level == "Principal"
        assert person.last_assessment_date == date(2026, 2, 15)
        assert latest.assessment_level == "Principal"
        assert latest.assessment_date == date(2026, 2, 15)
        assert older.assessment_level == "Staff"
    finally:
        session.close()


def test_creating_assessment_updates_personnel_summary_fields():
    session = _session()
    try:
        person = Personnel(staff_id="1001", name="Person One", assessment_level="UPE")
        session.add(person)
        session.commit()

        ok, _, assessment_id = db_ops.add_assessment(
            session,
            person.id,
            {
                "assessment_date": date(2026, 3, 1),
                "assessment_level": "TPCP",
            },
        )

        session.refresh(person)
        assessment = session.query(Assessment).filter_by(id=assessment_id).one()

        assert ok
        assert assessment.assessment_level == "TPCP"
        assert person.assessment_level == "TPCP"
        assert person.last_assessment_date == date(2026, 3, 1)
    finally:
        session.close()
