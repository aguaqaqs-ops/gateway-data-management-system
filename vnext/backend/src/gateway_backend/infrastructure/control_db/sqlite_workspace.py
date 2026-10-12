"""SQLite row mapping and transaction-scoped WorkspaceRepository adapter."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import cast

from gateway_shared_kernel import DigestRef
from gateway_shared_kernel.jcs import canonicalize_jcs, canonicalize_json_value

from gateway_backend.domain.workspace.errors import OpenWorkspaceConflict, WorkspaceVersionConflict
from gateway_backend.domain.workspace.models import (
    InputCompleteness,
    PreviewArtifactRef,
    PreviewAcceptanceRecord,
    PreviewCanonicalBindings,
    PreviewResult,
    PreviewResultDigests,
    SourceArtifactBinding,
    SourceArtifactRole,
    UploadRevision,
    Workspace,
    WorkspaceScope,
    WorkspaceState,
)

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_SQLITE_INT_MIN = -(2**63)
_SQLITE_INT_MAX = 2**63 - 1

_WORKSPACE_COLUMNS = (
    "workspace_id, owner_actor_id, gateway_device_external_key, business_project_id, "
    "repository_id, state, generation, optimistic_version, current_upload_revision_id, "
    "current_preview_result_id, created_at_us, updated_at_us, closed_at_us"
)
_UPLOAD_REVISION_COLUMNS = (
    "upload_revision_id, workspace_id, generation, input_completeness, source_artifacts, "
    "idempotency_key, request_fingerprint, created_by, created_at_us"
)
_PREVIEW_IDEMPOTENCY_COLUMNS = (
    "workspace_id, idempotency_key, request_fingerprint, operation_id, "
    "upload_revision_id, generation, business_baseline_node_id, baseline_head_version"
)


class SQLiteWorkspaceRepository:
    """Concrete WorkspaceRepository participant bound to one already-open transaction."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        transaction_now: datetime,
        read_only: bool = False,
    ) -> None:
        if not connection.in_transaction:
            raise RuntimeError("SQLiteWorkspaceRepository requires an active transaction")
        if type(read_only) is not bool:
            raise ValueError("read_only must be a bool")
        _validate_utc_datetime(transaction_now, "transaction_now")
        self._connection = connection
        self._transaction_now = transaction_now
        self._read_only = read_only

    def find_open_by_scope(self, scope: WorkspaceScope) -> Workspace | None:
        row = self._connection.execute(
            f"""
            SELECT {_WORKSPACE_COLUMNS}
            FROM workspace_records
            WHERE owner_actor_id = ?
              AND gateway_device_external_key = ?
              AND business_project_id = ?
              AND state = 'OPEN'
            """,
            (
                scope.owner_actor_id,
                scope.gateway_device_external_key,
                scope.business_project_id,
            ),
        ).fetchone()
        if row is None:
            return None
        return workspace_from_row(_row_mapping(row))

    def get_workspace(self, workspace_id: str) -> Workspace | None:
        row = self._connection.execute(
            f"SELECT {_WORKSPACE_COLUMNS} FROM workspace_records WHERE workspace_id = ?",
            (workspace_id,),
        ).fetchone()
        if row is None:
            return None
        return workspace_from_row(_row_mapping(row))

    def get_upload_revision(self, upload_revision_id: str) -> UploadRevision | None:
        row = self._connection.execute(
            f"SELECT {_UPLOAD_REVISION_COLUMNS} FROM upload_revision_records WHERE upload_revision_id = ?",
            (upload_revision_id,),
        ).fetchone()
        if row is None:
            return None
        return upload_revision_from_row(_row_mapping(row))

    def get_preview_result(self, preview_result_id: str) -> PreviewResult | None:
        row = self._connection.execute(
            """
            SELECT preview_result_id, workspace_id, upload_revision_id, generation, repository_id,
                   binding, operation_id, created_at_us
            FROM preview_result_records
            WHERE preview_result_id = ?
            """,
            (preview_result_id,),
        ).fetchone()
        if row is None:
            return None
        return preview_result_from_row(_row_mapping(row))

    def find_upload_idempotency(
        self,
        workspace_id: str,
        idempotency_key: str,
    ) -> UploadRevision | None:
        row = self._connection.execute(
            """
            SELECT ur.upload_revision_id, ur.workspace_id, ur.generation, ur.input_completeness,
                   ur.source_artifacts, ur.idempotency_key, ur.request_fingerprint, ur.created_by,
                   ur.created_at_us
            FROM upload_idempotency_records AS ui
            JOIN upload_revision_records AS ur ON ur.upload_revision_id = ui.upload_revision_id
            WHERE ui.workspace_id = ? AND ui.idempotency_key = ?
            """,
            (workspace_id, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        return upload_revision_from_row(_row_mapping(row))

    def find_preview_idempotency(
        self,
        workspace_id: str,
        idempotency_key: str,
    ) -> PreviewAcceptanceRecord | None:
        row = self._connection.execute(
            f"""
            SELECT {_PREVIEW_IDEMPOTENCY_COLUMNS}
            FROM preview_idempotency_records
            WHERE workspace_id = ? AND idempotency_key = ?
            """,
            (workspace_id, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        return _preview_acceptance_from_mapping(_row_mapping(row))

    def list_preview_acceptances(self, workspace_id: str) -> tuple[PreviewAcceptanceRecord, ...]:
        rows = self._connection.execute(
            f"""
            SELECT {_PREVIEW_IDEMPOTENCY_COLUMNS}
            FROM preview_idempotency_records
            WHERE workspace_id = ?
            ORDER BY generation ASC, idempotency_key ASC
            """,
            (workspace_id,),
        ).fetchall()
        return tuple(_preview_acceptance_from_mapping(_row_mapping(row)) for row in rows)

    def save_workspace(self, workspace: Workspace, *, expected_version: int) -> Workspace:
        self._require_writable()
        existing = self.get_workspace(workspace.workspace_id)
        if existing is None:
            if expected_version != workspace.optimistic_version:
                raise WorkspaceVersionConflict(
                    expected=expected_version,
                    actual=workspace.optimistic_version,
                )
            try:
                self._connection.execute(
                    f"""
                    INSERT INTO workspace_records ({_WORKSPACE_COLUMNS})
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    workspace_to_row(workspace),
                )
            except sqlite3.IntegrityError as exc:
                replay = self.find_open_by_scope(workspace.scope)
                if replay is None:
                    raise OpenWorkspaceConflict from exc
                return replay
            return workspace
        if existing.optimistic_version != expected_version:
            raise WorkspaceVersionConflict(
                expected=expected_version,
                actual=existing.optimistic_version,
            )
        updated = self._connection.execute(
            """
            UPDATE workspace_records
            SET owner_actor_id = ?,
                gateway_device_external_key = ?,
                business_project_id = ?,
                repository_id = ?,
                state = ?,
                generation = ?,
                optimistic_version = ?,
                current_upload_revision_id = ?,
                current_preview_result_id = ?,
                created_at_us = ?,
                updated_at_us = ?,
                closed_at_us = ?
            WHERE workspace_id = ? AND optimistic_version = ?
            """,
            (
                workspace.owner_actor_id,
                workspace.gateway_device_external_key,
                workspace.business_project_id,
                workspace.repository_id,
                workspace.state.value,
                workspace.generation,
                workspace.optimistic_version,
                workspace.current_upload_revision_id,
                workspace.current_preview_result_id,
                _datetime_to_epoch_us(workspace.created_at),
                _datetime_to_epoch_us(workspace.updated_at),
                _datetime_to_epoch_us(workspace.closed_at) if workspace.closed_at else None,
                workspace.workspace_id,
                expected_version,
            ),
        )
        if updated.rowcount != 1:
            current = self.get_workspace(workspace.workspace_id)
            actual = current.optimistic_version if current is not None else expected_version
            raise WorkspaceVersionConflict(expected=expected_version, actual=actual)
        return workspace

    def save_upload_revision(self, revision: UploadRevision) -> None:
        self._require_writable()
        self._connection.execute(
            f"""
            INSERT INTO upload_revision_records ({_UPLOAD_REVISION_COLUMNS})
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            upload_revision_to_row(revision),
        )
        self._connection.execute(
            """
            INSERT INTO upload_idempotency_records (
                workspace_id, idempotency_key, request_fingerprint, upload_revision_id
            ) VALUES (?, ?, ?, ?)
            """,
            (
                revision.workspace_id,
                revision.idempotency_key,
                revision.request_fingerprint,
                revision.upload_revision_id,
            ),
        )

    def save_preview_acceptance(self, record: PreviewAcceptanceRecord) -> None:
        self._require_writable()
        self._connection.execute(
            """
            INSERT INTO preview_idempotency_records (
                workspace_id, idempotency_key, request_fingerprint, operation_id,
                upload_revision_id, generation, business_baseline_node_id, baseline_head_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.workspace_id,
                record.idempotency_key,
                record.request_fingerprint,
                record.operation_id,
                record.upload_revision_id,
                record.generation,
                record.business_baseline_node_id,
                record.baseline_head_version,
            ),
        )

    def save_preview_result(self, result: PreviewResult) -> None:
        self._require_writable()
        self._connection.execute(
            """
            INSERT INTO preview_result_records (
                preview_result_id, workspace_id, upload_revision_id, generation, repository_id,
                binding, operation_id, created_at_us
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            preview_result_to_row(result),
        )

    def _require_writable(self) -> None:
        if self._read_only:
            raise RuntimeError("workspace repository is read-only in this transaction")


def workspace_to_row(workspace: Workspace) -> tuple[object, ...]:
    return (
        workspace.workspace_id,
        workspace.owner_actor_id,
        workspace.gateway_device_external_key,
        workspace.business_project_id,
        workspace.repository_id,
        workspace.state.value,
        workspace.generation,
        workspace.optimistic_version,
        workspace.current_upload_revision_id,
        workspace.current_preview_result_id,
        _datetime_to_epoch_us(workspace.created_at),
        _datetime_to_epoch_us(workspace.updated_at),
        _datetime_to_epoch_us(workspace.closed_at) if workspace.closed_at else None,
    )


def workspace_from_row(row: Mapping[str, object]) -> Workspace:
    return Workspace(
        workspace_id=_required_text(row, "workspace_id"),
        owner_actor_id=_required_text(row, "owner_actor_id"),
        gateway_device_external_key=_required_text(row, "gateway_device_external_key"),
        business_project_id=_required_text(row, "business_project_id"),
        repository_id=_required_text(row, "repository_id"),
        state=WorkspaceState(_required_text(row, "state")),
        generation=_required_int(row, "generation"),
        optimistic_version=_required_int(row, "optimistic_version"),
        current_upload_revision_id=_optional_text(row, "current_upload_revision_id"),
        current_preview_result_id=_optional_text(row, "current_preview_result_id"),
        created_at=_epoch_us_to_datetime(_required_int(row, "created_at_us")),
        updated_at=_epoch_us_to_datetime(_required_int(row, "updated_at_us")),
        closed_at=(
            _epoch_us_to_datetime(_required_int(row, "closed_at_us"))
            if row["closed_at_us"] is not None
            else None
        ),
    )


def upload_revision_to_row(revision: UploadRevision) -> tuple[object, ...]:
    return (
        revision.upload_revision_id,
        revision.workspace_id,
        revision.generation,
        revision.input_completeness.value,
        _encode_source_artifacts(revision.source_artifacts),
        revision.idempotency_key,
        revision.request_fingerprint,
        revision.created_by,
        _datetime_to_epoch_us(revision.created_at),
    )


def upload_revision_from_row(row: Mapping[str, object]) -> UploadRevision:
    return UploadRevision(
        upload_revision_id=_required_text(row, "upload_revision_id"),
        workspace_id=_required_text(row, "workspace_id"),
        generation=_required_int(row, "generation"),
        input_completeness=InputCompleteness(_required_text(row, "input_completeness")),
        source_artifacts=_decode_source_artifacts(_blob_value(row, "source_artifacts")),
        idempotency_key=_required_text(row, "idempotency_key"),
        request_fingerprint=_required_text(row, "request_fingerprint"),
        created_by=_required_text(row, "created_by"),
        created_at=_epoch_us_to_datetime(_required_int(row, "created_at_us")),
    )


def _preview_acceptance_from_mapping(row: Mapping[str, object]) -> PreviewAcceptanceRecord:
    return PreviewAcceptanceRecord(
        workspace_id=_required_text(row, "workspace_id"),
        idempotency_key=_required_text(row, "idempotency_key"),
        request_fingerprint=_required_text(row, "request_fingerprint"),
        operation_id=_required_text(row, "operation_id"),
        upload_revision_id=_required_text(row, "upload_revision_id"),
        generation=_required_int(row, "generation"),
        business_baseline_node_id=_required_text(row, "business_baseline_node_id"),
        baseline_head_version=_required_int(row, "baseline_head_version"),
    )


def preview_result_to_row(result: PreviewResult) -> tuple[object, ...]:
    binding = {
        "business_baseline_node_id": result.business_baseline_node_id,
        "business_baseline_commit_id": result.business_baseline_commit_id,
        "baseline_head_version": result.baseline_head_version,
        "ruleset_version": result.ruleset_version,
        "contract_version": result.contract_version,
        "provider_versions": dict(result.provider_versions),
        "digests": {
            "source_digest": result.digests.source_digest,
            "input_digest": result.digests.input_digest,
            "snapshot_digest": result.digests.snapshot_digest,
            "comparison_digest": result.digests.comparison_digest,
            "risk_digest": result.digests.risk_digest,
            "surface_digest": result.digests.surface_digest,
            "bundle_digest": result.digests.bundle_digest,
        },
        "canonical": {
            "canonical_table_set_closure_ref": _preview_artifact_ref_to_document(
                result.canonical.canonical_table_set_closure_ref
            ),
            "canonical_table_set_closure_digest": result.canonical.canonical_table_set_closure_digest.value,
            "canonicalization_manifest_ref": _preview_artifact_ref_to_document(
                result.canonical.canonicalization_manifest_ref
            ),
            "canonicalization_manifest_digest": result.canonical.canonicalization_manifest_digest.value,
            "baseline_canonical_state_digest": result.canonical.baseline_canonical_state_digest.value,
            "modified_canonical_state_digest": result.canonical.modified_canonical_state_digest.value,
            "storage_projection_ruleset_digest": result.canonical.storage_projection_ruleset_digest.value,
        },
        "bundle_artifact_id": result.bundle_artifact_id,
        "ready_closure_artifact_id": result.ready_closure_artifact_id,
    }
    return (
        result.preview_result_id,
        result.workspace_id,
        result.upload_revision_id,
        result.generation,
        result.repository_id,
        canonicalize_json_value(binding),
        result.operation_id,
        _datetime_to_epoch_us(result.created_at),
    )


def preview_result_from_row(row: Mapping[str, object]) -> PreviewResult:
    binding = json.loads(_blob_value(row, "binding").decode("utf-8"))
    if type(binding) is not dict:
        raise ValueError("preview binding must be an object")
    digests_payload = binding.get("digests")
    if type(digests_payload) is not dict:
        raise ValueError("preview binding digests must be an object")
    provider_versions = binding.get("provider_versions")
    if type(provider_versions) is not dict:
        raise ValueError("preview binding provider_versions must be an object")
    canonical_payload = binding.get("canonical")
    if type(canonical_payload) is not dict:
        raise ValueError("preview binding canonical must be an object")
    return PreviewResult(
        preview_result_id=_required_text(row, "preview_result_id"),
        workspace_id=_required_text(row, "workspace_id"),
        upload_revision_id=_required_text(row, "upload_revision_id"),
        generation=_required_int(row, "generation"),
        repository_id=_required_text(row, "repository_id"),
        business_baseline_node_id=str(binding["business_baseline_node_id"]),
        business_baseline_commit_id=str(binding["business_baseline_commit_id"]),
        baseline_head_version=int(binding["baseline_head_version"]),
        ruleset_version=str(binding["ruleset_version"]),
        contract_version=str(binding["contract_version"]),
        provider_versions={str(key): str(value) for key, value in provider_versions.items()},
        digests=PreviewResultDigests(
            source_digest=str(digests_payload["source_digest"]),
            input_digest=str(digests_payload["input_digest"]),
            snapshot_digest=str(digests_payload["snapshot_digest"]),
            comparison_digest=str(digests_payload["comparison_digest"]),
            risk_digest=str(digests_payload["risk_digest"]),
            surface_digest=str(digests_payload["surface_digest"]),
            bundle_digest=str(digests_payload["bundle_digest"]),
        ),
        canonical=PreviewCanonicalBindings(
            canonical_table_set_closure_ref=_preview_artifact_ref_from_document(
                canonical_payload.get("canonical_table_set_closure_ref")
            ),
            canonical_table_set_closure_digest=DigestRef(
                str(canonical_payload["canonical_table_set_closure_digest"])
            ),
            canonicalization_manifest_ref=_preview_artifact_ref_from_document(
                canonical_payload.get("canonicalization_manifest_ref")
            ),
            canonicalization_manifest_digest=DigestRef(
                str(canonical_payload["canonicalization_manifest_digest"])
            ),
            baseline_canonical_state_digest=DigestRef(
                str(canonical_payload["baseline_canonical_state_digest"])
            ),
            modified_canonical_state_digest=DigestRef(
                str(canonical_payload["modified_canonical_state_digest"])
            ),
            storage_projection_ruleset_digest=DigestRef(
                str(canonical_payload["storage_projection_ruleset_digest"])
            ),
        ),
        bundle_artifact_id=str(binding["bundle_artifact_id"]),
        ready_closure_artifact_id=str(binding["ready_closure_artifact_id"]),
        operation_id=_required_text(row, "operation_id"),
        created_at=_epoch_us_to_datetime(_required_int(row, "created_at_us")),
    )


def _preview_artifact_ref_to_document(ref: PreviewArtifactRef) -> dict[str, object]:
    return {
        "artifact_id": ref.artifact_id,
        "media_type": ref.media_type,
        "size_bytes": ref.size_bytes,
        "raw_sha256": ref.raw_sha256.value,
    }


def _preview_artifact_ref_from_document(raw: object) -> PreviewArtifactRef:
    if type(raw) is not dict:
        raise ValueError("preview artifact ref must be an object")
    return PreviewArtifactRef(
        artifact_id=str(raw["artifact_id"]),
        media_type=str(raw["media_type"]),
        size_bytes=int(raw["size_bytes"]),
        raw_sha256=DigestRef(str(raw["raw_sha256"])),
    )


def _encode_source_artifacts(
    source_artifacts: Mapping[SourceArtifactRole, SourceArtifactBinding],
) -> bytes:
    payload = {
        role.value: {
            "artifact_id": binding.artifact_id,
            "media_type": binding.media_type,
            "size_bytes": binding.size_bytes,
            "raw_sha256": binding.raw_sha256,
        }
        for role, binding in sorted(source_artifacts.items(), key=lambda item: item[0].value)
    }
    return canonicalize_jcs(canonicalize_json_value(payload))


def _decode_source_artifacts(payload: bytes) -> dict[SourceArtifactRole, SourceArtifactBinding]:
    document = json.loads(payload.decode("utf-8"))
    if type(document) is not dict:
        raise ValueError("source_artifacts must be an object")
    decoded: dict[SourceArtifactRole, SourceArtifactBinding] = {}
    for role_name, binding_payload in document.items():
        if type(binding_payload) is not dict:
            raise ValueError("source artifact binding must be an object")
        decoded[SourceArtifactRole(role_name)] = SourceArtifactBinding(
            artifact_id=str(binding_payload["artifact_id"]),
            media_type=str(binding_payload["media_type"]),
            size_bytes=int(binding_payload["size_bytes"]),
            raw_sha256=str(binding_payload["raw_sha256"]),
        )
    return decoded


def _row_mapping(row: object) -> Mapping[str, object]:
    return cast(Mapping[str, object], row)


def _required_text(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if type(value) is not str or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_text(row: Mapping[str, object], key: str) -> str | None:
    value = row[key]
    if value is None:
        return None
    if type(value) is not str or not value:
        raise ValueError(f"{key} must be a non-empty string or None")
    return value


def _required_int(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if type(value) is not int:
        raise ValueError(f"{key} must be an integer")
    return value


def _blob_value(row: Mapping[str, object], key: str) -> bytes:
    value = row[key]
    if type(value) is not bytes:
        raise ValueError(f"{key} must be bytes")
    return value


def _datetime_to_epoch_us(value: datetime) -> int:
    _validate_utc_datetime(value, "timestamp")
    delta = value - _EPOCH
    micros = (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
    if micros < _SQLITE_INT_MIN or micros > _SQLITE_INT_MAX:
        raise ValueError("timestamp is outside SQLite INTEGER range")
    return micros


def _epoch_us_to_datetime(value: int) -> datetime:
    if type(value) is not int:
        raise ValueError("epoch microseconds must be an integer")
    return _EPOCH + timedelta(microseconds=value)


def _validate_utc_datetime(value: object, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{label} must be an aware UTC datetime")
