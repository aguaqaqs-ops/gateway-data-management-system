from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from ....artifacts import ArtifactRef, LocalArtifactStore, RecordsArtifact
from ....core.digests import DigestRef
from ....core.diagnostics import DiagnosticRecord
from ....core.identifiers import canonical_identifier
from ...snapshot_materialization.models import SnapshotTable
from ..models import ComparisonTableFact, ProjectionSchema, ProjectionTable

if TYPE_CHECKING:
    from .policy import OrderedTablePolicy


class OrderedEntityKeyKind(StrEnum):
    REAL_STABLE = "REAL_STABLE"
    PSEUDO_BLANK = "PSEUDO_BLANK"


class OrderedSemanticKind(StrEnum):
    DATA_INSERT = "DATA_INSERT"
    DATA_DELETE = "DATA_DELETE"
    MOVE = "MOVE"
    CONTENT_UPDATE = "CONTENT_UPDATE"
    BLANK_INSERT_INTERVAL = "BLANK_INSERT_INTERVAL"
    BLANK_DELETE_INTERVAL = "BLANK_DELETE_INTERVAL"


class OrderedRecordKind(StrEnum):
    ORDERED_ROW_ADDED = "ORDERED_ROW_ADDED"
    ORDERED_ROW_DELETED = "ORDERED_ROW_DELETED"
    ORDERED_ROW_MODIFIED = "ORDERED_ROW_MODIFIED"
    ORDERED_ROW_MOVED = "ORDERED_ROW_MOVED"
    ORDERED_POSITION_CHANGED = "ORDERED_POSITION_CHANGED"
    ORDERED_INTERVAL_INSERTED = "ORDERED_INTERVAL_INSERTED"
    ORDERED_INTERVAL_DELETED = "ORDERED_INTERVAL_DELETED"
    ORDERED_BLANK_CHANGED = "ORDERED_BLANK_CHANGED"
    ORDERED_TABLE_DEGRADED = "ORDERED_TABLE_DEGRADED"


class OrderedReplayGuarantee(StrEnum):
    EXACT = "EXACT"
    PARTIAL = "PARTIAL"
    UNSUPPORTED = "UNSUPPORTED"


class OrderedTableProcessingMode(StrEnum):
    ORDERED_TAIL_SEGMENT = "ORDERED_TAIL_SEGMENT"
    ORDERED_LOCAL_PATCH = "ORDERED_LOCAL_PATCH"
    ORDERED_SHIFT_REPAIRED = "ORDERED_SHIFT_REPAIRED"
    ORDERED_REORDER_COMPLEX = "ORDERED_REORDER_COMPLEX"
    DEGRADED = "DEGRADED"


@dataclass(frozen=True, slots=True)
class OrderedPreparedRow:
    row_key: str
    entity_key_kind: OrderedEntityKeyKind | str
    position: int
    row: Mapping[str, object]
    blank_signature: tuple[tuple[str, object], ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.row_key, str) or not self.row_key.strip():
            raise ValueError("row_key must be a non-empty string")
        object.__setattr__(self, "row_key", canonical_identifier(self.row_key))
        object.__setattr__(self, "entity_key_kind", OrderedEntityKeyKind(self.entity_key_kind))
        if not isinstance(self.position, int) or isinstance(self.position, bool) or self.position < 0:
            raise ValueError("position must be a non-negative integer")
        if not isinstance(self.row, Mapping):
            raise TypeError("row must be a mapping")
        object.__setattr__(self, "row", dict(self.row))
        if self.blank_signature is not None and not isinstance(self.blank_signature, tuple):
            object.__setattr__(self, "blank_signature", tuple(self.blank_signature))


@dataclass(frozen=True, slots=True)
class OrderedPreparedRowsCacheEntry:
    source_table_name: str
    rows: tuple[OrderedPreparedRow, ...]
    ordered_digest_parts: object | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_table_name, str) or not self.source_table_name.strip():
            raise ValueError("source_table_name must be a non-empty string")
        object.__setattr__(self, "source_table_name", canonical_identifier(self.source_table_name))
        object.__setattr__(self, "rows", tuple(self.rows))


