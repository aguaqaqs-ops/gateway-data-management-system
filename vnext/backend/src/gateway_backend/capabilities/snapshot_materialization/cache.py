"""In-process SnapshotTableArtifact cache with explicit trust promotion."""

from __future__ import annotations

from dataclasses import dataclass

from gateway_backend.artifacts import ArtifactStorePort

from gateway_backend.capabilities.snapshot_materialization.artifact import (
    ArtifactPublishError,
    artifact_error_diagnostic,
    validate_snapshot_table_artifact,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ArtifactSourceBinding,
    CacheAuthorityInput,
    CacheLookupPolicy,
    CacheLookupStatus,
    CacheRevalidation,
    CacheTrustLevel,
    DiagnosticSeverity,
    MaterializationDiagnostic,
    MaterializationDiagnosticCode,
    SnapshotTableArtifact,
    SnapshotTableArtifactCacheKey,
    SnapshotTableArtifactCacheResult,
    ValidationStatusPolicy,
)


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    key: SnapshotTableArtifactCacheKey
    artifact: SnapshotTableArtifact
    trust: CacheTrustLevel
    binding: ArtifactSourceBinding


class SnapshotTableArtifactCache:
    def __init__(self) -> None:
        self._entries: dict[SnapshotTableArtifactCacheKey, _CacheEntry] = {}

    def put(
        self,
        key: SnapshotTableArtifactCacheKey,
        artifact: SnapshotTableArtifact,
        *,
        trust: CacheTrustLevel,
        binding: ArtifactSourceBinding,
        policy: ValidationStatusPolicy,
        store: ArtifactStorePort,
    ) -> None:
        if type(key) is not SnapshotTableArtifactCacheKey:
            raise ValueError("key must be SnapshotTableArtifactCacheKey")
        if type(artifact) is not SnapshotTableArtifact:
            raise ValueError("artifact must be SnapshotTableArtifact")
        if type(trust) is not CacheTrustLevel:
            raise ValueError("trust must be CacheTrustLevel")
        if type(binding) is not ArtifactSourceBinding:
            raise ValueError("binding must be ArtifactSourceBinding")
        if type(policy) is not ValidationStatusPolicy:
            raise ValueError("policy must be ValidationStatusPolicy")
        if policy is ValidationStatusPolicy.NO_CACHE_WRITE:
            raise ValueError("NO_CACHE_WRITE forbids cache put")
        if trust is CacheTrustLevel.COMMIT_VALIDATED:
            raise ValueError("COMMIT_VALIDATED requires promote(), not put()")
        if (
            policy is ValidationStatusPolicy.PROVISIONAL_ONLY
            and trust is not CacheTrustLevel.PROVISIONAL
        ):
            raise ValueError("PROVISIONAL_ONLY only accepts PROVISIONAL trust")
        if key.repository_id != binding.repository_id:
            raise ValueError("cache key repository_id must match the source binding")
        validate_snapshot_table_artifact(store, artifact)
        if artifact.manifest.snapshot_digest != binding.snapshot_digest:
            raise ValueError("artifact snapshot_digest must match the source binding")
        if artifact.manifest.descriptor != binding.descriptor:
            raise ValueError("artifact descriptor must match the source binding")
        self._entries[key] = _CacheEntry(
            key=key,
            artifact=artifact,
            trust=trust,
            binding=binding,
        )

    def lookup(
        self,
        key: SnapshotTableArtifactCacheKey,
        *,
        policy: CacheLookupPolicy,
        store: ArtifactStorePort,
        revalidation: CacheRevalidation | None = None,
    ) -> SnapshotTableArtifactCacheResult:
        entry = self._entries.get(key)
        if entry is None:
            return SnapshotTableArtifactCacheResult(status=CacheLookupStatus.MISS)
        if policy is CacheLookupPolicy.READ_COMMIT_VALIDATED_ONLY:
            if entry.trust is not CacheTrustLevel.COMMIT_VALIDATED:
                return _rejected(
                    MaterializationDiagnosticCode.CACHE_TRUST_POLICY_REJECTED,
                    "READ_COMMIT_VALIDATED_ONLY rejects non-COMMIT_VALIDATED entries",
                )
        needs_revalidation = (
            entry.trust is CacheTrustLevel.PROVISIONAL
            or policy
            in {
                CacheLookupPolicy.READ_PROVISIONAL_WITH_REVALIDATION,
                CacheLookupPolicy.READ_ANY_WITH_REVALIDATION,
            }
        )
        if needs_revalidation and entry.trust is CacheTrustLevel.PROVISIONAL:
            if revalidation is None:
                return _rejected(
                    MaterializationDiagnosticCode.CACHE_PROVISIONAL_REQUIRES_REVALIDATION,
                    "PROVISIONAL cache candidate requires source revalidation",
                )
        if revalidation is not None:
            mismatch = _revalidation_mismatch(entry, revalidation)
            if mismatch is not None:
                return mismatch
        try:
            validate_snapshot_table_artifact(store, entry.artifact)
        except ArtifactPublishError as exc:
            return SnapshotTableArtifactCacheResult(
                status=CacheLookupStatus.REJECTED,
                diagnostics=(artifact_error_diagnostic(exc),),
            )
        return SnapshotTableArtifactCacheResult(
            status=CacheLookupStatus.HIT,
            trust=entry.trust,
            artifact=entry.artifact,
        )

    def promote(
        self,
        key: SnapshotTableArtifactCacheKey,
        authority: CacheAuthorityInput,
    ) -> SnapshotTableArtifactCacheResult:
        entry = self._entries.get(key)
        if entry is None:
            return SnapshotTableArtifactCacheResult(status=CacheLookupStatus.MISS)
        if type(authority) is not CacheAuthorityInput:
            return _rejected(
                MaterializationDiagnosticCode.CACHE_PROMOTION_REQUIRES_AUTHORITY,
                "promotion requires CacheAuthorityInput",
            )
        if entry.binding.repository_id is None or entry.binding.resolved_commit_hash is None:
            return _rejected(
                MaterializationDiagnosticCode.CACHE_PROMOTION_REQUIRES_AUTHORITY,
                "promotion requires a repository source binding",
            )
        if (
            authority.repository_id != entry.binding.repository_id
            or authority.resolved_commit_hash != entry.binding.resolved_commit_hash
            or authority.snapshot_digest != entry.binding.snapshot_digest
        ):
            return _rejected(
                MaterializationDiagnosticCode.CACHE_PROMOTION_REQUIRES_AUTHORITY,
                "authority input does not match the cached source binding",
            )
        promoted = _CacheEntry(
            key=entry.key,
            artifact=entry.artifact,
            trust=CacheTrustLevel.COMMIT_VALIDATED,
            binding=entry.binding,
        )
        self._entries[key] = promoted
        return SnapshotTableArtifactCacheResult(
            status=CacheLookupStatus.HIT,
            trust=promoted.trust,
            artifact=promoted.artifact,
        )

    def delete(self, key: SnapshotTableArtifactCacheKey) -> None:
        self._entries.pop(key, None)


