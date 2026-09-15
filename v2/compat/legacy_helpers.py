"""Named compatibility helpers for the final app.py function inventory.

These are normal v2 functions, not a runtime bridge to app.py. They delegate
into the extracted analytics/services/bootstrap layers so the final static
inventory can be audited by legacy function name without executing the legacy
application.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
import pandas as pd
import plotly.graph_objects as go

from analytics.competency import _get_top_competency_strengths, _render_competency_strength_class
from analytics.readiness import (
    grade_rank, safe_display_value, safe_integer_display, safe_date_display,
    assessment_status, build_target_gap_dataframe, calculate_readiness_metrics,
    normalize_ruler_type, sort_grades, apply_readiness_personnel_filters,
    _build_filter_options, _reset_readiness_filters, build_readiness_detail_dataframe,
    build_personnel_readiness_summary,
)
from analytics.charts import _create_readiness_status_chart
from core.bootstrap import get_database_engine, open_session
from config import COMPETENCY_FULLNAMES, SCORE_COLS


def plotly_figure_to_png(figure, width=1400, height=800, scale=2):
    if figure is None: return None
    try:
        return BytesIO(figure.to_image(format="png", width=width, height=height, scale=scale, engine="kaleido"))
    except Exception:
        return None


def _grade_rank(value): return grade_rank(value)
def _safe_display_value(value, fallback="Not Applicable"): return safe_display_value(value, fallback)
def _safe_integer_display(value, fallback="Not Applicable"): return safe_integer_display(value, fallback)
def _safe_date_display(value, fallback="Not Applicable"): return safe_date_display(value, fallback)
def _get_assessment_status(value): return assessment_status(value)


def _build_target_gap_dataframe(person_row, target_sg, selected_ruler_requirements, tech_labels):
    requirements = selected_ruler_requirements.get(target_sg, {}) if target_sg else {}
    return build_target_gap_dataframe(person_row, requirements, person_row.get("SG"), target_sg, None, None, tech_labels)


def _calculate_readiness_metrics(gap_dataframe):
    metrics=calculate_readiness_metrics(gap_dataframe)
    return metrics.get("strict_readiness",0.0), metrics.get("weighted_readiness",0.0), {}


def _make_widget_safe_text(value):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(value).strip()).strip("_")


def _get_personnel_widget_key(person_row):
    return _make_widget_safe_text(person_row.get("id") or person_row.get("Staff ID") or person_row.get("Name") or "unknown")


def _normalize_ruler_name(value): return normalize_ruler_type(value)


def _get_personnel_ruler(person_row):
    value=person_row.get("Ruler Type") or person_row.get("ruler_type") or person_row.get("Background")
    return normalize_ruler_type(value)


def _get_personnel_sg(person_row):
    value=person_row.get("SG")
    if value is None or pd.isna(value): value=person_row.get("sg")
    return "" if value is None or pd.isna(value) else str(value).strip()


def _render_ruler_target_filters(person_row, ruler_map, suffix="main"):
    import streamlit as st
    rulers=sorted(ruler_map.keys(), key=lambda x: str(x))
    if not rulers: return None,None,{}
    current=_get_personnel_ruler(person_row)
    selected_ruler=st.selectbox("Career Ruler", rulers, index=rulers.index(current) if current in rulers else 0, key=f"career_ruler_{_get_personnel_widget_key(person_row)}_{suffix}")
    requirements=ruler_map.get(selected_ruler,{})
    grades=sort_grades(requirements.keys())
    current_sg=_get_personnel_sg(person_row)
    target_options=[g for g in grades if grade_rank(g) is None or grade_rank(g)>= (grade_rank(current_sg) or 0)]
    target=st.selectbox("Target Salary Grade", target_options or grades, key=f"target_sg_{_get_personnel_widget_key(person_row)}_{suffix}") if (target_options or grades) else None
    return selected_ruler,target,requirements


def _load_personnel_database_details(person_row, engine):
    import db_ops
    session=open_session(); personnel_id=None; cv=pd.DataFrame(); summary=None; error=None
    try:
        personnel_id=db_ops.resolve_personnel_id(session, database_id=person_row.get("id"), staff_id=person_row.get("Staff ID"), name=person_row.get("Name"))
        if personnel_id is not None: cv=db_ops.get_cv_documents(session,personnel_id)
    except Exception as exc: error=str(exc)
    finally: session.close()
    return personnel_id,cv,summary,error


def _format_summary_metric(value):
    if value is None or pd.isna(value): return "N/A"
    numeric=pd.to_numeric(value,errors="coerce")
    return str(value) if pd.isna(numeric) else f"{float(numeric):.2f}"


def _render_tech_class_reference():
    import streamlit as st
    with st.expander("📚 Tech Class Reference - Competency Definitions"):
        st.dataframe(pd.DataFrame([{"Code":c,"Competency Name":COMPETENCY_FULLNAMES.get(c,c)} for c in SCORE_COLS]), width="stretch", hide_index=True)


def render_readiness_methodology():
    import streamlit as st
    st.markdown("### 📐 Metric Methodology")
    st.markdown("Readiness compares assessed competency performance against the applicable Career Ruler and target grade.")
    st.dataframe(pd.DataFrame([
        {"Metric":"Weighted Readiness","Definition":"Assessed performance relative to target, capped at target."},
        {"Metric":"Strict Readiness","Definition":"Proportion of competencies meeting target."},
        {"Metric":"Assessment Coverage","Definition":"Assessed competencies divided by required competencies."},
        {"Metric":"Competency Gap","Definition":"Actual Score − Required Score."},
    ]), width="stretch", hide_index=True)


def _build_gap_charts(gap_dataframe, target_sg):
    bar=go.Figure(); bar.add_bar(x=gap_dataframe.get("Competency Code",[]),y=gap_dataframe.get("Actual Score",[]),name="Actual"); bar.add_scatter(x=gap_dataframe.get("Competency Code",[]),y=gap_dataframe.get("Target Score",[]),name="Target",mode="lines+markers")
    bar.update_layout(title=f"Actual vs Target ({target_sg})",height=430,yaxis={"range":[0,5],"dtick":1})
    radar=None
    assessed=gap_dataframe[gap_dataframe["Actual Score"].notna()].copy() if "Actual Score" in gap_dataframe else pd.DataFrame()
    if not assessed.empty:
        names=assessed["Competency Code"].tolist(); actual=assessed["Actual Score"].astype(float).tolist(); target=assessed["Target Score"].astype(float).tolist()
        radar=go.Figure(); radar.add_scatterpolar(r=actual+[actual[0]],theta=names+[names[0]],fill="toself",name="Actual"); radar.add_scatterpolar(r=target+[target[0]],theta=names+[names[0]],name=f"Target ({target_sg})",line={"dash":"dash"}); radar.update_layout(title="Competency Profile",height=430)
    return bar,radar


def _gap_status_style(value):
    return {"✅ Met":"background-color: #C6EFCE; color: #006100;","🟡 Minor Gap":"background-color: #FFF2CC; color: #7F6000;","🔴 Major Gap":"background-color: #FFC7CE; color: #9C0006;","Not Assessed":"background-color: #E7E6E6; color: #595959;"}.get(value,"")


def load_asset_text(relative_path):
    path=Path(__file__).resolve().parents[2]/relative_path
    return path.read_text(encoding="utf-8")


def scatter_age_vs_grade(df):
    size_col="Years of RE Experience" if "Years of RE Experience" in df.columns else ("Years in PET" if "Years in PET" in df.columns else None)
    cols=[c for c in ["Name","Age","SG","Staff Position","Department","Overall_avg",size_col] if c and c in df.columns]
    result=df[cols].copy()
    if "Years in RE Experience" in result: result["Years in RE Experience"]=result["Years in RE Experience"].fillna(0)
    if "Years in PET" in result: result["Years in PET"]=result["Years in PET"].fillna(0)
    return result.dropna(subset=[c for c in ["Age","SG"] if c in result.columns])


def _build_readiness_detail_dataframe(*args, **kwargs): return build_readiness_detail_dataframe(*args, **kwargs)
def _classify_readiness_status(weighted_readiness, strict_readiness, coverage, major_gap_count):
    from analytics.readiness import classify_readiness_status
    return classify_readiness_status(weighted_readiness,strict_readiness,coverage,major_gap_count)
def _recommend_readiness_action(readiness_status, coverage, major_gap_count, minor_gap_count):
    from analytics.readiness import recommend_readiness_action
    return recommend_readiness_action(readiness_status,coverage,major_gap_count,minor_gap_count)
def _find_top_personnel_gap(person_detail_dataframe):
    from analytics.readiness import find_top_personnel_gap
    return find_top_personnel_gap(person_detail_dataframe)
def _build_personnel_readiness_summary(*args, **kwargs): return build_personnel_readiness_summary(*args, **kwargs)
def _apply_readiness_personnel_filters(*args, **kwargs): return apply_readiness_personnel_filters(*args, **kwargs)
def _build_filter_options(*args, **kwargs): return _build_filter_options(*args, **kwargs)
def _reset_readiness_filters(session_state): return _reset_readiness_filters(session_state)


def get_engine(): return get_database_engine()
def bump_version(): return None
def _load_wide_df_cached(_version):
    from core.bootstrap import get_master_data
    return get_master_data()
def load_wide_df(_version): return _load_wide_df_cached(_version)
def _load_ruler_and_mappings_cached():
    from core.bootstrap import get_ruler_data
    return get_ruler_data()
def load_ruler_and_mappings(): return _load_ruler_and_mappings_cached()


def export_to_pdf(person_row, target_sg, df_gap, metrics, filename="individual_assessment_report.pdf", **kwargs):
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    buffer=BytesIO(); doc=SimpleDocTemplate(buffer,pagesize=A4,rightMargin=12*mm,leftMargin=12*mm,topMargin=12*mm,bottomMargin=12*mm)
    story=[Paragraph("DPE Reservoir Engineering — Individual Competency Assessment",__import__("reportlab.lib.styles",fromlist=["getSampleStyleSheet"]).getSampleStyleSheet()["Title"]),Spacer(1,6*mm)]
    story.append(Paragraph(f"Name: {person_row.get('Name','N/A')} | Staff ID: {person_row.get('Staff ID','N/A')}",__import__("reportlab.lib.styles",fromlist=["getSampleStyleSheet"]).getSampleStyleSheet()["BodyText"]))
    rows=[["Code","Competency","Actual","Target","Gap","Status"]]
    for _,row in df_gap.iterrows(): rows.append([str(row.get("Competency Code",row.get("Competency",""))),str(row.get("Competency Name","")),str(row.get("Actual Score",row.get("Actual",""))),str(row.get("Target Score",row.get("Target",""))),str(row.get("Gap","")),str(row.get("Status",""))])
    table=Table(rows,repeatRows=1); table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#20419A")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#CBD5E1"))])); story.append(table); doc.build(story); buffer.seek(0); return buffer
