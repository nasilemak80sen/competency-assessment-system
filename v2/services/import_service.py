"""Import workflow service boundary.

Phase 1 deliberately delegates to the existing db_ops implementation. No
business rule is duplicated or changed here yet.
"""

from __future__ import annotations


def bulk_import_from_dataframe(session, raw_df, *, ruler_map=None):
    """Delegate the existing import operation unchanged."""
    import db_ops

    return db_ops.bulk_import_from_df(session, raw_df, ruler_map=ruler_map)


def bulk_import_cv_list(session, cv_df):
    """Delegate the existing CV import operation unchanged."""
    import db_ops

    return db_ops.bulk_import_cv_list(session, cv_df)
