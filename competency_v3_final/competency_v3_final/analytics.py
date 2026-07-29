"""
analytics.py – calculations for dashboards: heatmaps, gaps, readiness,
distributions, scatter data.
"""

import numpy as np
import pandas as pd
from typing import Dict, List
from config import SCORE_COLS, REQ_COLS, GAP_COLS, COMP_TYPES


def build_heatmap_matrix(df: pd.DataFrame, value_cols: List[str] = None) -> pd.DataFrame:
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
    """Data for Age vs SG scatter, including Overall_avg for color/size and Unit Name."""
    cols = ["Name", "Age", "SG", "Staff Position", "Department", "Unit Name"]
    cols = [c for c in cols if c in df.columns]
    out = df[cols].copy()
    if "Overall_avg" in df.columns:
        out["Overall_avg"] = df["Overall_avg"]
    return out.dropna(subset=["Age", "SG"])


def gap_analysis_individual(row: pd.Series) -> pd.DataFrame:
    """Return per-competency actual/target/gap table for one person (a Series/row)."""
    records = []
    for sc, rc, gc in zip(SCORE_COLS, REQ_COLS, GAP_COLS):
        a = row.get(sc)
        r = row.get(rc)
        g = row.get(gc)
        if pd.isna(a) and pd.isna(r):
            continue
        records.append({
            "Competency": sc,
            "Type": sc[0],
            "Actual": a,
            "Target": r,
            "Gap": g,
            "Status": "Met" if (pd.notna(g) and g >= 0) else
                      ("Minor Gap" if (pd.notna(g) and g >= -1) else
                       ("Major Gap" if pd.notna(g) else "N/A"))
        })
    return pd.DataFrame(records)
