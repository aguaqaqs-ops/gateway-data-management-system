"""Versioned logical location identity; physical deployment paths never enter IDs."""
from __future__ import annotations

import hashlib
import re
from enum import StrEnum

from gateway_shared_kernel.jcs import canonicalize_json_value


class ArtifactLocation(StrEnum):
    DURABLE = "durable"
    CANONICAL = "canonical"
    COMPARISON = "comparison"
    EXPORT = "export"


_ID = re.compile(r"a1:(durable|canonical|comparison|export):[0-9a-f]{64}\Z")
_KIND = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def parse_artifact_id(artifact_id: str) -> ArtifactLocation:
    if type(artifact_id) is not str or (match := _ID.fullmatch(artifact_id)) is None:
        raise ValueError("artifact_id must use a1:<location>:<64 lowercase hex> format")
    return ArtifactLocation(match.group(1))


def build_artifact_id(location: ArtifactLocation, kind: str, identity_payload: object) -> str:
    """Hash the complete owner identity under an explicit logical location and kind."""
    if type(location) is not ArtifactLocation:
        raise ValueError("location must be ArtifactLocation")
    if type(kind) is not str or _KIND.fullmatch(kind) is None:
        raise ValueError("artifact kind must be a fixed lowercase token")
    token = hashlib.sha256(canonicalize_json_value([
        "gateway-artifact-id-v1", location.value, kind, identity_payload,
    ])).hexdigest()
    return f"a1:{location.value}:{token}"
