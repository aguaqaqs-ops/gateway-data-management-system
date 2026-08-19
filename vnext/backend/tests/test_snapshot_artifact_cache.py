"""SnapshotTableArtifact cache validation, promotion, and rebuild tests."""

from __future__ import annotations

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.snapshot_materialization.cache import SnapshotTableArtifactCache
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ArtifactSourceBinding,
    CacheAuthorityInput,
    CacheLookupPolicy,
    CacheLookupStatus,
    CacheRevalidation,
    CacheTrustLevel,
    MaterializationDiagnosticCode,
    MaterializationPolicy,
    SnapshotMaterializationStatus,
    SnapshotTableArtifact,
    SnapshotTableArtifactCacheKey,
    ValidationStatusPolicy,
)
from tests.support.repository_ref_materialization import (
    DEFAULT_REPOSITORY_ID,
    DEFAULT_REF,
    materialize_ref,
    minimal_fixture,
)
from tests.support.snapshot_artifact import publish_first_table, replace_stored_bytes
from tests.support.snapshot_materialization import materialize_sql, parse_fixture


def _binding_and_key(
    artifact: SnapshotTableArtifact,
    repository_id: str | None = None,
    resolved: str | None = None,
) -> tuple[ArtifactSourceBinding, SnapshotTableArtifactCacheKey]:
    binding = ArtifactSourceBinding(
        snapshot_digest=artifact.manifest.snapshot_digest,
        descriptor=artifact.manifest.descriptor,
        repository_id=repository_id,
        resolved_commit_hash=resolved,
    )
    key = SnapshotTableArtifactCacheKey(
        row_layout_digest=artifact.row_layout_digest,
        repository_id=repository_id,
    )
    return binding, key


def test_cache_hit_still_validates_descriptor_and_digest() -> None:
    store = InMemoryArtifactStore()
    artifact, _digest = publish_first_table(store)
    binding, key = _binding_and_key(artifact)
    cache = SnapshotTableArtifactCache()
    cache.put(
        key,
        artifact,
        trust=CacheTrustLevel.CONTENT_VERIFIED,
        binding=binding,
        policy=ValidationStatusPolicy.PROMOTE_AFTER_AUTHORITY_VALIDATION,
        store=store,
    )
    hit = cache.lookup(
        key,
        policy=CacheLookupPolicy.READ_ANY_WITH_REVALIDATION,
        store=store,
        revalidation=CacheRevalidation(
            snapshot_digest=binding.snapshot_digest,
            descriptor=binding.descriptor,
        ),
    )
    assert hit.status is CacheLookupStatus.HIT
    assert hit.artifact is not None
    assert hit.artifact.manifest.artifact_content_digest == artifact.manifest.artifact_content_digest

    row_ref = artifact.manifest.row_file_refs[0]
    replace_stored_bytes(store, row_ref, b"PAR1")
    rejected = cache.lookup(
        key,
        policy=CacheLookupPolicy.READ_ANY_WITH_REVALIDATION,
        store=store,
        revalidation=CacheRevalidation(
            snapshot_digest=binding.snapshot_digest,
            descriptor=binding.descriptor,
        ),
    )
    assert rejected.status is CacheLookupStatus.REJECTED


def test_provisional_without_revalidation_is_rejected() -> None:
    store = InMemoryArtifactStore()
    artifact, _digest = publish_first_table(store)
    binding, key = _binding_and_key(artifact)
    cache = SnapshotTableArtifactCache()
    cache.put(
        key,
        artifact,
        trust=CacheTrustLevel.PROVISIONAL,
        binding=binding,
        policy=ValidationStatusPolicy.PROVISIONAL_ONLY,
        store=store,
    )
    rejected = cache.lookup(
        key,
        policy=CacheLookupPolicy.READ_PROVISIONAL_WITH_REVALIDATION,
        store=store,
    )
    assert rejected.status is CacheLookupStatus.REJECTED
    assert rejected.diagnostics[0].code is (
        MaterializationDiagnosticCode.CACHE_PROVISIONAL_REQUIRES_REVALIDATION
    )
    commit_only = cache.lookup(
        key,
        policy=CacheLookupPolicy.READ_COMMIT_VALIDATED_ONLY,
        store=store,
        revalidation=CacheRevalidation(
            snapshot_digest=binding.snapshot_digest,
            descriptor=binding.descriptor,
        ),
    )
    assert commit_only.status is CacheLookupStatus.REJECTED
    assert commit_only.diagnostics[0].code is MaterializationDiagnosticCode.CACHE_TRUST_POLICY_REJECTED


