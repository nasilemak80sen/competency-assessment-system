"""Nationality normalization and geographic visualization helpers."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import pycountry

from config import COUNTRY_COORDINATES, NATIONALITY_ALIASES


_MAP_COLORSCALE = [
    [0.00, "#E8F1F2"],
    [0.01, "#BFD730"],
    [0.08, "#00A19C"],
    [0.35, "#20419A"],
    [1.00, "#763F98"],
]


def nationality_to_iso3(nationality):
    """Convert a nationality/country label to an ISO-3 country code."""
    if nationality is None or pd.isna(nationality):
        return None

    value = str(nationality).strip()
    if not value:
        return None

    value = NATIONALITY_ALIASES.get(value, value)

    try:
        return pycountry.countries.lookup(value).alpha_3
    except LookupError:
        return None


def prepare_nationality_map_data(
    personnel_df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str]]:
    """Prepare nationality counts, geographic coordinates and ISO-3 codes."""
    if (
        personnel_df is None
        or personnel_df.empty
        or "Nationality" not in personnel_df.columns
    ):
        return pd.DataFrame(), []

    df = personnel_df[["Nationality"]].copy()
    df["Nationality"] = df["Nationality"].fillna("").astype(str).str.strip()
    df = df[
        ~df["Nationality"].str.lower().isin(
            {"", "nan", "none", "n/a", "na", "not applicable"}
        )
    ].copy()

    # Preserve the original application's support for rows containing
    # multiple nationalities such as "British/Indonesian".
    df["Nationality"] = df["Nationality"].str.split("/")
    df = df.explode("Nationality")
    df["Nationality"] = (
        df["Nationality"]
        .astype(str)
        .str.strip()
        .replace(NATIONALITY_ALIASES)
    )

    summary = (
        df.groupby("Nationality", as_index=False)
        .size()
        .rename(columns={"size": "Personnel Count"})
    )

    summary["ISO3"] = summary["Nationality"].map(nationality_to_iso3)
    summary["Latitude"] = summary["Nationality"].map(
        lambda country: COUNTRY_COORDINATES.get(country, {}).get("latitude")
    )
    summary["Longitude"] = summary["Nationality"].map(
        lambda country: COUNTRY_COORDINATES.get(country, {}).get("longitude")
    )

    unmatched = (
        summary.loc[
            summary[["ISO3", "Latitude", "Longitude"]].isna().any(axis=1),
            "Nationality",
        ]
        .dropna()
        .sort_values()
        .unique()
        .tolist()
    )

    map_df = (
        summary.dropna(subset=["ISO3", "Latitude", "Longitude"])
        .sort_values("Personnel Count", ascending=False)
        .reset_index(drop=True)
    )

    total = map_df["Personnel Count"].sum()
    map_df["Representation"] = (
        map_df["Personnel Count"] / total * 100 if total > 0 else 0.0
    )
    map_df["Representation Display"] = map_df["Representation"].map(
        lambda value: f"{value:.1f}%"
    )

    return map_df, unmatched


def create_nationality_distribution_map(
    map_df: pd.DataFrame,
    projection_type: str = "orthographic",
):
    """Build a responsive Plotly geographic nationality map.

    The default presentation is an orthographic globe, matching Plotly's
    native Scattergeo globe style. The map uses only Plotly's built-in
    geographic renderer, so there are no external map tiles or Basemap
    dependencies.

    projection_type can be changed to another Plotly Geo projection such as
    "natural earth", "equirectangular", "mercator", "robinson",
    "winkel tripel" or "orthographic".
    """
    supported_projections = {
        "orthographic",
        "natural earth",
        "equirectangular",
        "mercator",
        "robinson",
        "winkel tripel",
    }
    if projection_type not in supported_projections:
        raise ValueError(
            f"Unsupported Plotly Geo projection: {projection_type!r}. "
            f"Choose from {sorted(supported_projections)}."
        )

    if map_df is None or map_df.empty:
        raise ValueError("Nationality map data cannot be empty.")

    chart_df = map_df.copy()
    chart_df["Personnel Count"] = pd.to_numeric(
        chart_df["Personnel Count"], errors="coerce"
    ).fillna(0)
    chart_df = chart_df[chart_df["Personnel Count"] > 0].copy()

    if chart_df.empty:
        raise ValueError(
            "Nationality map data contains no positive personnel counts."
        )

    fig = go.Figure()

    # Native Scattergeo bubbles are the primary visual, keeping the map close
    # to Plotly's standard globe example while retaining personnel counts.
    bubble_sizes = (
        chart_df["Personnel Count"].pow(0.5) * 6.0
    ).clip(lower=8, upper=38)

    fig.add_trace(
        go.Scattergeo(
            lon=chart_df["Longitude"],
            lat=chart_df["Latitude"],
            text=chart_df["Nationality"],
            customdata=chart_df[
                ["Personnel Count", "Representation Display"]
            ],
            mode="markers",
            marker={
                "size": bubble_sizes,
                "color": "#00A19C",
                "opacity": 0.82,
                "line": {
                    "color": "#FFFFFF",
                    "width": 1.4,
                },
            },
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Personnel: %{customdata[0]:.0f}<br>"
                "Representation: %{customdata[1]}"
                "<extra></extra>"
            ),
            showlegend=False,
        )
    )

    # Native Plotly Geo renderer: no external tiles and no Cartesian axes.
    # Streamlit controls the chart width responsively.
    fig.update_geos(
        scope="world",
        projection={
            "type": projection_type,
            "scale": 1.08 if projection_type == "orthographic" else 1.18,
        },
        center={
            "lat": 12,
            "lon": 70,
        },
        showframe=False,
        showland=True,
        landcolor="#DDE7E9",
        showocean=True,
        oceancolor="#F7FAFA",
        showlakes=True,
        lakecolor="#F7FAFA",
        showcountries=True,
        countrycolor="#AAB5BA",
        countrywidth=0.65,
        showcoastlines=True,
        coastlinecolor="#87969B",
        coastlinewidth=0.8,
        showrivers=False,
        bgcolor="rgba(0,0,0,0)",
    )

    fig.update_layout(
        autosize=True,
        width=None,
        height=500,
        margin={
            "l": 0,
            "r": 0,
            "t": 0,
            "b": 28,
        },
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={
            "family": "Arial, sans-serif",
            "color": "#263238",
        },
        hoverlabel={
            "bgcolor": "#FFFFFF",
            "font": {
                "color": "#263238",
            },
            "bordercolor": "#00A19C",
        },
        showlegend=False,
    )

    return fig


def create_nationality_bubble_map(map_df: pd.DataFrame):
    """Backward-compatible entry point for the nationality dashboard."""
    return create_nationality_distribution_map(map_df)


__all__ = [
    "prepare_nationality_map_data",
    "create_nationality_distribution_map",
    "create_nationality_bubble_map",
    "nationality_to_iso3",
]
