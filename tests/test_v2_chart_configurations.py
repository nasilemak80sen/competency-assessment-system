import pytest

from models import get_session, init_db
from v2.services.chart_configuration_service import (
    delete_chart_configuration,
    get_chart_configuration,
    list_chart_configurations,
    save_chart_configuration,
)


@pytest.fixture
def chart_config_session(tmp_path):
    engine = init_db(f"sqlite:///{tmp_path / 'chart-configurations.db'}")
    session = get_session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def test_chart_configuration_is_saved_and_restored(chart_config_session):
    saved = save_chart_configuration(
        chart_config_session,
        owner_user_id=7,
        owner_username="analyst",
        name="Department competency profile",
        description="Average B1 score by department",
        configuration={
            "filters": {"department": ["DPE"]},
            "chart": {"x": "Department", "y": "B1", "type": "Box Plot"},
        },
    )

    assert saved["created"] is True
    loaded = get_chart_configuration(chart_config_session, 7, saved["id"])
    assert loaded is not None
    assert loaded["name"] == "Department competency profile"
    assert loaded["configuration"]["chart"]["type"] == "Box Plot"
    assert loaded["configuration"]["filters"]["department"] == ["DPE"]


def test_chart_configuration_updates_by_case_insensitive_name(chart_config_session):
    first = save_chart_configuration(
        chart_config_session, 7, "analyst", "Age scatter",
        {"chart": {"x": "Age", "y": "Years in RE Experience"}},
    )
    second = save_chart_configuration(
        chart_config_session, 7, "analyst", "AGE SCATTER",
        {"chart": {"x": "Age", "y": "Years in PET"}},
    )

    assert first["id"] == second["id"]
    assert first["created"] is True
    assert second["created"] is False
    assert len(list_chart_configurations(chart_config_session, 7)) == 1

    loaded = get_chart_configuration(chart_config_session, 7, first["id"])
    assert loaded["name"] == "AGE SCATTER"
    assert loaded["configuration"]["chart"]["y"] == "Years in PET"


def test_chart_configurations_are_private_to_the_owner(chart_config_session):
    saved = save_chart_configuration(
        chart_config_session, 7, "analyst", "Private setup",
        {"chart": {"type": "Bubble Chart"}},
    )
    save_chart_configuration(
        chart_config_session, 8, "colleague", "Colleague setup",
        {"chart": {"type": "Scatter Plot"}},
    )

    assert [row["name"] for row in list_chart_configurations(chart_config_session, 7)] == [
        "Private setup"
    ]
    assert get_chart_configuration(chart_config_session, 8, saved["id"]) is None
    assert delete_chart_configuration(chart_config_session, 8, saved["id"]) is False
    assert get_chart_configuration(chart_config_session, 7, saved["id"]) is not None


def test_chart_configuration_delete_is_owner_scoped(chart_config_session):
    saved = save_chart_configuration(
        chart_config_session, 7, "analyst", "Remove me", {"chart": {}}
    )

    assert delete_chart_configuration(chart_config_session, 7, saved["id"]) is True
    assert get_chart_configuration(chart_config_session, 7, saved["id"]) is None


@pytest.mark.parametrize("name", ["", "   "])
def test_chart_configuration_requires_a_name(chart_config_session, name):
    with pytest.raises(ValueError, match="Enter a name"):
        save_chart_configuration(
            chart_config_session, 7, "analyst", name, {"chart": {}}
        )


def test_chart_configuration_converts_numpy_scalars_to_json(chart_config_session):
    import numpy as np

    saved = save_chart_configuration(
        chart_config_session,
        7,
        "analyst",
        "Numeric filters",
        {"filters": {"min_age": np.int64(35), "threshold": np.float64(2.5)}},
    )
    loaded = get_chart_configuration(chart_config_session, 7, saved["id"])
    assert loaded["configuration"]["filters"] == {
        "min_age": 35,
        "threshold": 2.5,
    }
