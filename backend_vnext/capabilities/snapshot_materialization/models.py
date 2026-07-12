from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from enum import StrEnum

from ...artifacts.manifest import ArtifactRef
from ...core.digests import DigestRef
from ...core.diagnostics import DiagnosticRecord
from ...core.identifiers import canonical_identifier
from .versions import (
    ROW_MATERIALIZATION_PROFILE,
    ROW_LAYOUT_DIGEST_VERSION,
    SNAPSHOT_DIGEST_CONTRACT_VERSION,
    SCALAR_ENCODING_VERSION,
    SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION,
    SNAPSHOT_SUMMARY_SCHEMA_VERSION,
    SQL_PARSER_VERSION,
    SQL_DUMP_SOURCE_CONTRACT_VERSION,
    TABLE_RULESET_VERSION,
)

PROJECTION_DIGEST_POLICY_DISABLED = "DISABLED"
PROJECTION_DIGEST_POLICY_FINAL_ONLY = "FINAL_ONLY"
PROJECTION_DIGEST_POLICY_PROVISIONAL_AND_FINAL = "PROVISIONAL_AND_FINAL"
PROJECTION_DIGEST_POLICIES = frozenset(
    {
        PROJECTION_DIGEST_POLICY_DISABLED,
        PROJECTION_DIGEST_POLICY_FINAL_ONLY,
        PROJECTION_DIGEST_POLICY_PROVISIONAL_AND_FINAL,
    }
)

def _coerce_digest(value: DigestRef | str | None) -> DigestRef | None:
    if value is None:
        return None
    if isinstance(value, DigestRef):
        return value
    return DigestRef.parse(str(value))


