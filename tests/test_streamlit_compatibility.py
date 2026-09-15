from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]


def test_v2_bootstrap_translates_modern_width_to_legacy_container_width():
    source = (ROOT / "v2" / "core" / "bootstrap.py").read_text(encoding="utf-8")
    assert "_patch_streamlit_width_compatibility" in source
    assert "DeltaGenerator" in source
    assert 'width == "stretch"' in source
    assert "use_container_width" in source
    for widget in ["button", "download_button", "link_button", "dataframe", "plotly_chart"]:
        assert f'"{widget}"' in source


def test_v2_pages_do_not_require_modern_button_width_api():
    page_root = ROOT / "v2"
    for path in page_root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert 'st.button("Reset", type="secondary", width="stretch"' not in source
        assert 'st.button("🔄 Refresh", type="secondary", width="stretch"' not in source
        assert 'st.button("📊 Generate Chart", type="primary", width="stretch"' not in source


def test_v2_width_keywords_are_all_handled_by_central_compatibility_layer():
    """Any Streamlit widget/container using width= must be centrally supported."""
    supported = {"button", "download_button", "link_button", "dataframe", "plotly_chart"}
    offenders = []

    for path in (ROOT / "v2").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not any(keyword.arg == "width" for keyword in node.keywords):
                continue
            if not isinstance(node.func, ast.Attribute):
                continue
            method = node.func.attr
            # Plotly figure/image helpers and other non-Streamlit APIs may also
            # legitimately accept a width argument; only enforce Streamlit
            # widget methods here.
            if method in {"to_image"}:
                continue
            if method not in supported:
                offenders.append(f"{path}:{node.lineno} -> {method}")

    assert not offenders, "Unsupported Streamlit width= calls found: " + ", ".join(offenders)


def test_v2_link_button_uses_central_container_compatibility():
    path = ROOT / "v2" / "pages" / "05_Individual_Assessment_Golden.py"
    source = path.read_text(encoding="utf-8")
    assert ".link_button(" in source
    bootstrap = (ROOT / "v2" / "core" / "bootstrap.py").read_text(encoding="utf-8")
    assert "DeltaGenerator" in bootstrap
    assert '"link_button"' in bootstrap


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
        "f'v2_main_nav_{idx}'",
        "f'v2_admin_nav_{idx}'",
    ]
    source = path.read_text(encoding="utf-8")
    assert 'key=f"nav_{idx}"' not in source
    assert 'key=f"admin_{idx}"' not in source
    assert 'key="nav_0"' not in source


def test_v2_navigation_declares_no_short_nav_keys():
    source = (ROOT / "v2" / "components" / "navigation.py").read_text(encoding="utf-8")
    # Check actual key declarations rather than comments/docstrings.
    tree = ast.parse(source)
    key_literals = []
    key_templates = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg != "key":
                continue
            if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                key_literals.append(keyword.value.value)
            elif isinstance(keyword.value, ast.JoinedStr):
                key_templates.append(ast.unparse(keyword.value))

    assert "nav_0" not in key_literals
    assert "admin_0" not in key_literals
    assert all("v2_main_nav_" in value or "v2_admin_nav_" in value for value in key_templates)


def test_v2_navigation_is_guarded_and_reset_per_script_run():
    navigation = (ROOT / "v2" / "components" / "navigation.py").read_text(encoding="utf-8")
    app = (ROOT / "v2" / "app.py").read_text(encoding="utf-8")
    assert 'if st.session_state.get("_v2_navigation_rendered", False):' in navigation
    assert 'st.session_state["_v2_navigation_rendered"] = True' in navigation
    assert 'st.session_state["_v2_navigation_rendered"] = False' in app
