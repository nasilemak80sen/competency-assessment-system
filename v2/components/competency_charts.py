"""Shared competency visualizations for ADMIN and USER assessment views."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# UI palette requested for the assessment experience.
ACTUAL_COLOR = "#00A651"  # PETRONAS-style emerald green
TARGET_COLOR = "#D62728"  # clear target/reference red


def build_actual_target_figures(gap: pd.DataFrame) -> tuple[go.Figure, go.Figure]:
    """Build the shared Actual-vs-Target combo chart and matching radar chart."""
    labels = gap["Competency"].astype(str)
    actual = pd.to_numeric(gap["Actual"], errors="coerce")
    target = pd.to_numeric(gap["Target"], errors="coerce")

    comparison = go.Figure()
    comparison.add_trace(
        go.Bar(
            x=labels,
            y=actual,
            name="Actual",
            marker_color=ACTUAL_COLOR,
            hovertemplate="%{x}<br>Actual: %{y:.1f}<extra></extra>",
        )
    )
    comparison.add_trace(
        go.Scatter(
            x=labels,
            y=target,
            name="Target",
            mode="lines+markers",
            line={"color": TARGET_COLOR, "width": 3},
            marker={"color": TARGET_COLOR, "size": 7},
            hovertemplate="%{x}<br>Target: %{y:.1f}<extra></extra>",
        )
    )
    comparison.update_layout(
        title="Actual vs Target Competency Scores",
        height=500,
        yaxis={"range": [0, 5], "dtick": 1, "title": "Score"},
        xaxis_title="Competency",
        hovermode="x unified",
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
        margin={"l": 45, "r": 20, "t": 70, "b": 70},
    )

    radar = go.Figure()
    radar.add_trace(
        go.Scatterpolar(
            r=actual.fillna(0),
            theta=labels,
            fill="toself",
            name="Actual",
            line={"color": ACTUAL_COLOR, "width": 3},
            fillcolor="rgba(0,166,81,0.18)",
            marker={"color": ACTUAL_COLOR, "size": 6},
        )
    )
    radar.add_trace(
        go.Scatterpolar(
            r=target,
            theta=labels,
            name="Target",
            line={"color": TARGET_COLOR, "width": 3},
            marker={"color": TARGET_COLOR, "size": 6},
        )
    )
    radar.update_layout(
        title="Competency Radar",
        height=500,
        polar={
            "radialaxis": {"range": [0, 5], "dtick": 1, "visible": True},
        },
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
        margin={"l": 35, "r": 35, "t": 70, "b": 35},
    )
    return comparison, radar


def render_actual_target_charts(gap: pd.DataFrame) -> None:
    """Render the shared combo chart and matching radar chart side by side."""
    required = {"Competency", "Actual", "Target"}
    if gap is None or gap.empty or not required.issubset(gap.columns):
        st.info("No competency score/target data is available for visualization.")
        return

    chart_col, radar_col = st.columns([3, 2])
    comparison, radar = build_actual_target_figures(gap)
    chart_col.plotly_chart(comparison, width="stretch", config={"displaylogo": False})
    radar_col.plotly_chart(radar, width="stretch", config={"displaylogo": False})


def normalize_legacy_competency_figure(fig: go.Figure) -> go.Figure:
    """Apply the shared Actual/Target palette to legacy ADMIN figures at render time.

    The canonical ADMIN page still lives in the golden implementation. This
    adapter keeps that page visually identical to the USER experience without
    changing the golden source file or its regression-test contract.
    """
    title = str((fig.layout.title.text if fig.layout.title else "") or "")
    if title == "Actual vs Target Competency Scores":
        for trace in fig.data:
            if isinstance(trace, go.Bar):
                trace.name = "Actual"
                trace.marker.color = ACTUAL_COLOR
            elif isinstance(trace, go.Scatter):
                trace.name = "Target"
                trace.mode = "lines+markers"
                trace.line.color = TARGET_COLOR
                trace.line.width = 3
                trace.marker.color = TARGET_COLOR
                trace.marker.size = 7
        fig.update_layout(barmode=None, hovermode="x unified")
    elif title == "Competency Radar":
        for trace in fig.data:
            if isinstance(trace, go.Scatterpolar):
                if str(trace.name).lower() == "actual":
                    trace.line.color = ACTUAL_COLOR
                    trace.line.width = 3
                    trace.marker.color = ACTUAL_COLOR
                    trace.fillcolor = "rgba(0,166,81,0.18)"
                elif str(trace.name).lower() == "target":
                    trace.line.color = TARGET_COLOR
                    trace.line.width = 3
                    trace.marker.color = TARGET_COLOR
        fig.update_layout(hovermode="closest")
    return fig
