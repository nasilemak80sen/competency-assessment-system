"""
db_ops.py – All database operations (CRUD + bulk import from DataFrame).
"""

import json
import re
import numpy as np
import pandas as pd
from datetime import datetime, date
from typing import Optional, Dict, Any, List, Tuple, cast

from sqlalchemy.orm import Session
from models import Personnel, Assessment, CompetencyScore, SummaryScore, CVDocument, AuditLog
from config import SCORE_COLS, REQ_COLS, GAP_COLS, SUMMARY_GROUPS, POSITION_TO_SG


# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe(val):
    """Convert numpy/pandas types and NaN/NaT to Python native / None."""
    if val is None:
        return None
    # Catches NaN, NaT, None, pd.NA in one go
    try:
        if pd.isnull(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, (np.integer,)):
        return int(val)
    if isinstance(val, (np.floating,)):
        return float(val)
    if isinstance(val, pd.Timestamp):
        return val.date()
    if isinstance(val, np.datetime64):
        ts = pd.Timestamp(val)
        return None if pd.isnull(ts) else ts.date()
    return val


def _log(session: Session, entity_type: str, entity_id: Optional[int],
         action: str, old: dict, new: dict, by: str = "system"):
    try:
        session.add(AuditLog(
            entity_type=entity_type, entity_id=int(entity_id) if entity_id is not None else None,
            action=action, changed_by=by,
            old_values=json.dumps(old), new_values=json.dumps(new)
        ))
        session.commit()
    except Exception:
        pass
def _normalise_matching_name(value):
    """
    Normalize personnel names for CV matching.
    """
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    normalized = str(value).lower().strip()

    replacements = {
        "@": " ",
        ".": " ",
        ",": " ",
        "'": "",
        "-": " ",
        "_": " ",
        "(": " ",
        ")": " ",
        "&": " and ",
    }

    for old_value, new_value in replacements.items():
        normalized = normalized.replace(
            old_value,
            new_value,
        )

    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    )

    return normalized.strip() or None


def _normalise_import_staff_id(value):
    """
    Normalize Staff IDs for database matching.
    """
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    cleaned = str(value).strip()

    cleaned = re.sub(
        r"\.0$",
        "",
        cleaned,
    )

    return cleaned or None


def _find_person_for_cv(
    session,
    cv_row,
):
    """
    Match one CV-list record to Personnel.

    Matching priority:
        1. Staff ID
        2. Exact normalized name
        3. Unique controlled partial-name match
    """
    source_staff_id = (
        _normalise_import_staff_id(
            cv_row.get("Staff ID")
        )
    )

    source_name = (
        _normalise_matching_name(
            cv_row.get("Name")
        )
    )

    # ------------------------------------------------------------------
    # 1. STAFF ID
    # ------------------------------------------------------------------

    if source_staff_id:
        person = (
            session.query(Personnel)
            .filter(
                Personnel.staff_id
                == source_staff_id,
                Personnel.is_deleted.is_(False),
            )
            .first()
        )

        if person:
            return person, "Staff ID"

    # ------------------------------------------------------------------
    # 2. EXACT NORMALIZED NAME
    # ------------------------------------------------------------------

    if source_name:
        active_people = (
            session.query(Personnel)
            .filter(
                Personnel.is_deleted.is_(False)
            )
            .all()
        )

        exact_matches = [
            person
            for person in active_people
            if (
                _normalise_matching_name(
                    person.name
                )
                == source_name
            )
        ]

        if len(exact_matches) == 1:
            return (
                exact_matches[0],
                "Exact normalized name",
            )

        # --------------------------------------------------------------
        # 3. UNIQUE PARTIAL-NAME MATCH
        # --------------------------------------------------------------

        partial_matches = []

        for person in active_people:
            database_name = (
                _normalise_matching_name(
                    person.name
                )
            )

            if not database_name:
                continue

            if (
                source_name in database_name
                or database_name in source_name
            ):
                partial_matches.append(person)

        if len(partial_matches) == 1:
            return (
                partial_matches[0],
                "Unique partial name",
            )

    return None, "No unique match"

# ── Personnel CRUD ────────────────────────────────────────────────────────────

