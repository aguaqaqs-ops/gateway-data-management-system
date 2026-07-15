from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Literal
from urllib.parse import quote
import uuid

import httpx
from fastapi import Depends, FastAPI, File, Form, Header, Request, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..artifacts import ArtifactRef, LocalArtifactStore
from ..capabilities.bundle_assembly import BundleInput
from ..capabilities.comparison import (
    ComparisonInput,
    ComparisonOptions,
    ComparisonRole,
    ComparisonRowDiffDetailPolicy,
    DirectedComparisonInput,
)
from ..contracts import SubmitSourcePackage
from ..core.digests import DigestRef
from ..tarball import create_stable_tarball
from ..flows import (
    ComparisonRiskFlowInput,
    HistoryCompareFlowInput,
    build_history_compare_pair_input,
    run_history_compare,
)
from .formal_security import (
    GatewayWorkspaceSessionPayload,
    SignedTokenError,
    SsoTicketPayload,
    sign_gateway_workspace_session,
    verify_gateway_workspace_session,
    verify_sso_ticket,
)
from .formal_state_store import VNextFormalStateStore
from .formal_operation_wait import wait_for_ready
from .formal_archive import (
    FormalArchiveExecuteRequest,
    FormalArchiveService,
)
from .formal_review import (
    FormalReviewContractError,
    FormalReviewRequest,
    FormalReviewService,
)
from .formal_submit import (
    FormalSubmitContractError,
    FormalSubmitRequest,
    FormalSubmitService,
)
from .formal_upload import (
    FormalUploadContractError,
    FormalUploadFile,
    FormalUploadRequest,
    FormalUploadService,
    benchmark_elapsed_ms,
    formal_upload_benchmark_run_id,
    log_formal_upload_benchmark_event,
    operation_envelope,
)
from ..formal_upload_benchmark import configure_formal_upload_benchmark_logging
from ..operations import InMemoryOperationStore
from ..capabilities.snapshot_materialization import (
    materialize_sql_dump_source,
    resolve_required_sql_document,
)


@dataclass(frozen=True)
class VNextFormalAppSettings:
    state_root: Path | None = None
    frontend_origins: tuple[str, ...] = ("http://127.0.0.1:5173",)
    control_plane_base_url: str = "http://127.0.0.1:8010"
    control_plane_internal_auth_token: str = "gateway-control-plane-internal-dev-token"
    control_plane_timeout_seconds: float = 10.0
    internal_bearer_token: str = "gateway-control-plane-internal-dev-token"
    sso_ticket_secret: str = "control-plane-sso-ticket-secret"
    workspace_session_secret: str = "gateway-workspace-session-dev-secret"
    workspace_session_cookie_name: str = "gateway_workspace_session"
    workspace_session_ttl_seconds: int = 60 * 60 * 8


class StrictDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ControlPlaneUpsertGatewayDeviceRequestDTO(StrictDTO):
    display_name: str = Field(min_length=1)
    status: str = Field(min_length=1)
    business_project_id: str = Field(min_length=1)
    repo_key: str = Field(min_length=1)
    artifact_root_key: str = Field(min_length=1)
    updated_by_actor_id: str | None = Field(default=None, min_length=1)
    requested_by_actor_id: str | None = Field(default=None, min_length=1)
    reason: str = Field(min_length=1)


class ControlPlaneDisableGatewayDeviceRequestDTO(StrictDTO):
    updated_by_actor_id: str | None = Field(default=None, min_length=1)
    requested_by_actor_id: str | None = Field(default=None, min_length=1)
    reason: str = Field(min_length=1)


class ControlPlaneOpenBaselineBatchRequestDTO(StrictDTO):
    base_main_hash: str = Field(min_length=1)
    baseline_kind: str = Field(min_length=1)
    opened_by_actor_id: str | None = Field(default=None, min_length=1)
    requested_by_actor_id: str | None = Field(default=None, min_length=1)
    reason: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class SubmissionReviewActionRequestDTO(StrictDTO):
    action: str = Field(min_length=1)
    reason: str | None = Field(default=None, min_length=1)
    idempotency_key: str | None = Field(default=None, min_length=1)


class ArchiveAnomalyResolutionRequestDTO(StrictDTO):
    workspace_id: str = Field(min_length=1)
    submission_id: str = Field(min_length=1)
    resolution_type: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    affected_submission_ids: tuple[str, ...] = ()


class ArchiveCandidateRequestDTO(StrictDTO):
    workspace_id: str = Field(min_length=1)
    source_kind: str = "APPROVED_SUBMISSION"
    role: str = Field(min_length=1)
    source_submission_id: str | None = None
    override_reason: str | None = None


class ArchiveConfirmationRequestDTO(StrictDTO):
    confirmation_status: str = Field(min_length=1)
    reason: str | None = None
    archive_candidate_id: str | None = None


class ArchiveSelectionRequestDTO(StrictDTO):
    selected_modified_candidate_id: str = Field(min_length=1)
    selected_initial_candidate_ids: tuple[str, ...] = ()
    candidate_set_hash: str | None = None
    override_reason: str | None = None


class ArchiveExecuteRequestDTO(StrictDTO):
    idempotency_key: str = Field(min_length=1)
    expected_base_main_hash: str = Field(min_length=1)
    selected_modified_candidate_id: str = Field(min_length=1)
    selected_initial_candidate_ids: tuple[str, ...] = ()
    workspace_confirmation_set_hash: str = Field(min_length=1)
    candidate_set_hash: str = Field(min_length=1)
    override_reason: str | None = None


HistoryComparisonNodeKind = Literal[
    "BASELINE_MAINLINE",
    "BASELINE_INITIAL_HISTORY",
    "SUBMISSION_MODIFIED",
]


class HistoryComparisonNodeSelectionDTO(StrictDTO):
    kind: HistoryComparisonNodeKind
    id: str = Field(min_length=1)


class HistoryComparisonRequestDTO(StrictDTO):
    nodes: tuple[HistoryComparisonNodeSelectionDTO, ...] = Field(min_length=2, max_length=3)

    @model_validator(mode="after")
    def reject_duplicate_nodes(self) -> "HistoryComparisonRequestDTO":
        seen: set[tuple[str, str]] = set()
        for node in self.nodes:
            key = (node.kind, node.id)
            if key in seen:
                raise ValueError("history comparison nodes must be unique")
            seen.add(key)
        return self


class ContractError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, object] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = {} if details is None else dict(details)


