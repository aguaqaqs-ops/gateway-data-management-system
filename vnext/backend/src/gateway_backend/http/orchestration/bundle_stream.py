"""Bundle streaming orchestration."""

from __future__ import annotations

from collections.abc import Iterator

from gateway_backend.application.workspace.preview import read_preview_result
from gateway_backend.domain.workspace.models import IdentityContext
from gateway_backend.domain.workspace.ports import BaselineHeadReadPort, WorkspaceRepository
from gateway_backend.http.dependencies import BundleReaderPort
from gateway_backend.http.errors import ApiError


def stream_preview_bundle(
    *,
    context: IdentityContext,
    workspace_id: str,
    preview_result_id: str,
    workspace_repository: WorkspaceRepository,
    baseline_head_read: BaselineHeadReadPort,
    bundle_reader: BundleReaderPort,
) -> tuple[str, Iterator[bytes]]:
    state = read_preview_result(
        context=context,
        preview_result_id=preview_result_id,
        workspace_id=workspace_id,
        repository=workspace_repository,
        baseline_head_read=baseline_head_read,
    )
    try:
        return bundle_reader.read_bundle(state.result.bundle_artifact_id)
    except KeyError:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="bundle is not available",
            status_code=404,
        ) from None
