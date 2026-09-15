"""Exact-parity runtime used while the monolithic app is being migrated."""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache, wraps
from pathlib import Path
import inspect
import re
import sys

# Streamlit executes v2/app.py with v2 as the application directory. The
# original app.py imports root-level modules (config, models, data_loader,
# db_ops, analytics, chart_builder), so make the repository root importable
# before executing any legacy source.
REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_APP = REPO_ROOT / "app.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st

from components.navigation import render_navigation


@lru_cache(maxsize=1)
def _read_legacy_source() -> str:
    """Read the original app.py without modifying it."""
    return LEGACY_APP.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _page_blocks() -> dict[str, str]:
    """Extract each original page branch as a standalone executable block.

    The monolithic app uses one ``if`` followed by several ``elif`` branches.
    A raw ``elif`` cannot be executed independently with ``exec()``, so only
    the branch keyword at the start of each extracted block is normalised to
    ``if``. The branch body itself is left unchanged.
    """
    source = _read_legacy_source()
    pattern = re.compile(r"(?m)^(?:if|elif) page == ([\"'])(.*?)\1:\s*$")
    matches = list(pattern.finditer(source))
    blocks: dict[str, str] = {}

    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        block = source[start:end]

        if block.startswith("elif "):
            block = "if " + block[len("elif "):]

        blocks[match.group(2)] = block

    return blocks


@lru_cache(maxsize=1)
def _shared_source() -> str:
    """Return legacy setup while replacing only the old page router."""
    source = _read_legacy_source()
    navigation_marker = source.index("# SIDEBAR NAVIGATION")
    first_page = re.search(
        r"(?m)^(?:if|elif) page == ([\"'])(.*?)\1:\s*$",
        source,
    )
    if first_page is None:
        raise RuntimeError("Could not locate the first page branch in app.py")

    navigation_block = source[navigation_marker:first_page.start()]
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


def _compat_wrapper(function):
    """Wrap a Streamlit function while removing only unsupported kwargs.

    The project contains UI code written against newer Streamlit APIs. The
    local environment shown by the traceback is older and rejects e.g.
    ``st.button(..., width="stretch")``. We detect the installed function
    signature and remove only kwargs that are not accepted, leaving every
    supported argument and all business logic untouched.
    """
    try:
        accepted = set(inspect.signature(function).parameters)
    except (TypeError, ValueError):
        accepted = None

    if accepted is None:
        return function

    @wraps(function)
    def wrapped(*args, **kwargs):
        if kwargs:
            kwargs = {
                key: value
                for key, value in kwargs.items()
                if key in accepted or any(
                    parameter.kind == inspect.Parameter.VAR_KEYWORD
                    for parameter in inspect.signature(function).parameters.values()
                )
            }
        return function(*args, **kwargs)

    return wrapped


@contextmanager
def _streamlit_api_compatibility():
    """Temporarily make selected Streamlit widget APIs version-tolerant."""
    targets = [
        "button",
        "link_button",
        "download_button",
    ]
    originals = {}

    try:
        for name in targets:
            function = getattr(st, name, None)
            if function is None:
                continue
            originals[name] = function
            setattr(st, name, _compat_wrapper(function))
        yield
    finally:
        for name, function in originals.items():
            setattr(st, name, function)


def render_legacy_page(page_label: str) -> None:
    """Render an original page branch with its original dependencies intact."""
    blocks = _page_blocks()
    if page_label not in blocks:
        available = "\n".join(f"- {name}" for name in blocks)
        raise KeyError(
            f"Legacy page {page_label!r} was not found. Available pages:\n{available}"
        )

    namespace = {
        "__name__": "__legacy_app_runtime__",
        "__file__": str(LEGACY_APP),
        "page": page_label,
    }

    # The legacy shared setup contains st.set_page_config(), so it must run
    # before the v2 navigation. The compatibility layer only affects widget
    # keyword arguments rejected by the installed Streamlit version.
    with _streamlit_api_compatibility():
        exec(_shared_source(), namespace, namespace)
        render_navigation()
        exec(blocks[page_label], namespace, namespace)
