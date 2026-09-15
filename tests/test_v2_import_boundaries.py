"""Import, navigation and golden-dashboard parity smoke tests."""
from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
V2_DIR = REPO_ROOT / "v2"


def _prepare_v2_path() -> None:
    """Mirror the path contract established by v2/core/bootstrap.py."""
    if str(V2_DIR) not in sys.path:
        sys.path.insert(0, str(V2_DIR))
    if str(REPO_ROOT) not in sys.path:
        sys.path.append(str(REPO_ROOT))


def test_bootstrap_import_contract():
    _prepare_v2_path()
    bootstrap = importlib.import_module("core.bootstrap")
    assert bootstrap.APP_TITLE if hasattr(bootstrap, "APP_TITLE") else True
    assert importlib.import_module("config")
    assert importlib.import_module("data_loader")
    assert importlib.import_module("models")


def test_native_analytics_imports_are_resolvable():
    _prepare_v2_path()
    readiness = importlib.import_module("analytics.readiness")
    charts = importlib.import_module("analytics.charts")
    competency = importlib.import_module("analytics.competency")
    nationality = importlib.import_module("analytics.nationality")
    workforce = importlib.import_module("analytics.workforce")

    assert hasattr(readiness, "build_readiness_detail_dataframe")
    assert hasattr(charts, "_create_readiness_status_chart")
    assert hasattr(competency, "build_heatmap_matrix")
    assert hasattr(nationality, "prepare_nationality_map_data")
    assert hasattr(workforce, "scatter_age_vs_grade")


def test_analytics_package_does_not_resolve_to_legacy_module():
    _prepare_v2_path()
    analytics = importlib.import_module("analytics")
    assert getattr(analytics, "__file__", "").replace("\\", "/").startswith(
        str(V2_DIR).replace("\\", "/")
    )


def test_page_registry_is_canonical_and_matches_golden_order():
    _prepare_v2_path()
    pages = importlib.import_module("core.pages")

    assert len(pages.PAGES) == 7
    assert len(pages.PAGE_BY_PATH) == 7
    assert pages.PAGE_BY_PATH[""] is pages.PAGES[0]

    expected_titles = [
        "🏠 Dashboard Home",
        "🌡️ Competency Heatmap",
        "👤 Individual Assessment & Talent Profile",
        "🎯 Readiness & Gaps",
        "📊 Chart Builder & Depth Analysis",
        "⚙️ Admin: Import Data",
        "⚙️ Admin: Personnel Database Settings",
    ]
    assert [page.title for page in pages.PAGES] == expected_titles
    assert pages.PAGE_BY_PATH["individual-assessment"] is pages.PAGES[2]


def test_navigation_does_not_use_raw_page_paths():
    source = (V2_DIR / "components" / "navigation.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "page_link" and node.args:
                first_arg = node.args[0]
                assert not (
                    isinstance(first_arg, ast.Constant)
                    and isinstance(first_arg.value, str)
                ), "Navigation must use registered st.Page objects, not raw paths."


def test_navigation_matches_golden_labels_and_button_layout():
    source = (V2_DIR / "components" / "navigation.py").read_text(encoding="utf-8")
    expected = [
        '("🏠 Dashboard", "🏠 Dashboard Home", "")',
        '("🌡️ Heatmap", "🌡️ Competency Heatmap", "competency-heatmap")',
        '("👤 Assessment", "👤 Individual Assessment & Talent Profile", "individual-assessment")',
        '("🎯 Readiness", "🎯 Readiness & Gaps", "readiness-gaps")',
        '("📊 Charts", "📊 Chart Builder & Depth Analysis", "chart-builder")',
        '("📥 Import", "⚙️ Admin: Import Data", "admin-import-data")',
        '("👥 Database", "⚙️ Admin: Personnel Database Settings", "admin-personnel-settings")',
        'st.columns(5)',
        'disabled=is_active',
        'st.switch_page(PAGE_BY_PATH[path])',
    ]
    for text in expected:
        assert text in source, f"Golden navigation detail missing: {text}"


def test_theme_uses_canonical_golden_css_asset():
    theme_source = (V2_DIR / "core" / "theme.py").read_text(encoding="utf-8")
    golden_css = (REPO_ROOT / "assets" / "css" / "petronas_theme.css").read_text(encoding="utf-8")
    assert "petronas_theme.css" in theme_source
    assert "_THEME_PATH" in theme_source
    assert "stButton > button:hover" in golden_css
    assert "stTabs [role=\"tab\"][aria-selected=\"true\"]" in golden_css
    assert "stDateInput" in golden_css
    assert "petronas-loader" in golden_css


def test_dashboard_contains_golden_sections_controls_and_formatting():
    source = (V2_DIR / "pages" / "01_Dashboard.py").read_text(encoding="utf-8")
    required_text = [
        "🏠 Dashboard Home",
        "🌐 RE Nationalities",
        "📊 Position Breakdown",
        "📊 Salary Grade Distribution by Employment Type",
        "🌏 Section Distribution",
        "🏢 Office Location Distribution",
        "👥 Gender Distribution",
        "📈 Grade (SG) Distribution by Gender",
        "📈 Age vs Salary Grade Analysis",
        "📊 Career Distribution (2D)",
        "🌐 Career Progression (3D)",
        "Filter by Personnel",
        "Filter by Unit Name",
        "Filter by Position",
        "Filter by Years in PETRONAS: ",
        "Filter by Years in RE Experience",
        'step=1.0',
        'f"{float(age):.0f}"',
        'f"{float(row[\'Years of RE Experience\']):.2f} Years"',
        'f"{float(row[\'Years in PET\']):.2f} Years"',
        "RE Experience Tier",
        "RE Experience Bubble Size",
        "Beautiful_Hover",
        "scatter_2d_age_sg",
        "scatter_3d_career_landscape",
    ]
    for text in required_text:
        assert text in source, f"Golden Dashboard detail missing: {text}"


def test_dashboard_backend_derives_golden_average_columns():
    _prepare_v2_path()
    bootstrap = importlib.import_module("core.bootstrap")
    df = pd.DataFrame(
        {
            "B1": [4.0],
            "B2": [2.0],
            "K1": [3.0],
            "P1": [5.0],
            "E1": [4.0],
        }
    )
    result = bootstrap.add_category_averages(df)
    assert result.loc[0, "B_avg"] == 3.0
    assert result.loc[0, "K_avg"] == 3.0
    assert result.loc[0, "P_avg"] == 5.0
    assert result.loc[0, "E_avg"] == 4.0
    assert result.loc[0, "Overall_avg"] == 3.6