def _coerce_numeric(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (str,)):
        text = value.strip()
        if not text or text.lower() in {"nan", "none", "null"}:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def add_personnel(session: Session, data: Dict[str, Any]) -> Tuple[bool, str, Optional[int]]:
    try:
        existing = session.query(Personnel).filter_by(staff_id=data.get("staff_id")).first()
        if existing:
            return False, f"Staff ID {data['staff_id']} already exists.", None

        sg = data.get("sg") or POSITION_TO_SG.get(data.get("staff_position", ""), None)

        p = Personnel(
            staff_id=data.get("staff_id"),
            name=data.get("name"),
            email=data.get("email"),
            gender=data.get("gender"),
            age=_safe(data.get("age")),
            birth_year=_safe(data.get("birth_year")),
            nationality=data.get("nationality"),
            employment_category=data.get("employment_category"),
            department=data.get("department"),
            section_name=data.get("section_name"),
            unit_name=data.get("unit_name"),
            sub_unit=data.get("sub_unit"),
            staff_position=data.get("staff_position"),
            sg=sg,
            joining_date=_safe(data.get("joining_date")),
            contract_expire_date=_safe(data.get("contract_expire_date")),
            years_in_pet=_safe(data.get("years_in_pet")),
            years_re_experience=_safe(data.get("years_re_experience")),
            sg_years=_safe(data.get("sg_years")),
            sg_start_date=_safe(data.get("sg_start_date")),
            age_promoted=_safe(data.get("age_promoted")),
            current_assignment=data.get("current_assignment"),
            assignment_date=_safe(data.get("assignment_date")),
            assignment_length=_safe(data.get("assignment_length")),
            chat_status=data.get("chat_status", "No Need"),
            chat_date=_safe(data.get("chat_date")),
            assessment_level=data.get("assessment_level"),
            last_assessment_date=_safe(data.get("last_assessment_date")),
            sub_disciplines=data.get("sub_disciplines"),
            potential=data.get("potential"),
            strength=data.get("strength"),
            recommendation=data.get("recommendation"),
            resource_sme=data.get("resource_sme"),
            interest=data.get("interest"),
            preference=data.get("preference"),
            comment=data.get("comment"),
            assessor1=data.get("assessor1"),
            assessor2=data.get("assessor2"),
            supervisor=data.get("supervisor"),
            remarks=data.get("remarks"),
        )
        session.add(p)
        session.flush()
        session.commit()
        _log(session, "Personnel", cast(int, p.id), "CREATE", {}, data)
        return True, f"Added: {p.name}", cast(int, p.id)
    except Exception as e:
        session.rollback()
        return False, str(e), None


def update_personnel(session: Session, pid: int, data: Dict[str, Any]) -> Tuple[bool, str]:
    try:
        p = session.query(Personnel).filter_by(id=pid).first()
        if not p:
            return False, "Personnel not found."
        old = {k: getattr(p, k) for k in data if hasattr(p, k)}
        for k, v in data.items():
            if hasattr(p, k):
                setattr(p, k, _safe(v))
        setattr(p, "updated_at", datetime.utcnow())
        session.commit()
        _log(session, "Personnel", pid, "UPDATE", old, data)
        return True, f"Updated: {p.name}"
    except Exception as e:
        session.rollback()
        return False, str(e)


def delete_personnel(session: Session, pid: int) -> Tuple[bool, str]:
    try:
        p = session.query(Personnel).filter_by(id=pid).first()
        if not p:
            return False, "Not found."
        setattr(p, "is_deleted", True)
        setattr(p, "is_active", False)
        session.commit()
        _log(session, "Personnel", pid, "DELETE", {"name": p.name}, {})
        return True, f"Deleted: {p.name}"
    except Exception as e:
        session.rollback()
        return False, str(e)


def get_all_personnel(session: Session, include_deleted: bool = False) -> pd.DataFrame:
    """Return all personnel as DataFrame for easy display."""
    q = session.query(Personnel)
    if not include_deleted:
        q = q.filter(Personnel.is_deleted == False)
    rows = [p.__dict__ for p in q.all()]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).drop(columns=["_sa_instance_state"], errors="ignore")
    return df


def get_personnel_by_id(session: Session, pid: int) -> Optional[Personnel]:
    return session.query(Personnel).filter_by(id=pid, is_deleted=False).first()


