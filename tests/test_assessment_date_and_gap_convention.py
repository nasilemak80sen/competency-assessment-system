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
    headers = ["Staff ID", "SG", "Last Assesment Date", "Staff Position", "Name"]
    for col, value in enumerate(headers, 1):
        ws.cell(3, col, value)
    for row, (sid, name, value) in enumerate([
        ("1", "Year Only", "2021"),
        ("2", "Ongoing", "Ongoing"),
        ("3", "TBA", "TBA"),
        ("4", "Full Date", "2021-05-12"),
    ], 4):
        ws.cell(row, 1, sid)
        ws.cell(row, 5, name)
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

 
def test_importer_preserves_date_markers_in_assessment_remarks():
    row = pd.Series({
        "Remarks": "Original remark",
        "Last Assesment Date": pd.NaT,
        "Last Assesment Date Source": "TBA",
    })
    assert db_ops._assessment_source_remarks(row) == "Original remark\nSource Last Assesment Date field: TBA"


def test_runtime_database_uses_validated_rebuilt_file():
    import sqlite3

    from config import BASE_DIR, DATABASE_PATH, DATABASE_URL

    expected_path = (BASE_DIR / "re_competency_rebuilt.db").resolve()
    assert DATABASE_PATH == expected_path
    assert DATABASE_URL == f"sqlite:///{expected_path.as_posix()}"
    assert DATABASE_PATH.is_file(), f"Configured database is missing: {DATABASE_PATH}"

    with sqlite3.connect(DATABASE_PATH) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "personnel",
            "assessments",
            "competency_scores",
            "summary_scores",
            "cv_documents",
        }.issubset(tables)
        assert connection.execute("SELECT COUNT(*) FROM personnel").fetchone()[0] > 0

def test_load_ruler_accepts_trailing_underscore_sheet_name(tmp_path):
    import openpyxl

    from config import SCORE_COLS
    from data_loader import load_ruler_and_tech_mapping

    workbook_path = tmp_path / "ruler_alias.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Ruler_"

    # Match the source workbook: competency headers begin in column E,
    # ruler type is column B, SG is column C, and type labels are group headers.
    for column, header in enumerate(SCORE_COLS, start=5):
        sheet.cell(row=4, column=column, value=header)

    rows = [
        (None, "P1", "Junior Executive"),
        (None, "P2", "Executive"),
        ("RDP", "P3", "Senior Executive"),
        (None, "P4", "Senior RE"),
        ("RMS", "P3", "Senior Executive"),
        (None, "P4", "Senior RE"),
        ("RSS", "P3", "Senior Executive"),
        (None, "P4", "Senior RE"),
    ]
    for row_number, (ruler_type, sg, position) in enumerate(rows, start=5):
        if ruler_type is not None:
            sheet.cell(row=row_number, column=2, value=ruler_type)
        sheet.cell(row=row_number, column=3, value=sg)
        sheet.cell(row=row_number, column=4, value=position)
        for column in range(5, 5 + len(SCORE_COLS)):
            sheet.cell(row=row_number, column=column, value=2)

    workbook.save(workbook_path)
    workbook.close()

    ruler_map, _ = load_ruler_and_tech_mapping(str(workbook_path))

    assert {"BASE", "RDP", "RMS", "RSS"}.issubset(ruler_map)
    assert set(ruler_map["BASE"]) == {"P1", "P2"}
    assert set(ruler_map["RDP"]) == {"P3", "P4"}
    assert set(ruler_map["RMS"]) == {"P3", "P4"}
    assert set(ruler_map["RSS"]) == {"P3", "P4"}
    assert ruler_map["RDP"]["P3"]["B1"] == 2.0
    assert ruler_map["RDP"]["P4"]["B1"] == 2.0

