"""Regression tests for the Phase 2 OpenGlobus nationality component."""
from __future__ import annotations
import pandas as pd
from v2.components.openglobus import OPEN_GLOBUS_VERSION,_build_openglobus_html,_records_from_map_df

def _sample_map_df():
    return pd.DataFrame({"Nationality":["Malaysian","British","Indonesian"],"Personnel Count":[176,5,6],"Latitude":[4.2105,55.3781,-0.7893],"Longitude":[101.9758,-3.4360,113.9213],"Representation Display":["94.1%","2.7%","3.2%"]})
def _sample_people_df():
    return pd.DataFrame({"Nationality":["Malaysian","British","Indonesian","Malaysian"],"Name":["A","B","C","D"],"Staff Position":["Engineer","Geologist","Engineer","Manager"],"Department":["RE","RE","RE","RE"],"SG":["P5","P6","P5","P7"],"Employment Category":["PERMANENT","CDH","PERMANENT","PERMANENT"],"Section Name":["A","B","A","C"]})
def test_records_include_personnel_for_phase_2():
    records=_records_from_map_df(_sample_map_df(),_sample_people_df())
    assert len(records)==3
    assert records[0]["nationality"]=="Malaysian"
    assert len(records[0]["people"])==2
    assert records[0]["people"][0]["Name"]=="A"
def test_openglobus_html_contains_phase_2_interaction_stack():
    html=_build_openglobus_html(_records_from_map_df(_sample_map_df(),_sample_people_df()),height=620)
    assert f"@openglobus/og@{OPEN_GLOBUS_VERSION}" in html
    assert "GlobusRgbTerrain" in html
    assert "OpenStreetMap" in html
    assert "new Entity({" in html
    assert "pickingEnabled:true" in html
    assert 'events.on("lclick"' in html
    assert "camera.setLonLat" in html
    assert "Employment Categories" in html
    assert "Salary Grades" in html
    assert "Section" in html
    assert "resetFilters" in html
    assert "RE Nationality Intelligence Globe" in html
def test_openglobus_html_keeps_osm_attribution_and_no_plotly_dependency():
    html=_build_openglobus_html(_records_from_map_df(_sample_map_df(),_sample_people_df()))
    assert "OpenStreetMap contributors" in html
    assert "plotly" not in html.lower()
