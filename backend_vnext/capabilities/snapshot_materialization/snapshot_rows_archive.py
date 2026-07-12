from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import tarfile
from time import perf_counter

import polars as pl

from ...artifacts import ArtifactManifest, ArtifactRef, LocalArtifactStore, StoredArtifact
from ...core.digests import DigestRef, canonical_json_bytes, stable_sha256
from ...core.identifiers import canonical_identifier
from ...core.row_digests import stable_snapshot_rows_digest
from ...core.scalar_encoding import parquet_scalar_value_normalizer
from ...tarball import create_stable_tarball
from .models import (
    Snapshot,
    SnapshotMaterializationResult,
    SnapshotMaterializationStage,
    SnapshotSummary,
    SnapshotTable,
    SnapshotTableDescriptor,
    SnapshotTableSet,
)


SNAPSHOT_ROWS_ARCHIVE_ARTIFACT_KIND = "backend-vnext/snapshot-rows-archive"
SNAPSHOT_ROWS_ARCHIVE_CONTRACT_VERSION = "backend-vnext/snapshot-rows-archive/v1"
SNAPSHOT_ROWS_ARCHIVE_MANIFEST_SCHEMA_VERSION = "backend-vnext/snapshot-rows-archive-manifest/v1"


@dataclass(frozen=True, slots=True)
class SnapshotRowsArchiveWriteResult:
    stored_artifact: StoredArtifact
    table_count: int
    physical_table_count: int
    row_count: int
    size_bytes: int
    duration_ms: float

    @property
    def artifact_ref(self) -> ArtifactRef:
        return self.stored_artifact.ref


@dataclass(frozen=True, slots=True)
class SnapshotRowsArchiveRestoreResult:
    materialized: SnapshotMaterializationResult
    table_count: int
    physical_table_count: int
    row_count: int
    size_bytes: int
    duration_ms: float
    cache_dir: Path


@dataclass(frozen=True, slots=True)
class _LogicalTableEntry:
    table_name: str
    physical_table_id: str
    descriptor_ref: str
    raw_create_sql: str


@dataclass(frozen=True, slots=True)
class _ParquetSnapshotTableReader:
    _descriptor: SnapshotTableDescriptor
    _path: Path
    _rows: tuple[tuple[object, ...], ...] | None = None

    def descriptor(self) -> SnapshotTableDescriptor:
        return self._descriptor

    def iter_rows(self) -> Iterator[tuple[object, ...]]:
        yield from self.rows

    def close(self) -> None:
        return None

    def validate_content_digest(self, expected_content_digest: DigestRef | str) -> DigestRef:
        expected = expected_content_digest
        if not isinstance(expected, DigestRef):
            expected = DigestRef.parse(str(expected))
        actual = stable_snapshot_rows_digest(self.rows, self._descriptor.columns)
        if actual != expected:
            raise ValueError("content digest does not match archived descriptor")
        return actual

    @property
    def rows(self) -> tuple[tuple[object, ...], ...]:
        rows = self._rows
        if rows is not None:
            return rows
        column_names = [column.name for column in self._descriptor.columns]
        if not self._path.is_file():
            raise FileNotFoundError(str(self._path))
        frame = pl.read_parquet(self._path)
        missing = [column_name for column_name in column_names if column_name not in frame.columns]
        if missing:
            raise ValueError(
                f"snapshot rows archive parquet is missing columns for "
                f"{self._descriptor.table_name}: {missing}"
            )
        if frame.height != self._descriptor.row_count:
            raise ValueError(
                f"snapshot rows archive parquet row count mismatch for "
                f"{self._descriptor.table_name}: expected {self._descriptor.row_count}, "
                f"got {frame.height}"
            )
        selected = frame.select(column_names)
        rows = tuple(tuple(row) for row in selected.iter_rows())
        object.__setattr__(self, "_rows", rows)
        return rows