def _revalidation_mismatch(
    entry: _CacheEntry,
    revalidation: CacheRevalidation,
) -> SnapshotTableArtifactCacheResult | None:
    if revalidation.snapshot_digest != entry.binding.snapshot_digest:
        return _rejected(
            MaterializationDiagnosticCode.ARTIFACT_DIGEST_MISMATCH,
            "revalidation snapshot_digest does not match the cache binding",
        )
    if revalidation.descriptor != entry.binding.descriptor:
        return _rejected(
            MaterializationDiagnosticCode.ARTIFACT_SCHEMA_MISMATCH,
            "revalidation descriptor does not match the cache binding",
        )
    if revalidation.descriptor.raw_content_digest != entry.artifact.manifest.descriptor.raw_content_digest:
        return _rejected(
            MaterializationDiagnosticCode.ARTIFACT_DIGEST_MISMATCH,
            "revalidation raw_content_digest does not match the artifact",
        )
    return None


def _rejected(
    code: MaterializationDiagnosticCode,
    message: str,
) -> SnapshotTableArtifactCacheResult:
    return SnapshotTableArtifactCacheResult(
        status=CacheLookupStatus.REJECTED,
        diagnostics=(
            MaterializationDiagnostic(
                code=code,
                severity=DiagnosticSeverity.ERROR,
                message=message,
            ),
        ),
    )
