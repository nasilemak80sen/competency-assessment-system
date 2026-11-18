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
