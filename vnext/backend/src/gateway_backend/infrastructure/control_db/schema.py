"""Control DB schema: one set of statements creates every table, constraint and index.

An empty control DB receives all statements. A control DB that already holds objects is accepted
only when its ``sqlite_master`` structure equals the structure those same statements produce; it is
then left untouched. Anything else fails closed with ``UnsupportedSchemaVersion`` before any write,
and the operator deletes the local control DB to recreate it. Schema changes edit this module
directly; forward migrations return only when a deployment must keep data.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from gateway_backend.operations import StoreBusy, UnsupportedSchemaVersion

__all__ = ["CONTROL_DB_SCHEMA_STATEMENTS", "bootstrap_control_db_schema", "verify_control_db_file"]

CONTROL_DB_SCHEMA_STATEMENTS: tuple[str, ...] = (
    # Durable operation runtime (Operations).
"""
    CREATE TABLE operation_records (
        operation_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(operation_id) = 'text' AND length(operation_id) BETWEEN 1 AND 255),
        contract_version TEXT NOT NULL
            CHECK (typeof(contract_version) = 'text' AND length(contract_version) BETWEEN 1 AND 128),
        optimistic_version INTEGER NOT NULL
            CHECK (typeof(optimistic_version) = 'integer' AND optimistic_version >= 0),
        job_kind TEXT NOT NULL
            CHECK (typeof(job_kind) = 'text' AND length(job_kind) BETWEEN 1 AND 128),
        job_contract_version TEXT NOT NULL
            CHECK (typeof(job_contract_version) = 'text' AND length(job_contract_version) BETWEEN 1 AND 128),
        job_payload BLOB
            CHECK (job_payload IS NULL OR typeof(job_payload) = 'blob'),
        job_payload_ref BLOB
            CHECK (job_payload_ref IS NULL OR typeof(job_payload_ref) = 'blob'),
        business_refs BLOB NOT NULL
            CHECK (typeof(business_refs) = 'blob'),
        artifact_refs BLOB NOT NULL
            CHECK (typeof(artifact_refs) = 'blob'),
        repository_operation_id TEXT
            CHECK
                (repository_operation_id IS NULL OR (typeof(repository_operation_id) = 'text' AND length(repository_operation_id) BETWEEN 1 AND 255)),
        checkpoint_ref BLOB
            CHECK (checkpoint_ref IS NULL OR typeof(checkpoint_ref) = 'blob'),
        ready_closure_ref BLOB
            CHECK (ready_closure_ref IS NULL OR typeof(ready_closure_ref) = 'blob'),
        status TEXT NOT NULL
            CHECK
                (typeof(status) = 'text' AND status IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'SUPERSEDED', 'MANUAL_RECOVERY_REQUIRED')),
        diagnostic BLOB
            CHECK (diagnostic IS NULL OR typeof(diagnostic) = 'blob'),
        cancel_requested INTEGER NOT NULL
            CHECK (typeof(cancel_requested) = 'integer' AND cancel_requested IN (0, 1)),
        created_at_us INTEGER NOT NULL
            CHECK (typeof(created_at_us) = 'integer'),
        updated_at_us INTEGER NOT NULL
            CHECK (typeof(updated_at_us) = 'integer'),
        completed_at_us INTEGER
            CHECK (completed_at_us IS NULL OR typeof(completed_at_us) = 'integer')
    )
    """,

    """
    CREATE INDEX operation_records_status_readback ON
        operation_records(status, updated_at_us, operation_id)
    """,

    """
    CREATE TABLE step_records (
        step_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(step_id) = 'text' AND length(step_id) BETWEEN 1 AND 255),
        operation_id TEXT NOT NULL
            CHECK (typeof(operation_id) = 'text' AND length(operation_id) BETWEEN 1 AND 255),
        contract_version TEXT NOT NULL
            CHECK (typeof(contract_version) = 'text' AND length(contract_version) BETWEEN 1 AND 128),
        optimistic_version INTEGER NOT NULL
            CHECK (typeof(optimistic_version) = 'integer' AND optimistic_version >= 0),
        step_name TEXT NOT NULL
            CHECK (typeof(step_name) = 'text' AND length(step_name) BETWEEN 1 AND 128),
        attempt_count INTEGER NOT NULL
            CHECK (typeof(attempt_count) = 'integer' AND attempt_count >= 0),
        status TEXT NOT NULL
            CHECK
                (typeof(status) = 'text' AND status IN ('PENDING', 'RUNNING', 'RETRY_WAIT', 'SUCCEEDED', 'FAILED', 'CANCELLED', 'MANUAL_RECOVERY_REQUIRED')),
        diagnostic BLOB
            CHECK (diagnostic IS NULL OR typeof(diagnostic) = 'blob'),
        cancel_requested INTEGER NOT NULL
            CHECK (typeof(cancel_requested) = 'integer' AND cancel_requested IN (0, 1)),
        retry_not_before_us INTEGER
            CHECK (retry_not_before_us IS NULL OR typeof(retry_not_before_us) = 'integer'),
        worker_id TEXT
            CHECK (worker_id IS NULL OR (typeof(worker_id) = 'text' AND length(worker_id) BETWEEN 1 AND 255)),
        lease_token TEXT
            CHECK
                (lease_token IS NULL OR (typeof(lease_token) = 'text' AND length(lease_token) BETWEEN 1 AND 255)),
        lease_expires_at_us INTEGER
            CHECK (lease_expires_at_us IS NULL OR typeof(lease_expires_at_us) = 'integer'),
        checkpoint_ref BLOB
            CHECK (checkpoint_ref IS NULL OR typeof(checkpoint_ref) = 'blob'),
        prior_output_refs BLOB NOT NULL
            CHECK (typeof(prior_output_refs) = 'blob'),
        created_at_us INTEGER NOT NULL
            CHECK (typeof(created_at_us) = 'integer'),
        updated_at_us INTEGER NOT NULL
            CHECK (typeof(updated_at_us) = 'integer'),
        started_at_us INTEGER
            CHECK (started_at_us IS NULL OR typeof(started_at_us) = 'integer'),
        completed_at_us INTEGER
            CHECK (completed_at_us IS NULL OR typeof(completed_at_us) = 'integer'),
        eligible_at_us INTEGER
            CHECK (eligible_at_us IS NULL OR typeof(eligible_at_us) = 'integer'),
        UNIQUE (operation_id, step_name),
        FOREIGN KEY (operation_id) REFERENCES operation_records(operation_id) ON DELETE RESTRICT
    )
    """,

    """
    CREATE INDEX step_records_claim_order ON
        step_records(status, eligible_at_us, created_at_us, step_id) WHERE status IN
        ('PENDING', 'RETRY_WAIT')
    """,

    """
    CREATE UNIQUE INDEX step_records_one_active_per_operation ON step_records(operation_id) WHERE
        status IN ('PENDING', 'RUNNING', 'RETRY_WAIT', 'MANUAL_RECOVERY_REQUIRED')
    """,

    # Workspace, upload, preview and submit flow.
    """
    CREATE TABLE workspace_records (
        workspace_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(workspace_id) = 'text' AND length(workspace_id) BETWEEN 1 AND 255),
        owner_actor_id TEXT NOT NULL
            CHECK (typeof(owner_actor_id) = 'text' AND length(owner_actor_id) BETWEEN 1 AND 255),
        gateway_device_external_key TEXT NOT NULL
            CHECK
                (typeof(gateway_device_external_key) = 'text' AND length(gateway_device_external_key) BETWEEN 1 AND 255),
        business_project_id TEXT NOT NULL
            CHECK (typeof(business_project_id) = 'text' AND length(business_project_id) BETWEEN 1 AND 255),
        repository_id TEXT NOT NULL
            CHECK (typeof(repository_id) = 'text' AND length(repository_id) BETWEEN 1 AND 255),
        state TEXT NOT NULL
            CHECK (typeof(state) = 'text' AND state IN ('OPEN', 'CLOSED')),
        generation INTEGER NOT NULL
            CHECK (typeof(generation) = 'integer' AND generation >= 0),
        optimistic_version INTEGER NOT NULL
            CHECK (typeof(optimistic_version) = 'integer' AND optimistic_version >= 0),
        current_upload_revision_id TEXT
            CHECK
                (current_upload_revision_id IS NULL OR (typeof(current_upload_revision_id) = 'text' AND length(current_upload_revision_id) BETWEEN 1 AND 255)),
        current_preview_result_id TEXT
            CHECK
                (current_preview_result_id IS NULL OR (typeof(current_preview_result_id) = 'text' AND length(current_preview_result_id) BETWEEN 1 AND 255)),
        created_at_us INTEGER NOT NULL
            CHECK (typeof(created_at_us) = 'integer'),
        updated_at_us INTEGER NOT NULL
            CHECK (typeof(updated_at_us) = 'integer'),
        closed_at_us INTEGER
            CHECK (closed_at_us IS NULL OR typeof(closed_at_us) = 'integer')
    )
    """,

    """
    CREATE UNIQUE INDEX workspace_records_open_exact_scope ON
        workspace_records(owner_actor_id, gateway_device_external_key, business_project_id) WHERE
        state = 'OPEN'
    """,

    """
    CREATE TABLE upload_idempotency_records (
        workspace_id TEXT NOT NULL
            CHECK (typeof(workspace_id) = 'text' AND length(workspace_id) BETWEEN 1 AND 255),
        idempotency_key TEXT NOT NULL
            CHECK (typeof(idempotency_key) = 'text' AND length(idempotency_key) BETWEEN 1 AND 255),
        request_fingerprint TEXT NOT NULL
            CHECK (typeof(request_fingerprint) = 'text' AND length(request_fingerprint) BETWEEN 1 AND 512),
        upload_revision_id TEXT NOT NULL
            CHECK (typeof(upload_revision_id) = 'text' AND length(upload_revision_id) BETWEEN 1 AND 255),
        PRIMARY KEY (workspace_id, idempotency_key),
        FOREIGN KEY (workspace_id) REFERENCES workspace_records(workspace_id) ON DELETE RESTRICT,
        FOREIGN KEY (upload_revision_id) REFERENCES upload_revision_records(upload_revision_id) ON
            DELETE RESTRICT
    )
    """,

    """
    CREATE TABLE upload_revision_records (
        upload_revision_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(upload_revision_id) = 'text' AND length(upload_revision_id) BETWEEN 1 AND 255),
        workspace_id TEXT NOT NULL
            CHECK (typeof(workspace_id) = 'text' AND length(workspace_id) BETWEEN 1 AND 255),
        generation INTEGER NOT NULL
            CHECK (typeof(generation) = 'integer' AND generation >= 0),
        input_completeness TEXT NOT NULL
            CHECK (typeof(input_completeness) = 'text' AND input_completeness IN ('FULL', 'MODIFIED_ONLY')),
        source_artifacts BLOB NOT NULL
            CHECK (typeof(source_artifacts) = 'blob'),
        idempotency_key TEXT NOT NULL
            CHECK (typeof(idempotency_key) = 'text' AND length(idempotency_key) BETWEEN 1 AND 255),
        request_fingerprint TEXT NOT NULL
            CHECK (typeof(request_fingerprint) = 'text' AND length(request_fingerprint) BETWEEN 1 AND 512),
        created_by TEXT NOT NULL
            CHECK (typeof(created_by) = 'text' AND length(created_by) BETWEEN 1 AND 255),
        created_at_us INTEGER NOT NULL
            CHECK (typeof(created_at_us) = 'integer'),
        UNIQUE (workspace_id, generation),
        FOREIGN KEY (workspace_id) REFERENCES workspace_records(workspace_id) ON DELETE RESTRICT
    )
    """,

    """
    CREATE TABLE "preview_idempotency_records" (
        workspace_id TEXT NOT NULL
            CHECK (typeof(workspace_id) = 'text' AND length(workspace_id) BETWEEN 1 AND 255),
        idempotency_key TEXT NOT NULL
            CHECK (typeof(idempotency_key) = 'text' AND length(idempotency_key) BETWEEN 1 AND 255),
        request_fingerprint TEXT NOT NULL
            CHECK (typeof(request_fingerprint) = 'text' AND length(request_fingerprint) BETWEEN 1 AND 512),
        operation_id TEXT NOT NULL
            CHECK (typeof(operation_id) = 'text' AND length(operation_id) BETWEEN 1 AND 255),
        upload_revision_id TEXT NOT NULL
            CHECK (typeof(upload_revision_id) = 'text' AND length(upload_revision_id) BETWEEN 1 AND 255),
        generation INTEGER NOT NULL
            CHECK (typeof(generation) = 'integer' AND generation >= 0),
        business_baseline_node_id TEXT NOT NULL
            CHECK
                (typeof(business_baseline_node_id) = 'text' AND length(business_baseline_node_id) BETWEEN 1 AND 255),
        baseline_head_version INTEGER NOT NULL
            CHECK (typeof(baseline_head_version) = 'integer' AND baseline_head_version >= 0),
        PRIMARY KEY (workspace_id, idempotency_key),
        FOREIGN KEY (workspace_id) REFERENCES workspace_records(workspace_id) ON DELETE RESTRICT,
        FOREIGN KEY (operation_id) REFERENCES operation_records(operation_id) ON DELETE RESTRICT,
        FOREIGN KEY (upload_revision_id) REFERENCES upload_revision_records(upload_revision_id) ON
            DELETE RESTRICT
    )
    """,

    """
    CREATE TABLE preview_result_records (
        preview_result_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(preview_result_id) = 'text' AND length(preview_result_id) BETWEEN 1 AND 255),
        workspace_id TEXT NOT NULL
            CHECK (typeof(workspace_id) = 'text' AND length(workspace_id) BETWEEN 1 AND 255),
        upload_revision_id TEXT NOT NULL
            CHECK (typeof(upload_revision_id) = 'text' AND length(upload_revision_id) BETWEEN 1 AND 255),
        generation INTEGER NOT NULL
            CHECK (typeof(generation) = 'integer' AND generation >= 0),
        repository_id TEXT NOT NULL
            CHECK (typeof(repository_id) = 'text' AND length(repository_id) BETWEEN 1 AND 255),
        binding BLOB NOT NULL
            CHECK (typeof(binding) = 'blob'),
        operation_id TEXT NOT NULL UNIQUE
            CHECK (typeof(operation_id) = 'text' AND length(operation_id) BETWEEN 1 AND 255),
        created_at_us INTEGER NOT NULL
            CHECK (typeof(created_at_us) = 'integer'),
        FOREIGN KEY (workspace_id) REFERENCES workspace_records(workspace_id) ON DELETE RESTRICT,
        FOREIGN KEY (upload_revision_id) REFERENCES upload_revision_records(upload_revision_id) ON
            DELETE RESTRICT
    )
    """,

    """
    CREATE TABLE submit_idempotency_records (
        workspace_id TEXT NOT NULL
            CHECK (typeof(workspace_id) = 'text' AND length(workspace_id) BETWEEN 1 AND 255),
        idempotency_key TEXT NOT NULL
            CHECK (typeof(idempotency_key) = 'text' AND length(idempotency_key) BETWEEN 1 AND 255),
        request_fingerprint TEXT NOT NULL
            CHECK (typeof(request_fingerprint) = 'text' AND length(request_fingerprint) BETWEEN 1 AND 512),
        submit_attempt_id TEXT NOT NULL UNIQUE
            CHECK (typeof(submit_attempt_id) = 'text' AND length(submit_attempt_id) BETWEEN 1 AND 255),
        PRIMARY KEY (workspace_id, idempotency_key),
        FOREIGN KEY (workspace_id) REFERENCES workspace_records(workspace_id) ON DELETE RESTRICT,
        FOREIGN KEY (submit_attempt_id) REFERENCES submit_attempt_records(submit_attempt_id) ON
            DELETE RESTRICT
    )
    """,

    """
    CREATE TABLE submit_attempt_records (
        submit_attempt_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(submit_attempt_id) = 'text' AND length(submit_attempt_id) BETWEEN 1 AND 255),
        workspace_id TEXT NOT NULL
            CHECK (typeof(workspace_id) = 'text' AND length(workspace_id) BETWEEN 1 AND 255),
        workspace_generation INTEGER NOT NULL
            CHECK (typeof(workspace_generation) = 'integer' AND workspace_generation >= 0),
        upload_revision_id TEXT NOT NULL
            CHECK (typeof(upload_revision_id) = 'text' AND length(upload_revision_id) BETWEEN 1 AND 255),
        preview_result_id TEXT NOT NULL
            CHECK (typeof(preview_result_id) = 'text' AND length(preview_result_id) BETWEEN 1 AND 255),
        repository_id TEXT NOT NULL
            CHECK (typeof(repository_id) = 'text' AND length(repository_id) BETWEEN 1 AND 255),
        business_baseline_node_id TEXT NOT NULL
            CHECK
                (typeof(business_baseline_node_id) = 'text' AND length(business_baseline_node_id) BETWEEN 1 AND 255),
        business_baseline_commit_id TEXT NOT NULL
            CHECK
                (typeof(business_baseline_commit_id) = 'text' AND length(business_baseline_commit_id) BETWEEN 1 AND 255),
        baseline_head_version INTEGER NOT NULL
            CHECK (typeof(baseline_head_version) = 'integer' AND baseline_head_version >= 0),
        repository_expected_commit_id TEXT NOT NULL
            CHECK
                (typeof(repository_expected_commit_id) = 'text' AND length(repository_expected_commit_id) BETWEEN 1 AND 255),
        canonical_business_digest TEXT NOT NULL
            CHECK
                (typeof(canonical_business_digest) = 'text' AND length(canonical_business_digest) BETWEEN 1 AND 512),
        source_digest TEXT NOT NULL
            CHECK (typeof(source_digest) = 'text' AND length(source_digest) BETWEEN 1 AND 512),
        snapshot_digest TEXT NOT NULL
            CHECK (typeof(snapshot_digest) = 'text' AND length(snapshot_digest) BETWEEN 1 AND 512),
        source_artifact_refs BLOB NOT NULL
            CHECK (typeof(source_artifact_refs) = 'blob'),
        canonical_table_set_closure_ref TEXT NOT NULL
            CHECK (typeof(canonical_table_set_closure_ref) = 'text' AND length(canonical_table_set_closure_ref) BETWEEN 1 AND 255),
        canonical_table_set_closure_digest TEXT NOT NULL
            CHECK (typeof(canonical_table_set_closure_digest) = 'text' AND length(canonical_table_set_closure_digest) BETWEEN 1 AND 512),
        preview_ready_closure_ref TEXT NOT NULL
            CHECK
                (typeof(preview_ready_closure_ref) = 'text' AND length(preview_ready_closure_ref) BETWEEN 1 AND 255),
        preview_ready_closure_digest TEXT NOT NULL
            CHECK
                (typeof(preview_ready_closure_digest) = 'text' AND length(preview_ready_closure_digest) BETWEEN 1 AND 512),
        canonicalization_manifest_ref TEXT NOT NULL
            CHECK (typeof(canonicalization_manifest_ref) = 'text' AND length(canonicalization_manifest_ref) BETWEEN 1 AND 255),
        canonicalization_manifest_digest TEXT NOT NULL
            CHECK (typeof(canonicalization_manifest_digest) = 'text' AND length(canonicalization_manifest_digest) BETWEEN 1 AND 512),
        prepared_canonicalization_manifest_ref TEXT
            CHECK (prepared_canonicalization_manifest_ref IS NULL OR (typeof(prepared_canonicalization_manifest_ref) = 'text' AND length(prepared_canonicalization_manifest_ref) BETWEEN 1 AND 255)),
        prepared_canonicalization_manifest_digest TEXT
            CHECK (prepared_canonicalization_manifest_digest IS NULL OR (typeof(prepared_canonicalization_manifest_digest) = 'text' AND length(prepared_canonicalization_manifest_digest) BETWEEN 1 AND 512)),
        repository_import_artifact_ref BLOB
            CHECK (repository_import_artifact_ref IS NULL OR typeof(repository_import_artifact_ref) = 'blob'),
        repository_artifact_ref BLOB
            CHECK (repository_artifact_ref IS NULL OR typeof(repository_artifact_ref) = 'blob'),
        repository_operation_id TEXT
            CHECK
                (repository_operation_id IS NULL OR (typeof(repository_operation_id) = 'text' AND length(repository_operation_id) BETWEEN 1 AND 255)),
        repository_operation_evidence TEXT
            CHECK
                (repository_operation_evidence IS NULL OR (typeof(repository_operation_evidence) = 'text' AND length(repository_operation_evidence) BETWEEN 1 AND 4096)),
        requested_target_ref TEXT NOT NULL
            CHECK (typeof(requested_target_ref) = 'text' AND requested_target_ref IN ('main')),
        requested_verification_policy TEXT NOT NULL
            CHECK
                (typeof(requested_verification_policy) = 'text' AND requested_verification_policy IN ('STRUCTURAL')),
        requested_unknown_type_policy TEXT NOT NULL
            CHECK
                (typeof(requested_unknown_type_policy) = 'text' AND requested_unknown_type_policy IN ('REJECT')),
        builder_mutation_policy TEXT NOT NULL
            CHECK (typeof(builder_mutation_policy) = 'text' AND builder_mutation_policy IN ('REBUILD_ALWAYS')),
        accept_idempotency_key TEXT NOT NULL
            CHECK (typeof(accept_idempotency_key) = 'text' AND length(accept_idempotency_key) BETWEEN 1 AND 255),
        accept_request_fingerprint TEXT NOT NULL
            CHECK
                (typeof(accept_request_fingerprint) = 'text' AND length(accept_request_fingerprint) BETWEEN 1 AND 512),
        repository_upload_idempotency_key TEXT NOT NULL
            CHECK
                (typeof(repository_upload_idempotency_key) = 'text' AND length(repository_upload_idempotency_key) BETWEEN 1 AND 255),
        repository_import_idempotency_key TEXT NOT NULL
            CHECK
                (typeof(repository_import_idempotency_key) = 'text' AND length(repository_import_idempotency_key) BETWEEN 1 AND 255),
        operation_id TEXT NOT NULL UNIQUE
            CHECK (typeof(operation_id) = 'text' AND length(operation_id) BETWEEN 1 AND 255),
        state TEXT NOT NULL
            CHECK (typeof(state) = 'text' AND state IN ('PREPARED', 'EFFECT_PENDING', 'FINALIZED', 'ABORTED')),
        submission_id TEXT
            CHECK
                (submission_id IS NULL OR (typeof(submission_id) = 'text' AND length(submission_id) BETWEEN 1 AND 255)),
        optimistic_version INTEGER NOT NULL
            CHECK (typeof(optimistic_version) = 'integer' AND optimistic_version >= 0),
        created_by TEXT NOT NULL
            CHECK (typeof(created_by) = 'text' AND length(created_by) BETWEEN 1 AND 255),
        created_at_us INTEGER NOT NULL
            CHECK (typeof(created_at_us) = 'integer'),
        effect_pending_at_us INTEGER
            CHECK (effect_pending_at_us IS NULL OR typeof(effect_pending_at_us) = 'integer'),
        finalized_at_us INTEGER
            CHECK (finalized_at_us IS NULL OR typeof(finalized_at_us) = 'integer'),
        aborted_at_us INTEGER
            CHECK (aborted_at_us IS NULL OR typeof(aborted_at_us) = 'integer'),
        abort_code TEXT
            CHECK (abort_code IS NULL OR (typeof(abort_code) = 'text' AND length(abort_code) BETWEEN 1 AND 128)),
        identity_confirmations BLOB NOT NULL DEFAULT X'5B5D'
            CHECK (typeof(identity_confirmations) = 'blob'),
        FOREIGN KEY (workspace_id) REFERENCES workspace_records(workspace_id) ON DELETE RESTRICT,
        FOREIGN KEY (operation_id) REFERENCES operation_records(operation_id) ON DELETE RESTRICT
    )
    """,

    """
    CREATE INDEX submit_attempt_records_repository_state ON submit_attempt_records(repository_id, state)
    """,

    """
    CREATE TABLE submission_records (
        submission_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(submission_id) = 'text' AND length(submission_id) BETWEEN 1 AND 255),
        submit_attempt_id TEXT NOT NULL UNIQUE
            CHECK (typeof(submit_attempt_id) = 'text' AND length(submit_attempt_id) BETWEEN 1 AND 255),
        workspace_id TEXT NOT NULL
            CHECK (typeof(workspace_id) = 'text' AND length(workspace_id) BETWEEN 1 AND 255),
        workspace_generation INTEGER NOT NULL
            CHECK (typeof(workspace_generation) = 'integer' AND workspace_generation >= 0),
        upload_revision_id TEXT NOT NULL
            CHECK (typeof(upload_revision_id) = 'text' AND length(upload_revision_id) BETWEEN 1 AND 255),
        preview_result_id TEXT NOT NULL
            CHECK (typeof(preview_result_id) = 'text' AND length(preview_result_id) BETWEEN 1 AND 255),
        repository_id TEXT NOT NULL
            CHECK (typeof(repository_id) = 'text' AND length(repository_id) BETWEEN 1 AND 255),
        based_on_baseline_node_id TEXT NOT NULL
            CHECK
                (typeof(based_on_baseline_node_id) = 'text' AND length(based_on_baseline_node_id) BETWEEN 1 AND 255),
        business_baseline_commit_id TEXT NOT NULL
            CHECK
                (typeof(business_baseline_commit_id) = 'text' AND length(business_baseline_commit_id) BETWEEN 1 AND 255),
        repository_commit_id TEXT NOT NULL
            CHECK (typeof(repository_commit_id) = 'text' AND length(repository_commit_id) BETWEEN 1 AND 255),
        canonical_business_digest TEXT NOT NULL
            CHECK
                (typeof(canonical_business_digest) = 'text' AND length(canonical_business_digest) BETWEEN 1 AND 512),
        source_artifact_refs BLOB NOT NULL
            CHECK (typeof(source_artifact_refs) = 'blob'),
        canonicalization_manifest_ref TEXT NOT NULL
            CHECK
                (typeof(canonicalization_manifest_ref) = 'text' AND length(canonicalization_manifest_ref) BETWEEN 1 AND 255),
        canonicalization_manifest_digest TEXT NOT NULL
            CHECK
                (typeof(canonicalization_manifest_digest) = 'text' AND length(canonicalization_manifest_digest) BETWEEN 1 AND 512),
        repository_import_artifact_raw_sha256 TEXT NOT NULL
            CHECK
                (typeof(repository_import_artifact_raw_sha256) = 'text' AND length(repository_import_artifact_raw_sha256) BETWEEN 1 AND 512),
        repository_artifact_id TEXT NOT NULL
            CHECK (typeof(repository_artifact_id) = 'text' AND length(repository_artifact_id) BETWEEN 1 AND 255),
        requested_verification_policy TEXT NOT NULL
            CHECK
                (typeof(requested_verification_policy) = 'text' AND requested_verification_policy IN ('STRUCTURAL')),
        completed_verification_policy TEXT NOT NULL
            CHECK
                (typeof(completed_verification_policy) = 'text' AND completed_verification_policy IN ('STRUCTURAL')),
        requested_unknown_type_policy TEXT NOT NULL
            CHECK
                (typeof(requested_unknown_type_policy) = 'text' AND requested_unknown_type_policy IN ('REJECT')),
        target_ref TEXT NOT NULL
            CHECK (typeof(target_ref) = 'text' AND target_ref IN ('main')),
        created_by TEXT NOT NULL
            CHECK (typeof(created_by) = 'text' AND length(created_by) BETWEEN 1 AND 255),
        created_at_us INTEGER NOT NULL
            CHECK (typeof(created_at_us) = 'integer'),
        identity_confirmations BLOB NOT NULL DEFAULT X'5B5D'
            CHECK (typeof(identity_confirmations) = 'blob'),
        FOREIGN KEY (workspace_id) REFERENCES workspace_records(workspace_id) ON DELETE RESTRICT,
        FOREIGN KEY (submit_attempt_id) REFERENCES submit_attempt_records(submit_attempt_id) ON
            DELETE RESTRICT
    )
    """,

    """
    CREATE INDEX submission_records_archive_candidate_lookup ON
        submission_records(repository_id, based_on_baseline_node_id, submission_id)
    """,

    """
    CREATE INDEX submission_records_repository_commit ON
        submission_records(repository_id, repository_commit_id)
    """,

    """
    CREATE TABLE workspace_submit_occupancy_records (
        workspace_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(workspace_id) = 'text' AND length(workspace_id) BETWEEN 1 AND 255),
        active_submit_attempt_id TEXT
            CHECK
                (active_submit_attempt_id IS NULL OR (typeof(active_submit_attempt_id) = 'text' AND length(active_submit_attempt_id) BETWEEN 1 AND 255)),
        active_submission_id TEXT
            CHECK
                (active_submission_id IS NULL OR (typeof(active_submission_id) = 'text' AND length(active_submission_id) BETWEEN 1 AND 255)),
        CHECK
            ( (active_submit_attempt_id IS NOT NULL AND active_submission_id IS NULL) OR (active_submit_attempt_id IS NULL AND active_submission_id IS NOT NULL) ),
        FOREIGN KEY (workspace_id) REFERENCES workspace_records(workspace_id) ON DELETE RESTRICT,
        FOREIGN KEY (active_submit_attempt_id) REFERENCES submit_attempt_records(submit_attempt_id)
            ON DELETE RESTRICT,
        FOREIGN KEY (active_submission_id) REFERENCES submission_records(submission_id) ON DELETE RESTRICT
    )
    """,

    """
    CREATE TABLE repository_submit_occupancy_records (
        repository_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(repository_id) = 'text' AND length(repository_id) BETWEEN 1 AND 255),
        workspace_id TEXT NOT NULL UNIQUE
            CHECK (typeof(workspace_id) = 'text' AND length(workspace_id) BETWEEN 1 AND 255),
        submit_attempt_id TEXT NOT NULL UNIQUE
            CHECK (typeof(submit_attempt_id) = 'text' AND length(submit_attempt_id) BETWEEN 1 AND 255),
        business_baseline_node_id TEXT NOT NULL
            CHECK
                (typeof(business_baseline_node_id) = 'text' AND length(business_baseline_node_id) BETWEEN 1 AND 255),
        baseline_head_version INTEGER NOT NULL
            CHECK (typeof(baseline_head_version) = 'integer' AND baseline_head_version >= 0),
        acquired_at_us INTEGER NOT NULL
            CHECK (typeof(acquired_at_us) = 'integer'),
        FOREIGN KEY (workspace_id) REFERENCES workspace_records(workspace_id) ON DELETE RESTRICT,
        FOREIGN KEY (submit_attempt_id) REFERENCES submit_attempt_records(submit_attempt_id) ON
            DELETE RESTRICT
    )
    """,

    # Review.
    """
    CREATE TABLE review_idempotency_records (
        business_project_id TEXT NOT NULL
            CHECK (typeof(business_project_id) = 'text' AND length(business_project_id) BETWEEN 1 AND 255),
        idempotency_key TEXT NOT NULL
            CHECK (typeof(idempotency_key) = 'text' AND length(idempotency_key) BETWEEN 1 AND 255),
        submission_id TEXT NOT NULL
            CHECK (typeof(submission_id) = 'text' AND length(submission_id) BETWEEN 1 AND 255),
        request_fingerprint TEXT NOT NULL
            CHECK (typeof(request_fingerprint) = 'text' AND length(request_fingerprint) BETWEEN 1 AND 512),
        event_sequence INTEGER NOT NULL
            CHECK (typeof(event_sequence) = 'integer' AND event_sequence >= 0),
        PRIMARY KEY (business_project_id, idempotency_key),
        FOREIGN KEY (submission_id) REFERENCES submission_records(submission_id) ON DELETE RESTRICT,
        FOREIGN KEY (submission_id, event_sequence) REFERENCES
            review_event_records(submission_id, sequence) ON DELETE RESTRICT
    )
    """,

    """
    CREATE TABLE review_event_records (
        submission_id TEXT NOT NULL
            CHECK (typeof(submission_id) = 'text' AND length(submission_id) BETWEEN 1 AND 255),
        sequence INTEGER NOT NULL
            CHECK (typeof(sequence) = 'integer' AND sequence >= 0),
        event_kind TEXT NOT NULL
            CHECK
                (typeof(event_kind) = 'text' AND event_kind IN ('SUBMISSION_FINALIZED', 'APPROVED', 'REJECTED', 'RETURNED_FOR_REVISION', 'WITHDRAWN')),
        from_status TEXT
            CHECK
                (from_status IS NULL OR (typeof(from_status) = 'text' AND from_status IN ('PENDING', 'APPROVED', 'REJECTED', 'RETURNED_FOR_REVISION', 'WITHDRAWN'))),
        to_status TEXT NOT NULL
            CHECK
                (typeof(to_status) = 'text' AND to_status IN ('PENDING', 'APPROVED', 'REJECTED', 'RETURNED_FOR_REVISION', 'WITHDRAWN')),
        reason TEXT
            CHECK
                (reason IS NULL OR (typeof(reason) = 'text' AND length(CAST(reason AS BLOB)) BETWEEN 0 AND 4096)),
        actor_id TEXT NOT NULL
            CHECK (typeof(actor_id) = 'text' AND length(actor_id) BETWEEN 1 AND 255),
        occurred_at_us INTEGER NOT NULL
            CHECK (typeof(occurred_at_us) = 'integer'),
        PRIMARY KEY (submission_id, sequence),
        FOREIGN KEY (submission_id) REFERENCES submission_records(submission_id) ON DELETE RESTRICT
    )
    """,

    """
    CREATE TABLE review_projection_records (
        submission_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(submission_id) = 'text' AND length(submission_id) BETWEEN 1 AND 255),
        status TEXT NOT NULL
            CHECK
                (typeof(status) = 'text' AND status IN ('PENDING', 'APPROVED', 'REJECTED', 'RETURNED_FOR_REVISION', 'WITHDRAWN')),
        optimistic_version INTEGER NOT NULL
            CHECK (typeof(optimistic_version) = 'integer' AND optimistic_version >= 0),
        latest_sequence INTEGER NOT NULL
            CHECK (typeof(latest_sequence) = 'integer' AND latest_sequence >= 0),
        updated_by TEXT NOT NULL
            CHECK (typeof(updated_by) = 'text' AND length(updated_by) BETWEEN 1 AND 255),
        updated_at_us INTEGER NOT NULL
            CHECK (typeof(updated_at_us) = 'integer'),
        FOREIGN KEY (submission_id) REFERENCES submission_records(submission_id) ON DELETE RESTRICT
    )
    """,

    # Provisioned scope mappings and repository baseline heads.
    """
    CREATE TABLE provisioned_scope_mappings (
        gateway_device_external_key TEXT NOT NULL
            CHECK
                (typeof(gateway_device_external_key) = 'text' AND length(gateway_device_external_key) BETWEEN 1 AND 255),
        business_project_id TEXT NOT NULL
            CHECK (typeof(business_project_id) = 'text' AND length(business_project_id) BETWEEN 1 AND 255),
        repository_id TEXT NOT NULL
            CHECK (typeof(repository_id) = 'text' AND length(repository_id) BETWEEN 1 AND 255),
        enabled INTEGER NOT NULL
            CHECK (typeof(enabled) = 'integer' AND enabled IN (0, 1)),
        PRIMARY KEY (gateway_device_external_key, business_project_id)
    )
    """,

    """
    CREATE UNIQUE INDEX provisioned_scope_mappings_one_active_device ON
        provisioned_scope_mappings(gateway_device_external_key) WHERE enabled = 1
    """,

    """
    CREATE UNIQUE INDEX provisioned_scope_mappings_one_repository ON
        provisioned_scope_mappings(repository_id)
    """,

    """
    CREATE TABLE baseline_node_records (
        node_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(node_id) = 'text' AND length(node_id) BETWEEN 1 AND 255),
        repository_id TEXT NOT NULL
            CHECK (typeof(repository_id) = 'text' AND length(repository_id) BETWEEN 1 AND 255),
        gateway_device_external_key TEXT NOT NULL
            CHECK
                (typeof(gateway_device_external_key) = 'text' AND length(gateway_device_external_key) BETWEEN 1 AND 255),
        business_project_id TEXT NOT NULL
            CHECK (typeof(business_project_id) = 'text' AND length(business_project_id) BETWEEN 1 AND 255),
        commit_id TEXT NOT NULL
            CHECK (typeof(commit_id) = 'text' AND length(commit_id) BETWEEN 1 AND 255),
        kind TEXT NOT NULL
            CHECK (typeof(kind) = 'text' AND kind IN ('INITIAL', 'ARCHIVED_SUBMISSION')),
        parent_node_id TEXT
            CHECK
                (parent_node_id IS NULL OR (typeof(parent_node_id) = 'text' AND length(parent_node_id) BETWEEN 1 AND 255)),
        source_submission_id TEXT
            CHECK
                (source_submission_id IS NULL OR (typeof(source_submission_id) = 'text' AND length(source_submission_id) BETWEEN 1 AND 255)),
        created_at_us INTEGER NOT NULL
            CHECK (typeof(created_at_us) = 'integer'),
        CHECK
            ( (kind = 'INITIAL' AND parent_node_id IS NULL AND source_submission_id IS NULL) OR (kind = 'ARCHIVED_SUBMISSION' AND parent_node_id IS NOT NULL AND source_submission_id IS NOT NULL) ),
        FOREIGN KEY (repository_id, parent_node_id) REFERENCES
            baseline_node_records(repository_id, node_id) ON DELETE RESTRICT
    )
    """,

    """
    CREATE UNIQUE INDEX baseline_node_records_one_initial_per_repository ON
        baseline_node_records(repository_id) WHERE kind = 'INITIAL'
    """,

    """
    CREATE UNIQUE INDEX baseline_node_records_repository_node ON
        baseline_node_records(repository_id, node_id)
    """,

    """
    CREATE TABLE baseline_head_records (
        repository_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(repository_id) = 'text' AND length(repository_id) BETWEEN 1 AND 255),
        node_id TEXT NOT NULL
            CHECK (typeof(node_id) = 'text' AND length(node_id) BETWEEN 1 AND 255),
        optimistic_version INTEGER NOT NULL
            CHECK (typeof(optimistic_version) = 'integer' AND optimistic_version >= 0),
        FOREIGN KEY (repository_id, node_id) REFERENCES
            baseline_node_records(repository_id, node_id) ON DELETE RESTRICT
    )
    """,

    # Archive.
    """
    CREATE TABLE archive_plan_records (
        plan_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(plan_id) = 'text' AND length(CAST(plan_id AS BLOB)) BETWEEN 1 AND 255),
        repository_id TEXT NOT NULL
            CHECK (typeof(repository_id) = 'text' AND length(CAST(repository_id AS BLOB)) BETWEEN 1 AND 255),
        gateway_device_external_key TEXT NOT NULL
            CHECK
                (typeof(gateway_device_external_key) = 'text' AND length(CAST(gateway_device_external_key AS BLOB)) BETWEEN 1 AND 255),
        business_project_id TEXT NOT NULL
            CHECK
                (typeof(business_project_id) = 'text' AND length(CAST(business_project_id AS BLOB)) BETWEEN 1 AND 255),
        idempotency_key TEXT NOT NULL
            CHECK (typeof(idempotency_key) = 'text' AND length(CAST(idempotency_key AS BLOB)) BETWEEN 1 AND 255),
        request_fingerprint TEXT NOT NULL
            CHECK
                (typeof(request_fingerprint) = 'text' AND length(CAST(request_fingerprint AS BLOB)) BETWEEN 1 AND 255),
        accepted_by TEXT NOT NULL
            CHECK (typeof(accepted_by) = 'text' AND length(CAST(accepted_by AS BLOB)) BETWEEN 1 AND 255),
        accepted_at_us INTEGER NOT NULL
            CHECK (typeof(accepted_at_us) = 'integer'),
        old_baseline_node_id TEXT NOT NULL
            CHECK
                (typeof(old_baseline_node_id) = 'text' AND length(CAST(old_baseline_node_id AS BLOB)) BETWEEN 1 AND 255),
        old_baseline_commit_id TEXT NOT NULL
            CHECK
                (typeof(old_baseline_commit_id) = 'text' AND length(CAST(old_baseline_commit_id AS BLOB)) BETWEEN 1 AND 255),
        old_baseline_head_version INTEGER NOT NULL
            CHECK (typeof(old_baseline_head_version) = 'integer' AND old_baseline_head_version >= 0),
        candidate_set_digest TEXT NOT NULL
            CHECK
                (typeof(candidate_set_digest) = 'text' AND length(CAST(candidate_set_digest AS BLOB)) BETWEEN 1 AND 255),
        selected_submission_id TEXT NOT NULL
            CHECK
                (typeof(selected_submission_id) = 'text' AND length(CAST(selected_submission_id AS BLOB)) BETWEEN 1 AND 255),
        selected_candidate_digest TEXT NOT NULL
            CHECK
                (typeof(selected_candidate_digest) = 'text' AND length(CAST(selected_candidate_digest AS BLOB)) BETWEEN 1 AND 255),
        selected_repository_commit_id TEXT NOT NULL
            CHECK
                (typeof(selected_repository_commit_id) = 'text' AND length(CAST(selected_repository_commit_id AS BLOB)) BETWEEN 1 AND 255),
        confirmation_refs_json TEXT NOT NULL
            CHECK (typeof(confirmation_refs_json) = 'text'),
        anomaly_resolution_refs_json TEXT NOT NULL
            CHECK (typeof(anomaly_resolution_refs_json) = 'text'),
        frozen_input_json TEXT NOT NULL
            CHECK (typeof(frozen_input_json) = 'text')
    )
    """,

    """
    CREATE UNIQUE INDEX archive_plan_records_start_key ON
        archive_plan_records( repository_id, gateway_device_external_key, business_project_id, idempotency_key )
    """,

    """
    CREATE TABLE archive_result_records (
        result_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(result_id) = 'text' AND length(CAST(result_id AS BLOB)) BETWEEN 1 AND 255),
        plan_id TEXT NOT NULL UNIQUE
            CHECK (typeof(plan_id) = 'text' AND length(CAST(plan_id AS BLOB)) BETWEEN 1 AND 255),
        baseline_node_id TEXT NOT NULL UNIQUE
            CHECK
                (typeof(baseline_node_id) = 'text' AND length(CAST(baseline_node_id AS BLOB)) BETWEEN 1 AND 255),
        archived_at_us INTEGER NOT NULL
            CHECK (typeof(archived_at_us) = 'integer'),
        FOREIGN KEY (plan_id) REFERENCES archive_plan_records(plan_id) ON DELETE RESTRICT,
        FOREIGN KEY (baseline_node_id) REFERENCES baseline_node_records(node_id) ON DELETE RESTRICT
    )
    """,

    """
    CREATE TABLE archive_disposition_records (
        submission_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(submission_id) = 'text' AND length(CAST(submission_id AS BLOB)) BETWEEN 1 AND 255),
        result_id TEXT NOT NULL
            CHECK (typeof(result_id) = 'text' AND length(CAST(result_id AS BLOB)) BETWEEN 1 AND 255),
        disposition TEXT NOT NULL
            CHECK (typeof(disposition) = 'text' AND disposition IN ('ARCHIVED_BASELINE', 'CLOSED_NOT_ARCHIVED')),
        FOREIGN KEY (result_id) REFERENCES archive_result_records(result_id) ON DELETE RESTRICT
    )
    """,

    """
    CREATE UNIQUE INDEX archive_disposition_records_one_selected_per_result ON
        archive_disposition_records(result_id) WHERE disposition = 'ARCHIVED_BASELINE'
    """,

    """
    CREATE INDEX archive_disposition_records_result_id ON archive_disposition_records(result_id)
    """,

    """
    CREATE TABLE archive_confirmation_events (
        event_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(event_id) = 'text' AND length(CAST(event_id AS BLOB)) BETWEEN 1 AND 255),
        repository_id TEXT NOT NULL
            CHECK (typeof(repository_id) = 'text' AND length(CAST(repository_id AS BLOB)) BETWEEN 1 AND 255),
        gateway_device_external_key TEXT NOT NULL
            CHECK
                (typeof(gateway_device_external_key) = 'text' AND length(CAST(gateway_device_external_key AS BLOB)) BETWEEN 1 AND 255),
        business_project_id TEXT NOT NULL
            CHECK
                (typeof(business_project_id) = 'text' AND length(CAST(business_project_id AS BLOB)) BETWEEN 1 AND 255),
        subject_kind TEXT NOT NULL
            CHECK (subject_kind = 'CONFIRM_SELECTION'),
        subject_digest TEXT NOT NULL
            CHECK (typeof(subject_digest) = 'text' AND length(CAST(subject_digest AS BLOB)) BETWEEN 1 AND 255),
        sequence INTEGER NOT NULL
            CHECK (typeof(sequence) = 'integer' AND sequence > 0),
        action TEXT NOT NULL
            CHECK (typeof(action) = 'text' AND action IN ('CONFIRM', 'REVOKE')),
        reason TEXT
            CHECK
                (reason IS NULL OR (typeof(reason) = 'text' AND length(CAST(reason AS BLOB)) BETWEEN 1 AND 4096)),
        actor_id TEXT NOT NULL
            CHECK (typeof(actor_id) = 'text' AND length(CAST(actor_id AS BLOB)) BETWEEN 1 AND 255),
        occurred_at_us INTEGER NOT NULL
            CHECK (typeof(occurred_at_us) = 'integer'),
        idempotency_key TEXT NOT NULL
            CHECK (typeof(idempotency_key) = 'text' AND length(CAST(idempotency_key AS BLOB)) BETWEEN 1 AND 255),
        request_fingerprint TEXT NOT NULL
            CHECK
                (typeof(request_fingerprint) = 'text' AND length(CAST(request_fingerprint AS BLOB)) BETWEEN 1 AND 255),
        request_payload_json TEXT NOT NULL
            CHECK (typeof(request_payload_json) = 'text'),
        UNIQUE (repository_id, subject_digest, sequence),
        UNIQUE (repository_id, idempotency_key)
    )
    """,

    """
    CREATE INDEX archive_confirmation_events_subject ON
        archive_confirmation_events(repository_id, subject_digest, sequence)
    """,

    """
    CREATE TABLE archive_anomaly_resolution_events (
        event_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(event_id) = 'text' AND length(CAST(event_id AS BLOB)) BETWEEN 1 AND 255),
        repository_id TEXT NOT NULL
            CHECK (typeof(repository_id) = 'text' AND length(CAST(repository_id AS BLOB)) BETWEEN 1 AND 255),
        gateway_device_external_key TEXT NOT NULL
            CHECK
                (typeof(gateway_device_external_key) = 'text' AND length(CAST(gateway_device_external_key AS BLOB)) BETWEEN 1 AND 255),
        business_project_id TEXT NOT NULL
            CHECK
                (typeof(business_project_id) = 'text' AND length(CAST(business_project_id AS BLOB)) BETWEEN 1 AND 255),
        subject_kind TEXT NOT NULL
            CHECK (subject_kind IN ('APPROVED_SIBLING_EXCLUDED', 'PROJECT_IDENTITY_EXCEPTION')),
        subject_digest TEXT NOT NULL
            CHECK (typeof(subject_digest) = 'text' AND length(CAST(subject_digest AS BLOB)) BETWEEN 1 AND 255),
        sequence INTEGER NOT NULL
            CHECK (typeof(sequence) = 'integer' AND sequence > 0),
        action TEXT NOT NULL
            CHECK
                (typeof(action) = 'text' AND action IN (
                    'ACKNOWLEDGE_EXCLUSION', 'ACKNOWLEDGE_IDENTITY_EXCEPTION', 'REVOKE'
                )),
        issue_code TEXT NOT NULL
            CHECK (typeof(issue_code) = 'text' AND length(CAST(issue_code AS BLOB)) BETWEEN 1 AND 255),
        target_submission_id TEXT NOT NULL
            CHECK
                (typeof(target_submission_id) = 'text' AND length(CAST(target_submission_id AS BLOB)) BETWEEN 1 AND 255),
        target_candidate_digest TEXT NOT NULL
            CHECK
                (typeof(target_candidate_digest) = 'text' AND length(CAST(target_candidate_digest AS BLOB)) BETWEEN 1 AND 255),
        reason TEXT NOT NULL
            CHECK (typeof(reason) = 'text' AND length(CAST(reason AS BLOB)) BETWEEN 1 AND 4096),
        actor_id TEXT NOT NULL
            CHECK (typeof(actor_id) = 'text' AND length(CAST(actor_id AS BLOB)) BETWEEN 1 AND 255),
        occurred_at_us INTEGER NOT NULL
            CHECK (typeof(occurred_at_us) = 'integer'),
        idempotency_key TEXT NOT NULL
            CHECK (typeof(idempotency_key) = 'text' AND length(CAST(idempotency_key AS BLOB)) BETWEEN 1 AND 255),
        request_fingerprint TEXT NOT NULL
            CHECK
                (typeof(request_fingerprint) = 'text' AND length(CAST(request_fingerprint AS BLOB)) BETWEEN 1 AND 255),
        request_payload_json TEXT NOT NULL
            CHECK (typeof(request_payload_json) = 'text'),
        UNIQUE (repository_id, subject_digest, sequence),
        UNIQUE (repository_id, idempotency_key)
    )
    """,

    """
    CREATE INDEX archive_anomaly_resolution_events_subject ON
        archive_anomaly_resolution_events(repository_id, subject_digest, sequence)
    """,

    # History compare.
    """
    CREATE TABLE history_compare_acceptance_records (
        acceptance_id TEXT NOT NULL PRIMARY KEY
            CHECK (typeof(acceptance_id) = 'text' AND length(CAST(acceptance_id AS BLOB)) BETWEEN 1 AND 255),
        gateway_device_external_key TEXT NOT NULL
            CHECK
                (typeof(gateway_device_external_key) = 'text' AND length(CAST(gateway_device_external_key AS BLOB)) BETWEEN 1 AND 255),
        business_project_id TEXT NOT NULL
            CHECK
                (typeof(business_project_id) = 'text' AND length(CAST(business_project_id AS BLOB)) BETWEEN 1 AND 255),
        repository_id TEXT NOT NULL
            CHECK (typeof(repository_id) = 'text' AND length(CAST(repository_id AS BLOB)) BETWEEN 1 AND 255),
        idempotency_key TEXT NOT NULL
            CHECK (typeof(idempotency_key) = 'text' AND length(CAST(idempotency_key AS BLOB)) BETWEEN 1 AND 255),
        request_fingerprint TEXT NOT NULL
            CHECK
                (typeof(request_fingerprint) = 'text' AND length(CAST(request_fingerprint AS BLOB)) BETWEEN 1 AND 512),
        comparison_ruleset_digest TEXT NOT NULL
            CHECK
                (typeof(comparison_ruleset_digest) = 'text' AND length(CAST(comparison_ruleset_digest AS BLOB)) BETWEEN 1 AND 255),
        nodes_json TEXT NOT NULL
            CHECK (typeof(nodes_json) = 'text'),
        operation_id TEXT NOT NULL UNIQUE
            CHECK (typeof(operation_id) = 'text' AND length(CAST(operation_id AS BLOB)) BETWEEN 1 AND 255),
        created_at_us INTEGER NOT NULL
            CHECK (typeof(created_at_us) = 'integer')
    )
    """,

    """
    CREATE UNIQUE INDEX history_compare_acceptance_scope_idempotency ON
        history_compare_acceptance_records( gateway_device_external_key, business_project_id, idempotency_key )
    """,

    # Artifact protection.
    """
    CREATE TABLE artifact_protection_intents (
        artifact_id TEXT NOT NULL
            CHECK (typeof(artifact_id) = 'text' AND length(artifact_id) BETWEEN 1 AND 255),
        owner_kind TEXT NOT NULL
            CHECK (typeof(owner_kind) = 'text' AND length(owner_kind) BETWEEN 1 AND 128),
        owner_id TEXT NOT NULL
            CHECK (typeof(owner_id) = 'text' AND length(owner_id) BETWEEN 1 AND 255),
        intent TEXT NOT NULL
            CHECK (typeof(intent) = 'text' AND length(intent) BETWEEN 1 AND 128),
        recorded_at_us INTEGER NOT NULL
            CHECK (typeof(recorded_at_us) = 'integer'),
        PRIMARY KEY (artifact_id, owner_kind, owner_id)
    )
    """,
)

_STRUCTURE_QUERY = """
    SELECT type, name, tbl_name, sql
    FROM sqlite_master
    WHERE substr(name, 1, 7) != 'sqlite_'
    ORDER BY type, name
