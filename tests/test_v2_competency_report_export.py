from __future__ import annotations

from io import BytesIO

import pandas as pd
from openpyxl import Workbook, load_workbook

from v2.services.heatmap_service import (
    get_configured_competency_max_scores,
    filter_personnel_by_competency_threshold,
)
from v2.services.report_export_service import (
    build_competency_report_workbook,
    filter_personnel_for_export,
    get_sub_department_options,
    get_sub_unit_options,
    resolve_organisation_columns,
)


def test_configured_competency_max_scores_are_explicit_and_validated():
    maxima = get_configured_competency_max_scores(
        {"B1": 5, "B4": 4, "B8": 3, "P5": 2, "E2": 2}
    )

    assert maxima == {"B1": 5, "B4": 4, "B8": 3, "P5": 2, "E2": 2}


def test_configured_competency_max_scores_reject_invalid_values():
    import pytest

    with pytest.raises(ValueError, match="whole-number level"):
        get_configured_competency_max_scores({"B1": 5.5})

    with pytest.raises(ValueError, match="Unknown competency code"):
        get_configured_competency_max_scores({"Z9": 5})


def test_missing_maximum_configuration_does_not_infer_caps_from_ruler_targets():
    assert get_configured_competency_max_scores({}) == {}


def test_competency_threshold_filter_is_inclusive_and_ignores_missing_scores():
    frame = pd.DataFrame(
        [
            {"Name": "Low", "Staff ID": "1", "B1": 2},
            {"Name": "Match", "Staff ID": "2", "B1": 4},
            {"Name": "Exact", "Staff ID": "3", "B1": 3},
            {"Name": "Unassessed", "Staff ID": "4", "B1": None},
        ]
    )

    filtered = filter_personnel_by_competency_threshold(frame, "B1", 3, maximum_score=4)

    assert filtered["Name"].tolist() == ["Match", "Exact"]
    assert frame["Name"].tolist() == ["Low", "Match", "Exact", "Unassessed"]


def test_sub_department_and_sub_unit_filters_are_dependent_and_use_current_schema():
    frame = pd.DataFrame(
        [
            {"Name": "A", "Staff ID": "1", "Unit Name": "SBA", "Sub Unit": "Cluster 1", "SG": "P3"},
            {"Name": "B", "Staff ID": "2", "Unit Name": "SBA", "Sub Unit": "Cluster 2", "SG": "P4"},
            {"Name": "C", "Staff ID": "3", "Unit Name": "JVM", "Sub Unit": "Cluster 1", "SG": "P5"},
        ]
    )

    assert resolve_organisation_columns(frame) == ("Unit Name", "Sub Unit")
    assert get_sub_department_options(frame) == ["JVM", "SBA"]
    assert get_sub_unit_options(frame, "SBA") == ["Cluster 1", "Cluster 2"]
    assert get_sub_unit_options(frame, "JVM") == ["Cluster 1"]

    filtered = filter_personnel_for_export(
        frame,
        search="b",
        sub_department="SBA",
        sub_unit="Cluster 2",
        salary_grades=["P4"],
    )
    assert filtered["Name"].tolist() == ["B"]


