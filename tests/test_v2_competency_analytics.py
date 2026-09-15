"""Regression tests for the first static analytics extraction."""

import pandas as pd

from v2.analytics.competency import (
    _get_all_competency_strengths,
    _get_competency_display_name,
    _safe_numeric,
)


def test_safe_numeric_preserves_legacy_conversion_rules():
    assert _safe_numeric("4.4") == 4
    assert _safe_numeric("4.6") == 5
    assert _safe_numeric(None) is None
    assert _safe_numeric("not-a-number") is None


def test_competency_display_name_falls_back_to_code():
    assert _get_competency_display_name("__missing__") == "__missing__"


def test_all_competency_strengths_preserves_gap_and_sort_rules():
    row = pd.Series(
        {
            "B1": 3,
            "R-B1": 4,
            "B2": 5,
            "R-B2": 5,
            "B3": 2,
            "R-B3": 1,
            "B4": None,
            "R-B4": 4,
        }
    )

    result = _get_all_competency_strengths(row, ["B1", "B2", "B3", "B4"])

    assert result["Score"].tolist() == [5, 3, 2]
    assert result["Gap"].tolist() == [0, -1, 1]
    assert result["Gap Status"].tolist() == [
        "Gap Closed",
        "Gap Remaining",
        "Above Target",
    ]
    assert result["Rank"].tolist() == [1, 2, 3]


def test_all_competency_strengths_empty_input_matches_legacy_shape():
    row = pd.Series({"B1": None})
    result = _get_all_competency_strengths(row, ["B1"])

    assert result.empty
    assert result.columns.tolist() == [
        "Rank",
        "Code",
        "Competency",
        "Score",
        "Target",
        "Gap",
        "Gap Status",
    ]
