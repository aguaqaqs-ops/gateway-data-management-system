"""Ruff C901 complexity exemption scanner used by ``tests/test_architecture.py``."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCAN_SUBDIRS = ("src", "tests", "benchmarks")

_FILE_NOQA_RE = re.compile(
    r"^#\s*(?:ruff|flake8)\s*:\s*noqa(?:\s*:\s*([^\r\n#]+))?",
    re.IGNORECASE,
)
_LINE_NOQA_RE = re.compile(
    r"^#\s*noqa\b(?:\s*:\s*([^\r\n#]+))?",
    re.IGNORECASE,
)
_CODE_TOKEN_RE = re.compile(r"[A-Za-z]+\d*")


class _FunctionLineVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self._scope: list[str] = []
        self.def_lines: dict[int, list[str]] = defaultdict(list)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        qualname = ".".join([*self._scope, node.name])
        self.def_lines[node.lineno].append(qualname)
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        qualname = ".".join([*self._scope, node.name])
        self.def_lines[node.lineno].append(qualname)
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()


def backend_python_files(root: Path = BACKEND_ROOT) -> list[Path]:
    files: list[Path] = []
    for subdir in SCAN_SUBDIRS:
        base = root / subdir
        if not base.exists():
            continue
        files.extend(
            path
            for path in sorted(base.rglob("*.py"))
            if "__pycache__" not in path.parts and ".venv" not in path.parts
        )
    return files


def scan_complexity_noqa_entries(
    paths: Iterable[Path],
    *,
    root: Path = BACKEND_ROOT,
) -> list[tuple[str, str]]:
    """Return every ``C901`` or blanket ``noqa`` marker as ``(relative_path, identity)``."""

    found: list[tuple[str, str]] = []
    for path in paths:
        rel_path = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        visitor = _FunctionLineVisitor()
        visitor.visit(ast.parse(text))
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for token_type, token_text, (start_row, _), _, _ in tokens:
            if token_type != tokenize.COMMENT:
                continue
            file_match = _FILE_NOQA_RE.match(token_text)
            if file_match is not None:
                codes_raw = file_match.group(1)
                if codes_raw is None:
                    found.append((rel_path, f"<file:{start_row}>"))
                    continue
                codes = {code.upper() for code in _CODE_TOKEN_RE.findall(codes_raw)}
                if "C901" in codes:
                    found.append((rel_path, f"<file:{start_row}>"))
                continue
            line_match = _LINE_NOQA_RE.match(token_text)
            if line_match is None:
                continue
            codes_raw = line_match.group(1)
            if codes_raw is None:
                found.append((rel_path, f"<bare-noqa:{start_row}>"))
                continue
            codes = {code.upper() for code in _CODE_TOKEN_RE.findall(codes_raw)}
            if "C901" not in codes:
                continue
            qualnames = visitor.def_lines.get(start_row, [])
            if len(qualnames) == 1:
                found.append((rel_path, qualnames[0]))
            else:
                found.append((rel_path, f"<non-def-line:{start_row}>"))
    return found


def find_complexity_baseline_drift(
    baseline: frozenset[tuple[str, str]],
    *,
    root: Path = BACKEND_ROOT,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str]]]:
    entries = scan_complexity_noqa_entries(backend_python_files(root), root=root)
    counts = Counter(entries)
    duplicates = sorted(entry for entry, count in counts.items() if count > 1)
    found_set = set(entries)
    unexpected = sorted(found_set - baseline)
    stale = sorted(baseline - found_set)
    return unexpected, stale, duplicates
