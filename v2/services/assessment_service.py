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
from models import Assessment, AssessmentImportBatch, AuditLog, CompetencyScore, Personnel


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
            assessment_type=assessment_data.get("assessment_type") or None,
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
                    self_rating=values.get("self_rating"),
                    evidence=values.get("evidence"),
                    assessor_comments=values.get("assessor_comments"),
                    superior_comments=values.get("superior_comments"),
                    assessor_approval=values.get("assessor_approval"),
                    superior_approval=values.get("superior_approval"),
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




def create_reviewed_assessment_import(
    session,
    *,
    personnel_id: int,
    operation: str,
    target_assessment_id: int | None,
    source_filename: str,
    source_sha256: str,
    payload: Dict,
    actor: dict | None = None,
) -> int:
    """Persist a parsed and human-reviewed assessment import for approval."""
    if operation not in {"create", "revise"}:
        raise ValueError("Assessment import operation must be create or revise.")
    if operation == "revise" and target_assessment_id is None:
        raise ValueError("Select an existing assessment to revise.")
    person = (
        session.query(Personnel)
        .filter(
            Personnel.id == int(personnel_id),
            Personnel.is_deleted.is_not(True),
        )
        .first()
    )
    if person is None:
        raise ValueError("The selected personnel record is unavailable.")
    if operation == "revise":
        target = (
            session.query(Assessment)
            .filter_by(id=int(target_assessment_id), personnel_id=int(personnel_id))
            .first()
        )
        if target is None:
            raise ValueError("The selected assessment does not belong to this personnel record.")
    actor_name = "system"
    if isinstance(actor, dict):
        actor_name = str(
            actor.get("username") or actor.get("display_name") or "system"
        )[:120]
    batch = AssessmentImportBatch(
        personnel_id=int(personnel_id),
        target_assessment_id=int(target_assessment_id) if target_assessment_id else None,
        operation=operation,
        status="reviewed",
        source_filename=str(source_filename)[:500],
        source_sha256=str(source_sha256)[:64],
        payload_json=json.dumps(payload, ensure_ascii=False, default=str),
        uploaded_by=actor_name,
        reviewed_by=actor_name,
        reviewed_at=datetime.utcnow(),
    )
    session.add(batch)
    session.commit()
    return int(batch.id)


