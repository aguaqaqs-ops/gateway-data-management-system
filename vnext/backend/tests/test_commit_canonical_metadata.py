"""Repository-scoped canonical commit provenance resolution."""

from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest
from gateway_shared_kernel import DigestRef
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.canonical_metadata.ports import (
    CommitCanonicalMetadataCode,
    CommitCanonicalMetadataError,
    CommitCanonicalScope,
)
from gateway_backend.application.canonical_metadata.manifest_reader import (
    ArtifactBackedCanonicalizationManifestReader,
)
from gateway_backend.artifacts import InMemoryArtifactStore, put_with_built_ref
from gateway_backend.capabilities.storage_projection import (
    CANONICALIZATION_MANIFEST_MEDIA_TYPE,
    CANONICALIZATION_MANIFEST_CONTRACT,
    STORAGE_PROJECTION_VERSION,
    CanonicalizationManifest,
    durable_manifest_bytes,
)
from gateway_backend.capabilities.storage_projection._digest import (
    compute_manifest_digest,
    manifest_document,
)
from gateway_backend.capabilities.table_rules.contracts import RULESET_ID, RULESET_VERSION
from gateway_backend.infrastructure.control_db.schema import bootstrap_control_db_schema
from gateway_backend.infrastructure.control_db.sqlite_commit_metadata import (
    SQLiteCommitCanonicalMetadataPort,
)

pytestmark = pytest.mark.unit

FROZEN_SCOPE = CommitCanonicalScope(
    gateway_device_external_key="device-1",
    business_project_id="project-1",
)
OTHER_SCOPE = CommitCanonicalScope(
    gateway_device_external_key="device-2",
    business_project_id="project-2",
)

COMMIT_METADATA_MISSING_CASES = (
    ("same_commit_in_another_repository", "other_repository"),
    ("ambiguous_same_repository_commit", "ambiguous_commit"),
    ("unregistered_commit", "unregistered"),
    ("submission_outside_frozen_scope", "outside_scope"),
)


class CountingMetadataMetrics:
    def __init__(self) -> None:
        self.digest_mismatches = 0

    def increment_digest_mismatch(self) -> None:
        self.digest_mismatches += 1


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    connection.row_factory = sqlite3.Row
    bootstrap_control_db_schema(connection)
    return connection


def _insert_workspace(
    connection: sqlite3.Connection,
    *,
    workspace_id: str,
    repository_id: str,
    scope: CommitCanonicalScope,
) -> None:
    connection.execute(
        """
        INSERT INTO workspace_records (
            workspace_id, owner_actor_id, gateway_device_external_key, business_project_id,
            repository_id, state, generation, optimistic_version, created_at_us, updated_at_us
        ) VALUES (?, 'actor-1', ?, ?, ?, 'CLOSED', 1, 1, 0, 0)
        """,
        (
            workspace_id,
            scope.gateway_device_external_key,
            scope.business_project_id,
            repository_id,
        ),
    )


def _insert_submission(
    connection: sqlite3.Connection,
    *,
    repository_id: str,
    commit_id: str,
    scope: CommitCanonicalScope,
    manifest_ref_id: str,
    manifest_digest: str,
    submission_id: str = "submission-1",
    workspace_id: str = "workspace-1",
) -> None:
    _insert_workspace(
        connection,
        workspace_id=workspace_id,
        repository_id=repository_id,
        scope=scope,
    )
    attempt_id = f"attempt-{submission_id}"
    snapshot_digest = "sha256:" + "33" * 32
    connection.execute(
        """
        INSERT INTO submit_attempt_records (
            submit_attempt_id, workspace_id, workspace_generation, upload_revision_id,
            preview_result_id, repository_id, business_baseline_node_id,
            business_baseline_commit_id, baseline_head_version, repository_expected_commit_id,
            canonical_business_digest, source_digest, snapshot_digest, source_artifact_refs,
            canonical_table_set_closure_ref, canonical_table_set_closure_digest,
            preview_ready_closure_ref, preview_ready_closure_digest, canonicalization_manifest_ref,
            canonicalization_manifest_digest, requested_target_ref, requested_verification_policy,
            requested_unknown_type_policy, builder_mutation_policy, accept_idempotency_key,
            accept_request_fingerprint, repository_upload_idempotency_key,
            repository_import_idempotency_key, operation_id, state, submission_id,
            optimistic_version, created_by, created_at_us
        ) VALUES (
            ?, ?, 1, 'upload-1', 'preview-1', ?, 'initial-node', 'initial-commit', 1,
            'initial-commit', 'sha256:canonical', 'sha256:source', ?, X'5B5D',
            'canonical-closure', 'sha256:closure', 'ready-closure', 'sha256:ready', ?, ?,
            'main', 'STRUCTURAL', 'REJECT', 'ADAPTIVE_PATCH', 'accept-key', 'sha256:fingerprint',
            'upload-key', 'import-key', ?, 'FINALIZED', ?, 1, 'actor-1', 0
        )
        """,
        (
            attempt_id,
            workspace_id,
            repository_id,
            snapshot_digest,
            manifest_ref_id,
            manifest_digest,
            f"operation-{submission_id}",
            submission_id,
        ),
    )
    connection.execute(
        """
        INSERT INTO submission_records (
            submission_id, submit_attempt_id, workspace_id, workspace_generation,
            upload_revision_id, preview_result_id, repository_id, based_on_baseline_node_id,
            business_baseline_commit_id, repository_commit_id, canonical_business_digest,
            source_artifact_refs, canonicalization_manifest_ref, canonicalization_manifest_digest,
            repository_import_artifact_raw_sha256, repository_artifact_id,
            requested_verification_policy, completed_verification_policy,
            requested_unknown_type_policy, target_ref, created_by, created_at_us
        ) VALUES (?, ?, ?, 1, 'upload-1', 'preview-1', ?, 'initial-node', 'initial-commit', ?,
                  'sha256:canonical', X'5B5D', ?, ?, 'sha256:package', 'repository-artifact-1',
                  'STRUCTURAL', 'STRUCTURAL', 'REJECT', 'main', 'actor-1', 0)
        """,
        (
            submission_id,
            attempt_id,
            workspace_id,
            repository_id,
            commit_id,
            manifest_ref_id,
            manifest_digest,
        ),
    )