def _coerce_optional_text(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string or None")
    return value


def _diagnostics_payload(
    diagnostics: Sequence[DiagnosticRecord],
) -> tuple[DiagnosticRecord, ...]:
    return tuple(diagnostics)


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return value


def _require_sequence(value: object, field_name: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence")
    return value


def _optional_payload_text(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{field_name} must be a non-empty string or None")
    return value


def _require_text(payload: Mapping[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    return _require_text_value(value, field_name)


def _require_text_value(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{field_name} must be a non-empty string")
    return value


def _optional_payload_int(value: object, *, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer or None")
    return value


def _optional_payload_datetime(value: object, *, field_name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{field_name} must be an ISO datetime string or None")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed


def _optional_payload_digest(value: object, *, field_name: str) -> DigestRef | None:
    if value is None:
        return None
    if isinstance(value, DigestRef):
        return value
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{field_name} must be a digest ref string or None")
    return DigestRef.parse(value)


class SnapshotMaterializationStage(StrEnum):
    PROVISIONAL = "PROVISIONAL"
    FINAL = "FINAL"


class SnapshotProjectionDigestAuthority(StrEnum):
    FINAL = "FINAL"
    PROVISIONAL_FAST = "PROVISIONAL_FAST"


@dataclass(frozen=True, slots=True)
class SnapshotTableColumn:
    name: str
    display_name: str | None = None
    scalar_type: str | None = None
    nullable: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("column name must be a non-empty string")
        if self.display_name is not None and (
            not isinstance(self.display_name, str) or not self.display_name.strip()
        ):
            raise ValueError("display_name must be a non-empty string or None")
        if self.scalar_type is not None and (
            not isinstance(self.scalar_type, str) or not self.scalar_type.strip()
        ):
            raise ValueError("scalar_type must be a non-empty string or None")
        if self.nullable is not None and not isinstance(self.nullable, bool):
            raise TypeError("nullable must be a bool or None")
        object.__setattr__(self, "name", canonical_identifier(self.name))
        if self.display_name is None:
            object.__setattr__(self, "display_name", self.name)

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "scalar_type": self.scalar_type,
            "nullable": self.nullable,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "SnapshotTableColumn":
        return cls(
            name=_require_text(payload, "name"),
            display_name=_optional_payload_text(payload.get("display_name"), field_name="display_name"),
            scalar_type=_optional_payload_text(payload.get("scalar_type"), field_name="scalar_type"),
            nullable=payload.get("nullable"),
        )


def _require_payload_digest(payload: Mapping[str, object], field_name: str) -> DigestRef:
    digest = _optional_payload_digest(payload.get(field_name), field_name=field_name)
    if digest is None:
        raise ValueError(f"{field_name} is required")
    return digest


def _canonical_identifier_tuple(values: Sequence[str], *, field_name: str) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field_name} must contain non-empty strings")
        canonical_value = canonical_identifier(value)
        if not canonical_value:
            raise ValueError(f"{field_name} must not contain empty identifiers")
        if canonical_value in seen:
            raise ValueError(f"duplicate canonical identifier in {field_name}: {canonical_value}")
        seen.add(canonical_value)
        normalized.append(canonical_value)
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class SnapshotProjectionDigest:
    projection_schema_digest: DigestRef | str
    selected_columns: tuple[str, ...]
    ignored_columns: tuple[str, ...] = field(default_factory=tuple)
    effective_compare_key: tuple[str, ...] = field(default_factory=tuple)
    row_identity_columns: tuple[str, ...] = field(default_factory=tuple)
    row_identity_digest: DigestRef | str | None = None
    projected_row_value_digest: DigestRef | str | None = None
    projection_logical_digest: DigestRef | str | None = None
    table_ruleset_version: str = TABLE_RULESET_VERSION
    projection_contract_version: str = "backend-vnext/comparison-projection/v1"
    scalar_encoding_version: str = SCALAR_ENCODING_VERSION
    digest_authority: SnapshotProjectionDigestAuthority | str = SnapshotProjectionDigestAuthority.FINAL

    def __post_init__(self) -> None:
        object.__setattr__(self, "projection_schema_digest", _coerce_digest(self.projection_schema_digest))
        object.__setattr__(self, "row_identity_digest", _coerce_digest(self.row_identity_digest))
        object.__setattr__(self, "projected_row_value_digest", _coerce_digest(self.projected_row_value_digest))
        object.__setattr__(self, "projection_logical_digest", _coerce_digest(self.projection_logical_digest))
        if self.projection_schema_digest is None:
            raise ValueError("projection_schema_digest is required")
        if self.row_identity_digest is None:
            raise ValueError("row_identity_digest is required")
        if self.projected_row_value_digest is None:
            raise ValueError("projected_row_value_digest is required")
        if self.projection_logical_digest is None:
            raise ValueError("projection_logical_digest is required")
        object.__setattr__(
            self,
            "selected_columns",
            _canonical_identifier_tuple(self.selected_columns, field_name="selected_columns"),
        )
        object.__setattr__(
            self,
            "ignored_columns",
            _canonical_identifier_tuple(self.ignored_columns, field_name="ignored_columns"),
        )
        object.__setattr__(
            self,
            "effective_compare_key",
            _canonical_identifier_tuple(self.effective_compare_key, field_name="effective_compare_key"),
        )
        object.__setattr__(
            self,
            "row_identity_columns",
            _canonical_identifier_tuple(self.row_identity_columns, field_name="row_identity_columns"),
        )
        selected_set = set(self.selected_columns)
        for field_name in ("effective_compare_key", "row_identity_columns"):
            missing = set(getattr(self, field_name)) - selected_set
            if missing:
                raise ValueError(f"{field_name} contains columns not present in selected_columns: {sorted(missing)}")
        for field_name in (
            "table_ruleset_version",
            "projection_contract_version",
            "scalar_encoding_version",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        object.__setattr__(self, "digest_authority", SnapshotProjectionDigestAuthority(self.digest_authority))

    def to_payload(self) -> dict[str, object]:
        return {
            "projection_schema_digest": self.projection_schema_digest.to_payload(),
            "selected_columns": list(self.selected_columns),
            "ignored_columns": list(self.ignored_columns),
            "effective_compare_key": list(self.effective_compare_key),
            "row_identity_columns": list(self.row_identity_columns),
            "row_identity_digest": self.row_identity_digest.to_payload(),
            "projected_row_value_digest": self.projected_row_value_digest.to_payload(),
            "projection_logical_digest": self.projection_logical_digest.to_payload(),
            "table_ruleset_version": self.table_ruleset_version,
            "projection_contract_version": self.projection_contract_version,
            "scalar_encoding_version": self.scalar_encoding_version,
            "digest_authority": self.digest_authority.value,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "SnapshotProjectionDigest":
        return cls(
            projection_schema_digest=_require_payload_digest(payload, "projection_schema_digest"),
            selected_columns=tuple(
                _require_text_value(item, "selected_columns item")
                for item in _require_sequence(payload.get("selected_columns"), "selected_columns")
            ),
            ignored_columns=tuple(
                _require_text_value(item, "ignored_columns item")
                for item in _require_sequence(payload.get("ignored_columns", ()), "ignored_columns")
            ),
            effective_compare_key=tuple(
                _require_text_value(item, "effective_compare_key item")
                for item in _require_sequence(payload.get("effective_compare_key", ()), "effective_compare_key")
            ),
            row_identity_columns=tuple(
                _require_text_value(item, "row_identity_columns item")
                for item in _require_sequence(payload.get("row_identity_columns", ()), "row_identity_columns")
            ),
            row_identity_digest=_require_payload_digest(payload, "row_identity_digest"),
            projected_row_value_digest=_require_payload_digest(payload, "projected_row_value_digest"),
            projection_logical_digest=_require_payload_digest(payload, "projection_logical_digest"),
            table_ruleset_version=_require_text(payload, "table_ruleset_version"),
            projection_contract_version=_require_text(payload, "projection_contract_version"),
            scalar_encoding_version=_require_text(payload, "scalar_encoding_version"),
            digest_authority=_require_text(payload, "digest_authority"),
        )


@dataclass(frozen=True, slots=True)
class SnapshotTableDescriptor:
    table_name: str
    display_table_name: str | None = None
    table_role: str | None = None
    columns: tuple[SnapshotTableColumn, ...] = field(default_factory=tuple)
    compare_key_columns: tuple[str, ...] = field(default_factory=tuple)
    row_count: int = 0
    materialization_stage: str = SnapshotMaterializationStage.FINAL.value
    source_ddl_digest: DigestRef | str | None = None
    table_raw_sql_digest: DigestRef | str | None = None
    fast_row_digest: DigestRef | str | None = None
    base_table_fingerprint: DigestRef | str | None = None
    compare_schema_digest: DigestRef | str | None = None
    raw_content_digest: DigestRef | str | None = None
    business_content_digest: DigestRef | str | None = None
    table_ruleset_version: str = TABLE_RULESET_VERSION
    row_materialization_profile: str = ROW_MATERIALIZATION_PROFILE
    scalar_encoding_version: str = SCALAR_ENCODING_VERSION
    degraded_reason: str | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    canonical_artifact_ref: str | None = None
    previous_canonical_artifact_ref: str | None = None
    projection_digests: tuple[SnapshotProjectionDigest, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.table_name, str) or not self.table_name.strip():
            raise ValueError("table_name must be a non-empty string")
        if self.display_table_name is not None and (
            not isinstance(self.display_table_name, str)
            or not self.display_table_name.strip()
        ):
            raise ValueError("display_table_name must be a non-empty string or None")
        if self.table_role is not None and (
            not isinstance(self.table_role, str) or not self.table_role.strip()
        ):
            raise ValueError("table_role must be a non-empty string or None")
        if not isinstance(self.row_count, int) or isinstance(self.row_count, bool) or self.row_count < 0:
            raise ValueError("row_count must be a non-negative integer")
        materialization_stage = SnapshotMaterializationStage(self.materialization_stage)
        object.__setattr__(self, "materialization_stage", materialization_stage.value)
        if self.degraded_reason is not None and (
            not isinstance(self.degraded_reason, str)
            or not self.degraded_reason.strip()
        ):
            raise ValueError("degraded_reason must be a non-empty string or None")
        if not isinstance(self.table_ruleset_version, str) or not self.table_ruleset_version:
            raise ValueError("table_ruleset_version must be a non-empty string")
        if not isinstance(self.row_materialization_profile, str) or not self.row_materialization_profile:
            raise ValueError("row_materialization_profile must be a non-empty string")
        if not isinstance(self.scalar_encoding_version, str) or not self.scalar_encoding_version:
            raise ValueError("scalar_encoding_version must be a non-empty string")
        object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        if self.display_table_name is None:
            object.__setattr__(self, "display_table_name", self.table_name)
        normalized_columns = tuple(self.columns)
        seen_columns: set[str] = set()
        for column in normalized_columns:
            if not isinstance(column, SnapshotTableColumn):
                raise TypeError("columns must contain SnapshotTableColumn values")
            if column.name in seen_columns:
                raise ValueError(f"duplicate canonical column name: {column.name}")
            seen_columns.add(column.name)
        object.__setattr__(self, "columns", normalized_columns)
        normalized_keys = tuple(canonical_identifier(column) for column in self.compare_key_columns)
        if normalized_keys and not set(normalized_keys).issubset(seen_columns):
            missing = sorted(set(normalized_keys) - seen_columns)
            raise ValueError(f"compare_key_columns missing columns: {missing}")
        object.__setattr__(self, "compare_key_columns", normalized_keys)
        object.__setattr__(self, "source_ddl_digest", _coerce_digest(self.source_ddl_digest))
        object.__setattr__(self, "table_raw_sql_digest", _coerce_digest(self.table_raw_sql_digest))
        object.__setattr__(self, "fast_row_digest", _coerce_digest(self.fast_row_digest))
        object.__setattr__(self, "base_table_fingerprint", _coerce_digest(self.base_table_fingerprint))
        object.__setattr__(
            self,
            "canonical_artifact_ref",
            _coerce_optional_text(self.canonical_artifact_ref, "canonical_artifact_ref"),
        )
        object.__setattr__(
            self,
            "previous_canonical_artifact_ref",
            _coerce_optional_text(
                self.previous_canonical_artifact_ref,
                "previous_canonical_artifact_ref",
            ),
        )
        if self.base_table_fingerprint is None and self.table_raw_sql_digest is not None:
            object.__setattr__(self, "base_table_fingerprint", self.table_raw_sql_digest)
        if self.table_raw_sql_digest is None and self.base_table_fingerprint is not None:
            object.__setattr__(self, "table_raw_sql_digest", self.base_table_fingerprint)
        if (
            self.table_raw_sql_digest is not None
            and self.base_table_fingerprint is not None
            and self.table_raw_sql_digest != self.base_table_fingerprint
        ):
            raise ValueError("table_raw_sql_digest and base_table_fingerprint must match when both are provided")
        object.__setattr__(self, "compare_schema_digest", _coerce_digest(self.compare_schema_digest))
        object.__setattr__(self, "raw_content_digest", _coerce_digest(self.raw_content_digest))
        object.__setattr__(self, "business_content_digest", _coerce_digest(self.business_content_digest))
        object.__setattr__(self, "diagnostics", _diagnostics_payload(self.diagnostics))
        normalized_projection_digests: list[SnapshotProjectionDigest] = []
        for digest in self.projection_digests:
            if not isinstance(digest, SnapshotProjectionDigest):
                raise TypeError("projection_digests must contain SnapshotProjectionDigest values")
            normalized_projection_digests.append(digest)
        object.__setattr__(self, "projection_digests", tuple(normalized_projection_digests))
        if self.compare_schema_digest is None:
            raise ValueError("compare_schema_digest is required")
        if self.materialization_stage == SnapshotMaterializationStage.FINAL.value:
            if self.raw_content_digest is None:
                raise ValueError("raw_content_digest is required for FINAL descriptors")
        elif self.raw_content_digest is None and self.materialization_digest is None:
            raise ValueError("provisional descriptors require a table digest")
        if self.business_content_digest is not None and self.raw_content_digest is None:
            raise ValueError("business_content_digest requires raw_content_digest")
        if (
            self.business_content_digest is not None
            and self.raw_content_digest is not None
            and self.business_content_digest != self.raw_content_digest
        ):
            raise ValueError("business_content_digest and raw_content_digest must match when both are provided")
        if self.business_content_digest is None and self.raw_content_digest is not None:
            object.__setattr__(self, "business_content_digest", self.raw_content_digest)

    def to_payload(self) -> dict[str, object]:
        return {
            "table_name": self.table_name,
            "display_table_name": self.display_table_name,
            "table_role": self.table_role,
            "columns": [column.to_payload() for column in self.columns],
            "compare_key_columns": list(self.compare_key_columns),
            "row_count": self.row_count,
            "materialization_stage": self.materialization_stage,
            "source_ddl_digest": (
                None if self.source_ddl_digest is None else self.source_ddl_digest.to_payload()
            ),
            "table_raw_sql_digest": (
                None if self.table_raw_sql_digest is None else self.table_raw_sql_digest.to_payload()
            ),
            "fast_row_digest": (
                None if self.fast_row_digest is None else self.fast_row_digest.to_payload()
            ),
            "base_table_fingerprint": (
                None if self.base_table_fingerprint is None else self.base_table_fingerprint.to_payload()
            ),
            "compare_schema_digest": self.compare_schema_digest.to_payload(),
            "raw_content_digest": self.raw_content_digest.to_payload() if self.raw_content_digest is not None else None,
            "business_content_digest": (
                None if self.business_content_digest is None else self.business_content_digest.to_payload()
            ),
            "table_ruleset_version": self.table_ruleset_version,
            "row_materialization_profile": self.row_materialization_profile,
            "scalar_encoding_version": self.scalar_encoding_version,
            "degraded_reason": self.degraded_reason,
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
            "canonical_artifact_ref": self.canonical_artifact_ref,
            "previous_canonical_artifact_ref": self.previous_canonical_artifact_ref,
            "projection_digests": [digest.to_payload() for digest in self.projection_digests],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "SnapshotTableDescriptor":
        columns_payload = _require_sequence(payload.get("columns"), "columns")
        diagnostics_payload = payload.get("diagnostics")
        if diagnostics_payload is None:
            diagnostics: tuple[DiagnosticRecord, ...] = tuple()
        else:
            diagnostics = tuple(
                DiagnosticRecord.from_payload(_require_mapping(item, "diagnostics item"))
                for item in _require_sequence(diagnostics_payload, "diagnostics")
            )
        projection_digests_payload = payload.get("projection_digests")
        if projection_digests_payload is None:
            projection_digests: tuple[SnapshotProjectionDigest, ...] = tuple()
        else:
            projection_digests = tuple(
                SnapshotProjectionDigest.from_payload(_require_mapping(item, "projection_digests item"))
                for item in _require_sequence(projection_digests_payload, "projection_digests")
            )
        return cls(
            table_name=_require_text(payload, "table_name"),
            display_table_name=_optional_payload_text(
                payload.get("display_table_name"),
                field_name="display_table_name",
            ),
            table_role=_optional_payload_text(payload.get("table_role"), field_name="table_role"),
            columns=tuple(
                SnapshotTableColumn.from_payload(_require_mapping(item, "columns item"))
                for item in columns_payload
            ),
            compare_key_columns=tuple(
                _require_text_value(item, "compare_key_columns item")
                for item in _require_sequence(payload.get("compare_key_columns"), "compare_key_columns")
            ),
            row_count=_optional_payload_int(payload.get("row_count"), field_name="row_count") or 0,
            materialization_stage=_optional_payload_text(
                payload.get("materialization_stage"),
                field_name="materialization_stage",
            )
            or SnapshotMaterializationStage.FINAL.value,
            source_ddl_digest=_optional_payload_digest(
                payload.get("source_ddl_digest"),
                field_name="source_ddl_digest",
            ),
            table_raw_sql_digest=_optional_payload_digest(
                payload.get("table_raw_sql_digest"),
                field_name="table_raw_sql_digest",
            ),
            fast_row_digest=_optional_payload_digest(
                payload.get("fast_row_digest"),
                field_name="fast_row_digest",
            ),
            base_table_fingerprint=_optional_payload_digest(
                payload.get("base_table_fingerprint"),
                field_name="base_table_fingerprint",
            ),
            compare_schema_digest=_optional_payload_digest(
                payload.get("compare_schema_digest"),
                field_name="compare_schema_digest",
            ),
            raw_content_digest=_optional_payload_digest(
                payload.get("raw_content_digest"),
                field_name="raw_content_digest",
            ),
            business_content_digest=_optional_payload_digest(
                payload.get("business_content_digest"),
                field_name="business_content_digest",
            ),
            table_ruleset_version=_require_text(payload, "table_ruleset_version"),
            row_materialization_profile=_require_text(payload, "row_materialization_profile"),
            scalar_encoding_version=_require_text(payload, "scalar_encoding_version"),
            degraded_reason=_optional_payload_text(
                payload.get("degraded_reason"),
                field_name="degraded_reason",
            ),
            diagnostics=diagnostics,
            canonical_artifact_ref=_optional_payload_text(
                payload.get("canonical_artifact_ref"),
                field_name="canonical_artifact_ref",
            ),
            previous_canonical_artifact_ref=_optional_payload_text(
                payload.get("previous_canonical_artifact_ref"),
                field_name="previous_canonical_artifact_ref",
            ),
            projection_digests=projection_digests,
        )

    @property
    def schema_digest(self) -> DigestRef | None:
        return self.compare_schema_digest

    @property
    def raw_ddl_digest(self) -> DigestRef | None:
        return self.source_ddl_digest

    @property
    def materialization_digest(self) -> DigestRef | None:
        """Prefer canonical raw content, then the provisional fast path."""
        return self.raw_content_digest or self.fast_row_digest

    @property
    def row_layout_digest(self) -> DigestRef | None:
        """Digest the physical export layout, not the table semantic identity."""
        if self.raw_content_digest is None:
            return None
        return DigestRef.from_payload(
            {
                "row_layout_digest_version": ROW_LAYOUT_DIGEST_VERSION,
                "raw_content_digest": self.raw_content_digest.to_payload(),
                "row_materialization_profile": self.row_materialization_profile,
                "scalar_encoding_version": self.scalar_encoding_version,
                "columns": [
                    {
                        "name": column.name,
                        "scalar_type": column.scalar_type,
                        "nullable": column.nullable,
                    }
                    for column in self.columns
                ],
            }
        )


def build_canonical_artifact_ref(
    *,
    table_name: str,
    base_table_fingerprint: DigestRef | str | None,
    compare_schema_digest: DigestRef | str | None,
    raw_content_digest: DigestRef | str | None,
    row_count: int,
    table_ruleset_version: str,
    row_materialization_profile: str,
    scalar_encoding_version: str,
) -> str:
    base_digest = _coerce_digest(base_table_fingerprint)
    schema_digest = _coerce_digest(compare_schema_digest)
    content_digest = _coerce_digest(raw_content_digest)
    if base_digest is None:
        raise ValueError("canonical artifact ref requires base_table_fingerprint")
    if schema_digest is None:
        raise ValueError("canonical artifact ref requires compare_schema_digest")
    if content_digest is None:
        raise ValueError("canonical artifact ref requires raw_content_digest")
    return DigestRef.from_payload(
        {
            "canonical_artifact_ref_version": "backend-vnext/canonical-artifact-ref/v1",
            "table_name": canonical_identifier(table_name),
            "base_table_fingerprint": base_digest.to_payload(),
            "compare_schema_digest": schema_digest.to_payload(),
            "raw_content_digest": content_digest.to_payload(),
            "row_count": row_count,
            "table_ruleset_version": table_ruleset_version,
            "row_materialization_profile": row_materialization_profile,
            "scalar_encoding_version": scalar_encoding_version,
        }
    ).to_payload()


def _canonical_ref_compatibility_key(descriptor: SnapshotTableDescriptor) -> tuple[object, ...]:
    raw_digest = descriptor.raw_content_digest
    if raw_digest is None:
        raise ValueError("canonical artifact refs require FINAL descriptors with raw_content_digest")
    return (
        descriptor.table_role,
        descriptor.compare_schema_digest.to_payload(),
        raw_digest.to_payload(),
        descriptor.business_content_digest.to_payload()
        if descriptor.business_content_digest is not None
        else None,
        descriptor.row_count,
        tuple(descriptor.compare_key_columns),
        descriptor.table_ruleset_version,
        descriptor.row_materialization_profile,
        descriptor.scalar_encoding_version,
    )


def _descriptor_sort_key(descriptor: SnapshotTableDescriptor) -> tuple[str, str]:
    return (descriptor.table_name.casefold(), descriptor.table_name)


def _previous_summary_table_map(
    previous_summary: "SnapshotSummary | None",
) -> dict[str, SnapshotTableDescriptor]:
    if previous_summary is None:
        return {}
    if previous_summary.materialization_stage != SnapshotMaterializationStage.FINAL.value:
        raise ValueError("previous_summary must be a FINAL SnapshotSummary")
    return {descriptor.table_name: descriptor for descriptor in previous_summary.tables}


def _build_current_canonical_ref(
    group: Sequence[SnapshotTableDescriptor],
    *,
    preferred_head_name: str | None = None,
) -> str:
    if not group:
        raise ValueError("canonical group must not be empty")
    sorted_group = sorted(group, key=_descriptor_sort_key)
    canonical_head = next(
        (
            descriptor
            for descriptor in sorted_group
            if preferred_head_name is not None and descriptor.table_name == preferred_head_name
        ),
        sorted_group[0],
    )
    return build_canonical_artifact_ref(
        table_name=canonical_head.table_name,
        base_table_fingerprint=canonical_head.base_table_fingerprint,
        compare_schema_digest=canonical_head.compare_schema_digest,
        raw_content_digest=canonical_head.raw_content_digest,
        row_count=canonical_head.row_count,
        table_ruleset_version=canonical_head.table_ruleset_version,
        row_materialization_profile=canonical_head.row_materialization_profile,
        scalar_encoding_version=canonical_head.scalar_encoding_version,
    )


def _apply_canonical_ref_group(
    group: Sequence[SnapshotTableDescriptor],
    *,
    canonical_ref: str,
    previous_ref: str | None,
) -> list[SnapshotTableDescriptor]:
    finalized: list[SnapshotTableDescriptor] = []
    for descriptor in sorted(group, key=_descriptor_sort_key):
        previous_canonical_artifact_ref = descriptor.previous_canonical_artifact_ref
        if (
            descriptor.canonical_artifact_ref is not None
            and descriptor.canonical_artifact_ref != canonical_ref
        ):
            previous_canonical_artifact_ref = descriptor.canonical_artifact_ref
        elif previous_ref is not None and previous_ref != canonical_ref:
            previous_canonical_artifact_ref = previous_ref
        finalized.append(
            replace(
                descriptor,
                canonical_artifact_ref=canonical_ref,
                previous_canonical_artifact_ref=previous_canonical_artifact_ref,
            )
        )
    return finalized


def _assign_initial_canonical_artifact_refs(
    descriptors: Sequence[SnapshotTableDescriptor],
) -> tuple[SnapshotTableDescriptor, ...]:
    if not descriptors:
        return tuple()
    grouped: dict[tuple[object, ...], list[SnapshotTableDescriptor]] = {}
    for descriptor in descriptors:
        group_key = _canonical_ref_compatibility_key(descriptor)
        grouped.setdefault(group_key, []).append(descriptor)

    finalized: list[SnapshotTableDescriptor] = []
    for group_key in sorted(grouped, key=repr):
        group = grouped[group_key]
        canonical_ref = _build_current_canonical_ref(group)
        finalized.extend(
            _apply_canonical_ref_group(group, canonical_ref=canonical_ref, previous_ref=None)
        )
    return tuple(sorted(finalized, key=_descriptor_sort_key))


def assign_canonical_artifact_refs(
    descriptors: Sequence[SnapshotTableDescriptor],
    *,
    previous_summary: "SnapshotSummary | None" = None,
) -> tuple[SnapshotTableDescriptor, ...]:
    if not descriptors:
        return tuple()
    previous_by_table = _previous_summary_table_map(previous_summary)
    if not previous_by_table:
        return _assign_initial_canonical_artifact_refs(descriptors)

    current_by_table = {descriptor.table_name: descriptor for descriptor in descriptors}
    existing_names = set(current_by_table) & set(previous_by_table)
    new_names = set(current_by_table) - set(previous_by_table)

    previous_group_members: dict[str, set[str]] = {}
    previous_group_heads: dict[str, str] = {}
    for previous_descriptor in previous_by_table.values():
        previous_ref = previous_descriptor.canonical_artifact_ref
        if previous_ref is None:
            continue
        previous_group_members.setdefault(previous_ref, set()).add(previous_descriptor.table_name)
        previous_group_heads.setdefault(previous_ref, previous_descriptor.table_name)
        if _descriptor_sort_key(previous_descriptor) < (
            previous_group_heads[previous_ref].casefold(),
            previous_group_heads[previous_ref],
        ):
            previous_group_heads[previous_ref] = previous_descriptor.table_name

    assigned_names: set[str] = set()
    resolved_groups: list[tuple[list[SnapshotTableDescriptor], str | None, str | None]] = []

    for previous_ref in sorted(previous_group_members):
        current_existing = sorted(previous_group_members[previous_ref] & existing_names)
        if not current_existing:
            continue
        partitions: dict[tuple[object, ...], list[SnapshotTableDescriptor]] = {}
        for table_name in current_existing:
            descriptor = current_by_table[table_name]
            partitions.setdefault(_canonical_ref_compatibility_key(descriptor), []).append(descriptor)
        for _, group in sorted(partitions.items(), key=lambda item: repr(item[0])):
            preferred_head = (
                previous_group_heads.get(previous_ref)
                if previous_group_heads.get(previous_ref) in {descriptor.table_name for descriptor in group}
                else None
            )
            current_ref = _build_current_canonical_ref(group, preferred_head_name=preferred_head)
            previous_pointer = previous_ref if current_ref != previous_ref else None
            resolved_groups.append((group, current_ref, previous_pointer))
            assigned_names.update(descriptor.table_name for descriptor in group)

    joinable_groups_by_key: dict[tuple[object, ...], list[tuple[list[SnapshotTableDescriptor], str]]] = {}
    for group, current_ref, _previous_pointer in resolved_groups:
        if current_ref is None:
            continue
        joinable_groups_by_key.setdefault(_canonical_ref_compatibility_key(group[0]), []).append((group, current_ref))

    standalone_new: list[SnapshotTableDescriptor] = []
    for table_name in sorted(new_names):
        descriptor = current_by_table[table_name]
        key = _canonical_ref_compatibility_key(descriptor)
        matches = joinable_groups_by_key.get(key, [])
        if len(matches) == 1:
            matches[0][0].append(descriptor)
            assigned_names.add(table_name)
        else:
            standalone_new.append(descriptor)

    if standalone_new:
        grouped_new: dict[tuple[object, ...], list[SnapshotTableDescriptor]] = {}
        for descriptor in standalone_new:
            grouped_new.setdefault(_canonical_ref_compatibility_key(descriptor), []).append(descriptor)
        for _, group in sorted(grouped_new.items(), key=lambda item: repr(item[0])):
            current_ref = _build_current_canonical_ref(group)
            resolved_groups.append((group, current_ref, None))
            assigned_names.update(descriptor.table_name for descriptor in group)

    orphan_existing = [
        current_by_table[name]
        for name in sorted(existing_names - assigned_names)
    ]
    if orphan_existing:
        finalized_orphans = _assign_initial_canonical_artifact_refs(orphan_existing)
        for descriptor in finalized_orphans:
            previous_descriptor = previous_by_table.get(descriptor.table_name)
            previous_ref = (
                None if previous_descriptor is None else previous_descriptor.canonical_artifact_ref
            )
            resolved_groups.append(([descriptor], descriptor.canonical_artifact_ref, previous_ref))

    finalized: list[SnapshotTableDescriptor] = []
    for group, current_ref, previous_pointer in resolved_groups:
        if current_ref is None:
            raise ValueError("resolved canonical group missing current ref")
        finalized.extend(
            _apply_canonical_ref_group(
                group,
                canonical_ref=current_ref,
                previous_ref=previous_pointer,
            )
        )
    return tuple(sorted(finalized, key=_descriptor_sort_key))


def _provisional_fast_alias_key(descriptor: SnapshotTableDescriptor) -> tuple[object, ...] | None:
    if descriptor.materialization_stage != SnapshotMaterializationStage.PROVISIONAL.value:
        return None
    if descriptor.table_role != "STANDARD_DIFF":
        return None
    if descriptor.table_name == "version_manager":
        return None
    if descriptor.fast_row_digest is None:
        return None
    return (
        descriptor.fast_row_digest.to_payload(),
        tuple(
            (
                column.name,
                column.scalar_type,
                column.nullable,
            )
            for column in descriptor.columns
        ),
        descriptor.row_count,
        tuple(descriptor.compare_key_columns),
        descriptor.table_role,
        descriptor.table_ruleset_version,
        descriptor.row_materialization_profile,
        descriptor.scalar_encoding_version,
    )


def build_provisional_fast_table_aliases(
    summary: "SnapshotSummary",
    *,
    input_role: str,
    pair_id: str,
) -> tuple[dict[str, object], ...]:
    if not isinstance(summary, SnapshotSummary):
        raise TypeError("summary must be a SnapshotSummary")
    if summary.materialization_stage != SnapshotMaterializationStage.PROVISIONAL.value:
        return tuple()
    if not isinstance(input_role, str) or not input_role:
        raise ValueError("input_role must be a non-empty string")
    if not isinstance(pair_id, str) or not pair_id:
        raise ValueError("pair_id must be a non-empty string")

    grouped: dict[tuple[object, ...], list[SnapshotTableDescriptor]] = {}
    for descriptor in summary.tables:
        alias_key = _provisional_fast_alias_key(descriptor)
        if alias_key is None:
            continue
        grouped.setdefault(alias_key, []).append(descriptor)

    aliases: list[dict[str, object]] = []
    for alias_key in sorted(grouped, key=repr):
        group = sorted(grouped[alias_key], key=_descriptor_sort_key)
        if len(group) < 2:
            continue
        canonical_table = group[0].table_name
        for descriptor in group[1:]:
            aliases.append(
                {
                    "logical_table_name": descriptor.table_name,
                    "canonical_table_name": canonical_table,
                    "alias_scope": "PROVISIONAL_FAST",
                    "input_role": input_role,
                    "pair_id": pair_id,
                    "reason": "FAST_ROW_DIGEST_MATCH",
                }
            )
    return tuple(aliases)


def build_canonical_table_aliases(
    summary: "SnapshotSummary",
    *,
    pair_id: str,
) -> tuple[dict[str, object], ...]:
    if not isinstance(summary, SnapshotSummary):
        raise TypeError("summary must be a SnapshotSummary")
    if summary.materialization_stage != SnapshotMaterializationStage.FINAL.value:
        return tuple()
    if not isinstance(pair_id, str) or not pair_id:
        raise ValueError("pair_id must be a non-empty string")

    grouped: dict[str, list[SnapshotTableDescriptor]] = {}
    for descriptor in summary.tables:
        if descriptor.canonical_artifact_ref is None:
            continue
        grouped.setdefault(descriptor.canonical_artifact_ref, []).append(descriptor)

    aliases: list[dict[str, object]] = []
    for canonical_ref in sorted(grouped):
        group = sorted(grouped[canonical_ref], key=_descriptor_sort_key)
        if len(group) < 2:
            continue
        canonical_table = group[0].table_name
        for descriptor in group[1:]:
            aliases.append(
                {
                    "logical_table_name": descriptor.table_name,
                    "canonical_table_name": canonical_table,
                    "alias_scope": "CANONICAL",
                    "pair_id": pair_id,
                    "reason": "CANONICAL_ARTIFACT_REF_MATCH",
                }
            )
    return tuple(aliases)


@dataclass(frozen=True, slots=True)
class SnapshotTable:
    descriptor: SnapshotTableDescriptor
    reader: "SnapshotTableReader"
    raw_create_sql: str

    def __post_init__(self) -> None:
        if not isinstance(self.raw_create_sql, str) or not self.raw_create_sql.strip():
            raise ValueError("raw_create_sql must be a non-empty string")
        if self.reader.descriptor() != self.descriptor:
            raise ValueError("reader descriptor does not match table descriptor")


@dataclass(frozen=True, slots=True)
class SnapshotTableSet:
    snapshot_id: str
    snapshot_digest: DigestRef | str
    table_ruleset_version: str = TABLE_RULESET_VERSION
    tables: Mapping[str, SnapshotTable] = field(default_factory=dict)
    resolution_plan: str | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id.strip():
            raise ValueError("snapshot_id must be a non-empty string")
        if not isinstance(self.table_ruleset_version, str) or not self.table_ruleset_version:
            raise ValueError("table_ruleset_version must be a non-empty string")
        if self.resolution_plan is not None and (
            not isinstance(self.resolution_plan, str) or not self.resolution_plan.strip()
        ):
            raise ValueError("resolution_plan must be a non-empty string or None")
        normalized: dict[str, SnapshotTable] = {}
        for key, table in self.tables.items():
            if not isinstance(key, str) or not key.strip():
                raise TypeError("table names must be strings")
            if not isinstance(table, SnapshotTable):
                raise TypeError("tables must contain SnapshotTable values")
            normalized_key = canonical_identifier(key)
            if normalized_key != table.descriptor.table_name:
                raise ValueError("table mapping key does not match descriptor table name")
            normalized[normalized_key] = table
        object.__setattr__(self, "tables", normalized)
        object.__setattr__(self, "snapshot_digest", _coerce_digest(self.snapshot_digest))
        object.__setattr__(self, "diagnostics", _diagnostics_payload(self.diagnostics))
        if self.snapshot_digest is None:
            raise ValueError("snapshot_digest is required")

    @property
    def table_descriptors(self) -> tuple[SnapshotTableDescriptor, ...]:
        return tuple(table.descriptor for table in self.tables.values())

    @property
    def table_count(self) -> int:
        return len(self.tables)


@dataclass(frozen=True, slots=True)
class SnapshotSourceContext:
    source_kind: str
    source_digest: DigestRef | str | None = None
    source_package_digest: DigestRef | str | None = None
    sql_source_digest: DigestRef | str | None = None
    source_document_ref: object | None = None
    repository_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_kind, str) or not self.source_kind.strip():
            raise ValueError("source_kind must be a non-empty string")
        if self.repository_ref is not None and (
            not isinstance(self.repository_ref, str) or not self.repository_ref.strip()
        ):
            raise ValueError("repository_ref must be a non-empty string or None")
        object.__setattr__(self, "source_digest", _coerce_digest(self.source_digest))
        object.__setattr__(self, "source_package_digest", _coerce_digest(self.source_package_digest))
        object.__setattr__(self, "sql_source_digest", _coerce_digest(self.sql_source_digest))
        if self.source_digest is None:
            object.__setattr__(
                self,
                "source_digest",
                self.sql_source_digest or self.source_package_digest,
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "source_kind": self.source_kind,
            "source_digest": None if self.source_digest is None else self.source_digest.to_payload(),
            "source_package_digest": (
                None if self.source_package_digest is None else self.source_package_digest.to_payload()
            ),
            "sql_source_digest": (
                None if self.sql_source_digest is None else self.sql_source_digest.to_payload()
            ),
            "repository_ref": self.repository_ref,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "SnapshotSourceContext":
        return cls(
            source_kind=_require_text(payload, "source_kind"),
            source_digest=_optional_payload_digest(payload.get("source_digest"), field_name="source_digest"),
            source_package_digest=_optional_payload_digest(
                payload.get("source_package_digest"),
                field_name="source_package_digest",
            ),
            sql_source_digest=_optional_payload_digest(
                payload.get("sql_source_digest"),
                field_name="sql_source_digest",
            ),
            repository_ref=_optional_payload_text(
                payload.get("repository_ref"),
                field_name="repository_ref",
            ),
        )


@dataclass(frozen=True, slots=True)
class SnapshotSummary:
    snapshot_id: str
    snapshot_digest: DigestRef | str
    raw_state_digest: DigestRef | str
    business_state_digest: DigestRef | str | None = None
    materialization_stage: str = SnapshotMaterializationStage.FINAL.value
    parser_version: str = SQL_PARSER_VERSION
    table_ruleset_version: str = TABLE_RULESET_VERSION
    summary_contract_version: str = SNAPSHOT_SUMMARY_SCHEMA_VERSION
    table_count: int = 0
    row_count_total: int | None = None
    configuration_generated_at: datetime | None = None
    tables: tuple[SnapshotTableDescriptor, ...] = field(default_factory=tuple)
    missing_or_unsupported_tables: tuple[str, ...] = field(default_factory=tuple)
    source_context: SnapshotSourceContext | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id.strip():
            raise ValueError("snapshot_id must be a non-empty string")
        materialization_stage = SnapshotMaterializationStage(self.materialization_stage)
        object.__setattr__(self, "materialization_stage", materialization_stage.value)
        for field_name in ("parser_version", "table_ruleset_version", "summary_contract_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if not isinstance(self.table_count, int) or isinstance(self.table_count, bool) or self.table_count < 0:
            raise ValueError("table_count must be a non-negative integer")
        if self.row_count_total is not None and (
            not isinstance(self.row_count_total, int)
            or isinstance(self.row_count_total, bool)
            or self.row_count_total < 0
        ):
            raise ValueError("row_count_total must be a non-negative integer or None")
        if self.configuration_generated_at is not None:
            if not isinstance(self.configuration_generated_at, datetime):
                raise TypeError("configuration_generated_at must be a datetime or None")
            if (
                self.configuration_generated_at.tzinfo is None
                or self.configuration_generated_at.utcoffset() is None
            ):
                raise ValueError("configuration_generated_at must be timezone-aware")
        if self.source_context is not None and not isinstance(self.source_context, SnapshotSourceContext):
            raise TypeError("source_context must be a SnapshotSourceContext or None")
        tables = tuple(self.tables)
        for table in tables:
            if not isinstance(table, SnapshotTableDescriptor):
                raise TypeError("tables must contain SnapshotTableDescriptor values")
        missing = tuple(canonical_identifier(name) for name in self.missing_or_unsupported_tables)
        object.__setattr__(self, "tables", tables)
        object.__setattr__(self, "missing_or_unsupported_tables", missing)
        object.__setattr__(self, "snapshot_digest", _coerce_digest(self.snapshot_digest))
        object.__setattr__(self, "raw_state_digest", _coerce_digest(self.raw_state_digest))
        object.__setattr__(self, "business_state_digest", _coerce_digest(self.business_state_digest))
        object.__setattr__(self, "diagnostics", _diagnostics_payload(self.diagnostics))
        if self.snapshot_digest is None or self.raw_state_digest is None:
            raise ValueError("snapshot_digest and raw_state_digest are required")
        if self.table_count != len(self.tables):
            raise ValueError("table_count must match the number of table descriptors")

    def to_payload(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_digest": self.snapshot_digest.to_payload(),
            "raw_state_digest": self.raw_state_digest.to_payload(),
            "business_state_digest": (
                None if self.business_state_digest is None else self.business_state_digest.to_payload()
            ),
            "materialization_stage": self.materialization_stage,
            "parser_version": self.parser_version,
            "table_ruleset_version": self.table_ruleset_version,
            "summary_contract_version": self.summary_contract_version,
            "table_count": self.table_count,
            "row_count_total": self.row_count_total,
            "configuration_generated_at": (
                None
                if self.configuration_generated_at is None
                else self.configuration_generated_at.astimezone(timezone.utc).isoformat()
            ),
            "tables": [table.to_payload() for table in self.tables],
            "missing_or_unsupported_tables": list(self.missing_or_unsupported_tables),
            "source_context": (
                None if self.source_context is None else self.source_context.to_payload()
            ),
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "SnapshotSummary":
        tables_payload = _require_sequence(payload.get("tables"), "tables")
        diagnostics_payload = payload.get("diagnostics")
        if diagnostics_payload is None:
            diagnostics: tuple[DiagnosticRecord, ...] = tuple()
        else:
            diagnostics = tuple(
                DiagnosticRecord.from_payload(_require_mapping(item, "diagnostics item"))
                for item in _require_sequence(diagnostics_payload, "diagnostics")
            )
        source_context_payload = payload.get("source_context")
        source_context = None
        if source_context_payload is not None:
            source_context = SnapshotSourceContext.from_payload(
                _require_mapping(source_context_payload, "source_context")
            )
        missing_tables = payload.get("missing_or_unsupported_tables")
        if missing_tables is None:
            missing_or_unsupported_tables: tuple[str, ...] = tuple()
        else:
            missing_or_unsupported_tables = tuple(
                canonical_identifier(name)
                for name in _require_sequence(missing_tables, "missing_or_unsupported_tables")
            )
        return cls(
            snapshot_id=_require_text(payload, "snapshot_id"),
            snapshot_digest=_optional_payload_digest(payload.get("snapshot_digest"), field_name="snapshot_digest"),
            raw_state_digest=_optional_payload_digest(payload.get("raw_state_digest"), field_name="raw_state_digest"),
            business_state_digest=_optional_payload_digest(
                payload.get("business_state_digest"),
                field_name="business_state_digest",
            ),
            materialization_stage=_optional_payload_text(
                payload.get("materialization_stage"),
                field_name="materialization_stage",
            )
            or SnapshotMaterializationStage.FINAL.value,
            parser_version=_require_text(payload, "parser_version"),
            table_ruleset_version=_require_text(payload, "table_ruleset_version"),
            summary_contract_version=_require_text(payload, "summary_contract_version"),
            table_count=_optional_payload_int(payload.get("table_count"), field_name="table_count") or 0,
            row_count_total=_optional_payload_int(payload.get("row_count_total"), field_name="row_count_total"),
            configuration_generated_at=_optional_payload_datetime(
                payload.get("configuration_generated_at"),
                field_name="configuration_generated_at",
            ),
            tables=tuple(
                SnapshotTableDescriptor.from_payload(_require_mapping(item, "tables item"))
                for item in tables_payload
            ),
            missing_or_unsupported_tables=missing_or_unsupported_tables,
            source_context=source_context,
            diagnostics=diagnostics,
        )


@dataclass(frozen=True, slots=True)
class Snapshot:
    snapshot_id: str
    source_kind: str
    source_package_id: str | None = None
    repository_id: str | None = None
    repository_ref: str | None = None
    parser_version: str = SQL_PARSER_VERSION
    table_ruleset_version: str = TABLE_RULESET_VERSION
    scalar_encoding_version: str = SCALAR_ENCODING_VERSION
    snapshot_materialization_contract_version: str = SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION
    row_materialization_profile: str = ROW_MATERIALIZATION_PROFILE
    materialization_stage: str = SnapshotMaterializationStage.FINAL.value
    snapshot_digest: DigestRef | str | None = None
    raw_state_digest: DigestRef | str | None = None
    business_state_digest: DigestRef | str | None = None
    summary: SnapshotSummary | None = None
    source_digest: DigestRef | str | None = None
    source_context: SnapshotSourceContext | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot_id, str) or not self.snapshot_id.strip():
            raise ValueError("snapshot_id must be a non-empty string")
        if not isinstance(self.source_kind, str) or not self.source_kind.strip():
            raise ValueError("source_kind must be a non-empty string")
        for field_name in (
            "source_package_id",
            "repository_id",
            "repository_ref",
        ):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must be a non-empty string or None")
        for field_name in (
            "parser_version",
            "table_ruleset_version",
            "scalar_encoding_version",
            "snapshot_materialization_contract_version",
            "row_materialization_profile",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        materialization_stage = SnapshotMaterializationStage(self.materialization_stage)
        object.__setattr__(self, "materialization_stage", materialization_stage.value)
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.summary is not None and not isinstance(self.summary, SnapshotSummary):
            raise TypeError("summary must be a SnapshotSummary or None")
        if self.summary is not None and self.summary.materialization_stage != self.materialization_stage:
            raise ValueError("snapshot summary materialization stage must match snapshot stage")
        if self.source_context is not None and not isinstance(self.source_context, SnapshotSourceContext):
            raise TypeError("source_context must be a SnapshotSourceContext or None")
        object.__setattr__(self, "snapshot_digest", _coerce_digest(self.snapshot_digest))
        object.__setattr__(self, "raw_state_digest", _coerce_digest(self.raw_state_digest))
        object.__setattr__(self, "business_state_digest", _coerce_digest(self.business_state_digest))
        object.__setattr__(self, "source_digest", _coerce_digest(self.source_digest))
        object.__setattr__(self, "diagnostics", _diagnostics_payload(self.diagnostics))
        if self.snapshot_digest is None or self.raw_state_digest is None:
            raise ValueError("snapshot_digest and raw_state_digest are required")


@dataclass(frozen=True, slots=True)
class SnapshotMaterializationInput:
    source_path: Path | None = None
    source_sql: str | None = None
    sql_dump_source: object | None = None
    source_kind: str = "SQL_DUMP_SOURCE"
    digest_contract_version: str = SNAPSHOT_DIGEST_CONTRACT_VERSION
    parser_version: str = SQL_PARSER_VERSION
    parser_input_contract_version: str = SQL_DUMP_SOURCE_CONTRACT_VERSION
    table_ruleset_version: str = TABLE_RULESET_VERSION
    scalar_encoding_version: str = SCALAR_ENCODING_VERSION
    snapshot_materialization_contract_version: str = (
        SNAPSHOT_MATERIALIZATION_CONTRACT_VERSION
    )
    summary_contract_version: str = SNAPSHOT_SUMMARY_SCHEMA_VERSION
    row_materialization_profile: str = ROW_MATERIALIZATION_PROFILE
    requested_tables: tuple[str, ...] = field(default_factory=tuple)
    materialization_policy: str = "READERS_REQUIRED"
    cache_policy: str = "DISABLED"
    projection_digest_policy: str = PROJECTION_DIGEST_POLICY_DISABLED
    previous_summary: "SnapshotSummary | None" = None
    table_rule_registry: object | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.source_path is None and self.source_sql is None and self.sql_dump_source is None:
            raise ValueError("either source_path, source_sql or sql_dump_source must be provided")
        if self.source_path is not None and not isinstance(self.source_path, Path):
            raise TypeError("source_path must be a Path or None")
        if self.source_sql is not None and not isinstance(self.source_sql, str):
            raise TypeError("source_sql must be a string or None")
        if self.sql_dump_source is not None:
            # The concrete type lives in sql_source.py; duck typing keeps this module decoupled.
            if not hasattr(self.sql_dump_source, "sql_source_digest"):
                raise TypeError("sql_dump_source must be a SqlDumpSource-compatible object or None")
        if not isinstance(self.source_kind, str) or not self.source_kind:
            raise ValueError("source_kind must be a non-empty string")
        for field_name in (
            "digest_contract_version",
            "parser_version",
            "parser_input_contract_version",
            "table_ruleset_version",
            "scalar_encoding_version",
            "snapshot_materialization_contract_version",
            "summary_contract_version",
            "row_materialization_profile",
            "materialization_policy",
            "cache_policy",
            "projection_digest_policy",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.projection_digest_policy not in PROJECTION_DIGEST_POLICIES:
            raise ValueError(
                "projection_digest_policy must be one of "
                f"{sorted(PROJECTION_DIGEST_POLICIES)}"
            )
        if self.table_rule_registry is not None:
            from ..table_rules import TableRuleRegistry

            if not isinstance(self.table_rule_registry, TableRuleRegistry):
                raise TypeError("table_rule_registry must be a TableRuleRegistry or None")
            if self.table_rule_registry.table_ruleset_version != self.table_ruleset_version:
                raise ValueError(
                    "table_ruleset_version must match table_rule_registry.table_ruleset_version"
                )
        if self.previous_summary is not None:
            if not isinstance(self.previous_summary, SnapshotSummary):
                raise TypeError("previous_summary must be a SnapshotSummary or None")
            if self.previous_summary.materialization_stage != SnapshotMaterializationStage.FINAL.value:
                raise ValueError("previous_summary must be a FINAL SnapshotSummary")
        normalized_requested_tables: list[str] = []
        seen_tables: set[str] = set()
        for table in self.requested_tables:
            canonical_table = canonical_identifier(table)
            if not canonical_table:
                raise ValueError("requested_tables must not contain empty identifiers")
            if canonical_table in seen_tables:
                continue
            seen_tables.add(canonical_table)
            normalized_requested_tables.append(canonical_table)
        object.__setattr__(self, "requested_tables", tuple(normalized_requested_tables))


@dataclass(frozen=True, slots=True)
class SnapshotMaterializationResult:
    snapshot: Snapshot
    summary: SnapshotSummary
    table_set: SnapshotTableSet | None = None
    table_artifact_refs: tuple[ArtifactRef, ...] | None = None
    materialization_input: SnapshotMaterializationInput | None = None
    cache_diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.snapshot, Snapshot):
            raise TypeError("snapshot must be a Snapshot")
        if not isinstance(self.summary, SnapshotSummary):
            raise TypeError("summary must be a SnapshotSummary")
        if self.table_set is not None and not isinstance(self.table_set, SnapshotTableSet):
            raise TypeError("table_set must be a SnapshotTableSet or None")
        if self.materialization_input is not None and not isinstance(
            self.materialization_input,
            SnapshotMaterializationInput,
        ):
            raise TypeError("materialization_input must be a SnapshotMaterializationInput or None")
        if self.table_artifact_refs is not None:
            normalized_table_artifact_refs: list[ArtifactRef] = []
            for table_artifact_ref in self.table_artifact_refs:
                if not isinstance(table_artifact_ref, ArtifactRef):
                    raise TypeError("table_artifact_refs must contain ArtifactRef values")
                normalized_table_artifact_refs.append(table_artifact_ref)
            object.__setattr__(self, "table_artifact_refs", tuple(normalized_table_artifact_refs))
        object.__setattr__(self, "cache_diagnostics", _diagnostics_payload(self.cache_diagnostics))
        object.__setattr__(self, "diagnostics", _diagnostics_payload(self.diagnostics))
        if self.snapshot.summary is not None and self.snapshot.summary != self.summary:
            raise ValueError("snapshot.summary must match result summary when present")
