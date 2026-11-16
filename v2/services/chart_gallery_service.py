"""Lightweight, data-aware thumbnail previews for the saved chart gallery."""
from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go

from chart_builder import ChartBuilder


PREVIEW_CHART_TYPES = {
    "Bar Chart",
    "Stacked Bar Chart",
    "Pie Chart",
    "Box Plot",
    "Scatter Plot",
    "Bubble Chart",
    "Line Chart",
    "Histogram",
}


def _native_values(dataframe: pd.DataFrame, column: str, saved_values: Any) -> list:
    if column not in dataframe.columns or not isinstance(saved_values, (list, tuple)):
        return []
    lookup = {str(value): value for value in dataframe[column].dropna().unique().tolist()}
    return [lookup[str(value)] for value in saved_values if str(value) in lookup]


def _apply_saved_filters(dataframe: pd.DataFrame, filters: dict) -> pd.DataFrame:
    categorical = {}
    for group_name in ("primary", "extra"):
        group = filters.get(group_name, {}) or {}
        if isinstance(group, dict):
            for column, values in group.items():
                matched = _native_values(dataframe, column, values)
                if matched:
                    categorical[column] = matched

    numeric_ranges = {}
    numeric_field = filters.get("numeric_field")
    numeric_range = filters.get("numeric_range")
    if (
        numeric_field in dataframe.columns
        and isinstance(numeric_range, (list, tuple))
        and len(numeric_range) == 2
    ):
        values = pd.to_numeric(dataframe[numeric_field], errors="coerce").dropna()
        if not values.empty:
            low, high = float(values.min()), float(values.max())
            saved_low = max(low, min(high, float(numeric_range[0])))
            saved_high = max(saved_low, min(high, float(numeric_range[1])))
            if low < high:
                numeric_ranges[numeric_field] = (saved_low, saved_high)

    filtered = ChartBuilder(dataframe).apply_filters(categorical, numeric_ranges)
    search = str(filters.get("search") or "").strip()
    if search:
        mask = pd.Series(False, index=filtered.index)
        for column in ("Name", "Staff ID"):
            if column in filtered.columns:
                mask |= filtered[column].astype("string").str.contains(
                    search, case=False, regex=False, na=False
                )
        filtered = filtered.loc[mask].copy()
    return filtered


def build_chart_preview(configuration: dict, dataframe: pd.DataFrame) -> go.Figure | None:
    """Rebuild a small chart preview using a saved setup against current data.

    No personnel rows are persisted with the setup. The preview is regenerated
    from the current master dataframe and the saved filters. Invalid or stale
    configurations return None rather than breaking the gallery.
    """
    if not isinstance(configuration, dict) or dataframe is None or dataframe.empty:
        return None

    chart = configuration.get("chart", {}) or {}
    filters = configuration.get("filters", {}) or {}
    chart_type = chart.get("chart_type")
    dimension = chart.get("dimension")
    measure = chart.get("measure")
    size_col = chart.get("size")
    color_col = chart.get("breakdown")
    if color_col == "(None)":
        color_col = None

    if chart_type not in PREVIEW_CHART_TYPES:
        return None
    if not dimension or dimension not in dataframe.columns:
        return None
    if measure and measure not in dataframe.columns:
        return None
    if size_col and size_col not in dataframe.columns:
        return None
    if color_col and color_col not in dataframe.columns:
        color_col = None
    if chart_type in {"Scatter Plot", "Bubble Chart", "Box Plot", "Line Chart"} and not measure:
        return None
    if chart_type == "Bubble Chart" and not size_col:
        return None

    try:
        filtered = _apply_saved_filters(dataframe, filters)
        if filtered.empty:
            return None

        aggregation = str(chart.get("aggregation") or "Average")
        if not measure:
            aggregation = "Count"

        top_n = chart.get("top_n")
        if top_n in (None, "All", ""):
            top_n = None
        else:
            top_n = int(top_n)

        builder = ChartBuilder(filtered)
        figure = builder.create_chart(
            chart_type,
            x_col=dimension,
            y_col=measure,
            color_col=color_col,
            size_col=size_col,
            title="",
            aggregation=aggregation,
            top_n=top_n,
        )
        figure.update_layout(
            title=None,
            height=190,
            margin=dict(l=12, r=12, t=10, b=28),
            showlegend=False,
            font=dict(size=9),
            xaxis_title=None,
            yaxis_title=None,
        )
        # Thumbnails are visual summaries, not a way to reveal individual
        # personnel details through hover labels.
        for trace in figure.data:
            trace.update(hoverinfo="skip")
        return figure
    except (KeyError, TypeError, ValueError, IndexError, ZeroDivisionError):
        return None
