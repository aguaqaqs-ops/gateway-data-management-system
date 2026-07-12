from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ...core.digests import DigestRef
from ...core.diagnostics import DiagnosticRecord
from ...core.row_digests import stable_rows_digest
from ...core.identifiers import canonical_identifier
from ...core.scalar_encoding import (
    normalize_snapshot_rows,
    normalize_snapshot_scalar_value,
    scalar_type_family,
)
from ..snapshot_materialization.models import SnapshotMaterializationResult
from .dolt_cli import CommandError, DoltCli
from .providers import (
    RepositoryImportFailurePhase,
    RepositoryImportPlan,
    RepositoryImportValidationPolicy,
    RepositoryImportValidationResult,
)


@dataclass(frozen=True, slots=True)
class RepositoryImportReadbackTableResult:
    table_name: str
    target_table_name: str
    matched: bool
    expected_row_count: int
    actual_row_count: int
    expected_schema_digest: DigestRef | None
    readback_schema_digest: DigestRef | None
    expected_row_digest: DigestRef | None
    readback_row_digest: DigestRef | None
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RepositoryImportReadbackResult:
    status: RepositoryImportValidationResult
    readback_snapshot_digest: DigestRef | None
    table_results: tuple[RepositoryImportReadbackTableResult, ...]
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)
    failure_phase: RepositoryImportFailurePhase | None = None
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class _TableValidationOutcome:
    result: RepositoryImportReadbackTableResult
    expected_summary_entry: dict[str, object]
    actual_summary_entry: dict[str, object]


