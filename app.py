"""
app.py - DPE | Reservoir Engineering Talent Profile
Run with: streamlit run app.py
"""

# =============================================================================
# STANDARD LIBRARY
# =============================================================================

from datetime import date, datetime
from pathlib import Path
import os
import re
import tempfile
import time
import config


# =============================================================================
# THIRD-PARTY PACKAGES
# =============================================================================

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pycountry
import streamlit as st
import streamlit.components.v1 as components

print("Streamlit:", st.__version__)

# =============================================================================
# APPLICATION CONFIGURATION
# =============================================================================

from config import (
    APP_TITLE,
    ASSESSMENT_LEVELS,
    CHAT_STATUS_OPTIONS,
    COMPETENCY_FULLNAMES,
    COMP_TYPES,
    COUNTRY_COORDINATES,
    CV_ALLOWED_FILE_TYPES,
    CV_COLUMNS_MAP,
    CV_LIST_SHEET,
    DATABASE_URL,
    DEPARTMENTS,
    EXCEL_PATH,
    GAP_COLS,
    GRADE_LABELS,
    HEATMAP_COLORSCALE,
    NATIONALITY_ALIASES,
    POSITIONS,
    PRIMARY,
    REQ_COLS,
    SCORE_COLS,
    SECONDARY,
    SUMMARY_GROUPS,
    USE_LIVE_EXCEL_SOURCE,POSITION_RANK, POSITION_TO_SG, SG_HIERARCHY, SG_RANK
)


# =============================================================================
# DATABASE AND DATA ACCESS
# =============================================================================

from models import (
    Assessment,
    Base,
    Personnel,
    SummaryScore,
    get_session,
    init_db,
)

from data_loader import (
    load_cv_list,
    load_master_data,
    load_ruler_and_tech_mapping,
)

import db_ops


# =============================================================================
# ANALYTICS AND VISUALIZATION MODULES
# =============================================================================

import analytics as an

from chart_builder import (
    ChartBuilder,
    ChartCompatibility,
    DataElementInfo,
)

# ============================================================================
# ASSESSMENT-BASED TALENT STRENGTH
# ============================================================================
#
# Purpose:
#   Automatically identify the strongest competencies for the selected
#   personnel based on their assessed competency scores.
#
# Competency classes are sourced directly from COMP_TYPES:
#   B = Base Competency
#   K = Knowledge
#   P = Pacing
#   E = Emerging
#
# This prevents the Talent Profile from maintaining a separate competency
# mapping from the Competency Heatmap.
# ============================================================================

from io import BytesIO


def plotly_figure_to_png(
    figure,
    width=1400,
    height=800,
    scale=2,
):
    """
    Convert a Plotly figure into PNG bytes for PDF inclusion.
    """
    if figure is None:
        return None

    try:
        image_bytes = figure.to_image(
            format="png",
            width=width,
            height=height,
            scale=scale,
            engine="kaleido",
        )

        return BytesIO(
            image_bytes
        )

    except Exception as exc:
        print(
            f"Unable to export Plotly chart: {exc}"
        )

        return None

def _safe_numeric(value):
    """
    Safely convert a value to a numeric float.

    Returns None when the value is missing or invalid.
    """
    try:
        value = pd.to_numeric(value, errors="coerce")

        if pd.isna(value):
            return None

        return int(round(value))

    except Exception:
        return None

def _get_competency_display_name(code, competency_labels=None):
    """Return the display label, honoring an optional caller-supplied mapping."""
    labels = competency_labels or COMPETENCY_FULLNAMES
    return labels.get(
        code,
        COMPETENCY_FULLNAMES.get(code, code),
    )
  
def _get_top_competency_strengths(
    person_row,
    competency_codes,
    competency_labels=None,
    top_n=3,
):
    """
    Get the highest-scoring competencies for a personnel.

    Parameters
    ----------
    person_row:
        Selected personnel pandas Series.

    competency_codes:
        List of competency score columns, e.g. B1-B12.

    competency_labels:
        Optional mapping of competency codes to display names.

    top_n:
        Number of top strengths to return.

    Returns
    -------
    pandas.DataFrame
    """

    results = []

    if person_row is None:
        return pd.DataFrame()

    for code in competency_codes:

        # Make sure the competency exists in the personnel record
        if code not in person_row.index:
            continue

        score = _safe_numeric(
            person_row.get(code)
        )

        # Ignore unassessed / invalid scores
        if score is None:
            continue

        results.append(
            {
                "Code": code,
                "Competency": _get_competency_display_name(
                    code,
                    competency_labels,
                ),
                "Score": score,
            }
        )

    if not results:
        return pd.DataFrame(
            columns=[
                "Rank",
                "Code",
                "Competency",
                "Score",
            ]
        )

    result_df = pd.DataFrame(results)

    # Highest score first.
    # Competency name is used as a deterministic secondary sort.
    result_df = result_df.sort_values(
        by=[
            "Score",
            "Competency",
        ],
        ascending=[
            False,
            True,
        ],
    ).reset_index(drop=True)

    # Add rank
    result_df.insert(
        0,
        "Rank",
        range(
            1,
            len(result_df) + 1,
        ),
    )

    return result_df.head(top_n)

# __LEGACY_REST__
