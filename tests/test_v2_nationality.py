"""Tests for the Dashboard nationality normalization and geospatial visual."""
from __future__ import annotations

import pandas as pd

from v2.analytics.nationality import (
    create_nationality_bubble_map,
    create_nationality_distribution_map,
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
    assert pd.notna(malaysia["ISO3"])
    assert malaysia["Representation Display"].endswith("%")


def _sample_map_df():
    return pd.DataFrame(
        {
            "Nationality": ["Malaysian", "British", "Indonesian"],
            "Personnel Count": [176, 5, 6],
            "Latitude": [4.2105, 55.3781, -0.7893],
            "Longitude": [101.9758, -3.4360, 113.9213],
            "ISO3": ["MYS", "GBR", "IDN"],
            "Representation": [94.1, 2.7, 3.2],
            "Representation Display": ["94.1%", "2.7%", "3.2%"],
        }
    )


def test_create_nationality_distribution_map_has_map_and_top_nationalities():
    fig = create_nationality_distribution_map(_sample_map_df())

    assert len(fig.data) == 3
    assert fig.data[0].type == "choropleth"
    assert fig.data[0].locationmode == "ISO-3"
    assert fig.data[1].type == "scattergeo"
    assert fig.data[2].type == "bar"
    assert fig.layout.geo.projection.type == "natural earth"
    assert fig.layout.geo.showcountries is True
    assert fig.layout.geo.showland is True
    assert fig.layout.height == 760


def test_create_nationality_bubble_map_remains_backward_compatible():
    fig = create_nationality_bubble_map(_sample_map_df())

    assert len(fig.data) == 3
    assert fig.data[0].type == "choropleth"
    assert fig.data[1].type == "scattergeo"
    assert fig.data[2].type == "bar"