def create_app(
    *,
    settings: VNextFormalAppSettings | None = None,
    state_store: VNextFormalStateStore | None = None,
    control_plane_transport: httpx.BaseTransport | None = None,
    repository_import_runner: object | None = None,
) -> FastAPI:
    current_settings = settings or VNextFormalAppSettings()
    configure_formal_upload_benchmark_logging()
    store = state_store or VNextFormalStateStore(root=current_settings.state_root)
    operation_store = InMemoryOperationStore()

    app = FastAPI(
        title="Gateway Data Management vNext Formal API",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(current_settings.frontend_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.vnext_formal_settings = current_settings
    app.state.vnext_formal_state_store = store
    app.state.vnext_formal_operation_store = operation_store
    upload_service = FormalUploadService(store=store, operation_store=operation_store)
    submit_service = FormalSubmitService(
        store=store,
        operation_store=operation_store,
        repository_import_runner=repository_import_runner,
    )
    archive_service = FormalArchiveService(store=store, operation_store=operation_store)
    review_service = FormalReviewService(store=store)
    app.state.vnext_formal_upload_service = upload_service
    app.state.vnext_formal_submit_service = submit_service
    app.state.vnext_formal_archive_service = archive_service
    app.state.vnext_formal_review_service = review_service

    def shutdown_submit_service() -> None:
        submit_service.shutdown()

    def shutdown_upload_service() -> None:
        upload_service.shutdown()

    def shutdown_archive_service() -> None:
        archive_service.shutdown()

    app.add_event_handler("shutdown", shutdown_upload_service)
    app.add_event_handler("shutdown", shutdown_submit_service)
    app.add_event_handler("shutdown", shutdown_archive_service)

    @app.exception_handler(ContractError)
    def handle_contract_error(_: Request, exc: ContractError) -> JSONResponse:
        return _error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(FormalUploadContractError)
    def handle_upload_contract_error(
        _: Request,
        exc: FormalUploadContractError,
    ) -> JSONResponse:
        return _error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(FormalSubmitContractError)
    def handle_submit_contract_error(
        _: Request,
        exc: FormalSubmitContractError,
    ) -> JSONResponse:
        return _error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(FormalReviewContractError)
    def handle_review_contract_error(
        _: Request,
        exc: FormalReviewContractError,
    ) -> JSONResponse:
        return _error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_FAILED",
            message="Request validation failed.",
            details={"error_count": len(exc.errors())},
        )

    def require_internal_auth(authorization: str | None = Header(default=None)) -> None:
        expected = f"Bearer {current_settings.internal_bearer_token}"
        if authorization != expected:
            raise ContractError(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="UNAUTHORIZED",
                message="Invalid gateway internal bearer token.",
            )

    def fetch_workspace_entry_context(*, actor_id: str, gateway_device_external_key: str) -> dict[str, Any]:
        path = (
            "/api/internal/gateway-devices/"
            f"{quote(gateway_device_external_key, safe='')}/actors/{quote(actor_id, safe='')}"
            "/workspace-entry-context"
        )
        try:
            with httpx.Client(
                base_url=current_settings.control_plane_base_url.rstrip("/"),
                timeout=current_settings.control_plane_timeout_seconds,
                transport=control_plane_transport,
            ) as client:
                response = client.get(
                    path,
                    headers={
                        "Authorization": (
                            f"Bearer {current_settings.control_plane_internal_auth_token}"
                        )
                    },
                )
        except httpx.HTTPError as exc:
            raise ContractError(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="DOLT_DEPENDENCY_UNAVAILABLE",
                message="Control-plane workspace entry context is unavailable.",
                details={"reason": str(exc)},
            ) from exc
        if response.status_code == status.HTTP_404_NOT_FOUND:
            raise ContractError(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="SESSION_CONTEXT_INVALID",
                message="Control-plane workspace entry context was not found.",
            )
        if response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
            raise ContractError(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="SESSION_CONTEXT_INVALID",
                message="Control-plane workspace entry context could not be authorized.",
            )
        if not response.is_success:
            raise ContractError(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="DOLT_DEPENDENCY_UNAVAILABLE",
                message="Control-plane workspace entry context response was not successful.",
                details={"status_code": response.status_code},
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise ContractError(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="SESSION_CONTEXT_INVALID",
                message="Control-plane workspace entry context response was invalid.",
            )
        if payload.get("actor_id") != actor_id:
            raise ContractError(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="SESSION_CONTEXT_INVALID",
                message="Control-plane actor did not match the SSO/session principal.",
            )
        if payload.get("gateway_device_external_key") != gateway_device_external_key:
            raise ContractError(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="SESSION_CONTEXT_INVALID",
                message="Control-plane gateway did not match the SSO/session principal.",
            )
        return payload

    def build_session_response(
        *,
        actor_id: str,
        gateway_device_external_key: str,
        expires_at: int,
    ) -> dict[str, Any]:
        context = fetch_workspace_entry_context(
            actor_id=actor_id,
            gateway_device_external_key=gateway_device_external_key,
        )
        return {
            "actor_id": context["actor_id"],
            "gateway_device_external_key": context["gateway_device_external_key"],
            "business_project_id": context["business_project_id"],
            "permissions": list(context.get("permissions", [])),
            "entry_mode": context.get("entry_mode", "review"),
            "display_context": context.get("display_context"),
            "session_expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
        }

    def current_session_payload(request: Request) -> dict[str, Any]:
        token = request.cookies.get(current_settings.workspace_session_cookie_name)
        if token is None:
            raise ContractError(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="UNAUTHORIZED",
                message="No active gateway workspace session.",
            )
        try:
            payload = verify_gateway_workspace_session(
                token,
                secret=current_settings.workspace_session_secret,
            )
        except SignedTokenError as exc:
            raise ContractError(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="SESSION_CONTEXT_INVALID",
                message=str(exc),
            ) from exc
        return build_session_response(
            actor_id=payload.actor_id,
            gateway_device_external_key=payload.gateway_device_external_key,
            expires_at=payload.expires_at,
        )

    def require_gateway(gateway_device_external_key: str) -> dict[str, object]:
        gateway = store.get_gateway_device(gateway_device_external_key)
        if gateway is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="GATEWAY_DEVICE_NOT_FOUND",
                message="Gateway device not found.",
                details={"gateway_device_external_key": gateway_device_external_key},
            )
        return gateway

    def require_active_gateway(gateway_device_external_key: str) -> dict[str, object]:
        gateway = require_gateway(gateway_device_external_key)
        if gateway.get("status") == "DISABLED":
            raise ContractError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="GATEWAY_DEVICE_DISABLED",
                message="Gateway device is disabled.",
                details={"gateway_device_external_key": gateway_device_external_key},
            )
        return gateway

    def require_upload_permission(session_payload: dict[str, Any]) -> None:
        if "upload_submit_workspace" not in set(session_payload.get("permissions", [])):
            raise ContractError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message="upload_submit_workspace permission is required.",
            )

    def require_review_permission(session_payload: dict[str, Any]) -> None:
        if "review_submission" not in set(session_payload.get("permissions", [])):
            raise ContractError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message="review_submission permission is required.",
            )

    def require_archive_permission(session_payload: dict[str, Any]) -> None:
        if "archive_mainline" not in set(session_payload.get("permissions", [])):
            raise ContractError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message="archive_mainline permission is required.",
            )

    def require_workspace_access(
        workspace: dict[str, object],
        session_payload: dict[str, Any],
    ) -> None:
        if workspace.get("owner_actor_id") != session_payload["actor_id"]:
            raise ContractError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message="Workspace owner does not match session.",
            )
        if workspace.get("gateway_device_external_key") != session_payload["gateway_device_external_key"]:
            raise ContractError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message="Workspace gateway does not match session.",
            )
        if workspace.get("business_project_id") != session_payload["business_project_id"]:
            raise ContractError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message="Workspace project does not match session.",
            )
        if workspace.get("baseline_batch_id") is None:
            raise ContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="WORKSPACE_STATE_CONFLICT",
                message="Workspace is not attached to an open batch.",
            )

    def require_workspace_scope(
        workspace: dict[str, object],
        session_payload: dict[str, Any],
    ) -> None:
        if workspace.get("gateway_device_external_key") != session_payload["gateway_device_external_key"]:
            raise ContractError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message="Workspace gateway does not match session.",
            )
        if workspace.get("business_project_id") != session_payload["business_project_id"]:
            raise ContractError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message="Workspace project does not match session.",
            )
        if workspace.get("baseline_batch_id") is None:
            raise ContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="WORKSPACE_STATE_CONFLICT",
                message="Workspace is not attached to an open batch.",
            )

    def require_batch_scope(batch: dict[str, object], session_payload: dict[str, Any]) -> None:
        if batch.get("gateway_device_external_key") != session_payload["gateway_device_external_key"]:
            raise ContractError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message="Batch gateway does not match session.",
            )
        gateway = store.get_gateway_device(str(batch["gateway_device_external_key"]))
        if gateway is None:
            raise ContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="ARCHIVE_STATE_CONFLICT",
                message="Gateway device record was not found.",
            )
        if gateway.get("business_project_id") != session_payload["business_project_id"]:
            raise ContractError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message="Batch project does not match session.",
            )

    def require_archive_session(request: Request, batch_id: str) -> tuple[dict[str, Any], dict[str, object]]:
        session_payload = current_session_payload(request)
        require_archive_permission(session_payload)
        batch = store.get_baseline_batch_by_id(batch_id)
        if batch is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="ARCHIVE_RESOURCE_NOT_FOUND",
                message="Baseline batch not found.",
                details={"batch_id": batch_id},
            )
        require_batch_scope(batch, session_payload)
        return session_payload, batch

    def require_history_read_session(request: Request) -> dict[str, Any]:
        session_payload = current_session_payload(request)
        if "view_gateway_workspace" not in set(session_payload.get("permissions", [])):
            raise ContractError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message="view_gateway_workspace permission is required.",
            )
        return session_payload

    def history_pair_plan(input_count: int) -> list[dict[str, object]]:
        if input_count == 2:
            return [
                {
                    "pair_id": "left_to_right",
                    "left_input_index": 0,
                    "right_input_index": 1,
                }
            ]
        if input_count == 3:
            return [
                {
                    "pair_id": "left_to_middle",
                    "left_input_index": 0,
                    "right_input_index": 1,
                },
                {
                    "pair_id": "middle_to_right",
                    "left_input_index": 1,
                    "right_input_index": 2,
                },
            ]
        raise ContractError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_FAILED",
            message="History comparison requires two or three nodes.",
        )

    def public_history_input(resolved: dict[str, object]) -> dict[str, object]:
        return {
            key: value
            for key, value in resolved.items()
            if key != "source_package"
        }

    def unresolved_history_response(
        *,
        session_payload: dict[str, Any],
        input_nodes: list[dict[str, object]],
        pair_plan: list[dict[str, object]],
    ) -> dict[str, object]:
        diagnostics = [
            diagnostic
            for node in input_nodes
            for diagnostic in node.get("diagnostics", [])
            if isinstance(diagnostic, dict)
        ]
        operation_id = f"history-comparison:{uuid.uuid4().hex}"
        return store.save_history_comparison(
            operation_id=operation_id,
            actor_id=str(session_payload["actor_id"]),
            gateway_device_external_key=str(session_payload["gateway_device_external_key"]),
            business_project_id=str(session_payload["business_project_id"]),
            status="FAILED_FINAL",
            input_nodes=input_nodes,
            pair_plan=pair_plan,
            bundle=None,
            diagnostics=diagnostics,
        )

    def materialize_history_input(resolved: dict[str, object]):
        source_package_payload = resolved.get("source_package")
        if not isinstance(source_package_payload, dict):
            raise ContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="HISTORY_COMPARISON_INPUT_UNAVAILABLE",
                message="History comparison input is not backed by a source package.",
                details={"node_id": str(resolved.get("id"))},
            )
        source_package = SubmitSourcePackage.from_payload(source_package_payload)
        return _materialize_history_staged_package(source_package.artifact_ref)

    def history_input_roles(input_count: int) -> tuple[str, ...]:
        return ("left", "right") if input_count == 2 else ("left", "middle", "right")

    def history_bundle_inputs(
        *,
        input_nodes: list[dict[str, object]],
        materialized_inputs: list[object],
    ) -> tuple[BundleInput, ...]:
        roles = history_input_roles(len(input_nodes))
        bundle_inputs: list[BundleInput] = []
        for index, (node, materialized) in enumerate(zip(input_nodes, materialized_inputs)):
            bundle_inputs.append(
                BundleInput(
                    input_index=index,
                    role=ComparisonRole.BEFORE if index == 0 else ComparisonRole.CURRENT,
                    display_name=(
                        str(node["display_name"])
                        if node.get("display_name") is not None
                        else f"{node['kind']} {node['id']}"
                    ),
                    display_metadata={
                        **dict(node.get("display_metadata", {})),
                        "history_role": roles[index],
                        "history_node_kind": str(node["kind"]),
                        "history_node_id": str(node["id"]),
                    },
                    snapshot_digest=materialized.summary.snapshot_digest,
                )
            )
        return tuple(bundle_inputs)

    def history_pair_inputs(
        *,
        pair_plan: list[dict[str, object]],
        materialized_inputs: list[object],
    ):
        pair_inputs = []
        for pair in pair_plan:
            left_index = int(pair["left_input_index"])
            right_index = int(pair["right_input_index"])
            before = materialized_inputs[left_index]
            current = materialized_inputs[right_index]
            pair_id = str(pair["pair_id"])
            pair_inputs.append(
                build_history_compare_pair_input(
                    pair_id=pair_id,
                    before_input_index=left_index,
                    current_input_index=right_index,
                    comparison_flow_input=ComparisonRiskFlowInput(
                        comparison_input=DirectedComparisonInput(
                            before=ComparisonInput(
                                role=ComparisonRole.BEFORE,
                                snapshot=before.snapshot,
                                summary=before.summary,
                                table_set_ref=before.table_set,
                            ),
                            current=ComparisonInput(
                                role=ComparisonRole.CURRENT,
                                snapshot=current.snapshot,
                                summary=current.summary,
                                table_set_ref=current.table_set,
                            ),
                            table_ruleset_version=current.summary.table_ruleset_version,
                            comparison_options=ComparisonOptions(
                                row_diff_detail_policy=(
                                    ComparisonRowDiffDetailPolicy.FULL_BEFORE_AFTER_VALUES
                                ),
                            ),
                        ),
                        records_store=LocalArtifactStore(
                            store.root
                            / "history-records"
                            / _safe_history_ref_component(pair_id)
                            / uuid.uuid4().hex
                        ),
                    ),
                )
            )
        return tuple(pair_inputs)

    def formal_history_bundle_payload(
        *,
        raw_bundle: dict[str, object],
        input_nodes: list[dict[str, object]],
        pair_plan: list[dict[str, object]],
        generated_at: str,
        bundle_root: Path | None = None,
    ) -> dict[str, object]:
        roles = history_input_roles(len(input_nodes))
        raw_pairs = raw_bundle.get("pairs", [])
        if not isinstance(raw_pairs, list):
            raw_pairs = []
        bundle = {
            "schema_version": "history-comparison-bundle/v1",
            "bundle_contract_version": "history-comparison-bundle/v1",
            "comparison_surface_contract_version": "comparison-surface/v1",
            "summary": raw_bundle.get("summary", {}),
            "diagnostics": raw_bundle.get("diagnostics", []),
            "source_bundle_manifest": raw_bundle,
        }
        bundle["inputs"] = [
            {
                **public_history_input(input_node),
                "role": roles[index],
            }
            for index, input_node in enumerate(input_nodes)
        ]
        bundle["pairs"] = [
            {
                **dict(pair_payload),
                **pair_plan[index],
                **(
                    {
                        "comparison_surface_contract_version": "comparison-surface/v1",
                        "surface": _read_json_file(bundle_root / str(pair_payload["surface_ref"])),
                    }
                    if bundle_root is not None
                    and isinstance(pair_payload.get("surface_ref"), str)
                    else {}
                ),
            }
            for index, pair_payload in enumerate(raw_pairs)
            if isinstance(pair_payload, dict)
        ]
        bundle["generated_at"] = generated_at
        return bundle

    def publish_formal_history_comparison_bundle(
        *,
        operation_id: str,
        flow_result: object,
    ):
        bundle_result = flow_result.bundle_result
        source_root = Path(bundle_result.bundle_root)
        operation_root = store.root / "history-comparisons" / _safe_history_ref_component(operation_id)
        published_root = operation_root / "comparison-bundle"
        tar_path = operation_root / "history-comparison-bundle.tar"
        if published_root.exists():
            shutil.rmtree(published_root)
        if tar_path.exists():
            tar_path.unlink()
        shutil.copytree(source_root, published_root)

        for pair_result in flow_result.pair_results:
            pair_id = str(pair_result.pair_id)
            pair_root = published_root / "pairs" / _safe_history_ref_component(pair_id)
            surface_path = pair_root / "comparison-surface.json"
            if not surface_path.is_file():
                raise ContractError(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    code="HISTORY_COMPARISON_BUNDLE_UNAVAILABLE",
                    message="Formal comparison surface was not generated.",
                    details={"operation_id": operation_id, "pair_id": pair_id},
                )
            surface_payload = _read_json_file(surface_path)
            record_artifacts_by_table = {
                artifact.manifest.table_name: artifact
                for artifact in pair_result.comparison_result.records_artifacts
            }
            table_payloads = surface_payload.get("tables")
            if not isinstance(table_payloads, list):
                raise ContractError(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    code="HISTORY_COMPARISON_BUNDLE_UNAVAILABLE",
                    message="Formal comparison surface tables are invalid.",
                    details={"operation_id": operation_id, "pair_id": pair_id},
                )
            next_table_payloads: list[dict[str, object]] = []
            for raw_table_payload in table_payloads:
                if not isinstance(raw_table_payload, dict):
                    continue
                table_payload = dict(raw_table_payload)
                table_name = str(table_payload.get("table_name") or "")
                records_refs = table_payload.get("records_refs")
                if isinstance(records_refs, dict) and records_refs.get("records_ref"):
                    records_artifact = record_artifacts_by_table.get(table_name)
                    if records_artifact is None:
                        raise ContractError(
                            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            code="HISTORY_COMPARISON_BUNDLE_UNAVAILABLE",
                            message="Formal comparison records artifact is missing.",
                            details={
                                "operation_id": operation_id,
                                "pair_id": pair_id,
                                "table_name": table_name,
                            },
                        )
                    records_ref = str(records_refs["records_ref"])
                    records_manifest_ref = str(
                        records_refs.get("records_manifest_ref")
                        or _records_manifest_ref(records_ref)
                    )
                    _write_formal_records_artifact(
                        published_root=published_root,
                        records_ref=records_ref,
                        records_manifest_ref=records_manifest_ref,
                        records_artifact=records_artifact,
                    )
                    records_refs = dict(records_refs)
                    records_refs["records_ref"] = records_ref
                    records_refs["records_manifest_ref"] = records_manifest_ref
                    records_refs["records_format"] = records_artifact.manifest.record_format
                    table_payload["records_refs"] = records_refs
                next_table_payloads.append(table_payload)
                table_path = pair_root / "tables" / f"{table_name}.json"
                if table_path.is_file():
                    _write_json_file(table_path, table_payload)

            surface_payload["tables"] = next_table_payloads
            _write_formal_risk_annotations(
                published_root=published_root,
                surface_payload=surface_payload,
                annotation_artifacts=pair_result.risk_result.annotation_artifacts,
                operation_id=operation_id,
                pair_id=pair_id,
            )
            _write_json_file(surface_path, surface_payload)

        return create_stable_tarball(source_root=published_root, tar_path=tar_path)

    def _read_json_file(path: Path) -> dict[str, object]:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise TypeError(f"{path} must contain a JSON object")
        return payload

    def _write_json_file(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _records_manifest_ref(records_ref: str) -> str:
        if records_ref.endswith(".parquet"):
            return records_ref.removesuffix(".parquet") + ".manifest.json"
        return records_ref.rstrip("/") + ".manifest.json"

    def _write_formal_records_artifact(
        *,
        published_root: Path,
        records_ref: str,
        records_manifest_ref: str,
        records_artifact: object,
    ) -> None:
        records_path = published_root / records_ref
        records_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(records_artifact.content_path, records_path)
        _write_json_file(published_root / records_manifest_ref, records_artifact.manifest.to_payload())

    def _write_formal_risk_annotations(
        *,
        published_root: Path,
        surface_payload: dict[str, object],
        annotation_artifacts: tuple[object, ...],
        operation_id: str,
        pair_id: str,
    ) -> None:
        artifacts_by_table = {
            artifact.table_name: artifact
            for artifact in annotation_artifacts
        }
        for table_payload in surface_payload.get("tables", []):
            if not isinstance(table_payload, dict):
                continue
            table_name = str(table_payload.get("table_name") or "")
            risk_refs = table_payload.get("risk_refs")
            if not isinstance(risk_refs, dict):
                continue
            annotation_ref = risk_refs.get("annotation_ref")
            annotation_manifest_ref = risk_refs.get("annotation_manifest_ref")
            if annotation_ref is None and annotation_manifest_ref is None:
                continue
            if not isinstance(annotation_ref, str) or not annotation_ref:
                raise ContractError(
                    status_code=status.HTTP_409_CONFLICT,
                    code="HISTORY_COMPARISON_BUNDLE_UNAVAILABLE",
                    message="History comparison risk annotation content ref is missing.",
                    details={
                        "operation_id": operation_id,
                        "pair_id": pair_id,
                        "table_name": table_name,
                    },
                )
            if not isinstance(annotation_manifest_ref, str) or not annotation_manifest_ref:
                raise ContractError(
                    status_code=status.HTTP_409_CONFLICT,
                    code="HISTORY_COMPARISON_BUNDLE_UNAVAILABLE",
                    message="History comparison risk annotation manifest ref is missing.",
                    details={
                        "operation_id": operation_id,
                        "pair_id": pair_id,
                        "table_name": table_name,
                    },
                )
            artifact = artifacts_by_table.get(table_name)
            if artifact is None:
                raise ContractError(
                    status_code=status.HTTP_409_CONFLICT,
                    code="HISTORY_COMPARISON_BUNDLE_UNAVAILABLE",
                    message="History comparison risk annotation artifact is missing.",
                    details={
                        "operation_id": operation_id,
                        "pair_id": pair_id,
                        "table_name": table_name,
                    },
                )
            content_payload = artifact.content_payload()
            if content_payload.get("table_name") != table_name:
                raise ContractError(
                    status_code=status.HTTP_409_CONFLICT,
                    code="HISTORY_COMPARISON_BUNDLE_UNAVAILABLE",
                    message="History comparison risk annotation table name does not match.",
                    details={
                        "operation_id": operation_id,
                        "pair_id": pair_id,
                        "table_name": table_name,
                    },
                )
            _write_json_file(published_root / annotation_ref, content_payload)
            if isinstance(annotation_manifest_ref, str) and annotation_manifest_ref:
                _write_json_file(published_root / annotation_manifest_ref, artifact.manifest_payload())

    def history_compare_response(
        *,
        request: Request,
        session_payload: dict[str, Any],
        resolved_inputs: list[dict[str, object]],
        pair_plan: list[dict[str, object]],
    ) -> dict[str, object]:
        input_nodes = [public_history_input(item) for item in resolved_inputs]
        if any(node.get("comparable_status") != "READY" for node in input_nodes):
            return unresolved_history_response(
                session_payload=session_payload,
                input_nodes=input_nodes,
                pair_plan=pair_plan,
            )

        operation_id = f"history-comparison:{uuid.uuid4().hex}"
        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        materialized_inputs = [materialize_history_input(item) for item in resolved_inputs]
        flow_result = run_history_compare(
            HistoryCompareFlowInput(
                bundle_root=(
                    store.root
                    / "history-comparisons"
                    / _safe_history_ref_component(operation_id)
                    / "vnext-bundle"
                ),
                bundle_inputs=history_bundle_inputs(
                    input_nodes=input_nodes,
                    materialized_inputs=materialized_inputs,
                ),
                pair_inputs=history_pair_inputs(
                    pair_plan=pair_plan,
                    materialized_inputs=materialized_inputs,
                ),
                operation_id=operation_id,
            )
        )
        wait_for_ready(lambda: flow_result.operation)
        formal_tarball = publish_formal_history_comparison_bundle(
            operation_id=operation_id,
            flow_result=flow_result,
        )
        formal_bundle_root = (
            store.root
            / "history-comparisons"
            / _safe_history_ref_component(operation_id)
            / "comparison-bundle"
        )
        history_bundle = formal_history_bundle_payload(
            raw_bundle=flow_result.bundle_result.manifest.to_payload(),
            input_nodes=input_nodes,
            pair_plan=pair_plan,
            generated_at=generated_at,
            bundle_root=formal_bundle_root,
        )
        comparison_bundle_download = {
            "download_url": str(
                request.url_for(
                    "download_history_comparison_bundle_artifact",
                    operation_id=operation_id,
                )
            ),
            "expires_at": (
                datetime.now(timezone.utc)
                .replace(microsecond=0)
                + timedelta(hours=1)
            ).isoformat(),
            "package_format": "tar",
            "size_bytes": formal_tarball.size_bytes,
            "sha256": formal_tarball.sha256,
        }
        return store.save_history_comparison(
            operation_id=operation_id,
            actor_id=str(session_payload["actor_id"]),
            gateway_device_external_key=str(session_payload["gateway_device_external_key"]),
            business_project_id=str(session_payload["business_project_id"]),
            status="READY",
            input_nodes=input_nodes,
            pair_plan=pair_plan,
            bundle=history_bundle,
            comparison_bundle_download=comparison_bundle_download,
            comparison_bundle_tar_path=str(formal_tarball.path),
            diagnostics=[],
        )

    def history_comparison_record_or_404(
        *,
        operation_id: str,
        session_payload: dict[str, Any],
    ) -> dict[str, object]:
        try:
            result = store.get_history_comparison(
                operation_id=operation_id,
                actor_id=str(session_payload["actor_id"]),
                gateway_device_external_key=str(session_payload["gateway_device_external_key"]),
                business_project_id=str(session_payload["business_project_id"]),
            )
        except PermissionError as exc:
            raise ContractError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message=str(exc),
            ) from exc
        if result is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="HISTORY_COMPARISON_OPERATION_NOT_FOUND",
                message="History comparison not found.",
                details={"operation_id": operation_id},
            )
        return result

    def require_history_comparison_ready_bundle(record: dict[str, object]) -> None:
        if record.get("operation", {}).get("status") == "READY" and record.get("bundle") is not None:
            return
        operation = record.get("operation", {})
        status_value = operation.get("status") if isinstance(operation, dict) else None
        operation_id = operation.get("operation_id") if isinstance(operation, dict) else None
        raise ContractError(
            status_code=status.HTTP_409_CONFLICT,
            code="HISTORY_COMPARISON_BUNDLE_NOT_READY",
            message="History comparison workbench bundle is not ready.",
            details={
                "operation_id": str(operation_id) if operation_id is not None else None,
                "status": str(status_value) if status_value is not None else None,
            },
        )

    def archive_store_contract_error(exc: Exception) -> ContractError:
        if isinstance(exc, KeyError):
            resource_id = str(exc.args[0]) if exc.args else None
            return ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="ARCHIVE_RESOURCE_NOT_FOUND",
                message="Archive resource was not found.",
                details={"resource_id": resource_id},
            )
        if isinstance(exc, PermissionError):
            return ContractError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message=str(exc),
            )
        if isinstance(exc, ValueError):
            return ContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="ARCHIVE_STATE_CONFLICT",
                message=str(exc),
            )
        return ContractError(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="ARCHIVE_INTERNAL_ERROR",
            message=str(exc),
        )

    def create_or_get_workspace_for_session(session_payload: dict[str, Any]) -> dict[str, object]:
        workspace, created = store.create_or_get_workspace(
            gateway_device_external_key=str(session_payload["gateway_device_external_key"]),
            owner_actor_id=str(session_payload["actor_id"]),
            business_project_id=str(session_payload["business_project_id"]),
        )
        return {"workspace": workspace, "created": created}

    @app.get("/api/sso/consume")
    def consume_sso_ticket(sso_ticket: str, response: Response) -> dict[str, Any]:
        try:
            ticket: SsoTicketPayload = verify_sso_ticket(
                sso_ticket,
                secret=current_settings.sso_ticket_secret,
            )
        except SignedTokenError as exc:
            raise ContractError(
                status_code=status.HTTP_401_UNAUTHORIZED,
                code="SESSION_CONTEXT_INVALID",
                message=str(exc),
            ) from exc

        session_expires_at = int(time.time()) + current_settings.workspace_session_ttl_seconds
        resolved = build_session_response(
            actor_id=ticket.owner_actor_id,
            gateway_device_external_key=ticket.gateway_device_external_key,
            expires_at=session_expires_at,
        )
        session_token = sign_gateway_workspace_session(
            GatewayWorkspaceSessionPayload(
                actor_id=ticket.owner_actor_id,
                gateway_device_external_key=ticket.gateway_device_external_key,
                expires_at=session_expires_at,
            ),
            secret=current_settings.workspace_session_secret,
        )
        response.set_cookie(
            current_settings.workspace_session_cookie_name,
            session_token,
            max_age=current_settings.workspace_session_ttl_seconds,
            httponly=True,
            secure=False,
            samesite="lax",
        )
        return resolved

    @app.get("/api/session")
    def get_session(request: Request) -> dict[str, Any]:
        return current_session_payload(request)

    @app.get("/api/workspace-tree")
    def get_workspace_tree(request: Request) -> dict[str, Any]:
        session_payload = current_session_payload(request)
        try:
            tree = store.get_workspace_tree(
                actor_id=str(session_payload["actor_id"]),
                gateway_device_external_key=str(session_payload["gateway_device_external_key"]),
                business_project_id=str(session_payload["business_project_id"]),
                permissions=tuple(str(item) for item in session_payload.get("permissions", [])),
            )
        except KeyError as exc:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="GATEWAY_DEVICE_NOT_FOUND",
                message="Gateway device not found.",
                details={"gateway_device_external_key": str(exc.args[0]) if exc.args else None},
            ) from exc
        except PermissionError as exc:
            raise ContractError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message=str(exc),
            ) from exc
        workspace_ids = _workspace_ids_from_tree(tree)
        active_operations = [
            *upload_service.active_operation_envelopes_for_workspace_ids(workspace_ids),
            *submit_service.active_operation_envelopes_for_workspace_ids(workspace_ids),
            *archive_service.active_operation_envelopes_for_workspace_ids(workspace_ids),
        ]
        return _formal_workspace_tree_payload(tree, active_operations=active_operations)

    @app.post("/api/history-comparisons", status_code=status.HTTP_202_ACCEPTED)
    def create_history_comparison(
        request: Request,
        payload: HistoryComparisonRequestDTO,
    ) -> dict[str, object]:
        session_payload = require_history_read_session(request)
        pair_plan = history_pair_plan(len(payload.nodes))
        resolved_inputs: list[dict[str, object]] = []
        for index, node in enumerate(payload.nodes):
            try:
                resolved_inputs.append(
                    store.resolve_history_comparison_node(
                        actor_id=str(session_payload["actor_id"]),
                        gateway_device_external_key=str(session_payload["gateway_device_external_key"]),
                        business_project_id=str(session_payload["business_project_id"]),
                        kind=node.kind,
                        node_id=node.id,
                        index=index,
                    )
                )
            except PermissionError as exc:
                raise ContractError(
                    status_code=status.HTTP_403_FORBIDDEN,
                    code="FORBIDDEN",
                    message=str(exc),
                ) from exc
            except KeyError as exc:
                raise ContractError(
                    status_code=status.HTTP_404_NOT_FOUND,
                    code="HISTORY_COMPARISON_NODE_NOT_FOUND",
                    message="History comparison node was not found.",
                    details={
                        "kind": node.kind,
                        "id": node.id,
                    },
                ) from exc
        return history_compare_response(
            request=request,
            session_payload=session_payload,
            resolved_inputs=resolved_inputs,
            pair_plan=pair_plan,
        )

    @app.get("/api/history-comparisons/{operation_id}")
    def get_history_comparison(operation_id: str, request: Request) -> dict[str, object]:
        session_payload = require_history_read_session(request)
        return history_comparison_record_or_404(
            operation_id=operation_id,
            session_payload=session_payload,
        )

    @app.get("/api/history-comparisons/{operation_id}/bundle/download")
    def get_history_comparison_bundle_download(
        operation_id: str,
        request: Request,
    ) -> dict[str, object]:
        session_payload = require_history_read_session(request)
        record = history_comparison_record_or_404(
            operation_id=operation_id,
            session_payload=session_payload,
        )
        require_history_comparison_ready_bundle(record)
        download = record.get("comparison_bundle_download")
        if not isinstance(download, dict):
            raise ContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="HISTORY_COMPARISON_BUNDLE_NOT_READY",
                message="History comparison bundle download is not ready.",
                details={"operation_id": operation_id},
            )
        return dict(download)

    @app.get(
        "/api/history-comparisons/{operation_id}/bundle/artifact",
        name="download_history_comparison_bundle_artifact",
    )
    def download_history_comparison_bundle_artifact(
        operation_id: str,
        request: Request,
    ) -> FileResponse:
        session_payload = require_history_read_session(request)
        record = history_comparison_record_or_404(
            operation_id=operation_id,
            session_payload=session_payload,
        )
        require_history_comparison_ready_bundle(record)
        try:
            tar_path_payload = store.get_history_comparison_bundle_artifact_path(
                operation_id=operation_id,
                actor_id=str(session_payload["actor_id"]),
                gateway_device_external_key=str(session_payload["gateway_device_external_key"]),
                business_project_id=str(session_payload["business_project_id"]),
            )
        except PermissionError as exc:
            raise ContractError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message=str(exc),
            ) from exc
        if tar_path_payload is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="HISTORY_COMPARISON_BUNDLE_NOT_FOUND",
                message="History comparison bundle artifact was not found.",
                details={"operation_id": operation_id},
            )
        tar_path = Path(tar_path_payload)
        if not tar_path.is_file():
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="HISTORY_COMPARISON_BUNDLE_NOT_FOUND",
                message="History comparison bundle artifact file was not found.",
                details={"operation_id": operation_id},
            )
        return FileResponse(
            tar_path,
            media_type="application/x-tar",
            filename=f"{operation_id}-comparison-bundle.tar",
        )

    @app.post("/api/workspaces/current")
    def create_current_workspace(request: Request) -> dict[str, object]:
        session_payload = current_session_payload(request)
        require_upload_permission(session_payload)
        return create_or_get_workspace_for_session(session_payload)

    @app.get("/api/workspaces/{workspace_id}")
    def get_workspace(workspace_id: str, request: Request) -> dict[str, object]:
        session_payload = current_session_payload(request)
        workspace = store.get_workspace(workspace_id)
        if workspace is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="WORKSPACE_NOT_FOUND",
                message="Workspace not found.",
                details={"workspace_id": workspace_id},
            )
        require_workspace_access(workspace, session_payload)
        return {"workspace": workspace}

    @app.post("/api/workspaces/{workspace_id}/uploads")
    async def upload_workspace_package(
        workspace_id: str,
        request: Request,
        upload_mode: str = Form(...),
        package_format: str = Form("directory-tar-gzip"),
        initial_file: UploadFile | None = File(default=None),
        modified_file: UploadFile | None = File(default=None),
        initial_filename: str | None = Form(default=None),
        modified_filename: str | None = Form(default=None),
        client_selected_root_name: str | None = Form(default=None),
        client_validation_summary: str | None = Form(default=None),
    ) -> dict[str, object]:
        session_payload = current_session_payload(request)
        require_upload_permission(session_payload)
        workspace = store.get_workspace(workspace_id)
        if workspace is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="WORKSPACE_NOT_FOUND",
                message="Workspace not found.",
                details={"workspace_id": workspace_id},
            )
        require_workspace_access(workspace, session_payload)
        benchmark_run_id = formal_upload_benchmark_run_id()
        envelope = upload_service.submit_upload(
            FormalUploadRequest(
                workspace_id=workspace_id,
                upload_mode=upload_mode,
                actor_id=str(session_payload["actor_id"]),
                initial_file=await _read_formal_upload_file(
                    initial_file,
                    filename_override=initial_filename,
                    benchmark_run_id=benchmark_run_id,
                    workspace_id=workspace_id,
                    operation_kind="upload",
                    upload_mode=upload_mode,
                    upload_kind="initial",
                ),
                modified_file=await _read_formal_upload_file(
                    modified_file,
                    filename_override=modified_filename,
                    benchmark_run_id=benchmark_run_id,
                    workspace_id=workspace_id,
                    operation_kind="upload",
                    upload_mode=upload_mode,
                    upload_kind="modified",
                ),
                package_format=package_format,
                client_selected_root_name=client_selected_root_name,
                client_validation_summary=client_validation_summary,
                benchmark_run_id=benchmark_run_id,
            )
        )
        return _operation_envelope_with_download_url(envelope, request)

    @app.get("/api/operations/{operation_id}")
    def get_operation(operation_id: str, request: Request) -> dict[str, object]:
        current_session_payload(request)
        operation = operation_store.get(operation_id)
        if operation is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="OPERATION_NOT_FOUND",
                message="Operation not found.",
                details={"operation_id": operation_id},
            )
        return _operation_envelope_with_download_url(operation_envelope(operation), request)

    @app.post("/api/submissions")
    async def submit_workspace(
        request: Request,
        workspace_id: str = Form(...),
        preview_token: str = Form(...),
        preview_revision_id: str = Form(...),
        preview_strategy_manifest_digest: str = Form(...),
        source_file: UploadFile = File(...),
        expected_source_payload_sha256: str | None = Form(default=None),
    ) -> dict[str, object]:
        session_payload = current_session_payload(request)
        require_upload_permission(session_payload)
        workspace = store.get_workspace(workspace_id)
        if workspace is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="WORKSPACE_NOT_FOUND",
                message="Workspace not found.",
                details={"workspace_id": workspace_id},
            )
        require_workspace_access(workspace, session_payload)
        benchmark_run_id = formal_upload_benchmark_run_id()
        envelope = submit_service.submit(
            FormalSubmitRequest(
                workspace_id=workspace_id,
                actor_id=str(session_payload["actor_id"]),
                preview_token=preview_token,
                preview_revision_id=preview_revision_id,
                preview_strategy_manifest_digest=preview_strategy_manifest_digest,
                source_file=(
                    await _read_formal_upload_file(
                        source_file,
                        filename_override=None,
                        benchmark_run_id=benchmark_run_id,
                        workspace_id=workspace_id,
                        operation_kind="submit",
                        upload_mode=None,
                        upload_kind="source",
                    )
                ),
                expected_source_payload_sha256=expected_source_payload_sha256,
                benchmark_run_id=benchmark_run_id,
            )
        )
        return envelope

    @app.get("/api/submissions/{submission_id}")
    def get_submission_detail(submission_id: str, request: Request) -> dict[str, object]:
        session_payload = current_session_payload(request)
        submission = store.get_submission(submission_id)
        if submission is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="SUBMISSION_NOT_FOUND",
                message="Submission not found.",
                details={"submission_id": submission_id},
            )
        workspace = store.get_workspace(str(submission["workspace_id"]))
        if workspace is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="WORKSPACE_NOT_FOUND",
                message="Workspace not found.",
                details={"workspace_id": str(submission["workspace_id"])},
            )
        require_workspace_access(workspace, session_payload)
        return {"submission": submission}

    @app.post("/api/submissions/{submission_id}/review-actions")
    def apply_submission_review_action(
        submission_id: str,
        payload: SubmissionReviewActionRequestDTO,
        request: Request,
    ) -> dict[str, object]:
        session_payload = current_session_payload(request)
        action = _normalized_review_action(payload.action)
        submission = store.get_submission(submission_id)
        if submission is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="SUBMISSION_NOT_FOUND",
                message="Submission not found.",
                details={"submission_id": submission_id},
            )
        workspace = store.get_workspace(str(submission["workspace_id"]))
        if workspace is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="WORKSPACE_NOT_FOUND",
                message="Workspace not found.",
                details={"workspace_id": str(submission["workspace_id"])},
            )
        require_workspace_access(workspace, session_payload)
        if action in {"START_REVIEW", "APPROVE", "REJECT"}:
            require_review_permission(session_payload)
        elif action == "WITHDRAW" and submission.get("submitter_actor_id") != session_payload["actor_id"]:
            raise ContractError(
                status_code=status.HTTP_403_FORBIDDEN,
                code="FORBIDDEN",
                message="Only the submitter may withdraw the pending submission.",
            )
        return review_service.apply(
            FormalReviewRequest(
                submission_id=submission_id,
                actor_id=str(session_payload["actor_id"]),
                action=action,
                reason=payload.reason,
                idempotency_key=payload.idempotency_key,
            )
        )

    @app.get("/api/baseline-batches/{batch_id}/archive-snapshot")
    def get_archive_snapshot(batch_id: str, request: Request) -> dict[str, object]:
        require_archive_session(request, batch_id)
        try:
            return store.get_archive_snapshot(batch_id)
        except Exception as exc:
            raise archive_store_contract_error(exc) from exc

    @app.post("/api/baseline-batches/{batch_id}/anomaly-resolutions")
    def accept_archive_anomaly_resolution(
        batch_id: str,
        payload: ArchiveAnomalyResolutionRequestDTO,
        request: Request,
    ) -> dict[str, object]:
        session_payload, _batch = require_archive_session(request, batch_id)
        workspace = store.get_workspace(payload.workspace_id)
        if workspace is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="WORKSPACE_NOT_FOUND",
                message="Workspace not found.",
                details={"workspace_id": payload.workspace_id},
            )
        require_workspace_scope(workspace, session_payload)
        try:
            resolution = store.accept_anomaly_resolution(
                batch_id=batch_id,
                workspace_id=payload.workspace_id,
                submission_id=payload.submission_id,
                actor_id=str(session_payload["actor_id"]),
                resolution_type=payload.resolution_type,
                reason=payload.reason,
                affected_submission_ids=payload.affected_submission_ids,
            )
            snapshot = store.get_archive_snapshot(batch_id)
        except Exception as exc:
            raise archive_store_contract_error(exc) from exc
        return {
            "resolution": resolution,
            "archive_snapshot": snapshot,
        }

    @app.put("/api/baseline-batches/{batch_id}/archive-candidates/{candidate_id}")
    def upsert_archive_candidate(
        batch_id: str,
        candidate_id: str,
        payload: ArchiveCandidateRequestDTO,
        request: Request,
    ) -> dict[str, object]:
        session_payload, _batch = require_archive_session(request, batch_id)
        workspace = store.get_workspace(payload.workspace_id)
        if workspace is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="WORKSPACE_NOT_FOUND",
                message="Workspace not found.",
                details={"workspace_id": payload.workspace_id},
            )
        require_workspace_scope(workspace, session_payload)
        try:
            workspace_payload, candidate = store.upsert_archive_candidate(
                batch_id=batch_id,
                workspace_id=payload.workspace_id,
                candidate_id=candidate_id,
                actor_id=str(session_payload["actor_id"]),
                source_kind=payload.source_kind,
                role=payload.role,
                source_submission_id=payload.source_submission_id,
                override_reason=payload.override_reason,
            )
        except Exception as exc:
            raise archive_store_contract_error(exc) from exc
        return {
            "workspace": workspace_payload,
            "candidate": candidate,
        }

    @app.put("/api/baseline-batches/{batch_id}/workspaces/{workspace_id}/archive-confirmation")
    def confirm_workspace_archive(
        batch_id: str,
        workspace_id: str,
        payload: ArchiveConfirmationRequestDTO,
        request: Request,
    ) -> dict[str, object]:
        session_payload, _batch = require_archive_session(request, batch_id)
        workspace = store.get_workspace(workspace_id)
        if workspace is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="WORKSPACE_NOT_FOUND",
                message="Workspace not found.",
                details={"workspace_id": workspace_id},
            )
        require_workspace_scope(workspace, session_payload)
        try:
            workspace_payload, confirmation, batch = store.confirm_workspace_archive(
                batch_id=batch_id,
                workspace_id=workspace_id,
                actor_id=str(session_payload["actor_id"]),
                confirmation_status=payload.confirmation_status,
                archive_candidate_id=payload.archive_candidate_id,
                reason=payload.reason,
            )
        except Exception as exc:
            raise archive_store_contract_error(exc) from exc
        return {
            "workspace": workspace_payload,
            "confirmation": confirmation,
            "baseline_batch": batch,
        }

    @app.put("/api/baseline-batches/{batch_id}/archive-selection")
    def select_archive_candidates(
        batch_id: str,
        payload: ArchiveSelectionRequestDTO,
        request: Request,
    ) -> dict[str, object]:
        session_payload, _batch = require_archive_session(request, batch_id)
        try:
            batch, selected_modified_candidate_id, selected_initial_candidate_ids = store.select_archive_candidates(
                batch_id=batch_id,
                actor_id=str(session_payload["actor_id"]),
                selected_modified_candidate_id=payload.selected_modified_candidate_id,
                selected_initial_candidate_ids=payload.selected_initial_candidate_ids,
                candidate_set_hash=payload.candidate_set_hash,
                override_reason=payload.override_reason,
            )
        except Exception as exc:
            raise archive_store_contract_error(exc) from exc
        return {
            "baseline_batch": batch,
            "selected_modified_candidate_id": selected_modified_candidate_id,
            "selected_initial_candidate_ids": list(selected_initial_candidate_ids),
        }

    @app.post("/api/baseline-batches/{batch_id}/archive-mainline/dry-run")
    def dry_run_archive_mainline(batch_id: str, request: Request) -> dict[str, object]:
        require_archive_session(request, batch_id)
        try:
            return store.dry_run_archive_mainline(batch_id)
        except Exception as exc:
            raise archive_store_contract_error(exc) from exc

    @app.post("/api/baseline-batches/{batch_id}/archive-mainline/execute")
    def execute_archive_mainline(
        batch_id: str,
        payload: ArchiveExecuteRequestDTO,
        request: Request,
    ) -> dict[str, object]:
        session_payload, _batch = require_archive_session(request, batch_id)
        try:
            return archive_service.execute(
                FormalArchiveExecuteRequest(
                    batch_id=batch_id,
                    actor_id=str(session_payload["actor_id"]),
                    idempotency_key=payload.idempotency_key,
                    expected_base_main_hash=payload.expected_base_main_hash,
                    selected_modified_candidate_id=payload.selected_modified_candidate_id,
                    selected_initial_candidate_ids=payload.selected_initial_candidate_ids,
                    workspace_confirmation_set_hash=payload.workspace_confirmation_set_hash,
                    candidate_set_hash=payload.candidate_set_hash,
                    override_reason=payload.override_reason,
                )
            )
        except Exception as exc:
            raise archive_store_contract_error(exc) from exc

    @app.get("/api/baseline-batches/{batch_id}/archive-mainline/execution-records")
    def list_archive_execution_records(batch_id: str, request: Request) -> dict[str, object]:
        require_archive_session(request, batch_id)
        try:
            return store.list_archive_executions(batch_id)
        except Exception as exc:
            raise archive_store_contract_error(exc) from exc

    @app.get("/api/preview-bundles/{preview_bundle_id}/download")
    def get_preview_bundle_download(preview_bundle_id: str, request: Request) -> dict[str, object]:
        current_session_payload(request)
        return upload_service.preview_bundle_metadata(
            preview_bundle_id,
            download_url=str(
                request.url_for(
                    "download_preview_bundle_artifact",
                    preview_bundle_id=preview_bundle_id,
                )
            ),
        )

    @app.get(
        "/api/preview-bundles/{preview_bundle_id}/artifact",
        name="download_preview_bundle_artifact",
    )
    def download_preview_bundle_artifact(preview_bundle_id: str, request: Request):
        current_session_payload(request)
        return upload_service.preview_bundle_artifact(preview_bundle_id)

    @app.put(
        "/api/internal/gateway-devices/{gateway_device_external_key}",
        dependencies=[Depends(require_internal_auth)],
    )
    def upsert_gateway_device(
        gateway_device_external_key: str,
        payload: ControlPlaneUpsertGatewayDeviceRequestDTO,
    ) -> dict[str, Any]:
        return store.upsert_gateway_device(
            gateway_device_external_key=gateway_device_external_key,
            display_name=payload.display_name,
            status=payload.status,
            business_project_id=payload.business_project_id,
            repo_key=payload.repo_key,
            artifact_root_key=payload.artifact_root_key,
            updated_by_actor_id=_requested_actor(payload),
            reason=payload.reason,
        )

    @app.post(
        "/api/internal/gateway-devices/{gateway_device_external_key}/disable",
        dependencies=[Depends(require_internal_auth)],
    )
    def disable_gateway_device(
        gateway_device_external_key: str,
        payload: ControlPlaneDisableGatewayDeviceRequestDTO,
    ) -> dict[str, Any]:
        require_gateway(gateway_device_external_key)
        return store.disable_gateway_device(
            gateway_device_external_key=gateway_device_external_key,
            updated_by_actor_id=_requested_actor(payload),
            reason=payload.reason,
        )

    @app.get(
        "/api/internal/gateway-devices/{gateway_device_external_key}/baseline-batches/current",
        dependencies=[Depends(require_internal_auth)],
    )
    def get_current_baseline_batch(gateway_device_external_key: str) -> dict[str, Any]:
        require_gateway(gateway_device_external_key)
        batch = store.get_current_baseline_batch(gateway_device_external_key)
        if batch is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="OPEN_BASELINE_BATCH_NOT_FOUND",
                message="Open baseline batch not found.",
                details={"gateway_device_external_key": gateway_device_external_key},
            )
        return batch

    @app.get(
        "/api/internal/gateway-devices/{gateway_device_external_key}/baseline-batches/latest",
        dependencies=[Depends(require_internal_auth)],
    )
    def get_latest_baseline_batch(gateway_device_external_key: str) -> dict[str, Any]:
        require_gateway(gateway_device_external_key)
        batch = store.get_latest_baseline_batch(gateway_device_external_key)
        if batch is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="BASELINE_BATCH_NOT_FOUND",
                message="Latest baseline batch not found.",
                details={"gateway_device_external_key": gateway_device_external_key},
            )
        return batch

    @app.post(
        "/api/internal/gateway-devices/{gateway_device_external_key}/baseline-batches",
        dependencies=[Depends(require_internal_auth)],
    )
    def open_baseline_batch(
        gateway_device_external_key: str,
        payload: ControlPlaneOpenBaselineBatchRequestDTO,
    ) -> dict[str, Any]:
        require_active_gateway(gateway_device_external_key)
        current = store.get_current_baseline_batch(gateway_device_external_key)
        if current is not None:
            raise ContractError(
                status_code=status.HTTP_409_CONFLICT,
                code="BASELINE_BATCH_STATE_CONFLICT",
                message="Gateway device already has an open baseline batch.",
                details={
                    "gateway_device_external_key": gateway_device_external_key,
                    "current_batch_id": str(current["batch_id"]),
                },
            )
        return store.open_baseline_batch(
            gateway_device_external_key=gateway_device_external_key,
            base_main_hash=payload.base_main_hash,
            baseline_kind=payload.baseline_kind,
            opened_by_actor_id=_requested_actor(payload),
            reason=payload.reason,
            idempotency_key=payload.idempotency_key,
        )

    @app.get(
        "/api/internal/gateway-devices/{gateway_device_external_key}/open-batch-workbench-summary",
        dependencies=[Depends(require_internal_auth)],
    )
    def get_open_batch_workbench_summary(gateway_device_external_key: str) -> dict[str, Any]:
        require_gateway(gateway_device_external_key)
        batch = store.get_current_baseline_batch(gateway_device_external_key)
        if batch is None:
            raise ContractError(
                status_code=status.HTTP_404_NOT_FOUND,
                code="OPEN_BASELINE_BATCH_NOT_FOUND",
                message="Open baseline batch not found.",
                details={"gateway_device_external_key": gateway_device_external_key},
            )
        return store.get_open_batch_workbench_summary(gateway_device_external_key)

    return app


