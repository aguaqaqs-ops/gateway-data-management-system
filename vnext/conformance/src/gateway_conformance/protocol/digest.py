"""Run evidence bundle content digest computation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from gateway_shared_kernel import DigestKind, semantic_digest
from gateway_shared_kernel.jcs import canonicalize_json_value


def compute_run_evidence_content_digest(evidence: dict[str, Any]) -> str:
    """Compute harness-owned run evidence semantic digest (excludes self-reference)."""
    projected = deepcopy(evidence)
    projected.pop("content_digest", None)
    payload_bytes = canonicalize_json_value(projected)
    return semantic_digest(DigestKind.RUN_EVIDENCE, payload_bytes).digest_ref.value
