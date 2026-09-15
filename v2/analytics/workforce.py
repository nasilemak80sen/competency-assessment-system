"""Workforce analytics migrated from the legacy dashboard."""
from __future__ import annotations

import pandas as pd


def scatter_age_vs_grade(df: pd.DataFrame) -> pd.DataFrame:
    """Prepare legacy-compatible Age vs SG scatter data.

    Keeps the legacy column preference for point sizing and returns only
    fields available in the source dataframe. Rows without Age or SG are
    excluded because they cannot be plotted meaningfully.
    """
    size_columns = ["Years of RE Experience", "Years in PET"]
    size_column = next((column for column in size_columns if column in df.columns), None)

    columns = ["Name", "Age", "SG", "Staff Position", "Department", "Overall_avg"]
    if size_column:
        columns.append(size_column)
    columns = [column for column in columns if column in df.columns]

    result = df[columns].copy()
    for column in size_columns:
        if column in result.columns:
            result[column] = result[column].fillna(0)

    required = [column for column in ("Age", "SG") if column in result.columns]
    if len(required) != 2:
        return result.iloc[0:0].copy()
    return result.dropna(subset=required)
