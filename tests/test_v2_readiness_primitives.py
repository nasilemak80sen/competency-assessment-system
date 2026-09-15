"""Regression tests for verified readiness primitives."""

import pandas as pd

from v2.analytics.readiness import (
    _get_assessment_status,
    _grade_rank,
    _safe_date_display,
    _safe_display_value,
    _safe_integer_display,
)


def test_grade_rank_preserves_salary_grade_parsing():
    assert _grade_rank("P1") == 1
    assert _grade_rank("p10") == 10
    assert _grade_rank(None) is None
    assert _grade_rank("Senior") is None


def test_display_helpers_preserve_missing_value_rules():
    assert _safe_display_value(None) == "Not Applicable"
    assert _safe_display_value("  None ") == "Not Applicable"
    assert _safe_display_value(" Reservoir Engineering ") == "Reservoir Engineering"
    assert _safe_integer_display("4.6") == 5
    assert _safe_integer_display("bad") == "Not Applicable"
    assert _safe_date_display("2026-08-10") == "10 Aug 2026"
    assert _safe_date_display("bad") == "Not Applicable"


def test_assessment_status_preserves_gap_thresholds():
    assert _get_assessment_status(float("nan")) == "Not Assessed"
    assert _get_assessment_status(0) == "✅ Met"
    assert _get_assessment_status(2) == "✅ Met"
    assert _get_assessment_status(-1) == "🟡 Minor Gap"
    assert _get_assessment_status(-2) == "🔴 Major Gap"
