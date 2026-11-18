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
