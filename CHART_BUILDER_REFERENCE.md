# 📊 Chart Builder Module - Developer Reference

## Module Overview

The `chart_builder.py` module provides a complete framework for creating interactive charts with intelligent data type detection and compatibility checking.

## Quick Start

```python
from chart_builder import ChartBuilder, ChartCompatibility, DataType

# Load your data
import pandas as pd
df = pd.read_csv("data.csv")

# Create a chart builder instance
builder = ChartBuilder(df)

# Create a scatter plot
fig = builder.create_scatter_plot(x_col="Age", y_col="Score", title="Age vs Score")

# Display in Streamlit
import streamlit as st
st.plotly_chart(fig)
```

## Core Classes & Functions

### DataType (Enum)
Represents the data type of a column.

```python
DataType.NUMERIC        # Numbers (int, float)
DataType.CATEGORICAL    # Text/categories
DataType.DATETIME       # Dates/times
DataType.MIXED          # Multiple types
DataType.UNKNOWN        # Cannot be determined
```

### DataElementInfo (Dataclass)
Contains metadata about a data column.

**Attributes:**
```python
name: str                               # Column name
data_type: DataType                    # Detected type
unique_count: int                      # Number of unique values
null_count: int                        # Number of missing values
sample_values: List[Any]               # First 3 non-null values
numeric_range: Optional[Tuple]         # (min, max) for numeric
is_empty: bool                         # True if all values are null
```

**Example:**
```python
info = ChartCompatibility.analyze_data_element(df['Age'], 'Age')
print(f"{info.name}: {info.data_type}")
print(f"Range: {info.numeric_range}")
print(f"Missing: {info.null_count}/{len(df)}")
```

### ChartCompatibility (Static Methods)

#### detect_data_type(series: pd.Series) -> DataType
Automatically detects the data type of a pandas Series.

```python
type_detected = ChartCompatibility.detect_data_type(df['Department'])
# Returns: DataType.CATEGORICAL
```

#### analyze_data_element(series: pd.Series, name: str) -> DataElementInfo
Provides comprehensive analysis of a data element.

```python
info = ChartCompatibility.analyze_data_element(df['Overall_avg'], 'Overall_avg')
# Returns DataElementInfo with statistics
```

#### get_compatible_charts(x_element: DataElementInfo, y_element: Optional[DataElementInfo]) -> Dict
Returns compatible chart types for given data elements.

```python
compatible = ChartCompatibility.get_compatible_charts(x_info, y_info)
# Returns:
# {
#     'Scatter Plot': {'is_compatible': True, 'reason': '', 'requirements': {...}},
#     'Bar Chart': {'is_compatible': False, 'reason': 'X-axis requires different data type', ...}
# }
```

#### get_suggestions(x_element: DataElementInfo, y_element: Optional[DataElementInfo]) -> Dict
Provides user-friendly suggestions for data issues.

```python
suggestions = ChartCompatibility.get_suggestions(x_info, y_info)
# Returns:
# {
#     'has_issues': False,
#     'issues': [],
#     'suggestions': ['✅ Good selection! Scatter plot is ideal...']
# }
```

### ChartBuilder (Instance Methods)

Initialize a ChartBuilder instance with a DataFrame:

```python
builder = ChartBuilder(df)
```

#### apply_filters(filters: Dict[str, List[Any]]) -> pd.DataFrame
Filter data by column values.

```python
filters = {
    'Department': ['DPE', 'PSR'],
    'SG': ['P5', 'P7']
}
filtered_df = builder.apply_filters(filters)
# Now builder.df contains only matching rows
```

#### create_scatter_plot(x_col, y_col, color_col=None, size_col=None, title=None)
Creates a scatter plot with optional color and size dimensions.

```python
fig = builder.create_scatter_plot(
    x_col='Age',
    y_col='Overall_avg',
    color_col='Department',
    size_col='Years_Experience',
    title='Age vs Competency by Department'
)
```

#### create_line_chart(x_col, y_col, color_col=None, title=None)
Creates a line chart with markers for trend visualization.

```python
fig = builder.create_line_chart(
    x_col='Chat Date',
    y_col='Assessment_Score',
    color_col='Position',
    title='Assessment Scores Over Time'
)
```

