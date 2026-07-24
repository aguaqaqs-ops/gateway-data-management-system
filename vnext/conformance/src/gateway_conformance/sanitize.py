"""Sanitize validation messages to avoid leaking host paths or payloads."""

from __future__ import annotations

import re
from pathlib import Path

from gateway_conformance.host_paths import redact_host_paths

_STACK_LINE = re.compile(r"^\s*File \"", re.MULTILINE)


def sanitize_message(message: str) -> str:
    """Strip absolute paths and stack-like fragments from an error message."""
    text = redact_host_paths(message)
    if _STACK_LINE.search(text):
        text = text.split("Traceback", 1)[0].rstrip()
    return text.strip()


def relative_label(root: Path, path: Path) -> str:
    """Return a scenario-relative POSIX label without resolving host absolute paths."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name
