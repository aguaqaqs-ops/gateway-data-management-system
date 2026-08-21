"""S6 neutral comparison core cache and closure restore contract tests."""

from __future__ import annotations

from dataclasses import fields, replace

import pytest
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.cache import (
    ComparisonCoreCache,
    ComparisonCoreCacheKey,
    ComparisonCoreCacheLookupStatus,
    ComparisonCoreCachePolicy,
    ComparisonCoreCacheRestoreBinding,
)
from gateway_backend.capabilities.comparison import (
    ArtifactScope,
    ComparisonMode,
    ComparisonPlan,
    ContinuationAction,
    DetailedFactsResult,
    IdentityStatus,
    RecordsPublicationContext,
    UnverifiableContinuationBinding,
    compare_plan,
    publish_records_closure,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import CacheTrustLevel
from tests.test_comparison_ordered import _plan as ordered_plan
from tests.test_comparison_standard import _plan as standard_plan

pytestmark = pytest.mark.unit


def _standard_pair(
    *, same: bool = False
) -> tuple[ComparisonPlan, DetailedFactsResult, InMemoryArtifactStore]:
    before = """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 'before');
    """
    current = before if same else """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, NULL);
    """
    plan = standard_plan(before, current)
    result = compare_plan(plan)
    assert isinstance(result, DetailedFactsResult)
    source_store = InMemoryArtifactStore()
    published = publish_records_closure(result, source_store)
    assert isinstance(published, DetailedFactsResult)
    return plan, published, source_store


def _cache_pair(
    plan: ComparisonPlan,
    result: DetailedFactsResult,
    source_store: InMemoryArtifactStore,
) -> tuple[ComparisonCoreCache, InMemoryArtifactStore, InMemoryArtifactStore, ComparisonCoreCacheKey]:
    cache_store = InMemoryArtifactStore()
    cache = ComparisonCoreCache()
    key = ComparisonCoreCacheKey.from_plan(plan)
    cache.put(
        key,
        result,
        source_store=source_store,
        cache_store=cache_store,
        validation_status=CacheTrustLevel.CONTENT_VERIFIED,
        input_validation_status=CacheTrustLevel.CONTENT_VERIFIED,
    )
    return cache, source_store, cache_store, key


def _binding(
    plan: ComparisonPlan,
    *,
    identity_status: IdentityStatus = IdentityStatus.SAME_PROJECT,
    assessment_digest: DigestRef | None = None,
    continuation_binding: UnverifiableContinuationBinding | None = None,
    continuation_policy_version: str | None = None,
    policy_revalidated: bool = False,
) -> ComparisonCoreCacheRestoreBinding:
    if assessment_digest is None:
        assessment_digest = plan.assessment_digest
    return ComparisonCoreCacheRestoreBinding(
        pair_id="cache-pair",
        before_snapshot_digest=plan.before.snapshot.snapshot_digest,
        current_snapshot_digest=plan.current.snapshot.snapshot_digest,
        artifact_scope=plan.artifact_scope,
        comparison_mode=ComparisonMode.DETAILED,
        identity_status=identity_status,
        assessment_digest=assessment_digest,
        continuation_binding=continuation_binding,
        continuation_policy_version=continuation_policy_version,
        policy_revalidated=policy_revalidated,
    )


def _changed_key(
    key: ComparisonCoreCacheKey,
    field: str,
    value: object,
) -> ComparisonCoreCacheKey:
    if field == "before_snapshot_digest":
        assert isinstance(value, DigestRef)
        return replace(key, before_snapshot_digest=value)
    if field == "current_snapshot_digest":
        assert isinstance(value, DigestRef)
        return replace(key, current_snapshot_digest=value)
    if field == "artifact_scope":
        assert isinstance(value, ArtifactScope)
        return replace(key, artifact_scope=value)
    if field == "comparison_options":
        assert isinstance(value, tuple)
        return replace(key, comparison_options=value)
    raise AssertionError(f"unsupported test key field: {field}")


def test_cache_hit_restores_operation_local_closure_without_changing_semantics() -> None:
    plan, result, source_store = _standard_pair()
    cache, _source_store, cache_store, key = _cache_pair(plan, result, source_store)

    restored = cache.restore(
        key,
        binding=_binding(plan),
        cache_store=cache_store,
        operation_store=InMemoryArtifactStore(),
        context=RecordsPublicationContext(artifact_id_prefix="comparison-operation-a"),
    )

    assert restored.status is ComparisonCoreCacheLookupStatus.HIT
    assert restored.result is not None and restored.result.facts is not None
    assert restored.result.facts.comparison_digest == result.facts.comparison_digest  # type: ignore[union-attr]
    assert restored.result.facts.facts_core_digest == result.facts.facts_core_digest  # type: ignore[union-attr]
    assert restored.result.records_closure is not None
    assert result.records_closure is not None
    assert restored.result.records_closure.records[0].records_content_digest == (
        result.records_closure.records[0].records_content_digest
    )
    assert restored.result.facts.records_ref is not None
    assert restored.result.facts.records_ref.artifact_id.startswith("comparison-operation-a-")
    assert restored.result.records_closure.records[0].records_ref.artifact_id.startswith(
        "comparison-operation-a-"
    )


def test_cache_restores_ordered_blank_and_empty_closures() -> None:
    ordered_before = """
        CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 1, 'a'), (NULL, 2, 'x'), (2, 3, 'b');
    """
    ordered_current = """
        CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 1, 'a'), (2, 2, 'b'), (NULL, 3, 'x');
    """
    ordered = ordered_plan(ordered_before, ordered_current)
    ordered_result = compare_plan(ordered)
    assert isinstance(ordered_result, DetailedFactsResult)
    ordered_store = InMemoryArtifactStore()
    ordered_published = publish_records_closure(ordered_result, ordered_store)
    assert isinstance(ordered_published, DetailedFactsResult)
    ordered_cache_store = InMemoryArtifactStore()
    ordered_cache = ComparisonCoreCache()
    ordered_key = ComparisonCoreCacheKey.from_plan(ordered)
    ordered_cache.put(
        ordered_key,
        ordered_published,
        source_store=ordered_store,
        cache_store=ordered_cache_store,
        validation_status=CacheTrustLevel.CONTENT_VERIFIED,
        input_validation_status=CacheTrustLevel.CONTENT_VERIFIED,
    )
    ordered_restored = ordered_cache.restore(
        ordered_key,
        binding=_binding(ordered),
        cache_store=ordered_cache_store,
        operation_store=InMemoryArtifactStore(),
    )
    assert ordered_restored.status is ComparisonCoreCacheLookupStatus.HIT
    assert ordered_restored.result is not None
    assert ordered_restored.result.records_closure is not None
    assert {entry.family.value for entry in ordered_restored.result.records_closure.records} == {
        "ORDERED",
        "BLANK",
    }

    empty_plan, empty_result, empty_source = _standard_pair(same=True)
    empty_cache, _source, empty_store, empty_key = _cache_pair(
        empty_plan, empty_result, empty_source
    )
    empty_hit = empty_cache.restore(
        empty_key,
        binding=_binding(empty_plan),
        cache_store=empty_store,
        operation_store=InMemoryArtifactStore(),
    )
    assert empty_hit.status is ComparisonCoreCacheLookupStatus.HIT
    assert empty_hit.result is not None
    assert empty_hit.result.records_closure is not None
    assert empty_hit.result.records_closure.records == ()


@pytest.mark.parametrize(
    ("label", "field", "value"),
    (
        ("before", "before_snapshot_digest", raw_blob_digest(b"other-before")),
        ("current", "current_snapshot_digest", raw_blob_digest(b"other-current")),
        ("scope", "artifact_scope", ArtifactScope.UPDATE_ONLY),
        ("option", "comparison_options", (("include_unchanged_tables", False),)),
    ),
)
def test_semantic_key_changes_are_cache_misses(label: str, field: str, value: object) -> None:
    del label
    plan, result, source_store = _standard_pair()
    cache, _source, cache_store, key = _cache_pair(plan, result, source_store)
    changed = _changed_key(key, field, value)
    hit = cache.lookup(changed, cache_store=cache_store)
    assert hit.status is ComparisonCoreCacheLookupStatus.MISS


def test_disabled_cache_and_cold_path_have_no_result() -> None:
    plan, result, source_store = _standard_pair()
    cache, _source, cache_store, key = _cache_pair(plan, result, source_store)
    disabled = cache.lookup(
        key,
        cache_store=cache_store,
        policy=ComparisonCoreCachePolicy.DISABLED,
    )
    missing = cache.lookup(
        replace(key, current_snapshot_digest=raw_blob_digest(b"cold")),
        cache_store=cache_store,
    )
    assert disabled.status is ComparisonCoreCacheLookupStatus.DISABLED
    assert missing.status is ComparisonCoreCacheLookupStatus.MISS


def test_tampered_cache_artifact_is_rejected() -> None:
    plan, result, source_store = _standard_pair()
    cache, _source, cache_store, key = _cache_pair(plan, result, source_store)
    value = cache.lookup(key, cache_store=cache_store).value
    assert value is not None and value.closure_ref is not None
    stored_ref, _raw = cache_store._artifacts[value.closure_ref.artifact_id]
    cache_store._artifacts[value.closure_ref.artifact_id] = (stored_ref, b"tampered")

    rejected = cache.lookup(key, cache_store=cache_store)
    assert rejected.status is ComparisonCoreCacheLookupStatus.REJECTED
    assert rejected.value is None


def test_identity_rebind_requires_fresh_unverifiable_continuation_policy() -> None:
    plan, result, source_store = _standard_pair()
    cache, _source, cache_store, key = _cache_pair(plan, result, source_store)
    assessment = plan.assessment_digest
    assert assessment is not None
    continuation = UnverifiableContinuationBinding(
        action=ContinuationAction.ALLOW_DETAILED_ON_UNVERIFIABLE,
        pair_id="cache-pair",
        before_snapshot_digest=plan.before.snapshot.snapshot_digest,
        current_snapshot_digest=plan.current.snapshot.snapshot_digest,
        assessment_digest=assessment,
        assessment_set_digest=raw_blob_digest(b"assessment-set"),
        policy_version="policy/v1",
    )

    blocked = cache.restore(
        key,
        binding=_binding(
            plan,
            identity_status=IdentityStatus.UNVERIFIABLE,
            continuation_binding=continuation,
        ),
        cache_store=cache_store,
        operation_store=InMemoryArtifactStore(),
    )
    assert blocked.status is ComparisonCoreCacheLookupStatus.REJECTED

    accepted = cache.restore(
        key,
        binding=_binding(
            plan,
            identity_status=IdentityStatus.UNVERIFIABLE,
            continuation_binding=continuation,
            continuation_policy_version="policy/v1",
            policy_revalidated=True,
        ),
        cache_store=cache_store,
        operation_store=InMemoryArtifactStore(),
    )
    assert accepted.status is ComparisonCoreCacheLookupStatus.HIT
    assert accepted.result is not None
    assert accepted.result.status.value == "DEGRADED"
    assert accepted.result.facts is not None
    assert accepted.result.facts.project_identity_status is IdentityStatus.UNVERIFIABLE


def test_replacement_and_insufficient_validation_status_are_rejected() -> None:
    plan, result, source_store = _standard_pair()
    cache = ComparisonCoreCache()
    key = ComparisonCoreCacheKey.from_plan(plan)
    with pytest.raises(ValueError, match="cannot exceed"):
        cache.put(
            key,
            result,
            source_store=source_store,
            cache_store=InMemoryArtifactStore(),
            validation_status=CacheTrustLevel.CONTENT_VERIFIED,
            input_validation_status=CacheTrustLevel.PROVISIONAL,
        )

    published = result
    assert published.facts is not None
    replacement = replace(
        published.facts,
        comparison_mode=ComparisonMode.DATASET_REPLACEMENT,
    )
    replacement_result = DetailedFactsResult(
        pair_id=published.pair_id,
        status=published.status,
        facts=replacement,
        records_closure=published.records_closure,
    )
    with pytest.raises(ValueError, match="DATASET_REPLACEMENT"):
        cache.put(
            key,
            replacement_result,
            source_store=source_store,
            cache_store=InMemoryArtifactStore(),
            validation_status=CacheTrustLevel.CONTENT_VERIFIED,
            input_validation_status=CacheTrustLevel.CONTENT_VERIFIED,
        )

    valid_cache_store = InMemoryArtifactStore()
    cache.put(
        key,
        result,
        source_store=source_store,
        cache_store=valid_cache_store,
        validation_status=CacheTrustLevel.CONTENT_VERIFIED,
        input_validation_status=CacheTrustLevel.CONTENT_VERIFIED,
    )
    replacement_binding = ComparisonCoreCacheRestoreBinding(
        pair_id="replacement-pair",
        before_snapshot_digest=plan.before.snapshot.snapshot_digest,
        current_snapshot_digest=plan.current.snapshot.snapshot_digest,
        artifact_scope=plan.artifact_scope,
        comparison_mode=ComparisonMode.DATASET_REPLACEMENT,
        identity_status=IdentityStatus.DIFFERENT_PROJECT,
        assessment_digest=plan.assessment_digest,
    )
    rejected = cache.restore(
        key,
        binding=replacement_binding,
        cache_store=valid_cache_store,
        operation_store=InMemoryArtifactStore(),
    )
    assert rejected.status is ComparisonCoreCacheLookupStatus.REJECTED
    assert rejected.result is None


def test_not_applicable_restore_rebinds_without_identity_digest() -> None:
    plan, result, source_store = _standard_pair()
    cache, _source, cache_store, key = _cache_pair(plan, result, source_store)
    binding = ComparisonCoreCacheRestoreBinding(
        pair_id="history-pair",
        before_snapshot_digest=plan.before.snapshot.snapshot_digest,
        current_snapshot_digest=plan.current.snapshot.snapshot_digest,
        artifact_scope=plan.artifact_scope,
        comparison_mode=ComparisonMode.DETAILED,
        identity_status=IdentityStatus.NOT_APPLICABLE,
        assessment_digest=None,
    )
    restored = cache.restore(
        key,
        binding=binding,
        cache_store=cache_store,
        operation_store=InMemoryArtifactStore(),
    )
    assert restored.status is ComparisonCoreCacheLookupStatus.HIT
    assert restored.result is not None and restored.result.facts is not None
    assert restored.result.facts.project_identity_status is IdentityStatus.NOT_APPLICABLE
    assert restored.result.facts.assessment_digest is None


def test_cache_key_and_value_do_not_store_flow_or_host_path_identity() -> None:
    plan, result, source_store = _standard_pair()
    cache, _source, cache_store, key = _cache_pair(plan, result, source_store)
    value = cache.lookup(key, cache_store=cache_store).value
    assert value is not None
    forbidden = {
        "pair_id",
        "operation_id",
        "workspace_id",
        "authorization",
        "submit_state",
        "host_path",
    }
    assert not forbidden.intersection({field.name for field in fields(key)})
    assert not forbidden.intersection({field.name for field in fields(value)})
    with pytest.raises(ValueError, match="host path"):
        replace(key, comparison_options=(("diagnostic", "/tmp/cache"),))
