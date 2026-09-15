from pathlib import Path

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
