from pathlib import Path

from v2.services.chart_workspace_service import (
    chart_configuration_matches,
    should_refresh_chart,
)


def _config(**overrides):
    values = {
        "chart_type": "Scatter Plot",
        "dimension": "Age",
        "measure": "Years of RE Experience",
        "rows": 120,
        "filter_signature": ("Department: DPE",),
    }
    values.update(overrides)
    return values


def test_manual_mode_keeps_previous_chart_when_controls_change():
    assert should_refresh_chart(
        live_update=False,
        generate_clicked=False,
        last_meta=_config(),
        current_config=_config(measure="Years in PET"),
    ) is False


def test_generate_button_always_refreshes_in_manual_mode():
    assert should_refresh_chart(
        live_update=False,
        generate_clicked=True,
        last_meta=_config(),
        current_config=_config(measure="Years in PET"),
    ) is True


def test_live_update_builds_chart_when_no_previous_chart_exists():
    assert should_refresh_chart(
        live_update=True,
        generate_clicked=False,
        last_meta=None,
        current_config=_config(),
    ) is True


def test_live_update_refreshes_when_a_chart_setting_changes():
    assert should_refresh_chart(
        live_update=True,
        generate_clicked=False,
        last_meta=_config(),
        current_config=_config(measure="Years in PET"),
    ) is True


def test_live_update_does_not_rebuild_an_unchanged_chart():
    config = _config()
    assert chart_configuration_matches(config, config)
    assert should_refresh_chart(
        live_update=True,
        generate_clicked=False,
        last_meta=config,
        current_config=config,
    ) is False


def test_filter_changes_trigger_live_refresh():
    assert should_refresh_chart(
        live_update=True,
        generate_clicked=False,
        last_meta=_config(),
        current_config=_config(filter_signature=("Department: PSR",)),
    ) is True


def test_workforce_filters_are_rendered_above_chart_workspace():
    page = Path("v2/pages/06_Chart_Builder.py").read_text(encoding="utf-8")
    filters_at = page.index("# WORKFORCE FILTER TOOLBAR")
    workspace_at = page.index('chart_controls_col, chart_workspace_col = st.columns([3, 9]')
    assert filters_at < workspace_at
    assert 'key="cb_reset_filters_v2"' in page
    assert 'key="cb_reset_chart_setup_v2"' in page


def test_chart_configuration_does_not_contain_workforce_filter_widgets():
    page = Path("v2/pages/06_Chart_Builder.py").read_text(encoding="utf-8")
    controls = page.split('chart_controls_col, chart_workspace_col = st.columns([3, 9]', 1)[1]
    controls = controls.split("with chart_workspace_col:", 1)[0]
    assert "st.text_input(" not in controls
    assert "st.multiselect(" not in controls
    assert "with chart_workspace_col:" in page
    assert "with chart_col:" not in page