#### create_bar_chart(x_col, y_col, color_col=None, title=None, stacked=False)
Creates a bar or stacked bar chart.

```python
# Regular bar chart
fig = builder.create_bar_chart(
    x_col='Department',
    y_col='Count',
    title='Personnel by Department'
)

# Stacked bar chart
fig = builder.create_bar_chart(
    x_col='Department',
    y_col='Count',
    color_col='Position',
    stacked=True,
    title='Personnel by Department and Position'
)
```

#### create_histogram(x_col, color_col=None, nbins=30, title=None)
Creates a histogram for distribution visualization.

```python
fig = builder.create_histogram(
    x_col='Overall_avg',
    nbins=20,
    color_col='Position',
    title='Distribution of Competency Scores'
)
```

#### create_box_plot(x_col, y_col, color_col=None, title=None)
Creates a box plot for statistical distribution comparison.

```python
fig = builder.create_box_plot(
    x_col='SG',
    y_col='Overall_avg',
    color_col='Department',
    title='Score Distribution by Grade'
)
```

#### create_pie_chart(x_col, y_col, title=None)
Creates a pie chart (groups top 10 categories).

```python
fig = builder.create_pie_chart(
    x_col='Department',
    y_col='Count',
    title='Personnel Distribution by Department'
)
```

#### create_bubble_chart(x_col, y_col, size_col, color_col=None, title=None)
Creates a bubble chart with 3+ variables.

```python
fig = builder.create_bubble_chart(
    x_col='Age',
    y_col='Overall_avg',
    size_col='Years_Experience',
    color_col='Position',
    title='Age vs Score (size: experience)'
)
```

#### create_chart(chart_type, x_col, y_col=None, ...)
Factory method for creating any chart type.

```python
fig = builder.create_chart(
    chart_type='Scatter Plot',
    x_col='Age',
    y_col='Overall_avg',
    title='Age vs Score'
)
```

#### get_filter_options() -> Dict[str, List[Any]]
Returns available filter values for each column.

```python
filter_opts = builder.get_filter_options()
# Returns:
# {
#     'Department': ['DPE', 'PSR', 'MPM', ...],
#     'Position': ['P5', 'P7', ...],
#     'Gender': ['M', 'F']
# }
```

## Supported Chart Types

| Chart Type | Best For | X-Axis | Y-Axis | Example |
|-----------|----------|--------|--------|---------|
| Scatter Plot | Relationships | Numeric | Numeric | Age vs Score |
| Line Chart | Trends | Numeric/DateTime | Numeric | Score over time |
| Bar Chart | Comparisons | Categorical | Numeric | Count by department |
| Stacked Bar | Composition | Categorical | Numeric | Positions by department |
| Histogram | Distribution | Numeric | - | Score distribution |
| Box Plot | Quartiles | Categorical | Numeric | Scores by position |
| Pie Chart | Proportions | Categorical | Numeric | % by department |
| Bubble Chart | 3+ vars | Numeric | Numeric | Multiple dimensions |

## Usage Examples

### Example 1: Department Comparison
```python
from chart_builder import ChartBuilder
import pandas as pd

# Load data
df = pd.read_csv('competency_data.csv')

# Create builder
builder = ChartBuilder(df)

# Analyze data
from chart_builder import ChartCompatibility
info_dept = ChartCompatibility.analyze_data_element(df['Department'], 'Department')
info_score = ChartCompatibility.analyze_data_element(df['Overall_avg'], 'Overall_avg')

# Check compatibility
compatible = ChartCompatibility.get_compatible_charts(info_dept, info_score)
print(f"Compatible charts: {list(compatible.keys())}")

# Create bar chart
fig = builder.create_bar_chart('Department', 'Overall_avg', title='Avg Score by Department')
```

### Example 2: Filtered Analysis
```python
# Create builder
builder = ChartBuilder(df)

# Apply filters
builder.apply_filters({'SG': ['P5', 'P7']})

# Create scatter plot of filtered data
fig = builder.create_scatter_plot(
    x_col='Age',
    y_col='Overall_avg',
    color_col='Department',
    title='Senior Staff Analysis'
)
```

