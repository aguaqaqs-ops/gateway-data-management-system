from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import json
from pathlib import Path
import pickle
import shutil
from typing import Protocol, runtime_checkable

from ..artifacts import ArtifactManifest, LocalArtifactStore, RecordsArtifact, RecordsArtifactManifest
from ..capabilities.comparison.models import (
    ComparisonComputeInput,
    ComparisonFacts,
    ComparisonOptions,
    ComparisonRecordsClosure,
)
from ..contracts.cache import (
    CacheLookupPolicy,
    CacheValidationStatus,
    ComparisonCoreCacheEntryPayload,
    ComparisonCoreCacheKeyPayload,
)
from ..core.digests import DigestRef
from ..core.identifiers import canonical_identifier


COMPARISON_CORE_CACHE_CONTRACT_VERSION = "backend-vnext/comparison-core-cache/v1"
COMPARISON_CORE_CACHE_NAMESPACE = "comparison-core"
COMPARISON_CORE_CACHE_ARTIFACT_KIND = "comparison-core-cache"
COMPARISON_CORE_CACHE_MANIFEST_FILE_NAME = "manifest.json"
COMPARISON_CORE_CACHE_ENTRY_FILE_NAME = "entry.pkl"
COMPARISON_CORE_CACHE_REGISTRY_FILE_NAME = "registry.json"
COMPARISON_CORE_CACHE_REGISTRY_SCHEMA_VERSION = "backend-vnext/comparison-core-cache-registry/v1"
COMPARISON_CORE_CACHE_PROVENANCE_PREVIEW_COMPLETION = "PREVIEW_COMPLETION"
COMPARISON_CORE_CACHE_PROVENANCE_SUBMIT_FINALIZE_PROMOTION = "SUBMIT_FINALIZE_PROMOTION"
COMPARISON_CORE_CACHE_PROVENANCE_HISTORY_COMPARE_COMPUTE = "HISTORY_COMPARE_COMPUTE"
COMPARISON_CORE_CACHE_POLICY_MISS_REASON = "VALIDATION_STATUS_POLICY_MISS"


