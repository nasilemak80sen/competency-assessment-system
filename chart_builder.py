"""
chart_builder.py - Dynamic chart generation with smart data element selection
Detects data types, recommends compatible chart types, and handles filtering
"""

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum


class DataType(Enum):
    """Detected data types for chart compatibility"""
    NUMERIC = "numeric"
    CATEGORICAL = "categorical"
    DATETIME = "datetime"
    MIXED = "mixed"
    UNKNOWN = "unknown"


@dataclass
class DataElementInfo:
    """Information about a data element for chart compatibility"""
    name: str
    data_type: DataType
    unique_count: int
    null_count: int
    sample_values: List[Any]
    numeric_range: Optional[Tuple[float, float]] = None
    is_empty: bool = False


class ChartCompatibility:
    """Manages chart type compatibility with data elements"""

    # Chart type definitions with compatible data types
    CHART_TYPES = {
        "Scatter Plot": {
            "x_required": DataType.NUMERIC,
            "y_required": DataType.NUMERIC,
            "description": "Best for showing relationship between two numeric variables",
            "icon": "📍"
        },
        "Line Chart": {
            "x_required": [DataType.NUMERIC, DataType.DATETIME],
            "y_required": DataType.NUMERIC,
            "description": "Best for showing trends over time or continuous numeric values",
            "icon": "📈"
        },
        "Bar Chart": {
            "x_required": [DataType.CATEGORICAL, DataType.NUMERIC],
            "y_required": DataType.NUMERIC,
            "description": "Best for comparing categories or groups",
            "icon": "📊"
        },
        "Stacked Bar Chart": {
            "x_required": [DataType.CATEGORICAL, DataType.NUMERIC],
            "y_required": DataType.NUMERIC,
            "description": "Best for showing composition across categories",
            "icon": "📚"
        },
        "Histogram": {
            "x_required": DataType.NUMERIC,
            "y_required": None,
            "description": "Best for showing distribution of a single numeric variable",
            "icon": "📉"
        },
        "Box Plot": {
            "x_required": DataType.CATEGORICAL,
            "y_required": DataType.NUMERIC,
            "description": "Best for comparing distributions across categories",
            "icon": "📦"
        },
        "Pie Chart": {
            "x_required": DataType.CATEGORICAL,
            "y_required": DataType.NUMERIC,
            "description": "Best for showing parts of a whole (max 10 categories)",
            "icon": "🥧"
        },
        "Bubble Chart": {
            "x_required": DataType.NUMERIC,
            "y_required": DataType.NUMERIC,
            "description": "Best for showing relationship between 3 numeric variables (bubble size)",
            "icon": "🫧"
        },
    }

    @staticmethod
    def detect_data_type(series: pd.Series) -> DataType:
        """Detect the data type of a pandas Series"""
        if series.isna().all():
            return DataType.UNKNOWN

        # Check if datetime
        if pd.api.types.is_datetime64_any_dtype(series):
            return DataType.DATETIME

        # Check if numeric
        if pd.api.types.is_numeric_dtype(series):
            return DataType.NUMERIC

        # Try to infer from values
        non_null = series.dropna()
        if len(non_null) == 0:
            return DataType.UNKNOWN

        # Sample values
        sample = non_null.head(100).astype(str)

        # Check if can be converted to numeric
        try:
            numeric_count = pd.to_numeric(sample, errors="coerce").notna().sum()
            if numeric_count / len(sample) > 0.8:  # 80% numeric
                return DataType.NUMERIC
        except:
            pass

        # Otherwise categorical
        unique_ratio = len(non_null.unique()) / len(non_null)
        if unique_ratio > 0.5:  # More than 50% unique = likely categorical or mixed
            return DataType.CATEGORICAL if unique_ratio < 0.95 else DataType.MIXED
        else:
            return DataType.CATEGORICAL

    @staticmethod
    def analyze_data_element(series: pd.Series, name: str) -> DataElementInfo:
        """Analyze a data element and return its characteristics"""
        data_type = ChartCompatibility.detect_data_type(series)
        non_null = series.dropna()

        numeric_range = None
        if data_type == DataType.NUMERIC:
            try:
                numeric_vals = pd.to_numeric(non_null, errors="coerce").dropna()
                if len(numeric_vals) > 0:
                    numeric_range = (float(numeric_vals.min()), float(numeric_vals.max()))
            except:
                pass

        sample_values = non_null.head(3).tolist() if len(non_null) > 0 else []

        return DataElementInfo(
            name=name,
            data_type=data_type,
            unique_count=len(non_null.unique()),
            null_count=series.isna().sum(),
            sample_values=sample_values,
            numeric_range=numeric_range,
            is_empty=len(non_null) == 0
        )

    @staticmethod
    def get_compatible_charts(x_element: DataElementInfo, y_element: Optional[DataElementInfo] = None) -> Dict[str, Any]:
        """Get compatible chart types for given data elements"""
        compatible = {}

        for chart_name, requirements in ChartCompatibility.CHART_TYPES.items():
            is_compatible = False
            reason = ""

            # Check if y-axis is required
            if requirements["y_required"] is None:
                # Chart only needs x-axis (e.g., Histogram)
                x_required = requirements.get("x_required")
                if isinstance(x_required, list):
                    is_compatible = x_element.data_type in x_required
                else:
                    is_compatible = x_element.data_type == x_required

                if not is_compatible:
                    reason = f"Requires {x_required.value if isinstance(x_required, DataType) else 'compatible'} data for X-axis"
            else:
                # Chart requires both axes
                if y_element is None:
                    reason = "Requires Y-axis selection"
                else:
                    x_required = requirements.get("x_required")
                    y_required = requirements.get("y_required")

                    x_match = False
                    y_match = False

                    # Check X
                    if isinstance(x_required, list):
                        x_match = x_element.data_type in x_required
                    else:
                        x_match = x_element.data_type == x_required

                    # Check Y
                    if isinstance(y_required, list):
                        y_match = y_element.data_type in y_required
                    else:
                        y_match = y_element.data_type == y_required

                    is_compatible = x_match and y_match

                    if not is_compatible:
                        if not x_match:
                            reason = f"X-axis requires different data type"
                        elif not y_match:
                            reason = f"Y-axis requires numeric data"

            compatible[chart_name] = {
                "is_compatible": is_compatible,
                "reason": reason,
                "requirements": requirements
            }

        return compatible

    @staticmethod
    def get_suggestions(x_element: DataElementInfo, y_element: Optional[DataElementInfo] = None) -> Dict[str, Any]:
        """Get suggestions for incompatible selections"""
        issues = []
        suggestions = []

        # Check for empty data
        if x_element.is_empty:
            issues.append(f"❌ X-axis '{x_element.name}' has no valid data")
        if y_element and y_element.is_empty:
            issues.append(f"❌ Y-axis '{y_element.name}' has no valid data")

        # Check for too many nulls
        if x_element.null_count / max(1, x_element.unique_count) > 0.5:
            issues.append(f"⚠️ X-axis '{x_element.name}' has >50% missing values")
        if y_element and y_element.null_count / max(1, y_element.unique_count) > 0.5:
            issues.append(f"⚠️ Y-axis '{y_element.name}' has >50% missing values")

        # Chart-specific suggestions
        if y_element:
            if y_element.data_type != DataType.NUMERIC:
                issues.append(f"❌ Y-axis '{y_element.name}' is not numeric")
                suggestions.append("💡 For Y-axis, select a numeric column (scores, counts, measurements)")

            if x_element.data_type == DataType.NUMERIC and y_element.data_type == DataType.NUMERIC:
                suggestions.append("✅ Good selection! Scatter plot is ideal for exploring relationships")

            if x_element.data_type == DataType.CATEGORICAL:
                suggestions.append("✅ Good selection! Bar chart is ideal for categorical comparisons")

        return {
            "has_issues": len(issues) > 0,
            "issues": issues,
            "suggestions": suggestions
        }


