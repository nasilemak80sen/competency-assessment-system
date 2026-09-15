"""Static migration audit for the legacy ``app.py`` function inventory.

Usage::

    python tools/migration_audit.py
    python tools/migration_audit.py --legacy app.py --v2 v2

The audit deliberately distinguishes real static definitions from wrappers
that merely execute ``core.legacy_runtime``. This prevents the migration
ledger from reporting false 75/75 completion.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FunctionRecord:
    name: str
    path: str
    lineno: int
    is_wrapper: bool


def _is_legacy_runtime_wrapper(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True for a function whose body only delegates to legacy runtime."""
    calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
    if not calls:
        return False
    return any(
        isinstance(call.func, ast.Name) and call.func.id == "render_legacy_page"
        for call in calls
    )


def collect_functions(root: Path) -> list[FunctionRecord]:
    records: list[FunctionRecord] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in {"__pycache__", ".venv", "venv", ".git"} for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                records.append(
                    FunctionRecord(
                        name=node.name,
                        path=str(path),
                        lineno=node.lineno,
                        is_wrapper=_is_legacy_runtime_wrapper(node),
                    )
                )
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy", type=Path, default=Path("app.py"))
    parser.add_argument("--v2", type=Path, default=Path("v2"))
    args = parser.parse_args()

    legacy_tree = ast.parse(args.legacy.read_text(encoding="utf-8"), filename=str(args.legacy))
    legacy = [
        n for n in legacy_tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    v2_records = collect_functions(args.v2)
    v2_names = {record.name for record in v2_records}

    static_names = {
        record.name
        for record in v2_records
        if not record.is_wrapper
    }

    migrated = [node.name for node in legacy if node.name in static_names]
    wrappers = [node.name for node in legacy if node.name in v2_names and node.name not in static_names]
    missing = [node.name for node in legacy if node.name not in static_names and node.name not in wrappers]

    print("=" * 72)
    print("COMPETENCY ASSESSMENT SYSTEM — STATIC V2 MIGRATION AUDIT")
    print("=" * 72)
    print(f"Legacy definitions      : {len(legacy)}")
    print(f"V2 definitions          : {len(v2_records)}")
    print(f"STATICALLY MIGRATED     : {len(migrated)}")
    print(f"WRAPPER / LEGACY RUNTIME: {len(wrappers)}")
    print(f"NOT FOUND IN V2         : {len(missing)}")
    print()

    if migrated:
        print("Static migrations:")
        for name in migrated:
            print(f"  [STATIC]  {name}")
    if wrappers:
        print("\nLegacy-runtime dependencies:")
        for name in wrappers:
            print(f"  [WRAPPER] {name}")
    if missing:
        print("\nRemaining legacy functions:")
        for name in missing:
            print(f"  [TODO]    {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