@dataclass(slots=True)
class OrderedPreparedRowsCache:
    entries: dict[tuple[object, ...], OrderedPreparedRowsCacheEntry] = field(default_factory=dict)
    hit_count: int = 0
    miss_count: int = 0
    saved_row_count: int = 0
    ordered_digest_parts_reuse_count: int = 0
    ordered_digest_parts_fallback_count: int = 0
    ordered_digest_parts_saved_row_count: int = 0

    def lookup(self, key: tuple[object, ...] | None) -> OrderedPreparedRowsCacheEntry | None:
        if key is None:
            return None
        entry = self.entries.get(key)
        if entry is None:
            self.miss_count += 1
            return None
        self.hit_count += 1
        self.saved_row_count += len(entry.rows)
        return entry

    def write(
        self,
        *,
        key: tuple[object, ...] | None,
        source_table_name: str,
        rows: Sequence[OrderedPreparedRow],
    ) -> None:
        if key is None or key in self.entries:
            return
        self.entries[key] = OrderedPreparedRowsCacheEntry(
            source_table_name=source_table_name,
            rows=tuple(rows),
        )

    def write_ordered_digest_parts(
        self,
        *,
        key: tuple[object, ...] | None,
        digest_parts: object | None,
    ) -> None:
        if key is None or digest_parts is None:
            return
        entry = self.entries.get(key)
        if entry is None or entry.ordered_digest_parts is not None:
            return
        self.entries[key] = OrderedPreparedRowsCacheEntry(
            source_table_name=entry.source_table_name,
            rows=entry.rows,
            ordered_digest_parts=digest_parts,
        )


@dataclass(frozen=True, slots=True)
class OrderedSemanticOp:
    semantic_kind: OrderedSemanticKind | str
    row_key: str
    entity_key_kind: OrderedEntityKeyKind | str
    before_position: int | None
    after_position: int | None
    changed_columns: tuple[str, ...]
    payload_before: Mapping[str, object] | None
    payload_after: Mapping[str, object] | None
    interval_index: int | None
    interval_label: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "semantic_kind", OrderedSemanticKind(self.semantic_kind))
        object.__setattr__(self, "entity_key_kind", OrderedEntityKeyKind(self.entity_key_kind))
        if not isinstance(self.row_key, str) or not self.row_key.strip():
            raise ValueError("row_key must be a non-empty string")
        object.__setattr__(self, "row_key", canonical_identifier(self.row_key))
        if self.changed_columns is not None and not isinstance(self.changed_columns, tuple):
            object.__setattr__(self, "changed_columns", tuple(self.changed_columns))
        if self.payload_before is not None and not isinstance(self.payload_before, Mapping):
            raise TypeError("payload_before must be a mapping or None")
        if self.payload_after is not None and not isinstance(self.payload_after, Mapping):
            raise TypeError("payload_after must be a mapping or None")
        if self.before_position is not None and (
            not isinstance(self.before_position, int)
            or isinstance(self.before_position, bool)
            or self.before_position < 0
        ):
            raise ValueError("before_position must be a non-negative integer or None")
        if self.after_position is not None and (
            not isinstance(self.after_position, int)
            or isinstance(self.after_position, bool)
            or self.after_position < 0
        ):
            raise ValueError("after_position must be a non-negative integer or None")
        if self.interval_index is not None and (
            not isinstance(self.interval_index, int)
            or isinstance(self.interval_index, bool)
            or self.interval_index < 0
        ):
            raise ValueError("interval_index must be a non-negative integer or None")
        if self.interval_label is not None and (
            not isinstance(self.interval_label, str) or not self.interval_label.strip()
        ):
            raise ValueError("interval_label must be a non-empty string or None")


