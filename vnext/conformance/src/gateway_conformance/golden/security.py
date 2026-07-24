"""Golden payload security scanning."""

from __future__ import annotations

import re
from typing import Any

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.host_paths import contains_host_path

_PID = re.compile(r"\bpid\s*[:=]\s*\d+\b", re.IGNORECASE)
_STACK = re.compile(r"\b(traceback|stack trace|file \")\b", re.IGNORECASE)
_PROVIDER = re.compile(r"\bprovider[_-]?id\b", re.IGNORECASE)


def _scan_string(value: str) -> None:
    if "/etc/passwd" in value:
        raise ConformanceValidationError("golden payload must not contain host path references")
    if contains_host_path(value):
        raise ConformanceValidationError("golden payload must not contain absolute paths")
    if _PID.search(value):
        raise ConformanceValidationError("golden payload must not contain PID metadata")
    if _STACK.search(value):
        raise ConformanceValidationError("golden payload must not contain stack or trace text")
    if _PROVIDER.search(value):
        raise ConformanceValidationError("golden payload must not contain provider metadata")


def assert_golden_payload_safe(value: Any) -> None:
    if isinstance(value, str):
        _scan_string(value)
        return
    if isinstance(value, dict):
        for item in value.values():
            assert_golden_payload_safe(item)
        return
    if isinstance(value, list):
        for item in value:
            assert_golden_payload_safe(item)
