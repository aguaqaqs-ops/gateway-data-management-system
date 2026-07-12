from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
import io
import json
from pathlib import Path

import polars as pl

from ..core.digests import DigestRef, canonical_json_bytes
from ..core.diagnostics import DiagnosticRecord
from .local_store import LocalArtifactStore, StoredArtifact
from .manifest import ArtifactManifest, ArtifactRef
from .versions import (
    RECORDS_ARTIFACT_CONTRACT_VERSION,
    RECORDS_ARTIFACT_KIND,
    RECORDS_ARTIFACT_MANIFEST_SCHEMA_VERSION,
    RECORDS_ARTIFACT_RECORD_FORMAT_JSONL,
    RECORDS_ARTIFACT_RECORD_FORMAT_PARQUET,
)


@dataclass(frozen=True, slots=True)
class RecordsJsonlContent:
    record_count: int
    content_bytes: bytes
    content_digest: DigestRef

    def __post_init__(self) -> None:
        if (
            not isinstance(self.record_count, int)
            or isinstance(self.record_count, bool)
            or self.record_count < 0
        ):
            raise ValueError("record_count must be a non-negative integer")
        content_bytes = bytes(self.content_bytes)
        actual_digest = DigestRef.from_bytes(content_bytes)
        content_digest = _coerce_digest(self.content_digest)
        if content_digest != actual_digest:
            raise ValueError("content_digest does not match content_bytes")
        object.__setattr__(self, "content_bytes", content_bytes)
        object.__setattr__(self, "content_digest", actual_digest)


@dataclass(frozen=True, slots=True)
class RecordsParquetContent:
    record_count: int
    content_bytes: bytes
    content_digest: DigestRef

    def __post_init__(self) -> None:
        if (
            not isinstance(self.record_count, int)
            or isinstance(self.record_count, bool)
            or self.record_count < 0
        ):
            raise ValueError("record_count must be a non-negative integer")
        content_bytes = bytes(self.content_bytes)
        actual_digest = DigestRef.from_bytes(content_bytes)
        content_digest = _coerce_digest(self.content_digest)
        if content_digest != actual_digest:
            raise ValueError("content_digest does not match content_bytes")
        object.__setattr__(self, "content_bytes", content_bytes)
        object.__setattr__(self, "content_digest", actual_digest)