def apply_reviewed_assessment_import(
    session,
    batch_id: int,
    actor: dict | None = None,
) -> Tuple[bool, str, Optional[int]]:
    """Apply a reviewed assessment import atomically and mark it approved.

    New assessments receive a complete 24-code matrix, with genuinely missing
    source values remaining NULL. Revisions update only competency codes
    explicitly supplied with a valid Final Rating, preserving unmentioned codes.
    """
    try:
        batch = (
            session.query(AssessmentImportBatch)
            .filter(AssessmentImportBatch.id == int(batch_id))
            .first()
        )
        if batch is None:
            return False, "The assessment import batch was not found.", None
        if batch.status != "reviewed":
            return False, f"This assessment import is {batch.status!r}, not awaiting approval.", None

        person = (
            session.query(Personnel)
            .filter(
                Personnel.id == int(batch.personnel_id),
                Personnel.is_deleted.is_not(True),
            )
            .first()
        )
        if person is None:
            return False, "The selected personnel record is unavailable or archived.", None

        payload = json.loads(batch.payload_json or "{}")
        metadata = payload.get("metadata") or {}
        source_scores = payload.get("scores") or {}
        if not isinstance(source_scores, dict) or not source_scores:
            return False, "There are no competency Final Ratings ready to import.", None

        validated = {}
        for code, values in source_scores.items():
            if code not in SCORE_COLS or not isinstance(values, dict):
                return False, f"Invalid competency import record: {code}.", None
            final_rating = values.get("final_rating")
            actual = (
                _validated_score(final_rating, code, "final rating")
                if final_rating not in (None, "")
                else None
            )
            self_rating = values.get("self_rating")
            self_rating = (
                _validated_score(self_rating, code, "self rating")
                if self_rating not in (None, "")
                else None
            )
            requirement = values.get("req")
            requirement = (
                _validated_score(requirement, code, "target")
                if requirement not in (None, "")
                else None
            )
            gap = (
                round(max(requirement - actual, 0.0), 2)
                if requirement is not None and actual is not None
                else None
            )
            achievement = (
                round(actual / requirement * 100.0, 1)
                if actual is not None and requirement is not None and requirement > 0
                else None
            )
            narrative = {
                "evidence": values.get("evidence") or None,
                "assessor_comments": values.get("assessor_comments") or None,
                "superior_comments": values.get("superior_comments") or None,
                "assessor_approval": values.get("assessor_approval") or None,
                "superior_approval": values.get("superior_approval") or None,
            }
            if actual is None and self_rating is None and not any(narrative.values()):
                continue
            validated[code] = {
                "actual": actual,
                "self_rating": self_rating,
                "requirement": requirement,
                "gap": gap,
                "old_ti_score": (
                    _validated_score(values.get("old_ti_score"), code, "old TI score")
                    if values.get("old_ti_score") not in (None, "") else None
                ),
                "mapping_guideline": values.get("mapping_guideline") or None,
                "grade_comparisons": values.get("grade_comparisons") or {},
                "achievement_pct": achievement,
                **narrative,
            }
        if not validated or not any(value["actual"] is not None for value in validated.values()):
            return False, "At least one valid Final Rating is required. Nothing was changed.", None

        assessment_date = metadata.get("assessment_date")
        if isinstance(assessment_date, str) and assessment_date.strip():
            try:
                assessment_date = date.fromisoformat(assessment_date[:10])
            except ValueError:
                return False, "Assessment date must be a valid ISO date.", None
        elif not assessment_date:
            assessment_date = None
        elif isinstance(assessment_date, datetime):
            assessment_date = assessment_date.date()

        actor_name = "system"
        actor_display_name = None
        if isinstance(actor, dict):
            actor_name = str(
                actor.get("username") or actor.get("display_name") or "system"
            )[:100]
            actor_display_name = actor.get("display_name")

        if batch.operation == "create":
            assessment = Assessment(
                personnel_id=person.id,
                assessment_date=assessment_date,
                assessment_level=metadata.get("assessment_level") or None,
                assessment_type=metadata.get("assessment_type") or None,
                assessor1=metadata.get("assessor1") or None,
                assessor2=metadata.get("assessor2") or None,
                supervisor=metadata.get("supervisor") or None,
                remarks=metadata.get("remarks") or None,
            )
            session.add(assessment)
            session.flush()
            existing_by_code = {}
            # Keep the matrix structurally complete, but leave absent source
            # scores NULL so they remain clearly "not assessed".
            for code in SCORE_COLS:
                record = CompetencyScore(
                    assessment_id=assessment.id,
                    personnel_id=person.id,
                    competency_code=code,
                    competency_type=code[0],
                )
                session.add(record)
                existing_by_code[code] = record
        elif batch.operation == "revise":
            assessment = (
                session.query(Assessment)
                .filter_by(
                    id=int(batch.target_assessment_id),
                    personnel_id=int(person.id),
                )
                .first()
            )
            if assessment is None:
                return False, "The assessment selected for revision no longer exists.", None
            old_header = {
                "assessment_date": assessment.assessment_date,
                "assessment_level": assessment.assessment_level,
                "assessment_type": assessment.assessment_type,
                "assessor1": assessment.assessor1,
                "assessor2": assessment.assessor2,
                "supervisor": assessment.supervisor,
                "remarks": assessment.remarks,
            }
            existing_by_code = {
                record.competency_code: record
                for record in assessment.scores
            }
            # Blank metadata in a source file does not erase existing values.
            if assessment_date is not None:
                assessment.assessment_date = assessment_date
            for field in ("assessment_level", "assessment_type", "assessor1", "assessor2", "supervisor", "remarks"):
                value = metadata.get(field)
                if value not in (None, ""):
                    setattr(assessment, field, value)
        else:
            return False, "Unknown assessment import operation.", None

        old_score_values = {}
        for code, values in validated.items():
            record = existing_by_code.get(code)
            if record is None:
                record = CompetencyScore(
                    assessment_id=assessment.id,
                    personnel_id=person.id,
                    competency_code=code,
                    competency_type=code[0],
                )
                session.add(record)
                existing_by_code[code] = record
            old_score_values[code] = {
                "actual": record.actual_score,
                "requirement": record.requirement_score,
                "gap": record.gap_score,
                "self_rating": record.self_rating,
                "old_ti_score": record.old_ti_score,
                "mapping_guideline": record.mapping_guideline,
                "grade_comparisons": record.grade_comparisons_json,
            }
            if values["actual"] is not None:
                record.actual_score = values["actual"]
            if values["self_rating"] is not None:
                record.self_rating = values["self_rating"]
            if values["old_ti_score"] is not None:
                record.old_ti_score = values["old_ti_score"]
            if values["mapping_guideline"] is not None:
                record.mapping_guideline = values["mapping_guideline"]
            if values["grade_comparisons"]:
                record.grade_comparisons_json = json.dumps(
                    values["grade_comparisons"], ensure_ascii=False, default=str
                )
            if values["requirement"] is not None:
                record.requirement_score = values["requirement"]
            if record.actual_score is not None and record.requirement_score is not None:
                record.gap_score = round(
                    max(record.requirement_score - record.actual_score, 0.0), 2
                )
                record.achievement_pct = (
                    round(record.actual_score / record.requirement_score * 100.0, 1)
                    if record.requirement_score > 0 else None
                )
            else:
                record.gap_score = None
                record.achievement_pct = None
            # Preserve previously saved narrative details when the source
            # does not contain a value, rather than wiping useful evidence.
            for field in (
                "evidence", "assessor_comments", "superior_comments",
                "assessor_approval", "superior_approval",
            ):
                if values.get(field) not in (None, ""):
                    setattr(record, field, values[field])

        if metadata.get("assessment_level"):
            person.assessment_level = metadata["assessment_level"]
        if assessment.assessment_date is not None:
            person.last_assessment_date = assessment.assessment_date
        person.updated_at = datetime.utcnow()

        batch.status = "approved"
        batch.approved_by = actor_name
        batch.approved_at = datetime.utcnow()
        audit_action = "CREATE" if batch.operation == "create" else "UPDATE"
        new_score_values = {
            code: {
                "actual": values["actual"],
                "self_rating": values["self_rating"],
                "old_ti_score": values["old_ti_score"],
                "mapping_guideline": values["mapping_guideline"],
                "grade_comparisons": values["grade_comparisons"],
                "requirement": (
                    existing_by_code[code].requirement_score
                    if code in existing_by_code else None
                ),
                "gap": existing_by_code[code].gap_score if code in existing_by_code else None,
            }
            for code, values in validated.items()
        }
        session.add(
            AuditLog(
                entity_type="Assessment",
                entity_id=int(assessment.id),
                action=audit_action,
                changed_by=actor_name,
                old_values=json.dumps(
                    old_score_values if batch.operation == "revise" else {},
                    ensure_ascii=False,
                    default=str,
                ),
                new_values=json.dumps(
                    {
                        "personnel_id": int(person.id),
                        "assessment_id": int(assessment.id),
                        "operation": batch.operation,
                        "source_filename": batch.source_filename,
                        "source_sha256": batch.source_sha256,
                        "score_updates": new_score_values,
                        "score_count": len(validated),
                        "actor_display_name": actor_display_name,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            )
        )
        session.commit()
        action_word = "created" if batch.operation == "create" else "revised"
        return (
            True,
            f"Assessment #{assessment.id} {action_word} for {person.name}. "
            f"{len(validated)} competency ratings were applied.",
            int(assessment.id),
        )
    except Exception as exc:
        session.rollback()
        return False, f"Assessment import was not approved. Transaction rolled back: {exc}", None


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
                "assessment_type": assessment.assessment_type,
                "assessor1": assessment.assessor1,
                "assessor2": assessment.assessor2,
                "supervisor": assessment.supervisor,
                "remarks": assessment.remarks,
                "score_count": sum(
                    1 for record in score_rows if record.actual_score is not None
                ),
                "matrix_count": len(score_rows),
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
            "self_rating": record.self_rating,
            "old_ti_score": record.old_ti_score,
            "mapping_guideline": record.mapping_guideline,
            "grade_comparisons": (
                json.loads(record.grade_comparisons_json)
                if record.grade_comparisons_json else {}
            ),
            "evidence": record.evidence,
            "assessor_comments": record.assessor_comments,
            "superior_comments": record.superior_comments,
            "assessor_approval": record.assessor_approval,
            "superior_approval": record.superior_approval,
        }
        for record in records
    }
