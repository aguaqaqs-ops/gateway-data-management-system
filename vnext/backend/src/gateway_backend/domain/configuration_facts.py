"""Immutable source-time and complete canonical content facts owned by the business lifecycle."""
from __future__ import annotations

from gateway_backend.artifacts.types import validate_artifact_id

from dataclasses import asdict, dataclass, fields
from datetime import datetime
import re
from typing import Self, cast

from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

CONFIGURATION_TIME_RULE = "gateway-vnext/configuration-generated-time/v1"
CONFIGURATION_FACTS_SCHEMA = "backend-vnext/configuration-facts/v1"
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{0,5}[1-9])?Z\Z")


def _text(value: object, name: str) -> None:
    if type(value) is not str or not value:
        raise ValueError(f"{name} must be a non-empty string")


def _digest(value: object) -> None:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ValueError("configuration facts require a sha256 digest")


def _integer(value: object) -> None:
    if type(value) is not int or not 0 <= value <= 9007199254740991:
        raise ValueError("configuration facts count/version must be a non-negative safe integer")


def _shape(value: object, cls: type[object]) -> dict[str, object]:
    if type(value) is not dict or set(value) != {field.name for field in fields(cls)}:  # type: ignore[arg-type]
        raise ValueError(f"invalid {cls.__name__} fields")
    return cast(dict[str, object], value)


@dataclass(frozen=True, slots=True)
class ConfigurationGeneratedTime:
    rule_id: str
    status: str
    selected_time_utc: str | None
    max_valid_time_utc: str | None
    valid_count: int
    empty_count: int
    invalid_count: int
    last_valid_source_row: int | None
    max_valid_source_row: int | None
    last_not_max: bool

    def __post_init__(self) -> None:
        if self.rule_id != CONFIGURATION_TIME_RULE:
            raise ValueError("configuration time rule identity mismatch")
        for count in (self.valid_count, self.empty_count, self.invalid_count):
            _integer(count)
        if type(self.last_not_max) is not bool:
            raise ValueError("last_not_max must be bool")
        total = self.valid_count + self.empty_count + self.invalid_count
        expected = "VALID" if self.valid_count else (
            "NO_ROWS" if total == 0 else "NO_VALUE" if self.invalid_count == 0 else "NO_VALID_VALUE"
        )
        if self.status in {"TABLE_ABSENT", "COLUMN_ABSENT"}:
            if total:
                raise ValueError("absent table/column cannot have value counts")
        elif self.status != expected:
            raise ValueError("configuration time status does not match counts")
        times = (self.selected_time_utc, self.max_valid_time_utc)
        rows = (self.last_valid_source_row, self.max_valid_source_row)
        if not self.valid_count:
            if any(value is not None for value in (*times, *rows)) or self.last_not_max:
                raise ValueError("missing time cannot publish an instant or source ordinal")
            return
        instants = []
        for value in times:
            if type(value) is not str or _UTC.fullmatch(value) is None:
                raise ValueError("configuration time must use canonical UTC")
            # Validate only native canonical output, never extract SQL values here.
            instants.append(datetime.fromisoformat(value[:-1] + "+00:00"))
        for row in rows:
            _integer(row)
            if cast(int, row) < 1 or cast(int, row) > total:
                raise ValueError("configuration time source ordinal out of range")
        if cast(int, self.max_valid_source_row) > cast(int, self.last_valid_source_row):
            raise ValueError("max source ordinal follows last valid source ordinal")
        if instants[0] > instants[1] or self.last_not_max != (instants[0] < instants[1]):
            raise ValueError("configuration time maximum/last_not_max mismatch")

    @classmethod
    def from_document(cls, value: object) -> Self:
        return cls(**_shape(value, cls))  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class CanonicalContentIdentity:
    canonical_state_digest: str
    storage_projection_ruleset_digest: str
    storage_projection_version: str
    scalar_encoding_version: int

    def __post_init__(self) -> None:
        _digest(self.canonical_state_digest)
        _digest(self.storage_projection_ruleset_digest)
        _text(self.storage_projection_version, "storage_projection_version")
        _integer(self.scalar_encoding_version)
        if self.scalar_encoding_version != 1 or self.storage_projection_version != "3":
            raise ValueError("unsupported configuration content projection/scalar encoding version")

    @classmethod
    def from_document(cls, value: object) -> Self:
        return cls(**_shape(value, cls))  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ConfigurationSideFacts:
    content_identity: CanonicalContentIdentity
    generated_time: ConfigurationGeneratedTime | None
    source_artifact_id: str | None
    sql_source_digest: str | None

    def __post_init__(self) -> None:
        if type(self.content_identity) is not CanonicalContentIdentity:
            raise ValueError("configuration side requires content identity")
        if self.generated_time is None:
            if self.source_artifact_id is not None or self.sql_source_digest is not None:
                raise ValueError("empty initial side cannot have source bindings")
        else:
            if type(self.generated_time) is not ConfigurationGeneratedTime:
                raise ValueError("configuration side requires native time facts")
            if type(self.source_artifact_id) is not str:
                raise ValueError("source_artifact_id must be a backend artifact ID")
            validate_artifact_id(self.source_artifact_id)
            _digest(self.sql_source_digest)

    @classmethod
    def from_document(cls, value: object) -> Self:
        raw = _shape(value, cls)
        return cls(
            content_identity=CanonicalContentIdentity.from_document(raw["content_identity"]),
            generated_time=None if raw["generated_time"] is None else ConfigurationGeneratedTime.from_document(raw["generated_time"]),
            source_artifact_id=cast(str | None, raw["source_artifact_id"]),
            sql_source_digest=cast(str | None, raw["sql_source_digest"]),
        )