@dataclass(frozen=True, slots=True)
class RecordsArtifactManifest:
    table_name: str
    record_count: int
    row_diff_detail_policy: str
    content_digest: DigestRef | str
    content_size_bytes: int
    record_format: str = RECORDS_ARTIFACT_RECORD_FORMAT_PARQUET
    artifact_kind: str = RECORDS_ARTIFACT_KIND
    artifact_contract_version: str = RECORDS_ARTIFACT_CONTRACT_VERSION
    metadata: Mapping[str, object] = field(default_factory=dict)
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.table_name, str) or not self.table_name:
            raise ValueError("table_name must be a non-empty string")
        if (
            not isinstance(self.record_count, int)
            or isinstance(self.record_count, bool)
            or self.record_count < 0
        ):
            raise ValueError("record_count must be a non-negative integer")
        if not isinstance(self.row_diff_detail_policy, str) or not self.row_diff_detail_policy:
            raise ValueError("row_diff_detail_policy must be a non-empty string")
        if not isinstance(self.record_format, str) or not self.record_format:
            raise ValueError("record_format must be a non-empty string")
        if not isinstance(self.artifact_kind, str) or not self.artifact_kind:
            raise ValueError("artifact_kind must be a non-empty string")
        if not isinstance(self.artifact_contract_version, str) or not self.artifact_contract_version:
            raise ValueError("artifact_contract_version must be a non-empty string")
        if (
            not isinstance(self.content_size_bytes, int)
            or isinstance(self.content_size_bytes, bool)
            or self.content_size_bytes < 0
        ):
            raise ValueError("content_size_bytes must be a non-negative integer")
        object.__setattr__(self, "content_digest", _coerce_digest(self.content_digest))
        object.__setattr__(self, "metadata", _mapping_payload(self.metadata))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        if self.created_at is not None and not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be a datetime or None")
        if self.created_at is not None and self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": RECORDS_ARTIFACT_MANIFEST_SCHEMA_VERSION,
            "table_name": self.table_name,
            "record_count": self.record_count,
            "row_diff_detail_policy": self.row_diff_detail_policy,
            "record_format": self.record_format,
            "artifact_kind": self.artifact_kind,
            "artifact_contract_version": self.artifact_contract_version,
            "content_digest": self.content_digest.to_payload(),
            "content_size_bytes": self.content_size_bytes,
            "metadata": _records_metadata(self.metadata),
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
            "created_at": (
                None
                if self.created_at is None
                else self.created_at.astimezone(timezone.utc).isoformat()
            ),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "RecordsArtifactManifest":
        schema_version = _required_str(payload, "schema_version")
        if schema_version != RECORDS_ARTIFACT_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported records artifact manifest schema version")
        diagnostics_payload = payload.get("diagnostics", [])
        if not isinstance(diagnostics_payload, list):
            raise TypeError("records diagnostics payload must be a list")
        created_at_value = payload.get("created_at")
        created_at = (
            None
            if created_at_value is None
            else datetime.fromisoformat(_required_str({"created_at": created_at_value}, "created_at"))
        )
        content_size_value = payload["content_size_bytes"]
        if not isinstance(content_size_value, int) or isinstance(content_size_value, bool):
            raise TypeError("content_size_bytes must be an integer")
        record_count_value = payload["record_count"]
        if not isinstance(record_count_value, int) or isinstance(record_count_value, bool):
            raise TypeError("record_count must be an integer")
        return cls(
            table_name=_required_str(payload, "table_name"),
            record_count=record_count_value,
            row_diff_detail_policy=_required_str(payload, "row_diff_detail_policy"),
            record_format=_required_str(payload, "record_format"),
            artifact_kind=_required_str(payload, "artifact_kind"),
            artifact_contract_version=_required_str(payload, "artifact_contract_version"),
            content_digest=DigestRef.parse(_required_str(payload, "content_digest")),
            content_size_bytes=content_size_value,
            metadata=_mapping_payload(_mapping_value(payload, "metadata")),
            diagnostics=tuple(
                DiagnosticRecord.from_payload(item)
                for item in diagnostics_payload
            ),
            created_at=created_at,
        )

    def to_artifact_manifest(self) -> ArtifactManifest:
        metadata = dict(_records_metadata(self.metadata))
        metadata.update(
            {
                "table_name": self.table_name,
                "record_count": self.record_count,
                "row_diff_detail_policy": self.row_diff_detail_policy,
                "record_format": self.record_format,
                "records_manifest_schema_version": RECORDS_ARTIFACT_MANIFEST_SCHEMA_VERSION,
            }
        )
        return ArtifactManifest(
            artifact_kind=self.artifact_kind,
            artifact_contract_version=self.artifact_contract_version,
            content_digest=self.content_digest,
            content_size_bytes=self.content_size_bytes,
            metadata=metadata,
            diagnostics=self.diagnostics,
            created_at=self.created_at,
        )

    @classmethod
    def from_artifact_manifest(
        cls,
        manifest: ArtifactManifest,
    ) -> "RecordsArtifactManifest":
        if manifest.artifact_kind != RECORDS_ARTIFACT_KIND:
            raise ValueError("artifact manifest is not a records artifact")
        if manifest.artifact_contract_version != RECORDS_ARTIFACT_CONTRACT_VERSION:
            raise ValueError("unsupported records artifact contract version")
        return cls(
            table_name=_required_str(manifest.metadata, "table_name"),
            record_count=_required_int(manifest.metadata, "record_count"),
            row_diff_detail_policy=_required_str(
                manifest.metadata,
                "row_diff_detail_policy",
            ),
            record_format=_required_str(manifest.metadata, "record_format"),
            artifact_kind=manifest.artifact_kind,
            artifact_contract_version=manifest.artifact_contract_version,
            content_digest=manifest.content_digest,
            content_size_bytes=manifest.content_size_bytes,
            metadata=_records_metadata(manifest.metadata),
            diagnostics=manifest.diagnostics,
            created_at=manifest.created_at,
        )


