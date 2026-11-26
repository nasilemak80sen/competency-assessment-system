from datetime import date

import openpyxl
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config import SCORE_COLS
from models import (
    Assessment,
    AssessmentImportBatch,
    Base,
    CompetencyScore,
    Personnel,
)
from v2.services.assessment_import_service import (
    _parse_pdf_text,
    parse_assessment_upload,
)
from v2.services.assessment_service import (
    apply_reviewed_assessment_import,
    create_reviewed_assessment_import,
    get_assessment_history,
    get_assessment_scores,
)


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)(), engine


def _sample_workbook_bytes():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "SMA 2025"
    sheet.append(["NAME", "Example Reservoir Engineer"])
    sheet.append(["STAFFID", "TEST-1101"])
    sheet.append(["Assessment Date:", "08-Jun-2026"])
    sheet.append(["SMA 2025"])
    sheet.append([
        "B1 - Fluid Characterisation",
        "Self Rating:", 3,
        "Final Rating:", 4,
        "Assessor / Superior Comments:", "",
        "Assessor's Approval", "Superior's Approval",
    ])
    sheet.append([
        "- Delivered PVT modelling and fluid characterisation work.",
        "", "", "", "",
        "Assessor Name, Rating & Comments: Assessor A. Rating 4. Comments: Strong evidence.",
        "", "Reviewed", "Approved",
    ])
    sheet.append([
        "", "", "", "", "",
        "Superior's comments: Evidence and final rating were reviewed.",
    ])
    sheet.append([
        "B2 - Rock Properties",
        "Self Rating:", 2,
        "Final Rating:", 3,
        "Assessor / Superior Comments:", "",
        "Assessor's Approval", "Superior's Approval",
    ])
    sheet.append(["- RCA and SCAL analysis evidence."])
    from io import BytesIO

    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_excel_parser_extracts_competency_scores_evidence_and_metadata():
    parsed = parse_assessment_upload(
        "assessment.xlsx",
        _sample_workbook_bytes(),
    )

    assert parsed["recognized_count"] == 2
    assert parsed["valid_final_count"] == 2
    assert parsed["metadata"]["person_name"] == "Example Reservoir Engineer"
    assert parsed["metadata"]["staff_id"] == "TEST-1101"
    assert parsed["metadata"]["assessment_date"] == date(2026, 6, 8).isoformat()
    assert parsed["metadata"]["assessment_type"] == "SMA 2025"

    by_code = {row["code"]: row for row in parsed["competencies"]}
    assert by_code["B1"]["self_rating"] == 3.0
    assert by_code["B1"]["final_rating"] == 4.0
    assert "PVT modelling" in by_code["B1"]["evidence"]
    assert "Strong evidence" in by_code["B1"]["assessor_comments"]
    assert "reviewed" in by_code["B1"]["superior_comments"].casefold()
    assert by_code["B2"]["final_rating"] == 3.0
    assert "B3" in parsed["missing_codes"]


def test_parser_resolves_exact_competency_name_without_tag():
    text = (
        "Fluid Characterisation\tSelf Rating:\t2\tFinal Rating:\t3\n"
        "- Evidence of PVT modelling.\n"
    )
    parsed = parse_assessment_upload("assessment.txt", text.encode("utf-8"))

    assert parsed["recognized_count"] == 1
    assert parsed["competencies"][0]["code"] == "B1"
    assert parsed["competencies"][0]["final_rating"] == 3.0


def test_pdf_text_parser_extracts_inline_ratings_and_comments():
    text = """SMA 2025
B1 - Fluid Characterisation Self Rating: 3 Final Rating: 4 Assessor / Superior Comments:
Evidence of PVT modelling and MMP work.
Assessor Name, Rating & Comments: Assessor A. Rating 4. Comments: Strong evidence.
Superior's comments: Reviewed and accepted.
B2 - Rock Properties Self Rating: 2 Final Rating: 3
RCA and SCAL analysis.
"""
    parsed = _parse_pdf_text(text)
    by_code = {row["code"]: row for row in parsed["competencies"]}

    assert by_code["B1"]["self_rating"] == 3.0
    assert by_code["B1"]["final_rating"] == 4.0
    assert "PVT modelling" in by_code["B1"]["evidence"]
    assert "Strong evidence" in by_code["B1"]["assessor_comments"]
    assert "Reviewed" in by_code["B1"]["superior_comments"][0]
    assert by_code["B2"]["final_rating"] == 3.0


def test_duplicate_competency_sections_are_flagged_and_not_selected():
    text = (
        "B1 - Fluid Characterisation\tSelf Rating:\t2\tFinal Rating:\t2\n"
        "- First B1 evidence.\n"
        "B1 - Fluid Characterisation\tSelf Rating:\t3\tFinal Rating:\t3\n"
        "- Second B1 evidence.\n"
    )
    parsed = parse_assessment_upload("duplicate.txt", text.encode("utf-8"))

    assert parsed["recognized_count"] == 0
    assert any("Duplicate competency section B1" in issue for issue in parsed["issues"])