@dataclass(frozen=True, slots=True)
class OrderedRecord:
    table_name: str
    record_kind: OrderedRecordKind | str
    semantic_kind: OrderedSemanticKind | str
    entity_key_kind: OrderedEntityKeyKind | str
    entity_key: str
    before_position: int | None = None
    after_position: int | None = None
    topology_before_rank: int | None = None
    topology_after_rank: int | None = None
    interval_index: int | None = None
    interval_label: str | None = None
    changed_columns: tuple[str, ...] = field(default_factory=tuple)
    payload_before: Mapping[str, object] | None = None
    payload_after: Mapping[str, object] | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.table_name, str) or not self.table_name.strip():
            raise ValueError("table_name must be a non-empty string")
        object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        object.__setattr__(self, "record_kind", OrderedRecordKind(self.record_kind))
        object.__setattr__(self, "semantic_kind", OrderedSemanticKind(self.semantic_kind))
        object.__setattr__(self, "entity_key_kind", OrderedEntityKeyKind(self.entity_key_kind))
        if not isinstance(self.entity_key, str) or not self.entity_key.strip():
            raise ValueError("entity_key must be a non-empty string")
        object.__setattr__(self, "entity_key", canonical_identifier(self.entity_key))
        if not isinstance(self.changed_columns, tuple):
            object.__setattr__(self, "changed_columns", tuple(self.changed_columns))
        if self.payload_before is not None and not isinstance(self.payload_before, Mapping):
            raise TypeError("payload_before must be a mapping or None")
        if self.payload_after is not None and not isinstance(self.payload_after, Mapping):
            raise TypeError("payload_after must be a mapping or None")
        for field_name in ("before_position", "after_position", "topology_before_rank", "topology_after_rank", "interval_index"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise ValueError(f"{field_name} must be a non-negative integer or None")
        if self.interval_label is not None and (
            not isinstance(self.interval_label, str) or not self.interval_label.strip()
        ):
            raise ValueError("interval_label must be a non-empty string or None")
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "table_name": self.table_name,
            "record_kind": self.record_kind.value,
            "semantic_kind": self.semantic_kind.value,
            "entity_key_kind": self.entity_key_kind.value,
            "entity_key": self.entity_key,
            "changed_columns": list(self.changed_columns),
        }
        if self.before_position is not None:
            payload["before_position"] = self.before_position
        if self.after_position is not None:
            payload["after_position"] = self.after_position
        if self.topology_before_rank is not None:
            payload["topology_before_rank"] = self.topology_before_rank
        if self.topology_after_rank is not None:
            payload["topology_after_rank"] = self.topology_after_rank
        if self.interval_index is not None:
            payload["interval_index"] = self.interval_index
        if self.interval_label is not None:
            payload["interval_label"] = self.interval_label
        if self.payload_before is not None:
            payload["payload_before"] = dict(self.payload_before)
        if self.payload_after is not None:
            payload["payload_after"] = dict(self.payload_after)
        if self.diagnostics:
            payload["diagnostics"] = [diagnostic.to_payload() for diagnostic in self.diagnostics]
        return payload