@dataclass(frozen=True, slots=True)
class RecordsArtifact:
    manifest: RecordsArtifactManifest
    stored: StoredArtifact

    def __post_init__(self) -> None:
        if not isinstance(self.manifest, RecordsArtifactManifest):
            raise TypeError("manifest must be a RecordsArtifactManifest")
        if not isinstance(self.stored, StoredArtifact):
            raise TypeError("stored must be a StoredArtifact")
        if self.stored.manifest.artifact_kind != self.manifest.artifact_kind:
            raise ValueError("stored manifest kind does not match records manifest")
        if self.stored.manifest.artifact_contract_version != self.manifest.artifact_contract_version:
            raise ValueError("stored manifest contract version does not match records manifest")
        if self.stored.manifest.content_digest != self.manifest.content_digest:
            raise ValueError("stored content digest does not match records manifest")
        if self.stored.manifest.content_size_bytes != self.manifest.content_size_bytes:
            raise ValueError("stored content size does not match records manifest")

    @property
    def ref(self) -> ArtifactRef:
        return self.stored.ref

    @property
    def manifest_path(self) -> Path:
        return self.stored.manifest_path

    @property
    def content_path(self) -> Path:
        return self.stored.content_path

    @property
    def artifact_dir(self) -> Path:
        return self.stored.artifact_dir

    @property
    def reused(self) -> bool:
        return self.stored.reused

    def read_records(self) -> tuple[dict[str, object], ...]:
        if self.manifest.record_format == RECORDS_ARTIFACT_RECORD_FORMAT_PARQUET:
            return read_records_parquet(self.content_path)
        if self.manifest.record_format == RECORDS_ARTIFACT_RECORD_FORMAT_JSONL:
            return parse_records_jsonl_bytes(self.content_path.read_bytes())
        raise ValueError(f"unsupported records format: {self.manifest.record_format}")


def records_parquet_content(
    records: Sequence[object],
    *,
    columns: Sequence[str] = (),
) -> RecordsParquetContent:
    rows = _records_parquet_rows(records, columns=columns)
    frame = pl.DataFrame(rows, strict=False)
    if frame.width == 0:
        frame = pl.DataFrame(_empty_records_parquet_columns())
    buffer = io.BytesIO()
    frame.write_parquet(buffer)
    content_bytes = buffer.getvalue()
    return RecordsParquetContent(
        record_count=len(rows),
        content_bytes=content_bytes,
        content_digest=DigestRef.from_bytes(content_bytes),
    )


def write_records_parquet(
    path: Path,
    records: Sequence[object],
    *,
    columns: Sequence[str] = (),
) -> RecordsParquetContent:
    content = records_parquet_content(records, columns=columns)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.content_bytes)
    return content


def read_records_parquet(path: Path) -> tuple[dict[str, object], ...]:
    frame = pl.read_parquet(path)
    if "record_payload" not in frame.columns:
        return tuple(frame.to_dicts())
    records: list[dict[str, object]] = []
    for payload in frame.get_column("record_payload").to_list():
        if not isinstance(payload, str) or not payload:
            continue
        decoded = json.loads(payload)
        if not isinstance(decoded, Mapping):
            raise TypeError("record_payload must decode to a JSON object")
        records.append(_mapping_payload(decoded))
    return tuple(records)


def _records_parquet_rows(
    records: Sequence[object],
    *,
    columns: Sequence[str],
) -> list[dict[str, object]]:
    normalized_columns = [str(column) for column in columns]
    rows: list[dict[str, object]] = []
    for index, record in enumerate(records):
        payload = _record_payload(record)
        rows.append(_records_parquet_row(payload, index=index, columns=normalized_columns))
    return rows


