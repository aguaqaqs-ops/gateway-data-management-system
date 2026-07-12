from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import ast
import json
import re
from time import perf_counter

from ...capabilities.snapshot_materialization import materialize_sql_source
from ...capabilities.snapshot_materialization.models import (
    SnapshotMaterializationResult,
)
from ...core.digests import DigestRef
from ...core.diagnostics import DiagnosticRecord
from ...core.identifiers import canonical_identifier
from .._paths import resolve_benchmark_path


DEFAULT_DATASET_SOURCE_FILE = "dbcfg.sql"
DEFAULT_DATASET_METADATA_FILE = "dataset.yaml"
DATASET_METADATA_SOURCE_SQL_FILE_KEY = "source_sql_file"
DATASET_METADATA_VALIDATION_TABLES_KEY = "validation_tables"


class RepositoryImportBenchmarkDatasetKind(str, Enum):
    BUSINESS_SMALL_CUT = "BUSINESS_SMALL_CUT"
    BUSINESS_SMALL = "BUSINESS_SMALL"
    BUSINESS_MEDIUM = "BUSINESS_MEDIUM"
    BUSINESS_LARGE = "BUSINESS_LARGE"
    GENERATED_CORRECTNESS = "GENERATED_CORRECTNESS"
    GENERATED_STRESS = "GENERATED_STRESS"


@dataclass(frozen=True, slots=True)
class RepositoryImportBenchmarkDatasetSpec:
    dataset_id: str
    dataset_kind: str
    dataset_dir: Path
    source_sql_path: Path
    dataset_metadata_path: Path | None = None
    requested_tables: tuple[str, ...] = field(default_factory=tuple)
    validation_table_names: tuple[str, ...] = field(default_factory=tuple)
    business_label: str | None = None
    anonymization_note: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_id, str) or not self.dataset_id.strip():
            raise ValueError("dataset_id must be a non-empty string")
        if not isinstance(self.dataset_kind, str) or not self.dataset_kind.strip():
            raise ValueError("dataset_kind must be a non-empty string")
        if not isinstance(self.dataset_dir, Path):
            raise TypeError("dataset_dir must be a Path")
        if not isinstance(self.source_sql_path, Path):
            raise TypeError("source_sql_path must be a Path")
        if self.dataset_metadata_path is not None and not isinstance(self.dataset_metadata_path, Path):
            raise TypeError("dataset_metadata_path must be a Path or None")
        normalized_tables: list[str] = []
        seen: set[str] = set()
        for table_name in self.requested_tables:
            canonical_table = canonical_identifier(str(table_name))
            if not canonical_table or canonical_table in seen:
                continue
            seen.add(canonical_table)
            normalized_tables.append(canonical_table)
        object.__setattr__(self, "requested_tables", tuple(normalized_tables))
        normalized_validation_tables: list[str] = []
        seen_validation_tables: set[str] = set()
        for table_name in self.validation_table_names:
            canonical_table = canonical_identifier(str(table_name))
            if not canonical_table or canonical_table in seen_validation_tables:
                continue
            seen_validation_tables.add(canonical_table)
            normalized_validation_tables.append(canonical_table)
        object.__setattr__(self, "validation_table_names", tuple(normalized_validation_tables))
        if self.business_label is not None and not isinstance(self.business_label, str):
            raise TypeError("business_label must be a string or None")
        if self.anonymization_note is not None and not isinstance(self.anonymization_note, str):
            raise TypeError("anonymization_note must be a string or None")