def store_snapshot_rows_archive(
    *,
    result: SnapshotMaterializationResult,
    artifact_store: LocalArtifactStore,
    work_root: Path,
) -> SnapshotRowsArchiveWriteResult:
    started_at = perf_counter()
    if result.table_set is None:
        raise ValueError("snapshot rows archive requires a materialized table_set")
    if result.summary.materialization_stage != SnapshotMaterializationStage.FINAL.value:
        raise ValueError("snapshot rows archive requires FINAL materialization")
    if result.summary.snapshot_digest != result.snapshot.snapshot_digest:
        raise ValueError("snapshot rows archive snapshot digest mismatch")

    work_root.mkdir(parents=True, exist_ok=True)
    archive_root = work_root / f"snapshot-rows-{result.summary.snapshot_digest.hex_digest}"
    if archive_root.exists():
        _remove_tree(archive_root)
    archive_root.mkdir(parents=True, exist_ok=True)

    logical_entries, physical_table_count = _write_archive_tree(archive_root, result)
    manifest_payload = _archive_manifest_payload(
        result=result,
        logical_entries=logical_entries,
        physical_table_count=physical_table_count,
    )
    _write_json(archive_root / "manifest.json", manifest_payload)
    _write_json(archive_root / "snapshot.json", _snapshot_payload(result.snapshot))
    _write_json(archive_root / "summary.json", result.summary.to_payload())

    tar_path = work_root / f"snapshot-rows-{result.summary.snapshot_digest.hex_digest}.tar"
    metadata = create_stable_tarball(source_root=archive_root, tar_path=tar_path)
    content_digest = stable_sha256(tar_path.read_bytes())
    manifest = ArtifactManifest(
        artifact_kind=SNAPSHOT_ROWS_ARCHIVE_ARTIFACT_KIND,
        artifact_contract_version=SNAPSHOT_ROWS_ARCHIVE_CONTRACT_VERSION,
        content_digest=content_digest,
        content_size_bytes=metadata.size_bytes,
        metadata={
            "schema_version": SNAPSHOT_ROWS_ARCHIVE_MANIFEST_SCHEMA_VERSION,
            "snapshot_id": result.summary.snapshot_id,
            "snapshot_digest": result.summary.snapshot_digest.to_payload(),
            "table_count": len(logical_entries),
            "physical_table_count": physical_table_count,
            "row_count": int(result.summary.row_count_total or 0),
            "package_format": metadata.package_format,
            "sha256": metadata.sha256,
        },
        created_at=datetime.now(timezone.utc),
    )
    stored = artifact_store.put_file(manifest, tar_path)
    return SnapshotRowsArchiveWriteResult(
        stored_artifact=stored,
        table_count=len(logical_entries),
        physical_table_count=physical_table_count,
        row_count=int(result.summary.row_count_total or 0),
        size_bytes=metadata.size_bytes,
        duration_ms=(perf_counter() - started_at) * 1000,
    )


def restore_snapshot_rows_archive(
    *,
    artifact_ref: ArtifactRef,
    artifact_store: LocalArtifactStore,
) -> SnapshotRowsArchiveRestoreResult:
    started_at = perf_counter()
    if artifact_ref.artifact_kind != SNAPSHOT_ROWS_ARCHIVE_ARTIFACT_KIND:
        raise ValueError("artifact ref is not a snapshot rows archive")
    if artifact_ref.artifact_contract_version != SNAPSHOT_ROWS_ARCHIVE_CONTRACT_VERSION:
        raise ValueError("unsupported snapshot rows archive contract version")

    stored = artifact_store.read(artifact_ref)
    cache_dir = artifact_store.root / "snapshot-rows-restore-cache" / artifact_ref.manifest_digest.hex_digest
    if not (cache_dir / "manifest.json").is_file():
        _extract_archive(stored.content_path, cache_dir)
    manifest_payload = _read_json(cache_dir / "manifest.json")
    if manifest_payload.get("schema_version") != SNAPSHOT_ROWS_ARCHIVE_MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported snapshot rows archive manifest schema version")
    summary = SnapshotSummary.from_payload(_read_json(cache_dir / "summary.json"))
    snapshot = _snapshot_from_payload(_read_json(cache_dir / "snapshot.json"), summary=summary)
    logical_entries = tuple(
        _logical_entry_from_payload(item)
        for item in _require_sequence(manifest_payload.get("logical_tables"), "logical_tables")
    )
    tables: dict[str, SnapshotTable] = {}
    for entry in logical_entries:
        descriptor = SnapshotTableDescriptor.from_payload(
            _read_json(cache_dir / entry.descriptor_ref)
        )
        table_name = canonical_identifier(entry.table_name)
        if descriptor.table_name != table_name:
            raise ValueError("snapshot rows archive logical descriptor mismatch")
        rows_path = cache_dir / "tables" / entry.physical_table_id / "rows.parquet"
        reader = _ParquetSnapshotTableReader(descriptor, rows_path)
        if descriptor.raw_content_digest is not None:
            reader.validate_content_digest(descriptor.raw_content_digest)
        tables[table_name] = SnapshotTable(
            descriptor=descriptor,
            reader=reader,
            raw_create_sql=entry.raw_create_sql,
        )
    table_set = SnapshotTableSet(
        snapshot_id=summary.snapshot_id,
        snapshot_digest=summary.snapshot_digest,
        table_ruleset_version=summary.table_ruleset_version,
        tables=tables,
        resolution_plan="SNAPSHOT_ROWS_ARCHIVE",
        diagnostics=summary.diagnostics,
    )
    materialized = SnapshotMaterializationResult(
        snapshot=snapshot,
        summary=summary,
        table_set=table_set,
    )
    return SnapshotRowsArchiveRestoreResult(
        materialized=materialized,
        table_count=len(tables),
        physical_table_count=int(manifest_payload.get("physical_table_count") or len(tables)),
        row_count=int(summary.row_count_total or 0),
        size_bytes=stored.manifest.content_size_bytes,
        duration_ms=(perf_counter() - started_at) * 1000,
        cache_dir=cache_dir,
    )


