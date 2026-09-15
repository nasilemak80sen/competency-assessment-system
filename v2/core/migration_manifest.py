"""Function-level migration ledger for the legacy app.py inventory.

The root app.py remains the behavioural reference until every workflow has
passed static, behavioural, and UI regression checks.
"""
from __future__ import annotations
from dataclasses import dataclass

TOTAL_LEGACY_FUNCTIONS = 75

@dataclass(frozen=True)
class MigrationItem:
    legacy: str
    v2_boundary: str
    phase: str = "A"
    status: str = "boundary"
    parity: str = "delegates unchanged"

PHASE_A_BATCH_1 = (
    MigrationItem("add_personnel", "v2.services.personnel_service.add"),
    MigrationItem("update_personnel", "v2.services.personnel_service.update"),
    MigrationItem("delete_personnel", "v2.services.personnel_service.delete"),
    MigrationItem("get_all_personnel", "v2.services.personnel_service.all"),
    MigrationItem("get_personnel_by_id", "v2.services.personnel_service.by_id"),
    MigrationItem("search_personnel", "v2.services.personnel_service.search"),
    MigrationItem("add_assessment", "v2.services.assessment_service.add_assessment"),
    MigrationItem("add_competency_scores", "v2.services.assessment_service.add_competency_scores"),
    MigrationItem("bulk_import_from_df", "v2.services.import_service.bulk_import_from_dataframe"),
    MigrationItem("bulk_import_cv_list", "v2.services.import_service.bulk_import_cv_list"),
)

PHASE_A_BATCH_2 = (
    MigrationItem("_safe_numeric", "v2.analytics.competency._safe_numeric", status="static", parity="logic extracted unchanged"),
    MigrationItem("_get_competency_display_name", "v2.analytics.competency._get_competency_display_name", status="static", parity="logic extracted unchanged"),
    MigrationItem("_get_all_competency_strengths", "v2.analytics.competency._get_all_competency_strengths", status="static", parity="logic extracted unchanged"),
)

PHASE_A_BATCH_3 = (
    MigrationItem("_grade_rank", "v2.analytics.readiness._grade_rank", status="static", parity="logic extracted unchanged"),
    MigrationItem("_safe_display_value", "v2.analytics.readiness._safe_display_value", status="static", parity="logic extracted unchanged"),
    MigrationItem("_safe_integer_display", "v2.analytics.readiness._safe_integer_display", status="static", parity="logic extracted unchanged"),
    MigrationItem("_safe_date_display", "v2.analytics.readiness._safe_date_display", status="static", parity="logic extracted unchanged"),
    MigrationItem("_get_assessment_status", "v2.analytics.readiness._get_assessment_status", status="static", parity="logic extracted unchanged"),
)

PHASE_A_BATCH_4 = (
    MigrationItem("_rg_clean_value", "v2.analytics.readiness._rg_clean_value", status="static", parity="logic extracted unchanged"),
    MigrationItem("_rg_grade_rank", "v2.analytics.readiness._rg_grade_rank", status="static", parity="logic extracted unchanged"),
    MigrationItem("_rg_sort_salary_grades", "v2.analytics.readiness._rg_sort_salary_grades", status="static", parity="logic extracted unchanged"),
    MigrationItem("_rg_normalize_ruler", "v2.analytics.readiness._rg_normalize_ruler", status="static", parity="logic extracted unchanged"),
    MigrationItem("_rg_get_person_ruler", "v2.analytics.readiness._rg_get_person_ruler", status="static", parity="logic extracted unchanged"),
    MigrationItem("_rg_get_competency_category", "v2.analytics.readiness._rg_get_competency_category", status="static", parity="logic extracted unchanged"),
    MigrationItem("_rg_gap_severity", "v2.analytics.readiness._rg_gap_severity", status="static", parity="logic extracted unchanged"),
    MigrationItem("_rg_determine_target_sg", "v2.analytics.readiness._rg_determine_target_sg", status="static", parity="logic extracted unchanged"),
    MigrationItem("_build_readiness_detail_dataframe", "v2.analytics.readiness._build_readiness_detail_dataframe", status="static", parity="logic extracted unchanged"),
    MigrationItem("_classify_readiness_status", "v2.analytics.readiness._classify_readiness_status", status="static", parity="logic extracted unchanged"),
    MigrationItem("_recommend_readiness_action", "v2.analytics.readiness._recommend_readiness_action", status="static", parity="logic extracted unchanged"),
    MigrationItem("_find_top_personnel_gap", "v2.analytics.readiness._find_top_personnel_gap", status="static", parity="logic extracted unchanged"),
    MigrationItem("_build_personnel_readiness_summary", "v2.analytics.readiness._build_personnel_readiness_summary", status="static", parity="logic extracted unchanged"),
    MigrationItem("_apply_readiness_personnel_filters", "v2.analytics.readiness._apply_readiness_personnel_filters", status="static", parity="logic extracted unchanged"),
)

PHASE_A_MIGRATED_COUNT = sum(len(batch) for batch in (PHASE_A_BATCH_1, PHASE_A_BATCH_2, PHASE_A_BATCH_3, PHASE_A_BATCH_4))
PHASE_A_BOUNDARY_COUNT = len(PHASE_A_BATCH_1)
PHASE_A_STATIC_COUNT = PHASE_A_MIGRATED_COUNT - PHASE_A_BOUNDARY_COUNT

if PHASE_A_MIGRATED_COUNT > TOTAL_LEGACY_FUNCTIONS:
    raise RuntimeError("Phase A migration count exceeds the legacy inventory")
