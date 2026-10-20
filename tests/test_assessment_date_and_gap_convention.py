import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from analytics import gap_analysis_individual, gap_summary
from models import Assessment, Base, Personnel
import db_ops


def test_assessment_date_is_nullable_and_add_assessment_accepts_missing_date():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    person = Personnel(staff_id="TEST-UNDATED", name="Undated Person", is_deleted=False)
    session.add(person)
    session.commit()

    ok, _, assessment_id = db_ops.add_assessment(
        session, person.id, {"assessment_date": None, "remarks": "Source date: TBA"}
    )

    assert ok is True
    assessment = session.get(Assessment, assessment_id)
    assert assessment is not None
    assert assessment.assessment_date is None
    assert assessment.remarks == "Source date: TBA"


def test_workbook_gap_convention_counts_positive_values_as_shortfalls():
    frame = pd.DataFrame([
        {"Name": "Shortfall", "G--B1": 1.0, "G--B2": 2.0},
        {"Name": "Meets", "G--B1": 0.0, "G--B2": -1.0},
    ])

    result = gap_summary(frame).set_index("Name")
    assert result.loc["Shortfall", "Gaps Count"] == 2
    assert result.loc["Shortfall", "Gap Status"] == ">1 Gap"
    assert result.loc["Meets", "Gaps Count"] == 0
    assert result.loc["Meets", "Gap Status"] == "No Gap"


def test_future_grade_gap_uses_requirement_minus_actual():
    row = pd.Series({"B1": 2.0})
    result = gap_analysis_individual(
        row,
        ruler_requirements={"P4": {"B1": 3.0}},
        current_sg="P3",
        include_future_grades=True,
    )
    future = result[result["Target Grade"] == "P4"].iloc[0]
    assert future["Gap"] == 1.0
    assert future["Status"] == "Minor Gap"