def _requested_actor(
    payload: (
        ControlPlaneUpsertGatewayDeviceRequestDTO
        | ControlPlaneDisableGatewayDeviceRequestDTO
        | ControlPlaneOpenBaselineBatchRequestDTO
    ),
) -> str:
    actor_id = payload.requested_by_actor_id or getattr(payload, "updated_by_actor_id", None)
    if actor_id is None:
        actor_id = getattr(payload, "opened_by_actor_id", None)
    if actor_id is None:
        raise ContractError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_FAILED",
            message="Control-plane audit actor is required.",
        )
    return actor_id


def _normalized_review_action(action: str) -> str:
    normalized = action.strip().upper().replace("-", "_")
    if normalized not in {"START_REVIEW", "APPROVE", "REJECT", "WITHDRAW"}:
        raise ContractError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="VALIDATION_FAILED",
            message="Unsupported submission review action.",
            details={"action": action},
        )
    return normalized


def _formal_workspace_tree_payload(
    tree: dict[str, object],
    *,
    active_operations: list[dict[str, object]] | None = None,
) -> dict[str, Any]:
    allowed_keys = (
        "gateway",
        "current_batch",
        "current_effective_baseline_id",
        "baselines",
        "actor_workspace",
        "submissions",
        "tree_nodes",
        "active_operations",
        "allowed_actions",
        "tree_commit_hash",
        "generated_at",
    )
    payload = {key: tree.get(key) for key in allowed_keys}
    payload["active_operations"] = [] if active_operations is None else active_operations
    return payload


