"""Static audit for legacy app parity and Streamlit API compatibility.

Run from the repository root:
    python tools/static_migration_audit.py

The audit is intentionally conservative. A function is considered statically
migrated only when a real definition exists under ``v2/``. A page wrapper that
calls ``legacy_runtime.render_legacy_page`` does not count as migration.
"""

from __future__ import annotations

import argparse
import ast
import inspect
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "app.py"
V2 = ROOT / "v2"


@dataclass(frozen=True)
class Definition:
    name: str
    kind: str
    file: str
    line: int
    qualname: str


@dataclass(frozen=True)
class StreamlitCall:
    function: str
    file: str
    line: int
    keywords: tuple[str, ...]


def _definitions(path: Path, prefix: str = "") -> list[Definition]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[Definition] = []

    def visit(body: list[ast.stmt], scope: str = "") -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = f"{scope}.{node.name}" if scope else node.name
                found.append(
                    Definition(node.name, "function", str(path.relative_to(ROOT)), node.lineno, qualname)
                )
                # Include nested functions because they are still executable
                # behavior that can be accidentally lost during extraction.
                visit(node.body, qualname)
            elif isinstance(node, ast.ClassDef):
                qualname = f"{scope}.{node.name}" if scope else node.name
                found.append(
                    Definition(node.name, "class", str(path.relative_to(ROOT)), node.lineno, qualname)
                )
                visit(node.body, qualname)

    visit(tree.body, prefix)
    return found


def collect_v2_definitions() -> list[Definition]:
    return [d for path in V2.rglob("*.py") for d in _definitions(path)]


def collect_legacy_definitions() -> list[Definition]:
    return _definitions(LEGACY)


def _streamlit_calls(path: Path) -> list[StreamlitCall]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls: list[StreamlitCall] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = None
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
            if node.func.value.id == "st":
                function = f"st.{node.func.attr}"
        if function is None:
            continue
        keywords = tuple(k.arg for k in node.keywords if k.arg is not None)
        calls.append(StreamlitCall(function, str(path.relative_to(ROOT)), node.lineno, keywords))
    return calls


def collect_streamlit_calls() -> list[StreamlitCall]:
    return _streamlit_calls(LEGACY)


def _unwrap_callable(obj):
    seen = set()
    while hasattr(obj, "__wrapped__") and id(obj) not in seen:
        seen.add(id(obj))
        obj = obj.__wrapped__
    return obj


def audit_streamlit_api() -> list[tuple[StreamlitCall, str]]:
    """Return calls whose explicit kwargs are rejected by installed Streamlit.

    This is a best-effort static/runtime hybrid audit. If a callable cannot be
    inspected, the call is reported as UNKNOWN rather than silently accepted.
    """
    try:
        import streamlit as st
    except Exception as exc:
        return [(c, f"UNKNOWN: Streamlit import failed: {exc}") for c in collect_streamlit_calls()]

    results = []
    for call in collect_streamlit_calls():
        attr = call.function.split(".", 1)[1]
        target = getattr(st, attr, None)
        if target is None:
            results.append((call, "UNAVAILABLE: installed Streamlit has no such API"))
            continue
        target = _unwrap_callable(target)
        try:
            signature = inspect.signature(target)
        except (TypeError, ValueError) as exc:
            results.append((call, f"UNKNOWN: cannot inspect signature ({exc})"))
            continue
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in signature.parameters.values()):
            results.append((call, "REVIEW: callable exposes **kwargs; runtime compatibility audit required"))
            continue
        accepted = set(signature.parameters)
        unsupported = sorted(set(call.keywords) - accepted)
        results.append((call, "UNSUPPORTED: " + ", ".join(unsupported) if unsupported else "OK"))
    return results


def _is_legacy_wrapper(path: Path) -> bool:
    source = path.read_text(encoding="utf-8")
    return "render_legacy_page(" in source


def migration_report() -> tuple[list[Definition], list[Definition], dict[str, list[Definition]]]:
    legacy = collect_legacy_definitions()
    v2 = collect_v2_definitions()
    by_name: dict[str, list[Definition]] = {}
    for definition in v2:
        by_name.setdefault(definition.name, []).append(definition)
    return legacy, v2, by_name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="exit non-zero when unmigrated functions or unsupported kwargs are found")
    args = parser.parse_args()

    legacy, v2, by_name = migration_report()
    print("=" * 88)
    print("LEGACY -> V2 STATIC MIGRATION AUDIT")
    print("=" * 88)
    print(f"Legacy definitions : {len(legacy)}")
    print(f"V2 definitions     : {len(v2)}")
    print()

    migrated = []
    ambiguous = []
    missing = []
    for definition in legacy:
        matches = by_name.get(definition.name, [])
        if not matches:
            missing.append(definition)
        elif any(not _is_legacy_wrapper(ROOT / match.file) for match in matches):
            migrated.append((definition, matches))
        else:
            ambiguous.append((definition, matches))

    print(f"STATICALLY MIGRATED : {len(migrated)}")
    print(f"WRAPPER/AMBIGUOUS   : {len(ambiguous)}")
    print(f"NOT FOUND IN V2     : {len(missing)}")
    print()

    if migrated:
        print("[MIGRATED]")
        for legacy_def, matches in migrated:
            locations = ", ".join(f"{m.file}:{m.line}" for m in matches)
            print(f"  {legacy_def.qualname:<55} -> {locations}")
        print()

    if ambiguous:
        print("[WRAPPER / NOT PROVEN AS STATIC MIGRATION]")
        for legacy_def, matches in ambiguous:
            locations = ", ".join(f"{m.file}:{m.line}" for m in matches)
            print(f"  {legacy_def.qualname:<55} -> {locations}")
        print()

    if missing:
        print("[NOT MIGRATED]")
        for definition in missing:
            print(f"  {definition.qualname:<55} <- {definition.file}:{definition.line}")
        print()

    print("=" * 88)
    print("STREAMLIT API AUDIT")
    print("=" * 88)
    api_results = audit_streamlit_api()
    unsupported = 0
    review = 0
    for call, status in api_results:
        if status.startswith("UNSUPPORTED"):
            unsupported += 1
        if status.startswith("REVIEW") or status.startswith("UNKNOWN") or status.startswith("UNAVAILABLE"):
            review += 1
        if status != "OK":
            print(f"  {status:<75} {call.file}:{call.line} {call.function}({', '.join(call.keywords)})")
    print(f"Streamlit calls audited: {len(api_results)}")
    print(f"Unsupported calls      : {unsupported}")
    print(f"Calls requiring review : {review}")

    if args.strict and (missing or ambiguous or unsupported):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
