"""V2 application bootstrap and shared runtime context."""
from __future__ import annotations

import functools
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

V2_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = V2_DIR.parent
# Keep v2 packages ahead of root-level legacy modules. The repository root is
# still exposed so v2 can import proven data/model modules such as config.py,
# data_loader.py and models.py without shadowing v2.analytics.
if str(V2_DIR) not in sys.path:
    sys.path.insert(0, str(V2_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))


def _patch_streamlit_width_compatibility() -> None:
    """Backport ``width=\"stretch\"`` to older Streamlit widget APIs.

    v2 was developed against a newer Streamlit release where several widgets
    accept a ``width`` keyword. Some deployed environments still expose the
    older ``use_container_width`` API instead. Translate the modern keyword
    centrally for both ``st.<widget>`` and ``container.<widget>`` calls so
    every v2 page remains compatible without duplicating version checks.
    """
    widget_names = (
        "button",
        "download_button",
        "link_button",
        "dataframe",
        "plotly_chart",
    )

    # Patch the module-level st methods first. Then patch DeltaGenerator so
    # calls made through columns, containers, tabs, expanders, etc. receive
    # the same compatibility treatment.
    targets = [st, DeltaGenerator]
    for target in targets:
        for widget_name in widget_names:
            original = getattr(target, widget_name, None)
            if original is None or getattr(original, "_v2_width_compat", False):
                continue

            @functools.wraps(original)
            def compatible_widget(*args, __original=original, **kwargs):
                width = kwargs.pop("width", None)
                if width == "stretch":
                    kwargs.setdefault("use_container_width", True)
                elif width is not None:
                    # Older Streamlit versions cannot express fixed widget
                    # width through these APIs, so simply omit unsupported
                    # values rather than crashing.
                    pass
                return __original(*args, **kwargs)

            compatible_widget._v2_width_compat = True
            setattr(target, widget_name, compatible_widget)


_patch_streamlit_width_compatibility()

from config import (  # noqa: E402
    APP_TITLE,
    COMP_TYPES,
    DATABASE_URL,
    EXCEL_PATH,
    SCORE_COLS,
)
from data_loader import load_master_data, load_ruler_and_tech_mapping  # noqa: E402
from models import init_db, get_session as db_get_session  # noqa: E402


def initialise_session() -> None:
    """Create stable cross-page state without overwriting widget-owned keys."""
    defaults = {
        "selected_personnel_id": None,
        "selected_staff_id": None,
        "selected_person_name": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def add_category_averages(df: pd.DataFrame) -> pd.DataFrame:
    """Match the golden app's derived dashboard columns exactly.

    The legacy app loads the master workbook and immediately derives one
    average column for each competency class plus ``Overall_avg``. Dashboard
    and other v2 pages therefore receive the same analytical dataframe shape
    rather than a raw workbook dataframe.
    """
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()

    out = df.copy()
    for competency_type, info in COMP_TYPES.items():
        cols = [column for column in info.get("cols", []) if column in out.columns]
        out[f"{competency_type}_avg"] = (
            out[cols].mean(axis=1, skipna=True) if cols else pd.Series(float("nan"), index=out.index)
        )

    available_scores = [column for column in SCORE_COLS if column in out.columns]
    out["Overall_avg"] = (
        out[available_scores].mean(axis=1, skipna=True)
        if available_scores
        else pd.Series(float("nan"), index=out.index)
    )
    return out


@st.cache_resource(show_spinner=False)
def get_database_engine():
    """Return one SQLAlchemy engine for the Streamlit process."""
    return init_db(DATABASE_URL)


@st.cache_data(show_spinner="Loading master data…")
def get_master_data():
    """Load the live master workbook and apply the golden derived columns."""
    df = load_master_data(EXCEL_PATH)
    return add_category_averages(df)


@st.cache_data(show_spinner="Loading career rulers…")
def get_ruler_data():
    """Load career-ruler requirements and competency labels."""
    return load_ruler_and_tech_mapping(EXCEL_PATH)


def open_session():
    """Open a database session; callers must close it."""
    return db_get_session(get_database_engine())


def set_selected_person(person_id=None, staff_id=None, name=None) -> None:
    """Set the canonical personnel selection shared across pages."""
    st.session_state.selected_personnel_id = person_id
    st.session_state.selected_staff_id = staff_id
    st.session_state.selected_person_name = name
