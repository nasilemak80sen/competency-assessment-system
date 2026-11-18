"""Assessment service boundary.

The legacy db_ops assessment functions remain available for existing callers.
The new save_assessment_transaction operation owns the complete assessment
write so the header, competency scores, and personnel summary commit together.
"""

from datetime import date, datetime
import json
import math
from typing import Dict, Optional, Tuple

import db_ops
from config import SCORE_COLS
from models import Assessment, AuditLog, CompetencyScore, Personnel


def add_assessment(session, personnel_id: int, data: Dict) -> Tuple[bool, str, Optional[int]]:
    """Backward-compatible wrapper for the legacy assessment-header operation."""
    return db_ops.add_assessment(session, personnel_id, data)


def add_competency_scores(
    session,
    assessment_id: Optional[int],
    personnel_id: Optional[int],
    scores: Dict[str, Dict],
) -> Tuple[bool, str]:
    """Backward-compatible wrapper for the legacy competency-score operation."""
    return db_ops.add_competency_scores(session, assessment_id, personnel_id, scores)


def _validated_score(value, code: str, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{code} {field} must be a numeric score from 0 to 5.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{code} {field} must be a numeric score from 0 to 5.")
    if not math.isfinite(number) or not 0.0 <= number <= 5.0:
        raise ValueError(f"{code} {field} must be between 0 and 5.")
    return number


def save_assessment_transaction(
    session,
    personnel_id: int,
    assessment_data: Dict,
    scores: Dict[str, Dict],
    actor: dict | None = None,
) -> Tuple[bool, str, Optional[int]]:
    """Save one assessment header and its complete competency matrix atomically.

    All validation occurs before writes. The ORM objects are flushed as needed
    for generated IDs, but the session is committed exactly once. Any failure
    rolls back the header, all scores, and the Personnel summary update.
    """
    try:
        if not isinstance(assessment_data, dict):
            return False, "Assessment details are required.", None
        if not isinstance(scores, dict):
            return False, "Competency scores must be provided as a mapping.", None

        expected_codes = set(SCORE_COLS)
        submitted_codes = set(scores)
        missing_codes = sorted(expected_codes - submitted_codes)
        unknown_codes = sorted(submitted_codes - expected_codes)
        if missing_codes or unknown_codes:
            details = []
            if missing_codes:
                details.append("missing: " + ", ".join(missing_codes))
            if unknown_codes:
                details.append("unknown: " + ", ".join(unknown_codes))
            return False, "The competency matrix is incomplete (" + "; ".join(details) + ").", None

        assessment_date = assessment_data.get("assessment_date")
        if isinstance(assessment_date, datetime):
            assessment_date = assessment_date.date()
        if not isinstance(assessment_date, date):
            return False, "A valid assessment date is required.", None

        validated_scores = {}
        for code in SCORE_COLS:
            values = scores.get(code)
            if not isinstance(values, dict):
                return False, f"Scores for {code} are missing.", None
            actual = _validated_score(values.get("actual"), code, "actual")
            requirement = _validated_score(values.get("req"), code, "target")
            gap = round(max(requirement - actual, 0.0), 2)
            achievement_pct = (
                round(actual / requirement * 100.0, 1)
                if requirement > 0
                else None
            )
            validated_scores[code] = {
                "actual": actual,
                "requirement": requirement,
                "gap": gap,
                "achievement_pct": achievement_pct,
            }

        person = (
            session.query(Personnel)
            .filter(
                Personnel.id == int(personnel_id),
                Personnel.is_deleted.is_not(True),
            )
            .first()
        )
        if person is None:
            return False, "The selected personnel record is unavailable or archived.", None

        assessment_level = assessment_data.get("assessment_level") or None
        assessment = Assessment(
            personnel_id=person.id,
            assessment_date=assessment_date,
            assessment_level=assessment_level,
            assessor1=assessment_data.get("assessor1") or None,
            assessor2=assessment_data.get("assessor2") or None,
            supervisor=assessment_data.get("supervisor") or None,
            remarks=assessment_data.get("remarks") or None,
        )
        session.add(assessment)
        session.flush()

        for code in SCORE_COLS:
            values = validated_scores[code]
            session.add(
                CompetencyScore(
                    assessment_id=assessment.id,
                    personnel_id=person.id,
                    competency_code=code,
                    competency_type=code[0],
                    actual_score=values["actual"],
                    requirement_score=values["requirement"],
                    gap_score=values["gap"],
                    achievement_pct=values["achievement_pct"],
                )
            )

        # Keep the established Personnel summary fields aligned with the new
        # latest assessment, but commit them in the same transaction.
        person.assessment_level = assessment_level
        person.last_assessment_date = assessment_date
        person.updated_at = datetime.utcnow()

        actor_name = "system"
        actor_display_name = None
        if isinstance(actor, dict):
            actor_name = str(actor.get("username") or actor.get("display_name") or "system")[:100]
            actor_display_name = actor.get("display_name")
        session.add(
            AuditLog(
                entity_type="Assessment",
                entity_id=int(assessment.id),
                action="CREATE",
                changed_by=actor_name,
                old_values=json.dumps({}, ensure_ascii=False),
                new_values=json.dumps(
                    {
                        "personnel_id": int(person.id),
                        "assessment_date": assessment_date.isoformat(),
                        "assessment_level": assessment_level,
                        "assessor1": assessment.assessor1,
                        "assessor2": assessment.assessor2,
                        "supervisor": assessment.supervisor,
                        "score_count": len(validated_scores),
                        "actor_display_name": actor_display_name,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            )
        )
        session.commit()
        return True, f"Assessment saved with all {len(validated_scores)} competency scores.", int(assessment.id)
    except Exception as exc:
        session.rollback()
        return False, f"Assessment was not saved. Transaction rolled back: {exc}", None


def get_assessment_history(session, personnel_id: int):
    """Return one summary row per assessment, newest first, including empty history rows."""
    assessments = (
        session.query(Assessment)
        .filter(Assessment.personnel_id == int(personnel_id))
        .order_by(
            Assessment.assessment_date.is_(None),
            Assessment.assessment_date.desc(),
            Assessment.id.desc(),
        )
        .all()
    )

    history = []
    for assessment in assessments:
        score_rows = list(assessment.scores or [])

        def average(attribute):
            values = [
                float(getattr(record, attribute))
                for record in score_rows
                if getattr(record, attribute) is not None
            ]
            return round(sum(values) / len(values), 2) if values else None

        history.append(
            {
                "id": int(assessment.id),
                "assessment_date": assessment.assessment_date,
                "assessment_level": assessment.assessment_level,
                "assessor1": assessment.assessor1,
                "assessor2": assessment.assessor2,
                "supervisor": assessment.supervisor,
                "remarks": assessment.remarks,
                "score_count": len(score_rows),
                "average_actual": average("actual_score"),
                "average_target": average("requirement_score"),
                "average_gap": average("gap_score"),
            }
        )
    return history


def get_assessment_scores(session, assessment_id: int):
    """Return a historical score matrix keyed by competency code."""
    records = (
        session.query(CompetencyScore)
        .filter(CompetencyScore.assessment_id == int(assessment_id))
        .order_by(CompetencyScore.competency_code)
        .all()
    )
    return {
        record.competency_code: {
            "actual": record.actual_score,
            "req": record.requirement_score,
            "gap": record.gap_score,
            "achievement_pct": record.achievement_pct,
        }
        for record in records
    }
