"""Pure competency calculations migrated from the legacy application.

Phase A rule: keep calculation semantics unchanged. Streamlit rendering stays
in the page/component layer until the full dependency chain is migrated.
"""

from __future__ import annotations

import pandas as pd

from config import COMPETENCY_FULLNAMES


def safe_numeric(value):
    """Safely convert a value to a rounded integer, or return None."""
    try:
        value = pd.to_numeric(value, errors="coerce")

        if pd.isna(value):
            return None

        return int(round(value))

    except Exception:
        return None


def get_competency_display_name(code):
    """Return the configured display name, falling back to the code."""
    return COMPETENCY_FULLNAMES.get(code, code)


def get_all_competency_strengths(person_row, competency_codes):
    """Return assessed competencies with target and gap information.

    This is the non-UI portion of the legacy ``_get_all_competency_strengths``
    function. Sorting, rank assignment, target handling, and gap labels are
    intentionally retained exactly so the page layer can consume the same
    result without changing business rules.
    """
    results = []

    if person_row is None:
        return pd.DataFrame()

    for code in competency_codes:
        if code not in person_row.index:
            continue

        actual = safe_numeric(person_row.get(code))

        if actual is None:
            continue

        req_col = f"R-{code}"
        required = None

        if req_col in person_row.index:
            required = safe_numeric(person_row.get(req_col))

        gap = None
        gap_status = "Target unavailable"

        if required is not None:
            gap = actual - required

            if gap > 0:
                gap_status = "Above Target"
            elif gap == 0:
                gap_status = "Gap Closed"
            else:
                gap_status = "Gap Remaining"

        results.append(
            {
                "Code": code,
                "Competency": get_competency_display_name(code),
                "Score": actual,
                "Target": required,
                "Gap": gap,
                "Gap Status": gap_status,
            }
        )

    if not results:
        return pd.DataFrame(
            columns=[
                "Rank",
                "Code",
                "Competency",
                "Score",
                "Target",
                "Gap",
                "Gap Status",
            ]
        )

    result_df = pd.DataFrame(results)

    result_df = result_df.sort_values(
        by=["Score", "Competency"],
        ascending=[False, True],
    ).reset_index(drop=True)

    result_df.insert(0, "Rank", range(1, len(result_df) + 1))

    return result_df