def _manifest(
    *,
    contract_version: str = CANONICALIZATION_MANIFEST_CONTRACT,
    storage_projection_version: str = STORAGE_PROJECTION_VERSION,
    ruleset_version: str = RULESET_VERSION,
) -> tuple[CanonicalizationManifest, bytes]:
    draft = CanonicalizationManifest(
        contract_version=contract_version,
        storage_projection_version=storage_projection_version,
        ruleset_id=RULESET_ID,
        ruleset_version=ruleset_version,
        ruleset_digest=DigestRef("sha256:" + "11" * 32),
        source_artifact_digest=DigestRef("sha256:" + "22" * 32),
        tables=(),
    )
    manifest = replace(draft, manifest_digest=compute_manifest_digest(draft))
    if (
        contract_version == CANONICALIZATION_MANIFEST_CONTRACT
        and storage_projection_version == STORAGE_PROJECTION_VERSION
        and ruleset_version == RULESET_VERSION
    ):
        payload = durable_manifest_bytes(manifest)
    else:
        document = dict(manifest_document(manifest))
        assert manifest.manifest_digest is not None
        document["manifest_digest"] = manifest.manifest_digest.value
        payload = canonicalize_json_value(document)
    return manifest, payload


def _put_manifest(store: InMemoryArtifactStore, payload: bytes, *, artifact_id: str) -> str:
    put_with_built_ref(
        store,
        payload,
        artifact_id=artifact_id,
        media_type=CANONICALIZATION_MANIFEST_MEDIA_TYPE,
    )
    return artifact_id


def _resolver(
    connection: sqlite3.Connection,
    store: InMemoryArtifactStore,
    *,
    metrics: CountingMetadataMetrics | None = None,
) -> SQLiteCommitCanonicalMetadataPort:
    connection.execute("BEGIN")
    return SQLiteCommitCanonicalMetadataPort(
        connection,
        manifest_reader=ArtifactBackedCanonicalizationManifestReader(
            artifact_store=store,
            artifact_refs=store,
        ),
        metrics=metrics,
    )