def search_personnel(session: Session, term: str) -> List[Personnel]:
    t = f"%{term}%"
    return session.query(Personnel).filter(
        Personnel.is_deleted == False,
        (Personnel.name.ilike(t) | Personnel.staff_id.ilike(t))
    ).all()


# ── Assessment CRUD ───────────────────────────────────────────────────────────

def add_assessment(session: Session, personnel_id: int, data: Dict) -> Tuple[bool, str, Optional[int]]:
    try:
        a = Assessment(
            personnel_id=personnel_id,
            assessment_date=_safe(data.get("assessment_date", date.today())),
            assessment_level=data.get("assessment_level"),
            assessor1=data.get("assessor1"),
            assessor2=data.get("assessor2"),
            supervisor=data.get("supervisor"),
            remarks=data.get("remarks"),
        )
        session.add(a)
        session.flush()
        session.commit()
        return True, "Assessment created.", cast(int, a.id)
    except Exception as e:
        session.rollback()
        return False, str(e), None


def add_competency_scores(session: Session, assessment_id: Optional[int],
                          personnel_id: Optional[int], scores: Dict[str, Dict]) -> Tuple[bool, str]:
    """
    scores = { "B1": {"actual": 3, "req": 3, "gap": 0}, ... }
    """
    try:
        if assessment_id is None or personnel_id is None:
            return False, "Assessment and personnel ids are required."

        assessment_id = int(assessment_id)
        personnel_id = int(personnel_id)

        for code, vals in scores.items():
            actual = _coerce_numeric(vals.get("actual"))
            req    = _coerce_numeric(vals.get("req"))
            gap    = _coerce_numeric(vals.get("gap"))
            pct    = round((actual / req * 100), 1) if (req is not None and req > 0 and actual is not None) else None
            session.add(CompetencyScore(
                assessment_id=assessment_id,
                personnel_id=personnel_id,
                competency_code=code,
                competency_type=code[0],
                actual_score=actual,
                requirement_score=req,
                gap_score=gap,
                achievement_pct=pct,
            ))
        session.commit()
        return True, f"{len(scores)} scores saved."
    except Exception as e:
        session.rollback()
        return False, str(e)


def get_latest_scores(session: Session, personnel_id: int) -> pd.DataFrame:
    """Return latest assessment scores as DataFrame."""
    latest = (
        session.query(Assessment)
        .filter_by(personnel_id=personnel_id)
        .order_by(Assessment.assessment_date.desc())
        .first()
    )
    if not latest:
        return pd.DataFrame()
    rows = [s.__dict__ for s in latest.scores]
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).drop(columns=["_sa_instance_state"], errors="ignore")


def get_assessment_history(session: Session, personnel_id: int) -> pd.DataFrame:
    """Return all assessments for trend analysis."""
    assessments = (
        session.query(Assessment)
        .filter_by(personnel_id=personnel_id)
        .order_by(Assessment.assessment_date)
        .all()
    )
    records = []
    for a in assessments:
        for s in a.scores:
            records.append({
                "date": a.assessment_date,
                "competency_code": s.competency_code,
                "competency_type": s.competency_type,
                "actual_score": s.actual_score,
                "requirement_score": s.requirement_score,
                "gap_score": s.gap_score,
                "achievement_pct": s.achievement_pct,
            })
    return pd.DataFrame(records)


# ── Summary Score CRUD ────────────────────────────────────────────────────────

def upsert_summary_score(session: Session, personnel_id: Optional[int], data: Dict) -> Tuple[bool, str]:
    try:
        if personnel_id is None:
            return False, "Personnel id is required."
        personnel_id = int(personnel_id)
        existing = session.query(SummaryScore).filter_by(personnel_id=personnel_id).first()
        if existing:
            for k, v in data.items():
                if hasattr(existing, k):
                    setattr(existing, k, _safe(v))
            setattr(existing, "updated_at", datetime.utcnow())
        else:
            s = SummaryScore(personnel_id=personnel_id)
            for k, v in data.items():
                if hasattr(s, k):
                    setattr(s, k, _safe(v))
            session.add(s)
        session.commit()
        return True, "Summary scores saved."
    except Exception as e:
        session.rollback()
        return False, str(e)


def get_all_summary_scores(session: Session) -> pd.DataFrame:
    rows = [s.__dict__ for s in session.query(SummaryScore).all()]
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).drop(columns=["_sa_instance_state"], errors="ignore")


