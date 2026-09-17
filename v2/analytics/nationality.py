"""Nationality normalization and geographic visualization helpers."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import pycountry
from plotly.subplots import make_subplots

from config import COUNTRY_COORDINATES, NATIONALITY_ALIASES


_MAP_COLORSCALE = [
    [0.00, "#BFD730"],
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
    """Prepare nationality counts, geographic coordinates and ISO-3 codes.

    The returned dataframe supports country-level choropleth rendering and
    centroid bubbles. ``unmatched`` contains nationality labels that cannot be
    represented geographically with the configured country metadata.
    """
    if personnel_df is None or personnel_df.empty or "Nationality" not in personnel_df.columns:
        return pd.DataFrame(), []

    df = personnel_df[["Nationality"]].copy()
    df["Nationality"] = df["Nationality"].fillna("").astype(str).str.strip()
    df = df[
        ~df["Nationality"].str.lower().isin(
            {"", "nan", "none", "n/a", "na", "not applicable"}
        )
    ].copy()

    df["Nationality"] = df["Nationality"].str.split("/")
    df = df.explode("Nationality")
    df["Nationality"] = (
        df["Nationality"].astype(str).str.strip().replace(NATIONALITY_ALIASES)
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


def create_nationality_distribution_map(map_df: pd.DataFrame):
    """Build an interactive 3D-style nationality globe for the dashboard.

    The visual design is inspired by the referenced Basemap globe project:
    orthographic globe, dark space-like canvas and a focused viewing angle.
    Plotly's native Geo renderer is used instead of generating PNG frames, so
    the globe stays interactive inside Streamlit without a Basemap dependency.

    The figure contains:
      1. An orthographic globe with country-level nationality colouring.
      2. Centroid bubbles showing personnel concentration.
      3. A compact Top Nationalities bar chart for exact comparison.
    """
    if map_df is None or map_df.empty:
        raise ValueError("Nationality map data cannot be empty.")

    chart_df = map_df.copy()
    chart_df["Personnel Count"] = pd.to_numeric(
        chart_df["Personnel Count"], errors="coerce"
    ).fillna(0)
    chart_df = chart_df[chart_df["Personnel Count"] > 0].copy()

    if chart_df.empty:
        raise ValueError("Nationality map data contains no positive personnel counts.")

    top_bar = chart_df.nlargest(10, "Personnel Count").sort_values(
        "Personnel Count", ascending=True
    )

    fig = make_subplots(
        rows=2,
        cols=1,
        specs=[[{"type": "geo"}], [{"type": "xy"}]],
        row_heights=[0.75, 0.25],
        vertical_spacing=0.07,
    )

    # Country-level nationality colouring.
    fig.add_trace(
        go.Choropleth(
            locations=chart_df["ISO3"],
            z=chart_df["Personnel Count"],
            text=chart_df["Nationality"],
            customdata=chart_df[["Personnel Count", "Representation Display"]],
            locationmode="ISO-3",
            colorscale=_MAP_COLORSCALE,
            zmin=0,
            zmax=max(float(chart_df["Personnel Count"].max()), 1.0),
            marker={
                "line": {
                    "color": "rgba(255,255,255,0.65)",
                    "width": 0.55,
                }
            },
            colorbar={
                "title": {"text": "Personnel"},
                "orientation": "h",
                "x": 0.5,
                "xanchor": "center",
                "y": 0.285,
                "yanchor": "bottom",
                "len": 0.34,
                "thickness": 10,
                "tickfont": {"size": 10, "color": "#E8EEF2"},
                "title_font": {"size": 10, "color": "#E8EEF2"},
            },
            hovertemplate=(
                "<b>%{text}</b><br>"
                "Personnel: %{customdata[0]:.0f}<br>"
                "Representation: %{customdata[1]}"
                "<extra></extra>"
            ),
            showscale=True,
        ),
        row=1,
        col=1,
    )

    # Centroid bubbles use sqrt scaling so smaller nationalities remain visible.
    bubble_sizes = (chart_df["Personnel Count"].pow(0.5) * 5.5).clip(
        lower=7, upper=34
    )

    fig.add_trace(
        go.Scattergeo(
            lon=chart_df["Longitude"],
            lat=chart_df["Latitude"],
            text=chart_df["Nationality"],
            customdata=chart_df[["Personnel Count", "Representation Display"]],
            mode="markers",
            marker={
                "size": bubble_sizes,
                "color": "#FFFFFF",
                "opacity": 0.88,
                "line": {
                    "color": "#00A19C",
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
        ),
        row=1,
        col=1,
    )

    # Exact comparison below the globe.
    fig.add_trace(
        go.Bar(
            x=top_bar["Personnel Count"],
            y=top_bar["Nationality"],
            orientation="h",
            text=top_bar["Personnel Count"].astype(int),
            textposition="outside",
            marker={
                "color": "#00A19C",
                "line": {"color": "#007F7B", "width": 0.5},
            },
            hovertemplate="<b>%{y}</b><br>Personnel: %{x:.0f}<extra></extra>",
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    # Basemap-inspired orthographic globe styling.
    fig.update_geos(
        row=1,
        col=1,
        scope="world",
        projection={
            "type": "orthographic",
            "scale": 1.55,
            "minscale": 0.85,
            "maxscale": 3.2,
            "rotation": {
                "lon": 105,
                "lat": 8,
                "roll": 0,
            },
        },
        showframe=False,
        showland=True,
        landcolor="#18252B",
        showocean=True,
        oceancolor="#050B10",
        showlakes=True,
        lakecolor="#07151C",
        showcountries=True,
        countrycolor="rgba(220,235,240,0.42)",
        countrywidth=0.45,
        coastlinecolor="rgba(255,255,255,0.55)",
        coastlinewidth=0.7,
        showcoastlines=True,
        showrivers=False,
        bgcolor="#050B10",
    )

    fig.update_xaxes(
        row=2,
        col=1,
        title_text="Personnel",
        showgrid=True,
        gridcolor="#24363E",
        zeroline=False,
        tickfont={"size": 10, "color": "#C8D5DA"},
        title_font={"size": 10, "color": "#C8D5DA"},
    )
    fig.update_yaxes(
        row=2,
        col=1,
        title_text="",
        tickfont={"size": 10, "color": "#C8D5DA"},
        automargin=True,
    )

    fig.add_annotation(
        text="<b>Top Nationalities</b>",
        x=0,
        y=0.255,
        xref="paper",
        yref="paper",
        xanchor="left",
        yanchor="bottom",
        showarrow=False,
        font={"size": 12, "color": "#E8EEF2"},
    )

    fig.add_annotation(
        text="Drag to rotate  •  Scroll to zoom",
        x=0.995,
        y=0.985,
        xref="paper",
        yref="paper",
        xanchor="right",
        yanchor="top",
        showarrow=False,
        font={"size": 10, "color": "#AFC1C8"},
    )

    fig.update_layout(
        height=790,
        margin={"l": 8, "r": 8, "t": 12, "b": 12},
        paper_bgcolor="#050B10",
        plot_bgcolor="#050B10",
        font={
            "family": "Arial, sans-serif",
            "color": "#E8EEF2",
        },
        hoverlabel={
            "bgcolor": "#101C22",
            "font": {"color": "#F3F7F8"},
            "bordercolor": "#2D4A55",
        },
        bargap=0.28,
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
