"""Streamlit iframe adapter for the modular OpenGlobus frontend.

Geospatial aggregation and validation live in services.geospatial_service.
This module only validates/packages frontend assets and mounts the iframe.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import streamlit.components.v1 as components
from v2.services.geospatial_service import validate_nationality_dataset

OPEN_GLOBUS_VERSION = "0.28.7"
OPEN_GLOBUS_JS = f"https://cdn.jsdelivr.net/npm/@openglobus/og@{OPEN_GLOBUS_VERSION}/lib/og.es.js"
OPEN_GLOBUS_RESOURCES = f"https://cdn.jsdelivr.net/npm/@openglobus/og@{OPEN_GLOBUS_VERSION}/lib/res"
OPEN_GLOBUS_FONTS = f"https://cdn.jsdelivr.net/npm/@openglobus/og@{OPEN_GLOBUS_VERSION}/lib/res/fonts"
_FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend" / "openglobus"
_MODULE_ORDER = ("contract.js", "filters.js", "markers.js", "layers.js", "details.js", "camera.js")


def _safe_json(value: Any) -> str:
    """Serialize safely inside an HTML script element."""
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    )


def _read_frontend_file(name: str) -> str:
    path = _FRONTEND_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"OpenGlobus frontend asset is missing: {path}")
    return path.read_text(encoding="utf-8")


def _build_openglobus_html(dataset: dict[str, Any], height: int = 620) -> str:
    """Build the iframe document from independently maintained frontend files."""
    validate_nationality_dataset(dataset)
    safe_height = max(520, int(height))
    template = _read_frontend_file("index.html")
    css = _read_frontend_file("styles.css").replace("__HEIGHT__", str(safe_height))
    scripts = []
    for module_name in _MODULE_ORDER:
        source = _read_frontend_file(module_name)
        if "</script" in source.casefold():
            raise ValueError(f"Unsafe closing script tag in frontend module {module_name}")
        scripts.append(f'<script data-re-globe-module="{module_name}">\n{source}\n</script>')
    main_script = _read_frontend_file("main.js")
    if "</script" in main_script.casefold():
        raise ValueError("Unsafe closing script tag in OpenGlobus main module")
    config = {
        "schemaVersion": dataset["schemaVersion"],
        "datasetType": dataset["datasetType"],
        "summary": dataset["summary"],
        "records": dataset["records"],
        "openGlobusUrl": OPEN_GLOBUS_JS,
        "resourcesUrl": OPEN_GLOBUS_RESOURCES,
        "fontsUrl": OPEN_GLOBUS_FONTS,
    }
    html = (
        template.replace("__CSS__", css)
        .replace("__CONFIG_JSON__", _safe_json(config))
        .replace("__MODULE_SCRIPTS__", "\n".join(scripts))
        .replace("__MAIN_SCRIPT__", main_script)
    )
    unresolved = [token for token in (
        "__CSS__", "__CONFIG_JSON__", "__MODULE_SCRIPTS__", "__MAIN_SCRIPT__"
    ) if token in html]
    if unresolved:
        raise RuntimeError(f"Unresolved OpenGlobus HTML template tokens: {unresolved}")
    return html


def render_nationality_globe(dataset: dict[str, Any], *, height: int = 620) -> None:
    """Render a validated renderer-neutral dataset in the OpenGlobus iframe."""
    components.html(
        _build_openglobus_html(dataset, height=height),
        height=max(520, int(height)),
        scrolling=False,
    )


__all__ = ["OPEN_GLOBUS_VERSION", "render_nationality_globe", "_build_openglobus_html"]