def _write_archive_tree(
    archive_root: Path,
    result: SnapshotMaterializationResult,
) -> tuple[tuple[_LogicalTableEntry, ...], int]:
    assert result.table_set is not None
    physical_ids_by_key: dict[str, str] = {}
    physical_source_by_id: dict[str, SnapshotTable] = {}
    logical_entries: list[_LogicalTableEntry] = []

    for table_name in sorted(result.table_set.tables):
        table = result.table_set.tables[table_name]
        descriptor = table.descriptor
        physical_key = descriptor.canonical_artifact_ref or descriptor.table_name
        physical_id = physical_ids_by_key.get(physical_key)
        if physical_id is None:
            physical_id = f"table-{len(physical_ids_by_key) + 1:05d}"
            physical_ids_by_key[physical_key] = physical_id
            physical_source_by_id[physical_id] = table
            _write_physical_table(archive_root, physical_id, table)
        descriptor_ref = f"tables/{physical_id}/logical/{descriptor.table_name}.descriptor.json"
        _write_json(archive_root / descriptor_ref, descriptor.to_payload())
        logical_entries.append(
            _LogicalTableEntry(
                table_name=descriptor.table_name,
                physical_table_id=physical_id,
                descriptor_ref=descriptor_ref,
                raw_create_sql=table.raw_create_sql,
            )
        )

    return tuple(logical_entries), len(physical_source_by_id)


def _write_physical_table(archive_root: Path, physical_id: str, table: SnapshotTable) -> None:
    table_dir = archive_root / "tables" / physical_id
    table_dir.mkdir(parents=True, exist_ok=True)
    _write_json(table_dir / "descriptor.json", table.descriptor.to_payload())
    _write_rows_parquet(table_dir / "rows.parquet", table)


def _write_rows_parquet(path: Path, table: SnapshotTable) -> None:
    columns = table.descriptor.columns
    column_names = [column.name for column in columns]
    column_values: list[list[object]] = [[] for _ in columns]
    normalizers = [parquet_scalar_value_normalizer(column.scalar_type) for column in columns]
    for row in table.reader.iter_rows():
        if len(row) != len(columns):
            raise ValueError(f"row width mismatch for {table.descriptor.table_name}")
        for value, values, normalize_value in zip(row, column_values, normalizers):
            values.append(normalize_value(value))
    columns_by_name = dict(zip(column_names, column_values))
    if any(columns_by_name.values()):
        frame = pl.DataFrame(columns_by_name, strict=False).select(column_names)
    else:
        frame = pl.DataFrame(schema={column.name: pl.Null for column in columns})
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f"{path.name}.tmp")
    frame.write_parquet(temporary_path)
    temporary_path.replace(path)


def _archive_manifest_payload(
    *,
    result: SnapshotMaterializationResult,
    logical_entries: tuple[_LogicalTableEntry, ...],
    physical_table_count: int,
) -> dict[str, object]:
    return {
        "schema_version": SNAPSHOT_ROWS_ARCHIVE_MANIFEST_SCHEMA_VERSION,
        "snapshot_id": result.summary.snapshot_id,
        "snapshot_digest": result.summary.snapshot_digest.to_payload(),
        "summary_digest": DigestRef.from_payload(result.summary.to_payload()).to_payload(),
        "materialization_stage": result.summary.materialization_stage,
        "table_count": len(logical_entries),
        "physical_table_count": physical_table_count,
        "row_count": result.summary.row_count_total,
        "logical_tables": [
            {
                "table_name": entry.table_name,
                "physical_table_id": entry.physical_table_id,
                "descriptor_ref": entry.descriptor_ref,
                "raw_create_sql": entry.raw_create_sql,
            }
            for entry in logical_entries
        ],
    }