class RepositoryImportReadbackValidator:
    def __init__(self, *, dolt: DoltCli | None = None) -> None:
        self.dolt = dolt or DoltCli()

    def validate(
        self,
        *,
        repo_dir: Path,
        source_snapshot: SnapshotMaterializationResult,
        plan: RepositoryImportPlan,
    ) -> RepositoryImportReadbackResult:
        if source_snapshot.table_set is None:
            raise ValueError("source_snapshot must include a table_set")

        diagnostics: list[DiagnosticRecord] = []
        table_results: list[RepositoryImportReadbackTableResult] = []

        if plan.validation_policy == RepositoryImportValidationPolicy.DISABLED:
            return RepositoryImportReadbackResult(
                status=RepositoryImportValidationResult.SKIPPED,
                readback_snapshot_digest=None,
                table_results=tuple(),
                diagnostics=tuple(),
            )

        validate_summary = plan.validation_policy in {
            RepositoryImportValidationPolicy.VERIFY_SCHEMA_ROW_COUNT_SUMMARY,
            RepositoryImportValidationPolicy.VERIFY_TABLE_DIGESTS,
        }
        validate_row_counts = plan.validation_policy in {
            RepositoryImportValidationPolicy.VERIFY_SCHEMA_ROW_COUNT_SUMMARY,
            RepositoryImportValidationPolicy.VERIFY_TABLE_DIGESTS,
            RepositoryImportValidationPolicy.VERIFY_ROW_COUNT_ONLY,
        }
        validation_table_names = set(plan.effective_validation_table_names)
        expected_summary_entries: list[dict[str, object]] = []
        actual_summary_entries: list[dict[str, object]] = []

        try:
            for plan_table in plan.tables:
                source_table = source_snapshot.table_set.tables[canonical_identifier(plan_table.table_name)]
                validate_rows = (
                    plan.validation_policy == RepositoryImportValidationPolicy.VERIFY_TABLE_DIGESTS
                    and canonical_identifier(plan_table.table_name) in validation_table_names
                )
                validation_outcome = self._validate_table(
                    repo_dir=repo_dir,
                    source_table=source_table,
                    plan_table=plan_table,
                    validate_summary=validate_summary,
                    validate_row_counts=validate_row_counts,
                    validate_rows=validate_rows,
                )
                table_results.append(validation_outcome.result)
                expected_summary_entries.append(validation_outcome.expected_summary_entry)
                actual_summary_entries.append(validation_outcome.actual_summary_entry)
                diagnostics.extend(validation_outcome.result.diagnostics)
        except CommandError as exc:
            diagnostics.append(
                DiagnosticRecord(
                    code="repository-import.readback.command-failed",
                    message="readback query failed",
                    phase="readback",
                    severity="ERROR",
                    details={
                        "tool": exc.tool,
                        "command": list(exc.command),
                        "returncode": exc.returncode,
                        "output_summary": exc.output_summary,
                    },
                )
            )
            return RepositoryImportReadbackResult(
                status=RepositoryImportValidationResult.FAILED,
                readback_snapshot_digest=None,
                table_results=tuple(table_results),
                diagnostics=tuple(diagnostics),
                failure_phase=RepositoryImportFailurePhase.READBACK_FAILED,
                failure_reason=exc.output_summary,
            )

        expected_summary_digest = _snapshot_summary_digest(
            table_entries=expected_summary_entries,
            table_ruleset_version=source_snapshot.summary.table_ruleset_version,
        )
        actual_summary_digest = _snapshot_summary_digest(
            table_entries=actual_summary_entries,
            table_ruleset_version=source_snapshot.summary.table_ruleset_version,
        )
        if expected_summary_digest != actual_summary_digest:
            diagnostics.append(
                DiagnosticRecord(
                    code="repository-import.readback.schema-row-count-summary-mismatch",
                    message="readback schema-row-count summary does not match the source snapshot summary",
                    phase="validation",
                    severity="ERROR",
                    details={
                        "expected_summary_digest": expected_summary_digest.to_payload(),
                        "actual_summary_digest": actual_summary_digest.to_payload(),
                        "policy": plan.validation_policy.value,
                    },
                )
            )

        all_matched = all(table_result.matched for table_result in table_results)
        if all_matched and expected_summary_digest == actual_summary_digest:
            return RepositoryImportReadbackResult(
                status=RepositoryImportValidationResult.PASSED,
                readback_snapshot_digest=source_snapshot.snapshot.snapshot_digest,
                table_results=tuple(table_results),
                diagnostics=tuple(diagnostics),
            )

        failure_reason = "; ".join(
            diagnostic.message for diagnostic in diagnostics if diagnostic.severity == "ERROR"
        )
        return RepositoryImportReadbackResult(
            status=RepositoryImportValidationResult.FAILED,
            readback_snapshot_digest=None,
            table_results=tuple(table_results),
            diagnostics=tuple(diagnostics),
            failure_phase=RepositoryImportFailurePhase.VALIDATION_MISMATCH,
            failure_reason=failure_reason or "readback validation mismatch",
        )

    def _validate_table(
        self,
        *,
        repo_dir: Path,
        source_table,
        plan_table,
        validate_summary: bool,
        validate_row_counts: bool,
        validate_rows: bool,
    ) -> _TableValidationOutcome:
        expected_columns = tuple(column.name for column in source_table.descriptor.columns)
        target_table_name = plan_table.target_table_name or plan_table.table_name
        expected_row_count = source_table.descriptor.row_count
        actual_row_count = self.dolt.count_rows(repo_dir, target_table_name)
        schema_diagnostics: list[DiagnosticRecord] = []
        row_diagnostics: list[DiagnosticRecord] = []

        expected_schema_digest: DigestRef | None = None
        readback_schema_digest: DigestRef | None = None
        expected_row_digest: DigestRef | None = None
        readback_row_digest: DigestRef | None = None
        readback_columns: tuple[str, ...] = tuple()

        if validate_summary:
            describe_rows = self.dolt.describe_table(repo_dir, target_table_name)
            readback_columns = tuple(_canonical_field_name(row) for row in describe_rows)
            expected_schema_digest = _schema_digest(
                table_name=source_table.descriptor.table_name,
                column_names=expected_columns,
                compare_key_columns=source_table.descriptor.compare_key_columns or expected_columns,
                table_ruleset_version=source_table.descriptor.table_ruleset_version,
                scalar_encoding_version=source_table.descriptor.scalar_encoding_version,
                row_materialization_profile=source_table.descriptor.row_materialization_profile,
            )
            readback_schema_digest = _schema_digest(
                table_name=source_table.descriptor.table_name,
                column_names=readback_columns,
                compare_key_columns=source_table.descriptor.compare_key_columns or expected_columns,
                table_ruleset_version=source_table.descriptor.table_ruleset_version,
                scalar_encoding_version=source_table.descriptor.scalar_encoding_version,
                row_materialization_profile=source_table.descriptor.row_materialization_profile,
            )
            if set(readback_columns) != set(expected_columns):
                schema_diagnostics.append(
                    DiagnosticRecord(
                        code="repository-import.readback.schema-columns-mismatch",
                        message="readback schema column set does not match the source snapshot",
                        phase="validation",
                        severity="ERROR",
                        details={
                            "table_name": source_table.descriptor.table_name,
                            "expected_columns": sorted(expected_columns),
                            "actual_columns": sorted(readback_columns),
                        },
                    )
                )

        if validate_rows:
            source_rows = _normalize_rows(
                tuple(source_table.reader.iter_rows()),
                source_table.descriptor.columns,
            )
            readback_rows = self.dolt.select_rows(
                repo_dir,
                target_table_name,
                order_by_columns=source_table.descriptor.compare_key_columns or expected_columns,
                binary_order_by_columns=_binary_order_by_columns(
                    source_table.descriptor.columns,
                    source_table.descriptor.compare_key_columns or expected_columns,
                ),
            )
            readback_row_tuples = _normalize_rows(
                (
                    tuple(row.get(column_name) for column_name in expected_columns)
                    for row in readback_rows
                ),
                source_table.descriptor.columns,
            )
            expected_row_digest = _rows_digest(
                source_rows,
                column_names=expected_columns,
            )
            readback_row_digest = _rows_digest(
                readback_row_tuples,
                column_names=expected_columns,
            )

        if validate_row_counts and expected_row_count != actual_row_count:
            row_diagnostics.append(
                DiagnosticRecord(
                    code="repository-import.readback.row-count-mismatch",
                    message="readback row count does not match the source snapshot",
                    phase="validation",
                    severity="ERROR",
                    details={
                        "table_name": source_table.descriptor.table_name,
                        "expected_row_count": expected_row_count,
                        "actual_row_count": actual_row_count,
                    },
                )
            )

        if validate_summary:
            actual_summary_entry = _table_summary_entry(
                table_name=source_table.descriptor.table_name,
                target_table_name=target_table_name,
                row_count=actual_row_count,
                schema_digest=readback_schema_digest,
            )
        else:
            actual_summary_entry = _table_summary_entry(
                table_name=source_table.descriptor.table_name,
                target_table_name=target_table_name,
                row_count=actual_row_count,
            )
        expected_summary_entry = _table_summary_entry(
            table_name=source_table.descriptor.table_name,
            target_table_name=target_table_name,
            row_count=expected_row_count,
            schema_digest=expected_schema_digest,
        )

        matched = True
        if validate_summary and expected_schema_digest != readback_schema_digest:
            matched = False
            row_diagnostics.append(
                DiagnosticRecord(
                    code="repository-import.readback.schema-digest-mismatch",
                    message="readback schema digest does not match the source snapshot",
                    phase="validation",
                    severity="ERROR",
                    details={
                        "table_name": source_table.descriptor.table_name,
                        "expected_schema_digest": expected_schema_digest.to_payload(),
                        "actual_schema_digest": readback_schema_digest.to_payload(),
                    },
                )
            )
        if validate_rows and expected_row_digest != readback_row_digest:
            matched = False
            row_diagnostics.append(
                DiagnosticRecord(
                    code="repository-import.readback.row-digest-mismatch",
                    message="readback row digest does not match the source snapshot",
                    phase="validation",
                    severity="ERROR",
                    details={
                        "table_name": source_table.descriptor.table_name,
                        "expected_row_digest": expected_row_digest.to_payload(),
                        "actual_row_digest": readback_row_digest.to_payload(),
                    },
                )
            )
        if row_diagnostics:
            matched = False

        return _TableValidationOutcome(
            result=RepositoryImportReadbackTableResult(
                table_name=source_table.descriptor.table_name,
                target_table_name=target_table_name,
                matched=matched,
                expected_row_count=expected_row_count,
                actual_row_count=actual_row_count,
                expected_schema_digest=expected_schema_digest,
                readback_schema_digest=readback_schema_digest,
                expected_row_digest=expected_row_digest,
                readback_row_digest=readback_row_digest,
                diagnostics=tuple(schema_diagnostics + row_diagnostics),
            ),
            expected_summary_entry=expected_summary_entry,
            actual_summary_entry=actual_summary_entry,
        )


