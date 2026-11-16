import pandas as pd
import pytest

from chart_builder import ChartBuilder, ChartCompatibility, DataType


@pytest.fixture
def workforce_df():
    return pd.DataFrame({
        "Name": ["A", "B", "C", "D", "E", "F"],
        "Department": ["RE", "RE", "PE", "PE", "PE", "RE"],
        "Nationality": ["MY", "MY", "UK", "MY", "UK", "MY"],
        "SG": [14, 14, 15, 15, 16, 16],
        "Score": [4.0, 3.0, 5.0, 2.0, 4.0, 4.5],
    })


def test_missing_ratio_uses_row_count(workforce_df):
    series = workforce_df["Score"].copy()
    series.iloc[:3] = None
    info = ChartCompatibility.analyze_data_element(series, "Score")
    assert info.null_count == 3
    assert info.row_count == 6
    assert info.missing_ratio == pytest.approx(0.5)


def test_selectable_columns_is_instance_method(workforce_df):
    builder = ChartBuilder(workforce_df)
    columns = builder.get_selectable_columns()
    assert "Name" in columns
    assert "Score" in columns


def test_numeric_codes_can_be_semantically_used_as_numeric_or_categorical(workforce_df):
    info = ChartCompatibility.analyze_data_element(workforce_df["SG"], "SG")
    assert info.data_type == DataType.NUMERIC


def test_count_aggregation_without_measure(workforce_df):
    result = ChartBuilder(workforce_df).aggregate("Department", aggregation="Count")
    counts = dict(zip(result["Department"], result["value"]))
    assert counts == {"PE": 3, "RE": 3}


def test_average_aggregation(workforce_df):
    result = ChartBuilder(workforce_df).aggregate("Department", "Score", "Average")
    values = dict(zip(result["Department"], result["value"]))
    assert values["PE"] == pytest.approx((5 + 2 + 4) / 3)
    assert values["RE"] == pytest.approx((4 + 3 + 4.5) / 3)


def test_top_n_is_ranked_not_first_n(workforce_df):
    result = ChartBuilder(workforce_df).aggregate(
        "Nationality", aggregation="Count", top_n=1
    )
    assert result["Nationality"].tolist() == ["MY"]
    assert result["value"].tolist() == [4]


def test_dynamic_filtering(workforce_df):
    builder = ChartBuilder(workforce_df)
    result = builder.apply_filters({"Department": ["RE"]})
    assert len(result) == 3
    assert set(result["Department"]) == {"RE"}


def test_recommendation_for_categorical_average(workforce_df):
    builder = ChartBuilder(workforce_df)
    x = ChartCompatibility.analyze_data_element(workforce_df["Department"], "Department")
    y = ChartCompatibility.analyze_data_element(workforce_df["Score"], "Score")
    recommendations = ChartCompatibility.recommend(x, y, "Average")
    assert recommendations
    assert recommendations[0]["chart"] == "Bar Chart"


def test_recommendation_for_numeric_relationship(workforce_df):
    x = ChartCompatibility.analyze_data_element(workforce_df["SG"], "SG")
    y = ChartCompatibility.analyze_data_element(workforce_df["Score"], "Score")
    recommendations = ChartCompatibility.recommend(x, y, "Average")
    assert recommendations[0]["chart"] == "Scatter Plot"


def test_grouped_bar_chart_generation(workforce_df):
    figure = ChartBuilder(workforce_df).create_chart(
        "Bar Chart",
        "Department",
        "Score",
        aggregation="Average",
    )
    assert figure.data
    assert len(figure.data[0].x) == 2


def test_count_pie_chart_generation(workforce_df):
    figure = ChartBuilder(workforce_df).create_chart(
        "Pie Chart",
        "Nationality",
        aggregation="Count",
        top_n=10,
    )
    assert figure.data
    assert set(figure.data[0].labels) == {"MY", "UK"}


def test_scatter_drops_missing_visual_encoding_values(workforce_df):
    workforce_df.loc[1, "Score"] = None
    workforce_df.loc[3, "SG"] = None
    figure = ChartBuilder(workforce_df).create_chart(
        "Scatter Plot", "SG", "Score", aggregation="Average"
    )
    assert figure.data
    assert len(figure.data[0].x) == 4


