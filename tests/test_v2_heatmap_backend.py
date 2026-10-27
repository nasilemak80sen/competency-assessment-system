from __future__ import annotations

from pathlib import Path

import pandas as pd

from v2.services.heatmap_service import (
    classify_employment_type,
    merge_database_personnel_for_heatmap,
)


ROOT = Path(__file__).resolve().parents[1]


def test_heatmap_merge_keeps_database_only_personnel_and_reconciles_current_fields():
    workbook = pd.DataFrame(
        [
            {
                "Name": "Workbook Person",
                "Staff ID": "1001",
                "Department": "DPE",
                "Employment Category": "Permanent",
                "B1": 2,
            },
            {
                "Name": "DB Updated Person",
                "Staff ID": "1002",
                "Department": "Workbook Department",
                "Employment Category": "Permanent",
                "B1": 1,
            },
        ]
    )
    database_records = [
        {
            "staff_id": "1002",
            "name": "DB Updated Person",
            "department": "PSR",
            "employment_category": "CDH",
            "staff_position": "Staff",
            "sg": "P5",
            "db_scores": {"B1": 5},
        },
        {
            "staff_id": "1003",
            "name": "Database Only Person",
            "department": "PSR",
            "employment_category": "Permanent Staff",
            "staff_position": "Staff",
            "sg": "P5",
            "db_scores": {},
        },
    ]

    merged = merge_database_personnel_for_heatmap(workbook, database_records)

    assert len(merged) == 3
    db_updated = merged.loc[merged["Staff ID"] == "1002"].iloc[0]
    assert db_updated["Department"] == "PSR"
    assert db_updated["Employment Category"] == "CDH"
    assert db_updated["Employment Type Filter"] == "CDH"
    assert float(db_updated["B1"]) == 5

    db_only = merged.loc[merged["Staff ID"] == "1003"].iloc[0]
    assert db_only["Name"] == "Database Only Person"
    assert db_only["Employment Category"] == "Permanent Staff"
    assert db_only["Employment Type Filter"] == "Permanent"
    assert pd.isna(db_only["B1"]), "Unassessed DB-only personnel should remain with blank score cells"


def test_heatmap_merge_matches_staff_ids_after_numeric_format_drift():
    workbook = pd.DataFrame(
        [{"Name": "One Person", "Staff ID": "1234.0", "Department": "DPE", "B1": 2}]
    )
    database_records = [
        {
            "staff_id": "1234",
            "name": "One Person (database)",
            "department": "PSR",
            "employment_category": "CDH",
            "db_scores": {"B1": 4},
        }
    ]

    merged = merge_database_personnel_for_heatmap(workbook, database_records)

    assert len(merged) == 1, "A numeric/string Staff ID mismatch must not create a duplicate person"
    assert merged.iloc[0]["Name"] == "One Person (database)"
    assert merged.iloc[0]["Department"] == "PSR"
    assert float(merged.iloc[0]["B1"]) == 4


def test_employment_type_filter_normalises_cdh_and_permanent_variants():
    assert classify_employment_type("CDH") == "CDH"
    assert classify_employment_type("CDH Staff") == "CDH"
    assert classify_employment_type("Permanent") == "Permanent"
    assert classify_employment_type("Permanent Staff") == "Permanent"
    assert classify_employment_type("perm") == "Permanent"
    assert classify_employment_type("Contract") == "Contract"
    assert classify_employment_type(None) == "Not specified"


def test_heatmap_keeps_unassessed_people_and_uses_database_reconciled_dataset():
    source = (ROOT / "v2/pages/03_Competency_Heatmap.py").read_text(encoding="utf-8")
    assert "df = get_heatmap_data()" in source
    assert '"Employment Type"' in source
    assert 'fdf["Employment Type Filter"].isin(f_employment)' in source
    assert 'heatmap_data = heatmap_data[heatmap_data[value_cols].notna().any(axis=1)]' not in source

    backend = (ROOT / "v2/core/bootstrap.py").read_text(encoding="utf-8")
    assert "merge_database_personnel_for_heatmap(workbook_df, records)" in backend
    assert "Personnel.is_deleted.is_(False), Personnel.is_deleted.is_(None)" in backend
