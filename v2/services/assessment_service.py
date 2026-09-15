"""Assessment service boundary.

Delegates to the proven db_ops persistence functions so the migration does
not alter assessment creation or competency-score rules.
"""

from typing import Dict, Optional, Tuple

import db_ops


def add_assessment(session, personnel_id: int, data: Dict) -> Tuple[bool, str, Optional[int]]:
    return db_ops.add_assessment(session, personnel_id, data)


def add_competency_scores(
    session,
    assessment_id: Optional[int],
    personnel_id: Optional[int],
    scores: Dict[str, Dict],
) -> Tuple[bool, str]:
    return db_ops.add_competency_scores(session, assessment_id, personnel_id, scores)
