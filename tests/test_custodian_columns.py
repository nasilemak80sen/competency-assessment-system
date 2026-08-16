import os
import pytest
from config import EXCEL_PATH
from data_loader import load_master_data


def test_custodian_summary_columns_present():
    if not os.path.exists(EXCEL_PATH):
        pytest.skip("Excel workbook not available: {}".format(EXCEL_PATH))
    df = load_master_data(EXCEL_PATH)
    expected = [
        "Custodian Base",
        "Custodian Keys",
        "Custodian Pacing",
        "Custodian Emerging",
        "Custodian CTI",
    ]
    for col in expected:
        assert col in df.columns, f"Missing expected summary column: {col}"
