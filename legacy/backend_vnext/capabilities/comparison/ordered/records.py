from __future__ import annotations

from collections.abc import Mapping, Sequence

from ....artifacts import ArtifactRef, LocalArtifactStore, RecordsArtifact, RecordsArtifactManifest, records_parquet_content, store_records_artifact
from ....core.digests import DigestRef, canonical_json_bytes
from ....core.diagnostics import DiagnosticRecord
from ..models import ORDERED_DIFF_CONTRACT_VERSION
from ....core.identifiers import canonical_identifier
from .models import OrderedRecord, OrderedRecordKind, OrderedSummary


def ordered_record_sort_key(record: OrderedRecord) -> tuple[object, ...]:
    kind_priority = {
        OrderedRecordKind.ORDERED_ROW_DELETED: 0,
        OrderedRecordKind.ORDERED_INTERVAL_DELETED: 1,
        OrderedRecordKind.ORDERED_ROW_MOVED: 2,
        OrderedRecordKind.ORDERED_POSITION_CHANGED: 2,
        OrderedRecordKind.ORDERED_ROW_MODIFIED: 3,
        OrderedRecordKind.ORDERED_ROW_ADDED: 4,
        OrderedRecordKind.ORDERED_INTERVAL_INSERTED: 5,
        OrderedRecordKind.ORDERED_BLANK_CHANGED: 6,
        OrderedRecordKind.ORDERED_TABLE_DEGRADED: 7,
    }
    position_key = (
        record.after_position
        if record.after_position is not None
        else record.before_position
        if record.before_position is not None
        else 10**9
    )
    return (
        kind_priority.get(record.record_kind, 99),
        position_key,
        canonical_json_bytes(record.entity_key),
        tuple(record.changed_columns),
        canonical_identifier(record.table_name),
    )


def sort_ordered_records(records: Sequence[OrderedRecord]) -> tuple[OrderedRecord, ...]:
    return tuple(sorted(records, key=ordered_record_sort_key))


def write_ordered_records(
    *,
    table_name: str,
    records: Sequence[OrderedRecord],
    comparison_contract_version: str,
    projection_contract_version: str,
    table_ruleset_version: str,
    scalar_encoding_version: str,
    row_diff_detail_policy: str,
    ordered_policy_digest: DigestRef | str | None,
    ordered_preprocess_applied: str,
    replay_guarantee: str,
    table_processing_mode: str,
    ordered_summary: OrderedSummary | Mapping[str, object] | None,
    before_ordered_digest: DigestRef | str | None,
    current_ordered_digest: DigestRef | str | None,
    diagnostics: Sequence[DiagnosticRecord],
    records_store: LocalArtifactStore | None = None,
) -> tuple[ArtifactRef, RecordsArtifact | None]:
    sorted_records = sort_ordered_records(records)
    content = records_parquet_content(sorted_records)
    manifest = RecordsArtifactManifest(
        table_name=table_name,
        record_count=content.record_count,
        row_diff_detail_policy=row_diff_detail_policy,
        content_digest=content.content_digest,
        content_size_bytes=len(content.content_bytes),
        metadata={
            "comparison_contract_version": comparison_contract_version,
            "projection_contract_version": projection_contract_version,
            "table_ruleset_version": table_ruleset_version,
            "scalar_encoding_version": scalar_encoding_version,
            "ordered_contract_version": ORDERED_DIFF_CONTRACT_VERSION,
            "ordered_policy_digest": _optional_digest_payload(ordered_policy_digest),
            "ordered_preprocess_applied": ordered_preprocess_applied,
            "replay_guarantee": replay_guarantee,
            "table_processing_mode": table_processing_mode,
            "ordered_summary": _ordered_summary_payload(ordered_summary),
            "before_ordered_digest": _optional_digest_payload(before_ordered_digest),
            "current_ordered_digest": _optional_digest_payload(current_ordered_digest),
        },
        diagnostics=tuple(diagnostics),
    )
    artifact_manifest = manifest.to_artifact_manifest()
    manifest_digest = DigestRef.from_payload(artifact_manifest.to_payload())
    logical_ref = artifact_manifest.to_ref(manifest_digest)
    if records_store is None:
        return logical_ref, None
    stored = store_records_artifact(records_store, manifest, sorted_records)
    return stored.ref, stored


def _ordered_summary_payload(summary: OrderedSummary | Mapping[str, object] | None) -> dict[str, object] | None:
    if summary is None:
        return None
    if isinstance(summary, OrderedSummary):
        return summary.to_payload()
    return dict(summary)


def _optional_digest_payload(value: DigestRef | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, DigestRef):
        return value.to_payload()
    return DigestRef.parse(str(value)).to_payload()
