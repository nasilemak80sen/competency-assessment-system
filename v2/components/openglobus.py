"""OpenGlobus 3D Earth visualization embedded in Streamlit.

The globe is rendered inside a Streamlit component iframe using the
OpenGlobus WebGL engine. Python remains responsible for preparing the
nationality data; JavaScript owns only the client-side globe rendering.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit.components.v1 as components


OPEN_GLOBUS_VERSION = "0.28.7"
OPEN_GLOBUS_JS = (
    f"https://cdn.jsdelivr.net/npm/@openglobus/og@{OPEN_GLOBUS_VERSION}/lib/og.es.js"
)
OPEN_GLOBUS_CSS = (
    f"https://cdn.jsdelivr.net/npm/@openglobus/og@{OPEN_GLOBUS_VERSION}/lib/og.css"
)
OPEN_GLOBUS_RESOURCES = (
    f"https://cdn.jsdelivr.net/npm/@openglobus/og@{OPEN_GLOBUS_VERSION}/lib/res"
)
OPEN_GLOBUS_FONTS = (
    f"https://cdn.jsdelivr.net/npm/@openglobus/og@{OPEN_GLOBUS_VERSION}/lib/res/fonts"
)


def _records_from_map_df(map_df: pd.DataFrame) -> list[dict]:
    """Convert prepared nationality data into JSON-safe globe records."""
    if map_df is None or map_df.empty:
        return []

    required = {"Nationality", "Personnel Count", "Latitude", "Longitude"}
    missing = required.difference(map_df.columns)
    if missing:
        raise ValueError(
            f"OpenGlobus nationality data is missing columns: {sorted(missing)}"
        )

    records: list[dict] = []
    for _, row in map_df.iterrows():
        try:
            count = int(float(row["Personnel Count"]))
            latitude = float(row["Latitude"])
            longitude = float(row["Longitude"])
        except (TypeError, ValueError):
            continue

        if count <= 0:
            continue

        representation = row.get("Representation Display", "")
        if pd.isna(representation):
            representation = ""

        records.append(
            {
                "nationality": str(row["Nationality"]),
                "count": count,
                "latitude": latitude,
                "longitude": longitude,
                "representation": str(representation),
            }
        )

    return records


def _build_openglobus_html(records: list[dict], height: int = 560) -> str:
    """Build the self-contained OpenGlobus iframe document."""
    safe_height = max(420, int(height))
    payload = json.dumps(records, ensure_ascii=False).replace("</", "<\\\\/")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="{OPEN_GLOBUS_CSS}">
<style>
    :root {{
        color-scheme: light;
        --globe-bg: #eef4f5;
        --accent: #00a19c;
        --text: #183238;
    }}

    html, body {{
        width: 100%;
        height: 100%;
        margin: 0;
        padding: 0;
        overflow: hidden;
        background: transparent;
        font-family: Arial, sans-serif;
    }}

    #shell {{
        position: relative;
        width: 100%;
        height: {safe_height}px;
        min-height: 420px;
        overflow: hidden;
        border-radius: 14px;
        background:
            radial-gradient(circle at 50% 45%, #ffffff 0%, var(--globe-bg) 62%, #dfeaec 100%);
        box-shadow: inset 0 0 0 1px rgba(22, 58, 64, 0.08);
    }}

    #globus {{
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
    }}

    #hud {{
        position: absolute;
        left: 16px;
        top: 14px;
        z-index: 20;
        pointer-events: none;
        padding: 9px 12px;
        border-radius: 10px;
        background: rgba(255,255,255,0.86);
        backdrop-filter: blur(8px);
        box-shadow: 0 5px 18px rgba(18, 47, 53, 0.10);
        color: var(--text);
    }}

    #hud .title {{
        font-size: 13px;
        font-weight: 700;
        letter-spacing: 0.02em;
    }}

    #hud .subtitle {{
        margin-top: 2px;
        font-size: 10px;
        opacity: 0.68;
    }}

    #status {{
        position: absolute;
        left: 50%;
        top: 50%;
        transform: translate(-50%, -50%);
        z-index: 30;
        padding: 12px 16px;
        border-radius: 10px;
        background: rgba(255,255,255,0.94);
        box-shadow: 0 8px 28px rgba(18, 47, 53, 0.15);
        color: var(--text);
        font-size: 13px;
    }}

    #status.hidden {{
        display: none;
    }}

    #attribution {{
        position: absolute;
        right: 12px;
        bottom: 9px;
        z-index: 20;
        padding: 4px 7px;
        border-radius: 6px;
        background: rgba(255,255,255,0.78);
        color: #4a6065;
        font-size: 9px;
        line-height: 1.3;
        pointer-events: none;
    }}

    #attribution a {{
        color: #34666c;
        text-decoration: none;
    }}

    .og-control {{
        font-family: Arial, sans-serif;
    }}
</style>
</head>
<body>
<div id="shell">
    <div id="globus"></div>

    <div id="hud">
        <div class="title">🌍 RE Nationality Globe</div>
        <div class="subtitle">Interactive 3D personnel distribution</div>
    </div>

    <div id="status">Loading 3D Earth…</div>

    <div id="attribution">
        OpenGlobus ·
        <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">
            © OpenStreetMap contributors
        </a>
    </div>
</div>

<script type="module">
import {{
    Globe,
    GlobusRgbTerrain,
    OpenStreetMap,
    control,
    Vector
}} from "{OPEN_GLOBUS_JS}";

const records = {payload};

const shell = document.getElementById("shell");
const status = document.getElementById("status");

function hideStatus() {{
    status.classList.add("hidden");
}}

function markerSvg(count) {{
    const maxCount = Math.max(...records.map((item) => item.count), 1);
    const normalized = Math.sqrt(count) / Math.sqrt(maxCount);
    const radius = 12 + normalized * 14;
    const diameter = Math.ceil(radius * 2 + 8);

    const svg =
        '<svg xmlns="http://www.w3.org/2000/svg" width="' + diameter +
        '" height="' + diameter + '" viewBox="0 0 ' + diameter + ' ' + diameter + '">' +
        '<defs><filter id="shadow" x="-50%" y="-50%" width="200%" height="200%">' +
        '<feDropShadow dx="0" dy="2" stdDeviation="2.2" flood-color="#073f43" flood-opacity="0.32"/>' +
        '</filter></defs>' +
        '<circle cx="' + (diameter / 2) + '" cy="' + (diameter / 2) +
        '" r="' + radius + '" fill="#00A19C" fill-opacity="0.84" stroke="#ffffff" ' +
        'stroke-width="2" filter="url(#shadow)"/></svg>';

    return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
}}

const osm = new OpenStreetMap("OpenStreetMap", {{
    isBaseLayer: true,
    visibility: true,
    attribution: "© OpenStreetMap contributors, ODbL"
}});

const entities = records.map((item) => ({{
    name: item.nationality,
    lonlat: [item.longitude, item.latitude],
    billboard: {{
        src: markerSvg(item.count),
        size: [36, 36],
        offset: [0, 18],
        color: "rgba(255,255,255,0.96)"
    }},
    label: {{
        text: item.nationality + " · " + item.count,
        size: 14,
        offset: [0, 30, 0],
        color: "rgba(24,50,56,0.96)",
        outlineColor: "rgba(255,255,255,0.95)",
        outline: 2
    }},
    properties: {{
        nationality: item.nationality,
        personnel: item.count,
        representation: item.representation
    }}
}}));

const nationalityLayer = new Vector("Nationalities", {{
    entities,
    clampToGround: true,
    async: false,
    scaleByDistance: [10000, 5000000, 1]
}});

try {{
    const globe = new Globe({{
        target: "globus",
        name: "RE Nationality Globe",
        terrain: new GlobusRgbTerrain(),
        layers: [osm, nationalityLayer],
        atmosphereEnabled: true,
        resourcesSrc: "{OPEN_GLOBUS_RESOURCES}",
        fontsSrc: "{OPEN_GLOBUS_FONTS}",
        msaa: 4,
        idleMode: true,
        navigation: {{
            mode: "north",
            inertia: 0.18,
            zoomSpeed: 1.15
        }}
    }});

    if (control.KeyboardNavigation) {{
        globe.renderer.addControl(new control.KeyboardNavigation());
    }}

    hideStatus();

    window.setTimeout(() => window.dispatchEvent(new Event("resize")), 250);
}} catch (error) {{
    console.error("OpenGlobus initialization failed:", error);
    status.textContent =
        "3D Earth could not be initialized. Check WebGL/network access.";
}}
</script>
</body>
</html>
"""


def render_nationality_globe(
    map_df: pd.DataFrame,
    *,
    height: int = 560,
) -> None:
    """Render the OpenGlobus nationality globe inside Streamlit."""
    records = _records_from_map_df(map_df)

    if not records:
        raise ValueError("Nationality globe data cannot be empty.")

    components.html(
        _build_openglobus_html(records, height=height),
        height=max(420, int(height)),
        scrolling=False,
    )


__all__ = [
    "OPEN_GLOBUS_VERSION",
    "render_nationality_globe",
    "_build_openglobus_html",
    "_records_from_map_df",
]
