"""Readiness calculation stack migrated from the legacy application."""
from __future__ import annotations
import re
import numpy as np
import pandas as pd
from config import COMPETENCY_FULLNAMES, SCORE_COLS

READINESS_STATUS_ORDER = ["Ready", "Near Ready", "Development Required", "Not Assessed"]
CATEGORY_ORDER = ["Base", "Key", "Pacing", "Emerging"]

def grade_rank(sg_value):
    if sg_value is None: return None
    try:
        if pd.isna(sg_value): return None
    except (TypeError, ValueError): pass
    match = re.fullmatch(r"P(\d+)", str(sg_value).strip().upper())
    return int(match.group(1)) if match else None

def safe_display_value(value, fallback="Not Applicable"):
    if value is None: return fallback
    try:
        if pd.isna(value): return fallback
    except (TypeError, ValueError): pass
    cleaned = str(value).strip()
    return fallback if cleaned.lower() in {"", "nan", "none", "nat"} else cleaned

def safe_integer_display(value, fallback="Not Applicable"):
    numeric_value = pd.to_numeric(value, errors="coerce")
    return fallback if pd.isna(numeric_value) else int(round(float(numeric_value)))

def safe_date_display(value, fallback="Not Applicable"):
    parsed_date = pd.to_datetime(value, errors="coerce")
    return fallback if pd.isna(parsed_date) else parsed_date.strftime("%d %b %Y")

def assessment_status(gap_value):
    if pd.isna(gap_value): return "Not Assessed"
    if gap_value >= 0: return "✅ Met"
    if gap_value >= -1: return "🟡 Minor Gap"
    return "🔴 Major Gap"

def _rg_clean_value(value, fallback=None):
    if value is None: return fallback
    try:
        if pd.isna(value): return fallback
    except (TypeError, ValueError): pass
    cleaned = str(value).strip()
    return fallback if cleaned.casefold() in {"", "none", "nan", "nat"} else cleaned

def _rg_grade_rank(salary_grade):
    cleaned = _rg_clean_value(salary_grade)
    if cleaned is None: return None
    match = re.fullmatch(r"P(\d+)", cleaned.upper())
    return int(match.group(1)) if match else None

def _rg_sort_salary_grades(salary_grades):
    unique_grades = {str(g).strip().upper() for g in salary_grades if _rg_clean_value(g) is not None}
    return sorted(unique_grades, key=lambda g: _rg_grade_rank(g) if _rg_grade_rank(g) is not None else 999)

def _rg_normalize_ruler(ruler_value):
    cleaned = _rg_clean_value(ruler_value, "BASE").upper()
    return {"NO RULER ASSIGNED":"BASE", "BASE":"BASE", "RDP":"RDP", "RMS":"RMS", "RSS":"RSS"}.get(cleaned, cleaned)

def _rg_get_person_ruler(person_row, ruler_map):
    ruler_value = person_row.get("Ruler Type") or person_row.get("ruler_type")
    if _rg_clean_value(ruler_value) is None: ruler_value = person_row.get("Background")
    ruler_name = _rg_normalize_ruler(ruler_value)
    lookup = {str(key).strip().upper(): key for key in ruler_map.keys()}
    if ruler_name in lookup: return lookup[ruler_name]
    if "BASE" in lookup: return lookup["BASE"]
    return next(iter(ruler_map.keys()), None)

def _rg_get_competency_category(competency_code):
    return {"B":"Base", "K":"Key", "P":"Pacing", "E":"Emerging"}.get(str(competency_code).strip().upper()[:1], "Other")

def _rg_gap_severity(gap_value, is_assessed):
    if not is_assessed or pd.isna(gap_value): return "Not Assessed"
    if gap_value >= 0: return "Met"
    if gap_value >= -1: return "Minor Gap"
    return "Major Gap"