def test_review_approval_creates_complete_matrix_and_preserves_source_fields():
    session, engine = _session()
    try:
        person = Personnel(
            staff_id="TEST-1101",
            name="Example Reservoir Engineer",
            is_deleted=False,
            is_active=True,
        )
        session.add(person)
        session.commit()

        batch_id = create_reviewed_assessment_import(
            session,
            personnel_id=person.id,
            operation="create",
            target_assessment_id=None,
            source_filename="assessment.xlsx",
            source_sha256="a" * 64,
            payload={
                "metadata": {
                    "assessment_date": "2026-06-08",
                    "assessment_level": "Staff",
                    "assessment_type": "SMA 2025",
                    "assessor1": "Assessor A",
                    "remarks": None,
                },
                "scores": {
                    "B1": {
                        "self_rating": 3,
                        "final_rating": 4,
                        "req": 3,
                        "evidence": "PVT modelling work.",
                        "assessor_comments": "Strong technical evidence.",
                        "superior_comments": "Reviewed.",
                    },
                    "B2": {
                        "self_rating": 2,
                        "final_rating": 3,
                        "req": 4,
                        "evidence": "RCA and SCAL evidence.",
                    },
                },
            },
            actor={"username": "reviewer"},
        )
        batch = session.get(AssessmentImportBatch, batch_id)
        assert batch.status == "reviewed"

        ok, message, assessment_id = apply_reviewed_assessment_import(
            session,
            batch_id,
            actor={"username": "approver"},
        )

        assert ok is True
        assert assessment_id is not None
        assessment = session.get(Assessment, assessment_id)
        assert assessment.assessment_date == date(2026, 6, 8)
        assert assessment.assessment_type == "SMA 2025"
        assert assessment.assessor1 == "Assessor A"
        assert len(assessment.scores) == len(SCORE_COLS)
        by_code = {row.competency_code: row for row in assessment.scores}
        assert by_code["B1"].actual_score == 4
        assert by_code["B1"].self_rating == 3
        assert by_code["B1"].gap_score == 0
        assert by_code["B1"].evidence == "PVT modelling work."
        assert by_code["B1"].assessor_comments == "Strong technical evidence."
        assert by_code["B2"].actual_score == 3
        assert by_code["B2"].gap_score == 1
        assert by_code["B3"].actual_score is None
        assert session.get(AssessmentImportBatch, batch_id).status == "approved"
        history = get_assessment_history(session, person.id)
        assert history[0]["score_count"] == 2
        assert history[0]["matrix_count"] == 24

        approved_again, _, _ = apply_reviewed_assessment_import(session, batch_id)
        assert approved_again is False
    finally:
        session.close()
        engine.dispose()


def test_revision_updates_only_imported_ratings_and_keeps_unmentioned_values():
    session, engine = _session()
    try:
        person = Personnel(
            staff_id="TEST-1102",
            name="Revision Test Person",
            is_deleted=False,
            is_active=True,
        )
        session.add(person)
        session.flush()
        assessment = Assessment(
            personnel_id=person.id,
            assessment_date=date(2025, 6, 1),
            assessment_level="Staff",
            assessment_type="SMA",
        )
        session.add(assessment)
        session.flush()
        session.add_all([
            CompetencyScore(
                assessment_id=assessment.id,
                personnel_id=person.id,
                competency_code="B1",
                competency_type="B",
                actual_score=2,
                requirement_score=3,
                gap_score=1,
            ),
            CompetencyScore(
                assessment_id=assessment.id,
                personnel_id=person.id,
                competency_code="B2",
                competency_type="B",
                actual_score=3,
                requirement_score=4,
                gap_score=1,
                evidence="Original B2 evidence",
            ),
        ])
        session.commit()

        batch_id = create_reviewed_assessment_import(
            session,
            personnel_id=person.id,
            operation="revise",
            target_assessment_id=assessment.id,
            source_filename="corrected_assessment.xlsx",
            source_sha256="b" * 64,
            payload={
                "metadata": {"assessment_date": "2025-06-01"},
                "scores": {
                    "B1": {"final_rating": 4, "self_rating": 3, "req": 3},
                    "B2": {"evidence": "Revised B2 evidence"},
                },
            },
            actor={"username": "reviewer"},
        )
        ok, _, revised_id = apply_reviewed_assessment_import(
            session, batch_id, actor={"username": "approver"}
        )

        assert ok is True
        assert revised_id == assessment.id
        scores = get_assessment_scores(session, assessment.id)
        assert scores["B1"]["actual"] == 4
        assert scores["B1"]["gap"] == 0
        assert scores["B2"]["actual"] == 3
        assert scores["B2"]["evidence"] == "Revised B2 evidence"
    finally:
        session.close()
        engine.dispose()