def _records_parquet_row(
    payload: Mapping[str, object],
    *,
    index: int,
    columns: Sequence[str],
) -> dict[str, object]:
    table_name = str(payload.get("table_name") or "")
    raw_kind = str(payload.get("record_kind") or "")
    row_identity = _list_value(payload.get("row_identity"))
    changed_columns = _string_list(payload.get("changed_columns"))
    before_values = _list_value(payload.get("before_values"))
    current_values = _list_value(payload.get("current_values"))
    payload_before = payload.get("payload_before")
    payload_after = payload.get("payload_after")
    if isinstance(payload_before, Mapping) or isinstance(payload_after, Mapping) or "semantic_kind" in payload:
        return _ordered_records_parquet_row(payload, index=index)

    display_kind = _standard_display_record_kind(raw_kind)
    before_payload = _values_payload(columns, before_values) if before_values else None
    current_payload = _values_payload(columns, current_values) if current_values else None
    record_id = f"{table_name}:{index + 1:06d}"
    return {
        "record_id": record_id,
        "group_id": record_id,
        "record_kind": display_kind,
        "entity_key": canonical_json_bytes(row_identity).decode("utf-8") if row_identity else "",
        "changed_columns": json.dumps(changed_columns, ensure_ascii=False),
        "payload_before": _json_payload(before_payload),
        "payload_current": _json_payload(current_payload),
        "payload_after": _json_payload(current_payload),
        "record_payload": json.dumps(_mapping_payload(payload), ensure_ascii=False, sort_keys=True),
    }


def _ordered_records_parquet_row(payload: Mapping[str, object], *, index: int) -> dict[str, object]:
    table_name = str(payload.get("table_name") or "")
    record_id = f"{table_name}:{index + 1:06d}"
    changed_columns = _string_list(payload.get("changed_columns"))
    before_payload = payload.get("payload_before")
    after_payload = payload.get("payload_after")
    return {
        "record_id": record_id,
        "group_id": record_id,
        "op_id": record_id,
        "op_group_key": record_id,
        "record_kind": str(payload.get("record_kind") or ""),
        "semantic_kind": str(payload.get("semantic_kind") or ""),
        "entity_key_kind": str(payload.get("entity_key_kind") or ""),
        "entity_key": str(payload.get("entity_key") or ""),
        "before_position": payload.get("before_position"),
        "after_position": payload.get("after_position"),
        "current_position": payload.get("after_position"),
        "changed_columns": json.dumps(changed_columns, ensure_ascii=False),
        "payload_before": _json_payload(before_payload if isinstance(before_payload, Mapping) else None),
        "payload_current": _json_payload(after_payload if isinstance(after_payload, Mapping) else None),
        "payload_after": _json_payload(after_payload if isinstance(after_payload, Mapping) else None),
        "record_payload": json.dumps(_mapping_payload(payload), ensure_ascii=False, sort_keys=True),
    }


def _empty_records_parquet_columns() -> dict[str, list[object]]:
    return {
        "record_id": [],
        "group_id": [],
        "record_kind": [],
        "entity_key": [],
        "changed_columns": [],
        "payload_before": [],
        "payload_current": [],
        "payload_after": [],
        "record_payload": [],
    }


def _standard_display_record_kind(record_kind: str) -> str:
    if record_kind == "ROW_ADDED":
        return "INSERT"
    if record_kind == "ROW_DELETED":
        return "DELETE"
    if record_kind == "ROW_MODIFIED":
        return "UPDATE"
    return record_kind


def _values_payload(columns: Sequence[str], values: Sequence[object]) -> dict[str, object]:
    return {
        column: values[index] if index < len(values) else None
        for index, column in enumerate(columns)
    }


def _json_payload(payload: Mapping[str, object] | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(dict(payload), ensure_ascii=False, sort_keys=True)


def _list_value(value: object) -> list[object]:
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, list):
        return list(value)
    return []


def _string_list(value: object) -> list[str]:
    return [str(item) for item in _list_value(value)]


def records_jsonl_content(records: Sequence[object]) -> RecordsJsonlContent:
    lines: list[bytes] = []
    for record in records:
        payload = _record_payload(record)
        lines.append(canonical_json_bytes(payload))
    content_bytes = b"\n".join(lines)
    if lines:
        content_bytes += b"\n"
    return RecordsJsonlContent(
        record_count=len(lines),
        content_bytes=content_bytes,
        content_digest=DigestRef.from_bytes(content_bytes),
    )


def write_records_jsonl(path: Path, records: Sequence[object]) -> RecordsJsonlContent:
    content = records_jsonl_content(records)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.content_bytes)
    return content