class ChartBuilder:
    """Builds charts with data filtering and customization"""

    def __init__(self, dataframe: pd.DataFrame):
        self.df = dataframe.copy()
        self.original_df = dataframe.copy()
        self.filters: Dict[str, Any] = {}

    def apply_filters(self, filters: Dict[str, List[Any]]) -> pd.DataFrame:
        """Apply filters to dataframe"""
        df = self.original_df.copy()

        for column, values in filters.items():
            if column in df.columns and values:
                df = df[df[column].isin(values)]

        self.df = df
        return df

    def create_scatter_plot(self, x_col: str, y_col: str, color_col: Optional[str] = None, 
                           size_col: Optional[str] = None, title: str = None) -> go.Figure:
        """Create scatter plot"""
        title = title or f"{x_col} vs {y_col}"

        fig = px.scatter(
            self.df,
            x=x_col,
            y=y_col,
            color=color_col,
            size=size_col,
            title=title,
            hover_data=self.df.columns[:5]  # Show first 5 columns on hover
        )

        fig.update_layout(
            hovermode="closest",
            template="plotly_white",
            height=600,
            xaxis_title=x_col,
            yaxis_title=y_col
        )

        return fig

    def create_bar_chart(self, x_col: str, y_col: str, color_col: Optional[str] = None,
                        title: str = None, stacked: bool = False) -> go.Figure:
        """Create bar chart"""
        title = title or f"{y_col} by {x_col}"
        barmode = "stack" if stacked else "group"

        fig = px.bar(
            self.df,
            x=x_col,
            y=y_col,
            color=color_col,
            title=title,
            barmode=barmode,
            hover_data=self.df.columns[:5]
        )

        fig.update_layout(
            template="plotly_white",
            height=600,
            xaxis_title=x_col,
            yaxis_title=y_col
        )

        return fig

    def create_line_chart(self, x_col: str, y_col: str, color_col: Optional[str] = None,
                         title: str = None) -> go.Figure:
        """Create line chart"""
        title = title or f"Trend of {y_col}"

        fig = px.line(
            self.df,
            x=x_col,
            y=y_col,
            color=color_col,
            markers=True,
            title=title,
            hover_data=self.df.columns[:5]
        )

        fig.update_layout(
            template="plotly_white",
            height=600,
            xaxis_title=x_col,
            yaxis_title=y_col
        )

        return fig

    def create_histogram(self, x_col: str, color_col: Optional[str] = None,
                        nbins: int = 30, title: str = None) -> go.Figure:
        """Create histogram"""
        title = title or f"Distribution of {x_col}"

        fig = px.histogram(
            self.df,
            x=x_col,
            color=color_col,
            nbins=nbins,
            title=title,
            hover_data=self.df.columns[:5]
        )

        fig.update_layout(
            template="plotly_white",
            height=600,
            xaxis_title=x_col,
            yaxis_title="Count"
        )

        return fig

    def create_box_plot(self, x_col: str, y_col: str, color_col: Optional[str] = None,
                       title: str = None) -> go.Figure:
        """Create box plot"""
        title = title or f"Distribution of {y_col} by {x_col}"

        fig = px.box(
            self.df,
            x=x_col,
            y=y_col,
            color=color_col,
            title=title,
            hover_data=self.df.columns[:5]
        )

        fig.update_layout(
            template="plotly_white",
            height=600,
            xaxis_title=x_col,
            yaxis_title=y_col
        )

        return fig

    def create_pie_chart(self, x_col: str, y_col: str, title: str = None) -> go.Figure:
        """Create pie chart"""
        title = title or f"Distribution of {x_col}"

        # Group by x_col and sum y_col
        grouped = self.df.groupby(x_col)[y_col].sum().head(10)

        fig = px.pie(
            values=grouped.values,
            names=grouped.index,
            title=title
        )

        fig.update_layout(
            template="plotly_white",
            height=600
        )

        return fig

    def create_bubble_chart(self, x_col: str, y_col: str, size_col: str, 
                           color_col: Optional[str] = None, title: str = None) -> go.Figure:
        """Create bubble chart"""
        title = title or f"{x_col} vs {y_col} (bubble size: {size_col})"

        fig = px.scatter(
            self.df,
            x=x_col,
            y=y_col,
            size=size_col,
            color=color_col,
            title=title,
            hover_data=self.df.columns[:5]
        )

        fig.update_layout(
            template="plotly_white",
            height=600,
            xaxis_title=x_col,
            yaxis_title=y_col
        )

        return fig

    def create_chart(self, chart_type: str, x_col: str, y_col: Optional[str] = None,
                    color_col: Optional[str] = None, size_col: Optional[str] = None,
                    title: Optional[str] = None, **kwargs) -> go.Figure:
        """Factory method to create any chart type"""

        chart_map = {
            "Scatter Plot": self.create_scatter_plot,
            "Line Chart": self.create_line_chart,
            "Bar Chart": self.create_bar_chart,
            "Stacked Bar Chart": lambda **kw: self.create_bar_chart(stacked=True, **kw),
            "Histogram": self.create_histogram,
            "Box Plot": self.create_box_plot,
            "Pie Chart": self.create_pie_chart,
            "Bubble Chart": self.create_bubble_chart,
        }

        if chart_type not in chart_map:
            raise ValueError(f"Unknown chart type: {chart_type}")

        creator = chart_map[chart_type]
        return creator(x_col=x_col, y_col=y_col, color_col=color_col, 
                      size_col=size_col, title=title, **kwargs)

    def get_filter_options(self) -> Dict[str, List[Any]]:
        """Get available filter options for each column"""
        options = {}
        for col in self.original_df.columns:
            if self.original_df[col].dtype == "object" or len(self.original_df[col].unique()) <= 20:
                options[col] = sorted(self.original_df[col].dropna().unique().tolist())
        return options
