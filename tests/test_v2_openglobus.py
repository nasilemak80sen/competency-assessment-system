"""Backend contract and HTML packaging tests for the OpenGlobus component."""
from __future__ import annotations
import pandas as pd
import pytest
from v2.components.openglobus import OPEN_GLOBUS_VERSION, _build_openglobus_html
from v2.services.geospatial_service import (
    GEOSPATIAL_DATASET_TYPE, GEOSPATIAL_SCHEMA_VERSION,
    build_nationality_dataset, validate_nationality_dataset,
)


def _sample_map_df():
    return pd.DataFrame({
        "Nationality": ["Malaysian", "British", "Indonesian"],
        "Personnel Count": [2, 1, 1],
        "Latitude": [4.2105, 55.3781, -0.7893],
        "Longitude": [101.9758, -3.4360, 113.9213],
        "Representation": [50.0, 25.0, 25.0],
        "Representation Display": ["50.0%", "25.0%", "25.0%"],
    })


def _sample_people_df():
    return pd.DataFrame({
        "Nationality": ["Malaysian", "British", "Indonesian", "Malaysian"],
        "Name": ["A", "B", "C", "D"],
        "Staff Position": ["Engineer", "Geologist", "Engineer", "Manager"],
        "Department": ["RE"] * 4, "SG": ["P5", "P6", "P5", "P7"],
        "Employment Category": ["PERMANENT", "CDH", "PERMANENT", "PERMANENT"],
        "Section Name": ["A", "B", "A", "C"],
        "Staff ID": ["001", "002", "003", "004"],
        "Current Location:": ["Office 1", "Office 2", "Office 3", "Office 4"],
    })


def test_dataset_contract_contains_aggregate_and_detail_records():
    dataset = build_nationality_dataset(_sample_map_df(), _sample_people_df())
    assert dataset["schemaVersion"] == GEOSPATIAL_SCHEMA_VERSION == 1
    assert dataset["datasetType"] == GEOSPATIAL_DATASET_TYPE
    assert dataset["summary"] == {"nationalityCount": 3, "personnelMembershipCount": 4}
    assert dataset["records"][0]["id"] == "malaysian"
    assert dataset["records"][0]["personnelCount"] == 2
    assert len(dataset["records"][0]["people"]) == 2
    assert dataset["records"][0]["people"][0]["name"] == "A"


def test_payload_excludes_staff_ids_and_unneeded_hr_fields():
    dataset = build_nationality_dataset(_sample_map_df(), _sample_people_df())
    person = dataset["records"][0]["people"][0]
    assert set(person) == {"name", "staffPosition", "department", "salaryGrade", "employmentCategory", "sectionName"}
    assert "Staff ID" not in str(dataset)
    assert "Current Location" not in str(dataset)


def test_dual_nationality_support_and_duplicate_token_handling():
    people = _sample_people_df().iloc[[0]].copy()
    people.loc[people.index[0], "Nationality"] = "Malaysian/Malaysian"
    dataset = build_nationality_dataset(_sample_map_df().iloc[[0]].copy(), people)
    assert len(dataset["records"][0]["people"]) == 1


def test_html_contains_split_frontend_and_both_stylesheets():
    html = _build_openglobus_html(build_nationality_dataset(_sample_map_df(), _sample_people_df()))
    assert f"@openglobus/og@{OPEN_GLOBUS_VERSION}/lib/og.es.js" in html
    assert f"@openglobus/og@{OPEN_GLOBUS_VERSION}/lib/og.css" in html
    assert 'id="re-globe-config"' in html
    for module in ("contract.js", "filters.js", "markers.js", "layers.js", "details.js", "camera.js"):
        assert f'data-re-globe-module="{module}"' in html
    assert "await import(config.openGlobusUrl)" in html
    assert "GlobusRgbTerrain" in html and "OpenStreetMap" in html
    assert "pickingEnabled: true" in html and "flyLonLat" in html
    assert "resetFilters" in html and "© OpenStreetMap contributors" in html


def test_contract_rejects_bad_coordinates_and_duplicate_nationalities():
    frame = _sample_map_df()
    frame.loc[0, "Latitude"] = 95
    with pytest.raises(ValueError, match="Latitude out of range"):
        build_nationality_dataset(frame, _sample_people_df())
    duplicate = pd.concat([_sample_map_df(), _sample_map_df().iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="Duplicate nationality"):
        build_nationality_dataset(duplicate, _sample_people_df())


def test_contract_validator_rejects_summary_mismatch():
    dataset = build_nationality_dataset(_sample_map_df(), _sample_people_df())
    dataset["summary"]["nationalityCount"] = 99
    with pytest.raises(ValueError, match="nationalityCount"):
        validate_nationality_dataset(dataset)
