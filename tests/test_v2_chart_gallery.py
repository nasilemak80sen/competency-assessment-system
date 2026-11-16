import pandas as pd

from v2.services.chart_gallery_service import build_chart_preview


def _workforce():
    return pd.DataFrame({
        "Name": ["A", "B", "C", "D"],
        "Staff ID": ["001", "002", "003", "004"],
        "Department": ["DPE", "DPE", "PSR", "PSR"],
        "Age": [32, 41, 38, 45],
        "Years of RE Experience": [6.0, 15.0, 11.0, 19.0],
        "Years in PET": [4.0, 12.0, 9.0, 17.0],
        "B1": [3.0, 4.0, 2.0, 5.0],
    })


def test_gallery_preview_rebuilds_saved_scatter_with_saved_filters():
    preview = build_chart_preview(
        {
            "filters": {"primary": {"Department": ["DPE"]}},
            "chart": {
                "chart_type": "Scatter Plot",
                "dimension": "Age",
                "measure": "Years of RE Experience",
                "aggregation": "Average",
            },
        },
        _workforce(),
    )

    assert preview is not None
    assert len(preview.data) > 0
    assert len(preview.data[0].x) == 2
    assert preview.data[0].hoverinfo == "skip"
    assert preview.layout.height == 190


def test_gallery_preview_supports_bubble_chart():
    preview = build_chart_preview(
        {
            "filters": {},
            "chart": {
                "chart_type": "Bubble Chart",
                "dimension": "Years of RE Experience",
                "measure": "B1",
                "size": "Years in PET",
                "aggregation": "Average",
            },
        },
        _workforce(),
    )

    assert preview is not None
    assert preview.data
    assert preview.data[0].marker.size is not None


def test_gallery_preview_supports_box_plot():
    preview = build_chart_preview(
        {
            "filters": {},
            "chart": {
                "chart_type": "Box Plot",
                "dimension": "Department",
                "measure": "B1",
                "aggregation": "Average",
            },
        },
        _workforce(),
    )

    assert preview is not None
    assert preview.data
    assert preview.data[0].type == "box"
    assert preview.data[0].hoverinfo == "skip"


def test_gallery_preview_hides_removed_source_field_gracefully():
    preview = build_chart_preview(
        {
            "filters": {},
            "chart": {
                "chart_type": "Scatter Plot",
                "dimension": "Age at Hire",
                "measure": "Years of RE Experience",
            },
        },
        _workforce(),
    )

    assert preview is None


def test_gallery_preview_handles_empty_saved_filter_result():
    preview = build_chart_preview(
        {
            "filters": {"primary": {"Department": ["No matching department"]}},
            "chart": {
                "chart_type": "Scatter Plot",
                "dimension": "Age",
                "measure": "Years of RE Experience",
            },
        },
        _workforce(),
    )

    assert preview is None
