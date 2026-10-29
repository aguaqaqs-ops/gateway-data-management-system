"""Immutable public contracts for deterministic comparison bundle assembly."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from gateway_shared_kernel import DigestRef
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import ArtifactRef, assert_no_host_path_identity, artifact_ref_to_dict
from gateway_backend.capabilities.surface_assembly.contracts import (
    SurfaceAssemblyResult,
)

BUNDLE_CONTRACT_VERSION = "backend-vnext/comparison-bundle/v3"
BUNDLE_MANIFEST_MEDIA_TYPE = "application/vnd.gateway.comparison-bundle.manifest+json"
BUNDLE_CLOSURE_MEDIA_TYPE = "application/vnd.gateway.comparison-bundle.closure+json"
MAX_BUNDLE_MANIFEST_JSON_BYTES = 16 * 1024 * 1024
MAX_BUNDLE_CLOSURE_JSON_BYTES = 16 * 1024 * 1024
MAX_BUNDLE_WALL_TIME_SECONDS = 300.0
MAX_PAIR_CONCURRENCY = 8


class BundleProfile(StrEnum):
    SINGLE_PAIR = "SINGLE_PAIR"
    MULTI_PAIR = "MULTI_PAIR"


class BundleRefScope(StrEnum):
    BUNDLE_RELATIVE = "BUNDLE_RELATIVE"


class BundleAssemblyStatus(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class BundlePairStatus(StrEnum):
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class BundleArtifactKind(StrEnum):
    SURFACE = "SURFACE"
    SNAPSHOT_TABLE = "SNAPSHOT_TABLE"
    RECORDS = "RECORDS"
    RECORDS_MANIFEST = "RECORDS_MANIFEST"
    RECORDS_CLOSURE = "RECORDS_CLOSURE"
    RISK_REPORT = "RISK_REPORT"
    RISK_ANNOTATION = "RISK_ANNOTATION"
    RISK_ANNOTATION_MANIFEST = "RISK_ANNOTATION_MANIFEST"
    RISK_ANNOTATION_CLOSURE = "RISK_ANNOTATION_CLOSURE"
    PROJECTION = "PROJECTION"
    DIAGNOSTICS = "DIAGNOSTICS"
    OTHER = "OTHER"


class BundleTableSide(StrEnum):
    BEFORE = "before"
    CURRENT = "current"
    BROWSE = "browse"


@dataclass(frozen=True, slots=True)
class BundleTableBinding:
    pair_id: str
    table_name: str
    side: BundleTableSide

    def __post_init__(self) -> None:
        object.__setattr__(self, "pair_id", _identifier(self.pair_id, "pair_id"))
        object.__setattr__(self, "table_name", _identifier(self.table_name, "table_name"))
        if type(self.side) is not BundleTableSide:
            raise ValueError("side must be BundleTableSide")

    def to_document(self) -> dict[str, object]:
        return {
            "pair_id": self.pair_id,
            "side": self.side.value,
            "table_name": self.table_name,
        }


def _binding_side_from_path(logical_path: str) -> BundleTableSide:
    parts = logical_path.split("/")
    try:
        table_index = parts.index("tables")
        return BundleTableSide(parts[table_index + 1])
    except (ValueError, IndexError) as exc:
        raise ValueError("snapshot table binding path must identify before/current/browse side") from exc


def _text(value: object, label: str) -> str:
    if type(value) is not str or value == "":
        raise ValueError(f"{label} must be a non-empty string")
    assert_no_host_path_identity(value, label=label)
    return value


def _identifier(value: object, label: str) -> str:
    result = _text(value, label)
    if any(character in result for character in "/\\") or result in {".", ".."}:
        raise ValueError(f"{label} must be an opaque identifier")
    return result


def _non_negative(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return value


def _digest(value: object, label: str) -> DigestRef:
    if type(value) is not DigestRef:
        raise ValueError(f"{label} must be DigestRef")
    return value


def _optional_digest(value: DigestRef | None, label: str) -> None:
    if value is not None:
        _digest(value, label)


def _ref(value: object, label: str) -> ArtifactRef:
    if type(value) is not ArtifactRef:
        raise ValueError(f"{label} must be ArtifactRef")
    lowered = value.artifact_id.casefold()
    if lowered.startswith(
        (
            "cache-",
            "cache:",
            "repository-",
            "repository:",
            "repo-",
            "repo:",
            "flow-",
            "flow:",
            "operation-",
            "operation:",
            "workspace-",
            "workspace:",
            "preview-",
            "preview:",
            "submit-",
            "submit:",
            "history-",
            "history:",
            "dolt-",
            "dolt:",
        )
    ):
        raise ValueError(f"{label} must not use cache, repository or flow-local identity")
    return value


def _optional_ref(value: ArtifactRef | None, label: str) -> None:
    if value is not None:
        _ref(value, label)


def _string_pairs(value: object, label: str) -> tuple[tuple[str, str], ...]:
    if type(value) is not tuple:
        raise ValueError(f"{label} must be a tuple")
    result: list[tuple[str, str]] = []
    for item in value:
        if type(item) is not tuple or len(item) != 2:
            raise ValueError(f"{label} must contain string pairs")
        key, text = item
        result.append((_text(key, f"{label}.key"), _text(text, f"{label}.value")))
    ordered = tuple(sorted(result))
    if len({key for key, _ in ordered}) != len(ordered):
        raise ValueError(f"{label} must use unique keys")
    return ordered


def validate_logical_path(value: object, *, label: str = "logical_path") -> str:
    path = _text(value, label)
    if (
        path.startswith("/")
        or path.endswith("/")
        or "\\" in path
        or "//" in path
        or any(part in {"", ".", ".."} for part in path.split("/"))
        or "://" in path
    ):
        raise ValueError(f"{label} must be a normalized relative path")
    lowered = path.casefold()
    forbidden_prefixes = (
        "cache/",
        "repository/",
        "repo/",
        "flow/",
        "operation/",
        "workspace/",
        "tmp/",
        "preview/",
        "submit/",
        "history/",
        "dolt/",
    )
    if lowered.startswith(forbidden_prefixes):
        raise ValueError(f"{label} must not use cache, repository or flow identity")
    return path


@dataclass(frozen=True, slots=True)
class BundleInput:
    input_index: int
    role: str
    display_name: str
    display_metadata: tuple[tuple[str, str], ...] = ()
    snapshot_digest: DigestRef | None = None

    def __post_init__(self) -> None:
        _non_negative(self.input_index, "input_index")
        _text(self.role, "role")
        _text(self.display_name, "display_name")
        object.__setattr__(self, "display_metadata", _string_pairs(self.display_metadata, "display_metadata"))
        _optional_digest(self.snapshot_digest, "snapshot_digest")

    def to_document(self) -> dict[str, object]:
        return {
            "display_metadata": {key: value for key, value in self.display_metadata},
            "display_name": self.display_name,
            "input_index": self.input_index,
            "role": self.role,
            "snapshot_digest": None if self.snapshot_digest is None else self.snapshot_digest.value,
        }


@dataclass(frozen=True, slots=True)
class BundleArtifactBinding:
    """A source artifact and its intended bundle-relative manifest location."""

    source_ref: ArtifactRef
    logical_path: str
    kind: BundleArtifactKind
    pair_id: str | None = None
    table_name: str | None = None
    shared: bool = False
    table_bindings: tuple[BundleTableBinding, ...] = ()

    def __post_init__(self) -> None:
        _ref(self.source_ref, "source_ref")
        object.__setattr__(self, "logical_path", validate_logical_path(self.logical_path))
        if type(self.kind) is not BundleArtifactKind:
            raise ValueError("kind must be BundleArtifactKind")
        if self.pair_id is not None:
            object.__setattr__(self, "pair_id", _identifier(self.pair_id, "pair_id"))
        if self.table_name is not None:
            object.__setattr__(self, "table_name", _identifier(self.table_name, "table_name"))
        if type(self.shared) is not bool:
            raise ValueError("shared must be bool")
        if self.shared and self.pair_id is not None:
            raise ValueError("shared artifact must not be pair-scoped")
        if type(self.table_bindings) is not tuple or any(
            type(item) is not BundleTableBinding for item in self.table_bindings
        ):
            raise ValueError("table_bindings must contain BundleTableBinding")
        if self.kind is BundleArtifactKind.SNAPSHOT_TABLE:
            bindings = self.table_bindings
            if not bindings:
                if self.pair_id is None or self.table_name is None:
                    raise ValueError("snapshot table artifact requires an explicit table binding")
                bindings = (
                    BundleTableBinding(
                        pair_id=self.pair_id,
                        table_name=self.table_name,
                        side=_binding_side_from_path(self.logical_path),
                    ),
                )
            ordered = tuple(
                sorted(set(bindings), key=lambda item: (item.pair_id, item.side.value, item.table_name))
            )
            object.__setattr__(self, "table_bindings", ordered)
        elif self.table_bindings:
            raise ValueError("only snapshot table artifacts may carry table_bindings")

    def to_document(self, *, include_source_ref: bool = True) -> dict[str, object]:
        document: dict[str, object] = {
            "kind": self.kind.value,
            "logical_path": self.logical_path,
            "pair_id": self.pair_id,
            "shared": self.shared,
            "table_name": self.table_name,
        }
        if self.kind is BundleArtifactKind.SNAPSHOT_TABLE:
            document["table_bindings"] = [item.to_document() for item in self.table_bindings]
        if include_source_ref:
            document["source_ref"] = artifact_ref_to_dict(self.source_ref)
        return document


@dataclass(frozen=True, slots=True)
class BundleArtifactClosure:
    entries: tuple[BundleArtifactBinding, ...] = ()

    def __post_init__(self) -> None:
        if type(self.entries) is not tuple or any(
            type(item) is not BundleArtifactBinding for item in self.entries
        ):
            raise ValueError("entries must contain BundleArtifactBinding")
        ordered = tuple(sorted(self.entries, key=lambda item: (item.logical_path, item.kind.value)))
        if len({item.logical_path for item in ordered}) != len(ordered):
            raise ValueError("closure logical paths must be unique")
        if len({item.source_ref for item in ordered if item.kind is not BundleArtifactKind.SNAPSHOT_TABLE}) != len(
            tuple(item for item in ordered if item.kind is not BundleArtifactKind.SNAPSHOT_TABLE)
        ):
            raise ValueError("closure source refs must be unique")
        object.__setattr__(self, "entries", ordered)


@dataclass(frozen=True, slots=True)
class BundlePairInput:
    pair_id: str
    before_input_index: int
    current_input_index: int
    surface_result: SurfaceAssemblyResult
    surface_artifact_closure: BundleArtifactClosure = BundleArtifactClosure()
    required: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "pair_id", _identifier(self.pair_id, "pair_id"))
        _non_negative(self.before_input_index, "before_input_index")
        _non_negative(self.current_input_index, "current_input_index")
        if self.before_input_index == self.current_input_index:
            raise ValueError("before and current input indexes must differ")
        if type(self.surface_result) is not SurfaceAssemblyResult:
            raise ValueError("surface_result must be SurfaceAssemblyResult")
        if type(self.surface_artifact_closure) is not BundleArtifactClosure:
            raise ValueError("surface_artifact_closure must be BundleArtifactClosure")
        if type(self.required) is not bool:
            raise ValueError("required must be bool")


@dataclass(frozen=True, slots=True)
class BundlePairFailure:
    pair_id: str
    required: bool
    diagnostics: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "pair_id", _identifier(self.pair_id, "pair_id"))
        if type(self.required) is not bool:
            raise ValueError("required must be bool")
        if type(self.diagnostics) is not tuple or any(
            type(item) is not str or item == "" for item in self.diagnostics
        ):
            raise ValueError("diagnostics must contain non-empty strings")

    def to_document(self) -> dict[str, object]:
        return {
            "diagnostics": list(self.diagnostics),
            "pair_id": self.pair_id,
            "required": self.required,
        }


@dataclass(frozen=True, slots=True)
class BundleClosureEntry:
    logical_path: str
    artifact_ref: ArtifactRef
    kind: BundleArtifactKind
    size_bytes: int
    raw_sha256: DigestRef
    pair_id: str | None = None
    table_name: str | None = None
    shared: bool = False
    table_bindings: tuple[BundleTableBinding, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "logical_path", validate_logical_path(self.logical_path))
        _ref(self.artifact_ref, "artifact_ref")
        if type(self.kind) is not BundleArtifactKind:
            raise ValueError("kind must be BundleArtifactKind")
        _non_negative(self.size_bytes, "size_bytes")
        _digest(self.raw_sha256, "raw_sha256")
        if self.artifact_ref.size_bytes != self.size_bytes:
            raise ValueError("closure size does not match artifact ref")
        if self.artifact_ref.raw_sha256 != self.raw_sha256:
            raise ValueError("closure digest does not match artifact ref")
        if self.pair_id is not None:
            object.__setattr__(self, "pair_id", _identifier(self.pair_id, "pair_id"))
        if self.table_name is not None:
            object.__setattr__(self, "table_name", _identifier(self.table_name, "table_name"))
        if type(self.shared) is not bool:
            raise ValueError("shared must be bool")
        if type(self.table_bindings) is not tuple or any(
            type(item) is not BundleTableBinding for item in self.table_bindings
        ):
            raise ValueError("table_bindings must contain BundleTableBinding")
        if self.kind is BundleArtifactKind.SNAPSHOT_TABLE:
            if not self.table_bindings:
                raise ValueError("snapshot table closure entry requires table bindings")
            ordered = tuple(
                sorted(set(self.table_bindings), key=lambda item: (item.pair_id, item.side.value, item.table_name))
            )
            object.__setattr__(self, "table_bindings", ordered)
        elif self.table_bindings:
            raise ValueError("only snapshot table closure entries may carry table_bindings")

    def to_document(self) -> dict[str, object]:
        document: dict[str, object] = {
            "artifact_ref": artifact_ref_to_dict(self.artifact_ref),
            "kind": self.kind.value,
            "logical_path": self.logical_path,
            "raw_sha256": self.raw_sha256.value,
            "shared": self.shared,
            "size_bytes": self.size_bytes,
        }
        if self.kind is BundleArtifactKind.SNAPSHOT_TABLE:
            document["table_bindings"] = [item.to_document() for item in self.table_bindings]
        else:
            document["pair_id"] = self.pair_id
            document["table_name"] = self.table_name
        return document


@dataclass(frozen=True, slots=True)
class BundleArtifactManifest:
    entries: tuple[BundleClosureEntry, ...]

    def __post_init__(self) -> None:
        if type(self.entries) is not tuple or any(
            type(item) is not BundleClosureEntry for item in self.entries
        ):
            raise ValueError("entries must contain BundleClosureEntry")
        ordered = tuple(sorted(self.entries, key=lambda item: (item.logical_path, item.kind.value)))
        if len({item.logical_path for item in ordered}) != len(ordered):
            raise ValueError("manifest logical paths must be unique")
        object.__setattr__(self, "entries", ordered)

    def to_document(self) -> dict[str, object]:
        return {"entries": [item.to_document() for item in self.entries]}


@dataclass(frozen=True, slots=True)
class BundlePair:
    pair_id: str
    before_input_index: int
    current_input_index: int
    surface_ref: ArtifactRef
    surface_digest: DigestRef
    comparison_digest: DigestRef
    risk_evaluation_digest: DigestRef | None
    summary: tuple[tuple[str, str], ...] = ()
    status: BundlePairStatus = BundlePairStatus.PUBLISHED

    def __post_init__(self) -> None:
        object.__setattr__(self, "pair_id", _identifier(self.pair_id, "pair_id"))
        _non_negative(self.before_input_index, "before_input_index")
        _non_negative(self.current_input_index, "current_input_index")
        _ref(self.surface_ref, "surface_ref")
        _digest(self.surface_digest, "surface_digest")
        _digest(self.comparison_digest, "comparison_digest")
        _optional_digest(self.risk_evaluation_digest, "risk_evaluation_digest")
        object.__setattr__(self, "summary", _string_pairs(self.summary, "summary"))
        if type(self.status) is not BundlePairStatus:
            raise ValueError("status must be BundlePairStatus")

    def to_document(self) -> dict[str, object]:
        return {
            "before_input_index": self.before_input_index,
            "comparison_digest": self.comparison_digest.value,
            "current_input_index": self.current_input_index,
            "pair_id": self.pair_id,
            "risk_evaluation_digest": (
                None if self.risk_evaluation_digest is None else self.risk_evaluation_digest.value
            ),
            "status": self.status.value,
            "summary": {key: value for key, value in self.summary},
            "surface_digest": self.surface_digest.value,
            "surface_ref": artifact_ref_to_dict(self.surface_ref),
        }


@dataclass(frozen=True, slots=True)
class BundleSummary:
    pair_count: int
    published_pair_count: int
    degraded_pair_count: int
    artifact_count: int
    diagnostics_count: int

    def __post_init__(self) -> None:
        for label in (
            "pair_count",
            "published_pair_count",
            "degraded_pair_count",
            "artifact_count",
            "diagnostics_count",
        ):
            _non_negative(getattr(self, label), label)
        if self.published_pair_count > self.pair_count:
            raise ValueError("published_pair_count exceeds pair_count")

    def to_document(self) -> dict[str, object]:
        return {
            "artifact_count": self.artifact_count,
            "degraded_pair_count": self.degraded_pair_count,
            "diagnostics_count": self.diagnostics_count,
            "pair_count": self.pair_count,
            "published_pair_count": self.published_pair_count,
        }


@dataclass(frozen=True, slots=True)
class ComparisonBundle:
    bundle_contract_version: str
    bundle_digest: DigestRef
    bundle_id: str
    bundle_profile: BundleProfile
    status: BundleAssemblyStatus
    inputs: tuple[BundleInput, ...]
    pairs: tuple[BundlePair, ...]
    failed_pairs: tuple[BundlePairFailure, ...]
    summary: BundleSummary
    manifest_ref: ArtifactRef
    artifact_closure_ref: ArtifactRef
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.bundle_contract_version != BUNDLE_CONTRACT_VERSION:
            raise ValueError("unsupported bundle contract version")
        _digest(self.bundle_digest, "bundle_digest")
        object.__setattr__(self, "bundle_id", _identifier(self.bundle_id, "bundle_id"))
        if type(self.bundle_profile) is not BundleProfile:
            raise ValueError("bundle_profile must be BundleProfile")
        if type(self.status) is not BundleAssemblyStatus:
            raise ValueError("status must be BundleAssemblyStatus")
        if type(self.inputs) is not tuple or any(type(item) is not BundleInput for item in self.inputs):
            raise ValueError("inputs must contain BundleInput")
        if type(self.pairs) is not tuple or any(type(item) is not BundlePair for item in self.pairs):
            raise ValueError("pairs must contain BundlePair")
        if type(self.failed_pairs) is not tuple or any(
            type(item) is not BundlePairFailure for item in self.failed_pairs
        ):
            raise ValueError("failed_pairs must contain BundlePairFailure")
        pair_ids = tuple(item.pair_id for item in self.pairs)
        if pair_ids != tuple(sorted(pair_ids)) or len(set(pair_ids)) != len(pair_ids):
            raise ValueError("pairs must use canonical unique order")
        _ref(self.manifest_ref, "manifest_ref")
        _ref(self.artifact_closure_ref, "artifact_closure_ref")
        if type(self.diagnostics) is not tuple or any(
            type(item) is not str or item == "" for item in self.diagnostics
        ):
            raise ValueError("diagnostics must contain non-empty strings")

    def to_document(self) -> dict[str, object]:
        return {
            "artifact_closure_ref": artifact_ref_to_dict(self.artifact_closure_ref),
            "bundle_contract_version": self.bundle_contract_version,
            "bundle_digest": self.bundle_digest.value,
            "bundle_id": self.bundle_id,
            "bundle_profile": self.bundle_profile.value,
            "diagnostics": list(self.diagnostics),
            "failed_pairs": [item.to_document() for item in self.failed_pairs],
            "inputs": [item.to_document() for item in self.inputs],
            "manifest_ref": artifact_ref_to_dict(self.manifest_ref),
            "pairs": [item.to_document() for item in self.pairs],
            "status": self.status.value,
            "summary": self.summary.to_document(),
        }


@dataclass(frozen=True, slots=True)
class BundleAssemblyInput:
    bundle_contract_version: str
    bundle_profile: BundleProfile
    inputs: tuple[BundleInput, ...]
    pairs: tuple[BundlePairInput, ...]
    shared_artifacts: BundleArtifactClosure = BundleArtifactClosure()
    artifact_policy: BundleAssemblyPolicy | None = None
    ref_scope: BundleRefScope = BundleRefScope.BUNDLE_RELATIVE

    def __post_init__(self) -> None:
        if self.bundle_contract_version != BUNDLE_CONTRACT_VERSION:
            raise ValueError("unsupported bundle contract version")
        if type(self.bundle_profile) is not BundleProfile:
            raise ValueError("bundle_profile must be BundleProfile")
        if type(self.inputs) is not tuple or any(type(item) is not BundleInput for item in self.inputs):
            raise ValueError("inputs must contain BundleInput")
        if type(self.pairs) is not tuple or any(type(item) is not BundlePairInput for item in self.pairs):
            raise ValueError("pairs must contain BundlePairInput")
        if type(self.shared_artifacts) is not BundleArtifactClosure:
            raise ValueError("shared_artifacts must be BundleArtifactClosure")
        if self.artifact_policy is None:
            object.__setattr__(self, "artifact_policy", BundleAssemblyPolicy())
        elif type(self.artifact_policy) is not BundleAssemblyPolicy:
            raise ValueError("artifact_policy must be BundleAssemblyPolicy")
        if self.ref_scope is not BundleRefScope.BUNDLE_RELATIVE:
            raise ValueError("bundle ref scope must be BUNDLE_RELATIVE")
        inputs = tuple(sorted(self.inputs, key=lambda item: item.input_index))
        if len({item.input_index for item in inputs}) != len(inputs):
            raise ValueError("inputs must use canonical unique indexes")
        pairs = tuple(sorted(self.pairs, key=lambda item: item.pair_id))
        if len({item.pair_id for item in pairs}) != len(pairs):
            raise ValueError("pairs must use canonical unique ids")
        object.__setattr__(self, "inputs", inputs)
        object.__setattr__(self, "pairs", pairs)


@dataclass(frozen=True, slots=True)
class BundleAssemblyPolicy:
    max_bundle_manifest_json_bytes: int = MAX_BUNDLE_MANIFEST_JSON_BYTES
    max_bundle_closure_json_bytes: int = MAX_BUNDLE_CLOSURE_JSON_BYTES
    max_bundle_wall_time_seconds: float = MAX_BUNDLE_WALL_TIME_SECONDS
    max_pair_concurrency: int = MAX_PAIR_CONCURRENCY

    def __post_init__(self) -> None:
        for label in ("max_bundle_manifest_json_bytes", "max_bundle_closure_json_bytes"):
            if type(getattr(self, label)) is not int or getattr(self, label) < 1:
                raise ValueError(f"{label} must be positive")
        if type(self.max_bundle_wall_time_seconds) not in {int, float}:
            raise ValueError("max_bundle_wall_time_seconds must be numeric")
        if self.max_bundle_wall_time_seconds <= 0:
            raise ValueError("max_bundle_wall_time_seconds must be positive")
        if type(self.max_pair_concurrency) is not int or not 1 <= self.max_pair_concurrency <= MAX_PAIR_CONCURRENCY:
            raise ValueError("max_pair_concurrency must be between 1 and 8")
        object.__setattr__(self, "max_bundle_wall_time_seconds", float(self.max_bundle_wall_time_seconds))


@dataclass(frozen=True, slots=True)
class BundleAssemblyContext:
    checkpoint: Callable[[], None] = lambda: None
    cancel_requested: Callable[[], bool] = lambda: False

    def __post_init__(self) -> None:
        if not callable(self.checkpoint) or not callable(self.cancel_requested):
            raise ValueError("bundle execution hooks must be callable")


@dataclass(frozen=True, slots=True)
class BundleAssemblyResult:
    status: BundleAssemblyStatus
    bundle: ComparisonBundle | None = None
    manifest_ref: ArtifactRef | None = None
    artifact_closure_ref: ArtifactRef | None = None
    referenced_artifacts: tuple[ArtifactRef, ...] = ()
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.status) is not BundleAssemblyStatus:
            raise ValueError("status must be BundleAssemblyStatus")
        published = self.status in {BundleAssemblyStatus.READY, BundleAssemblyStatus.DEGRADED}
        if published != (self.bundle is not None):
            raise ValueError("published statuses require a bundle and failure statuses must not publish one")
        if published:
            if self.manifest_ref is None or self.artifact_closure_ref is None:
                raise ValueError("published result requires manifest and closure refs")
        elif self.manifest_ref is not None or self.artifact_closure_ref is not None:
            raise ValueError("failed result must not publish manifest or closure refs")
        _optional_ref(self.manifest_ref, "manifest_ref")
        _optional_ref(self.artifact_closure_ref, "artifact_closure_ref")
        if type(self.referenced_artifacts) is not tuple or any(
            type(item) is not ArtifactRef for item in self.referenced_artifacts
        ):
            raise ValueError("referenced_artifacts must contain ArtifactRef")
        if len(set(self.referenced_artifacts)) != len(self.referenced_artifacts):
            raise ValueError("referenced_artifacts must be unique")
        if type(self.diagnostics) is not tuple or any(
            type(item) is not str or item == "" for item in self.diagnostics
        ):
            raise ValueError("diagnostics must contain non-empty strings")


BundleInputSet: TypeAlias = tuple[BundleInput, ...]


def canonical_bundle_json(document: dict[str, object]) -> bytes:
    return canonicalize_json_value(document)
