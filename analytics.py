"""
analytics.py – UPDATED
Calculations for dashboards: heatmaps, gaps, readiness, distributions, scatter data.

UPDATED: gap_analysis_individual() now accepts any ruler_requirements dict
without enforcing P3+ restriction. The app layer controls which grades to show.
"""

import re
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from config import SCORE_COLS, REQ_COLS, GAP_COLS, COMP_TYPES, COMPETENCY_FULLNAMES


def build_heatmap_matrix(df: pd.DataFrame, value_cols: Optional[List[str]] = None) -> pd.DataFrame:
    """
    df: personnel dataframe with score columns (B1..E2)
    Returns a matrix indexed by Name, columns = competencies, values = scores.
    Drops rows where ALL scores are NaN (not yet assessed).
    """
    value_cols = value_cols or [c for c in SCORE_COLS if c in df.columns]
    mat = df.set_index("Name")[value_cols]
    mat = mat.dropna(how="all")
    return mat


def category_average(row: pd.Series, prefix: str, cols: List[str]) -> float:
    vals = [row[c] for c in cols if c in row.index and pd.notna(row[c])]
    return float(np.mean(vals)) if vals else np.nan


def add_category_averages(df: pd.DataFrame) -> pd.DataFrame:
    """Add Base_avg, Knowledge_avg, Pacing_avg, Emerging_avg, Overall_avg columns."""
    out = df.copy()
    for ctype, info in COMP_TYPES.items():
        cols = [c for c in info["cols"] if c in df.columns]
        out[f"{ctype}_avg"] = out[cols].mean(axis=1, skipna=True)
    all_cols = [c for c in SCORE_COLS if c in df.columns]
    out["Overall_avg"] = out[all_cols].mean(axis=1, skipna=True)
    return out


def gap_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each person, count: no_gap, minor_gap (gap<0 but >=-1), major_gap (gap<-1)
    across all G-- columns. Returns Name + counts + overall gap status.
    """
    gap_cols = [c for c in GAP_COLS if c in df.columns]
    out = []
    for _, row in df.iterrows():
        gaps = [row[c] for c in gap_cols if pd.notna(row[c])]
        if not gaps:
            status = "Not Assessed"
            n_gaps = None
        else:
            n_gaps = sum(1 for g in gaps if g < 0)
            if n_gaps == 0:
                status = "No Gap"
            elif n_gaps == 1:
                status = "1 Gap"
            else:
                status = ">1 Gap"
        out.append({
            "Name": row["Name"],
            "Staff Position": row.get("Staff Position"),
            "SG": row.get("SG"),
            "Department": row.get("Department"),
            "Gaps Count": n_gaps,
            "Gap Status": status,
        })
    return pd.DataFrame(out)


def readiness_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Determine readiness for assessment based on overall achievement %.
    achievement% = mean(actual/requirement*100) across competencies with valid req.
    """
    score_cols = [c for c in SCORE_COLS if c in df.columns]
    req_cols   = [c for c in REQ_COLS if c in df.columns]

    out = []
    for _, row in df.iterrows():
        pcts = []
        for sc, rc in zip(score_cols, req_cols):
            a, r = row.get(sc), row.get(rc)
            if pd.notna(a) and pd.notna(r) and r > 0:
                pcts.append(a / r * 100)
        if not pcts:
            achievement = np.nan
            tier = "Not Assessed"
            ready = "N/A"
        else:
            achievement = float(np.mean(pcts))
            if achievement < 50:
                tier = "Tier 1 (<50%)"
            elif achievement < 80:
                tier = "Tier 2 (50-80%)"
            elif achievement < 100:
                tier = "Tier 3 (80-99%)"
            else:
                tier = "Tier 4 (≥100%)"
            ready = "Ready" if achievement >= 80 else "Not Ready"

        out.append({
            "Name": row["Name"],
            "Staff Position": row.get("Staff Position"),
            "SG": row.get("SG"),
            "Department": row.get("Department"),
            "Age": row.get("Age"),
            "Achievement %": round(achievement, 1) if pd.notna(achievement) else None,
            "Readiness Tier": tier,
            "Ready for Assessment": ready,
        })
    return pd.DataFrame(out)


def assessment_completion_by_dept(df: pd.DataFrame) -> pd.DataFrame:
    """% of personnel per department who have at least one score filled."""
    score_cols = [c for c in SCORE_COLS if c in df.columns]
    df2 = df.copy()
    df2["has_assessment"] = df2[score_cols].notna().any(axis=1)
    grp = df2.groupby("Department").agg(
        total=("Name", "count"),
        assessed=("has_assessment", "sum"),
    ).reset_index()
    grp["completion_pct"] = (grp["assessed"] / grp["total"] * 100).round(1)
    return grp.sort_values("completion_pct", ascending=False)