### Example 3: Multi-filter + Type Detection
```python
from chart_builder import ChartBuilder, ChartCompatibility

builder = ChartBuilder(df)

# Apply multiple filters
filters = {
    'Department': ['DPE', 'PSR'],
    'Chat Status': ['Yes']
}
builder.apply_filters(filters)

# Analyze selected columns
x_info = ChartCompatibility.analyze_data_element(builder.df['Age'], 'Age')
y_info = ChartCompatibility.analyze_data_element(builder.df['Years_Experience'], 'Years_Experience')

# Get suggestions
suggestions = ChartCompatibility.get_suggestions(x_info, y_info)
if suggestions['has_issues']:
    print("Issues found:")
    for issue in suggestions['issues']:
        print(f"  {issue}")
else:
    # Create chart
    fig = builder.create_scatter_plot('Age', 'Years_Experience')
```

## Data Type Detection Logic

The system uses the following logic to detect data types:

1. **Check for datetime**: `pd.api.types.is_datetime64_any_dtype()`
2. **Check for numeric**: `pd.api.types.is_numeric_dtype()`
3. **Try numeric conversion**: Convert values to numbers; if >80% succeed → NUMERIC
4. **Unique ratio test**: 
   - >50% unique → CATEGORICAL or MIXED
   - ≤50% unique → CATEGORICAL

## Chart Compatibility Rules

### Scatter Plot
- ✅ X: NUMERIC, Y: NUMERIC
- ❌ Otherwise

### Line Chart
- ✅ X: NUMERIC or DATETIME, Y: NUMERIC
- ❌ Otherwise

### Bar Chart
- ✅ X: CATEGORICAL or NUMERIC, Y: NUMERIC
- ❌ Otherwise

### Histogram
- ✅ X: NUMERIC (Y not required)
- ❌ Otherwise

### Box Plot
- ✅ X: CATEGORICAL, Y: NUMERIC
- ❌ Otherwise

### Pie Chart
- ✅ X: CATEGORICAL, Y: NUMERIC
- ❌ Otherwise

### Bubble Chart
- ✅ X: NUMERIC, Y: NUMERIC (size: NUMERIC)
- ❌ Otherwise

## Error Handling

The module handles various error scenarios:

```python
try:
    builder = ChartBuilder(df)
    fig = builder.create_scatter_plot('Age', 'Score')
except ValueError as e:
    print(f"Data validation error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Performance Tips

1. **Large Datasets**: Filter before charting for better performance
   ```python
   builder.apply_filters({'Department': ['DPE']})
   ```

2. **Type Detection**: Cache results if analyzing same column multiple times
   ```python
   info = ChartCompatibility.analyze_data_element(df['Age'], 'Age')
   # Reuse 'info' instead of re-analyzing
   ```

3. **Multiple Charts**: Reuse ChartBuilder instance
   ```python
   builder = ChartBuilder(df)
   fig1 = builder.create_scatter_plot(...)
   fig2 = builder.create_bar_chart(...)  # Reuses same builder
   ```

## Extending the Module

### Adding a New Chart Type

1. Add to `ChartCompatibility.CHART_TYPES`:
   ```python
   CHART_TYPES = {
       ...
       "New Chart": {
           "x_required": DataType.CATEGORICAL,
           "y_required": DataType.NUMERIC,
           "description": "Description here",
           "icon": "🆕"
       }
   }
   ```

2. Add method to ChartBuilder:
   ```python
   def create_new_chart(self, x_col, y_col, **kwargs):
       fig = px.new_chart_type(...)
       return fig
   ```

3. Add to `create_chart()` factory:
   ```python
   "New Chart": self.create_new_chart
   ```

## Troubleshooting

### Empty Chart Results
- Check for NaN/null values: `df.isna().sum()`
- Verify filters applied: `builder.df.shape`
- Check data type detection: `analyze_data_element()`

### Unexpected Compatibility
- Review data type detection logic
- Check for edge cases (all NaN, single unique value)
- Verify column names match exactly

### Performance Issues
- Profile code with `cProfile`
- Filter large datasets before charting
- Use appropriate bin counts for histograms

---

**Version**: 1.0
**Last Updated**: 2026-06-17
**Python**: 3.8+
**Dependencies**: pandas, plotly, streamlit, numpy
