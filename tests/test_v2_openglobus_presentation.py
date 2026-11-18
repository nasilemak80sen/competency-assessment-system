"""Regression coverage for the OpenGlobus nationality-globe presentation."""
from v2.components.openglobus import (
    _PROFILE_BRIDGE_JS,
    _build_openglobus_html,
)


def _sample_records():
    return [
        {
            "nationality": "Malaysian",
            "count": 4,
            "latitude": 4.21,
            "longitude": 101.98,
            "representation": "100.0%",
            "people": [
                {
                    "personnel_id": 9001,
                    "Name": "Example Person",
                    "Staff Position": "Reservoir Engineer",
                    "Department": "Development",
                    "SG": "P3",
                    "Employment Category": "Permanent",
                    "Section Name": "Reservoir Management",
                }
            ],
        }
    ]


def test_globe_replaces_permanent_country_labels_with_hover_popups():
    html = _build_openglobus_html(_sample_records())

    assert 'id="hovercard"' in html
    assert "pointermove" in html
    assert "positionHoverCard" in html
    assert 'id="labelMode"' not in html
    assert "entityOptions.label" not in html


def test_globe_uses_hover_summary_and_preserves_click_detail_and_fly_to():
    html = _build_openglobus_html(_sample_records())

    assert 'id="hovercard"' in html
    assert 'events.on("mousemove"' in html
    assert 'events.on("lclick"' in html
    assert "flyLonLat(" in html
    assert "Personnel directory" in html


def test_globe_personnel_rows_send_profile_selection_to_streamlit():
    html = _build_openglobus_html(_sample_records())

    assert 'data-personnel-id="'+ "'+personnelId+'" in html
    assert "postMessage" in html
    assert 'type:"profile-select"' in html
    assert "personnelId" in html
    assert "View profile" in html
    assert "Profile not linked" in html
    assert "assessmentProfileUrl" not in html
    assert 'aria-label="Open assessment profile' in html
    assert 'target="_blank" rel="noopener" aria-label="Open assessment profile' not in html


def test_streamlit_bridge_accepts_only_the_globe_iframe_and_triggers_profile_selection():
    assert 'event.source !== frame.contentWindow' in _PROFILE_BRIDGE_JS
    assert 'message.source !== "re-workforce-openglobus"' in _PROFILE_BRIDGE_JS
    assert 'message.type !== "profile-select"' in _PROFILE_BRIDGE_JS
    assert 'setTriggerValue("profile_selected", personnelId)' in _PROFILE_BRIDGE_JS


def test_dashboard_uses_session_aware_streamlit_page_navigation():
    from pathlib import Path

    dashboard = Path("v2/pages/01_Dashboard.py").read_text(encoding="utf-8")

    assert 'st.session_state["requested_personnel_id"] = selected_profile_id' in dashboard
    assert 'st.switch_page("pages/05_Individual_Assessment.py")' in dashboard
    assert 'target="_blank"' not in dashboard


def test_globe_initially_focuses_the_largest_nationality_at_country_level_zoom():
    records = _sample_records() + [
        {
            "nationality": "Indonesian",
            "count": 12,
            "latitude": -2.5,
            "longitude": 118.0,
            "representation": "75.0%",
            "people": [],
        }
    ]
    html = _build_openglobus_html(records)

    assert "const defaultFocusRecord=records.reduce((largest,record)=>" in html
    assert "visibleCount(record)>visibleCount(largest)?record:largest" in html
    assert "selectedRecord=defaultFocusRecord;" in html
    assert (
        "new LonLat(\n        defaultFocusRecord.longitude,\n"
        "        defaultFocusRecord.latitude,\n        4500000\n"
        "      ),\n      undefined,\n      northUp"
    ) in html
    assert "12000000" not in html


def test_globe_uses_supported_north_locked_navigation_mode():
    html = _build_openglobus_html(_sample_records())

    assert 'navigation:{mode:"lockNorth",inertia:.18,zoomSpeed:1.15}' in html
    assert 'navigation:{mode:"north"' not in html