@dataclass(frozen=True, slots=True)
class ConfigurationFacts:
    schema: str
    operation_id: str
    workspace_id: str
    upload_revision_id: str
    generation: int
    repository_id: str
    business_baseline_node_id: str
    business_baseline_commit_id: str
    baseline_head_version: int
    baseline_is_initial: bool
    baseline_source_submission_id: str | None
    initial_origin: str
    baseline_content_identity: CanonicalContentIdentity
    initial: ConfigurationSideFacts
    modified: ConfigurationSideFacts

    def __post_init__(self) -> None:
        if self.schema != CONFIGURATION_FACTS_SCHEMA:
            raise ValueError("configuration facts schema mismatch")
        for name in ("operation_id", "workspace_id", "upload_revision_id", "repository_id", "business_baseline_node_id", "business_baseline_commit_id"):
            _text(getattr(self, name), name)
        _integer(self.generation)
        _integer(self.baseline_head_version)
        if type(self.baseline_is_initial) is not bool:
            raise ValueError("baseline_is_initial must be bool")
        if self.baseline_is_initial:
            if self.baseline_source_submission_id is not None:
                raise ValueError("INITIAL baseline cannot reference a submission")
        else:
            _text(self.baseline_source_submission_id, "baseline_source_submission_id")
        if type(self.baseline_content_identity) is not CanonicalContentIdentity or any(type(side) is not ConfigurationSideFacts for side in (self.initial, self.modified)):
            raise ValueError("configuration facts require complete side/content identities")
        if self.modified.generated_time is None:
            raise ValueError("modified side requires source time facts")
        if self.initial_origin == "UPLOADED":
            if self.initial.generated_time is None:
                raise ValueError("uploaded initial requires source time facts")
            initial_identity = self.initial.content_identity
            modified_identity = self.modified.content_identity
            if (initial_identity.storage_projection_ruleset_digest, initial_identity.storage_projection_version, initial_identity.scalar_encoding_version) != (modified_identity.storage_projection_ruleset_digest, modified_identity.storage_projection_version, modified_identity.scalar_encoding_version):
                raise ValueError("uploaded configuration facts rules/projection/scalar identity mismatch")
        elif self.initial_origin in {"BASELINE_REUSED", "INITIAL_EMPTY"}:
            if self.initial.content_identity != self.baseline_content_identity:
                raise ValueError("reused initial must match exact baseline content identity")
            if (self.initial_origin == "INITIAL_EMPTY") != self.baseline_is_initial or (self.initial.generated_time is None) != self.baseline_is_initial:
                raise ValueError("reused initial applicability does not match baseline")
        else:
            raise ValueError("invalid initial origin")

    @property
    def facts_digest(self) -> str:
        return raw_blob_digest(canonicalize_json_value(asdict(self))).value

    def to_document(self) -> dict[str, object]:
        return {"facts": asdict(self), "facts_digest": self.facts_digest}

    @classmethod
    def from_document(cls, value: object) -> Self:
        if type(value) is not dict or set(value) != {"facts", "facts_digest"}:
            raise ValueError("configuration facts envelope fields mismatch")
        raw = _shape(value["facts"], cls)
        nested = {key: raw[key] for key in raw if key not in {"initial", "modified", "baseline_content_identity"}}
        result = cls(**nested,  # type: ignore[arg-type]
            baseline_content_identity=CanonicalContentIdentity.from_document(raw["baseline_content_identity"]),
            initial=ConfigurationSideFacts.from_document(raw["initial"]),
            modified=ConfigurationSideFacts.from_document(raw["modified"]))
        if value["facts_digest"] != result.facts_digest:
            raise ValueError("configuration facts digest mismatch")
        return result

    def assert_binding(self, *, workspace_id: str, upload_revision_id: str, generation: int,
                       repository_id: str, business_baseline_node_id: str,
                       business_baseline_commit_id: str, baseline_head_version: int | None = None,
                       operation_id: str | None = None, modified_digest: str | None = None) -> None:
        expected = {"workspace_id": workspace_id, "upload_revision_id": upload_revision_id, "generation": generation,
            "repository_id": repository_id, "business_baseline_node_id": business_baseline_node_id,
            "business_baseline_commit_id": business_baseline_commit_id}
        if baseline_head_version is not None:
            expected["baseline_head_version"] = baseline_head_version
        if operation_id is not None:
            expected["operation_id"] = operation_id
        if any(getattr(self, key) != value for key, value in expected.items()):
            raise ValueError("configuration facts input/baseline binding mismatch")
        if modified_digest is not None and self.modified.content_identity.canonical_state_digest != modified_digest:
            raise ValueError("configuration facts modified content binding mismatch")

    def assert_source_artifacts(self, source_artifact_refs: tuple[str, ...]) -> None:
        uploaded_sources = (self.modified.source_artifact_id,) + (
            (self.initial.source_artifact_id,) if self.initial_origin == "UPLOADED" else ())
        if any(source not in source_artifact_refs for source in uploaded_sources):
            raise ValueError("configuration source artifacts do not match frozen sources")