def _workspace_ids_from_tree(tree: dict[str, object]) -> set[str]:
    workspace_ids: set[str] = set()
    actor_workspace = tree.get("actor_workspace")
    if isinstance(actor_workspace, dict) and isinstance(actor_workspace.get("id"), str):
        workspace_ids.add(str(actor_workspace["id"]))
    baselines = tree.get("baselines")
    if not isinstance(baselines, list):
        return workspace_ids
    for baseline in baselines:
        if not isinstance(baseline, dict):
            continue
        workspaces = baseline.get("workspaces")
        if not isinstance(workspaces, list):
            continue
        for item in workspaces:
            if not isinstance(item, dict):
                continue
            workspace = item.get("workspace")
            if isinstance(workspace, dict) and isinstance(workspace.get("id"), str):
                workspace_ids.add(str(workspace["id"]))
    return workspace_ids


def _safe_history_ref_component(value: str) -> str:
    normalized = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "-"
        for char in value.strip()
    ).strip("-")
    return normalized or "history-comparison"


def _materialize_history_staged_package(staged_package):
    if isinstance(staged_package, ArtifactRef):
        staged_package = resolve_required_sql_document(staged_package)
    materialized = materialize_sql_dump_source(staged_package)
    if materialized.table_set is None:
        raise ContractError(
            status_code=status.HTTP_409_CONFLICT,
            code="HISTORY_COMPARISON_INPUT_UNAVAILABLE",
            message="History comparison input did not produce tables.",
        )
    return materialized


