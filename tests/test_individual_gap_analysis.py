import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from analytics import gap_analysis_individual
import db_ops
from data_loader import _normalize_summary_column_name
from models import Base, Personnel


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


def test_get_wide_dataframe_includes_summary_scores_from_database():
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    person = Personnel(staff_id='TEST-1', name='Sample Person', is_deleted=False)
    session.add(person)
    session.commit()
    session.refresh(person)

    ok, _ = db_ops.upsert_summary_score(session, person.id, {
        'staff_base': 3.5,
        'staff_keys': 4.0,
        'principal_base': 2.5,
    })

    assert ok is True

    wide_df = db_ops.get_wide_dataframe(session)

    assert 'Staff Base' in wide_df.columns
    assert wide_df.loc[0, 'Staff Base'] == 3.5
    assert wide_df.loc[0, 'Staff Keys'] == 4.0
    assert wide_df.loc[0, 'Principal Base'] == 2.5


def test_normalize_summary_column_name_strips_suffix_digits():
    assert _normalize_summary_column_name('Staff Base2') == 'Staff Base'
    assert _normalize_summary_column_name('Staff Keys3') == 'Staff Keys'
    assert _normalize_summary_column_name('Staff Pacing4') == 'Staff Pacing'
    assert _normalize_summary_column_name('Staff Emerging5') == 'Staff Emerging'
    assert _normalize_summary_column_name('Staff CTI6') == 'Staff CTI'