def _rg_determine_target_sg(current_sg, ruler_requirements, target_mode, selected_target_sg=None):
    available_grades = _rg_sort_salary_grades(ruler_requirements.keys())
    if not available_grades: return None
    current_sg = str(current_sg or "").strip().upper()
    if target_mode == "Current requirement": return current_sg if current_sg in available_grades else None
    if target_mode == "Selected target grade": return selected_target_sg if selected_target_sg in available_grades else None
    current_rank = _rg_grade_rank(current_sg)
    if current_rank is None: return available_grades[0]
    future_grades = [g for g in available_grades if _rg_grade_rank(g) is not None and _rg_grade_rank(g) > current_rank]
    return future_grades[0] if future_grades else None

def build_readiness_detail_dataframe(personnel_dataframe, ruler_map, target_mode, selected_target_sg=None):
    records = []
    if personnel_dataframe is None or personnel_dataframe.empty or not ruler_map: return pd.DataFrame()
    for dataframe_index, person_row in personnel_dataframe.iterrows():
        name = _rg_clean_value(person_row.get("Name"), "Unknown Personnel")
        staff_id = _rg_clean_value(person_row.get("Staff ID"))
        personnel_id = person_row.get("id")
        department = _rg_clean_value(person_row.get("Department"), "Not Specified")
        position = _rg_clean_value(person_row.get("Staff Position"), "Not Specified")
        employment = _rg_clean_value(person_row.get("Employment Category"), "Not Specified")
        current_sg = _rg_clean_value(person_row.get("SG"), "").upper()
        years = pd.to_numeric(person_row.get("Years in Salary Grade"), errors="coerce")
        ruler = _rg_get_person_ruler(person_row, ruler_map)
        if ruler is None: continue
        requirements = ruler_map.get(ruler, {})
        target_sg = _rg_determine_target_sg(current_sg, requirements, target_mode, selected_target_sg)
        if target_sg is None: continue
        target_requirements = requirements.get(target_sg, {})
        for code in SCORE_COLS:
            if code not in target_requirements: continue
            target = pd.to_numeric(target_requirements.get(code), errors="coerce")
            if pd.isna(target): continue
            actual = pd.to_numeric(person_row.get(code), errors="coerce")
            assessed = pd.notna(actual)
            gap = float(actual)-float(target) if assessed else np.nan
            capped = min(float(actual), float(target)) if assessed and target > 0 else 0.0
            burden = abs(min(gap, 0)) if pd.notna(gap) else 0.0
            records.append({"Personnel ID":personnel_id,"DataFrame Index":dataframe_index,"Name":name,"Staff ID":staff_id,"Department":department,"Staff Position":position,"Employment Category":employment,"Current SG":current_sg,"Career Ruler":ruler,"Target SG":target_sg,"Years in Grade":years,"Competency Code":code,"Competency Name":COMPETENCY_FULLNAMES.get(code,code),"Category":_rg_get_competency_category(code),"Actual Score":actual,"Target Score":float(target),"Capped Actual":capped,"Gap":gap,"Gap Burden":burden,"Gap Severity":_rg_gap_severity(gap,assessed),"Is Assessed":bool(assessed),"Is Met":bool(assessed and gap >= 0),"Is Major Gap":bool(assessed and gap < -1),"Is Minor Gap":bool(assessed and -1 <= gap < 0)})
    return pd.DataFrame(records)

def classify_readiness_status(weighted_readiness, strict_readiness, coverage, major_gap_count):
    if coverage < 40: return "Not Assessed"
    if weighted_readiness >= 80 and strict_readiness >= 75 and coverage >= 90 and major_gap_count == 0: return "Ready"
    if weighted_readiness >= 65 and coverage >= 75 and major_gap_count <= 2: return "Near Ready"
    return "Development Required"

def recommend_readiness_action(readiness_status, coverage, major_gap_count, minor_gap_count):
    if coverage < 40: return "Complete Assessment"
    if readiness_status == "Ready": return "Ready for Assessment"
    if readiness_status == "Near Ready" and major_gap_count == 0 and minor_gap_count <= 2: return "Close 1-2 Minor Gaps"
    if major_gap_count >= 3: return "Leadership Review Required"
    if major_gap_count > 0: return "Targeted Technical Development"
    return "Focused Development Plan"