def _canonical_field_name(row: Mapping[str, object]) -> str:
    field_name = row.get("Field")
    if field_name is None:
        raise ValueError("describe output is missing the Field column")
    return canonical_identifier(str(field_name))


def _normalize_rows(
    rows: Sequence[Sequence[object]],
    columns: Sequence[object],
) -> tuple[tuple[object, ...], ...]:
    return normalize_snapshot_rows(rows, columns)


def _normalize_value(value: object, scalar_type: str | None) -> object:
    return normalize_snapshot_scalar_value(value, scalar_type)


def _binary_order_by_columns(
    columns: Sequence[object],
    order_by_columns: Sequence[str],
) -> tuple[str, ...]:
    column_types = {
        canonical_identifier(getattr(column, "name")): scalar_type_family(getattr(column, "scalar_type", None))
        for column in columns
    }
    binary_columns: list[str] = []
    for column_name in order_by_columns:
        canonical_name = canonical_identifier(column_name)
        family = column_types.get(canonical_name)
        if family in {
            "char",
            "varchar",
            "text",
            "tinytext",
            "mediumtext",
            "longtext",
            "enum",
            "set",
        }:
            binary_columns.append(canonical_name)
    return tuple(binary_columns)


def _table_summary_entry(
    *,
    table_name: str,
    target_table_name: str,
    row_count: int,
    schema_digest: DigestRef | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "table_name": canonical_identifier(table_name),
        "target_table_name": canonical_identifier(target_table_name),
        "row_count": row_count,
    }
    if schema_digest is not None:
        payload["schema_digest"] = schema_digest.to_payload()
    return payload