# ── Bulk Import from DataFrame ────────────────────────────────────────────────

def _normalize_key(value):
    if value is None:
        return None
    try:
        s = str(value).strip()
    except Exception:
        return None
    return re.sub(r"\s+", " ", s)


def _find_ruler_requirements(ruler_map: Dict[str, Dict[str, Dict[str, Any]]], ruler_type: str, sg: str) -> Optional[Dict[str, Any]]:
    if not ruler_map or not ruler_type or not sg:
        return None
    ruler_type_norm = _normalize_key(ruler_type)
    sg_norm = _normalize_key(sg)
    if not ruler_type_norm or not sg_norm:
        return None
    candidates = [ruler_type_norm, ruler_type_norm.upper(), ruler_type_norm.title(), ruler_type_norm.lower()]
    for key in candidates:
        type_map = ruler_map.get(key)
        if not type_map:
            continue
        if sg_norm in type_map:
            return type_map[sg_norm]
        if sg_norm.upper() in type_map:
            return type_map[sg_norm.upper()]
        if sg_norm.title() in type_map:
            return type_map[sg_norm.title()]
    return None


def _build_ruler_requirements(row: pd.Series, ruler_map: Dict[str, Dict[str, Dict[str, Any]]]) -> Dict[str, Any]:
    reqs = {}
    if not ruler_map:
        return reqs
    ruler_type = row.get("Ruler Type") or row.get("Background")
    if pd.isna(ruler_type):
        ruler_type = row.get("Background")
    sg = row.get("SG")
    if pd.isna(sg) or sg is None or str(sg).strip() == "":
        position_key = _normalize_key(row.get("Staff Position") or "") or ""
        sg = POSITION_TO_SG.get(position_key, None)
    reqs = _find_ruler_requirements(ruler_map, str(ruler_type or ""), str(sg or ""))
    return reqs or {}