def find_top_personnel_gap(person_detail_dataframe):
    gaps = person_detail_dataframe[person_detail_dataframe["Gap"].notna() & (person_detail_dataframe["Gap"] < 0)]
    if gaps.empty: return "None"
    row = gaps.sort_values("Gap", ascending=True).iloc[0]
    return f"{row['Competency Code']} - {row['Competency Name']}"

def build_personnel_readiness_summary(detail_dataframe):
    if detail_dataframe is None or detail_dataframe.empty: return pd.DataFrame()
    groups = ["DataFrame Index","Name","Staff ID","Department","Staff Position","Employment Category","Current SG","Career Ruler","Target SG"]
    records = []
    for values, person in detail_dataframe.groupby(groups, dropna=False):
        group_record = dict(zip(groups, values))
        total = len(person); assessed = int(person["Is Assessed"].sum()); met = int(person["Is Met"].sum()); major = int(person["Is Major Gap"].sum()); minor = int(person["Is Minor Gap"].sum())
        coverage = assessed/total*100 if total else 0.0; strict = met/total*100 if total else 0.0
        target_total = person["Target Score"].fillna(0).clip(lower=0).sum(); weighted = person["Capped Actual"].sum()/target_total*100 if target_total > 0 else 0.0
        burden = person["Gap Burden"].sum(); status = classify_readiness_status(weighted,strict,coverage,major); action = recommend_readiness_action(status,coverage,major,minor)
        cat = {}
        for category in CATEGORY_ORDER:
            part = person[person["Category"] == category]; target = part["Target Score"].fillna(0).clip(lower=0).sum(); cat[category] = part["Capped Actual"].sum()/target*100 if target > 0 else np.nan
        years = person["Years in Grade"].dropna()
        records.append({**group_record,"Required Competencies":total,"Assessed Competencies":assessed,"Assessment Coverage %":coverage,"Weighted Readiness %":weighted,"Strict Readiness %":strict,"Met Competencies":met,"Minor Gaps":minor,"Major Gaps":major,"Gap Burden":burden,"Readiness Status":status,"Recommended Action":action,"Top Gap":find_top_personnel_gap(person),"Years in Grade":float(years.iloc[0]) if not years.empty else np.nan,"Base Readiness %":cat.get("Base"),"Key Readiness %":cat.get("Key"),"Pacing Readiness %":cat.get("Pacing"),"Emerging Readiness %":cat.get("Emerging")})
    return pd.DataFrame(records)

def apply_readiness_personnel_filters(personnel_dataframe, search_text="", departments=None, positions=None, salary_grades=None, employment_categories=None):
    result = personnel_dataframe.copy()
    if search_text:
        text = str(search_text).strip().casefold(); names = result.get("Name",pd.Series("",index=result.index)).fillna("").astype(str).str.casefold(); staff = result.get("Staff ID",pd.Series("",index=result.index)).fillna("").astype(str).str.casefold(); result = result[names.str.contains(text,na=False,regex=False) | staff.str.contains(text,na=False,regex=False)]
    if departments: result = result[result["Department"].isin(departments)]
    if positions: result = result[result["Staff Position"].isin(positions)]
    if salary_grades: result = result[result["SG"].isin(salary_grades)]
    if employment_categories and "Employment Category" in result.columns: result = result[result["Employment Category"].isin(employment_categories)]
    return result.copy()

_grade_rank=grade_rank; _safe_display_value=safe_display_value; _safe_integer_display=safe_integer_display; _safe_date_display=safe_date_display; _get_assessment_status=assessment_status
_build_readiness_detail_dataframe=build_readiness_detail_dataframe; _build_personnel_readiness_summary=build_personnel_readiness_summary; _classify_readiness_status=classify_readiness_status; _recommend_readiness_action=recommend_readiness_action; _find_top_personnel_gap=find_top_personnel_gap; _apply_readiness_personnel_filters=apply_readiness_personnel_filters
