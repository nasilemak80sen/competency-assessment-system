"""Tests for the Dashboard nationality normalization and geospatial map."""
from __future__ import annotations

import pandas as pd

from v2.analytics.nationality import (
    create_nationality_bubble_map,
    prepare_nationality_map_data,
)


def test_prepare_nationality_map_data_normalizes_counts_and_coordinates():
    df = pd.DataFrame(
        {
            "Nationality": [
                "Malaysian",
                "Malaysian",
                "British",
                "British/Indonesian",
                None,
                "N/A",
            ]
        }
    )

    map_df, unmatched = prepare_nationality_map_data(df)

    assert not map_df.empty
    assert unmatched == []
    assert set(map_df["Nationality"]) >= {"Malaysian", "British", "Indonesian"}

    malaysia = map_df.loc[map_df["Nationality"] == "Malaysian"].iloc[0]
    assert int(malaysia["Personnel Count"]) == 2
    assert pd.notna(malaysia["Latitude"])
    assert pd.notna(malaysia["Longitude"])
    assert malaysia["Representation Display"].endswith("%")


def test_create_nationality_bubble_map_uses_native_plotly_geo_renderer():
    map_df = pd.DataFrame(
        {
            "Nationality": ["Malaysian", "British"],
            "Personnel Count": [20, 3],
            "Latitude": [4.2105, 55.3781],
            "Longitude": [101.9758, -3.4360],
            "Representation": [86.9565, 13.0435],
            "Representation Display": ["87%", "13%"],
        }
    )

    fig = create_nationality_bubble_map(map_df)

    assert len(fig.data) == 1
    assert fig.data[0].type == "scattergeo"
    assert fig.data[0].marker.sizemode == "area"
    assert fig.layout.geo.projection.type == "natural earth"
    assert fig.layout.geo.showcountries is True
    assert fig.layout.geo.showland is True
