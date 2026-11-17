"""Snapshot table descriptor document codecs owned by snapshot_materialization."""

from __future__ import annotations

from gateway_shared_kernel import DigestRef
from pydantic import BaseModel, ConfigDict

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    DegradedReason,
    DiagnosticSeverity,
    MaterializationDiagnostic,
    MaterializationDiagnosticCode,
    MaterializationStage,
    SnapshotColumnDescriptor,
    SnapshotTableDescriptor,
)


class _StrictDocument(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class _SnapshotColumnDocument(_StrictDocument):
    name: str
    display_name: str
    nullable: bool
    scalar_type: str | None


class _MaterializationDiagnosticDocument(_StrictDocument):
    code: str
    severity: str
    message: str
    table: str | None
    column: str | None


class _SnapshotDescriptorDocument(_StrictDocument):
    table_name: str
    display_table_name: str
    columns: list[_SnapshotColumnDocument]
    primary_key_columns: list[str]
    compare_key_columns: list[str]
    row_count: int
    materialization_stage: str
    compare_schema_digest: str
    table_ruleset_version: int
    row_materialization_profile: str
    scalar_encoding_version: int
    raw_content_digest: str | None
    degraded_reason: str | None
    diagnostics: list[_MaterializationDiagnosticDocument]


def snapshot_descriptor_to_document(descriptor: SnapshotTableDescriptor) -> dict[str, object]:
    return {
        "table_name": descriptor.table_name,
        "display_table_name": descriptor.display_table_name,
        "columns": [
            {
                "name": column.name,
                "display_name": column.display_name,
                "nullable": column.nullable,
                "scalar_type": column.scalar_type,
            }
            for column in descriptor.columns
        ],
        "primary_key_columns": list(descriptor.primary_key_columns),
        "compare_key_columns": list(descriptor.compare_key_columns),
        "row_count": descriptor.row_count,
        "materialization_stage": descriptor.materialization_stage.value,
        "compare_schema_digest": descriptor.compare_schema_digest.value,
        "table_ruleset_version": descriptor.table_ruleset_version,
        "row_materialization_profile": descriptor.row_materialization_profile,
        "scalar_encoding_version": descriptor.scalar_encoding_version,
        "raw_content_digest": None
        if descriptor.raw_content_digest is None
        else descriptor.raw_content_digest.value,
        "degraded_reason": None
        if descriptor.degraded_reason is None
        else descriptor.degraded_reason.value,
        "diagnostics": [
            {
                "code": diagnostic.code.value,
                "severity": diagnostic.severity.value,
                "message": diagnostic.message,
                "table": diagnostic.table,
                "column": diagnostic.column,
            }
            for diagnostic in descriptor.diagnostics
        ],
    }


def snapshot_descriptor_from_document(raw: object) -> SnapshotTableDescriptor:
    doc = _SnapshotDescriptorDocument.model_validate(raw)
    return SnapshotTableDescriptor(
        table_name=doc.table_name,
        display_table_name=doc.display_table_name,
        columns=tuple(
            SnapshotColumnDescriptor(c.name, c.display_name, c.nullable, c.scalar_type)
            for c in doc.columns
        ),
        primary_key_columns=tuple(doc.primary_key_columns),
        compare_key_columns=tuple(doc.compare_key_columns),
        row_count=doc.row_count,
        materialization_stage=MaterializationStage(doc.materialization_stage),
        compare_schema_digest=DigestRef(doc.compare_schema_digest),
        table_ruleset_version=doc.table_ruleset_version,
        row_materialization_profile=doc.row_materialization_profile,
        scalar_encoding_version=doc.scalar_encoding_version,
        raw_content_digest=(
            None if doc.raw_content_digest is None else DigestRef(doc.raw_content_digest)
        ),
        degraded_reason=(
            None if doc.degraded_reason is None else DegradedReason(doc.degraded_reason)
        ),
        diagnostics=tuple(
            MaterializationDiagnostic(
                MaterializationDiagnosticCode(d.code),
                DiagnosticSeverity(d.severity),
                d.message,
                d.table,
                d.column,
            )
            for d in doc.diagnostics
        ),
    )


__all__ = [
    "snapshot_descriptor_from_document",
    "snapshot_descriptor_to_document",
]
