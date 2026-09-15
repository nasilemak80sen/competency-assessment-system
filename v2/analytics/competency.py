"""Pure competency calculations migrated from the legacy application."""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import COMPETENCY_FULLNAMES, SCORE_COLS


def build_heatmap_matrix(df: pd.DataFrame, value_cols=None) -> pd.DataFrame:
    """Return personnel-by-competency scores for the competency heatmap."""
    columns = list(value_cols) if value_cols is not None else [c for c in SCORE_COLS if c in df.columns]
    columns = [c for c in columns if c in df.columns]
    if df is None or df.empty or "Name" not in df.columns or not columns:
        return pd.DataFrame()
    matrix = df.set_index("Name")[columns].copy()
    return matrix.dropna(how="all")


def _safe_numeric(value):
    try:
        value = pd.to_numeric(value, errors="coerce")
        if pd.isna(value): return None
        return int(round(value))
    except Exception:
        return None


def _get_competency_display_name(code, competency_labels=None):
    labels = competency_labels or COMPETENCY_FULLNAMES
    return labels.get(code, code)


def _get_top_competency_strengths(person_row, competency_codes, competency_labels=None, top_n=3):
    results=[]
    if person_row is None: return pd.DataFrame()
    for code in competency_codes:
        if code not in person_row.index: continue
        score=_safe_numeric(person_row.get(code))
        if score is None: continue
        results.append({"Code":code,"Competency":_get_competency_display_name(code,competency_labels),"Score":score})
    if not results: return pd.DataFrame(columns=["Rank","Code","Competency","Score"])
    result=pd.DataFrame(results).sort_values(["Score","Competency"],ascending=[False,True]).reset_index(drop=True)
    result.insert(0,"Rank",range(1,len(result)+1))
    return result.head(top_n)


def _get_all_competency_strengths(person_row, competency_codes):
    results=[]
    if person_row is None: return pd.DataFrame()
    for code in competency_codes:
        if code not in person_row.index: continue
        actual=_safe_numeric(person_row.get(code))
        if actual is None: continue
        required=_safe_numeric(person_row.get(f"R-{code}")) if f"R-{code}" in person_row.index else None
        gap=None; gap_status="Target unavailable"
        if required is not None:
            gap=actual-required; gap_status="Above Target" if gap>0 else ("Gap Closed" if gap==0 else "Gap Remaining")
        results.append({"Code":code,"Competency":_get_competency_display_name(code),"Score":actual,"Target":required,"Gap":gap,"Gap Status":gap_status})
    if not results: return pd.DataFrame(columns=["Rank","Code","Competency","Score","Target","Gap","Gap Status"])
    result=pd.DataFrame(results).sort_values(["Score","Competency"],ascending=[False,True]).reset_index(drop=True)
    result.insert(0,"Rank",range(1,len(result)+1))
    return result


def _render_competency_strength_class(person_row, class_code, class_config):
    """Render a competency-class strength section for Streamlit pages."""
    import streamlit as st
    label=class_config.get("label",class_code); codes=class_config.get("cols",[])
    st.markdown(f"#### {label}")
    if not codes:
        st.info("No competencies are configured for this class."); return
    strength_df=_get_all_competency_strengths(person_row,codes)
    if strength_df.empty:
        st.info(f"No assessed {label.lower()} scores are available for this personnel."); return
    top3=strength_df.head(3); columns=st.columns(len(top3)); medals=["🥇","🥈","🥉"]
    for idx,(_,row) in enumerate(top3.iterrows()):
        with columns[idx]:
            st.markdown(f"### {medals[idx]}")
            st.markdown(f"**{row['Competency']}**")
            st.metric("Score",f"{row['Score']:.0f}")
            if pd.notna(row["Target"]): st.caption(f"Target: **{row['Target']:.0f}**")
            else: st.caption("Target: **Not Available**")


safe_numeric = _safe_numeric
get_competency_display_name = _get_competency_display_name
get_all_competency_strengths = _get_all_competency_strengths