def _snapshot_summary_digest(
    *,
    table_entries: Sequence[dict[str, object]],
    table_ruleset_version: str,
) -> DigestRef:
    return DigestRef.from_payload(
        {
            "table_ruleset_version": table_ruleset_version,
            "tables": sorted(
                table_entries,
                key=lambda entry: (
                    str(entry.get("table_name", "")),
                    str(entry.get("target_table_name", "")),
                ),
            ),
        }
    )


def _schema_digest(
    *,
    table_name: str,
    column_names: Sequence[str],
    compare_key_columns: Sequence[str],
    table_ruleset_version: str,
    scalar_encoding_version: str,
    row_materialization_profile: str,
) -> DigestRef:
    return DigestRef.from_payload(
        {
            "table_name": canonical_identifier(table_name),
            "columns": sorted(canonical_identifier(column_name) for column_name in column_names),
            "compare_key_columns": sorted(
                canonical_identifier(column_name) for column_name in compare_key_columns
            ),
            "table_ruleset_version": table_ruleset_version,
            "scalar_encoding_version": scalar_encoding_version,
            "row_materialization_profile": row_materialization_profile,
        }
    )


def _rows_digest(
    rows: Sequence[Sequence[object]],
    *,
    compare_key_columns: Sequence[str] = (),
    column_names: Sequence[str],
) -> DigestRef:
    del compare_key_columns
    return stable_rows_digest(rows, column_names)
