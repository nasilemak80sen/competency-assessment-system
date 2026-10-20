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


def test_load_master_data_does_not_invent_full_date_from_year_or_markers(tmp_path):
    import openpyxl
    from data_loader import load_master_data

    path = tmp_path / "assessment_dates.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "All"
    headers = ["Staff ID", "Name", "Last Assesment Date"]
    for col, value in enumerate(headers, 1):
        ws.cell(3, col, value)
    for row, (sid, name, value) in enumerate([
        ("1", "Year Only", "2021"),
        ("2", "Ongoing", "Ongoing"),
        ("3", "TBA", "TBA"),
        ("4", "Full Date", "2021-05-12"),
    ], 4):
        ws.cell(row, 1, sid)
        ws.cell(row, 2, name)
        ws.cell(row, 3, value)
    wb.save(path)

    df = load_master_data(str(path))
    indexed = df.set_index("Name")
    assert pd.isna(indexed.loc["Year Only", "Last Assesment Date"])
    assert indexed.loc["Year Only", "Last Assesment Date Source"] == "2021"
    assert pd.isna(indexed.loc["Ongoing", "Last Assesment Date"])
    assert indexed.loc["Ongoing", "Last Assesment Date Source"] == "Ongoing"
    assert pd.isna(indexed.loc["TBA", "Last Assesment Date"])
    assert indexed.loc["Full Date", "Last Assesment Date"].date().isoformat() == "2021-05-12"
