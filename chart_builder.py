"""
Dynamic Chart Builder engine.

Phase A-E:
- robust data typing and missing-value analysis
- single chart factory and centralised filtering
- dimension/measure/aggregation model
- virtual row-count measure
- recommendation engine
- dynamic categorical/numeric filters and Top-N
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


class DataType(Enum):
    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    DATETIME = "datetime"
    MIXED = "mixed"
    UNKNOWN = "unknown"


@dataclass
class DataElementInfo:
    name: str
    data_type: DataType
    unique_count: int
    null_count: int
    row_count: int
    sample_values: List[Any]
    numeric_range: Optional[Tuple[float, float]] = None
    is_empty: bool = False

    @property
    def missing_ratio(self) -> float:
        return self.null_count / max(1, self.row_count)


class ChartCompatibility:
    CHART_TYPES = {
        "Scatter Plot": {"x": {DataType.NUMERIC}, "y": {DataType.NUMERIC}, "icon": "📍",
                         "description": "Relationship between two numeric variables."},
        "Line Chart": {"x": {DataType.NUMERIC, DataType.DATETIME}, "y": {DataType.NUMERIC}, "icon": "📈",
                       "description": "Trend across ordered or time-based values."},
        "Bar Chart": {"x": {DataType.CATEGORICAL, DataType.NUMERIC, DataType.DATETIME},
                      "y": {DataType.NUMERIC}, "icon": "📊", "description": "Compare aggregated values by category."},
        "Stacked Bar Chart": {"x": {DataType.CATEGORICAL, DataType.NUMERIC, DataType.DATETIME},
                              "y": {DataType.NUMERIC}, "icon": "📚", "description": "Composition across groups."},
        "Histogram": {"x": {DataType.NUMERIC}, "y": None, "icon": "📉",
                      "description": "Distribution of a numeric variable."},
        "Box Plot": {"x": {DataType.CATEGORICAL}, "y": {DataType.NUMERIC}, "icon": "📦",
                     "description": "Distribution of a numeric measure across groups."},
        "Pie Chart": {"x": {DataType.CATEGORICAL}, "y": {DataType.NUMERIC}, "icon": "🥧",
                      "description": "Part-to-whole composition; best with a small number of categories."},
        "Bubble Chart": {"x": {DataType.NUMERIC}, "y": {DataType.NUMERIC}, "icon": "🫧",
                         "description": "Numeric relationship with a third measure controlling size."},
    }

    @staticmethod
    def detect_data_type(series: pd.Series) -> DataType:
        if series is None or series.dropna().empty:
            return DataType.UNKNOWN
        if pd.api.types.is_datetime64_any_dtype(series):
            return DataType.DATETIME
        if pd.api.types.is_bool_dtype(series):
            return DataType.CATEGORICAL
        if pd.api.types.is_numeric_dtype(series):
            return DataType.NUMERIC

        non_null = series.dropna()
        sample = non_null.head(100).astype(str)
        numeric_ratio = pd.to_numeric(sample, errors="coerce").notna().mean()
        if numeric_ratio >= 0.95:
            return DataType.NUMERIC

        unique_ratio = non_null.nunique(dropna=True) / max(1, len(non_null))
        return DataType.MIXED if unique_ratio >= 0.95 else DataType.CATEGORICAL

    @staticmethod
    def analyze_data_element(series: pd.Series, name: str) -> DataElementInfo:
        data_type = ChartCompatibility.detect_data_type(series)
        non_null = series.dropna()
        numeric_range = None
        if data_type == DataType.NUMERIC:
            values = pd.to_numeric(non_null, errors="coerce").dropna()
            if not values.empty:
                numeric_range = (float(values.min()), float(values.max()))
        return DataElementInfo(
            name=name,
            data_type=data_type,
            unique_count=int(non_null.nunique()),
            null_count=int(series.isna().sum()),
            row_count=int(len(series)),
            sample_values=non_null.head(3).tolist(),
            numeric_range=numeric_range,
            is_empty=non_null.empty,
        )

    @classmethod
    def get_compatible_charts(cls, x_element: DataElementInfo,
                              y_element: Optional[DataElementInfo] = None) -> Dict[str, Any]:
        result = {}
        for name, req in cls.CHART_TYPES.items():
            x_ok = x_element.data_type in req["x"]
            y_ok = req["y"] is None or (y_element is not None and y_element.data_type in req["y"])
            if req["y"] is None:
                reason = "" if x_ok else "X-axis must be numeric."
            elif y_element is None:
                reason = "Requires a numeric Y-axis measure."
            elif not x_ok:
                reason = "X-axis data type is not compatible."
            elif not y_ok:
                reason = "Y-axis must be numeric."
            else:
                reason = ""
            result[name] = {
                "is_compatible": x_ok and y_ok,
                "reason": reason,
                "requirements": req,
            }
        return result

    @classmethod
    def get_suggestions(cls, x_element: DataElementInfo,
                        y_element: Optional[DataElementInfo] = None) -> Dict[str, Any]:
        issues: List[str] = []
        suggestions: List[str] = []
        for element, axis in ((x_element, "X"), (y_element, "Y")):
            if element is None:
                continue
            if element.is_empty:
                issues.append(f"❌ {axis}-axis '{element.name}' has no valid data.")
            if element.missing_ratio > 0.5:
                issues.append(f"⚠️ {axis}-axis '{element.name}' has {element.missing_ratio:.0%} missing values.")
        if y_element and y_element.data_type != DataType.NUMERIC:
            issues.append(f"❌ Y-axis '{y_element.name}' is not numeric.")
            suggestions.append("Select a numeric measure or use Count as the measure.")
        if x_element.data_type == DataType.CATEGORICAL and y_element:
            suggestions.append("Bar charts are suitable for grouped categorical comparisons.")
        if x_element.data_type == DataType.NUMERIC and y_element and y_element.data_type == DataType.NUMERIC:
            suggestions.append("Scatter plots are suitable for exploring numeric relationships.")
        if x_element.data_type == DataType.DATETIME and y_element:
            suggestions.append("Line charts are suitable for ordered time-based trends.")
        return {"has_issues": bool(issues), "issues": issues, "suggestions": suggestions}

    @classmethod
    def recommend(cls, x_info: DataElementInfo, y_info: Optional[DataElementInfo],
                   aggregation: str = "Average", color_col: Optional[str] = None) -> List[Dict[str, Any]]:
        ranked: List[Dict[str, Any]] = []
        if x_info.data_type == DataType.DATETIME and y_info and y_info.data_type == DataType.NUMERIC:
            ranked.append({"chart": "Line Chart", "reason": "Time-based dimension with a numeric measure."})
        if x_info.data_type == DataType.CATEGORICAL and y_info and y_info.data_type == DataType.NUMERIC:
            ranked.append({"chart": "Bar Chart", "reason": f"{aggregation} by category is easy to compare."})
            if color_col:
                ranked.append({"chart": "Stacked Bar Chart", "reason": "A breakdown is available for grouped composition."})
            if x_info.unique_count <= 10:
                ranked.append({"chart": "Pie Chart", "reason": "A small categorical set can show composition."})
            if aggregation in {"Average", "Median"}:
                ranked.append({"chart": "Box Plot", "reason": "Useful for comparing score distributions by category."})
        if x_info.data_type == DataType.NUMERIC and y_info and y_info.data_type == DataType.NUMERIC:
            ranked.insert(0, {"chart": "Scatter Plot", "reason": "Both axes are numeric."})
            if color_col:
                ranked.append({"chart": "Bubble Chart", "reason": "A third dimension can be encoded by size."})
        return ranked


class ChartBuilder:
    AGGREGATIONS = ("Count", "Sum", "Average", "Median", "Minimum", "Maximum")

    def __init__(self, dataframe: pd.DataFrame):
        if dataframe is None or dataframe.empty:
            raise ValueError("Cannot create ChartBuilder with empty or None dataframe.")
        self.original_df = dataframe.copy()
        self.df = dataframe.copy()
        self.filters: Dict[str, Any] = {}

    def apply_filters(self, filters: Optional[Dict[str, Sequence[Any]]] = None,
                      numeric_ranges: Optional[Dict[str, Tuple[float, float]]] = None) -> pd.DataFrame:
        df = self.original_df.copy()
        self.filters = filters or {}
        for column, values in self.filters.items():
            if values and column in df.columns:
                df = df[df[column].isin(values)]
        for column, bounds in (numeric_ranges or {}).items():
            if column in df.columns and bounds:
                numeric = pd.to_numeric(df[column], errors="coerce")
                df = df[numeric.between(bounds[0], bounds[1], inclusive="both")]
        self.df = df
        return self.df

    def get_selectable_columns(self) -> List[str]:
        id_columns = {"id", "ID", "Id"}
        return [
            col for col in self.df.columns
            if col not in id_columns
            and not ChartCompatibility.analyze_data_element(self.df[col], col).is_empty
            and ChartCompatibility.analyze_data_element(self.df[col], col).data_type != DataType.MIXED
        ]

    def get_filter_options(self, max_categories: int = 100) -> Dict[str, List[Any]]:
        """Return stable categorical filter values, including mixed int/string columns."""
        options: Dict[str, List[Any]] = {}
        for col in self.get_selectable_columns():
            info = ChartCompatibility.analyze_data_element(self.df[col], col)
            if info.data_type != DataType.CATEGORICAL or info.unique_count > max_categories:
                continue

            values = self.df[col].dropna().unique().tolist()
            # Pandas/Python cannot directly order heterogeneous values such as
            # [14, 15, "16"]. Sort by a display key while preserving raw values.
            options[col] = sorted(
                values,
                key=lambda value: (str(type(value).__name__), str(value)),
            )
        return options

    def aggregate(self, dimension: str, measure: Optional[str] = None,
                  aggregation: str = "Count", color_col: Optional[str] = None,
                  top_n: Optional[int] = None) -> pd.DataFrame:
        if dimension not in self.df.columns:
            raise KeyError(dimension)
        if aggregation not in self.AGGREGATIONS:
            raise ValueError(f"Unsupported aggregation: {aggregation}")

        group_cols = [dimension] + ([color_col] if color_col and color_col in self.df.columns and color_col != dimension else [])
        work = self.df.copy()
        if aggregation == "Count":
            grouped = work.groupby(group_cols, dropna=False).size().reset_index(name="value")
        else:
            if not measure or measure not in work.columns:
                raise ValueError("A numeric measure is required for this aggregation.")
            numeric = pd.to_numeric(work[measure], errors="coerce")
            work = work.assign(__measure=numeric)
            grouped_series = work.groupby(group_cols, dropna=False)["__measure"]
            operation = {
                "Sum": "sum", "Average": "mean", "Median": "median",
                "Minimum": "min", "Maximum": "max",
            }[aggregation]
            grouped = getattr(grouped_series, operation)().reset_index(name="value")

        if top_n:
            ranked = grouped.groupby(dimension, dropna=False)["value"].sum().sort_values(ascending=False).head(top_n)
            grouped = grouped[grouped[dimension].isin(ranked.index)]

        return grouped

    def _hover_columns(self, data_frame: Optional[pd.DataFrame] = None) -> List[str]:
        """Return only columns that actually exist in the dataframe being plotted."""
        frame = data_frame if data_frame is not None else self.df
        return [col for col in frame.columns[:8] if col in frame.columns]

    def create_chart(self, chart_type: str, x_col: str, y_col: Optional[str] = None,
                     color_col: Optional[str] = None, size_col: Optional[str] = None,
                     title: Optional[str] = None, aggregation: str = "Average",
                     top_n: Optional[int] = None, **kwargs) -> go.Figure:
        if chart_type not in ChartCompatibility.CHART_TYPES:
            raise ValueError(f"Unknown chart type: {chart_type}")

        title = title or f"{chart_type}: {x_col}"
        if chart_type in {"Bar Chart", "Stacked Bar Chart", "Pie Chart"} and aggregation:
            if aggregation == "Count" or y_col:
                grouped = self.aggregate(x_col, y_col, aggregation, color_col,
                                         top_n if chart_type != "Pie Chart" else (top_n or 10))
                if chart_type == "Pie Chart":
                    grouped = grouped.groupby(x_col, dropna=False)["value"].sum().reset_index()
                    fig = px.pie(grouped, names=x_col, values="value", title=title)
                else:
                    fig = px.bar(grouped, x=x_col, y="value", color=color_col,
                                 title=title,
                                 barmode="stack" if chart_type == "Stacked Bar Chart" else "group",
                                 hover_data=self._hover_columns(grouped))
                fig.update_layout(xaxis_title=x_col, yaxis_title=f"{aggregation} of {y_col}" if y_col else "Count")
                return self._finish(fig)

        if chart_type == "Histogram":
            fig = px.histogram(self.df, x=x_col, color=color_col, nbins=kwargs.get("nbins", 30),
                               title=title, hover_data=self._hover_columns(self.df))
        elif chart_type == "Box Plot":
            fig = px.box(self.df, x=x_col, y=y_col, color=color_col, title=title,
                         hover_data=self._hover_columns())
        elif chart_type == "Scatter Plot":
            fig = px.scatter(self.df, x=x_col, y=y_col, color=color_col, size=size_col,
                             title=title, hover_data=self._hover_columns())
        elif chart_type == "Bubble Chart":
            if not size_col:
                raise ValueError("Bubble Chart requires a numeric bubble-size measure.")
            fig = px.scatter(self.df, x=x_col, y=y_col, size=size_col, color=color_col,
                             title=title, hover_data=self._hover_columns())
        elif chart_type == "Line Chart":
            fig = px.line(self.df.sort_values(x_col), x=x_col, y=y_col, color=color_col,
                          markers=True, title=title, hover_data=self._hover_columns())
        else:
            raise ValueError(f"Chart type '{chart_type}' requires a compatible dimension/measure selection.")
        return self._finish(fig)

    @staticmethod
    def _finish(fig: go.Figure) -> go.Figure:
        fig.update_layout(template="plotly_white", height=600, margin=dict(l=40, r=30, t=70, b=50))
        return fig

    # Backward-compatible helpers
    def create_scatter_plot(self, x_col, y_col, color_col=None, size_col=None, title=None):
        return self.create_chart("Scatter Plot", x_col, y_col, color_col, size_col, title)

    def create_line_chart(self, x_col, y_col, color_col=None, title=None):
        return self.create_chart("Line Chart", x_col, y_col, color_col, title=title)

    def create_bar_chart(self, x_col, y_col, color_col=None, title=None, stacked=False):
        return self.create_chart("Stacked Bar Chart" if stacked else "Bar Chart", x_col, y_col, color_col, title=title)

    def create_histogram(self, x_col, color_col=None, nbins=30, title=None):
        return self.create_chart("Histogram", x_col, color_col=color_col, title=title, nbins=nbins)

    def create_box_plot(self, x_col, y_col, color_col=None, title=None):
        return self.create_chart("Box Plot", x_col, y_col, color_col, title=title)

    def create_pie_chart(self, x_col, y_col, title=None):
        return self.create_chart("Pie Chart", x_col, y_col, title=title, aggregation="Sum", top_n=10)

    def create_bubble_chart(self, x_col, y_col, size_col, color_col=None, title=None):
        return self.create_chart("Bubble Chart", x_col, y_col, color_col, size_col, title)
