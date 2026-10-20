"""SQLite row mapping and transaction-scoped submission repository adapter."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import cast

from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.domain.submission.errors import (
    SubmitAttemptInvariantViolation,
    SubmitAttemptVersionConflict,
    SubmitOccupancyConflict,
)
from gateway_backend.domain.submission.models import (
    BackendArtifactRef,
    BuilderMutationPolicy,
    RepositoryArtifactRef,
    RepositorySubmitOccupancy,
    SubmitAcceptanceRecord,
    SubmitAttempt,
    SubmitAttemptState,
    IdentityConfirmationAction,
    SubmitIdentityConfirmation,
    SubmitTargetRef,
    SubmitUnknownTypePolicy,
    SubmitVerificationPolicy,
    Submission,
    WorkspaceSubmitOccupancy,
)
from gateway_backend.domain.submission.errors import ArchiveCandidateReadBoundExceeded
from gateway_backend.domain.submission.ports import (
    ArchiveActiveAttemptFacts,
    ArchiveCandidateFacts,
)
from gateway_backend.domain.submission.review import ReviewStatus

_ARCHIVE_CANDIDATE_FETCH_LIMIT = 201
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_SQLITE_INT_MIN = -(2**63)
_SQLITE_INT_MAX = 2**63 - 1

_SUBMIT_ATTEMPT_COLUMNS = (
    "submit_attempt_id, workspace_id, workspace_generation, upload_revision_id, "
    "preview_result_id, repository_id, business_baseline_node_id, business_baseline_commit_id, "
    "baseline_head_version, repository_expected_commit_id, canonical_business_digest, "
    "source_digest, snapshot_digest, source_artifact_refs, canonical_table_set_closure_ref, "
    "canonical_table_set_closure_digest, preview_ready_closure_ref, preview_ready_closure_digest, canonicalization_manifest_ref, "
    "canonicalization_manifest_digest, prepared_canonicalization_manifest_ref, "
    "prepared_canonicalization_manifest_digest, repository_import_artifact_ref, repository_artifact_ref, "
    "repository_operation_id, repository_operation_evidence, requested_target_ref, "
    "requested_verification_policy, requested_unknown_type_policy, builder_mutation_policy, "
    "accept_idempotency_key, accept_request_fingerprint, repository_upload_idempotency_key, "
    "repository_import_idempotency_key, operation_id, state, submission_id, optimistic_version, "
    "created_by, created_at_us, effect_pending_at_us, finalized_at_us, aborted_at_us, abort_code, "
    "identity_confirmations"
)

SUBMISSION_COLUMNS = (
    "submission_id, submit_attempt_id, workspace_id, workspace_generation, upload_revision_id, "
    "preview_result_id, repository_id, based_on_baseline_node_id, business_baseline_commit_id, "
    "repository_commit_id, canonical_business_digest, source_artifact_refs, "
    "canonicalization_manifest_ref, canonicalization_manifest_digest, "
    "repository_import_artifact_raw_sha256, repository_artifact_id, "
    "requested_verification_policy, completed_verification_policy, requested_unknown_type_policy, "
    "target_ref, created_by, created_at_us, identity_confirmations"
)


class SQLiteSubmissionRepository:
    """Concrete submission participant bound to one already-open transaction."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        *,
        transaction_now: datetime,
        read_only: bool = False,
    ) -> None:
        if not connection.in_transaction:
            raise RuntimeError("SQLiteSubmissionRepository requires an active transaction")
        if type(read_only) is not bool:
            raise ValueError("read_only must be a bool")
        _validate_utc_datetime(transaction_now, "transaction_now")
        self._connection = connection
        self._transaction_now = transaction_now
        self._read_only = read_only

    def find_submit_idempotency(
        self,
        workspace_id: str,
        idempotency_key: str,
    ) -> SubmitAcceptanceRecord | None:
        row = self._connection.execute(
            """
            SELECT workspace_id, idempotency_key, request_fingerprint, submit_attempt_id
            FROM submit_idempotency_records
            WHERE workspace_id = ? AND idempotency_key = ?
            """,
            (workspace_id, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        return SubmitAcceptanceRecord(
            workspace_id=row[0],
            idempotency_key=row[1],
            request_fingerprint=row[2],
            submit_attempt_id=row[3],
        )

    def get_submit_attempt(self, submit_attempt_id: str) -> SubmitAttempt | None:
        row = self._connection.execute(
            f"SELECT {_SUBMIT_ATTEMPT_COLUMNS} FROM submit_attempt_records WHERE submit_attempt_id = ?",
            (submit_attempt_id,),
        ).fetchone()
        if row is None:
            return None
        return submit_attempt_from_row(row_mapping(row))

    def get_submission(self, submission_id: str) -> Submission | None:
        row = self._connection.execute(
            f"SELECT {SUBMISSION_COLUMNS} FROM submission_records WHERE submission_id = ?",
            (submission_id,),
        ).fetchone()
        if row is None:
            return None
        return submission_from_row(row_mapping(row))

    def get_submission_by_attempt(self, submit_attempt_id: str) -> Submission | None:
        row = self._connection.execute(
            f"SELECT {SUBMISSION_COLUMNS} FROM submission_records WHERE submit_attempt_id = ?",
            (submit_attempt_id,),
        ).fetchone()
        if row is None:
            return None
        return submission_from_row(row_mapping(row))

    def get_workspace_occupancy(self, workspace_id: str) -> WorkspaceSubmitOccupancy | None:
        row = self._connection.execute(
            """
            SELECT workspace_id, active_submit_attempt_id, active_submission_id
            FROM workspace_submit_occupancy_records
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        ).fetchone()
        if row is None:
            return None
        return WorkspaceSubmitOccupancy(
            workspace_id=row[0],
            active_submit_attempt_id=row[1],
            active_submission_id=row[2],
        )

    def get_repository_occupancy(self, repository_id: str) -> RepositorySubmitOccupancy | None:
        row = self._connection.execute(
            """
            SELECT repository_id, workspace_id, submit_attempt_id, business_baseline_node_id,
                   baseline_head_version, acquired_at_us
            FROM repository_submit_occupancy_records
            WHERE repository_id = ?
            """,
            (repository_id,),
        ).fetchone()
        if row is None:
            return None
        return RepositorySubmitOccupancy(
            repository_id=row[0],
            workspace_id=row[1],
            submit_attempt_id=row[2],
            business_baseline_node_id=row[3],
            baseline_head_version=row[4],
            acquired_at=_epoch_us_to_datetime(row[5]),
        )

    def list_archive_candidate_facts(
        self,
        repository_id: str,
        *,
        baseline_node_id: str,
        baseline_commit_id: str,
    ) -> tuple[ArchiveCandidateFacts, ...]:
        rows = self._connection.execute(
            """
            SELECT
                s.*,
                p.status AS review_status,
                p.latest_sequence AS review_sequence
            FROM submission_records AS s
            LEFT JOIN review_projection_records AS p
                ON s.submission_id = p.submission_id
            LEFT JOIN archive_disposition_records AS d
                ON s.submission_id = d.submission_id
            WHERE s.repository_id = ?
              AND s.based_on_baseline_node_id = ?
              AND s.business_baseline_commit_id = ?
              AND d.submission_id IS NULL
              AND (
                p.status = 'APPROVED'
                OR p.submission_id IS NULL
                OR NOT EXISTS (
                  SELECT 1
                  FROM review_event_records AS e
                  WHERE e.submission_id = s.submission_id
                )
                OR EXISTS (
                  SELECT 1
                  FROM review_event_records AS e
                  WHERE e.submission_id = s.submission_id
                    AND e.sequence = (
                      SELECT MAX(e2.sequence)
                      FROM review_event_records AS e2
                      WHERE e2.submission_id = s.submission_id
                    )
                    AND e.to_status = 'APPROVED'
                    AND (p.status IS NULL OR p.status != 'APPROVED')
                )
              )
            ORDER BY s.submission_id
            LIMIT ?
            """,
            (
                repository_id,
                baseline_node_id,
                baseline_commit_id,
                _ARCHIVE_CANDIDATE_FETCH_LIMIT,
            ),
        ).fetchall()
        if len(rows) >= _ARCHIVE_CANDIDATE_FETCH_LIMIT:
            raise ArchiveCandidateReadBoundExceeded()
        facts: list[ArchiveCandidateFacts] = []
        for row in rows:
            mapping = row_mapping(row)
            submission = submission_from_row(mapping)
            review_status_raw = mapping.get("review_status")
            review_sequence_raw = mapping.get("review_sequence")
            review_status = (
                None
                if review_status_raw is None
                else ReviewStatus(str(review_status_raw))
            )
            review_sequence = (
                None
                if review_sequence_raw is None
                else int(cast(int | str, review_sequence_raw))
            )
            facts.append(
                ArchiveCandidateFacts(
                    submission=submission,
                    review_status=review_status,
                    review_sequence=review_sequence,
                )
            )
        return tuple(facts)

    def list_active_submit_attempts(self, repository_id: str) -> tuple[ArchiveActiveAttemptFacts, ...]:
        rows = self._connection.execute(
            """
            SELECT submit_attempt_id, state
            FROM submit_attempt_records
            WHERE repository_id = ?
              AND state IN ('PREPARED', 'EFFECT_PENDING')
            ORDER BY submit_attempt_id
            """,
            (repository_id,),
        ).fetchall()
        return tuple(
            ArchiveActiveAttemptFacts(
                submit_attempt_id=row["submit_attempt_id"],
                state=row["state"],
            )
            for row in rows
        )

    def insert_attempt_prepared(self, attempt: SubmitAttempt) -> None:
        self._require_writable()
        if attempt.state is not SubmitAttemptState.PREPARED:
            raise ValueError("insert_attempt_prepared requires PREPARED state")
        try:
            self._connection.execute(
                f"""
                INSERT INTO submit_attempt_records ({_SUBMIT_ATTEMPT_COLUMNS})
                VALUES ({", ".join("?" for _ in submit_attempt_to_row(attempt))})
                """,
                submit_attempt_to_row(attempt),
            )
        except sqlite3.IntegrityError as exc:
            raise _map_integrity_error(exc) from None

    def insert_idempotency(self, record: SubmitAcceptanceRecord) -> None:
        self._require_writable()
        try:
            self._connection.execute(
                """
                INSERT INTO submit_idempotency_records (
                    workspace_id, idempotency_key, request_fingerprint, submit_attempt_id
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    record.workspace_id,
                    record.idempotency_key,
                    record.request_fingerprint,
                    record.submit_attempt_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise _map_integrity_error(exc) from None

    def insert_submission(self, submission: Submission) -> None:
        self._require_writable()
        try:
            self._connection.execute(
                f"""
                INSERT INTO submission_records ({SUBMISSION_COLUMNS})
                VALUES ({", ".join("?" for _ in submission_to_row(submission))})
                """,
                submission_to_row(submission),
            )
        except sqlite3.IntegrityError as exc:
            raise _map_integrity_error(exc) from None

    def cas_update_attempt(
        self,
        attempt: SubmitAttempt,
        *,
        expected_version: int,
    ) -> SubmitAttempt:
        self._require_writable()
        current = self.get_submit_attempt(attempt.submit_attempt_id)
        if current is not None and current.identity_confirmations != attempt.identity_confirmations:
            raise SubmitAttemptInvariantViolation("SubmitAttempt identity confirmations are immutable")
        row = submit_attempt_to_row(attempt)
        updated = self._connection.execute(
            """
            UPDATE submit_attempt_records
            SET workspace_id = ?, workspace_generation = ?, upload_revision_id = ?,
                preview_result_id = ?, repository_id = ?, business_baseline_node_id = ?,
                business_baseline_commit_id = ?, baseline_head_version = ?,
                repository_expected_commit_id = ?, canonical_business_digest = ?,
                source_digest = ?, snapshot_digest = ?, source_artifact_refs = ?,
                canonical_table_set_closure_ref = ?, canonical_table_set_closure_digest = ?, preview_ready_closure_ref = ?,
                preview_ready_closure_digest = ?, canonicalization_manifest_ref = ?,
                canonicalization_manifest_digest = ?, prepared_canonicalization_manifest_ref = ?,
                prepared_canonicalization_manifest_digest = ?, repository_import_artifact_ref = ?,
                repository_artifact_ref = ?, repository_operation_id = ?,
                repository_operation_evidence = ?, requested_target_ref = ?,
                requested_verification_policy = ?, requested_unknown_type_policy = ?,
                builder_mutation_policy = ?, accept_idempotency_key = ?,
                accept_request_fingerprint = ?, repository_upload_idempotency_key = ?,
                repository_import_idempotency_key = ?, operation_id = ?, state = ?,
                submission_id = ?, optimistic_version = ?, created_by = ?, created_at_us = ?,
                effect_pending_at_us = ?, finalized_at_us = ?, aborted_at_us = ?, abort_code = ?,
                identity_confirmations = ?
            WHERE submit_attempt_id = ? AND optimistic_version = ?
            """,
            row[1:] + (attempt.submit_attempt_id, expected_version),
        )
        if updated.rowcount != 1:
            current = self.get_submit_attempt(attempt.submit_attempt_id)
            actual = current.optimistic_version if current is not None else expected_version
            raise SubmitAttemptVersionConflict(expected=expected_version, actual=actual)
        return attempt

    def insert_workspace_attempt_occupancy(
        self,
        *,
        workspace_id: str,
        submit_attempt_id: str,
    ) -> None:
        self._require_writable()
        try:
            self._connection.execute(
                """
                INSERT INTO workspace_submit_occupancy_records (
                    workspace_id, active_submit_attempt_id, active_submission_id
                ) VALUES (?, ?, NULL)
                """,
                (workspace_id, submit_attempt_id),
            )
        except sqlite3.IntegrityError as exc:
            raise _map_integrity_error(exc) from None

    def switch_workspace_occupancy_to_submission(
        self,
        *,
        workspace_id: str,
        submit_attempt_id: str,
        submission_id: str,
    ) -> None:
        self._require_writable()
        updated = self._connection.execute(
            """
            UPDATE workspace_submit_occupancy_records
            SET active_submit_attempt_id = NULL, active_submission_id = ?
            WHERE workspace_id = ? AND active_submit_attempt_id = ?
            """,
            (submission_id, workspace_id, submit_attempt_id),
        )
        if updated.rowcount != 1:
            raise SubmitOccupancyConflict("workspace submit occupancy switch failed")

    def delete_workspace_occupancy(
        self,
        workspace_id: str,
        *,
        expected_submit_attempt_id: str,
    ) -> None:
        self._require_writable()
        updated = self._connection.execute(
            """
            DELETE FROM workspace_submit_occupancy_records
            WHERE workspace_id = ? AND active_submit_attempt_id = ?
            """,
            (workspace_id, expected_submit_attempt_id),
        )
        if updated.rowcount != 1:
            raise SubmitOccupancyConflict("workspace submit occupancy delete failed")

    def delete_workspace_submission_occupancy(
        self,
        workspace_id: str,
        *,
        expected_submission_id: str,
    ) -> None:
        self._require_writable()
        updated = self._connection.execute(
            """
            DELETE FROM workspace_submit_occupancy_records
            WHERE workspace_id = ? AND active_submission_id = ?
            """,
            (workspace_id, expected_submission_id),
        )
        if updated.rowcount != 1:
            raise SubmitOccupancyConflict("workspace submission occupancy delete failed")

    def insert_repository_occupancy(self, occupancy: RepositorySubmitOccupancy) -> None:
        self._require_writable()
        try:
            self._connection.execute(
                """
                INSERT INTO repository_submit_occupancy_records (
                    repository_id, workspace_id, submit_attempt_id,
                    business_baseline_node_id, baseline_head_version, acquired_at_us
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    occupancy.repository_id,
                    occupancy.workspace_id,
                    occupancy.submit_attempt_id,
                    occupancy.business_baseline_node_id,
                    occupancy.baseline_head_version,
                    _datetime_to_epoch_us(occupancy.acquired_at),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise _map_integrity_error(exc) from None

    def delete_repository_occupancy(
        self,
        *,
        repository_id: str,
        workspace_id: str,
        submit_attempt_id: str,
        business_baseline_node_id: str,
        baseline_head_version: int,
    ) -> None:
        self._require_writable()
        updated = self._connection.execute(
            """
            DELETE FROM repository_submit_occupancy_records
            WHERE repository_id = ?
              AND workspace_id = ?
              AND submit_attempt_id = ?
              AND business_baseline_node_id = ?
              AND baseline_head_version = ?
            """,
            (
                repository_id,
                workspace_id,
                submit_attempt_id,
                business_baseline_node_id,
                baseline_head_version,
            ),
        )
        if updated.rowcount != 1:
            raise SubmitOccupancyConflict("repository submit occupancy delete failed")

    def _require_writable(self) -> None:
        if self._read_only:
            raise RuntimeError("submission repository is read-only in this transaction")


def submit_attempt_to_row(attempt: SubmitAttempt) -> tuple[object, ...]:
    return (
        attempt.submit_attempt_id,
        attempt.workspace_id,
        attempt.workspace_generation,
        attempt.upload_revision_id,
        attempt.preview_result_id,
        attempt.repository_id,
        attempt.business_baseline_node_id,
        attempt.business_baseline_commit_id,
        attempt.baseline_head_version,
        attempt.repository_expected_commit_id,
        attempt.canonical_business_digest,
        attempt.source_digest,
        attempt.snapshot_digest,
        _encode_string_list(attempt.source_artifact_refs),
        attempt.canonical_table_set_closure_ref,
        attempt.canonical_table_set_closure_digest,
        attempt.preview_ready_closure_ref,
        attempt.preview_ready_closure_digest,
        attempt.canonicalization_manifest_ref,
        attempt.canonicalization_manifest_digest,
        attempt.prepared_canonicalization_manifest_ref,
        attempt.prepared_canonicalization_manifest_digest,
        _encode_backend_artifact_ref(attempt.repository_import_artifact_ref),
        _encode_repository_artifact_ref(attempt.repository_artifact_ref),
        attempt.repository_operation_id,
        attempt.repository_operation_evidence,
        attempt.requested_target_ref.value,
        attempt.requested_verification_policy.value,
        attempt.requested_unknown_type_policy.value,
        attempt.builder_mutation_policy.value,
        attempt.accept_idempotency_key,
        attempt.accept_request_fingerprint,
        attempt.repository_upload_idempotency_key,
        attempt.repository_import_idempotency_key,
        attempt.operation_id,
        attempt.state.value,
        attempt.submission_id,
        attempt.optimistic_version,
        attempt.created_by,
        _datetime_to_epoch_us(attempt.created_at),
        _datetime_to_epoch_us(attempt.effect_pending_at) if attempt.effect_pending_at else None,
        _datetime_to_epoch_us(attempt.finalized_at) if attempt.finalized_at else None,
        _datetime_to_epoch_us(attempt.aborted_at) if attempt.aborted_at else None,
        attempt.abort_code,
        _encode_identity_confirmations(attempt.identity_confirmations),
    )


def submit_attempt_from_row(row: Mapping[str, object]) -> SubmitAttempt:
    mapping = row_mapping(row)
    return SubmitAttempt(
        submit_attempt_id=_required_text(mapping, "submit_attempt_id"),
        workspace_id=_required_text(mapping, "workspace_id"),
        workspace_generation=_required_int(mapping, "workspace_generation"),
        upload_revision_id=_required_text(mapping, "upload_revision_id"),
        preview_result_id=_required_text(mapping, "preview_result_id"),
        repository_id=_required_text(mapping, "repository_id"),
        business_baseline_node_id=_required_text(mapping, "business_baseline_node_id"),
        business_baseline_commit_id=_required_text(mapping, "business_baseline_commit_id"),
        baseline_head_version=_required_int(mapping, "baseline_head_version"),
        repository_expected_commit_id=_required_text(mapping, "repository_expected_commit_id"),
        canonical_business_digest=_required_text(mapping, "canonical_business_digest"),
        source_digest=_required_text(mapping, "source_digest"),
        snapshot_digest=_required_text(mapping, "snapshot_digest"),
        source_artifact_refs=_decode_string_list(_blob_value(mapping, "source_artifact_refs")),
        canonical_table_set_closure_ref=_required_text(mapping, "canonical_table_set_closure_ref"),
        canonical_table_set_closure_digest=_required_text(
            mapping, "canonical_table_set_closure_digest"
        ),
        preview_ready_closure_ref=_required_text(mapping, "preview_ready_closure_ref"),
        preview_ready_closure_digest=_required_text(mapping, "preview_ready_closure_digest"),
        canonicalization_manifest_ref=_required_text(mapping, "canonicalization_manifest_ref"),
        canonicalization_manifest_digest=_required_text(mapping, "canonicalization_manifest_digest"),
        prepared_canonicalization_manifest_ref=_optional_text(
            mapping, "prepared_canonicalization_manifest_ref"
        ),
        prepared_canonicalization_manifest_digest=_optional_text(
            mapping, "prepared_canonicalization_manifest_digest"
        ),
        repository_import_artifact_ref=_decode_backend_artifact_ref(
            mapping.get("repository_import_artifact_ref")
        ),
        repository_artifact_ref=_decode_repository_artifact_ref(
            mapping.get("repository_artifact_ref")
        ),
        repository_operation_id=_optional_text(mapping, "repository_operation_id"),
        repository_operation_evidence=_optional_text(mapping, "repository_operation_evidence"),
        requested_target_ref=SubmitTargetRef(_required_text(mapping, "requested_target_ref")),
        requested_verification_policy=SubmitVerificationPolicy(
            _required_text(mapping, "requested_verification_policy")
        ),
        requested_unknown_type_policy=SubmitUnknownTypePolicy(
            _required_text(mapping, "requested_unknown_type_policy")
        ),
        builder_mutation_policy=BuilderMutationPolicy(
            _required_text(mapping, "builder_mutation_policy")
        ),
        accept_idempotency_key=_required_text(mapping, "accept_idempotency_key"),
        accept_request_fingerprint=_required_text(mapping, "accept_request_fingerprint"),
        repository_upload_idempotency_key=_required_text(
            mapping, "repository_upload_idempotency_key"
        ),
        repository_import_idempotency_key=_required_text(
            mapping, "repository_import_idempotency_key"
        ),
        operation_id=_required_text(mapping, "operation_id"),
        state=SubmitAttemptState(_required_text(mapping, "state")),
        submission_id=_optional_text(mapping, "submission_id"),
        optimistic_version=_required_int(mapping, "optimistic_version"),
        created_by=_required_text(mapping, "created_by"),
        created_at=_epoch_us_to_datetime(_required_int(mapping, "created_at_us")),
        effect_pending_at=_optional_epoch_us(mapping, "effect_pending_at_us"),
        finalized_at=_optional_epoch_us(mapping, "finalized_at_us"),
        aborted_at=_optional_epoch_us(mapping, "aborted_at_us"),
        abort_code=_optional_text(mapping, "abort_code"),
        identity_confirmations=_decode_identity_confirmations(
            _blob_value(mapping, "identity_confirmations")
        ),
    )


def submission_to_row(submission: Submission) -> tuple[object, ...]:
    return (
        submission.submission_id,
        submission.submit_attempt_id,
        submission.workspace_id,
        submission.workspace_generation,
        submission.upload_revision_id,
        submission.preview_result_id,
        submission.repository_id,
        submission.based_on_baseline_node_id,
        submission.business_baseline_commit_id,
        submission.repository_commit_id,
        submission.canonical_business_digest,
        _encode_string_list(submission.source_artifact_refs),
        submission.canonicalization_manifest_ref,
        submission.canonicalization_manifest_digest,
        submission.repository_import_artifact_raw_sha256,
        submission.repository_artifact_id,
        submission.requested_verification_policy.value,
        submission.completed_verification_policy.value,
        submission.requested_unknown_type_policy.value,
        submission.target_ref.value,
        submission.created_by,
        _datetime_to_epoch_us(submission.created_at),
        _encode_identity_confirmations(submission.identity_confirmations),
    )


def submission_from_row(row: Mapping[str, object]) -> Submission:
    return Submission(
        submission_id=_required_text(row, "submission_id"),
        submit_attempt_id=_required_text(row, "submit_attempt_id"),
        workspace_id=_required_text(row, "workspace_id"),
        workspace_generation=_required_int(row, "workspace_generation"),
        upload_revision_id=_required_text(row, "upload_revision_id"),
        preview_result_id=_required_text(row, "preview_result_id"),
        repository_id=_required_text(row, "repository_id"),
        based_on_baseline_node_id=_required_text(row, "based_on_baseline_node_id"),
        business_baseline_commit_id=_required_text(row, "business_baseline_commit_id"),
        repository_commit_id=_required_text(row, "repository_commit_id"),
        canonical_business_digest=_required_text(row, "canonical_business_digest"),
        source_artifact_refs=_decode_string_list(_blob_value(row, "source_artifact_refs")),
        canonicalization_manifest_ref=_required_text(row, "canonicalization_manifest_ref"),
        canonicalization_manifest_digest=_required_text(row, "canonicalization_manifest_digest"),
        repository_import_artifact_raw_sha256=_required_text(
            row, "repository_import_artifact_raw_sha256"
        ),
        repository_artifact_id=_required_text(row, "repository_artifact_id"),
        requested_verification_policy=SubmitVerificationPolicy(
            _required_text(row, "requested_verification_policy")
        ),
        completed_verification_policy=SubmitVerificationPolicy(
            _required_text(row, "completed_verification_policy")
        ),
        requested_unknown_type_policy=SubmitUnknownTypePolicy(
            _required_text(row, "requested_unknown_type_policy")
        ),
        target_ref=SubmitTargetRef(_required_text(row, "target_ref")),
        created_by=_required_text(row, "created_by"),
        created_at=_epoch_us_to_datetime(_required_int(row, "created_at_us")),
        identity_confirmations=_decode_identity_confirmations(
            _blob_value(row, "identity_confirmations")
        ),
    )


def _encode_string_list(values: Sequence[str]) -> bytes:
    return canonicalize_json_value(list(values))


def _encode_identity_confirmations(
    values: tuple[SubmitIdentityConfirmation, ...],
) -> bytes:
    return canonicalize_json_value(
        [
            {
                "action": item.action.value,
                "assessment_set_digest": item.assessment_set_digest,
                "reason": item.reason,
                "actor_id": item.actor_id,
                "confirmed_at_us": _datetime_to_epoch_us(item.confirmed_at),
            }
            for item in values
        ]
    )


def _decode_identity_confirmations(value: bytes) -> tuple[SubmitIdentityConfirmation, ...]:
    decoded = json.loads(value)
    if type(decoded) is not list:
        raise ValueError("identity confirmations must be a JSON array")
    result: list[SubmitIdentityConfirmation] = []
    for item in decoded:
        if type(item) is not dict or set(item) != {
            "action",
            "assessment_set_digest",
            "reason",
            "actor_id",
            "confirmed_at_us",
        }:
            raise ValueError("identity confirmation record has an invalid shape")
        confirmed_at_us = item["confirmed_at_us"]
        if type(confirmed_at_us) is not int:
            raise ValueError("identity confirmation timestamp must be an integer")
        result.append(
            SubmitIdentityConfirmation(
                action=IdentityConfirmationAction(item["action"]),
                assessment_set_digest=item["assessment_set_digest"],
                reason=item["reason"],
                actor_id=item["actor_id"],
                confirmed_at=_epoch_us_to_datetime(confirmed_at_us),
            )
        )
    return tuple(result)


def identity_exception_from_blob(value: object) -> bool:
    if type(value) is not bytes:
        raise ValueError("identity confirmations must be stored as bytes")
    return bool(_decode_identity_confirmations(value))


def _decode_string_list(payload: bytes) -> tuple[str, ...]:
    document = json.loads(payload.decode("utf-8"))
    if type(document) is not list:
        raise ValueError("string list column must be a JSON array")
    items: list[str] = []
    for item in document:
        if type(item) is not str:
            raise ValueError("string list items must be strings")
        items.append(item)
    return tuple(items)


def _encode_backend_artifact_ref(ref: BackendArtifactRef | None) -> bytes | None:
    if ref is None:
        return None
    return canonicalize_json_value(
        {
            "artifact_id": ref.artifact_id,
            "media_type": ref.media_type,
            "size_bytes": ref.size_bytes,
            "raw_sha256": ref.raw_sha256,
        }
    )


def _decode_backend_artifact_ref(value: object) -> BackendArtifactRef | None:
    if value is None:
        return None
    if type(value) is not bytes:
        raise ValueError("backend artifact ref must be bytes or None")
    document = json.loads(value.decode("utf-8"))
    mapping = _require_exact_object(document, _ARTIFACT_REF_KEYS, "backend artifact ref")
    return BackendArtifactRef(
        artifact_id=_required_object_text(mapping, "artifact_id"),
        media_type=_required_object_text(mapping, "media_type"),
        size_bytes=_required_object_int(mapping, "size_bytes"),
        raw_sha256=_required_object_text(mapping, "raw_sha256"),
    )


def _encode_repository_artifact_ref(ref: RepositoryArtifactRef | None) -> bytes | None:
    if ref is None:
        return None
    return canonicalize_json_value(
        {
            "artifact_id": ref.artifact_id,
            "media_type": ref.media_type,
            "size_bytes": ref.size_bytes,
            "raw_sha256": ref.raw_sha256,
        }
    )


def _decode_repository_artifact_ref(value: object) -> RepositoryArtifactRef | None:
    if value is None:
        return None
    if type(value) is not bytes:
        raise ValueError("repository artifact ref must be bytes or None")
    document = json.loads(value.decode("utf-8"))
    mapping = _require_exact_object(document, _ARTIFACT_REF_KEYS, "repository artifact ref")
    return RepositoryArtifactRef(
        artifact_id=_required_object_text(mapping, "artifact_id"),
        media_type=_required_object_text(mapping, "media_type"),
        size_bytes=_required_object_int(mapping, "size_bytes"),
        raw_sha256=_required_object_text(mapping, "raw_sha256"),
    )


def _map_integrity_error(exc: sqlite3.IntegrityError) -> Exception:
    message = str(exc).lower()
    if "submit_idempotency_records" in message or "unique" in message:
        if "idempotency" in message or "submit_idempotency" in message:
            return SubmitOccupancyConflict("submit idempotency or occupancy constraint violated")
        return SubmitOccupancyConflict("submit occupancy constraint violated")
    return SubmitOccupancyConflict("submit persistence constraint violated")


def row_mapping(row: object) -> Mapping[str, object]:
    if isinstance(row, sqlite3.Row):
        return {key: row[key] for key in row.keys()}
    return cast(Mapping[str, object], row)


_ARTIFACT_REF_KEYS = frozenset({"artifact_id", "media_type", "size_bytes", "raw_sha256"})


def _require_exact_object(
    document: object,
    expected_keys: frozenset[str],
    label: str,
) -> Mapping[str, object]:
    if type(document) is not dict:
        raise ValueError(f"{label} must be an object")
    mapping = cast(Mapping[str, object], document)
    actual_keys = frozenset(mapping)
    if actual_keys != expected_keys:
        raise ValueError(f"{label} keys must match exactly")
    return mapping


def _required_object_text(mapping: Mapping[str, object], key: str) -> str:
    value = mapping[key]
    if type(value) is not str or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _required_object_int(mapping: Mapping[str, object], key: str) -> int:
    value = mapping[key]
    if type(value) is not int:
        raise ValueError(f"{key} must be an integer")
    return value


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


def _optional_epoch_us(row: Mapping[str, object], key: str) -> datetime | None:
    value = row[key]
    if value is None:
        return None
    return _epoch_us_to_datetime(_required_int(row, key))


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
