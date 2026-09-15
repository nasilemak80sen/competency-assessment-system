"""Nationality normalization and geographic visualization helpers."""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import pycountry

from config import COUNTRY_COORDINATES, NATIONALITY_ALIASES


def prepare_nationality_map_data(personnel_df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Prepare nationality counts and configured country coordinates."""
    if personnel_df is None or personnel_df.empty or "Nationality" not in personnel_df.columns:
        return pd.DataFrame(), []
    df = personnel_df[["Nationality"]].copy()
    df["Nationality"] = df["Nationality"].fillna("").astype(str).str.strip()
    df = df[~df["Nationality"].str.lower().isin({"", "nan", "none", "n/a", "na", "not applicable"})].copy()
    df["Nationality"] = df["Nationality"].str.split("/")
    df = df.explode("Nationality")
    df["Nationality"] = df["Nationality"].astype(str).str.strip().replace(NATIONALITY_ALIASES)
    summary = df.groupby("Nationality", as_index=False).size().rename(columns={"size": "Personnel Count"})
    summary["Latitude"] = summary["Nationality"].map(lambda c: COUNTRY_COORDINATES.get(c, {}).get("latitude"))
    summary["Longitude"] = summary["Nationality"].map(lambda c: COUNTRY_COORDINATES.get(c, {}).get("longitude"))
    unmatched = (summary.loc[summary[["Latitude", "Longitude"]].isna().any(axis=1), "Nationality"]
                 .dropna().sort_values().unique().tolist())
    map_df = summary.dropna(subset=["Latitude", "Longitude"]).sort_values("Personnel Count", ascending=False).reset_index(drop=True)
    total = map_df["Personnel Count"].sum()
    map_df["Representation"] = map_df["Personnel Count"] / total * 100 if total > 0 else 0.0
    map_df["Representation Display"] = map_df["Representation"].map(lambda value: f"{value:.0f}%")
    return map_df, unmatched


def create_nationality_bubble_map(map_df: pd.DataFrame):
    """Build the legacy nationality bubble map presentation."""
    fig = px.scatter_map(
        map_df, lat="Latitude", lon="Longitude", size="Personnel Count", color="Personnel Count",
        hover_name="Nationality",
        hover_data={"Latitude": False, "Longitude": False, "Personnel Count": True, "Representation Display": True},
        custom_data=["Nationality", "Personnel Count", "Representation Display"], size_max=42, zoom=2.0,
        center={"lat": 15, "lon": 65},
        color_continuous_scale=[[0.00,"#BFD730"],[0.01,"#00A19C"],[0.04,"#20419A"],[1.00,"#763F98"]],
        map_style="carto-voyager", opacity=0.75,
    )
    fig.update_traces(marker={"sizemin": 7}, hovertemplate="<b>%{customdata[0]}</b><br>Personnel: %{customdata[1]:.0f}<br>Representation: %{customdata[2]}<extra></extra>")
    fig.update_layout(height=560, margin={"l":0,"r":0,"t":40,"b":0}, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
                      coloraxis_colorbar={"title":{"text":"Personnel"},"orientation":"h","x":0.5,"xanchor":"center","y":-0.05,"yanchor":"top","len":0.45,"thickness":12,"tickfont":{"size":11}},
                      font={"family":"Arial, sans-serif","color":"#263238"})
    return fig


def nationality_to_iso3(nationality):
    """Convert a nationality/country label to an ISO-3 code."""
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


__all__ = ["prepare_nationality_map_data", "create_nationality_bubble_map", "nationality_to_iso3"]
