import numpy as np
import pandas as pd

from v2.analytics.readiness import (
    apply_readiness_personnel_filters,
    build_personnel_readiness_summary,
    build_readiness_detail_dataframe,
    classify_readiness_status,
    recommend_readiness_action,
)


def _ruler():
    return {"BASE": {"P1": {"B1": 3.0, "B2": 4.0}}}


def _people():
    return pd.DataFrame([
        {"id": 1, "Name": "Alice", "Staff ID": "001", "Department": "DPE", "Staff Position": "Staff", "Employment Category": "Permanent", "SG": "P1", "Ruler Type": "BASE", "B1": 3, "B2": 2, "Years in Salary Grade": 2},
        {"id": 2, "Name": "Bob", "Staff ID": "002", "Department": "PSR", "Staff Position": "Staff", "Employment Category": "Contract", "SG": "P1", "Ruler Type": "BASE", "B1": np.nan, "B2": 4, "Years in Salary Grade": 1},
    ])


def test_readiness_detail_preserves_gap_semantics():
    detail = build_readiness_detail_dataframe(_people(), _ruler(), "Current requirement")
    alice = detail[detail["Name"] == "Alice"].set_index("Competency Code")
    assert alice.loc["B1", "Gap"] == 0
    assert bool(alice.loc["B1", "Is Met"])
    assert alice.loc["B2", "Gap"] == -2
    assert bool(alice.loc["B2", "Is Major Gap"])


def test_readiness_summary_calculates_coverage_weighted_and_strict():
    detail = build_readiness_detail_dataframe(_people(), _ruler(), "Current requirement")
    summary = build_personnel_readiness_summary(detail).set_index("Name")
    assert summary.loc["Alice", "Assessment Coverage %"] == 100.0
    assert summary.loc["Alice", "Strict Readiness %"] == 50.0
    assert round(summary.loc["Alice", "Weighted Readiness %"], 6) == round(5 / 7 * 100, 6)
    assert summary.loc["Alice", "Readiness Status"] == "Development Required"


def test_readiness_filters_match_name_staff_department_and_grade():
    result = apply_readiness_personnel_filters(_people(), search_text="002", departments=["PSR"], salary_grades=["P1"])
    assert result["Name"].tolist() == ["Bob"]


def test_readiness_status_rules_are_explicit():
    assert classify_readiness_status(90, 80, 95, 0) == "Ready"
    assert classify_readiness_status(70, 60, 80, 2) == "Near Ready"
    assert classify_readiness_status(70, 60, 30, 0) == "Not Assessed"
    assert recommend_readiness_action("Ready", 95, 0, 0) == "Ready for Assessment"
    assert recommend_readiness_action("Development Required", 90, 3, 0) == "Leadership Review Required"