@pytest.mark.parametrize(
    ("case", "setup"),
    COMMIT_METADATA_MISSING_CASES,
    ids=[case for case, _setup in COMMIT_METADATA_MISSING_CASES],
)
def test_commit_metadata_is_resolved_only_from_the_requested_repository_and_frozen_scope(
    case: str,
    setup: str,
) -> None:
    connection = _connection()
    store = InMemoryArtifactStore()
    manifest, payload = _manifest()
    assert manifest.manifest_digest is not None
    manifest_ref_id = _put_manifest(store, payload, artifact_id=f"manifest-{case.replace('_', '-')}")
    if setup == "other_repository":
        _insert_submission(
            connection,
            repository_id="repository-other",
            commit_id="shared-commit",
            scope=FROZEN_SCOPE,
            manifest_ref_id=manifest_ref_id,
            manifest_digest=manifest.manifest_digest.value,
        )
        requested_repository = "repository-current"
        requested_commit = "shared-commit"
    elif setup == "ambiguous_commit":
        _insert_submission(
            connection,
            repository_id="repository-current",
            commit_id="ambiguous-commit",
            scope=FROZEN_SCOPE,
            manifest_ref_id=manifest_ref_id,
            manifest_digest=manifest.manifest_digest.value,
        )
        _insert_submission(
            connection,
            repository_id="repository-current",
            commit_id="ambiguous-commit",
            scope=FROZEN_SCOPE,
            manifest_ref_id=manifest_ref_id,
            manifest_digest=manifest.manifest_digest.value,
            submission_id="submission-2",
            workspace_id="workspace-2",
        )
        requested_repository = "repository-current"
        requested_commit = "ambiguous-commit"
    elif setup == "outside_scope":
        _insert_submission(
            connection,
            repository_id="repository-current",
            commit_id="scoped-commit",
            scope=OTHER_SCOPE,
            manifest_ref_id=manifest_ref_id,
            manifest_digest=manifest.manifest_digest.value,
        )
        requested_repository = "repository-current"
        requested_commit = "scoped-commit"
    else:
        requested_repository = "repository-current"
        requested_commit = "unregistered-commit"

    resolver = _resolver(connection, store)
    with pytest.raises(CommitCanonicalMetadataError) as raised:
        resolver.resolve(
            repository_id=requested_repository,
            commit_id=requested_commit,
            scope=FROZEN_SCOPE,
        )
    assert raised.value.code is CommitCanonicalMetadataCode.MISSING
    connection.close()


def test_initial_commit_returns_an_initial_marker_without_opening_a_manifest() -> None:
    connection = _connection()
    connection.execute(
        """
        INSERT INTO baseline_node_records (
            node_id, repository_id, gateway_device_external_key, business_project_id,
            commit_id, kind, parent_node_id, source_submission_id, created_at_us
        ) VALUES ('initial-node', 'repository-1', 'device-1', 'project-1', 'initial-commit',
                  'INITIAL', NULL, NULL, 0)
        """
    )
    resolver = _resolver(connection, InMemoryArtifactStore())

    metadata = resolver.resolve(
        repository_id="repository-1",
        commit_id="initial-commit",
        scope=FROZEN_SCOPE,
    )

    assert metadata.initial is True
    assert metadata.manifest is None
    assert metadata.repository_id == "repository-1"
    connection.close()


def test_manifest_digest_mismatch_fails_with_diagnostic_log_and_metric(
    caplog: pytest.LogCaptureFixture,
) -> None:
    connection = _connection()
    store = InMemoryArtifactStore()
    manifest, payload = _manifest()
    assert manifest.manifest_digest is not None
    manifest_ref_id = _put_manifest(store, payload, artifact_id="manifest-digest-mismatch")
    _insert_submission(
        connection,
        repository_id="repository-1",
        commit_id="commit-1",
        scope=FROZEN_SCOPE,
        manifest_ref_id=manifest_ref_id,
        manifest_digest="sha256:" + "33" * 32,
    )
    metrics = CountingMetadataMetrics()
    resolver = _resolver(connection, store, metrics=metrics)

    with caplog.at_level("ERROR", logger="gateway_backend.infrastructure.control_db.sqlite_commit_metadata"):
        with pytest.raises(CommitCanonicalMetadataError) as raised:
            resolver.resolve(
                repository_id="repository-1",
                commit_id="commit-1",
                scope=FROZEN_SCOPE,
            )

    assert raised.value.code is CommitCanonicalMetadataCode.DIGEST_MISMATCH
    assert metrics.digest_mismatches == 1
    event = next(record for record in caplog.records if getattr(record, "event", None))
    assert getattr(event, "event") == "commit_canonical_metadata_digest_mismatch"
    assert getattr(event, "metric_name") == "commit_canonical_metadata_digest_mismatch_total"
    assert getattr(event, "metric_increment") == 1
    connection.close()


def test_unsupported_manifest_versions_fail_closed_as_missing_provenance() -> None:
    connection = _connection()
    store = InMemoryArtifactStore()
    historical, payload = _manifest(
        contract_version="published-contract-2",
        storage_projection_version="published-storage-0",
        ruleset_version="published-rules-v1",
    )
    assert historical.manifest_digest is not None
    manifest_ref_id = _put_manifest(store, payload, artifact_id="manifest-historical")
    _insert_submission(
        connection,
        repository_id="repository-1",
        commit_id="historical-commit",
        scope=FROZEN_SCOPE,
        manifest_ref_id=manifest_ref_id,
        manifest_digest=historical.manifest_digest.value,
    )
    resolver = _resolver(connection, store)

    with pytest.raises(CommitCanonicalMetadataError) as raised:
        resolver.resolve(
            repository_id="repository-1",
            commit_id="historical-commit",
            scope=FROZEN_SCOPE,
        )

    assert raised.value.code is CommitCanonicalMetadataCode.MISSING
    connection.close()
