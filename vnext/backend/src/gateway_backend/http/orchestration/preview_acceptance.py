"""HTTP command mapping for Preview acceptance."""

from __future__ import annotations

from collections.abc import Mapping

from gateway_backend.application.workspace.contracts import (
    StartPreviewCommand,
    compute_preview_request_fingerprint,
)
from gateway_backend.domain.workspace.models import IdentityContext


def build_start_preview_command(
    *,
    context: IdentityContext,
    workspace_id: str,
    expected_workspace_version: int,
    upload_revision_id: str,
    generation: int,
    expected_baseline_node_id: str,
    expected_baseline_head_version: int,
    idempotency_key: str,
    request_fingerprint_seed: Mapping[str, object],
) -> StartPreviewCommand:
    fingerprint = compute_preview_request_fingerprint(
        workspace_id=workspace_id,
        expected_workspace_version=expected_workspace_version,
        upload_revision_id=upload_revision_id,
        generation=generation,
        expected_baseline_node_id=expected_baseline_node_id,
        expected_baseline_head_version=expected_baseline_head_version,
        request_fingerprint_seed=request_fingerprint_seed,
    )
    return StartPreviewCommand(
        context=context,
        workspace_id=workspace_id,
        expected_workspace_version=expected_workspace_version,
        upload_revision_id=upload_revision_id,
        generation=generation,
        expected_baseline_node_id=expected_baseline_node_id,
        expected_baseline_head_version=expected_baseline_head_version,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
    )