def test_bubble_drops_missing_size_values(workforce_df):
    workforce_df["Size"] = [10, None, 20, 30, None, 40]
    figure = ChartBuilder(workforce_df).create_chart(
        "Bubble Chart", "SG", "Score", size_col="Size", aggregation="Average"
    )
    assert figure.data
    assert len(figure.data[0].x) == 4


def test_chart_builder_field_allowlist_excludes_unrelated_workbook_columns():
    from chart_builder import (
        CHART_BUILDER_FIELDS,
        get_chart_builder_field_label,
        get_chart_builder_fields,
    )

    dataframe = pd.DataFrame({
        "Name": ["A"],
        "Department": ["DPE"],
        "Age": [37],
        "R-B1": [3.0],
        "G--B1": [-1.0],
        "Contract Expire Date": [pd.Timestamp("2027-01-01")],
        "Last Assesment Date Source": ["2026"],
        "Helper Column": [99],
    })

    selected = get_chart_builder_fields(dataframe)
    assert selected == ["Name", "Age", "Department", "R-B1", "G--B1"]
    assert "Contract Expire Date" not in CHART_BUILDER_FIELDS
    assert "Helper Column" not in selected
    assert get_chart_builder_field_label("G--B1") == "G-B1"


def test_numeric_aggregation_returns_actual_measure_and_sample_sizes():
    dataframe = pd.DataFrame({
        "Department": ["DPE", "DPE", "PSR"],
        "Score": [4.0, None, 2.0],
    })

    result = ChartBuilder(dataframe).aggregate(
        "Department", "Score", aggregation="Average"
    )
    by_department = result.set_index("Department")

    assert by_department.loc["DPE", "value"] == pytest.approx(4.0)
    assert by_department.loc["DPE", "Records"] == 2
    assert by_department.loc["DPE", "Valid Values"] == 1
    assert by_department.loc["PSR", "value"] == pytest.approx(2.0)
    assert by_department.loc["PSR", "Records"] == 1
    assert by_department.loc["PSR", "Valid Values"] == 1


def test_numeric_bar_chart_uses_aggregated_measure_not_row_count():
    dataframe = pd.DataFrame({
        "Department": ["DPE", "DPE", "PSR"],
        "Score": [4.0, 2.0, 5.0],
    })

    figure = ChartBuilder(dataframe).create_chart(
        "Bar Chart", "Department", "Score", aggregation="Average"
    )

    trace = figure.data[0]
    plotted = dict(zip(trace.x, trace.y))
    assert plotted["DPE"] == pytest.approx(3.0)
    assert plotted["PSR"] == pytest.approx(5.0)
    assert figure.layout.yaxis.title.text == "Average of Score"


def test_chart_builder_field_list_contains_all_competency_score_requirement_and_gap_columns():
    from chart_builder import CHART_BUILDER_FIELDS

    for code in (
        [f"B{i}" for i in range(1, 13)]
        + [f"K{i}" for i in range(1, 6)]
        + [f"P{i}" for i in range(1, 6)]
        + ["E1", "E2"]
    ):
        assert code in CHART_BUILDER_FIELDS
        assert f"R-{code}" in CHART_BUILDER_FIELDS
        assert f"G--{code}" in CHART_BUILDER_FIELDS


def test_box_plot_generation_for_categorical_group_and_numeric_measure(workforce_df):
    figure = ChartBuilder(workforce_df).create_chart(
        "Box Plot",
        "Department",
        "Score",
    )

    assert figure.data
    assert len(figure.data) >= 1
    assert figure.layout.yaxis.title.text == "Score"


def test_numeric_relationship_recommends_bubble_as_a_three_measure_option(workforce_df):
    x = ChartCompatibility.analyze_data_element(workforce_df["SG"], "SG")
    y = ChartCompatibility.analyze_data_element(workforce_df["Score"], "Score")
    recommendations = ChartCompatibility.recommend(x, y)

    assert recommendations[0]["chart"] == "Scatter Plot"
    assert any(item["chart"] == "Bubble Chart" for item in recommendations)