def read_records_jsonl(path: Path) -> tuple[dict[str, object], ...]:
    return parse_records_jsonl_bytes(path.read_bytes())


def parse_records_jsonl_bytes(raw: bytes) -> tuple[dict[str, object], ...]:
    text = raw.decode("utf-8")
    if not text:
        return tuple()
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line:
            raise ValueError(f"records JSONL line {line_number} is empty")
        payload = json.loads(line)
        if not isinstance(payload, Mapping):
            raise TypeError("records JSONL lines must decode to JSON objects")
        records.append(_mapping_payload(payload))
    return tuple(records)


def store_records_artifact(
    store: LocalArtifactStore,
    manifest: RecordsArtifactManifest,
    records: Sequence[object],
) -> RecordsArtifact:
    if manifest.record_format == RECORDS_ARTIFACT_RECORD_FORMAT_PARQUET:
        content = records_parquet_content(
            records,
            columns=_record_columns(manifest.metadata),
        )
    elif manifest.record_format == RECORDS_ARTIFACT_RECORD_FORMAT_JSONL:
        content = records_jsonl_content(records)
    else:
        raise ValueError(f"unsupported records format: {manifest.record_format}")
    if content.record_count != manifest.record_count:
        raise ValueError("record_count does not match records content")
    if content.content_digest != manifest.content_digest:
        raise ValueError("content_digest does not match records content")
    if len(content.content_bytes) != manifest.content_size_bytes:
        raise ValueError("content_size_bytes does not match records content")
    stored = store.put_bytes(manifest.to_artifact_manifest(), content.content_bytes)
    return RecordsArtifact(
        manifest=RecordsArtifactManifest.from_artifact_manifest(stored.manifest),
        stored=stored,
    )


def read_records_artifact(
    store: LocalArtifactStore,
    ref: ArtifactRef | DigestRef | str,
) -> RecordsArtifact:
    stored = store.read(ref)
    return RecordsArtifact(
        manifest=RecordsArtifactManifest.from_artifact_manifest(stored.manifest),
        stored=stored,
    )


def restore_records_artifact(
    source_store: LocalArtifactStore,
    target_store: LocalArtifactStore,
    ref: ArtifactRef | DigestRef | str,
) -> RecordsArtifact:
    source_artifact = read_records_artifact(source_store, ref)
    restored = target_store.put_bytes(
        source_artifact.manifest.to_artifact_manifest(),
        source_artifact.content_path.read_bytes(),
    )
    return RecordsArtifact(
        manifest=RecordsArtifactManifest.from_artifact_manifest(restored.manifest),
        stored=restored,
    )


def _record_payload(record: object) -> dict[str, object]:
    payload = json.loads(canonical_json_bytes(record).decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError("records must serialize to JSON objects")
    return _mapping_payload(payload)


def _record_columns(metadata: Mapping[str, object]) -> tuple[str, ...]:
    value = metadata.get("record_columns")
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise TypeError("record_columns must be a list or tuple")
    return tuple(str(item) for item in value)


def _records_metadata(payload: Mapping[str, object]) -> dict[str, object]:
    normalized = _mapping_payload(payload)
    metadata = {
        key: value
        for key, value in normalized.items()
        if key
        not in {
            "table_name",
            "record_count",
            "row_diff_detail_policy",
            "record_format",
            "records_manifest_schema_version",
        }
    }
    payload = json.loads(canonical_json_bytes(metadata).decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError("records metadata must normalize to a JSON object")
    return _mapping_payload(payload)


def _mapping_payload(payload: Mapping[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if not isinstance(key, str):
            raise TypeError("mapping keys must be strings")
        normalized[key] = value
    return normalized


def _coerce_digest(value: DigestRef | str) -> DigestRef:
    if isinstance(value, DigestRef):
        return value
    return DigestRef.parse(_required_str({"content_digest": value}, "content_digest"))


def _required_str(payload: Mapping[str, object], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str) or not value:
        raise TypeError(f"{key} must be a non-empty string")
    return value


def _required_int(payload: Mapping[str, object], key: str) -> int:
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be an integer")
    return value


def _mapping_value(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload.get(key, {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be a mapping")
    return value