def test_export_preserves_source_master_headers_and_overlays_current_values(tmp_path):
    source_path = tmp_path / "master.xlsx"
    source_wb = Workbook()
    source_ws = source_wb.active
    source_ws.title = "All"
    source_ws["A1"] = "Original master heading"
    headers = [
        "Name", "Staff ID", "Department", "Section Name", "Unit Name",
        "Sub Unit", "SG", "Current Location:", "Date in Position",
        "Date of Appointment to Current Grade", "Age Promoted to Staff or Principal",
        "Last Assesment Date", "B1", "R-B1", "G-B1",
    ]
    for column, value in enumerate(headers, start=1):
        source_ws.cell(3, column, value)
    source_ws.append([])
    source_ws.append([
        "Workbook Person", 1001, "DPE", "RMS", "SBA", "Cluster 1",
        "P3", "Old assignment", None, None, None, "Old date", 2, 3, 1,
    ])
    source_wb.save(source_path)
    source_wb.close()

    selected = pd.DataFrame(
        [
            {
                "Name": "Workbook Person",
                "Staff ID": "1001",
                "Department": "PSR",
                "Section Name": "RMS",
                "Unit Name": "SBA",
                "Sub Unit": "Cluster 2",
                "SG": "P4",
                "Current Assignment": "Current assignment",
                "Assignment Date": pd.Timestamp("2026-10-01"),
                "SG Start Date": pd.Timestamp("2025-01-01"),
                "Age Promoted": 31,
                "Last Assessment Date": pd.Timestamp("2026-10-15"),
                "B1": 4,
                "R-B1": 3,
                "G--B1": -1,
            },
            {
                "Name": "Database Only Person",
                "Staff ID": "2002",
                "Department": "DPE",
                "Unit Name": "JVM",
                "Sub Unit": "Cluster 9",
                "SG": "P5",
                "B1": 2,
            },
        ]
    )

    content = build_competency_report_workbook(
        source_workbook_path=source_path,
        personnel=selected,
        filters={
            "search": "",
            "sub_department": "All",
            "sub_unit": "All",
            "salary_grades": ["P4", "P5"],
        },
        competency_names={"B1": "Fluid characterisation"},
        maximum_scores={"B1": 5, "P5": 2, "E1": 2},
    )

    exported = load_workbook(BytesIO(content), data_only=True)
    try:
        assert exported.sheetnames == [
            "Personnel Master",
            "Competency Breakdown",
            "Assessment Summary",
            "Report Metadata",
        ]

        master = exported["Personnel Master"]
        assert master["A1"].value == "Original master heading"
        exported_headers = [master.cell(3, column).value for column in range(1, len(headers) + 1)]
        assert exported_headers == headers

        rows_by_id = {
            str(master.cell(row, 2).value): row
            for row in range(4, master.max_row + 1)
        }
        workbook_person_row = rows_by_id["1001"]
        database_person_row = rows_by_id["2002"]
        assert master.cell(workbook_person_row, 3).value == "PSR"
        assert master.cell(workbook_person_row, 6).value == "Cluster 2"
        assert master.cell(workbook_person_row, 7).value == "P4"
        assert master.cell(workbook_person_row, 8).value == "Current assignment"
        assert master.cell(workbook_person_row, 9).value.date().isoformat() == "2026-10-01"
        assert master.cell(workbook_person_row, 10).value.date().isoformat() == "2025-01-01"
        assert master.cell(workbook_person_row, 11).value == 31
        assert master.cell(workbook_person_row, 12).value == pd.Timestamp("2026-10-15").to_pydatetime()
        assert master.cell(workbook_person_row, 13).value == 4
        assert master.cell(workbook_person_row, 15).value == -1
        assert master.cell(database_person_row, 1).value == "Database Only Person"
        assert master.cell(database_person_row, 5).value == "JVM"
        assert master.cell(database_person_row, 8).value == 2

        breakdown = exported["Competency Breakdown"]
        assert breakdown["H2"].value == "Fluid characterisation"
        assert breakdown["I2"].value == 4
        assert breakdown["J2"].value == 5
        assert breakdown["K2"].value == 3
        assert breakdown["L2"].value == -1

        summary = exported["Assessment Summary"]
        assert summary["A1"].value == "PERSONNEL ASSESSMENT SUMMARY"
        assert summary["A2"].value == "Name"
        assert summary.max_row > 4

        metadata = exported["Report Metadata"]
        assert metadata["A1"].value == "Competency Report Export"
        assert metadata["A3"].value == "Selected Personnel"
        assert metadata["B3"].value == 2
    finally:
        exported.close()


def test_export_rejects_empty_personnel_selection():
    try:
        build_competency_report_workbook(
            source_workbook_path="missing.xlsx",
            personnel=pd.DataFrame(),
        )
    except ValueError as exc:
        assert "Select at least one" in str(exc)
    else:
        raise AssertionError("An empty export selection must be rejected.")
