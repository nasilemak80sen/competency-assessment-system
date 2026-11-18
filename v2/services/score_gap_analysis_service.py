"""Chart-ready competency score and requirement analysis."""
from __future__ import annotations

import pandas as pd

from v2.analytics.readiness import (
    _rg_sort_salary_grades,
    build_readiness_detail_dataframe,
)


SCORE_GAP_CHART_FIELD_GROUPS = {
    "Personnel": (
        "Name", "Staff ID", "Department", "Staff Position", "Employment Category",
    ),
    "Career & requirements": (
        "Current SG", "Career Ruler", "Target SG", "Years in Grade",
    ),
    "Competency": (
        "Competency Code", "Competency Name", "Category",
    ),
    "Scoring measures": (
        "Actual Score", "Target Score", "Gap", "Gap Burden", "Capped Actual",
    ),
    "Assessment status": (
        "Gap Severity", "Is Assessed", "Is Met", "Is Major Gap", "Is Minor Gap",
    ),
}


def get_score_gap_target_grades(ruler_map: dict) -> list[str]:
    """Return the sorted union of grades present across all Career Rulers."""
    if not isinstance(ruler_map, dict) or not ruler_map:
        return []
    return _rg_sort_salary_grades(
        grade
        for requirements in ruler_map.values()
        if isinstance(requirements, dict)
        for grade in requirements.keys()
    )


def get_score_gap_chart_fields(dataframe: pd.DataFrame) -> list[str]:
    """Return populated, curated fields from the person-competency detail frame."""
    if dataframe is None or dataframe.empty:
        return []
    return [
        column
        for group_fields in SCORE_GAP_CHART_FIELD_GROUPS.values()
        for column in group_fields
        if column in dataframe.columns and dataframe[column].notna().any()
    ]


def build_score_gap_chart_dataframe(
    personnel_dataframe: pd.DataFrame,
    ruler_map: dict,
    requirement_mode: str = "Current requirement",
    selected_target_sg: str | None = None,
) -> pd.DataFrame:
    """Build one row per person/competency using the authoritative ruler resolver.

    Gap is signed (target minus actual): positive means shortfall, zero means
    requirement met, negative means the score exceeds target. Gap Burden stays
    non-negative for shortfall-only prioritisation. Missing actual scores keep
    a null Gap instead of being counted as zero.
    """
    if personnel_dataframe is None or personnel_dataframe.empty:
        return pd.DataFrame()
    if not isinstance(ruler_map, dict) or not ruler_map:
        return pd.DataFrame()
    detail = build_readiness_detail_dataframe(
        personnel_dataframe,
        ruler_map,
        requirement_mode,
        selected_target_sg,
    )
    return detail.copy() if isinstance(detail, pd.DataFrame) else pd.DataFrame()
