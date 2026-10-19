"""Find changed Python functions that no test references.

Maps the added/modified line numbers from the diff onto function definitions
(via `ast`) in the *current* working tree, then greps the test tree for each
function name. The result tells the test-writing agent exactly what to cover,
so it spends tokens only on real gaps.
"""
from __future__ import annotations

import ast
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .diffparse import FileChange


@dataclass
class Gap:
    path: str
    function: str
    qualname: str
    lineno: int
    changed_lines: int
    referenced_by_tests: bool


def _functions(tree: ast.AST):
    """Return [(qualname, node)] for every function/method, outer before inner."""
    stack: list[tuple[str, ast.AST]] = []

    def visit(node: ast.AST, prefix: str):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                q = f"{prefix}{child.name}"
                stack.append((q, child))
                visit(child, q + ".")
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            else:
                visit(child, prefix)

    visit(tree, "")
    return stack


def _test_identifiers(root: Path, test_dirs: list[str]) -> set[str]:
    """Identifiers actually *used in code* by the tests (names, attributes, imports).

    Strings and comments do not count: a test that only mentions a function in a
    docstring does not test it.
    """
    idents: set[str] = set()
    for d in test_dirs:
        base = root / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.py")):
            text = p.read_text(encoding="utf-8", errors="replace")
            try:
                tree = ast.parse(text)
            except SyntaxError:
                idents.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", text))
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Name):
                    idents.add(node.id)
                elif isinstance(node, ast.Attribute):
                    idents.add(node.attr)
                elif isinstance(node, ast.alias):
                    idents.add(node.name.split(".")[-1])
                    if node.asname:
                        idents.add(node.asname)
    return idents


def find_gaps(files: list[FileChange], root: str | Path = ".",
              test_dirs: list[str] | None = None) -> list[Gap]:
    root = Path(root)
    test_dirs = test_dirs or ["tests"]
    used = _test_identifiers(root, test_dirs)
    gaps: list[Gap] = []
    for f in files:
        if not f.path.endswith(".py") or f.status == "deleted":
            continue
        if any(f.path.startswith(d.rstrip("/") + "/") for d in test_dirs) or Path(f.path).name.startswith("test_"):
            continue
        src_path = root / f.path
        if not src_path.exists():
            continue
        try:
            tree = ast.parse(src_path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        changed = set(f.added_line_numbers)
        best: dict[str, tuple[ast.AST, int]] = {}
        for qual, node in _functions(tree):
            end = getattr(node, "end_lineno", node.lineno)
            n = len([ln for ln in changed if node.lineno <= ln <= end])
            if n:
                best[qual] = (node, n)
        for qual, (node, n) in best.items():
            if node.name.startswith("__") and node.name != "__init__":
                continue
            referenced = node.name in used
            gaps.append(Gap(f.path, node.name, qual, node.lineno, n, referenced))
    return gaps


def untested(gaps: list[Gap]) -> list[Gap]:
    return [g for g in gaps if not g.referenced_by_tests and not g.function.startswith("_")]


def to_dicts(gaps: list[Gap]) -> list[dict]:
    return [asdict(g) for g in gaps]