@dataclass(frozen=True, slots=True)
class ComparisonCoreCacheKey:
    before_snapshot_digest: DigestRef | str
    current_snapshot_digest: DigestRef | str
    comparison_contract_version: str
    projection_contract_version: str
    scalar_encoding_version: str
    table_ruleset_digest: DigestRef | str
    requested_tables: tuple[str, ...] = field(default_factory=tuple)
    comparison_options: ComparisonOptions = field(default_factory=ComparisonOptions)
    table_aliases: tuple[tuple[str, str, str], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for field_name in (
            "comparison_contract_version",
            "projection_contract_version",
            "scalar_encoding_version",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        object.__setattr__(self, "before_snapshot_digest", DigestRef.parse(str(self.before_snapshot_digest)))
        object.__setattr__(self, "current_snapshot_digest", DigestRef.parse(str(self.current_snapshot_digest)))
        object.__setattr__(self, "table_ruleset_digest", DigestRef.parse(str(self.table_ruleset_digest)))
        if not isinstance(self.requested_tables, tuple):
            object.__setattr__(self, "requested_tables", tuple(self.requested_tables))
        object.__setattr__(
            self,
            "requested_tables",
            tuple(
                canonical_identifier(table_name)
                for table_name in self.requested_tables
                if canonical_identifier(table_name)
            ),
        )
        if not isinstance(self.comparison_options, ComparisonOptions):
            raise TypeError("comparison_options must be a ComparisonOptions")
        if not isinstance(self.table_aliases, tuple):
            object.__setattr__(self, "table_aliases", tuple(self.table_aliases))
        object.__setattr__(
            self,
            "table_aliases",
            tuple(
                sorted(
                    (_table_alias_payload(alias) for alias in self.table_aliases),
                )
            ),
        )

    def payload_for_digest(self) -> dict[str, object]:
        return self.to_contract_payload().to_payload()

    def to_contract_payload(self) -> ComparisonCoreCacheKeyPayload:
        return ComparisonCoreCacheKeyPayload(
            before_snapshot_digest=self.before_snapshot_digest,
            current_snapshot_digest=self.current_snapshot_digest,
            comparison_contract_version=self.comparison_contract_version,
            projection_contract_version=self.projection_contract_version,
            scalar_encoding_version=self.scalar_encoding_version,
            table_ruleset_digest=self.table_ruleset_digest,
            requested_tables=self.requested_tables,
            comparison_options=_comparison_options_payload(self.comparison_options),
            table_aliases=tuple(
                {
                    "alias_scope": alias_scope,
                    "logical_table_name": logical,
                    "canonical_table_name": canonical,
                }
                for alias_scope, logical, canonical in self.table_aliases
            ),
        )

    @property
    def cache_key_digest(self) -> DigestRef:
        return DigestRef.from_payload(self.payload_for_digest())


def build_comparison_core_cache_key(
    *,
    comparison_input: ComparisonComputeInput,
    table_ruleset_digest: DigestRef | str,
) -> ComparisonCoreCacheKey:
    return ComparisonCoreCacheKey(
        before_snapshot_digest=_comparison_input_identity_digest(comparison_input.before),
        current_snapshot_digest=_comparison_input_identity_digest(comparison_input.current),
        comparison_contract_version=comparison_input.comparison_contract_version,
        projection_contract_version=comparison_input.projection_contract_version,
        scalar_encoding_version=comparison_input.scalar_encoding_version or "",
        table_ruleset_digest=table_ruleset_digest,
        requested_tables=comparison_input.requested_tables,
        comparison_options=comparison_input.comparison_options,
        table_aliases=tuple(
            alias.payload_for_digest()
            for alias in getattr(comparison_input, "table_aliases", ())
        ),
    )


@dataclass(frozen=True, slots=True)
class ComparisonCoreCacheEntry:
    facts: ComparisonFacts
    records_closure: ComparisonRecordsClosure
    records_artifacts: tuple[RecordsArtifact, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.facts, ComparisonFacts):
            raise TypeError("facts must be a ComparisonFacts")
        if not isinstance(self.records_closure, ComparisonRecordsClosure):
            raise TypeError("records_closure must be a ComparisonRecordsClosure")
        if not isinstance(self.records_artifacts, tuple):
            object.__setattr__(self, "records_artifacts", tuple(self.records_artifacts))
        normalized_records_artifacts: list[RecordsArtifact] = []
        for records_artifact in self.records_artifacts:
            if not isinstance(records_artifact, RecordsArtifact):
                raise TypeError("records_artifacts must contain RecordsArtifact values")
            normalized_records_artifacts.append(records_artifact)
        object.__setattr__(self, "records_artifacts", tuple(normalized_records_artifacts))

    def to_contract_payload(
        self,
        *,
        validation_status: CacheValidationStatus | str = CacheValidationStatus.PROVISIONAL,
    ) -> ComparisonCoreCacheEntryPayload:
        return ComparisonCoreCacheEntryPayload(
            comparison_digest=self.facts.comparison_digest,
            facts_core_digest=self.records_closure.facts_core_digest,
            records_artifact_count=len(self.records_artifacts),
            records_table_names=tuple(
                records_artifact.manifest.table_name
                for records_artifact in self.records_artifacts
            ),
            validation_status=validation_status,
        )


@dataclass(frozen=True, slots=True)
class ComparisonCoreCacheLookup:
    value: ComparisonCoreCacheEntry | None
    cache_key_digest: DigestRef | str
    validation_status: CacheValidationStatus | str | None = None
    miss_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cache_key_digest", DigestRef.parse(str(self.cache_key_digest)))
        if self.validation_status is not None:
            object.__setattr__(self, "validation_status", CacheValidationStatus(self.validation_status))
        if self.miss_reason is not None and (
            not isinstance(self.miss_reason, str) or not self.miss_reason.strip()
        ):
            raise ValueError("miss_reason must be a non-empty string or None")

    @property
    def hit(self) -> bool:
        return self.value is not None


@runtime_checkable
class ComparisonCoreCache(Protocol):
    @property
    def enabled(self) -> bool: ...

    def lookup(
        self,
        *,
        key: ComparisonCoreCacheKey,
        lookup_policy: CacheLookupPolicy | str = CacheLookupPolicy.READ_ANY,
        now: datetime | None = None,
    ) -> ComparisonCoreCacheLookup: ...

    def write(
        self,
        *,
        key: ComparisonCoreCacheKey,
        value: ComparisonCoreCacheEntry,
        validation_status: CacheValidationStatus | str = CacheValidationStatus.PROVISIONAL,
        provenance: str | None = None,
        now: datetime | None = None,
    ) -> ComparisonCoreCacheEntry: ...

    def rekey(
        self,
        *,
        source_key: ComparisonCoreCacheKey,
        target_key: ComparisonCoreCacheKey,
        validation_status: CacheValidationStatus | str | None = None,
        provenance: str | None = None,
        now: datetime | None = None,
    ) -> ComparisonCoreCacheLookup: ...

    def clear(self) -> None: ...


class DisabledComparisonCoreCache:
    @property
    def enabled(self) -> bool:
        return False

    def lookup(
        self,
        *,
        key: ComparisonCoreCacheKey,
        lookup_policy: CacheLookupPolicy | str = CacheLookupPolicy.READ_ANY,
        now: datetime | None = None,
    ) -> ComparisonCoreCacheLookup:
        del lookup_policy, now
        return ComparisonCoreCacheLookup(
            value=None,
            cache_key_digest=key.cache_key_digest,
            miss_reason="DISABLED",
        )

    def write(
        self,
        *,
        key: ComparisonCoreCacheKey,
        value: ComparisonCoreCacheEntry,
        validation_status: CacheValidationStatus | str = CacheValidationStatus.PROVISIONAL,
        provenance: str | None = None,
        now: datetime | None = None,
    ) -> ComparisonCoreCacheEntry:
        del key, validation_status, provenance, now
        return value

    def rekey(
        self,
        *,
        source_key: ComparisonCoreCacheKey,
        target_key: ComparisonCoreCacheKey,
        validation_status: CacheValidationStatus | str | None = None,
        provenance: str | None = None,
        now: datetime | None = None,
    ) -> ComparisonCoreCacheLookup:
        del now, target_key, validation_status, provenance
        return ComparisonCoreCacheLookup(
            value=None,
            cache_key_digest=source_key.cache_key_digest,
            miss_reason="DISABLED",
        )

    def clear(self) -> None:
        return None


class InMemoryComparisonCoreCache:
    def __init__(self) -> None:
        self._entries: dict[ComparisonCoreCacheKey, ComparisonCoreCacheEntry] = {}
        self._statuses: dict[ComparisonCoreCacheKey, CacheValidationStatus] = {}
        self._entry_digests: dict[ComparisonCoreCacheKey, DigestRef] = {}
        self._registry: dict[str, dict[str, object]] = {}

    @property
    def enabled(self) -> bool:
        return True

    def lookup(
        self,
        *,
        key: ComparisonCoreCacheKey,
        lookup_policy: CacheLookupPolicy | str = CacheLookupPolicy.READ_ANY,
        now: datetime | None = None,
    ) -> ComparisonCoreCacheLookup:
        del now
        lookup_policy = CacheLookupPolicy(lookup_policy)
        value = self._entries.get(key)
        if value is None:
            return ComparisonCoreCacheLookup(
                value=None,
                cache_key_digest=key.cache_key_digest,
                miss_reason="REGISTRY_MISS",
            )
        validation_status = self._statuses.get(key, CacheValidationStatus.PROVISIONAL)
        if not _lookup_policy_allows(lookup_policy, validation_status):
            return ComparisonCoreCacheLookup(
                value=None,
                cache_key_digest=key.cache_key_digest,
                validation_status=validation_status,
                miss_reason=COMPARISON_CORE_CACHE_POLICY_MISS_REASON,
            )
        return ComparisonCoreCacheLookup(
            value=value,
            cache_key_digest=key.cache_key_digest,
            validation_status=validation_status,
        )

    def write(
        self,
        *,
        key: ComparisonCoreCacheKey,
        value: ComparisonCoreCacheEntry,
        validation_status: CacheValidationStatus | str = CacheValidationStatus.PROVISIONAL,
        provenance: str | None = None,
        now: datetime | None = None,
    ) -> ComparisonCoreCacheEntry:
        validation_status = CacheValidationStatus(validation_status)
        entry_digest = _entry_content_digest(value)
        existing_value = self._entries.get(key)
        existing_digest = self._entry_digests.get(key)
        if existing_value is not None:
            if existing_digest != entry_digest:
                raise ValueError("comparison core cache entry already exists with different payload")
            validation_status = _max_validation_status(
                self._statuses.get(key, CacheValidationStatus.PROVISIONAL),
                validation_status,
            )
            self._statuses[key] = validation_status
            self._registry[key.cache_key_digest.to_payload()] = _registry_entry_payload(
                key=key,
                entry_content_digest=entry_digest,
                validation_status=validation_status,
                provenance=provenance,
                now=now,
            )
            return existing_value
        self._entries[key] = value
        self._statuses[key] = validation_status
        self._entry_digests[key] = entry_digest
        self._registry[key.cache_key_digest.to_payload()] = _registry_entry_payload(
            key=key,
            entry_content_digest=entry_digest,
            validation_status=validation_status,
            provenance=provenance,
            now=now,
        )
        return value

    def rekey(
        self,
        *,
        source_key: ComparisonCoreCacheKey,
        target_key: ComparisonCoreCacheKey,
        validation_status: CacheValidationStatus | str | None = None,
        provenance: str | None = None,
        now: datetime | None = None,
    ) -> ComparisonCoreCacheLookup:
        source_value = self._entries.get(source_key)
        if source_value is None:
            return ComparisonCoreCacheLookup(
                value=None,
                cache_key_digest=target_key.cache_key_digest,
                miss_reason="REGISTRY_MISS",
            )
        target_status = (
            CacheValidationStatus(validation_status)
            if validation_status is not None
            else self._statuses.get(source_key, CacheValidationStatus.PROVISIONAL)
        )
        self.write(
            key=target_key,
            value=source_value,
            validation_status=target_status,
            provenance=provenance,
            now=now,
        )
        target_digest = self._entry_digests[target_key]
        self._registry[target_key.cache_key_digest.to_payload()] = _registry_entry_payload(
            key=target_key,
            entry_content_digest=target_digest,
            validation_status=self._statuses[target_key],
            provenance=provenance,
            source_key_digest=source_key.cache_key_digest,
            now=now,
        )
        return ComparisonCoreCacheLookup(
            value=source_value,
            cache_key_digest=target_key.cache_key_digest,
            validation_status=self._statuses[target_key],
        )

    def clear(self) -> None:
        self._entries.clear()
        self._statuses.clear()
        self._entry_digests.clear()
        self._registry.clear()


class FilesystemComparisonCoreCache:
    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._records_store = LocalArtifactStore(self._root / "records-artifacts")

    @property
    def enabled(self) -> bool:
        return True

    @property
    def root(self) -> Path:
        return self._root

    def lookup(
        self,
        *,
        key: ComparisonCoreCacheKey,
        lookup_policy: CacheLookupPolicy | str = CacheLookupPolicy.READ_ANY,
        now: datetime | None = None,
    ) -> ComparisonCoreCacheLookup:
        lookup_policy = CacheLookupPolicy(lookup_policy)
        manifest_path = self._manifest_path(key)
        entry_path = self._entry_path(key)
        if not manifest_path.is_file() or not entry_path.is_file():
            return ComparisonCoreCacheLookup(
                value=None,
                cache_key_digest=key.cache_key_digest,
                miss_reason="MISSING_OBJECT",
            )
        try:
            manifest_payload = _json_loads_mapping(manifest_path.read_bytes())
            manifest = ArtifactManifest.from_payload(manifest_payload)
            if manifest.artifact_kind != COMPARISON_CORE_CACHE_ARTIFACT_KIND:
                raise ValueError("comparison core cache artifact kind mismatch")
            if manifest.artifact_contract_version != COMPARISON_CORE_CACHE_CONTRACT_VERSION:
                return ComparisonCoreCacheLookup(
                    value=None,
                    cache_key_digest=key.cache_key_digest,
                    miss_reason="VERSION_MISMATCH",
                )
            metadata = manifest.metadata
            cached_key_digest = _required_digest(metadata, "cache_key_digest")
            if cached_key_digest != key.cache_key_digest:
                raise ValueError("cached key digest mismatch")
            validation_status = CacheValidationStatus(
                str(metadata.get("validation_status") or CacheValidationStatus.PROVISIONAL.value)
            )
            entry_bytes = entry_path.read_bytes()
            if DigestRef.from_bytes(entry_bytes) != manifest.content_digest:
                raise ValueError("comparison core cache entry digest mismatch")
            if len(entry_bytes) != manifest.content_size_bytes:
                raise ValueError("comparison core cache entry size mismatch")
            value = pickle.loads(entry_bytes)
            if not isinstance(value, ComparisonCoreCacheEntry):
                raise TypeError("comparison core cache entry payload is invalid")
        except (OSError, TypeError, ValueError, pickle.PickleError, AttributeError, EOFError, ImportError):
            return ComparisonCoreCacheLookup(
                value=None,
                cache_key_digest=key.cache_key_digest,
                miss_reason="MANIFEST_INVALID",
            )
        self._write_registry_entry(
            key=key,
            entry_content_digest=manifest.content_digest,
            validation_status=validation_status,
            provenance=_optional_text(metadata.get("provenance")),
            source_key_digest=_optional_digest(metadata.get("source_key_digest")),
            now=now,
        )
        if not _lookup_policy_allows(lookup_policy, validation_status):
            return ComparisonCoreCacheLookup(
                value=None,
                cache_key_digest=key.cache_key_digest,
                validation_status=validation_status,
                miss_reason=COMPARISON_CORE_CACHE_POLICY_MISS_REASON,
            )
        return ComparisonCoreCacheLookup(
            value=value,
            cache_key_digest=key.cache_key_digest,
            validation_status=validation_status,
        )

    def write(
        self,
        *,
        key: ComparisonCoreCacheKey,
        value: ComparisonCoreCacheEntry,
        validation_status: CacheValidationStatus | str = CacheValidationStatus.PROVISIONAL,
        provenance: str | None = None,
        now: datetime | None = None,
    ) -> ComparisonCoreCacheEntry:
        validation_status = CacheValidationStatus(validation_status)
        entry = self._normalize_entry(value)
        entry_bytes = pickle.dumps(entry, protocol=pickle.HIGHEST_PROTOCOL)
        entry_content_digest = DigestRef.from_bytes(entry_bytes)
        manifest = ArtifactManifest(
            artifact_kind=COMPARISON_CORE_CACHE_ARTIFACT_KIND,
            artifact_contract_version=COMPARISON_CORE_CACHE_CONTRACT_VERSION,
            content_digest=entry_content_digest,
            content_size_bytes=len(entry_bytes),
            metadata=_comparison_core_cache_metadata(
                key=key,
                value=entry,
                validation_status=validation_status,
                provenance=provenance,
            ),
        )
        manifest_path = self._manifest_path(key)
        entry_path = self._entry_path(key)
        manifest_payload = manifest.to_payload()

        if manifest_path.is_file() or entry_path.is_file():
            if not manifest_path.is_file() or not entry_path.is_file():
                raise ValueError("comparison core cache entry is partially written")
            existing_manifest_payload = _json_loads_mapping(manifest_path.read_bytes())
            existing_manifest = ArtifactManifest.from_payload(existing_manifest_payload)
            existing_bytes = entry_path.read_bytes()
            if existing_manifest.content_digest != entry_content_digest or existing_bytes != entry_bytes:
                raise ValueError("comparison core cache entry already exists with different payload")
            existing_value = pickle.loads(existing_bytes)
            if not isinstance(existing_value, ComparisonCoreCacheEntry):
                raise TypeError("comparison core cache entry payload is invalid")
            existing_status = _metadata_validation_status(existing_manifest.metadata)
            merged_status = _max_validation_status(existing_status, validation_status)
            if merged_status != existing_status:
                manifest = ArtifactManifest(
                    artifact_kind=COMPARISON_CORE_CACHE_ARTIFACT_KIND,
                    artifact_contract_version=COMPARISON_CORE_CACHE_CONTRACT_VERSION,
                    content_digest=existing_manifest.content_digest,
                    content_size_bytes=existing_manifest.content_size_bytes,
                    metadata=_comparison_core_cache_metadata(
                        key=key,
                        value=existing_value,
                        validation_status=merged_status,
                        provenance=provenance,
                    ),
                    diagnostics=existing_manifest.diagnostics,
                    created_at=existing_manifest.created_at,
                )
                manifest_payload = manifest.to_payload()
                _write_bytes(
                    manifest_path,
                    json.dumps(manifest_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"),
                )
            else:
                manifest = existing_manifest
            self._write_registry_entry(
                key=key,
                entry_content_digest=manifest.content_digest,
                validation_status=merged_status,
                provenance=_optional_text(manifest.metadata.get("provenance")) or provenance,
                now=now,
            )
            return existing_value

        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        _write_bytes(manifest_path, json.dumps(manifest_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        _write_bytes(entry_path, entry_bytes)
        self._write_registry_entry(
            key=key,
            entry_content_digest=entry_content_digest,
            validation_status=validation_status,
            provenance=provenance,
            now=now,
        )
        return entry

    def rekey(
        self,
        *,
        source_key: ComparisonCoreCacheKey,
        target_key: ComparisonCoreCacheKey,
        validation_status: CacheValidationStatus | str | None = None,
        provenance: str | None = None,
        now: datetime | None = None,
    ) -> ComparisonCoreCacheLookup:
        source_lookup = self.lookup(key=source_key, lookup_policy=CacheLookupPolicy.READ_ANY, now=now)
        if not source_lookup.hit or not isinstance(source_lookup.value, ComparisonCoreCacheEntry):
            return ComparisonCoreCacheLookup(
                value=None,
                cache_key_digest=target_key.cache_key_digest,
                miss_reason=source_lookup.miss_reason,
            )

        entry = source_lookup.value
        validation_status = (
            CacheValidationStatus(validation_status)
            if validation_status is not None
            else source_lookup.validation_status or CacheValidationStatus.PROVISIONAL
        )
        entry_bytes = pickle.dumps(entry, protocol=pickle.HIGHEST_PROTOCOL)
        entry_content_digest = DigestRef.from_bytes(entry_bytes)
        manifest = ArtifactManifest(
            artifact_kind=COMPARISON_CORE_CACHE_ARTIFACT_KIND,
            artifact_contract_version=COMPARISON_CORE_CACHE_CONTRACT_VERSION,
            content_digest=entry_content_digest,
            content_size_bytes=len(entry_bytes),
            metadata=_comparison_core_cache_metadata(
                key=target_key,
                value=entry,
                validation_status=validation_status,
                provenance=provenance,
                source_key_digest=source_key.cache_key_digest,
            ),
        )
        manifest_path = self._manifest_path(target_key)
        entry_path = self._entry_path(target_key)
        manifest_payload = manifest.to_payload()

        entry_dir = self._entry_dir(target_key)
        if manifest_path.is_file() or entry_path.is_file():
            if not manifest_path.is_file() or not entry_path.is_file():
                raise ValueError("comparison core cache entry is partially written")
            existing_manifest_payload = _json_loads_mapping(manifest_path.read_bytes())
            existing_manifest = ArtifactManifest.from_payload(existing_manifest_payload)
            existing_bytes = entry_path.read_bytes()
            if existing_manifest.content_digest != entry_content_digest or existing_bytes != entry_bytes:
                raise ValueError("comparison core cache entry already exists with different payload")
            existing_status = _metadata_validation_status(existing_manifest.metadata)
            validation_status = _max_validation_status(existing_status, validation_status)
            if validation_status != existing_status:
                manifest = ArtifactManifest(
                    artifact_kind=COMPARISON_CORE_CACHE_ARTIFACT_KIND,
                    artifact_contract_version=COMPARISON_CORE_CACHE_CONTRACT_VERSION,
                    content_digest=existing_manifest.content_digest,
                    content_size_bytes=existing_manifest.content_size_bytes,
                    metadata=_comparison_core_cache_metadata(
                        key=target_key,
                        value=entry,
                        validation_status=validation_status,
                        provenance=provenance,
                        source_key_digest=source_key.cache_key_digest,
                    ),
                    diagnostics=existing_manifest.diagnostics,
                    created_at=existing_manifest.created_at,
                )
                manifest_payload = manifest.to_payload()
                _write_bytes(
                    manifest_path,
                    json.dumps(manifest_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"),
                )
            else:
                manifest = existing_manifest
            self._write_registry_entry(
                key=target_key,
                entry_content_digest=manifest.content_digest,
                validation_status=validation_status,
                provenance=_optional_text(manifest.metadata.get("provenance")) or provenance,
                source_key_digest=source_key.cache_key_digest,
                now=now,
            )
            return ComparisonCoreCacheLookup(
                value=entry,
                cache_key_digest=target_key.cache_key_digest,
                validation_status=validation_status,
            )

        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        _write_bytes(
            manifest_path,
            json.dumps(manifest_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8"),
        )
        _write_bytes(entry_path, entry_bytes)
        self._write_registry_entry(
            key=target_key,
            entry_content_digest=entry_content_digest,
            validation_status=validation_status,
            provenance=provenance,
            source_key_digest=source_key.cache_key_digest,
            now=now,
        )
        return ComparisonCoreCacheLookup(
            value=entry,
            cache_key_digest=target_key.cache_key_digest,
            validation_status=validation_status,
        )

    def clear(self) -> None:
        if self._root.exists():
            shutil.rmtree(self._root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._records_store = LocalArtifactStore(self._root / "records-artifacts")

    def _normalize_entry(self, value: ComparisonCoreCacheEntry) -> ComparisonCoreCacheEntry:
        normalized_records_artifacts = tuple(
            _store_records_artifact(self._records_store, records_artifact)
            for records_artifact in value.records_artifacts
        )
        return ComparisonCoreCacheEntry(
            facts=value.facts,
            records_closure=value.records_closure,
            records_artifacts=normalized_records_artifacts,
        )

    def _manifest_path(self, key: ComparisonCoreCacheKey) -> Path:
        return self._entry_dir(key) / COMPARISON_CORE_CACHE_MANIFEST_FILE_NAME

    def _entry_path(self, key: ComparisonCoreCacheKey) -> Path:
        return self._entry_dir(key) / COMPARISON_CORE_CACHE_ENTRY_FILE_NAME

    def _entry_dir(self, key: ComparisonCoreCacheKey) -> Path:
        return self._root / key.cache_key_digest.hex_digest

    def _registry_path(self) -> Path:
        return self._root / COMPARISON_CORE_CACHE_REGISTRY_FILE_NAME

    def _write_registry_entry(
        self,
        *,
        key: ComparisonCoreCacheKey,
        entry_content_digest: DigestRef | str,
        validation_status: CacheValidationStatus | str,
        provenance: str | None = None,
        source_key_digest: DigestRef | str | None = None,
        now: datetime | None = None,
    ) -> None:
        registry_path = self._registry_path()
        try:
            registry_payload = _json_loads_mapping(registry_path.read_bytes()) if registry_path.is_file() else {}
            entries = registry_payload.get("entries", {})
            if not isinstance(entries, Mapping):
                entries = {}
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            entries = {}
        normalized_entries = {str(entry_key): entry_value for entry_key, entry_value in entries.items()}
        normalized_entries[key.cache_key_digest.to_payload()] = _registry_entry_payload(
            key=key,
            entry_content_digest=entry_content_digest,
            validation_status=validation_status,
            provenance=provenance,
            source_key_digest=source_key_digest,
            now=now,
        )
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        _write_bytes(
            registry_path,
            json.dumps(
                {
                    "schema_version": COMPARISON_CORE_CACHE_REGISTRY_SCHEMA_VERSION,
                    "entries": normalized_entries,
                },
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8"),
        )


def _comparison_options_payload(options: ComparisonOptions) -> dict[str, object]:
    return {
        "include_unchanged_tables": options.include_unchanged_tables,
        "row_diff_detail_policy": options.row_diff_detail_policy.value,
        "max_inline_record_count": options.max_inline_record_count,
    }


def _table_alias_payload(alias: Mapping[str, object] | tuple[str, str, str]) -> tuple[str, str, str]:
    if isinstance(alias, tuple):
        if len(alias) != 3:
            raise ValueError("table alias tuple must contain scope, logical, canonical")
        alias_scope, logical, canonical = alias
    else:
        raw_logical = alias.get("logical_table_name")
        raw_canonical = alias.get("canonical_table_name")
        raw_scope = alias.get("alias_scope")
        if not isinstance(raw_scope, str) or not raw_scope.strip():
            raise ValueError("table alias alias_scope must be a non-empty string")
        if not isinstance(raw_logical, str) or not raw_logical.strip():
            raise ValueError("table alias logical_table_name must be a non-empty string")
        if not isinstance(raw_canonical, str) or not raw_canonical.strip():
            raise ValueError("table alias canonical_table_name must be a non-empty string")
        alias_scope = raw_scope.strip()
        logical = raw_logical
        canonical = raw_canonical
    logical_name = canonical_identifier(logical)
    canonical_name = canonical_identifier(canonical)
    if not logical_name or not canonical_name:
        raise ValueError("table alias names must resolve to non-empty identifiers")
    if logical_name == canonical_name:
        raise ValueError("table alias logical/canonical names must differ")
    return (alias_scope.strip(), logical_name, canonical_name)


def _comparison_input_identity_digest(comparison_input: object) -> DigestRef:
    repository_backed_context = getattr(comparison_input, "repository_backed_context", None)
    if repository_backed_context is None:
        snapshot = getattr(comparison_input, "snapshot", None)
        snapshot_digest = getattr(snapshot, "snapshot_digest", None)
        if snapshot_digest is None:
            raise ValueError("comparison input snapshot digest is required")
        return DigestRef.parse(str(snapshot_digest))
    return DigestRef.from_payload(
        {
            "repository_id": repository_backed_context.repository_id,
            "resolved_commit_hash": repository_backed_context.resolved_commit_hash,
        }
    )


def _comparison_core_cache_metadata(
    *,
    key: ComparisonCoreCacheKey,
    value: ComparisonCoreCacheEntry,
    validation_status: CacheValidationStatus | str = CacheValidationStatus.PROVISIONAL,
    provenance: str | None = None,
    source_key_digest: DigestRef | str | None = None,
) -> dict[str, object]:
    entry_payload = value.to_contract_payload(validation_status=validation_status)
    metadata = {
        "cache_key_digest": key.cache_key_digest.to_payload(),
        "cache_key_payload": key.to_contract_payload().to_payload(),
        **entry_payload.to_payload(),
        "entry_payload": entry_payload.to_payload(),
        "runtime_serialization": "pickle",
    }
    if provenance is not None:
        metadata["provenance"] = _required_text(provenance, "provenance")
    if source_key_digest is not None:
        metadata["source_key_digest"] = DigestRef.parse(str(source_key_digest)).to_payload()
    return metadata


def _store_records_artifact(
    store: LocalArtifactStore,
    records_artifact: RecordsArtifact,
) -> RecordsArtifact:
    stored = store.put_bytes(
        records_artifact.manifest.to_artifact_manifest(),
        records_artifact.content_path.read_bytes(),
    )
    stored = replace(stored, reused=False)
    return RecordsArtifact(
        manifest=RecordsArtifactManifest.from_artifact_manifest(stored.manifest),
        stored=stored,
    )


def _required_digest(payload: Mapping[str, object], field_name: str) -> DigestRef:
    value = payload[field_name]
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field_name} must be a non-empty string")
    return DigestRef.parse(value)


def _optional_digest(value: object | None) -> DigestRef | None:
    if value is None:
        return None
    return DigestRef.parse(str(value))


def _required_text(payload: object, field_name: str) -> str:
    if not isinstance(payload, str) or not payload.strip():
        raise TypeError(f"{field_name} must be a non-empty string")
    return payload.strip()


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("optional text fields must be strings or None")
    normalized = value.strip()
    return normalized or None


def _metadata_validation_status(metadata: Mapping[str, object]) -> CacheValidationStatus:
    return CacheValidationStatus(
        str(metadata.get("validation_status") or CacheValidationStatus.PROVISIONAL.value)
    )


def _validation_status_rank(status: CacheValidationStatus | str) -> int:
    return {
        CacheValidationStatus.PROVISIONAL: 0,
        CacheValidationStatus.CONTENT_VERIFIED: 1,
        CacheValidationStatus.COMMIT_VALIDATED: 2,
    }[CacheValidationStatus(status)]


def _max_validation_status(
    left: CacheValidationStatus | str,
    right: CacheValidationStatus | str,
) -> CacheValidationStatus:
    left_status = CacheValidationStatus(left)
    right_status = CacheValidationStatus(right)
    if _validation_status_rank(right_status) > _validation_status_rank(left_status):
        return right_status
    return left_status


def _lookup_policy_allows(
    lookup_policy: CacheLookupPolicy | str,
    validation_status: CacheValidationStatus | str,
) -> bool:
    policy = CacheLookupPolicy(lookup_policy)
    status = CacheValidationStatus(validation_status)
    if policy is CacheLookupPolicy.READ_ANY:
        return True
    if policy is CacheLookupPolicy.READ_COMMIT_VALIDATED_ONLY:
        return status is CacheValidationStatus.COMMIT_VALIDATED
    raise ValueError(f"unsupported cache lookup policy: {lookup_policy}")


def _entry_content_digest(value: ComparisonCoreCacheEntry) -> DigestRef:
    return DigestRef.from_bytes(pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL))


def _registry_entry_payload(
    *,
    key: ComparisonCoreCacheKey,
    entry_content_digest: DigestRef | str,
    validation_status: CacheValidationStatus | str,
    provenance: str | None = None,
    source_key_digest: DigestRef | str | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    timestamp = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    payload: dict[str, object] = {
        "cache_key_digest": key.cache_key_digest.to_payload(),
        "entry_content_digest": DigestRef.parse(str(entry_content_digest)).to_payload(),
        "validation_status": CacheValidationStatus(validation_status).value,
        "updated_at": timestamp.astimezone(timezone.utc).isoformat(),
    }
    if provenance is not None:
        payload["provenance"] = _required_text(provenance, "provenance")
    if source_key_digest is not None:
        payload["source_key_digest"] = DigestRef.parse(str(source_key_digest)).to_payload()
    return payload


def _json_loads_mapping(raw: bytes) -> dict[str, object]:
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError("cache manifest payload must be a mapping")
    return {str(key): value for key, value in payload.items()}


def _write_bytes(path: Path, data: bytes) -> None:
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_bytes(data)
    tmp_path.replace(path)


__all__ = [
    "COMPARISON_CORE_CACHE_CONTRACT_VERSION",
    "COMPARISON_CORE_CACHE_ARTIFACT_KIND",
    "COMPARISON_CORE_CACHE_NAMESPACE",
    "COMPARISON_CORE_CACHE_POLICY_MISS_REASON",
    "COMPARISON_CORE_CACHE_PROVENANCE_HISTORY_COMPARE_COMPUTE",
    "COMPARISON_CORE_CACHE_PROVENANCE_PREVIEW_COMPLETION",
    "COMPARISON_CORE_CACHE_PROVENANCE_SUBMIT_FINALIZE_PROMOTION",
    "COMPARISON_CORE_CACHE_REGISTRY_FILE_NAME",
    "COMPARISON_CORE_CACHE_REGISTRY_SCHEMA_VERSION",
    "ComparisonCoreCache",
    "ComparisonCoreCacheEntry",
    "ComparisonCoreCacheKey",
    "ComparisonCoreCacheLookup",
    "DisabledComparisonCoreCache",
    "FilesystemComparisonCoreCache",
    "InMemoryComparisonCoreCache",
    "build_comparison_core_cache_key",
]
