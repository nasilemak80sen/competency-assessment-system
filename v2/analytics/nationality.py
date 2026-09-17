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

    The returned dataframe supports both country-level choropleth rendering and
    optional centroid bubbles. ``unmatched`` contains nationality labels that
    cannot be represented geographically with the configured country metadata.
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

    # Some source rows contain multiple nationalities separated by '/'.
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

    # A country needs an ISO code for the filled map and coordinates for the
    # optional centroid bubble. Keep the current unmatched behaviour so admins
    # can see source values that need configuration.
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
    """Build the enterprise-style global nationality distribution visual.

    Layout:
      1. Country-filled world map for geographic context.
      2. Small centroid bubbles to emphasize personnel concentration.
      3. Top-nationalities horizontal bar chart for exact comparison.

    The renderer uses Plotly's built-in Geo renderer and therefore does not
    depend on MapLibre or external map tiles.
    """
    if map_df is None or map_df.empty:
        raise ValueError("Nationality map data cannot be empty.")

    chart_df = map_df.copy()
    chart_df["Personnel Count"] = pd.to_numeric(
        chart_df["Personnel Count"], errors="coerce"
    ).fillna(0)
    chart_df = chart_df[chart_df["Personnel Count"] > 0].copy()

    # Keep the map readable when there are many nationalities, while the
    # underlying data table remains available through the existing dashboard.
    top_bar = chart_df.nlargest(10, "Personnel Count").sort_values(
        "Personnel Count", ascending=True
    )

    fig = make_subplots(
        rows=2,
        cols=1,
        specs=[[{"type": "geo"}], [{"type": "xy"}]],
        row_heights=[0.73, 0.27],
        vertical_spacing=0.08,
    )

    # ------------------------------------------------------------------
    # Layer 1: country-level choropleth
    # ------------------------------------------------------------------
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
                    "color": "#FFFFFF",
                    "width": 0.65,
                }
            },
            colorbar={
                "title": {"text": "Personnel"},
                "orientation": "h",
                "x": 0.5,
                "xanchor": "center",
                "y": 0.315,
                "yanchor": "bottom",
                "len": 0.36,
                "thickness": 11,
                "tickfont": {"size": 10},
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

    # ------------------------------------------------------------------
    # Layer 2: centroid bubbles — visual emphasis, not the data source
    # ------------------------------------------------------------------
    # sqrt scaling prevents Malaysia from visually swallowing all smaller
    # nationalities while keeping the actual count in the hover tooltip.
    bubble_sizes = (chart_df["Personnel Count"].pow(0.5) * 5.5).clip(lower=8, upper=38)

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
                "opacity": 0.78,
                "line": {
                    "color": "#20419A",
                    "width": 1.5,
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

    # ------------------------------------------------------------------
    # Layer 3: exact top-nationality comparison
    # ------------------------------------------------------------------
    fig.add_trace(
        go.Bar(
            x=top_bar["Personnel Count"],
            y=top_bar["Nationality"],
            orientation="h",
            text=top_bar["Personnel Count"].astype(int),
            textposition="outside",
            marker={
                "color": "#20419A",
                "line": {"color": "#16316F", "width": 0.5},
            },
            hovertemplate="<b>%{y}</b><br>Personnel: %{x:.0f}<extra></extra>",
            showlegend=False,
        ),
        row=2,
        col=1,
    )

    fig.update_geos(
        row=1,
        col=1,
        scope="world",
        projection_type="natural earth",
        projection_scale=1.08,
        center={"lat": 15, "lon": 65},
        showframe=False,
        showland=True,
        landcolor="#F4F6F7",
        showocean=True,
        oceancolor="#EAF1F4",
        showlakes=True,
        lakecolor="#EAF1F4",
        showcountries=True,
        countrycolor="#C8D0D5",
        countrywidth=0.55,
        coastlinecolor="#AEB8BE",
        coastlinewidth=0.7,
    )

    fig.update_xaxes(
        row=2,
        col=1,
        title_text="Personnel",
        showgrid=True,
        gridcolor="#E6EAED",
        zeroline=False,
        tickfont={"size": 10},
        title_font={"size": 11},
    )
    fig.update_yaxes(
        row=2,
        col=1,
        title_text="",
        tickfont={"size": 10},
        automargin=True,
    )

    fig.add_annotation(
        text="<b>Top Nationalities</b>",
        x=0,
        y=0.275,
        xref="paper",
        yref="paper",
        xanchor="left",
        yanchor="bottom",
        showarrow=False,
        font={"size": 13, "color": "#263238"},
    )

    fig.update_layout(
        height=760,
        margin={"l": 8, "r": 8, "t": 18, "b": 18},
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font={
            "family": "Arial, sans-serif",
            "color": "#263238",
        },
        hoverlabel={
            "bgcolor": "#FFFFFF",
            "font": {"color": "#263238"},
            "bordercolor": "#D5DADD",
        },
        bargap=0.28,
        showlegend=False,
    )
    return fig


def create_nationality_bubble_map(map_df: pd.DataFrame):
    """Backward-compatible alias for the redesigned nationality visual."""
    return create_nationality_distribution_map(map_df)


__all__ = [
    "prepare_nationality_map_data",
    "create_nationality_distribution_map",
    "create_nationality_bubble_map",
    "nationality_to_iso3",
]