def test_promote_requires_matching_authority() -> None:
    store = InMemoryArtifactStore()
    provider, _rows = minimal_fixture()
    result = materialize_ref(
        provider,
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        artifact_store=store,
    )
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.snapshot is not None
    assert result.table_set is not None
    artifact = result.table_set.tables[0].artifact
    assert artifact is not None
    binding, key = _binding_and_key(
        artifact,
        repository_id=DEFAULT_REPOSITORY_ID,
        resolved=DEFAULT_REF,
    )
    cache = SnapshotTableArtifactCache()
    cache.put(
        key,
        artifact,
        trust=CacheTrustLevel.CONTENT_VERIFIED,
        binding=binding,
        policy=ValidationStatusPolicy.PROMOTE_AFTER_AUTHORITY_VALIDATION,
        store=store,
    )
    missing = cache.promote(
        key,
        CacheAuthorityInput(
            repository_id="other-repo",
            resolved_commit_hash=DEFAULT_REF,
            snapshot_digest=artifact.manifest.snapshot_digest,
        ),
    )
    assert missing.status is CacheLookupStatus.REJECTED
    assert missing.diagnostics[0].code is (
        MaterializationDiagnosticCode.CACHE_PROMOTION_REQUIRES_AUTHORITY
    )
    promoted = cache.promote(
        key,
        CacheAuthorityInput(
            repository_id=DEFAULT_REPOSITORY_ID,
            resolved_commit_hash=DEFAULT_REF,
            snapshot_digest=artifact.manifest.snapshot_digest,
        ),
    )
    assert promoted.status is CacheLookupStatus.HIT
    assert promoted.trust is CacheTrustLevel.COMMIT_VALIDATED
    hit = cache.lookup(key, policy=CacheLookupPolicy.READ_COMMIT_VALIDATED_ONLY, store=store)
    assert hit.status is CacheLookupStatus.HIT


def test_sql_dump_cache_cannot_self_promote() -> None:
    store = InMemoryArtifactStore()
    artifact, _digest = publish_first_table(store)
    binding, key = _binding_and_key(artifact)
    cache = SnapshotTableArtifactCache()
    cache.put(
        key,
        artifact,
        trust=CacheTrustLevel.CONTENT_VERIFIED,
        binding=binding,
        policy=ValidationStatusPolicy.PROMOTE_AFTER_AUTHORITY_VALIDATION,
        store=store,
    )
    rejected = cache.promote(
        key,
        CacheAuthorityInput(
            repository_id="repo-x",
            resolved_commit_hash="abc123def456abc123def456abc123de",
            snapshot_digest=artifact.manifest.snapshot_digest,
        ),
    )
    assert rejected.status is CacheLookupStatus.REJECTED
    assert rejected.diagnostics[0].code is (
        MaterializationDiagnosticCode.CACHE_PROMOTION_REQUIRES_AUTHORITY
    )


def test_cache_delete_rebuilds_from_sql_and_repository_ref() -> None:
    store = InMemoryArtifactStore()
    artifact, _digest = publish_first_table(store)
    binding, key = _binding_and_key(artifact)
    cache = SnapshotTableArtifactCache()
    cache.put(
        key,
        artifact,
        trust=CacheTrustLevel.CONTENT_VERIFIED,
        binding=binding,
        policy=ValidationStatusPolicy.PROMOTE_AFTER_AUTHORITY_VALIDATION,
        store=store,
    )
    cache.delete(key)
    assert cache.lookup(key, policy=CacheLookupPolicy.READ_ANY_WITH_REVALIDATION, store=store).status is (
        CacheLookupStatus.MISS
    )
    rebuilt = materialize_sql(
        parse_fixture("sql/valid/s2-minimal-create-insert/input.sql"),
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        artifact_store=InMemoryArtifactStore(),
    )
    assert rebuilt.status is SnapshotMaterializationStatus.COMPLETE
    assert rebuilt.table_set is not None
    assert rebuilt.table_set.tables[0].artifact is not None
    assert (
        rebuilt.table_set.tables[0].descriptor.raw_content_digest
        == artifact.manifest.descriptor.raw_content_digest
    )

    provider, _rows = minimal_fixture()
    ref_result = materialize_ref(
        provider,
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        artifact_store=InMemoryArtifactStore(),
    )
    assert ref_result.status is SnapshotMaterializationStatus.COMPLETE
    assert ref_result.table_set is not None
    assert ref_result.table_set.tables[0].artifact is not None
