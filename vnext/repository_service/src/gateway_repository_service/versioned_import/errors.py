"""Errors raised by the production Candidate A import provider adapter."""

from __future__ import annotations

import re

_PRIVATE_REF_RE = re.compile(r"gateway-import-[0-9a-f]{32}", re.IGNORECASE)
_PATH_RE = re.compile(r"/[A-Za-z0-9_.:/-]+")
_MAX_DETAIL_LENGTH = 512


class ImportProviderError(RuntimeError):
    """Candidate A import provider execution or correctness failure."""


def sanitize_import_error_detail(detail: str | None) -> str | None:
    if detail is None:
        return None
    sanitized = _PRIVATE_REF_RE.sub("<private-ref>", detail)
    sanitized = _PATH_RE.sub("<path>", sanitized)
    if len(sanitized) > _MAX_DETAIL_LENGTH:
        return sanitized[:_MAX_DETAIL_LENGTH]
    return sanitized
