"""Refresh policy for the interactive chart-builder workspace."""

from __future__ import annotations


def chart_configuration_matches(
    last_meta: dict | None,
    current_config: dict,
) -> bool:
    """Return whether the last successful chart represents the current setup."""
    if not isinstance(last_meta, dict):
        return False
    return all(
        key in last_meta and last_meta[key] == value
        for key, value in current_config.items()
    )


def should_refresh_chart(
    *,
    live_update: bool,
    generate_clicked: bool,
    last_meta: dict | None,
    current_config: dict,
) -> bool:
    """Refresh on demand, or automatically only when the chart setup changes."""
    if generate_clicked:
        return True
    return bool(live_update and not chart_configuration_matches(last_meta, current_config))
