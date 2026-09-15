from pathlib import Path
import ast

from v2.core.migration_manifest import PHASE_A_MIGRATED_COUNT, TOTAL_LEGACY_FUNCTIONS


ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "v2"


def _imports_legacy_runtime(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "core.legacy_runtime":
            return True
        if isinstance(node, ast.Import):
            if any(alias.name == "core.legacy_runtime" for alias in node.names):
                return True
    return False


def test_v2_pages_do_not_depend_on_legacy_runtime():
    pages = sorted((V2 / "pages").glob("*.py"))
    assert pages
    assert all(not _imports_legacy_runtime(page) for page in pages)
    assert not (V2 / "core" / "legacy_runtime.py").exists()


def test_migration_manifest_is_bounded():
    assert 0 < PHASE_A_MIGRATED_COUNT <= TOTAL_LEGACY_FUNCTIONS


def test_all_registered_v2_pages_exist():
    expected = [
        "01_Dashboard.py", "02_Personnel.py", "03_Competency_Heatmap.py",
        "04_Readiness_and_Gaps.py", "05_Individual_Assessment.py",
        "06_Chart_Builder.py", "07_Admin.py", "08_Admin_Import_Data.py",
    ]
    assert all((V2 / "pages" / name).exists() for name in expected)
