"""Regression tests for the static migration audit itself."""

from pathlib import Path
import ast


ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "app.py"
AUDIT = ROOT / "tools" / "static_migration_audit.py"
RUNTIME = ROOT / "v2" / "core" / "legacy_runtime.py"


def test_audit_tool_compiles():
    compile(AUDIT.read_text(encoding="utf-8"), str(AUDIT), "exec")


def test_legacy_app_has_real_function_definitions():
    tree = ast.parse(LEGACY.read_text(encoding="utf-8"), filename=str(LEGACY))
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert len(functions) >= 50, "Unexpectedly small legacy function inventory"


def test_runtime_has_generic_unexpected_keyword_retry():
    source = RUNTIME.read_text(encoding="utf-8")
    assert "unexpected keyword argument" in source
    assert "_legacy_api_compat" in source


def test_runtime_covers_common_streamlit_widgets():
    source = RUNTIME.read_text(encoding="utf-8")
    for name in (
        "button",
        "link_button",
        "download_button",
        "dataframe",
        "plotly_chart",
        "columns",
        "selectbox",
        "multiselect",
        "radio",
        "date_input",
        "number_input",
        "text_input",
        "file_uploader",
    ):
        assert f'"{name}"' in source
