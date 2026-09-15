"""Verified readiness primitives extracted from the legacy application.

The root ``app.py`` remains the behavioural reference. Only transformations
whose source behaviour has been inspected are implemented here; UI rendering
and unverified aggregation remain on the reference path for now.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from config import COMPETENCY_FULLNAMES


def grade_rank(sg_value):
    """Convert a salary grade into its numeric rank."""
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
    """Convert missing profile values into a readable fallback."""
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
    """Format a date as ``%d %b %Y``."""
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


_grade_rank = grade_rank
_safe_display_value = safe_display_value
_safe_integer_display = safe_integer_display
_safe_date_display = safe_date_display
_get_assessment_status = assessment_status
