import numpy as np
import pandas as pd

from v2.services.score_gap_analysis_service import (
    build_score_gap_chart_dataframe,
    get_score_gap_chart_fields,
    get_score_gap_target_grades,
)


def _people():
    return pd.DataFrame([
        {
            "Name": "Alice", "Staff ID": "001", "Department": "DPE",
            "Staff Position": "Staff", "Employment Category": "Permanent",
            "SG": "P1", "Ruler Type": "BASE", "B1": 4.0,
            "Years in Salary Grade": 2,
        },
        {
            "Name": "Bob", "Staff ID": "002", "Department": "PSR",
            "Staff Position": "Staff", "Employment Category": "Permanent",
            "SG": "P1", "Ruler Type": "RDP", "B1": 1.0,
            "Years in Salary Grade": 1,
        },
        {
            "Name": "Cara", "Staff ID": "003", "Department": "DPE",
            "Staff Position": "Staff", "Employment Category": "Contract",
            "SG": "P1", "Ruler Type": "BASE", "B1": np.nan,
            "Years in Salary Grade": 3,
        },
    ])


def _rulers():
    return {
        "BASE": {"P1": {"B1": 3.0}, "P2": {"B1": 4.0}},
        "RDP": {"P1": {"B1": 2.0}, "P2": {"B1": 5.0}},
    }


def test_score_gap_uses_person_specific_ruler_and_current_sg():
    detail = build_score_gap_chart_dataframe(_people(), _rulers(), "Current requirement")
    indexed = detail.set_index("Name")

    assert indexed.loc["Alice", "Career Ruler"] == "BASE"
    assert indexed.loc["Alice", "Target SG"] == "P1"
    assert indexed.loc["Alice", "Target Score"] == 3.0
    assert indexed.loc["Alice", "Gap"] == -1.0
    assert indexed.loc["Alice", "Gap Burden"] == 0.0

    assert indexed.loc["Bob", "Career Ruler"] == "RDP"
    assert indexed.loc["Bob", "Target Score"] == 2.0
    assert indexed.loc["Bob", "Gap"] == 1.0
    assert indexed.loc["Bob", "Gap Burden"] == 1.0

    assert pd.isna(indexed.loc["Cara", "Actual Score"])
    assert pd.isna(indexed.loc["Cara", "Gap"])


def test_score_gap_next_grade_uses_next_grade_within_each_ruler():
    detail = build_score_gap_chart_dataframe(_people(), _rulers(), "Next salary grade")
    indexed = detail.set_index("Name")

    assert indexed.loc["Alice", "Target SG"] == "P2"
    assert indexed.loc["Alice", "Target Score"] == 4.0
    assert indexed.loc["Bob", "Target SG"] == "P2"
    assert indexed.loc["Bob", "Target Score"] == 5.0


def test_score_gap_selected_grade_and_target_options_are_available():
    detail = build_score_gap_chart_dataframe(
        _people(), _rulers(), "Selected target grade", "P2"
    )
    indexed = detail.set_index("Name")

    assert indexed.loc["Alice", "Target Score"] == 4.0
    assert indexed.loc["Bob", "Target Score"] == 5.0
    assert get_score_gap_target_grades(_rulers()) == ["P1", "P2"]


def test_score_gap_chart_field_allowlist_is_curated():
    detail = build_score_gap_chart_dataframe(_people(), _rulers(), "Current requirement")
    fields = get_score_gap_chart_fields(detail)

    assert "Actual Score" in fields
    assert "Target Score" in fields
    assert "Gap" in fields
    assert "Career Ruler" in fields
    assert "Current SG" in fields
    assert "Personnel ID" not in fields
    assert "DataFrame Index" not in fields
