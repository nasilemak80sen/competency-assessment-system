"""Visualization helpers extracted from the legacy readiness layer."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from analytics.readiness import CATEGORY_ORDER, READINESS_STATUS_ORDER, _rg_sort_salary_grades

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
                         xaxis_title="Personnel", yaxis_title=None, margin={"l":10,"r":40,"t":60,"b":40},
                         paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF")
    figure.update_xaxes(showgrid=True, gridcolor="#E8EDF2", zeroline=False)
    return figure


def _create_department_readiness_chart(summary_dataframe):
    department_summary = (summary_dataframe.groupby("Department", as_index=False)
                          .agg(Median_Readiness=("Weighted Readiness %","median"), Personnel=("Name","count"),
                               Median_Coverage=("Assessment Coverage %","median"),
                               Personnel_With_Major_Gaps=("Major Gaps", lambda values: int((values > 0).sum()))))
    department_summary["Major Gap Rate %"] = department_summary["Personnel_With_Major_Gaps"] / department_summary["Personnel"] * 100
    department_summary = department_summary.sort_values("Median_Readiness", ascending=True)
    figure = px.scatter(department_summary, x="Median_Readiness", y="Department", size="Personnel", color="Median_Coverage",
                        custom_data=["Personnel","Median_Coverage","Major Gap Rate %"],
                        color_continuous_scale=[[0.0,"#FDB924"],[0.5,"#BFD730"],[1.0,"#00A19C"]], size_max=35)
    figure.update_traces(hovertemplate="<b>%{y}</b><br>Median readiness: %{x:.0f}%<br>Personnel: %{customdata,.0f}<br>Median coverage: %{customdata.0f}%<br>Major-gap rate: %{customdata.0f}%<extra></extra>")
    figure.add_vline(x=80, line_dash="dash", line_color="#00A19C", annotation_text="80% readiness", annotation_position="top")
    figure.update_layout(title="Median Readiness by Department", height=390, xaxis_title="Median Weighted Readiness (%)", yaxis_title=None,
                         coloraxis_colorbar={"title":"Coverage %"}, margin={"l":10,"r":20,"t":60,"b":40},
                         paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF")
    figure.update_xaxes(range=[0,105], showgrid=True, gridcolor="#E8EDF2")
    return figure


def _create_readiness_box_plot(summary_dataframe):
    order = _rg_sort_salary_grades(summary_dataframe["Current SG"].dropna())
    figure = px.box(summary_dataframe, x="Current SG", y="Weighted Readiness %", color="Current SG", points="all", hover_name="Name",
                    hover_data={"Current SG":False,"Department":True,"Staff Position":True,"Assessment Coverage %":":.0f","Major Gaps":True,"Target SG":True},
                    category_orders={"Current SG":order})
    figure.add_hline(y=80, line_dash="dash", line_color="#00A19C", annotation_text="Ready threshold", annotation_position="top left")
    figure.update_layout(title="Weighted Readiness Distribution by Current Salary Grade", height=480, showlegend=False,
                         xaxis_title="Current Salary Grade", yaxis_title="Weighted Readiness (%)", margin={"l":20,"r":20,"t":70,"b":40},
                         paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF")
    figure.update_yaxes(range=[0,105], showgrid=True, gridcolor="#E8EDF2")
    return figure


def _create_readiness_coverage_scatter(summary_dataframe):
    dataframe = summary_dataframe.copy()
    dataframe["Bubble Size"] = dataframe["Major Gaps"].fillna(0) + 1
    figure = px.scatter(dataframe, x="Assessment Coverage %", y="Weighted Readiness %", size="Bubble Size", color="Readiness Status", hover_name="Name",
                        hover_data={"Bubble Size":False,"Department":True,"Staff Position":True,"Current SG":True,"Target SG":True,"Strict Readiness %":":.0f","Major Gaps":True},
                        color_discrete_map=READINESS_STATUS_COLORS, size_max=32)
    figure.add_vline(x=90, line_dash="dash", line_color="#20419A", annotation_text="90% coverage", annotation_position="top")
    figure.add_hline(y=80, line_dash="dash", line_color="#00A19C", annotation_text="80% readiness", annotation_position="top left")
    figure.update_layout(title="Readiness versus Assessment Coverage", height=520, xaxis_title="Assessment Coverage (%)",
                         yaxis_title="Weighted Readiness (%)", legend_title="Readiness Status", margin={"l":20,"r":20,"t":70,"b":40},
                         paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF")
    figure.update_xaxes(range=[0,105], showgrid=True, gridcolor="#E8EDF2")
    figure.update_yaxes(range=[0,105], showgrid=True, gridcolor="#E8EDF2")
    return figure


def _create_category_readiness_heatmap(summary_dataframe):
    mapping = {"Base Readiness %":"Base","Key Readiness %":"Key","Pacing Readiness %":"Pacing","Emerging Readiness %":"Emerging"}
    available = [column for column in mapping if column in summary_dataframe.columns]
    heatmap = summary_dataframe.groupby("Staff Position")[available].median().rename(columns=mapping).reindex(columns=CATEGORY_ORDER).dropna(how="all")
    figure = go.Figure(data=go.Heatmap(z=heatmap.values, x=heatmap.columns, y=heatmap.index,
        colorscale=[[0.0,"#C62828"],[0.5,"#FDB924"],[0.8,"#BFD730"],[1.0,"#00A19C"]], zmin=0,zmax=100,
        text=np.round(heatmap.values,1), texttemplate="%{text:.0f}%", customdata=np.round(heatmap.values,1),
        hovertemplate="<b>%{y}</b><br>Category: %{x}<br>Median readiness: %{customdata:.0f}%<extra></extra>", colorbar={"title":"Readiness %"}))
    figure.update_layout(title="Median Category Readiness by Staff Position", height=450, xaxis_title="Competency Category", yaxis_title="Staff Position",
                         margin={"l":20,"r":20,"t":70,"b":40}, paper_bgcolor="#FFFFFF")
    return figure


def _create_category_gap_distribution(detail_dataframe):
    counts = detail_dataframe.groupby(["Category","Gap Severity"]).size().reset_index(name="Competencies")
    totals = counts.groupby("Category")["Competencies"].transform("sum")
    counts["Percentage"] = counts["Competencies"] / totals * 100
    figure = px.bar(counts, x="Percentage", y="Category", color="Gap Severity", orientation="h", barmode="stack", text="Percentage",
                    custom_data=["Competencies"], category_orders={"Category":CATEGORY_ORDER,"Gap Severity":GAP_SEVERITY_ORDER}, color_discrete_map=GAP_SEVERITY_COLORS)
    figure.update_traces(texttemplate="%{x:.0f}%", textposition="inside",
                         hovertemplate="<b>%{y}</b><br>Status: %{fullData.name}<br>Percentage: %{x:.0f}%<br>Competency records: %{customdata,.0f}<extra></extra>")
    figure.update_layout(title="Gap Severity Distribution by Competency Category", height=430, xaxis_title="Share of Required Competencies (%)", yaxis_title=None,
                         legend_title="Gap Severity", legend={"orientation":"h","y":1.12,"x":0.5,"xanchor":"center"},
                         margin={"l":20,"r":20,"t":90,"b":40}, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF")
    figure.update_xaxes(range=[0,100])
    return figure


def _build_competency_risk_summary(detail_dataframe):
    records = []
    for code, detail in detail_dataframe.groupby("Competency Code"):
        assessed = detail[detail["Is Assessed"]]
        assessed_count = assessed["Name"].nunique()
        gaps = assessed[assessed["Gap"] < 0]
        affected = gaps["Name"].nunique()
        records.append({"Competency Code":code,"Competency Name":detail["Competency Name"].iloc[0],"Category":detail["Category"].iloc[0],
                        "Assessed Personnel":assessed_count,"Affected Personnel":affected,
                        "Gap Prevalence %":affected/assessed_count*100 if assessed_count else 0.0,
                        "Average Gap Severity":gaps["Gap Burden"].mean() if not gaps.empty else 0.0,
                        "Gap Burden":gaps["Gap Burden"].sum(),"Major Gap Count":int(gaps["Is Major Gap"].sum())})
    return pd.DataFrame(records)


def _create_competency_risk_matrix(risk_dataframe):
    plot = risk_dataframe[risk_dataframe["Affected Personnel"] > 0].copy()
    figure = px.scatter(plot, x="Gap Prevalence %", y="Average Gap Severity", size="Affected Personnel", color="Category", hover_name="Competency Code",
                        hover_data={"Competency Name":True,"Category":True,"Affected Personnel":True,"Assessed Personnel":True,"Gap Burden":":.0f","Major Gap Count":True},
                        color_discrete_map=CATEGORY_COLORS, size_max=45)
    if not plot.empty:
        figure.add_vline(x=plot["Gap Prevalence %"].median(), line_dash="dot", line_color="#64748B")
        figure.add_hline(y=plot["Average Gap Severity"].median(), line_dash="dot", line_color="#64748B")
    figure.update_layout(title="Competency Risk Matrix", height=540, xaxis_title="Personnel with a Gap (%)", yaxis_title="Average Gap Severity", legend_title="Category",
                         margin={"l":20,"r":20,"t":70,"b":40}, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF")
    figure.update_xaxes(range=[0,105], showgrid=True, gridcolor="#E8EDF2")
    figure.update_yaxes(rangemode="tozero", showgrid=True, gridcolor="#E8EDF2")
    return figure


def _create_top_competency_gap_chart(risk_dataframe, ranking_metric):
    ranking_map = {"Affected personnel":"Affected Personnel","Average gap severity":"Average Gap Severity","Total gap burden":"Gap Burden","Major-gap count":"Major Gap Count"}
    metric = ranking_map[ranking_metric]
    plot = risk_dataframe.sort_values(metric, ascending=False).head(12).sort_values(metric, ascending=True).copy()
    plot["Competency Label"] = plot["Competency Code"] + " - " + plot["Competency Name"]
    figure = px.bar(plot, x=metric, y="Competency Label", orientation="h", color="Category", text=metric, color_discrete_map=CATEGORY_COLORS,
                    custom_data=["Affected Personnel","Gap Prevalence %","Average Gap Severity","Gap Burden","Major Gap Count"])
    figure.update_traces(texttemplate="%{x:.0f}", textposition="outside",
                         hovertemplate="<b>%{y}</b><br>Affected personnel: %{customdata,.0f}<br>Gap prevalence: %{customdata.0f}%<br>Average severity: %{customdata.2f}<br>Gap burden: %{customdata.0f}<br>Major gaps: %{customdata,.0f}<extra></extra>")
    figure.update_layout(title=f"Top Competency Gaps by {ranking_metric}", height=540, xaxis_title=ranking_metric.title(), yaxis_title=None, legend_title="Category",
                         margin={"l":10,"r":50,"t":70,"b":40}, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF")
    figure.update_xaxes(showgrid=True, gridcolor="#E8EDF2")
    return figure


def _create_department_competency_heatmap(detail_dataframe, top_n):
    assessed = detail_dataframe[detail_dataframe["Is Assessed"]].copy()
    if assessed.empty: return None
    assessed["Has Gap"] = assessed["Gap"] < 0
    rates = assessed.groupby("Competency Code")["Has Gap"].mean().sort_values(ascending=False)
    selected = rates.head(int(top_n)).index.tolist() if top_n != "All" else rates.index.tolist()
    heatmap = (assessed[assessed["Competency Code"].isin(selected)].groupby(["Department","Competency Code"])["Has Gap"].mean().mul(100)
               .unstack("Competency Code").reindex(columns=selected).dropna(how="all"))
    if heatmap.empty: return None
    figure = go.Figure(data=go.Heatmap(z=heatmap.values, x=heatmap.columns, y=heatmap.index, zmin=0,zmax=100,
        colorscale=[[0.0,"#E8F5F3"],[0.5,"#FDB924"],[1.0,"#C62828"]], text=np.round(heatmap.values,0), texttemplate="%{text:.0f}%",
        hovertemplate="<b>%{y}</b><br>Competency: %{x}<br>Personnel below target: %{z:.0f}%<extra></extra>", colorbar={"title":"Below Target %"}))
    figure.update_layout(title="Department by Competency Gap Rate", height=max(420,40*len(heatmap.index)+160), xaxis_title="Competency Code", yaxis_title="Department",
                         margin={"l":20,"r":20,"t":70,"b":40}, paper_bgcolor="#FFFFFF")
    return figure


def _create_personnel_priority_scatter(summary_dataframe):
    required = ["Name","Weighted Readiness %","Gap Burden","Readiness Status"]
    if any(c not in summary_dataframe.columns for c in required): return None
    plot = summary_dataframe[summary_dataframe["Weighted Readiness %"].notna() & summary_dataframe["Gap Burden"].notna()].copy()
    if plot.empty: return None
    years = pd.to_numeric(plot.get("Years in Grade",0), errors="coerce").fillna(0).clip(lower=0)
    plot["Bubble Size"] = years.add(1)
    plot["Weighted Readiness %"] = pd.to_numeric(plot["Weighted Readiness %"], errors="coerce")
    plot["Gap Burden"] = pd.to_numeric(plot["Gap Burden"], errors="coerce")
    plot = plot.dropna(subset=["Weighted Readiness %","Gap Burden"])
    if plot.empty: return None
    optional = {"Staff ID":True,"Department":True,"Staff Position":True,"Current SG":True,"Career Ruler":True,"Target SG":True,
                "Assessment Coverage %":":.0f","Strict Readiness %":":.0f","Major Gaps":True,"Minor Gaps":True,"Recommended Action":True,"Bubble Size":False}
    hover = {c:f for c,f in optional.items() if c in plot.columns}
    figure = px.scatter(plot, x="Weighted Readiness %", y="Gap Burden", size="Bubble Size", color="Readiness Status", hover_name="Name", hover_data=hover,
                        color_discrete_map=READINESS_STATUS_COLORS, category_orders={"Readiness Status":READINESS_STATUS_ORDER}, size_max=36, opacity=0.82)
    readiness_median = plot["Weighted Readiness %"].median(); burden_median = plot["Gap Burden"].median()
    if pd.notna(readiness_median): figure.add_vline(x=float(readiness_median), line_dash="dot", line_color="#64748B", annotation_text="Median readiness", annotation_position="top")
    if pd.notna(burden_median): figure.add_hline(y=float(burden_median), line_dash="dot", line_color="#64748B", annotation_text="Median gap burden", annotation_position="top left")
    figure.add_vline(x=80, line_dash="dash", line_color="#00A19C", annotation_text="80% readiness threshold", annotation_position="bottom right")
    figure.update_layout(title={"text":"<b>Personnel Readiness versus Gap Burden</b><br><sup>Bubble size represents years in grade</sup>","x":0.01,"xanchor":"left"},
                         height=560, xaxis_title="Weighted Readiness (%)", yaxis_title="Gap Burden", legend_title="Readiness Status",
                         margin={"l":30,"r":20,"t":80,"b":50}, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
                         hoverlabel={"bgcolor":"#FFFFFF","font":{"color":"#0F172A"}})
    figure.update_xaxes(range=[0,105], showgrid=True, gridcolor="#E8EDF2", zeroline=False)
    figure.update_yaxes(rangemode="tozero", showgrid=True, gridcolor="#E8EDF2", zeroline=False)
    return figure


__all__ = [
    "_create_readiness_status_chart", "_create_department_readiness_chart", "_create_readiness_box_plot",
    "_create_readiness_coverage_scatter", "_create_category_readiness_heatmap", "_create_category_gap_distribution",
    "_build_competency_risk_summary", "_create_competency_risk_matrix", "_create_top_competency_gap_chart",
    "_create_department_competency_heatmap", "_create_personnel_priority_scatter",
]