"""
_MISMATCH_NAME_LIMIT = 8
_NOT_READABLE_MESSAGE = (
    "control DB file is not a readable SQLite database; "
    "delete the local control DB and start again to recreate it"
)

_StructureRow = tuple[str, str, str, str | None]


def bootstrap_control_db_schema(connection: sqlite3.Connection) -> None:
    """Create the schema in an empty control DB, or verify an existing one without writing.

    The check runs inside ``BEGIN IMMEDIATE``. A rejected database is rolled back and not modified.
    """

    if connection.in_transaction:
        raise ValueError("schema bootstrap requires a connection outside a transaction")
    try:
        connection.execute("BEGIN IMMEDIATE")
        existing = _read_structure(connection)
        if existing:
            _assert_expected_structure(existing)
        else:
            for statement in CONTROL_DB_SCHEMA_STATEMENTS:
                connection.execute(statement)
        connection.execute("COMMIT")
    except UnsupportedSchemaVersion:
        _rollback_if_needed(connection)
        raise
    except sqlite3.OperationalError as exc:
        _rollback_if_needed(connection)
        if "busy" in str(exc).lower() or "locked" in str(exc).lower():
            raise StoreBusy("control DB is busy") from None
        raise
    except BaseException:
        _rollback_if_needed(connection)
        raise


def verify_control_db_file(db_path: Path) -> None:
    """Check an existing control DB file read-only, before the connection profile touches it.

    The connection profile switches the journal mode to WAL, which writes to the file. A file that
    is rejected here is therefore never opened for writing. Missing and empty files are left to
    ``bootstrap_control_db_schema``, which creates the schema in them.
    """

    if not db_path.is_file() or db_path.stat().st_size == 0:
        return
    connection = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True, isolation_level=None)
    try:
        existing = _read_structure(connection)
    except sqlite3.OperationalError as exc:
        if "busy" in str(exc).lower() or "locked" in str(exc).lower():
            raise StoreBusy("control DB is busy") from None
        raise
    except sqlite3.DatabaseError:
        raise UnsupportedSchemaVersion(_NOT_READABLE_MESSAGE) from None
    finally:
        connection.close()
    if existing:
        _assert_expected_structure(existing)


def _read_structure(connection: sqlite3.Connection) -> list[_StructureRow]:
    return [
        (row[0], row[1], row[2], row[3]) for row in connection.execute(_STRUCTURE_QUERY).fetchall()
    ]


def _assert_expected_structure(existing: list[_StructureRow]) -> None:
    expected = _expected_structure()
    if existing == expected:
        return
    unexpected, missing = _mismatched_object_names(existing, expected)
    raise UnsupportedSchemaVersion(
        "control DB schema does not match this build "
        f"(unexpected objects: {_shown(unexpected)}; missing or changed objects: {_shown(missing)}); "
        "delete the local control DB and start again to recreate it"
    )


def _shown(names: list[str]) -> str:
    if not names:
        return "none"
    shown = ", ".join(names[:_MISMATCH_NAME_LIMIT])
    if len(names) > _MISMATCH_NAME_LIMIT:
        shown += f" and {len(names) - _MISMATCH_NAME_LIMIT} more"
    return shown


def _expected_structure() -> list[_StructureRow]:
    scratch = sqlite3.connect(":memory:", isolation_level=None)
    try:
        for statement in CONTROL_DB_SCHEMA_STATEMENTS:
            scratch.execute(statement)
        return [(row[0], row[1], row[2], row[3]) for row in scratch.execute(_STRUCTURE_QUERY)]
    finally:
        scratch.close()


def _mismatched_object_names(
    existing: list[_StructureRow],
    expected: list[_StructureRow],
) -> tuple[list[str], list[str]]:
    existing_by_key = {(kind, name): (tbl_name, sql) for kind, name, tbl_name, sql in existing}
    expected_by_key = {(kind, name): (tbl_name, sql) for kind, name, tbl_name, sql in expected}
    unexpected = sorted({name for _kind, name in existing_by_key.keys() - expected_by_key.keys()})
    missing = sorted(
        {
            name
            for (kind, name), value in expected_by_key.items()
            if existing_by_key.get((kind, name)) != value
        }
    )
    return unexpected, missing


def _rollback_if_needed(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        connection.execute("ROLLBACK")
