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
    assert set(map_df["Nationality"]) >= {
        "Malaysian",
        "British",
        "Indonesian",
    }

    malaysia = map_df.loc[
        map_df["Nationality"] == "Malaysian"
    ].iloc[0]

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


def test_create_nationality_distribution_map_is_responsive_orthographic_globe():
    fig = create_nationality_distribution_map(_sample_map_df())

    # The dashboard uses a native Plotly Scattergeo globe with proportional
    # personnel bubbles and no secondary chart.
    assert len(fig.data) == 1
    assert fig.data[0].type == "scattergeo"

    assert fig.layout.geo.scope == "world"
    assert fig.layout.geo.projection.type == "orthographic"
    assert fig.layout.geo.projection.scale == 1.08
    assert fig.layout.geo.center.lat == 12
    assert fig.layout.geo.center.lon == 70
    assert fig.layout.geo.showcountries is True
    assert fig.layout.geo.showland is True
    assert fig.layout.geo.showocean is True

    # Streamlit owns the responsive width; Plotly does not impose a fixed
    # width, avoiding the old square-canvas behaviour.
    assert fig.layout.autosize is True
    assert fig.layout.width is None
    assert fig.layout.height == 500


def test_create_nationality_distribution_map_supports_other_plotly_projections():
    fig = create_nationality_distribution_map(
        _sample_map_df(),
        projection_type="natural earth",
    )
    assert fig.data[0].type == "scattergeo"
    assert fig.layout.geo.projection.type == "natural earth"


def test_create_nationality_distribution_map_rejects_unknown_projection():
    try:
        create_nationality_distribution_map(
            _sample_map_df(),
            projection_type="not-a-real-projection",
        )
    except ValueError as exc:
        assert "Unsupported Plotly Geo projection" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported projection.")


def test_create_nationality_bubble_map_remains_backward_compatible():
    fig = create_nationality_bubble_map(_sample_map_df())

    assert len(fig.data) == 1
    assert fig.data[0].type == "scattergeo"
    assert fig.layout.geo.projection.type == "orthographic"
    assert fig.layout.autosize is True
