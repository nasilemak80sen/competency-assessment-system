"""Static parity checks for the v2 legacy-runtime migration."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
LEGACY_APP = ROOT / "app.py"
RUNTIME = ROOT / "v2" / "core" / "legacy_runtime.py"

EXPECTED_PAGES = {
    "🏠 Dashboard Home",
    "👥 Personnel Directory",
    "🌡️ Competency Heatmap",
    "👤 Individual Assessment & Talent Profile",
    "🎯 Readiness & Gaps",
    "📊 Chart Builder & Depth Analysis",
    "⚙️ Admin: Import Data",
    "⚙️ Admin: Personnel Database Settings",
}


def _branch_blocks(source: str) -> dict[str, str]:
    pattern = re.compile(r"(?m)^(?:if|elif) page == ([\"'])(.*?)\1:\s*$")
    matches = list(pattern.finditer(source))
    blocks = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        block = source[match.start():end]
        if block.startswith("elif "):
            block = "if " + block[len("elif "):]
        blocks[match.group(2)] = block
    return blocks


def test_all_original_pages_are_present():
    blocks = _branch_blocks(LEGACY_APP.read_text(encoding="utf-8"))
    assert set(blocks) == EXPECTED_PAGES


def test_every_extracted_page_branch_compiles():
    source = LEGACY_APP.read_text(encoding="utf-8")
    blocks = _branch_blocks(source)
    for page_name, block in blocks.items():
        compile(block, f"<legacy:{page_name}>", "exec")


def test_runtime_contains_elif_normalisation():
    runtime = RUNTIME.read_text(encoding="utf-8")
    assert 'if block.startswith("elif ")' in runtime
    assert 'block = "if " + block[len("elif "):]' in runtime


def test_original_app_is_not_replaced_by_v2_wrapper():
    source = LEGACY_APP.read_text(encoding="utf-8")
    assert len(source) > 300_000
    assert "def export_to_pdf(" in source
    assert "def prepare_nationality_map_data(" in source
    assert "def create_nationality_bubble_map(" in source
