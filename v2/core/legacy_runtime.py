"""
Exact-parity runtime for the v2 migration.

This module intentionally executes the original app.py page branches rather
than re-implementing them. The goal is to preserve the original UI/UX and
business rules while we move the monolith into real modules one workflow at
a time.

Migration rule:
    1. Do not change the extracted page source here.
    2. First establish v2 parity with app.py.
    3. Then replace one extracted branch at a time with a normal module.
    4. Write-heavy workflows are migrated only after their original branch is
       isolated and verified.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

import streamlit as st

from components.navigation import render_navigation


REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_APP = REPO_ROOT / "app.py"


@lru_cache(maxsize=1)
def _read_legacy_source() -> str:
    """Read the original monolithic app.py without modifying it."""
    return LEGACY_APP.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _page_blocks() -> dict[str, str]:
    """Extract the original page branches verbatim from app.py."""
    source = _read_legacy_source()

    pattern = re.compile(
        r"(?m)^(?:if|elif) page == ([\"'])(.*?)\1:\s*$"
    )
    matches = list(pattern.finditer(source))

    blocks: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        blocks[match.group(2)] = source[start:end]

    return blocks


@lru_cache(maxsize=1)
def _shared_source() -> str:
    """
    Return the original application setup up to the first page branch.

    The legacy interactive navigation is excluded because v2 supplies native
    Streamlit page links. The original imports, helper functions, database
    bootstrap, cached loaders, session state, and wide-data construction are
    retained verbatim.
    """
    source = _read_legacy_source()

    navigation_marker = source.index("# SIDEBAR NAVIGATION")
    first_page = re.search(
        r"(?m)^(?:if|elif) page == ([\"'])(.*?)\1:\s*$",
        source,
    )
    if first_page is None:
        raise RuntimeError("Could not locate the first page branch in app.py")

    navigation_end = first_page.start()
    navigation_block = source[navigation_marker:navigation_end]

    lines = navigation_block.splitlines(keepends=True)
    retained: list[str] = []
    skipping_radio = False
    skipping_navigation_import = False

    for line in lines:
        if line.startswith("st.sidebar.title("):
            continue
        if line.startswith("page = st.sidebar.radio("):
            skipping_radio = True
            continue
        if skipping_radio:
            if "])" in line:
                skipping_radio = False
            continue
        if line.startswith("from navigation import render_navigation"):
            skipping_navigation_import = True
            continue
        if skipping_navigation_import:
            if "page = render_navigation()" in line:
                skipping_navigation_import = False
            continue
        retained.append(line)

    return source[:navigation_marker] + "".join(retained)


def render_legacy_page(page_label: str) -> None:
    """
    Render one original app.py page branch inside the v2 Streamlit page.

    The original branch code is not rewritten. Only the selected `page` value
    and the v2 native navigation shell are supplied by this adapter.
    """
    blocks = _page_blocks()
    if page_label not in blocks:
        available = "\n".join(f"- {name}" for name in blocks)
        raise KeyError(
            f"Legacy page {page_label!r} was not found. Available pages:\n{available}"
        )

    render_navigation()

    namespace = {
        "__name__": "__legacy_app_runtime__",
        "__file__": str(LEGACY_APP),
        "page": page_label,
    }

    exec(_shared_source(), namespace, namespace)
    exec(blocks[page_label], namespace, namespace)
