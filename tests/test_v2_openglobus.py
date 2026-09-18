"""Regression tests for the OpenGlobus nationality component."""
from __future__ import annotations

import pandas as pd

from v2.components.openglobus import (
    OPEN_GLOBUS_VERSION,
    _build_openglobus_html,
    _records_from_map_df,
)


def _sample_map_df():
    return pd.DataFrame(
        {
            "Nationality": ["Malaysian", "British", "Indonesian"],
            "Personnel Count": [176, 5, 6],
            "Latitude": [4.2105, 55.3781, -0.7893],
            "Longitude": [101.9758, -3.4360, 113.9213],
            "Representation Display": ["94.1%", "2.7%", "3.2%"],
        }
    )


def test_records_from_map_df_creates_json_safe_globe_records():
    records = _records_from_map_df(_sample_map_df())

    assert len(records) == 3
    assert records[0] == {
        "nationality": "Malaysian",
        "count": 176,
        "latitude": 4.2105,
        "longitude": 101.9758,
        "representation": "94.1%",
    }


def test_openglobus_html_contains_native_webgl_globe_configuration():
    records = _records_from_map_df(_sample_map_df())
    html = _build_openglobus_html(records, height=560)

    assert f"@openglobus/og@{OPEN_GLOBUS_VERSION}" in html
    assert "GlobusRgbTerrain" in html
    assert "OpenStreetMap" in html
    assert 'new Globe({' in html
    assert 'new Vector("Nationalities"' in html
    assert "atmosphereEnabled: true" in html
    assert "msaa: 4" in html
    assert 'width: 100%' in html
    assert "height: 560px" in html
    assert "Malaysian" in html
    assert "176" in html


def test_openglobus_html_keeps_osm_attribution_and_no_plotly_dependency():
    records = _records_from_map_df(_sample_map_df())
    html = _build_openglobus_html(records)

    assert "OpenStreetMap contributors" in html
    assert "plotly" not in html.lower()
