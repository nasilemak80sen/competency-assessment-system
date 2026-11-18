"""Regression coverage for the OpenGlobus nationality-globe presentation."""
from v2.components.openglobus import _build_openglobus_html


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


def test_globe_defaults_to_selected_only_labels_and_offers_density_options():
    html = _build_openglobus_html(_sample_records())

    assert '<option value="selected">Labels: selected only</option>' in html
    assert '<option value="top">Labels: top 5</option>' in html
    assert '<option value="all">Labels: all</option>' in html
    assert '<option value="none">Labels: off</option>' in html
    assert 'labelMode.value==="selected"' in html
    assert 'labelMode.value==="top"' in html
    assert 'labelMode.value==="all"' in html


def test_globe_uses_hover_summary_and_preserves_click_detail_and_fly_to():
    html = _build_openglobus_html(_sample_records())

    assert 'id="hovercard"' in html
    assert 'events.on("mousemove"' in html
    assert 'events.on("lclick"' in html
    assert "flyLonLat(" in html
    assert "Personnel directory" in html


def test_globe_labels_are_added_conditionally_not_to_every_marker():
    html = _build_openglobus_html(_sample_records())

    assert "if(showLabel){" in html
    assert 'entityOptions.label={' in html
    assert 'label:{text:record.nationality+" · "+count' not in html


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
        "new LonLat(\n      defaultFocusRecord.longitude,\n"
        "      defaultFocusRecord.latitude,\n      4500000\n    )"
    ) in html
    assert "12000000" not in html


def test_globe_uses_supported_north_locked_navigation_mode():
    html = _build_openglobus_html(_sample_records())

    assert 'navigation:{mode:"lockNorth",inertia:.18,zoomSpeed:1.15}' in html
    assert 'navigation:{mode:"north"' not in html
