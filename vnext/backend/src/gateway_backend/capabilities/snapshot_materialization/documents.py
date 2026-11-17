"""Snapshot table descriptor document codecs owned by snapshot_materialization."""

from __future__ import annotations

from gateway_shared_kernel import DigestRef

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    DegradedReason,
    DiagnosticSeverity,
    MaterializationDiagnostic,
    MaterializationDiagnosticCode,
    MaterializationStage,
    SnapshotColumnDescriptor,
    SnapshotTableDescriptor,
)
from gateway_backend.document_fields import document_string, document_string_tuple


def _document_int(raw: dict[str, object], key: str) -> int:
    value = raw[key]
    if type(value) is not int or isinstance(value, bool) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


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
    if type(raw) is not dict:
        raise ValueError("snapshot descriptor must be an object")
    expected = {
        "table_name",
        "display_table_name",
        "columns",
        "primary_key_columns",
        "compare_key_columns",
        "row_count",
        "materialization_stage",
        "compare_schema_digest",
        "table_ruleset_version",
        "row_materialization_profile",
        "scalar_encoding_version",
        "raw_content_digest",
        "degraded_reason",
        "diagnostics",
    }
    if set(raw) != expected:
        raise ValueError("snapshot descriptor fields are invalid")
    columns_raw = raw["columns"]
    diagnostics_raw = raw["diagnostics"]
    if type(columns_raw) is not list or type(diagnostics_raw) is not list:
        raise ValueError("snapshot descriptor columns and diagnostics must be lists")
    columns: list[SnapshotColumnDescriptor] = []
    for item in columns_raw:
        if type(item) is not dict or set(item) != {
            "name",
            "display_name",
            "nullable",
            "scalar_type",
        }:
            raise ValueError("snapshot column fields are invalid")
        scalar_type = item["scalar_type"]
        if scalar_type is not None and type(scalar_type) is not str:
            raise ValueError("scalar_type must be a string or null")
        if type(item["nullable"]) is not bool:
            raise ValueError("nullable must be bool")
        columns.append(
            SnapshotColumnDescriptor(
                name=document_string(item, "name"),
                display_name=document_string(item, "display_name"),
                nullable=item["nullable"],
                scalar_type=scalar_type,
            )
        )
    diagnostics: list[MaterializationDiagnostic] = []
    for item in diagnostics_raw:
        if type(item) is not dict or set(item) != {
            "code",
            "severity",
            "message",
            "table",
            "column",
        }:
            raise ValueError("snapshot diagnostic fields are invalid")
        table = item["table"]
        column = item["column"]
        if (table is not None and type(table) is not str) or (
            column is not None and type(column) is not str
        ):
            raise ValueError("snapshot diagnostic table and column must be strings or null")
        diagnostics.append(
            MaterializationDiagnostic(
                code=MaterializationDiagnosticCode(document_string(item, "code")),
                severity=DiagnosticSeverity(document_string(item, "severity")),
                message=document_string(item, "message"),
                table=table,
                column=column,
            )
        )
    raw_content = raw["raw_content_digest"]
    raw_degraded = raw["degraded_reason"]
    if raw_content is not None and type(raw_content) is not str:
        raise ValueError("raw_content_digest must be a string or null")
    if raw_degraded is not None and type(raw_degraded) is not str:
        raise ValueError("degraded_reason must be a string or null")
    return SnapshotTableDescriptor(
        table_name=document_string(raw, "table_name"),
        display_table_name=document_string(raw, "display_table_name"),
        columns=tuple(columns),
        primary_key_columns=document_string_tuple(raw, "primary_key_columns"),
        compare_key_columns=document_string_tuple(raw, "compare_key_columns"),
        row_count=_document_int(raw, "row_count"),
        materialization_stage=MaterializationStage(document_string(raw, "materialization_stage")),
        compare_schema_digest=DigestRef(document_string(raw, "compare_schema_digest")),
        table_ruleset_version=_document_int(raw, "table_ruleset_version"),
        row_materialization_profile=document_string(raw, "row_materialization_profile"),
        scalar_encoding_version=_document_int(raw, "scalar_encoding_version"),
        raw_content_digest=None if raw_content is None else DigestRef(raw_content),
        degraded_reason=None if raw_degraded is None else DegradedReason(raw_degraded),
        diagnostics=tuple(diagnostics),
    )


__all__ = [
    "snapshot_descriptor_from_document",
    "snapshot_descriptor_to_document",
]
