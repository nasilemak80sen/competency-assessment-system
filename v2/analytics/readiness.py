"""Pure readiness primitives extracted from the legacy application.

Only behaviour whose complete legacy implementation has been verified is
placed here. UI rendering and the remaining readiness aggregation stay in the
legacy reference until their full dependency chain is extracted.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from config import COMPETENCY_FULLNAMES


def grade_rank(sg_value):
    """Convert a salary grade such as ``P4`` into its numeric rank."""
    if sg_value is None:
        return None

    try:
        if pd.isna(sg_value):
            return None
    except (TypeError, ValueError):
        pass

    match = re.fullmatch(r"P(\d+)", str(sg_value).strip().upper())

    if match is None:
        return None

    return int(match.group(1))


def safe_display_value(value, fallback="Not Applicable"):
    """Convert missing profile values into the legacy readable fallback."""
    if value is None:
        return fallback

    try:
        if pd.isna(value):
            return fallback
    except (TypeError, ValueError):
        pass

    cleaned = str(value).strip()

    if cleaned.lower() in {"", "nan", "none", "nat"}:
        return fallback

    return cleaned


def safe_integer_display(value, fallback="Not Applicable"):
    """Display a numeric value as a rounded integer."""
    numeric_value = pd.to_numeric(value, errors="coerce")

    if pd.isna(numeric_value):
        return fallback

    return int(round(float(numeric_value)))


def safe_date_display(value, fallback="Not Applicable"):
    """Format a date using the legacy ``%d %b %Y`` representation."""
    parsed_date = pd.to_datetime(value, errors="coerce")

    if pd.isna(parsed_date):
        return fallback

    return parsed_date.strftime("%d %b %Y")


def assessment_status(gap_value):
    """Classify a competency gap using the legacy thresholds."""
    if pd.isna(gap_value):
        return "Not Assessed"

    if gap_value >= 0:
        return "✅ Met"

    if gap_value >= -1:
        return "🟡 Minor Gap"

    return "🔴 Major Gap"


def build_target_gap_dataframe(
    person_row,
    target_sg,
    selected_ruler_requirements,
    tech_labels,
):
    """Build the target-gap records for the four competency classes.

    This function intentionally stops at the verified transformation stage;
    page-specific presentation remains in the legacy reference until the full
    downstream readiness workflow has been extracted and regression-tested.
    """
    if not target_sg:
        return pd.DataFrame()

    target_requirements = selected_ruler_requirements.get(target_sg, {})

    competency_groups = {
        "Base": [f"B{i}" for i in range(1, 13)],
        "Key": [f"K{i}" for i in range(1, 6)],
        "Pacing": [f"P{i}" for i in range(1, 6)],
        "Emerging": ["E1", "E2"],
    }

    records = []

    for category, competency_codes in competency_groups.items():
        for competency_code in competency_codes:
            if competency_code not in target_requirements:
                continue

            actual_score = pd.to_numeric(
                person_row.get(competency_code),
                errors="coerce",
            )
            target_score = pd.to_numeric(
                target_requirements.get(competency_code),
                errors="coerce",
            )

            gap_score = (
                actual_score - target_score
                if pd.notna(actual_score) and pd.notna(target_score)
                else np.nan
            )

            records.append(
                {
                    "Category": category,
                    "Competency Code": competency_code,
                    "Competency Name": tech_labels.get(
                        competency_code,
                        COMPETENCY_FULLNAMES.get(
                            competency_code,
                            competency_code,
                        ),
                    ),
                    "Actual Score": actual_score,
                    "Target Score": target_score,
                    "Gap": gap_score,
                }
            )

    if not records:
        return pd.DataFrame()

    result = pd.DataFrame(records)
    result["Status"] = result["Gap"].apply(assessment_status)
    return result


_grade_rank = grade_rank
_safe_display_value = safe_display_value
_safe_integer_display = safe_integer_display
_safe_date_display = safe_date_display
_get_assessment_status = assessment_status
_build_target_gap_dataframe = build_target_gap_dataframe