def bulk_import_from_df(session: Session, df: pd.DataFrame, ruler_map: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None) -> Dict[str, int]:
    """
    Import all personnel + their current scores from the Excel DataFrame.
    Returns counts: added, skipped, errors.
    """
    added = skipped = errors = 0

    for idx, row in df.iterrows():
        sid = str(row.get("Staff ID", "")).strip()
        if not sid or sid in ("nan", "None", ""):
            # No Staff ID in source (e.g. blank rows) -> generate a stable synthetic ID
            name_slug = "".join(c if c.isalnum() else "_" for c in str(row.get("Name", "UNKNOWN")))
            sid = f"NOID-{name_slug[:40]}-{idx}"

        existing = session.query(Personnel).filter_by(staff_id=sid).first()

        # If the Staff ID is already used by a DIFFERENT person (e.g. shared
        # placeholder "UPTREX" ID across 20 trainees), mint a unique ID instead
        # of dropping this record.
        if existing and existing.name != row.get("Name"):
            sid = f"{sid}-{idx}"
            existing = session.query(Personnel).filter_by(staff_id=sid).first()

        sg_val = row.get("SG")
        if pd.isna(sg_val) or not sg_val:
            sg_val = POSITION_TO_SG.get(str(row.get("Staff Position", "")).strip(), "UNK")

        data = {
            "staff_id":           sid,
            "name":               row.get("Name"),
            "email":              row.get("Email Address"),
            "gender":             row.get("Gender"),
            "age":                row.get("Age"),
            "birth_year":         row.get("Birth Year"),
            "nationality":        row.get("Nationality"),
            "employment_category": row.get("Employment Category"),
            "department":         row.get("Department"),
            "section_name":       row.get("Section Name"),
            "unit_name":          row.get("Unit Name"),
            "sub_unit":           row.get("Sub Unit"),
            "staff_position":     row.get("Staff Position"),
            "sg":                 sg_val,
            "joining_date":       row.get("Joining Date"),
            "contract_expire_date": row.get("Contract Expire Date"),
            "years_in_pet":       row.get("Years in PET"),
            "years_re_experience": row.get("Years of RE Experience"),
            "sg_years":           row.get("Years in Salary Grade"),
            "sg_start_date":      row.get("Date of Appointment to Current Grade"),
            "age_promoted":       row.get("Age Promoted to Staff or Principal"),
            "current_assignment": row.get("Current Assignment / Loc:"),
            "assignment_date":    row.get("Date in Position"),
            "assignment_length":  row.get("Length in Current Assignment"),
            "chat_status":        row.get("Chat Status"),
            "chat_date":          row.get("Chat Date"),
            "assessment_level":   row.get("Assessment Level"),
            "last_assessment_date": row.get("Last Assesment Date"),
            "sub_disciplines":    row.get("Sub-Disciplines"),
            "potential":          row.get("Potential"),
            "strength":           row.get("Strength"),
            "recommendation":     row.get("Recommendation"),
            "resource_sme":       row.get("Resource/SME"),
            "interest":           row.get("Interest"),
            "preference":         row.get("Preference"),
            "comment":            row.get("Comment/Suggestion"),
            "assessor1":          row.get("Assesor1"),
            "assessor2":          row.get("Assessor2"),
            "supervisor":         row.get("Supervisor"),
            "remarks":            row.get("Remarks"),
        }

        if existing:
            # Update existing
            for k, v in data.items():
                if hasattr(existing, k):
                    setattr(existing, k, _safe(v))
            setattr(existing, "updated_at", datetime.utcnow())
            session.flush()
            pid = cast(int, existing.id)
            skipped += 1
        else:
            ok, msg, pid = add_personnel(session, data)
            if not ok:
                errors += 1
                continue
            added += 1

        if pid is None:
            continue

        # ── Import competency scores as a single assessment ──────────────────
        score_dict = {}
        from config import SCORE_COLS, REQ_COLS
        ruler_requirements = _build_ruler_requirements(row, ruler_map or {})
        for sc, rc in zip(SCORE_COLS, REQ_COLS):
            actual = _safe(row.get(sc))
            req = None
            if sc in ruler_requirements:
                req = _safe(ruler_requirements.get(sc))
            if req is None:
                req = _safe(row.get(rc))
            # NOTE: Excel's G--col uses (Requirement - Actual) convention.
            # We standardize internally to (Actual - Requirement): positive = exceeds target.
            actual_num = _coerce_numeric(actual)
            req_num = _coerce_numeric(req)
            gap = round(actual_num - req_num, 2) if (actual_num is not None and req_num is not None) else None
            if actual_num is not None or req_num is not None:
                score_dict[sc] = {"actual": actual_num, "req": req_num, "gap": gap}

        if score_dict:
            adate = _safe(row.get("Last Assesment Date")) or date.today()
            # Only create assessment if date is a valid date
            if not isinstance(adate, date):
                try:
                    adate = pd.to_datetime(adate).date()
                except Exception:
                    adate = date.today()

            # Check if assessment for that date already exists for this person
            existing_a = session.query(Assessment).filter_by(
                personnel_id=pid, assessment_date=adate
            ).first()

            if not existing_a:
                a = Assessment(
                    personnel_id=pid,
                    assessment_date=adate,
                    assessment_level=_safe(row.get("Assessment Level")),
                    assessor1=_safe(row.get("Assesor1")),
                    assessor2=_safe(row.get("Assessor2")),
                    supervisor=_safe(row.get("Supervisor")),
                )
                session.add(a)
                session.flush()
                add_competency_scores(session, cast(int, a.id), pid, score_dict)

        # ── Import summary scores ──────────────────────────────────────────
        sum_data = {
            "staff_base":       _safe(row.get("Staff Base")),
            "staff_keys":       _safe(row.get("Staff Keys")),
            "staff_pacing":     _safe(row.get("Staff Pacing")),
            "staff_emerging":   _safe(row.get("Staff Emerging")),
            "staff_cti":        _safe(row.get("Staff CTI")),
            "principal_base":   _safe(row.get("Principal Base")),
            "principal_keys":   _safe(row.get("Principal Keys")),
            "principal_pacing": _safe(row.get("Principal Pacing")),
            "principal_emerging": _safe(row.get("Principal Emerging")),
            "principal_cti":    _safe(row.get("Principal CTI")),
            "custodian_base":   _safe(row.get("Custodian Base")),
            "custodian_keys":   _safe(row.get("Custodian Keys")),
            "custodian_pacing": _safe(row.get("Custodian Pacing")),
            "custodian_emerging": _safe(row.get("Custodian Emerging")),
            "custodian_cti":    _safe(row.get("Custodian CTI")),
        }
        upsert_summary_score(session, pid, sum_data)

    try:
        session.commit()
    except Exception:
        session.rollback()

    return {"added": added, "updated": skipped, "errors": errors}

