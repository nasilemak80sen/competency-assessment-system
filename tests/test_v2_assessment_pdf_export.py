from __future__ import annotations

import zipfile
from io import BytesIO

import pandas as pd

from v2.services.assessment_report_service import (
    build_assessment_report_data,
    build_personnel_assessment_pdf,
)


def _person():
    return pd.Series({
        "Name": "Alex Example",
        "Staff ID": "10001",
        "Staff Position": "Senior Executive",
        "SG": "P3",
        "Department": "DPE",
        "Section Name": "RMS",
        "Unit Name": "SBA",
        "Sub Unit": "Cluster 1",
        "Nationality": "Malaysia",
        "Employment Category": "Permanent",
        "Ruler Type": "RDP",
        "Strength": "Reservoir modelling",
        "Interest": "EOR",
        "Background": "Reservoir Engineering",
        "Potential": "Technical specialist",
        "Recommendation": "Advanced reservoir studies",
        "Assessment Level": "Staff",
        "B1": 4,
        "B2": 1,
        "R-B1": 3,
        "R-B2": 3,
        "G--B1": -1,
        "G--B2": 2,
    })


def _rulers():
    return {
        "RDP": {
            "P4": {"B1": 3, "B2": 3},
            "P5": {"B1": 4, "B2": 4},
        }
    }


def test_pdf_report_data_reuses_individual_assessment_target_logic_and_history():
    person = _person()
    history = [
        {"date": "2025-01-01", "type": "B", "actual": 2},
        {"date": "2025-06-01", "type": "B", "actual": 3},
        {"date": "2026-01-01", "type": "B", "actual": 4},
    ]
    report = build_assessment_report_data(
        person,
        _rulers(),
        history=history,
        summary={"staff_base": 75.0},
        target_mode="Next salary grade",
    )

    assert report["career_ruler"] == "RDP"
    assert report["target"] == "P4"
    assert report["metrics"]["total"] == 2
    assert report["metrics"]["met"] == 1
    assert report["metrics"]["major"] == 1
    assert len(report["future_gap"]) == 2 * 24
    assert len(report["history"]) == 3
    assert report["summary"]["staff_base"] == 75.0


def test_pdf_report_builder_creates_a_pdf_with_personnel_assessment_content():
    pdf = build_personnel_assessment_pdf(
        _person(),
        _rulers(),
        history=[
            {"date": "2025-01-01", "type": "B", "actual": 2},
            {"date": "2026-01-01", "type": "B", "actual": 4},
        ],
        summary={"staff_base": 75.0, "principal_base": 61.0},
    )

    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 4000


def test_pdf_report_can_be_created_when_no_ruler_or_gap_is_available():
    person = _person()
    person["Ruler Type"] = "UNKNOWN"
    pdf = build_personnel_assessment_pdf(person, {}, history=[], summary=None)
    assert pdf.startswith(b"%PDF-")
    assert len(pdf) > 1500


def test_admin_export_page_offers_pdf_reports_for_the_selected_personnel():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "v2"
        / "pages"
        / "12_Admin_Competency_Report_Export.py"
    ).read_text(encoding="utf-8")

    assert "build_personnel_assessment_pdf(" in source
    assert "get_ruler_data()" in source
    assert "database_person.assessments" in source
    assert "SummaryScore" in source
    assert "Download PDF report (.pdf)" in source
    assert "Download PDF reports (.zip)" in source
    assert "zipfile.ZipFile" in source
    assert "history=history" in source