@dataclass(frozen=True, slots=True)
class OrderedSummary:
    row_added_count: int = 0
    row_deleted_count: int = 0
    row_modified_count: int = 0
    row_moved_count: int = 0
    position_changed_count: int = 0
    interval_inserted_count: int = 0
    interval_deleted_count: int = 0
    blank_changed_count: int = 0
    degraded_count: int = 0

    def __post_init__(self) -> None:
        for field_name in (
            "row_added_count",
            "row_deleted_count",
            "row_modified_count",
            "row_moved_count",
            "position_changed_count",
            "interval_inserted_count",
            "interval_deleted_count",
            "blank_changed_count",
            "degraded_count",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")

    def to_payload(self) -> dict[str, object]:
        return {
            "row_added_count": self.row_added_count,
            "row_deleted_count": self.row_deleted_count,
            "row_modified_count": self.row_modified_count,
            "row_moved_count": self.row_moved_count,
            "position_changed_count": self.position_changed_count,
            "interval_inserted_count": self.interval_inserted_count,
            "interval_deleted_count": self.interval_deleted_count,
            "blank_changed_count": self.blank_changed_count,
            "degraded_count": self.degraded_count,
        }


@dataclass(frozen=True, slots=True)
class OrderedReplayValidation:
    semantic_replay_passed: bool
    artifact_replay_passed: bool
    mismatch_count: int
    mismatch_examples: tuple[Mapping[str, object], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.semantic_replay_passed, bool):
            raise TypeError("semantic_replay_passed must be a bool")
        if not isinstance(self.artifact_replay_passed, bool):
            raise TypeError("artifact_replay_passed must be a bool")
        if not isinstance(self.mismatch_count, int) or isinstance(self.mismatch_count, bool) or self.mismatch_count < 0:
            raise ValueError("mismatch_count must be a non-negative integer")
        if not isinstance(self.mismatch_examples, tuple):
            object.__setattr__(self, "mismatch_examples", tuple(self.mismatch_examples))
        normalized_examples: list[Mapping[str, object]] = []
        for example in self.mismatch_examples:
            if not isinstance(example, Mapping):
                raise TypeError("mismatch_examples must contain mappings")
            normalized_examples.append(dict(example))
        object.__setattr__(self, "mismatch_examples", tuple(normalized_examples))

    def as_dict(self) -> dict[str, object]:
        return {
            "semantic_replay_passed": self.semantic_replay_passed,
            "artifact_replay_passed": self.artifact_replay_passed,
            "mismatch_count": self.mismatch_count,
            "mismatch_examples": [dict(example) for example in self.mismatch_examples],
        }


@dataclass(frozen=True, slots=True)
class OrderedTableCompareInput:
    table_name: str
    projection_schema: ProjectionSchema | None = None
    ordered_policy: "OrderedTablePolicy" | None = None
    comparison_contract_version: str = ""
    projection_contract_version: str = ""
    table_ruleset_version: str = ""
    scalar_encoding_version: str = ""
    row_diff_detail_policy: str = "COUNTS_ONLY"
    before_descriptor: Mapping[str, object] | None = None
    current_descriptor: Mapping[str, object] | None = None
    before_table: SnapshotTable | None = None
    current_table: SnapshotTable | None = None
    before_projection: ProjectionTable | None = None
    current_projection: ProjectionTable | None = None
    row_counts: tuple[int | None, int | None] | None = None
    records_store: LocalArtifactStore | None = None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    benchmark_run_id: str | None = None
    prepared_rows_cache: OrderedPreparedRowsCache | None = None
    before_prepare_cache_key: tuple[object, ...] | None = None
    current_prepare_cache_key: tuple[object, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.table_name, str) or not self.table_name.strip():
            raise ValueError("table_name must be a non-empty string")
        object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        if self.projection_schema is not None and not isinstance(self.projection_schema, ProjectionSchema):
            raise TypeError("projection_schema must be a ProjectionSchema or None")
        for field_name in (
            "comparison_contract_version",
            "projection_contract_version",
            "table_ruleset_version",
            "scalar_encoding_version",
            "row_diff_detail_policy",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.before_descriptor is not None and not isinstance(self.before_descriptor, Mapping):
            raise TypeError("before_descriptor must be a mapping or None")
        if self.current_descriptor is not None and not isinstance(self.current_descriptor, Mapping):
            raise TypeError("current_descriptor must be a mapping or None")
        if self.before_table is not None and not isinstance(self.before_table, SnapshotTable):
            raise TypeError("before_table must be a SnapshotTable or None")
        if self.current_table is not None and not isinstance(self.current_table, SnapshotTable):
            raise TypeError("current_table must be a SnapshotTable or None")
        if self.before_projection is not None and not isinstance(self.before_projection, ProjectionTable):
            raise TypeError("before_projection must be a ProjectionTable or None")
        if self.current_projection is not None and not isinstance(self.current_projection, ProjectionTable):
            raise TypeError("current_projection must be a ProjectionTable or None")
        if self.row_counts is not None and (
            not isinstance(self.row_counts, tuple) or len(self.row_counts) != 2
        ):
            raise ValueError("row_counts must be a pair of before/current counts or None")
        if self.records_store is not None and not isinstance(self.records_store, LocalArtifactStore):
            raise TypeError("records_store must be a LocalArtifactStore or None")
        if self.prepared_rows_cache is not None and not isinstance(
            self.prepared_rows_cache,
            OrderedPreparedRowsCache,
        ):
            raise TypeError("prepared_rows_cache must be an OrderedPreparedRowsCache or None")
        for field_name in ("before_prepare_cache_key", "current_prepare_cache_key"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, tuple):
                raise TypeError(f"{field_name} must be a tuple or None")
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))
        if self.benchmark_run_id is not None and not isinstance(self.benchmark_run_id, str):
            raise TypeError("benchmark_run_id must be a string or None")