def bulk_import_cv_list(
    session,
    cv_df: pd.DataFrame,
) -> Dict[str, int]:
    """
    Import or update CV document records.

    A CV document is considered the same document when the
    personnel ID and SharePoint URL match. If no SharePoint URL
    exists, file name is used as the fallback identity.
    """
    result = {
        "added": 0,
        "updated": 0,
        "skipped": 0,
        "unmatched": 0,
        "errors": 0,
    }

    if cv_df is None or cv_df.empty:
        return result

    try:
        for _, cv_row in cv_df.iterrows():
            try:
                person, match_method = (
                    _find_person_for_cv(
                        session,
                        cv_row,
                    )
                )

                if person is None:
                    result["unmatched"] += 1
                    continue

                file_name = _safe(
                    cv_row.get(
                        "CV File Name"
                    )
                )

                sharepoint_url = _safe(
                    cv_row.get(
                        "SharePoint URL"
                    )
                )

                if not file_name:
                    result["skipped"] += 1
                    continue

                existing_query = (
                    session.query(CVDocument)
                    .filter(
                        CVDocument.personnel_id
                        == person.id
                    )
                )

                if sharepoint_url:
                    existing = (
                        existing_query
                        .filter(
                            CVDocument.sharepoint_url
                            == sharepoint_url
                        )
                        .first()
                    )
                else:
                    existing = (
                        existing_query
                        .filter(
                            CVDocument.file_name
                            == file_name
                        )
                        .first()
                    )

                document_values = {
                    "file_name": file_name,
                    "file_type": _safe(
                        cv_row.get("File Type")
                    ),
                    "cv_status": _safe(
                        cv_row.get("CV Status")
                    ),
                    "local_file_path": _safe(
                        cv_row.get(
                            "Local File Path"
                        )
                    ),
                    "local_file_url": _safe(
                        cv_row.get(
                            "Local File Link"
                        )
                    ),
                    "sharepoint_url":
                        sharepoint_url,
                    "modified_date": _safe(
                        cv_row.get(
                            "Modified Date"
                        )
                    ),
                    "match_method": (
                        f"{match_method}; "
                        f"{_safe(cv_row.get('Match Method')) or ''}"
                    ).strip("; "),
                    "notes": _safe(
                        cv_row.get("Notes")
                    ),
                    "source_name": _safe(
                        cv_row.get("Name")
                    ),
                    "source_staff_id":
                        _normalise_import_staff_id(
                            cv_row.get("Staff ID")
                        ),
                    "source_position": _safe(
                        cv_row.get(
                            "Staff Position"
                        )
                    ),
                }

                if existing:
                    for field_name, field_value in (
                        document_values.items()
                    ):
                        setattr(
                            existing,
                            field_name,
                            field_value,
                        )

                    existing.updated_at = (
                        datetime.utcnow()
                    )

                    result["updated"] += 1

                else:
                    document = CVDocument(
                        personnel_id=person.id,
                        **document_values,
                    )

                    session.add(document)

                    result["added"] += 1

            except Exception:
                result["errors"] += 1

        session.commit()

    except Exception:
        session.rollback()
        raise

    return result

# ── Analytics helpers ─────────────────────────────────────────────────────────

