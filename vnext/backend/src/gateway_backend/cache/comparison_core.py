"""Pair-level neutral comparison core cache.

The cache stores only canonical comparison facts and validated records closure metadata.  It never
stores flow identity, operation state, authorization, submit state or host paths.  A hit is useful
only after the caller supplies a fresh detailed binding; records are copied into an operation-local
artifact store before the restored result is returned.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import ArtifactRef, ArtifactStorePort, assert_no_host_path_identity
from gateway_backend.capabilities.comparison.artifacts import (
    RecordsPublicationContext,
    RecordsPublicationPolicy,
    RestoredRecordsClosure,
    open_records_closure,
    restore_records_closure,
)
from gateway_backend.capabilities.comparison.contracts import (
    BLANK_COMPARISON_CONTRACT_VERSION,
    COMPARISON_CONTRACT_VERSION,
    ORDERED_DIFF_CONTRACT_VERSION,
    ArtifactScope,
    ComparisonFacts,
    ComparisonMode,
    ComparisonOptions,
    ComparisonPlan,
    ComparisonRecordsClosure,
    DetailedFactsResult,
    IdentityStatus,
    PairResultStatus,
    UnverifiableContinuationBinding,
    ContinuationAction,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    COMPARISON_PROJECTION_CONTRACT_VERSION,
    CacheTrustLevel,
    SCALAR_ENCODING_VERSION,
)


COMPARISON_CORE_CACHE_CONTRACT_VERSION = "backend-vnext/comparison-core-cache/v1"
COMPARISON_CORE_CACHE_ALGORITHM_VERSION = "comparison-core-cache/v1"


class ComparisonCoreCachePolicy(StrEnum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


class ComparisonCoreCacheLookupStatus(StrEnum):
    HIT = "HIT"
    MISS = "MISS"
    DISABLED = "DISABLED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class ComparisonCoreCacheKey:
    """Canonical semantic address for one directed detailed comparison pair."""

    before_snapshot_digest: DigestRef
    current_snapshot_digest: DigestRef
    comparison_contract_version: str = COMPARISON_CONTRACT_VERSION
    projection_contract_version: str = COMPARISON_PROJECTION_CONTRACT_VERSION
    table_ruleset_version: tuple[tuple[str, str, str], ...] = ()
    scalar_encoding_version: int = SCALAR_ENCODING_VERSION
    ordered_contract_version: str = ORDERED_DIFF_CONTRACT_VERSION
    blank_contract_version: str = BLANK_COMPARISON_CONTRACT_VERSION
    requested_tables: tuple[str, ...] = ()
    comparison_options: ComparisonOptions = ()
    artifact_scope: ArtifactScope = ArtifactScope.ALL_CHANGES
    algorithm_version: str = COMPARISON_CORE_CACHE_ALGORITHM_VERSION
    contract_version: str = COMPARISON_CORE_CACHE_CONTRACT_VERSION

    def __post_init__(self) -> None:
        for label in ("before_snapshot_digest", "current_snapshot_digest"):
            if type(getattr(self, label)) is not DigestRef:
                raise ValueError(f"{label} must be DigestRef")
        for label in (
            "comparison_contract_version",
            "projection_contract_version",
            "ordered_contract_version",
            "blank_contract_version",
            "algorithm_version",
            "contract_version",
        ):
            value = getattr(self, label)
            if type(value) is not str or value == "":
                raise ValueError(f"{label} must be a non-empty string")
        if type(self.scalar_encoding_version) is not int or self.scalar_encoding_version < 1:
            raise ValueError("scalar_encoding_version must be a positive integer")
        if type(self.artifact_scope) is not ArtifactScope:
            raise ValueError("artifact_scope must be ArtifactScope")
        if type(self.requested_tables) is not tuple or any(
            type(item) is not str or item == "" for item in self.requested_tables
        ):
            raise ValueError("requested_tables must contain non-empty strings")
        if len(set(self.requested_tables)) != len(self.requested_tables):
            raise ValueError("requested_tables must not repeat table names")
        if self.requested_tables != tuple(sorted(self.requested_tables)):
            raise ValueError("requested_tables must use canonical order")
        if type(self.table_ruleset_version) is not tuple:
            raise ValueError("table_ruleset_version must be a tuple")
        for item in self.table_ruleset_version:
            if (
                type(item) is not tuple
                or len(item) != 3
                or any(type(part) is not str or part == "" for part in item)
            ):
                raise ValueError("table_ruleset_version entries must be non-empty strings")
        if tuple(item[0] for item in self.table_ruleset_version) != self.requested_tables:
            raise ValueError("table rules and requested tables must have the same canonical scope")
        _validate_options(self.comparison_options)
        assert_no_host_path_identity(self._payload())

    @classmethod
    def from_plan(cls, plan: ComparisonPlan) -> ComparisonCoreCacheKey:
        if type(plan) is not ComparisonPlan:
            raise TypeError("plan must be ComparisonPlan")
        versions = dict(plan.contract_versions)
        policies = tuple(
            (
                task.table_name,
                task.policy.policy_version if task.policy is not None else "comparison-table-policy/v1",
                _table_policy_fingerprint(task.policy),
            )
            for task in plan.tasks
        )
        return cls(
            before_snapshot_digest=plan.before.snapshot.snapshot_digest,
            current_snapshot_digest=plan.current.snapshot.snapshot_digest,
            comparison_contract_version=str(
                versions.get("comparison_contract_version", COMPARISON_CONTRACT_VERSION)
            ),
            projection_contract_version=str(
                versions.get("projection_contract_version", COMPARISON_PROJECTION_CONTRACT_VERSION)
            ),
            table_ruleset_version=policies,
            scalar_encoding_version=SCALAR_ENCODING_VERSION,
            requested_tables=tuple(task.table_name for task in plan.tasks),
            comparison_options=plan.comparison_options,
            artifact_scope=plan.artifact_scope,
        )

    @property
    def cache_key_digest(self) -> DigestRef:
        return raw_blob_digest(canonicalize_json_value(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "cache_contract_version": self.contract_version,
            "before_snapshot_digest": self.before_snapshot_digest.value,
            "current_snapshot_digest": self.current_snapshot_digest.value,
            "comparison_contract_version": self.comparison_contract_version,
            "projection_contract_version": self.projection_contract_version,
            "table_ruleset_version": [list(item) for item in self.table_ruleset_version],
            "scalar_encoding_version": self.scalar_encoding_version,
            "ordered_contract_version": self.ordered_contract_version,
            "blank_contract_version": self.blank_contract_version,
            "requested_tables": list(self.requested_tables),
            "comparison_options": [list(item) for item in self.comparison_options],
            "artifact_scope": self.artifact_scope.value,
            "algorithm_version": self.algorithm_version,
        }


@dataclass(frozen=True, slots=True)
class ComparisonCoreCacheValue:
    """Neutral facts and cache-local closure; no flow or operation identity."""

    facts: ComparisonFacts
    records_closure: ComparisonRecordsClosure | None
    closure_ref: ArtifactRef | None
    validation_status: CacheTrustLevel

    def __post_init__(self) -> None:
        if type(self.facts) is not ComparisonFacts:
            raise ValueError("facts must be ComparisonFacts")
        if self.facts.comparison_mode is not ComparisonMode.DETAILED:
            raise ValueError("comparison core cache only accepts DETAILED facts")
        if self.records_closure is not None and type(self.records_closure) is not ComparisonRecordsClosure:
            raise ValueError("records_closure must be ComparisonRecordsClosure or None")
        if self.closure_ref is not None and type(self.closure_ref) is not ArtifactRef:
            raise ValueError("closure_ref must be ArtifactRef or None")
        if type(self.validation_status) is not CacheTrustLevel:
            raise ValueError("validation_status must be CacheTrustLevel")
        if (self.records_closure is None) != (self.closure_ref is None):
            raise ValueError("closure and closure_ref must be present together")
        if (self.facts.records_ref is None) != (self.closure_ref is None):
            raise ValueError("facts records_ref must match closure presence")
        if self.records_closure is not None:
            assert self.closure_ref is not None
            if self.facts.records_ref != self.closure_ref:
                raise ValueError("facts records_ref must identify the cached closure")
            if self.records_closure.comparison_digest != self.facts.comparison_digest:
                raise ValueError("closure comparison digest must match facts")
            if self.records_closure.facts_core_digest != self.facts.facts_core_digest:
                raise ValueError("closure facts core digest must match facts")


@dataclass(frozen=True, slots=True)
class ComparisonCoreCacheLookup:
    status: ComparisonCoreCacheLookupStatus
    key_digest: DigestRef
    value: ComparisonCoreCacheValue | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.status) is not ComparisonCoreCacheLookupStatus:
            raise ValueError("status must be ComparisonCoreCacheLookupStatus")
        if type(self.key_digest) is not DigestRef:
            raise ValueError("key_digest must be DigestRef")
        if self.value is not None and type(self.value) is not ComparisonCoreCacheValue:
            raise ValueError("value must be ComparisonCoreCacheValue or None")
        _validate_diagnostics(self.diagnostics)
        if self.status is ComparisonCoreCacheLookupStatus.HIT and self.value is None:
            raise ValueError("cache hit requires a value")
        if self.status is not ComparisonCoreCacheLookupStatus.HIT and self.value is not None:
            raise ValueError("non-hit cache result must not expose a value")


@dataclass(frozen=True, slots=True)
class ComparisonCoreCacheRestoreBinding:
    """Fresh detailed binding supplied by the trusted flow/orchestrator."""

    pair_id: str
    before_snapshot_digest: DigestRef
    current_snapshot_digest: DigestRef
    artifact_scope: ArtifactScope
    comparison_mode: ComparisonMode
    identity_status: IdentityStatus
    assessment_digest: DigestRef | None
    continuation_binding: UnverifiableContinuationBinding | None = None
    continuation_policy_version: str | None = None
    policy_revalidated: bool = False

    def __post_init__(self) -> None:
        if type(self.pair_id) is not str or self.pair_id == "":
            raise ValueError("pair_id must be a non-empty string")
        if any(token in self.pair_id for token in ("/", "\\", "\x00")):
            raise ValueError("pair_id must not be a path-shaped identity")
        for label in ("before_snapshot_digest", "current_snapshot_digest"):
            if type(getattr(self, label)) is not DigestRef:
                raise ValueError(f"{label} must be DigestRef")
        if type(self.artifact_scope) is not ArtifactScope:
            raise ValueError("artifact_scope must be ArtifactScope")
        if type(self.comparison_mode) is not ComparisonMode:
            raise ValueError("comparison_mode must be ComparisonMode")
        if type(self.identity_status) is not IdentityStatus:
            raise ValueError("identity_status must be IdentityStatus")
        if self.assessment_digest is not None and type(self.assessment_digest) is not DigestRef:
            raise ValueError("assessment_digest must be DigestRef or None")
        if self.continuation_binding is not None and type(
            self.continuation_binding
        ) is not UnverifiableContinuationBinding:
            raise ValueError("continuation_binding must be UnverifiableContinuationBinding or None")
        if self.continuation_policy_version is not None and (
            type(self.continuation_policy_version) is not str or self.continuation_policy_version == ""
        ):
            raise ValueError("continuation_policy_version must be a non-empty string or None")
        if type(self.policy_revalidated) is not bool:
            raise ValueError("policy_revalidated must be bool")


@dataclass(frozen=True, slots=True)
class ComparisonCoreCacheRestoreResult:
    status: ComparisonCoreCacheLookupStatus
    key_digest: DigestRef
    result: DetailedFactsResult | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.status) is not ComparisonCoreCacheLookupStatus:
            raise ValueError("status must be ComparisonCoreCacheLookupStatus")
        if type(self.key_digest) is not DigestRef:
            raise ValueError("key_digest must be DigestRef")
        if self.result is not None and type(self.result) is not DetailedFactsResult:
            raise ValueError("result must be DetailedFactsResult or None")
        _validate_diagnostics(self.diagnostics)
        if self.status is ComparisonCoreCacheLookupStatus.HIT and self.result is None:
            raise ValueError("restored cache hit requires a result")
        if self.status is not ComparisonCoreCacheLookupStatus.HIT and self.result is not None:
            raise ValueError("non-hit restore must not expose a result")


class ComparisonCoreCache:
    """Hermetic in-process cache with fail-closed content validation."""

    def __init__(self) -> None:
        self._entries: dict[ComparisonCoreCacheKey, ComparisonCoreCacheValue] = {}

    def put(
        self,
        key: ComparisonCoreCacheKey,
        result: DetailedFactsResult,
        *,
        source_store: ArtifactStorePort,
        cache_store: ArtifactStorePort,
        validation_status: CacheTrustLevel,
        input_validation_status: CacheTrustLevel,
        policy: RecordsPublicationPolicy | None = None,
        context: RecordsPublicationContext | None = None,
    ) -> ComparisonCoreCacheValue:
        if type(key) is not ComparisonCoreCacheKey:
            raise TypeError("key must be ComparisonCoreCacheKey")
        if type(result) is not DetailedFactsResult:
            raise TypeError("result must be DetailedFactsResult")
        if type(validation_status) is not CacheTrustLevel:
            raise TypeError("validation_status must be CacheTrustLevel")
        if type(input_validation_status) is not CacheTrustLevel:
            raise TypeError("input_validation_status must be CacheTrustLevel")
        if _trust_rank(validation_status) > _trust_rank(input_validation_status):
            raise ValueError("cache validation status cannot exceed input validation status")
        facts = result.facts
        if facts is None:
            raise ValueError("detailed result must contain facts")
        if facts.comparison_mode is not ComparisonMode.DETAILED:
            raise ValueError("DATASET_REPLACEMENT cannot enter the detailed core cache")
        if (facts.records_ref is None) != (result.records_closure is None):
            raise ValueError("result facts and records closure must agree")

        cached_closure: RestoredRecordsClosure | None = None
        if facts.records_ref is not None:
            if result.records_closure is None:
                raise ValueError("records_ref requires records_closure")
            verified = open_records_closure(source_store, facts.records_ref, policy=policy)
            if verified != result.records_closure:
                raise ValueError("result records closure is not source-store verified")
            cached_closure = restore_records_closure(
                source_store,
                cache_store,
                facts.records_ref,
                policy=policy,
                context=context or RecordsPublicationContext(artifact_id_prefix="comparison-cache"),
            )

        cached_facts = replace(
            facts,
            records_ref=None if cached_closure is None else cached_closure.closure_ref,
        )
        value = ComparisonCoreCacheValue(
            facts=cached_facts,
            records_closure=None if cached_closure is None else cached_closure.closure,
            closure_ref=None if cached_closure is None else cached_closure.closure_ref,
            validation_status=validation_status,
        )
        self._entries[key] = value
        return value

    def lookup(
        self,
        key: ComparisonCoreCacheKey,
        *,
        cache_store: ArtifactStorePort,
        policy: ComparisonCoreCachePolicy = ComparisonCoreCachePolicy.ENABLED,
        minimum_validation_status: CacheTrustLevel = CacheTrustLevel.PROVISIONAL,
        records_policy: RecordsPublicationPolicy | None = None,
    ) -> ComparisonCoreCacheLookup:
        if type(key) is not ComparisonCoreCacheKey:
            raise TypeError("key must be ComparisonCoreCacheKey")
        if type(policy) is not ComparisonCoreCachePolicy:
            raise TypeError("policy must be ComparisonCoreCachePolicy")
        if type(minimum_validation_status) is not CacheTrustLevel:
            raise TypeError("minimum_validation_status must be CacheTrustLevel")
        key_digest = key.cache_key_digest
        if policy is ComparisonCoreCachePolicy.DISABLED:
            return _lookup(key_digest, ComparisonCoreCacheLookupStatus.DISABLED, "COMPARISON_CACHE_DISABLED")
        value = self._entries.get(key)
        if value is None:
            return _lookup(key_digest, ComparisonCoreCacheLookupStatus.MISS, "COMPARISON_CACHE_MISS")
        if _trust_rank(value.validation_status) < _trust_rank(minimum_validation_status):
            return _lookup(
                key_digest,
                ComparisonCoreCacheLookupStatus.REJECTED,
                "COMPARISON_CACHE_VALIDATION_STATUS_REJECTED",
            )
        try:
            _validate_cached_value(key, value, cache_store, records_policy)
        except Exception:
            return _lookup(
                key_digest,
                ComparisonCoreCacheLookupStatus.REJECTED,
                "COMPARISON_CACHE_ENTRY_INVALID",
            )
        return ComparisonCoreCacheLookup(
            status=ComparisonCoreCacheLookupStatus.HIT,
            key_digest=key_digest,
            value=value,
        )

    def restore(
        self,
        key: ComparisonCoreCacheKey,
        *,
        binding: ComparisonCoreCacheRestoreBinding,
        cache_store: ArtifactStorePort,
        operation_store: ArtifactStorePort,
        policy: ComparisonCoreCachePolicy = ComparisonCoreCachePolicy.ENABLED,
        minimum_validation_status: CacheTrustLevel = CacheTrustLevel.PROVISIONAL,
        records_policy: RecordsPublicationPolicy | None = None,
        context: RecordsPublicationContext | None = None,
    ) -> ComparisonCoreCacheRestoreResult:
        if type(binding) is not ComparisonCoreCacheRestoreBinding:
            raise TypeError("binding must be ComparisonCoreCacheRestoreBinding")
        hit = self.lookup(
            key,
            cache_store=cache_store,
            policy=policy,
            minimum_validation_status=minimum_validation_status,
            records_policy=records_policy,
        )
        if hit.status is not ComparisonCoreCacheLookupStatus.HIT:
            return ComparisonCoreCacheRestoreResult(
                status=hit.status,
                key_digest=hit.key_digest,
                diagnostics=hit.diagnostics,
            )
        assert hit.value is not None
        try:
            _validate_restore_binding(key, hit.value.facts, binding)
            restored_closure: RestoredRecordsClosure | None = None
            if hit.value.closure_ref is not None:
                restored_closure = restore_records_closure(
                    cache_store,
                    operation_store,
                    hit.value.closure_ref,
                    policy=records_policy,
                    context=context or RecordsPublicationContext(
                        artifact_id_prefix="comparison-operation"
                    ),
                )
            facts = replace(
                hit.value.facts,
                comparison_mode=binding.comparison_mode,
                project_identity_status=binding.identity_status,
                assessment_digest=binding.assessment_digest,
                records_ref=(
                    None if restored_closure is None else restored_closure.closure_ref
                ),
            )
            status = facts.summary.status
            if binding.identity_status is IdentityStatus.UNVERIFIABLE:
                status = PairResultStatus.DEGRADED
            result = DetailedFactsResult(
                pair_id=binding.pair_id,
                status=status,
                facts=facts,
                records_closure=(
                    None if restored_closure is None else restored_closure.closure
                ),
                diagnostics=facts.diagnostics,
            )
            return ComparisonCoreCacheRestoreResult(
                status=ComparisonCoreCacheLookupStatus.HIT,
                key_digest=hit.key_digest,
                result=result,
            )
        except Exception:
            return ComparisonCoreCacheRestoreResult(
                status=ComparisonCoreCacheLookupStatus.REJECTED,
                key_digest=hit.key_digest,
                diagnostics=("COMPARISON_CACHE_RESTORE_REJECTED",),
            )


def _validate_cached_value(
    key: ComparisonCoreCacheKey,
    value: ComparisonCoreCacheValue,
    cache_store: ArtifactStorePort,
    policy: RecordsPublicationPolicy | None,
) -> None:
    facts = value.facts
    if facts.before_snapshot_digest != key.before_snapshot_digest:
        raise ValueError("cached before snapshot digest does not match key")
    if facts.current_snapshot_digest != key.current_snapshot_digest:
        raise ValueError("cached current snapshot digest does not match key")
    if facts.comparison_contract_version != key.comparison_contract_version:
        raise ValueError("cached comparison contract does not match key")
    if facts.projection_contract_version != key.projection_contract_version:
        raise ValueError("cached projection contract does not match key")
    if facts.scalar_encoding_version != key.scalar_encoding_version:
        raise ValueError("cached scalar encoding does not match key")
    if value.closure_ref is None:
        if facts.records_ref is not None or value.records_closure is not None:
            raise ValueError("cached closure state is inconsistent")
        return
    if facts.records_ref != value.closure_ref or value.records_closure is None:
        raise ValueError("cached facts and closure refs are inconsistent")
    reopened = open_records_closure(cache_store, value.closure_ref, policy=policy)
    if reopened != value.records_closure:
        raise ValueError("cached closure changed in storage")
    if reopened.comparison_digest != facts.comparison_digest:
        raise ValueError("cached closure comparison digest mismatch")
    if reopened.facts_core_digest != facts.facts_core_digest:
        raise ValueError("cached closure facts core digest mismatch")


def _validate_restore_binding(
    key: ComparisonCoreCacheKey,
    facts: ComparisonFacts,
    binding: ComparisonCoreCacheRestoreBinding,
) -> None:
    if binding.comparison_mode is not ComparisonMode.DETAILED:
        raise ValueError("comparison core cache cannot restore DATASET_REPLACEMENT")
    if binding.before_snapshot_digest != key.before_snapshot_digest:
        raise ValueError("restore before snapshot digest mismatch")
    if binding.current_snapshot_digest != key.current_snapshot_digest:
        raise ValueError("restore current snapshot digest mismatch")
    if binding.artifact_scope is not key.artifact_scope:
        raise ValueError("restore artifact scope mismatch")
    if binding.identity_status is IdentityStatus.DIFFERENT_PROJECT:
        raise ValueError("replacement identity cannot restore detailed core")
    if binding.identity_status is IdentityStatus.NOT_APPLICABLE:
        if binding.assessment_digest is not None or binding.continuation_binding is not None:
            raise ValueError("NOT_APPLICABLE restore forbids identity and continuation binding")
        return
    if binding.assessment_digest is None:
        raise ValueError("applicable restore requires assessment_digest")
    if binding.identity_status is IdentityStatus.UNVERIFIABLE:
        continuation = binding.continuation_binding
        if continuation is None:
            raise ValueError("UNVERIFIABLE restore requires continuation binding")
        if continuation.action is not ContinuationAction.ALLOW_DETAILED_ON_UNVERIFIABLE:
            raise ValueError("invalid continuation action")
        if continuation.pair_id != binding.pair_id:
            raise ValueError("continuation pair mismatch")
        if continuation.before_snapshot_digest != binding.before_snapshot_digest:
            raise ValueError("continuation before snapshot mismatch")
        if continuation.current_snapshot_digest != binding.current_snapshot_digest:
            raise ValueError("continuation current snapshot mismatch")
        if continuation.assessment_digest != binding.assessment_digest:
            raise ValueError("continuation assessment mismatch")
        if continuation.assessment_set_digest is None:
            raise ValueError("continuation assessment set is required")
        if not binding.policy_revalidated:
            raise ValueError("continuation policy was not revalidated")
        if binding.continuation_policy_version != continuation.policy_version:
            raise ValueError("continuation policy version mismatch")

    if facts.comparison_mode is not ComparisonMode.DETAILED:
        raise ValueError("cached facts are not detailed")


def _table_policy_fingerprint(policy: object) -> str:
    if policy is None:
        return raw_blob_digest(canonicalize_json_value({"policy": None})).value
    table_name = getattr(policy, "table_name")
    ignored_columns = getattr(policy, "ignored_columns")
    keyless_policy = getattr(getattr(policy, "keyless_policy"), "value")
    policy_version = getattr(policy, "policy_version")
    ordered = getattr(policy, "ordered_policy")
    ordered_payload: object = None
    if ordered is not None:
        ordered_payload = {
            "policy_id": ordered.policy_id,
            "policy_version": ordered.policy_version,
            "order_key": list(ordered.order_key),
            "row_identity_key": None
            if ordered.row_identity_key is None
            else list(ordered.row_identity_key),
            "stable_key_candidates": list(ordered.stable_key_candidates),
            "value_columns": list(ordered.value_columns),
            "ignored_columns": list(ordered.ignored_columns),
            "blank_row_policy": ordered.blank_row_policy.value,
            "move_policy": ordered.move_policy,
            "ambiguity_policy": ordered.ambiguity_policy,
            "tail_change_policy": ordered.tail_change_policy,
            "table_processing_mode_policy": ordered.table_processing_mode_policy,
            "policy_digest": None
            if ordered.policy_digest is None
            else ordered.policy_digest.value,
        }
    payload = {
        "table_name": table_name,
        "ignored_columns": list(ignored_columns),
        "keyless_policy": keyless_policy,
        "policy_version": policy_version,
        "ordered_policy": ordered_payload,
    }
    return raw_blob_digest(canonicalize_json_value(payload)).value


def _validate_options(options: ComparisonOptions) -> None:
    if type(options) is not tuple:
        raise ValueError("comparison_options must be a tuple")
    keys: set[str] = set()
    for item in options:
        if type(item) is not tuple or len(item) != 2:
            raise ValueError("comparison_options must contain key/value pairs")
        key, value = item
        if type(key) is not str or key == "" or key in keys:
            raise ValueError("comparison_options keys must be unique non-empty strings")
        if value is not None and type(value) not in {str, int, bool}:
            raise ValueError("comparison_options values must be scalar JSON values")
        keys.add(key)


def _trust_rank(value: CacheTrustLevel) -> int:
    return {
        CacheTrustLevel.PROVISIONAL: 0,
        CacheTrustLevel.CONTENT_VERIFIED: 1,
        CacheTrustLevel.COMMIT_VALIDATED: 2,
    }[value]


def _lookup(
    key_digest: DigestRef,
    status: ComparisonCoreCacheLookupStatus,
    diagnostic: str,
) -> ComparisonCoreCacheLookup:
    return ComparisonCoreCacheLookup(
        status=status,
        key_digest=key_digest,
        diagnostics=(diagnostic,),
    )


def _validate_diagnostics(diagnostics: tuple[str, ...]) -> None:
    if type(diagnostics) is not tuple or any(type(item) is not str or item == "" for item in diagnostics):
        raise ValueError("diagnostics must contain non-empty strings")