async def _read_formal_upload_file(
    upload_file: UploadFile | None,
    *,
    filename_override: str | None,
    benchmark_run_id: str | None = None,
    workspace_id: str | None = None,
    operation_kind: str | None = None,
    upload_mode: str | None = None,
    upload_kind: str | None = None,
) -> FormalUploadFile | None:
    if upload_file is None:
        return None
    started_at = time.perf_counter()
    safe_filename = filename_override or upload_file.filename or "upload.tar.gz"
    spool_root = Path(tempfile.gettempdir()) / "backend_vnext_upload_spool" / (workspace_id or "default")
    spool_root.mkdir(parents=True, exist_ok=True)
    safe_spool_name = safe_filename.replace("/", "_").replace("\\", "_")
    spool_path = spool_root / f"{uuid.uuid4().hex}-{safe_spool_name}"
    hasher = hashlib.sha256()
    size_bytes = 0
    with spool_path.open("wb") as target:
        while True:
            chunk = await upload_file.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
            size_bytes += len(chunk)
            target.write(chunk)
    log_formal_upload_benchmark_event(
        "route.multipart_spool",
        benchmark_run_id=benchmark_run_id,
        workspace_id=workspace_id,
        operation_kind=operation_kind,
        upload_mode=upload_mode,
        upload_kind=upload_kind,
        filename=safe_filename,
        size_bytes=size_bytes,
        sha256_digest=f"sha256:{hasher.hexdigest()}",
        file_backed=True,
        duration_ms=benchmark_elapsed_ms(started_at),
    )
    return FormalUploadFile(
        filename=safe_filename,
        source_path=spool_path,
        size_bytes=size_bytes,
        sha256_digest=f"sha256:{hasher.hexdigest()}",
    )


def _operation_envelope_with_download_url(
    envelope: dict[str, object],
    request: Request,
) -> dict[str, object]:
    ready_result = envelope.get("ready_result")
    if not isinstance(ready_result, dict):
        return envelope
    preview_bundle = ready_result.get("preview_bundle")
    if not isinstance(preview_bundle, dict):
        return envelope
    preview_bundle_id = preview_bundle.get("preview_bundle_id")
    if not isinstance(preview_bundle_id, str) or not preview_bundle_id:
        return envelope
    patched_ready = dict(ready_result)
    patched_ready["preview_bundle_download_url"] = str(
        request.url_for(
            "download_preview_bundle_artifact",
            preview_bundle_id=preview_bundle_id,
        )
    )
    return {**envelope, "ready_result": patched_ready}


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": {} if details is None else details,
                "request_id": None,
            }
        },
    )
