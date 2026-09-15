"""V2 application bootstrap and shared runtime context."""
from __future__ import annotations

import sys
from pathlib import Path
import streamlit as st

V2_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = V2_DIR.parent
# Keep v2 packages ahead of root-level legacy modules. The repository root is
# still exposed so v2 can import proven data/model modules such as config.py,
# data_loader.py and models.py without shadowing v2.analytics.
if str(V2_DIR) not in sys.path:
    sys.path.insert(0, str(V2_DIR))
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from config import APP_TITLE, DATABASE_URL, EXCEL_PATH  # noqa: E402
from data_loader import load_master_data, load_ruler_and_tech_mapping  # noqa: E402
from models import init_db, get_session as db_get_session  # noqa: E402


def initialise_session() -> None:
    """Create stable cross-page state without overwriting widget-owned keys."""
    defaults = {"selected_personnel_id": None, "selected_staff_id": None, "selected_person_name": None}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


@st.cache_resource(show_spinner=False)
def get_database_engine():
    """Return one SQLAlchemy engine for the Streamlit process."""
    return init_db(DATABASE_URL)


@st.cache_data(show_spinner="Loading master data…")
def get_master_data():
    """Load and normalize the Excel master dataset."""
    return load_master_data(EXCEL_PATH)


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
