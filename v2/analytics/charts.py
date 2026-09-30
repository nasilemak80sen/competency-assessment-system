"""Visualization helpers extracted from the legacy readiness layer."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from .readiness import CATEGORY_ORDER, READINESS_STATUS_ORDER, _rg_sort_salary_grades

READINESS_STATUS_COLORS = {
    "Ready": "#00A19C", "Near Ready": "#BFD730",
    "Development Required": "#FDB924", "Not Assessed": "#94A3B8",
}
GAP_SEVERITY_ORDER = ["Major Gap", "Minor Gap", "Not Assessed", "Met"]
GAP_SEVERITY_COLORS = {
    "Major Gap": "#C62828", "Minor Gap": "#FDB924",
    "Not Assessed": "#94A3B8", "Met": "#00A19C",
}
CATEGORY_COLORS = {"Base": "#00A19C", "Key": "#20419A", "Pacing": "#763F98", "Emerging": "#FDB924"}


def _create_readiness_status_chart(summary_dataframe):
    status_counts = (summary_dataframe["Readiness Status"].value_counts()
                     .reindex(READINESS_STATUS_ORDER, fill_value=0)
                     .rename_axis("Readiness Status").reset_index(name="Personnel"))
    figure = px.bar(status_counts, x="Personnel", y="Readiness Status", orientation="h", text="Personnel",
                    color="Readiness Status", color_discrete_map=READINESS_STATUS_COLORS,
                    category_orders={"Readiness Status": READINESS_STATUS_ORDER})
    figure.update_traces(textposition="outside", hovertemplate="<b>%{y}</b><br>Personnel: %{x:,.0f}<extra></extra>")
    figure.update_layout(title="Competency Readiness Status", height=390, showlegend=False,
                         xaxis_title="Personnel", yaxis_title=None,
                         margin={"l": 10, "r": 40, "t": 60, "b": 40}, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF")
    return figure


def _create_department_readiness_chart(summary_dataframe):
    department_summary = (summary_dataframe.groupby("Department", as_index=False)
                           .agg(Median_Readiness=("Weighted Readiness %", "median"),
                                Personnel=("Name", "count"),
                                Median_Coverage=("Assessment Coverage %", "median"),
                                Personnel_With_Major_Gaps=("Major Gaps", lambda values: int((values > 0).sum()))))
    department_summary["Major Gap Rate %"] = department_summary["Personnel_With_Major_Gaps"] / department_summary["Personnel"] * 100
    department_summary = department_summary.sort_values("Median_Readiness", ascending=True)
    figure = px.scatter(department_summary, x="Median_Readiness", y="Department", size="Personnel", color="Median_Coverage",
                        custom_data=["Personnel", "Median_Coverage", "Major Gap Rate %"], size_max=35,
                        color_continuous_scale=[[0.0, "#FDB924"], [0.5, "#BFD730"], [1.0, "#00A19C"]])
    figure.update_traces(hovertemplate=("<b>%{y}</b><br>Median readiness: %{x:.0f}%<br>Personnel: %{customdata[0]:.0f}<br>"
                                        "Median coverage: %{customdata[1]:.0f}%<br>Major-gap rate: %{customdata[2]:.0f}%<extra></extra>"))
    figure.add_vline(x=80, line_dash="dash", line_color="#00A19C", annotation_text="80% readiness", annotation_position="top")
    figure.update_layout(title="Median Readiness by Department", height=390,
                         xaxis_title="Median Weighted Readiness (%)", yaxis_title=None,
                         coloraxis_colorbar={"title": "Coverage %"}, margin={"l": 10, "r": 20, "t": 60, "b": 40},
                         paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF")
    figure.update_xaxes(range=[0, 105])
    return figure


def _create_readiness_box_plot(summary_dataframe):
    salary_grade_order = _rg_sort_salary_grades(summary_dataframe["Current SG"].dropna())
    figure = px.box(summary_dataframe, x="Current SG", y="Weighted Readiness %", color="Current SG", points="all",
                    hover_name="Name", category_orders={"Current SG": salary_grade_order})
    figure.add_hline(y=80, line_dash="dash", line_color="#00A19C", annotation_text="Ready threshold", annotation_position="top left")
    figure.update_layout(title="Weighted Readiness Distribution by Current Salary Grade", height=480, showlegend=False,
                         xaxis_title="Current Salary Grade", yaxis_title="Weighted Readiness (%)")
    figure.update_yaxes(range=[0, 105])
    return figure


def _create_readiness_coverage_scatter(summary_dataframe):
    plot_dataframe = summary_dataframe.copy()
    plot_dataframe["Bubble Size"] = plot_dataframe["Major Gaps"].fillna(0) + 1
    figure = px.scatter(plot_dataframe, x="Assessment Coverage %", y="Weighted Readiness %", size="Bubble Size",
                        color="Readiness Status", hover_name="Name", color_discrete_map=READINESS_STATUS_COLORS,
                        category_orders={"Readiness Status": READINESS_STATUS_ORDER}, size_max=32)
    figure.add_vline(x=90, line_dash="dash", line_color="#20419A", annotation_text="90% coverage", annotation_position="top")
    figure.add_hline(y=80, line_dash="dash", line_color="#00A19C", annotation_text="80% readiness", annotation_position="top left")
    figure.update_layout(title="Readiness versus Assessment Coverage", height=520,
                         xaxis_title="Assessment Coverage (%)", yaxis_title="Weighted Readiness (%)")
    figure.update_xaxes(range=[0, 105]); figure.update_yaxes(range=[0, 105])
    return figure


def _create_category_readiness_heatmap(summary_dataframe):
    category_columns = {"Base Readiness %": "Base", "Key Readiness %": "Key", "Pacing Readiness %": "Pacing", "Emerging Readiness %": "Emerging"}
    available_columns = [c for c in category_columns if c in summary_dataframe.columns]
    heatmap_dataframe = (summary_dataframe.groupby("Staff Position")[available_columns].median()
                         .rename(columns=category_columns).reindex(columns=CATEGORY_ORDER).dropna(how="all"))
    figure = go.Figure(data=go.Heatmap(z=heatmap_dataframe.values, x=heatmap_dataframe.columns, y=heatmap_dataframe.index,
                                       zmin=0, zmax=100, colorscale=[[0, "#C62828"], [0.5, "#FDB924"], [0.8, "#BFD730"], [1, "#00A19C"]]))
    figure.update_layout(title="Median Category Readiness by Staff Position", height=450,
                         xaxis_title="Competency Category", yaxis_title="Staff Position")
    return figure


def _create_category_gap_distribution(detail_dataframe):
    counts = detail_dataframe.groupby(["Category", "Gap Severity"]).size().reset_index(name="Competencies")
    totals = counts.groupby("Category")["Competencies"].transform("sum")
    counts["Percentage"] = counts["Competencies"] / totals * 100
    figure = px.bar(counts, x="Percentage", y="Category", color="Gap Severity", orientation="h", barmode="stack",
                    category_orders={"Category": CATEGORY_ORDER, "Gap Severity": GAP_SEVERITY_ORDER},
                    color_discrete_map=GAP_SEVERITY_COLORS)
    figure.update_layout(title="Gap Severity Distribution by Competency Category", height=430,
                         xaxis_title="Share of Required Competencies (%)", yaxis_title=None)
    figure.update_xaxes(range=[0, 100])
    return figure


def _build_competency_risk_summary(detail_dataframe):
    records = []
    for competency_code, detail in detail_dataframe.groupby("Competency Code"):
        assessed = detail[detail["Is Assessed"]]
        gaps = assessed[assessed["Gap"] < 0]
        assessed_people = assessed["Name"].nunique()
        affected_people = gaps["Name"].nunique()
        records.append({"Competency Code": competency_code,
                        "Competency Name": detail["Competency Name"].iloc[0],
                        "Category": detail["Category"].iloc[0],
                        "Assessed Personnel": assessed_people,
                        "Affected Personnel": affected_people,
                        "Gap Prevalence %": affected_people / assessed_people * 100 if assessed_people else 0.0,
                        "Average Gap Severity": gaps["Gap Burden"].mean() if not gaps.empty else 0.0,
                        "Gap Burden": gaps["Gap Burden"].sum(),
                        "Major Gap Count": int(gaps["Is Major Gap"].sum())})
    return pd.DataFrame(records)


def _create_competency_risk_matrix(risk_dataframe):
    plot_dataframe = risk_dataframe[risk_dataframe["Affected Personnel"] > 0].copy()
    figure = px.scatter(plot_dataframe, x="Gap Prevalence %", y="Average Gap Severity", size="Affected Personnel",
                        color="Category", hover_name="Competency Code", size_max=45,
                        color_discrete_map=CATEGORY_COLORS)
    figure.update_layout(title="Competency Risk Matrix", height=540, xaxis_title="Personnel with a Gap (%)",
                         yaxis_title="Average Gap Severity")
    figure.update_xaxes(range=[0, 105])
    return figure


def _create_top_competency_gap_chart(risk_dataframe, ranking_metric):
    ranking_map = {"Affected personnel": "Affected Personnel", "Average gap severity": "Average Gap Severity",
                   "Total gap burden": "Gap Burden", "Major-gap count": "Major Gap Count"}
    metric_column = ranking_map[ranking_metric]
    plot_dataframe = risk_dataframe.sort_values(metric_column, ascending=False).head(12).sort_values(metric_column, ascending=True).copy()
    plot_dataframe["Competency Label"] = plot_dataframe["Competency Code"] + " - " + plot_dataframe["Competency Name"]
    figure = px.bar(plot_dataframe, x=metric_column, y="Competency Label", orientation="h", color="Category",
                    color_discrete_map=CATEGORY_COLORS)
    figure.update_layout(title=f"Top Competency Gaps by {ranking_metric}", height=540, xaxis_title=ranking_metric.title(), yaxis_title=None)
    return figure


def _create_department_competency_heatmap(detail_dataframe, top_n):
    assessed = detail_dataframe[detail_dataframe["Is Assessed"]].copy()
    if assessed.empty:
        return None
    assessed["Has Gap"] = assessed["Gap"] < 0
    rates = assessed.groupby("Competency Code")["Has Gap"].mean().sort_values(ascending=False)
    selected = rates.index.tolist() if top_n == "All" else rates.head(int(top_n)).index.tolist()
    source = assessed[assessed["Competency Code"].isin(selected)]
    matrix = source.groupby(["Department", "Competency Code"])["Has Gap"].mean().mul(100).unstack("Competency Code").reindex(columns=selected)
    if matrix.empty:
        return None
    return go.Figure(data=go.Heatmap(z=matrix.values, x=matrix.columns, y=matrix.index, zmin=0, zmax=100,
                                     colorscale=[[0, "#E8F5F3"], [0.5, "#FDB924"], [1, "#C62828"]]))


def _create_personnel_priority_scatter(summary_dataframe):
    required = ["Name", "Weighted Readiness %", "Gap Burden", "Readiness Status"]
    if any(c not in summary_dataframe.columns for c in required):
        return None
    plot_dataframe = summary_dataframe.dropna(subset=["Weighted Readiness %", "Gap Burden"]).copy()
    if plot_dataframe.empty:
        return None
    plot_dataframe["Bubble Size"] = pd.to_numeric(plot_dataframe.get("Years in Grade", 0), errors="coerce").fillna(0).clip(lower=0).add(1)
    figure = px.scatter(plot_dataframe, x="Weighted Readiness %", y="Gap Burden", size="Bubble Size", color="Readiness Status",
                        hover_name="Name", color_discrete_map=READINESS_STATUS_COLORS, size_max=36)
    figure.add_vline(x=80, line_dash="dash", line_color="#00A19C", annotation_text="80% readiness threshold")
    figure.update_layout(title="Personnel Readiness versus Gap Burden", height=560,
                         xaxis_title="Weighted Readiness (%)", yaxis_title="Gap Burden")
    figure.update_xaxes(range=[0, 105])
    return figure
