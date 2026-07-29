import pandas as pd
from analytics import gap_analysis_individual


def test_gap_analysis_individual_includes_gap_rows_for_higher_grades():
    row = pd.Series({
        'B1': 2,
        'R-B1': 3,
        'G--B1': -1,
        'K1': 2,
        'R-K1': 3,
        'G--K1': -1,
        'P1': 2,
        'R-P1': 3,
        'G--P1': -1,
        'E1': 2,
        'R-E1': 3,
        'G--E1': -1,
    })

    df = gap_analysis_individual(
        row,
        name_map={},
        ruler_requirements={
            'P3': {'B1': 3, 'K1': 3, 'P1': 3, 'E1': 3},
            'P4': {'B1': 3, 'K1': 3, 'P1': 3, 'E1': 3},
        },
        current_sg='P3',
        include_future_grades=True,
    )

    assert 'P4' in set(df['Target Grade'])
    assert 'P3' in set(df['Target Grade'])
    assert len(df) >= 8
