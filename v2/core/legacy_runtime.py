"""Exact-parity runtime used while the monolithic app is being migrated."""

from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache, wraps
from pathlib import Path
import inspect
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_APP = REPO_ROOT / "app.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st
from components.navigation import render_navigation


@lru_cache(maxsize=1)
def _read_legacy_source() -> str:
    return LEGACY_APP.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _page_blocks() -> dict[str, str]:
    """Extract every original page branch and make each branch executable."""
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
    """Return the original shared setup with only the old router removed."""
    source = _read_legacy_source()
    navigation_marker = source.index("# SIDEBAR NAVIGATION")
    first_page = re.search(r"(?m)^(?:if|elif) page == ([\"'])(.*?)\1:\s*$", source)
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
    """Remove only keywords that the installed callable explicitly rejects."""
    try:
        signature = inspect.signature(function)
        accepted = set(signature.parameters)
        accepts_kwargs = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        )
    except (TypeError, ValueError):
        return function

    @wraps(function)
    def wrapped(*args, **kwargs):
        if not accepts_kwargs:
            kwargs = {key: value for key, value in kwargs.items() if key in accepted}
        return function(*args, **kwargs)

    return wrapped


def _legacy_api_compat(function):
    """Retry a Streamlit call after removing an unsupported keyword.

    Older Streamlit releases frequently expose methods through a metrics
    wrapper that advertises ``**kwargs`` even though the underlying widget
    rejects newer arguments. A runtime retry catches that exact failure mode
    for *any* unsupported keyword instead of maintaining a growing list of
    version-specific arguments.

    Only errors matching Python's ``unexpected keyword argument`` message
    are retried. Other TypeErrors from the application or Streamlit propagate
    normally and therefore remain visible rather than being masked.
    """
    @wraps(function)
    def wrapped(*args, **kwargs):
        pending = dict(kwargs)
        while pending:
            try:
                return function(*args, **pending)
            except TypeError as exc:
                match = re.search(r"unexpected keyword argument ['\"]([^'\"]+)['\"]", str(exc))
                if match is None:
                    raise
                unsupported = match.group(1)
                if unsupported not in pending:
                    raise
                pending.pop(unsupported)
        return function(*args)

    return wrapped


def _dataframe_compat(function):
    """Bridge newer dataframe width values and other unsupported kwargs."""
    return _legacy_api_compat(function)


@contextmanager
def _streamlit_api_compatibility():
    """Bridge newer Streamlit API arguments across legacy widget calls."""
    originals = {}

    # These are the Streamlit calls used by the legacy app where API keyword
    # drift is most likely to surface across the project's installed version.
    # The retry mechanism is generic: if another keyword is unsupported, it is
    # removed only after Streamlit explicitly rejects that keyword.
    targets = (
        "button",
        "link_button",
        "download_button",
        "dataframe",
        "data_editor",
        "plotly_chart",
        "columns",
        "container",
        "expander",
        "tabs",
        "selectbox",
        "multiselect",
        "radio",
        "date_input",
        "number_input",
        "text_input",
        "text_area",
        "file_uploader",
        "page_link",
    )

    try:
        for name in targets:
            function = getattr(st, name, None)
            if function is not None:
                originals[name] = function
                setattr(st, name, _legacy_api_compat(function))
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

    with _streamlit_api_compatibility():
        exec(_shared_source(), namespace, namespace)
        render_navigation()
        exec(blocks[page_label], namespace, namespace)
