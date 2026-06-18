# 📊 Chart Builder - User Guide

## Overview

The **Chart Builder** is a powerful feature in the Competency Assessment System that allows you to create custom charts and visualizations from your Excel data. It automatically analyzes your data and recommends the best chart types for your analysis.

## Key Features

✨ **Smart Data Analysis**
- Automatically detects data types (numeric, categorical, datetime)
- Provides data quality warnings and suggestions
- Shows sample values and data ranges

🎨 **Multiple Chart Types**
- Scatter Plot - Show relationships between two numeric variables
- Line Chart - Display trends over time or continuous values
- Bar Chart - Compare categories or groups
- Stacked Bar Chart - Show composition across categories
- Histogram - Visualize distribution of a single numeric variable
- Box Plot - Compare distributions across categories
- Pie Chart - Display parts of a whole (up to 10 categories)
- Bubble Chart - Show relationship between 3 numeric variables

🔍 **Data Filtering**
- Filter by Department
- Filter by Staff Position
- Filter by Salary Grade (SG)
- Combine multiple filters for focused analysis

⚠️ **Data Validation**
- Compatibility checking for selected data elements
- Popup alerts for incompatible data
- Intelligent suggestions for better data element selection

## How to Use

### Step 1: Apply Filters (Optional)

1. Click on **"Step 1: Apply Filters"** to expand the filter section
2. Select filters based on your analysis needs:
   - **Department**: Filter by specific departments
   - **Staff Position**: Filter by job roles
   - **Salary Grade (SG)**: Filter by grade levels
3. The system shows how many records match your filters

**💡 Tip**: You can combine multiple filters (e.g., "DPE Department" + "Staff Position" = "P5")

### Step 2: Select Data Elements

1. In **Step 2**, select your data elements:
   - **🔴 X-Axis Data Element**: The primary variable for your chart (required)
   - **🔵 Y-Axis Data Element**: Secondary variable for paired charts (optional)

2. Available columns include:
   - **Numeric**: Age, Years of Experience, Scores (B1-E2), Averages
   - **Categorical**: Department, Position, Gender, Staff ID, Chat Status
   - **DateTime**: Assessment dates, joining dates, appointment dates

### Step 3: Review Data Analysis

The system automatically analyzes your selected elements and displays:
- **Data Type**: Numeric, Categorical, or DateTime
- **Unique Values**: Number of distinct values
- **Missing Values**: Count of null/empty values
- **Range**: For numeric data (min to max)
- **Sample Values**: Example data points

### Step 4: Check Compatibility

The system validates data compatibility and shows:

✅ **No Issues**: Data is suitable for analysis
⚠️ **Data Issues**: Missing data, incompatible types, or insufficient data
💡 **Suggestions**: Recommended data elements for better analysis

### Step 5: Select Chart Type

Available chart types are displayed with descriptions. Only compatible charts are shown:

| Chart Type | Best For | Requirements |
|-----------|----------|--------------|
| 📍 Scatter Plot | Relationships between 2 numeric variables | Both X & Y numeric |
| 📈 Line Chart | Trends over time | X: Numeric/DateTime, Y: Numeric |
| 📊 Bar Chart | Category comparisons | X: Categorical, Y: Numeric |
| 📚 Stacked Bar | Composition by category | X: Categorical, Y: Numeric |
| 📉 Histogram | Distribution of single variable | X: Numeric |
| 📦 Box Plot | Distribution by category | X: Categorical, Y: Numeric |
| 🥧 Pie Chart | Parts of whole (≤10 categories) | X: Categorical, Y: Numeric |
| 🫧 Bubble Chart | 3 variable relationships | X: Numeric, Y: Numeric |

### Step 6: View Your Chart

The generated chart includes:
- **Interactive visualization** (hover for details)
- **Zoom & pan controls**
- **Download option** (PNG, SVG)
- **Data summary statistics**

## Common Use Cases

### 1. Age vs Competency Score by Department
1. Apply Filter: Select "DPE" Department
2. X-Axis: Age
3. Y-Axis: Overall_avg
4. Chart Type: Scatter Plot
→ See how competency varies by age within a department

### 2. Position Distribution
1. No filters needed
2. X-Axis: Staff Position
3. Y-Axis: (no Y-axis needed)
4. Chart Type: Bar Chart
→ Count of personnel by position

### 3. Assessment Completion Trend
1. No filters
2. X-Axis: Last Assesment Date
3. Y-Axis: (numeric like Score or count)
4. Chart Type: Line Chart
→ Track assessment trends over time

### 4. Gap Analysis by Grade
1. No filters
2. X-Axis: SG (Salary Grade)
3. Y-Axis: Overall_avg
4. Chart Type: Box Plot
→ Compare score distributions across salary grades

## Tips & Best Practices

💡 **Data Quality**
- Filter out "Not Assessed" personnel for clearer analysis
- Look for data completeness (missing values count)
- Use data with sufficient samples (>10 records recommended)

🎯 **Chart Selection**
- Scatter plots work best with 50-500 data points
- Box plots need categorical data with groups
- Pie charts should have ≤10 categories
- Histograms show distribution best with 100+ data points

🔍 **Analysis**
- Use filters to segment data meaningfully
- Compare multiple charts to understand patterns
- Hover over data points for details
- Download charts for reporting

## Supported Data Elements

### Personnel Information
- Name, Staff ID, Gender, Age, Nationality, Email
- Department, Section, Unit, Position, SG (Salary Grade)
- Joining Date, Years of Experience, Employment Category

### Assessment Data
- All competency scores (B1-B12, K1-K5, P1-P5, E1-E2)
- Requirements (R-B1, R-K1, etc.)
- Gaps (G--B1, G--K1, etc.)
- Summary averages (Overall_avg, B_avg, K_avg, P_avg, E_avg)

### Assessment Metadata
- Chat Status, Assessment Level, Last Assessment Date
- Potential, Strength, Interest, Recommendation
- Assessor information, Chat Date

## Troubleshooting

### "No compatible chart types" message
- ✅ Solution: Select a numeric Y-axis for paired charts
- ✅ Solution: Use a categorical X-axis if selecting Bar Chart

### Chart shows too few data points
- ✅ Solution: Remove filters to include more records
- ✅ Solution: Select columns with higher data completeness

### "Missing Values" warning appears
- ℹ️ This is normal. Charts will exclude null values automatically
- ✅ Solution: Filter to include only records with complete data

### Data doesn't match expectations
- ✅ Check active filters in Step 1
- ✅ Verify which records are included (count shown in Step 1)
- ✅ Review sample values in Step 3

## Exporting Charts

1. Hover over the chart in the top-right corner
2. Click the **camera icon** to download as PNG
3. Or use **"Download as CSV"** for the underlying data

## Next Steps

- Combine multiple filters for deeper analysis
- Compare charts with different data elements
- Use results to identify trends and insights
- Share visualizations with stakeholders

---

**Need help?** Contact your system administrator or refer to the main documentation.
