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