def _snapshot_payload(snapshot: Snapshot) -> dict[str, object]:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "source_kind": snapshot.source_kind,
        "source_package_id": snapshot.source_package_id,
        "repository_id": snapshot.repository_id,
        "repository_ref": snapshot.repository_ref,
        "parser_version": snapshot.parser_version,
        "table_ruleset_version": snapshot.table_ruleset_version,
        "scalar_encoding_version": snapshot.scalar_encoding_version,
        "snapshot_materialization_contract_version": snapshot.snapshot_materialization_contract_version,
        "row_materialization_profile": snapshot.row_materialization_profile,
        "materialization_stage": snapshot.materialization_stage,
        "snapshot_digest": None if snapshot.snapshot_digest is None else snapshot.snapshot_digest.to_payload(),
        "raw_state_digest": None if snapshot.raw_state_digest is None else snapshot.raw_state_digest.to_payload(),
        "business_state_digest": (
            None if snapshot.business_state_digest is None else snapshot.business_state_digest.to_payload()
        ),
        "source_digest": None if snapshot.source_digest is None else snapshot.source_digest.to_payload(),
        "source_context": None if snapshot.source_context is None else snapshot.source_context.to_payload(),
        "created_at": snapshot.created_at.astimezone(timezone.utc).isoformat(),
        "diagnostics": [diagnostic.to_payload() for diagnostic in snapshot.diagnostics],
    }


def _snapshot_from_payload(payload: Mapping[str, object], *, summary: SnapshotSummary) -> Snapshot:
    created_at_value = payload.get("created_at")
    created_at = (
        datetime.now(timezone.utc)
        if created_at_value is None
        else datetime.fromisoformat(str(created_at_value))
    )
    return Snapshot(
        snapshot_id=str(payload["snapshot_id"]),
        source_kind=str(payload["source_kind"]),
        source_package_id=_optional_text(payload.get("source_package_id")),
        repository_id=_optional_text(payload.get("repository_id")),
        repository_ref=_optional_text(payload.get("repository_ref")),
        parser_version=str(payload["parser_version"]),
        table_ruleset_version=str(payload["table_ruleset_version"]),
        scalar_encoding_version=str(payload["scalar_encoding_version"]),
        snapshot_materialization_contract_version=str(
            payload["snapshot_materialization_contract_version"]
        ),
        row_materialization_profile=str(payload["row_materialization_profile"]),
        materialization_stage=str(payload["materialization_stage"]),
        snapshot_digest=DigestRef.parse(str(payload["snapshot_digest"])),
        raw_state_digest=DigestRef.parse(str(payload["raw_state_digest"])),
        business_state_digest=(
            None
            if payload.get("business_state_digest") is None
            else DigestRef.parse(str(payload["business_state_digest"]))
        ),
        summary=summary,
        source_digest=(
            None
            if payload.get("source_digest") is None
            else DigestRef.parse(str(payload["source_digest"]))
        ),
        source_context=summary.source_context,
        created_at=created_at,
    )


def _logical_entry_from_payload(payload: object) -> _LogicalTableEntry:
    mapping = _require_mapping(payload, "logical_tables item")
    return _LogicalTableEntry(
        table_name=str(mapping["table_name"]),
        physical_table_id=str(mapping["physical_table_id"]),
        descriptor_ref=str(mapping["descriptor_ref"]),
        raw_create_sql=str(mapping["raw_create_sql"]),
    )


def _extract_archive(content_path: Path, cache_dir: Path) -> None:
    temporary_dir = cache_dir.with_name(f"{cache_dir.name}.tmp")
    if temporary_dir.exists():
        _remove_tree(temporary_dir)
    temporary_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(content_path, mode="r") as archive:
            for member in archive.getmembers():
                if member.isdir():
                    continue
                if member.issym() or member.islnk():
                    raise ValueError("snapshot rows archive links are not supported")
                target_path = temporary_dir / member.name
                resolved = target_path.resolve()
                try:
                    resolved.relative_to(temporary_dir.resolve())
                except ValueError as exc:
                    raise ValueError("snapshot rows archive entry escapes restore root")
                target_path.parent.mkdir(parents=True, exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError(f"snapshot rows archive entry is not readable: {member.name}")
                target_path.write_bytes(source.read())
        if cache_dir.exists():
            _remove_tree(cache_dir)
        temporary_dir.replace(cache_dir)
    finally:
        if temporary_dir.exists():
            _remove_tree(temporary_dir)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(payload))


def _read_json(path: Path) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise TypeError(f"{path} must contain a JSON object")
    return payload


def _remove_tree(path: Path) -> None:
    for child in sorted(path.rglob("*"), reverse=True):
        if child.is_file() or child.is_symlink():
            child.unlink()
        elif child.is_dir():
            child.rmdir()
    path.rmdir()


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return value


def _require_sequence(value: object, field_name: str) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a sequence")
    return tuple(value)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
