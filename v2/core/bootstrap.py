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
# Always put v2 first, even when Streamlit or the launching environment
# has already inserted it later in sys.path. A simple "if not in sys.path"
# check is insufficient because the root-level legacy analytics.py can win.
_V2_PATH = str(V2_DIR)
if _V2_PATH in sys.path:
    sys.path.remove(_V2_PATH)
sys.path.insert(0, _V2_PATH)

_ROOT_PATH = str(REPO_ROOT)
if _ROOT_PATH not in sys.path:
    sys.path.append(_ROOT_PATH)

# If the legacy root-level analytics.py was imported before this bootstrap,
# remove only that specific module so analytics.* resolves to v2/analytics.
# Do not evict an already-loaded v2 analytics package.
_legacy_analytics_file = (REPO_ROOT / "analytics.py").resolve()
_loaded_analytics = sys.modules.get("analytics")
_loaded_analytics_file = getattr(_loaded_analytics, "__file__", None)
if _loaded_analytics_file:
    try:
        if Path(_loaded_analytics_file).resolve() == _legacy_analytics_file:
            del sys.modules["analytics"]
    except (OSError, RuntimeError):
        # A path-resolution problem should not prevent application startup.
        pass


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
from models import init_db, get_session as db_get_session, Personnel  # noqa: E402
from services.heatmap_service import merge_database_personnel_for_heatmap  # noqa: E402


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


def _excel_cache_identity() -> tuple[str, int, int]:
    """Return a cache key that changes whenever the source workbook changes."""
    path = Path(EXCEL_PATH).expanduser().resolve()
    stat = path.stat()
    return str(path), stat.st_mtime_ns, stat.st_size


@st.cache_data(show_spinner="Loading master data…")
def _get_master_data_cached(path: str, modified_ns: int, file_size: int):
    # modified_ns and file_size are intentionally cache-key arguments.
    df = load_master_data(path)
    return add_category_averages(df)


