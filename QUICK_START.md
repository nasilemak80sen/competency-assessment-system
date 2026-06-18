# 🚀 Chart Builder - Quick Start Guide

## 5-Minute Quick Start

### Before You Begin
- Ensure Excel data is imported into the system
- Navigate to **"📊 Chart Builder"** from the sidebar

---

## Your First Chart in 5 Steps

### Step 1️⃣: **Skip Filters** (Optional)
- Click **"Step 1: Apply Filters"** to expand
- If you want to focus on specific data, select:
  - Department: e.g., "DPE"
  - Position: e.g., "P5"
  - Grade: e.g., "P7"
- Otherwise, use all data (skip this step)

### Step 2️⃣: **Pick Your Data Elements**
```
Select X-Axis:  Staff Position
Select Y-Axis:  Overall_avg
```

### Step 3️⃣: **Review the Analysis**
- The system shows data types and quality
- If you see warnings ⚠️, read the suggestions 💡

### Step 4️⃣: **Pick Your Chart Type**
- System shows only compatible charts
- Click the chart you want:
  ```
  📊 Bar Chart  ← Click this for comparing positions
  ```

### Step 5️⃣: **View Your Chart!** 🎉
- Interactive chart appears
- Statistics shown below
- Download if needed (camera icon)

---

## Common Scenarios

### 📌 "Compare Personnel by Department"
```
X-Axis:     Department
Y-Axis:     (skip)
Chart Type: 📊 Bar Chart
Result:     Personnel count by department
```

### 📌 "Age vs Competency Score"
```
X-Axis:     Age
Y-Axis:     Overall_avg
Chart Type: 📍 Scatter Plot
Result:     See if older staff have higher scores
```

### 📌 "Score Distribution by Position"
```
X-Axis:     Staff Position
Y-Axis:     Overall_avg
Chart Type: 📦 Box Plot
Result:     Compare score ranges by job level
```

### 📌 "Assessment Trends Over Time"
```
X-Axis:     Last Assesment Date
Y-Axis:     Overall_avg
Chart Type: 📈 Line Chart
Result:     Track how scores change over time
```

---

## Data Elements You Can Use

### 🔴 **Numeric** (Best for Y-axis)
```
Age                    Units in years
Overall_avg            Competency score (0-5)
B_avg, K_avg, P_avg    Category averages
Years in PET           Experience
[B1-B12 scores]        Individual competencies
```

### 🔵 **Categorical** (Best for X-axis)
```
Department            DPE, PSR, MPM, etc.
Staff Position        P5, P7, Manager, etc.
SG (Grade)           P5, P7, CDH, etc.
Gender               M / F
Chat Status          Yes / No / No Need
```

---

## Chart Type Quick Reference

| Chart | When to Use | Example |
|-------|-----------|---------|
| 📊 **Bar Chart** | Count/compare categories | People per department |
| 📍 **Scatter Plot** | Find relationships | Age vs Score |
| 📈 **Line Chart** | Show trends over time | Scores over months |
| 📚 **Stacked Bar** | Show composition | Positions within dept |
| 📉 **Histogram** | See distribution shape | Score distribution |
| 📦 **Box Plot** | Compare ranges | Scores by position |
| 🥧 **Pie Chart** | Show percentages | % by department |
| 🫧 **Bubble Chart** | 3 dimensions | Age vs Score vs Years |

---

## Troubleshooting Quick Fixes

### ❌ "No compatible chart types"
**Fix:** Make sure Y-axis is numeric (score, age, count)

### ❌ "Chart shows no data"
**Fix:** Check Step 1 - you might have filtered out all records

### ⚠️ "Missing Values" warning
**Fix:** Normal - empty cells in data. Chart will ignore them.

### ❌ "Pie chart has too many slices"
**Fix:** Select a column with ≤10 categories

---

## Advanced: Using Filters

### Combine Multiple Filters
```
Department: Select "DPE" + "PSR"
Position:   Select "P5"
→ Result: Only DPE & PSR department's P5 positions
```

### See Filter Results
Record count updates:
```
"✅ Filters applied: Showing 45 of 229 records"
```

---

## Tips & Tricks

💡 **Hover over data**: Get exact values
💡 **Download chart**: Click camera icon (top right of chart)
💡 **Try different charts**: Same data, different chart = new insights
💡 **Use filters**: Focus on the data that matters
💡 **Check sample values**: See what data looks like in Step 3

---

## Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| Submit Filter | Click button or Enter |
| Change Filter | Click multiselect again |
| Download Chart | Hover → Click camera |
| Zoom Chart | Click and drag |
| Pan Chart | Shift + Click and drag |

---

## What If Questions

### "Can I see all columns I can chart?"
Step 2 shows all available data elements. Look at the dropdowns!

### "How do I save my chart?"
Click the camera icon 📷 (top right of chart) to download as PNG

### "Can I compare two departments?"
Yes! Step 1 - Select both departments in the filter

### "What's the red/blue/green color?"
Plotly's default colors. They'll stay consistent for each chart.

### "Can I get exact numbers from my chart?"
Yes! Hover over any data point to see exact values

### "Does filtering change my original data?"
No! Filters only affect the chart. Original data stays unchanged.

---

## Data Flow Diagram

```
📁 Excel File
    ↓
📊 Import Data (Admin Page)
    ↓
💾 Database
    ↓
📊 Chart Builder
    ├→ Step 1: Filter
    ├→ Step 2: Select Columns
    ├→ Step 3: Analyze Data
    ├→ Step 4: Check Compatibility
    ├→ Step 5: Pick Chart
    └→ Step 6: View Chart! 🎉
```

---

## Real-World Examples

### Example 1: HR Director
*Question:* "Which department has the lowest average scores?"
```
Step 2: X=Department, Y=Overall_avg
Step 5: Select Bar Chart
→ See department comparison instantly
```

### Example 2: Training Manager
*Question:* "Has our training improved scores over time?"
```
Step 2: X=Last Assesment Date, Y=Overall_avg
Step 5: Select Line Chart
→ See improvement trend
```

### Example 3: Recruitment Officer
*Question:* "Do more experienced people score higher?"
```
Step 1: Filter by Position="P5"
Step 2: X=Years Experience, Y=Overall_avg
Step 5: Select Scatter Plot
→ See the relationship visually
```

---

## Need Help?

### For More Details
- 📘 **Full Guide**: Read CHART_BUILDER_GUIDE.md
- 👨‍💻 **For Developers**: See CHART_BUILDER_REFERENCE.md
- 📋 **Technical Details**: See CHART_BUILDER_IMPLEMENTATION.md

### Common Issues
- See CHART_BUILDER_GUIDE.md → "Troubleshooting" section

### Feature Not Working?
1. Check if data is imported (Admin: Import Data)
2. Verify you have numeric AND categorical columns
3. Try a simpler chart type first (Bar Chart)
4. Read error message carefully - it has hints!

---

## Summary Checklist

- [ ] I can open Chart Builder page
- [ ] I can select X and Y axes
- [ ] I can apply filters
- [ ] I can create a Bar Chart
- [ ] I can create a Scatter Plot
- [ ] I can see what data looks like (Step 3)
- [ ] I can understand warning messages
- [ ] I can hover over chart for details
- [ ] I can download my chart

**If all checked ✅ - You're ready to explore your data!**

---

**Happy Charting! 📊✨**

*Last Updated: 2026-06-17*
