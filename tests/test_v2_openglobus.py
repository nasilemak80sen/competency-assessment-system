"""Regression tests for the Phase 2 OpenGlobus nationality component."""
from __future__ import annotations
import pandas as pd
from v2.components.openglobus import (
    OPEN_GLOBUS_VERSION,
    _PROFILE_BRIDGE_JS,
    _build_openglobus_html,
    _records_from_map_df,
)

def _sample_map_df():
    return pd.DataFrame({"Nationality":["Malaysian","British","Indonesian"],"Personnel Count":[176,5,6],"Latitude":[4.2105,55.3781,-0.7893],"Longitude":[101.9758,-3.4360,113.9213],"Representation Display":["94.1%","2.7%","3.2%"]})
def _sample_people_df():
    return pd.DataFrame({"personnel_id":[101,102,103,104],"Nationality":["Malaysian","British","Indonesian","Malaysian"],"Name":["A","B","C","D"],"Staff Position":["Engineer","Geologist","Engineer","Manager"],"Department":["RE","RE","RE","RE"],"SG":["P5","P6","P5","P7"],"Employment Category":["PERMANENT","CDH","PERMANENT","PERMANENT"],"Section Name":["A","B","A","C"]})
def test_records_include_personnel_for_phase_2():
    records=_records_from_map_df(_sample_map_df(),_sample_people_df())
    assert len(records)==3
    assert records[0]["nationality"]=="Malaysian"
    assert len(records[0]["people"])==2
    assert records[0]["people"][0]["Name"]=="A"
    assert records[0]["people"][0]["personnel_id"]==101
def test_openglobus_html_contains_phase_2_interaction_stack():
    html=_build_openglobus_html(_records_from_map_df(_sample_map_df(),_sample_people_df()),height=620)
    assert f"@openglobus/og@{OPEN_GLOBUS_VERSION}" in html
    assert "GlobusRgbTerrain" in html
    assert "OpenStreetMap" in html
    assert "new Entity(entityOptions)" in html
    assert "const entityOptions={" in html
    assert "pickingEnabled:true" in html
    assert 'events.on("lclick"' in html
    assert "camera.setLonLat" in html
    assert "Employment Categories" in html
    assert "Salary Grades" in html
    assert "Section" in html
    assert "resetFilters" in html
    assert "RE Workforce Geography" in html
def test_openglobus_html_keeps_osm_attribution_and_no_plotly_dependency():
    html=_build_openglobus_html(_records_from_map_df(_sample_map_df(),_sample_people_df()))
    assert "OpenStreetMap contributors" in html
    assert "plotly" not in html.lower()

def test_openglobus_hover_is_anchored_near_marker_and_country_labels_are_hidden():
    html=_build_openglobus_html(_records_from_map_df(_sample_map_df(),_sample_people_df()))

    assert "pointermove" in html
    assert "positionHoverCard" in html
    assert 'transform:translate(-50%,-100%)' in html
    assert 'id="labelMode"' not in html
    assert "entityOptions.label" not in html
    assert "Labels:" not in html


def test_openglobus_personnel_directory_emits_session_aware_profile_selection():
    html=_build_openglobus_html(_records_from_map_df(_sample_map_df(),_sample_people_df()))

    assert "data-personnel-id" in html
    assert "postMessage" in html
    assert 'type:"profile-select"' in html
    assert "personnelId" in html
    assert "View profile" in html
    assert "Profile not linked" in html
    assert "assessmentProfileUrl" not in html
    assert 'target="_blank" rel="noopener" aria-label="Open assessment profile' not in html

    assert 'event.source !== frame.contentWindow' in _PROFILE_BRIDGE_JS
    assert 'setTriggerValue("profile_selected", personnelId)' in _PROFILE_BRIDGE_JS


def test_globe_initial_camera_uses_a_north_up_vector():
    html=_build_openglobus_html(_records_from_map_df(_sample_map_df(),_sample_people_df()))

    assert ",Vec3} from " in html
    assert "const northUp=" in html
    assert "Vec3.NORTH" in html
    assert "new Vec3(0,1,0)" in html
    assert "      northUp\n    );" in html
    assert 'navigation:{mode:"lockNorth"' in html