@dataclass(frozen=True, slots=True)
class RepositoryImportBenchmarkDatasetManifest:
    dataset_id: str
    dataset_kind: str
    source_sql_digest: DigestRef | str
    source_sql_bytes: int
    table_count: int
    row_count_total: int
    largest_table_row_count: int
    insert_statement_count: int | None = None
    validation_table_names: tuple[str, ...] = field(default_factory=tuple)
    business_label: str | None = None
    anonymization_note: str | None = None
    created_at: str | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for field_name in ("dataset_id", "dataset_kind"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        object.__setattr__(self, "source_sql_digest", DigestRef.parse(str(self.source_sql_digest)))
        for field_name in ("source_sql_bytes", "table_count", "row_count_total", "largest_table_row_count"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.insert_statement_count is not None and (
            not isinstance(self.insert_statement_count, int)
            or isinstance(self.insert_statement_count, bool)
            or self.insert_statement_count < 0
        ):
            raise ValueError("insert_statement_count must be a non-negative integer or None")
        normalized_validation_tables: list[str] = []
        seen_validation_tables: set[str] = set()
        for table_name in self.validation_table_names:
            canonical_table = canonical_identifier(str(table_name))
            if not canonical_table or canonical_table in seen_validation_tables:
                continue
            seen_validation_tables.add(canonical_table)
            normalized_validation_tables.append(canonical_table)
        object.__setattr__(self, "validation_table_names", tuple(normalized_validation_tables))
        if self.business_label is not None and not isinstance(self.business_label, str):
            raise TypeError("business_label must be a string or None")
        if self.anonymization_note is not None and not isinstance(self.anonymization_note, str):
            raise TypeError("anonymization_note must be a string or None")
        if self.created_at is not None and not isinstance(self.created_at, str):
            raise TypeError("created_at must be a string or None")
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")

    def to_payload(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_kind": self.dataset_kind,
            "source_sql_digest": self.source_sql_digest.to_payload(),
            "source_sql_bytes": self.source_sql_bytes,
            "table_count": self.table_count,
            "row_count_total": self.row_count_total,
            "largest_table_row_count": self.largest_table_row_count,
            "insert_statement_count": self.insert_statement_count,
            "validation_table_names": list(self.validation_table_names),
            "business_label": self.business_label,
            "anonymization_note": self.anonymization_note,
            "created_at": self.created_at,
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "RepositoryImportBenchmarkDatasetManifest":
        diagnostics_payload = payload.get("diagnostics", [])
        if diagnostics_payload is None:
            diagnostics_payload = []
        if not isinstance(diagnostics_payload, list):
            raise TypeError("dataset diagnostics payload must be a list")
        return cls(
            dataset_id=str(payload["dataset_id"]),
            dataset_kind=str(payload["dataset_kind"]),
            source_sql_digest=DigestRef.parse(str(payload["source_sql_digest"])),
            source_sql_bytes=_required_int(payload["source_sql_bytes"]),
            table_count=_required_int(payload["table_count"]),
            row_count_total=_required_int(payload["row_count_total"]),
            largest_table_row_count=_required_int(payload["largest_table_row_count"]),
            insert_statement_count=_optional_int(payload.get("insert_statement_count")),
            validation_table_names=_normalize_requested_tables(
                payload.get("validation_table_names")
                if payload.get("validation_table_names") is not None
                else payload.get(DATASET_METADATA_VALIDATION_TABLES_KEY)
            ),
            business_label=_optional_str(payload.get("business_label")),
            anonymization_note=_optional_str(payload.get("anonymization_note")),
            created_at=_optional_str(payload.get("created_at")),
            diagnostics=tuple(DiagnosticRecord.from_payload(item) for item in diagnostics_payload),
        )


@dataclass(frozen=True, slots=True)
class RepositoryImportBenchmarkDatasetResolution:
    spec: RepositoryImportBenchmarkDatasetSpec
    manifest: RepositoryImportBenchmarkDatasetManifest
    source_snapshot: SnapshotMaterializationResult
    source_sql_text: str
    source_sql_materialization_ms: int | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.spec, RepositoryImportBenchmarkDatasetSpec):
            raise TypeError("spec must be a RepositoryImportBenchmarkDatasetSpec")
        if not isinstance(self.manifest, RepositoryImportBenchmarkDatasetManifest):
            raise TypeError("manifest must be a RepositoryImportBenchmarkDatasetManifest")
        if not isinstance(self.source_snapshot, SnapshotMaterializationResult):
            raise TypeError("source_snapshot must be a SnapshotMaterializationResult")
        if not isinstance(self.source_sql_text, str):
            raise TypeError("source_sql_text must be a string")
        if self.source_sql_materialization_ms is not None and (
            not isinstance(self.source_sql_materialization_ms, int)
            or isinstance(self.source_sql_materialization_ms, bool)
            or self.source_sql_materialization_ms < 0
        ):
            raise ValueError("source_sql_materialization_ms must be a non-negative integer or None")
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")


class RepositoryImportDatasetResolver:
    def __init__(self, dataset_root: Path) -> None:
        self.dataset_root = resolve_benchmark_path(dataset_root)

    def resolve(self, dataset_ids: Sequence[str] | None = None) -> tuple[RepositoryImportBenchmarkDatasetSpec, ...]:
        if not self.dataset_root.is_dir():
            raise ValueError(f"dataset root does not exist: {self.dataset_root}")

        selected_ids = {canonical_identifier(dataset_id) for dataset_id in dataset_ids or () if str(dataset_id).strip()}
        specs: list[RepositoryImportBenchmarkDatasetSpec] = []
        missing_source_files: list[str] = []
        found_ids: set[str] = set()

        for dataset_dir in sorted(path for path in self.dataset_root.iterdir() if path.is_dir()):
            spec, missing_source_file = self._build_dataset_spec(dataset_dir)
            if spec is None:
                if missing_source_file is not None:
                    missing_source_files.append(missing_source_file)
                continue
            canonical_dataset_id = canonical_identifier(spec.dataset_id)
            if selected_ids and canonical_dataset_id not in selected_ids:
                continue
            specs.append(spec)
            found_ids.add(canonical_dataset_id)

        if selected_ids:
            missing = sorted(selected_ids - found_ids)
            for dataset_id in missing:
                spec, missing_source_file = self._build_nested_dataset_spec(dataset_id)
                if spec is None:
                    if missing_source_file is not None:
                        missing_source_files.append(missing_source_file)
                    continue
                canonical_dataset_id = canonical_identifier(spec.dataset_id)
                specs.append(spec)
                found_ids.add(canonical_dataset_id)
            missing = sorted(selected_ids - found_ids)
            if missing:
                message = f"dataset(s) not found in root {self.dataset_root}: {missing}"
                if missing_source_files:
                    message += "; missing source file(s): " + ", ".join(sorted(dict.fromkeys(missing_source_files)))
                raise ValueError(message)

        return tuple(specs)

    def _build_dataset_spec(
        self,
        dataset_dir: Path,
        *,
        dataset_id: str | None = None,
    ) -> tuple[RepositoryImportBenchmarkDatasetSpec | None, str | None]:
        metadata_path = _find_metadata_path(dataset_dir)
        metadata = _load_dataset_metadata(metadata_path)
        effective_dataset_id = canonical_identifier(
            str(metadata.get("dataset_id") or dataset_id or _relative_dataset_id(self.dataset_root, dataset_dir))
        )
        source_sql_relative_path = _resolve_dataset_source_sql_relative_path(dataset_dir, metadata)
        if source_sql_relative_path is None:
            return None, f"{effective_dataset_id} -> {Path(DEFAULT_DATASET_SOURCE_FILE).as_posix()}"
        source_sql_path = dataset_dir / source_sql_relative_path
        if not source_sql_path.is_file():
            return None, f"{effective_dataset_id} -> {source_sql_relative_path.as_posix()}"
        return (
            RepositoryImportBenchmarkDatasetSpec(
                dataset_id=effective_dataset_id,
                dataset_kind=_normalize_dataset_kind(
                    str(metadata.get("dataset_kind") or _dataset_kind_from_dir(self.dataset_root, dataset_dir))
                ),
                dataset_dir=dataset_dir,
                source_sql_path=source_sql_path,
                dataset_metadata_path=metadata_path,
                requested_tables=_normalize_requested_tables(metadata.get("requested_tables")),
                validation_table_names=_normalize_requested_tables(
                    metadata.get(DATASET_METADATA_VALIDATION_TABLES_KEY)
                    if metadata.get(DATASET_METADATA_VALIDATION_TABLES_KEY) is not None
                    else metadata.get("validation_table_names")
                ),
                business_label=_optional_str(metadata.get("business_label")),
                anonymization_note=_optional_str(metadata.get("anonymization_note")),
            ),
            None,
        )

    def _build_nested_dataset_spec(
        self,
        dataset_id: str,
    ) -> tuple[RepositoryImportBenchmarkDatasetSpec | None, str | None]:
        candidate_dir = self.dataset_root / Path(dataset_id)
        if not candidate_dir.is_dir():
            return None, None
        return self._build_dataset_spec(candidate_dir, dataset_id=dataset_id)


class RepositoryImportDatasetManifestBuilder:
    def build(
        self,
        spec: RepositoryImportBenchmarkDatasetSpec,
        *,
        requested_tables: Sequence[str] | None = None,
    ) -> RepositoryImportBenchmarkDatasetResolution:
        if not spec.source_sql_path.is_file():
            raise ValueError(f"source SQL file not found: {spec.source_sql_path}")
        source_sql_text = spec.source_sql_path.read_text(encoding="utf-8")
        effective_requested_tables = tuple(
            canonical_identifier(table)
            for table in (requested_tables if requested_tables is not None else spec.requested_tables)
            if str(table).strip()
        )
        materialize_start = perf_counter()
        source_snapshot = materialize_sql_source(
            source_sql=source_sql_text,
            requested_tables=effective_requested_tables,
        )
        if source_snapshot.table_set is None:
            raise ValueError("snapshot materialization did not produce a table set")
        missing_validation_tables = sorted(
            set(spec.validation_table_names) - set(source_snapshot.table_set.tables)
        )
        if missing_validation_tables:
            raise ValueError(
                "validation_tables were not found in the SQL source: "
                f"{missing_validation_tables}"
            )

        row_counts = [table.descriptor.row_count for table in source_snapshot.table_set.tables.values()]
        manifest = RepositoryImportBenchmarkDatasetManifest(
            dataset_id=spec.dataset_id,
            dataset_kind=spec.dataset_kind,
            source_sql_digest=DigestRef.from_bytes(source_sql_text.encode("utf-8")),
            source_sql_bytes=len(spec.source_sql_path.read_bytes()),
            table_count=source_snapshot.summary.table_count,
            row_count_total=source_snapshot.summary.row_count_total or 0,
            largest_table_row_count=max(row_counts) if row_counts else 0,
            insert_statement_count=_count_insert_statements(source_sql_text),
            validation_table_names=spec.validation_table_names,
            business_label=spec.business_label,
            anonymization_note=spec.anonymization_note,
            created_at=_utc_now_iso(),
            diagnostics=tuple(source_snapshot.diagnostics),
        )
        return RepositoryImportBenchmarkDatasetResolution(
            spec=spec,
            manifest=manifest,
            source_snapshot=source_snapshot,
            source_sql_text=source_sql_text,
            source_sql_materialization_ms=_elapsed_ms(materialize_start),
            diagnostics=tuple(source_snapshot.diagnostics),
        )


def _find_metadata_path(dataset_dir: Path) -> Path | None:
    yaml_path = dataset_dir / DEFAULT_DATASET_METADATA_FILE
    if yaml_path.is_file():
        return yaml_path
    json_path = dataset_dir / "dataset.json"
    if json_path.is_file():
        return json_path
    return None


def _load_dataset_metadata(path: Path | None) -> dict[str, object]:
    if path is None or not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise TypeError("dataset metadata JSON must be an object")
        return payload

    metadata: dict[str, object] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = _parse_scalar_value(value.strip())
    return metadata


def _parse_scalar_value(value: str) -> object:
    if not value:
        return ""
    if value.startswith(("'", '"', "[", "{")):
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError):
            pass
    lowered = value.lower()
    if lowered in {"null", "none", "~"}:
        return None
    if lowered in {"true", "false"}:
        return lowered == "true"
    return value


def _normalize_requested_tables(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        items = value
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return ()
        if stripped.startswith("["):
            try:
                parsed = ast.literal_eval(stripped)
            except (ValueError, SyntaxError):
                parsed = [part.strip() for part in stripped.strip("[]").split(",")]
            items = parsed if isinstance(parsed, (list, tuple)) else [parsed]
        else:
            items = [part.strip() for part in stripped.split(",")]
    else:
        return (canonical_identifier(str(value)),)
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        table_name = canonical_identifier(str(item))
        if not table_name or table_name in seen:
            continue
        seen.add(table_name)
        normalized.append(table_name)
    return tuple(normalized)


def _resolve_source_sql_relative_path(value: object) -> Path:
    if value is None:
        return Path(DEFAULT_DATASET_SOURCE_FILE)
    if not isinstance(value, str):
        raise TypeError(f"{DATASET_METADATA_SOURCE_SQL_FILE_KEY} must be a string or null")
    stripped = value.strip()
    if not stripped:
        return Path(DEFAULT_DATASET_SOURCE_FILE)
    relative_path = Path(stripped)
    if relative_path.is_absolute():
        raise ValueError(f"{DATASET_METADATA_SOURCE_SQL_FILE_KEY} must be a relative path")
    if any(part == ".." for part in relative_path.parts):
        raise ValueError(f"{DATASET_METADATA_SOURCE_SQL_FILE_KEY} must not contain parent path segments")
    return relative_path


def _resolve_dataset_source_sql_relative_path(dataset_dir: Path, metadata: Mapping[str, object]) -> Path | None:
    configured_source_sql_file = metadata.get(DATASET_METADATA_SOURCE_SQL_FILE_KEY)
    if configured_source_sql_file is not None:
        return _resolve_source_sql_relative_path(configured_source_sql_file)
    for candidate in (Path(DEFAULT_DATASET_SOURCE_FILE), Path("sql") / DEFAULT_DATASET_SOURCE_FILE):
        if (dataset_dir / candidate).is_file():
            return candidate
    return None


def _relative_dataset_id(dataset_root: Path, dataset_dir: Path) -> str:
    try:
        return dataset_dir.relative_to(dataset_root).as_posix()
    except ValueError:
        return dataset_dir.name


def _dataset_kind_from_dir(dataset_root: Path, dataset_dir: Path) -> str:
    try:
        relative_parts = dataset_dir.relative_to(dataset_root).parts
    except ValueError:
        relative_parts = dataset_dir.parts
    if not relative_parts:
        return dataset_dir.name
    return relative_parts[0]


def _normalize_dataset_kind(value: str) -> str:
    normalized = canonical_identifier(value).replace("-", "_").upper()
    if normalized in RepositoryImportBenchmarkDatasetKind.__members__:
        return normalized
    return normalized


def _count_insert_statements(source_sql_text: str) -> int | None:
    matches = re.findall(r"(?i)\binsert\s+into\b", source_sql_text)
    return len(matches) if matches else None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))


def _required_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("expected an integer")
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _required_int(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)
