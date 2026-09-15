from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def test_v2_bootstrap_translates_modern_width_to_legacy_container_width():
    source = (ROOT / "v2" / "core" / "bootstrap.py").read_text(encoding="utf-8")
    assert "_patch_streamlit_width_compatibility" in source
    assert 'width == "stretch"' in source
    assert 'use_container_width' in source
    for widget in ["button", "download_button", "link_button", "dataframe", "plotly_chart"]:
        assert f'"{widget}"' in source


def test_v2_pages_do_not_require_modern_button_width_api():
    page_root = ROOT / "v2"
    for path in page_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        # The compatibility shim may still accept legacy source during
        # migration, but direct button calls should use the stable API.
        assert 'st.button("Reset", type="secondary", width="stretch"' not in source
        assert 'st.button("🔄 Refresh", type="secondary", width="stretch"' not in source
        assert 'st.button("📊 Generate Chart", type="primary", width="stretch"' not in source


def test_v2_navigation_keys_are_namespaced_away_from_streamlit_nav_namespace():
    path = ROOT / "v2" / "components" / "navigation.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    explicit_keys = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "button":
            continue
        for keyword in node.keywords:
            if keyword.arg == "key" and isinstance(keyword.value, ast.JoinedStr):
                explicit_keys.append(ast.unparse(keyword.value))

    assert explicit_keys == [
        'f"v2_main_nav_{idx}"',
        'f"v2_admin_nav_{idx}"',
    ]
    source = path.read_text(encoding="utf-8")
    assert 'key=f"nav_{idx}"' not in source
    assert 'key=f"admin_{idx}"' not in source
    assert 'key="nav_0"' not in source


def test_v2_navigation_declares_no_short_nav_keys():
    source = (ROOT / "v2" / "components" / "navigation.py").read_text(encoding="utf-8")
    assert "nav_0" not in source
    assert "nav_1" not in source
    assert "nav_2" not in source
    assert "nav_3" not in source
    assert "nav_4" not in source