@dataclass(frozen=True, slots=True)
class OrderedTableCompareResult:
    table_fact: ComparisonTableFact
    ordered_summary: OrderedSummary | None = None
    before_ordered_digest: DigestRef | str | None = None
    current_ordered_digest: DigestRef | str | None = None
    records: tuple[OrderedRecord, ...] = field(default_factory=tuple)
    records_ref: ArtifactRef | None = None
    records_artifact: RecordsArtifact | None = None
    replay_validation: OrderedReplayValidation | None = None
    replay_guarantee: OrderedReplayGuarantee | str = OrderedReplayGuarantee.UNSUPPORTED
    table_processing_mode: OrderedTableProcessingMode | str = OrderedTableProcessingMode.DEGRADED
    ordered_preprocess_applied: str = "NONE"
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    degrade_reason: str | None = None
    planner_mode: str | None = None
    prepared_row_count_before: int | None = None
    prepared_row_count_current: int | None = None
    ordered_input_source: str | None = None
    benchmark_phase_events: tuple[Mapping[str, object], ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.table_fact, ComparisonTableFact):
            raise TypeError("table_fact must be a ComparisonTableFact")
        if self.ordered_summary is not None and not isinstance(self.ordered_summary, OrderedSummary):
            raise TypeError("ordered_summary must be an OrderedSummary or None")
        if self.before_ordered_digest is not None:
            object.__setattr__(self, "before_ordered_digest", DigestRef.parse(str(self.before_ordered_digest)))
        if self.current_ordered_digest is not None:
            object.__setattr__(self, "current_ordered_digest", DigestRef.parse(str(self.current_ordered_digest)))
        if not isinstance(self.records, tuple):
            object.__setattr__(self, "records", tuple(self.records))
        normalized_records: list[OrderedRecord] = []
        for record in self.records:
            if not isinstance(record, OrderedRecord):
                raise TypeError("records must contain OrderedRecord values")
            normalized_records.append(record)
        object.__setattr__(self, "records", tuple(normalized_records))
        if self.records_ref is not None and not isinstance(self.records_ref, ArtifactRef):
            raise TypeError("records_ref must be an ArtifactRef or None")
        if self.records_artifact is not None and not isinstance(self.records_artifact, RecordsArtifact):
            raise TypeError("records_artifact must be a RecordsArtifact or None")
        if self.replay_validation is not None and not isinstance(self.replay_validation, OrderedReplayValidation):
            raise TypeError("replay_validation must be an OrderedReplayValidation or None")
        object.__setattr__(self, "replay_guarantee", OrderedReplayGuarantee(self.replay_guarantee))
        object.__setattr__(self, "table_processing_mode", OrderedTableProcessingMode(self.table_processing_mode))
        if not isinstance(self.ordered_preprocess_applied, str) or not self.ordered_preprocess_applied:
            raise ValueError("ordered_preprocess_applied must be a non-empty string")
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))
        if self.degrade_reason is not None and (
            not isinstance(self.degrade_reason, str) or not self.degrade_reason.strip()
        ):
            raise ValueError("degrade_reason must be a non-empty string or None")
        if self.planner_mode is not None and (
            not isinstance(self.planner_mode, str) or not self.planner_mode.strip()
        ):
            raise ValueError("planner_mode must be a non-empty string or None")
        for field_name in ("prepared_row_count_before", "prepared_row_count_current"):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError(f"{field_name} must be a non-negative integer or None")
        if self.ordered_input_source is not None and (
            not isinstance(self.ordered_input_source, str) or not self.ordered_input_source.strip()
        ):
            raise ValueError("ordered_input_source must be a non-empty string or None")
        if not isinstance(self.benchmark_phase_events, tuple):
            object.__setattr__(self, "benchmark_phase_events", tuple(self.benchmark_phase_events))
        normalized_phase_events: list[Mapping[str, object]] = []
        for event in self.benchmark_phase_events:
            if not isinstance(event, Mapping):
                raise TypeError("benchmark_phase_events must contain mappings")
            normalized_phase_events.append(dict(event))
        object.__setattr__(self, "benchmark_phase_events", tuple(normalized_phase_events))


def ordered_record_kind_for_semantic_kind(semantic_kind: OrderedSemanticKind | str) -> OrderedRecordKind:
    normalized = OrderedSemanticKind(semantic_kind)
    if normalized is OrderedSemanticKind.DATA_INSERT:
        return OrderedRecordKind.ORDERED_ROW_ADDED
    if normalized is OrderedSemanticKind.DATA_DELETE:
        return OrderedRecordKind.ORDERED_ROW_DELETED
    if normalized is OrderedSemanticKind.MOVE:
        return OrderedRecordKind.ORDERED_ROW_MOVED
    if normalized is OrderedSemanticKind.CONTENT_UPDATE:
        return OrderedRecordKind.ORDERED_ROW_MODIFIED
    if normalized is OrderedSemanticKind.BLANK_INSERT_INTERVAL:
        return OrderedRecordKind.ORDERED_INTERVAL_INSERTED
    return OrderedRecordKind.ORDERED_INTERVAL_DELETED