def _normalise_overlay_key(value):
    """Normalise a Staff ID or name for joining Excel rows to database records."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    key = str(value).strip()
    if not key or key.casefold() in {"nan", "none", "nat"}:
        return None
    if key.endswith(".0") and key[:-2].isdigit():
        key = key[:-2]
    return key.casefold()


def _overlay_database_assessment_levels(df: pd.DataFrame, personnel_rows) -> pd.DataFrame:
    """Make SQLite's editable assessment level authoritative over the Excel snapshot.

    The workbook remains the baseline for bulk data and competency values. Once
    a personnel record exists in SQLite, however, its Assessment Level is the
    value edited by Admin CRUD and must be what all V2 pages display. A stored
    NULL is also respected so an intentional "Not specified" value can clear
    the workbook value.
    """
    if df is None or df.empty or "Assessment Level" not in df.columns:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()

    by_staff_id = {}
    name_candidates = {}
    for staff_id, name, assessment_level in personnel_rows:
        sid_key = _normalise_overlay_key(staff_id)
        name_key = _normalise_overlay_key(name)
        if sid_key:
            by_staff_id[sid_key] = assessment_level
        if name_key:
            name_candidates.setdefault(name_key, []).append(assessment_level)

    # Fall back to a name only when that name is unique in the database.
    by_name = {
        name: values[0]
        for name, values in name_candidates.items()
        if len(values) == 1
    }

    out = df.copy()
    for index, row in out.iterrows():
        sid_key = _normalise_overlay_key(row.get("Staff ID"))
        name_key = _normalise_overlay_key(row.get("Name"))
        if sid_key and sid_key in by_staff_id:
            out.at[index, "Assessment Level"] = by_staff_id[sid_key]
        elif name_key and name_key in by_name:
            out.at[index, "Assessment Level"] = by_name[name_key]
    return out


def get_master_data():
    """Load workbook data, then overlay assessment levels edited in SQLite.

    Excel remains the bulk-import source, while SQLite is the CRUD source of
    truth for assessment level. This keeps database edits visible across every
    page that consumes the shared master dataframe.
    """
    path, modified_ns, file_size = _excel_cache_identity()
    df = _get_master_data_cached(path, modified_ns, file_size)
    session = None
    try:
        session = db_get_session(get_database_engine())
        rows = (
            session.query(Personnel.staff_id, Personnel.name, Personnel.assessment_level)
            .filter(Personnel.is_deleted.is_(False))
            .all()
        )
        return _overlay_database_assessment_levels(df, rows)
    except Exception as exc:
        # Do not silently imply that CRUD changes are reflected if the database
        # overlay cannot be read. Keep the dashboard available and surface the
        # data-source problem to the operator.
        st.warning(f"Could not refresh Assessment Level values from SQLite: {exc}")
        return df
    finally:
        if session is not None:
            session.close()


@st.cache_data(show_spinner="Loading career rulers…")
def _get_ruler_data_cached(path: str, modified_ns: int, file_size: int):
    # modified_ns and file_size are intentionally cache-key arguments.
    return load_ruler_and_tech_mapping(path)


def get_ruler_data():
    """Load career-ruler requirements, refreshing cache when the file changes."""
    path, modified_ns, file_size = _excel_cache_identity()
    return _get_ruler_data_cached(path, modified_ns, file_size)


def open_session():
    """Open a database session; callers must close it."""
    return db_get_session(get_database_engine())


def set_selected_person(person_id=None, staff_id=None, name=None) -> None:
    """Set the canonical personnel selection shared across pages."""
    st.session_state.selected_personnel_id = person_id
    st.session_state.selected_staff_id = staff_id
    st.session_state.selected_person_name = name

def get_heatmap_data() -> pd.DataFrame:
    """Return workbook data reconciled with every non-deleted DB personnel row.

    The workbook provides the baseline competency matrix. SQLite contributes
    current personnel fields and the most recent assessment with non-null
    scores. Database-only personnel are kept even when they have no recorded
    competency scores, allowing the heatmap to show them as unassessed rows.
    """
    workbook_df = get_master_data()
    session = None
    records = []
    try:
        session = db_get_session(get_database_engine())
        people = (
            session.query(Personnel)
            .filter(Personnel.is_deleted.is_(False))
            .order_by(Personnel.name.asc(), Personnel.staff_id.asc())
            .all()
        )

        for person in people:
            scored_assessments = []
            for assessment in person.assessments or []:
                scored = {
                    score.competency_code: score.actual_score
                    for score in (assessment.scores or [])
                    if score.competency_code and score.actual_score is not None
                }
                if scored:
                    assessed_date = assessment.assessment_date
                    created_at = assessment.created_at
                    scored_assessments.append(
                        (
                            (
                                assessed_date is not None,
                                assessed_date.isoformat() if assessed_date is not None else "",
                                created_at.isoformat() if created_at is not None else "",
                                int(assessment.id or 0),
                            ),
                            scored,
                        )
                    )

            latest_scores = (
                max(scored_assessments, key=lambda item: item[0])[1]
                if scored_assessments
                else {}
            )
            records.append(
                {
                    "staff_id": person.staff_id,
                    "name": person.name,
                    "email": person.email,
                    "gender": person.gender,
                    "age": person.age,
                    "birth_year": person.birth_year,
                    "nationality": person.nationality,
                    "employment_category": person.employment_category,
                    "department": person.department,
                    "section_name": person.section_name,
                    "unit_name": person.unit_name,
                    "sub_unit": person.sub_unit,
                    "staff_position": person.staff_position,
                    "sg": person.sg,
                    "joining_date": person.joining_date,
                    "contract_expire_date": person.contract_expire_date,
                    "years_in_pet": person.years_in_pet,
                    "years_re_experience": person.years_re_experience,
                    "sg_years": person.sg_years,
                    "sg_start_date": person.sg_start_date,
                    "age_promoted": person.age_promoted,
                    "current_assignment": person.current_assignment,
                    "assignment_date": person.assignment_date,
                    "assignment_length": person.assignment_length,
                    "chat_status": person.chat_status,
                    "chat_date": person.chat_date,
                    "assessment_level": person.assessment_level,
                    "last_assessment_date": person.last_assessment_date,
                    "sub_disciplines": person.sub_disciplines,
                    "potential": person.potential,
                    "strength": person.strength,
                    "recommendation": person.recommendation,
                    "resource_sme": person.resource_sme,
                    "interest": person.interest,
                    "preference": person.preference,
                    "comment": person.comment,
                    "assessor1": person.assessor1,
                    "assessor2": person.assessor2,
                    "supervisor": person.supervisor,
                    "remarks": person.remarks,
                    "db_scores": latest_scores,
                }
            )

        return merge_database_personnel_for_heatmap(workbook_df, records)
    except Exception as exc:
        # Keep the view available if SQLite cannot be queried, but clearly
        # identify that the result may omit database-only personnel.
        st.warning(f"Could not reconcile database personnel for the heatmap: {exc}")
        return workbook_df.copy() if isinstance(workbook_df, pd.DataFrame) else pd.DataFrame()
    finally:
        if session is not None:
            session.close()