def get_wide_dataframe(session: Session) -> pd.DataFrame:
    """
    Reconstruct a 'wide' DataFrame (one row per person) with columns:
    Name, Staff Position, SG, Department, Age, Chat Status,
    B1..E2 (latest actual), R-B1..R-E2 (latest requirement), G--B1..G--E2 (latest gap)
    and summary score columns such as Staff Base / Principal Base.
    Used by analytics.py for heatmaps, gaps, readiness, scatter and the individual
    assessment summary section.
    """
    people = session.query(Personnel).filter_by(is_deleted=False).all()
    rows = []
    for p in people:
        row = {
            "id": p.id,
            "Name": p.name,
            "Staff ID": p.staff_id,
            "Staff Position": p.staff_position,
            "SG": p.sg,
            "Department": p.department,
            "Section Name": p.section_name,
            "Current Assignment / Loc:": p.current_assignment,
            "Unit Name": p.unit_name,
            "Age": p.age,
            "Gender": p.gender,
            "Chat Status": p.chat_status or "No Need",
            "Years in PET": p.years_in_pet,
        }
        # latest assessment
        latest = (
            session.query(Assessment)
            .filter_by(personnel_id=p.id)
            .order_by(Assessment.assessment_date.desc())
            .first()
        )
        if latest:
            for s in latest.scores:
                row[s.competency_code] = s.actual_score
                row[f"R-{s.competency_code}"] = s.requirement_score
                row[f"G--{s.competency_code}"] = s.gap_score

        summary = (
            session.query(SummaryScore)
            .filter_by(personnel_id=p.id)
            .order_by(SummaryScore.updated_at.desc(), SummaryScore.created_at.desc())
            .first()
        )
        if summary is not None:
            summary_columns = {
                "staff_base": "Staff Base",
                "staff_keys": "Staff Keys",
                "staff_pacing": "Staff Pacing",
                "staff_emerging": "Staff Emerging",
                "staff_cti": "Staff CTI",
                "principal_base": "Principal Base",
                "principal_keys": "Principal Keys",
                "principal_pacing": "Principal Pacing",
                "principal_emerging": "Principal Emerging",
                "principal_cti": "Principal CTI",
                "custodian_base": "Custodian Base",
                "custodian_keys": "Custodian Keys",
                "custodian_pacing": "Custodian Pacing",
                "custodian_emerging": "Custodian Emerging",
                "custodian_cti": "Custodian CTI",
            }
            for attr, display_name in summary_columns.items():
                value = getattr(summary, attr, None)
                if value is not None:
                    row[display_name] = value
        cv_count = (
            session.query(CVDocument)
            .filter( CVDocument.personnel_id == p.id ).count() )

        row["CV Available"] = ( "Yes" if cv_count > 0 else "No")

        row["CV Document Count"] = ( cv_count )
        rows.append(row)

    return pd.DataFrame(rows)


def get_stats_overview(session: Session) -> Dict:
    total   = session.query(Personnel).filter_by(is_deleted=False).count()
    yes_cnt = session.query(Personnel).filter_by(chat_status="Yes",  is_deleted=False).count()
    no_cnt  = session.query(Personnel).filter_by(chat_status="No",   is_deleted=False).count()
    nn_cnt  = session.query(Personnel).filter_by(chat_status="No Need", is_deleted=False).count()
    return {
        "total": total,
        "chat_yes": yes_cnt,
        "chat_no": no_cnt,
        "chat_no_need": nn_cnt,
    }
def get_cv_documents(
    session,
    personnel_id: int,
) -> pd.DataFrame:
    """
    Return all CV documents for the selected personnel.
    """
    documents = (
        session.query(CVDocument)
        .filter(
            CVDocument.personnel_id
            == personnel_id
        )
        .order_by(
            CVDocument.modified_date.desc(),
            CVDocument.id.desc(),
        )
        .all()
    )

    records = []

    for document in documents:
        records.append(
            {
                "id": document.id,
                "Personnel ID":
                    document.personnel_id,
                "CV Status":
                    document.cv_status,
                "CV File Name":
                    document.file_name,
                "File Type":
                    document.file_type,
                "SharePoint URL":
                    document.sharepoint_url,
                "Modified Date":
                    document.modified_date,
                "Match Method":
                    document.match_method,
                "Notes":
                    document.notes,
            }
        )

    return pd.DataFrame(records)

def get_cv_stats(
    session,
) -> Dict[str, int]:
    """
    Return CV coverage statistics.
    """
    total_personnel = (
        session.query(Personnel)
        .filter(
            Personnel.is_deleted.is_(False)
        )
        .count()
    )

    personnel_with_cv = (
        session.query(
            CVDocument.personnel_id
        )
        .distinct()
        .count()
    )

    total_documents = (
        session.query(CVDocument)
        .count()
    )

    return {
        "total": total_personnel,
        "personnel_with_cv": personnel_with_cv,
        "personnel_without_cv": max(
            total_personnel - personnel_with_cv,
            0,
        ),
        "total_documents": total_documents,
    }