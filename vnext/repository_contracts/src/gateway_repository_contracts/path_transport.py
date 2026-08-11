"""Path transport encoding for bounded opaque CommitId values."""

from __future__ import annotations

import base64
import binascii
import re

from pydantic import TypeAdapter, ValidationError

from gateway_repository_contracts.types import CommitIdString

_COMMIT_ID_ADAPTER: TypeAdapter[CommitIdString] = TypeAdapter(CommitIdString)
# Worst-case base64url length for a 1024-code-point UTF-8 CommitId (4 bytes each).
MAX_COMMIT_ID_PATH_SEGMENT_LENGTH = 5464
_MAX_COMMIT_ID_PATH_SEGMENT_LENGTH = MAX_COMMIT_ID_PATH_SEGMENT_LENGTH
_COMMIT_ID_PATH_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
COMMIT_ID_PATH_SEGMENT_PATTERN = _COMMIT_ID_PATH_SEGMENT_PATTERN.pattern


def encode_commit_id_path_segment(commit_id: str) -> str:
    """Encode a CommitId for use as a single HTTP path segment."""

    validated = _validate_commit_id(commit_id)
    encoded = base64.urlsafe_b64encode(validated.encode("utf-8")).decode("ascii").rstrip("=")
    if len(encoded) > _MAX_COMMIT_ID_PATH_SEGMENT_LENGTH:
        raise ValueError("encoded commit id path segment exceeds transport limit")
    return encoded


def decode_commit_id_path_segment(segment: str) -> str:
    """Decode a canonical CommitId path segment back to the logical opaque value."""

    if not segment or len(segment) > _MAX_COMMIT_ID_PATH_SEGMENT_LENGTH:
        raise ValueError("commit id path segment is invalid")
    if "=" in segment or segment.strip() != segment or not _COMMIT_ID_PATH_SEGMENT_PATTERN.fullmatch(
        segment
    ):
        raise ValueError("commit id path segment is not canonical base64url")
    padding = "=" * (-len(segment) % 4)
    try:
        decoded_bytes = base64.urlsafe_b64decode(segment + padding)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("commit id path segment is not valid base64url") from exc
    try:
        commit_id = decoded_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("commit id path segment is not valid UTF-8") from exc
    validated = _validate_commit_id(commit_id)
    if encode_commit_id_path_segment(validated) != segment:
        raise ValueError("commit id path segment is not canonical base64url")
    return validated


def _validate_commit_id(commit_id: str) -> str:
    try:
        return _COMMIT_ID_ADAPTER.validate_python(commit_id)
    except ValidationError as exc:
        raise ValueError("commit id is invalid") from exc