def scatter_age_vs_grade(df: pd.DataFrame) -> pd.DataFrame:
    """
    Data for Age vs SG scatter, including Overall_avg for color/size.
    Returns only columns that exist in the input dataframe.
    """
    # Define ideal columns in order of preference
    size_cols = ["Years of RE Experience", "Years in PET"]
    
    # Find which size column actually exists
    size_col_available = None
    for col in size_cols:
        if col in df.columns:
            size_col_available = col
            break
    
    # Build column list with only columns that exist
    cols = [
        "Name", 
        "Age", 
        "SG", 
        "Staff Position", 
        "Department", 
        "Overall_avg"
    ]
    
    # Only include size column if it exists
    if size_col_available:
        cols.append(size_col_available)
    
    # Filter to only existing columns
    cols = [c for c in cols if c in df.columns]
    
    # Create output
    out = df[cols].copy()
    
    # Fill NaN values
    if "Years in RE Experience" in out.columns:
        out["Years in RE Experience"] = out["Years in RE Experience"].fillna(0)
    if "Years in PET" in out.columns:
        out["Years in PET"] = out["Years in PET"].fillna(0)
    
    # Remove rows missing Age or SG
    return out.dropna(subset=["Age", "SG"])


def gap_analysis_individual(
    row: pd.Series,
    name_map: Optional[Dict[str, str]] = None,
    ruler_requirements: Optional[Dict[str, Dict[str, float]]] = None,
    current_sg: Optional[str] = None,
    include_future_grades: bool = False,
) -> pd.DataFrame:
    """
    Return per-competency actual/target/gap table for one person.

    Args:
        row: Personnel row from dataframe
        name_map: Mapping of competency codes to full names
        ruler_requirements: Dict of {grade: {competency: required_level}}
                           e.g., {"P3": {"B1": 2, "B2": 2}, "P4": {"B1": 2, ...}}
        current_sg: Current salary grade string (e.g., "P5")
        include_future_grades: If True and ruler_requirements provided, include beyond-grade rows

    UPDATED: Removed P3+ restriction. The app layer now controls which grades are shown
    via the filtered_ruler_requirements dict it passes in.
    
    Returns:
        DataFrame with columns: Competency, Competency Name, Type, Actual, Target, Gap,
                               Status, Target Grade, Target Source
    """
    records = []
    name_map = name_map or {}
    ruler_requirements = ruler_requirements or {}
    current_sg = str(current_sg).strip() if current_sg else None

    def _status_for_gap(gap_value):
        """Determine status based on gap value."""
        if pd.isna(gap_value):
            return "N/A"
        if gap_value >= 0:
            return "Met"
        if gap_value >= -1:
            return "Minor Gap"
        return "Major Gap"

    # ── CURRENT-GRADE REQUIREMENTS ─────────────────────────────────────────
    # These come from the person's record (R-B1, R-B2, etc.)
    for sc, rc, gc in zip(SCORE_COLS, REQ_COLS, GAP_COLS):
        a = row.get(sc)
        r = row.get(rc)
        g = row.get(gc)
        if pd.isna(a) and pd.isna(r):
            continue
        comp_name = name_map.get(sc) or COMPETENCY_FULLNAMES.get(sc, sc)
        records.append({
            "Competency": sc,
            "Competency Name": comp_name,
            "Type": sc[0],
            "Actual": a,
            "Target": r,
            "Gap": g,
            "Status": _status_for_gap(g),
            "Target Grade": current_sg or "Current",
            "Target Source": "Current",
        })

    # ── BEYOND-GRADE REQUIREMENTS (from ruler_requirements) ───────────────
    # CHANGE: No P3+ gate here. App.py filters which grades are passed in.
    if include_future_grades and ruler_requirements:
        for grade in sorted(ruler_requirements.keys()):
            grade_req = ruler_requirements[grade]
            
            if not grade_req:
                continue
            
            for sc in SCORE_COLS:
                if sc not in grade_req:
                    continue
                
                a = row.get(sc)
                if pd.isna(a):
                    continue
                
                target = grade_req[sc]
                g = a - target
                comp_name = name_map.get(sc) or COMPETENCY_FULLNAMES.get(sc, sc)
                
                records.append({
                    "Competency": sc,
                    "Competency Name": comp_name,
                    "Type": sc[0],
                    "Actual": a,
                    "Target": target,
                    "Gap": g,
                    "Status": _status_for_gap(g),
                    "Target Grade": grade,
                    "Target Source": "Ruler",
                })

    return pd.DataFrame(records)