from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
import json

from ...core.digests import DigestRef, canonical_json_bytes
from ...core.diagnostics import DiagnosticRecord
from ...core.identifiers import canonical_identifier
from ...repository_server import (
    LocalRepositoryTableAccessProvider,
    RepositoryBackend,
    RepositoryRef,
    RepositoryResolvedRef,
    RepositoryServerTableCache,
    RepositoryTableCatalog,
    RepositoryTableCatalogTable,
    RepositoryTableColumn,
    RepositoryTableExportArtifact,
    TupleRepositoryTableReader,
)
from ..table_rules import TableRuleRegistry, default_table_rule_registry
from ..snapshot_materialization import (
    RepositoryRefMaterializationInput,
    materialize_repository_ref,
)
from ..snapshot_materialization.hidden_summary import (
    HIDDEN_SNAPSHOT_SUMMARY_TABLE_COLUMNS,
    HIDDEN_SNAPSHOT_SUMMARY_TABLE_KEY,
    HIDDEN_SNAPSHOT_SUMMARY_TABLE_NAME,
    HIDDEN_SNAPSHOT_SUMMARY_TABLE_SCHEMA_VERSION,
)
from ..snapshot_materialization.models import (
    SnapshotMaterializationStage,
    SnapshotMaterializationResult,
    SnapshotSummary,
)
from .dolt_cli import CommandError, DoltCli
from .providers import (
    RepositoryImportFailurePhase,
    RepositoryImportPlan,
    RepositoryImportValidationPolicy,
    RepositoryImportValidationResult,
)
from .readback import RepositoryImportReadbackResult, RepositoryImportReadbackTableResult
from .readback import (
    _normalize_rows,
    _rows_digest,
    _schema_digest,
    _snapshot_summary_digest,
    _table_summary_entry,
)


LOCAL_REPOSITORY_SERVER_CONTRACT_VERSION = "backend-vnext/repository-server/local-dolt/v1"


@dataclass(frozen=True, slots=True)
class _TableValidationOutcome:
    result: RepositoryImportReadbackTableResult
    expected_summary_entry: dict[str, object]
    actual_summary_entry: dict[str, object]


def _hidden_summary_diagnostics(
    *,
    source_summary: SnapshotSummary,
    hidden_summary: SnapshotSummary,
) -> tuple[DiagnosticRecord, ...]:
    diagnostics: list[DiagnosticRecord] = []
    if hidden_summary.materialization_stage != SnapshotMaterializationStage.FINAL.value:
        diagnostics.append(
            DiagnosticRecord(
                code="repository-import.readback.hidden-summary-stage-mismatch",
                message="hidden snapshot summary must be FINAL",
                phase="validation",
                severity="ERROR",
                details={
                    "actual_stage": hidden_summary.materialization_stage,
                },
            )
        )
    source_payload = source_summary.to_payload()
    hidden_payload = hidden_summary.to_payload()
    if canonical_json_bytes(source_payload) != canonical_json_bytes(hidden_payload):
        diagnostics.append(
            DiagnosticRecord(
                code="repository-import.readback.hidden-summary-payload-mismatch",
                message="hidden snapshot summary payload does not match the source FINAL summary",
                phase="validation",
                severity="ERROR",
                details={
                    "source_snapshot_digest": source_summary.snapshot_digest.to_payload(),
                    "hidden_snapshot_digest": hidden_summary.snapshot_digest.to_payload(),
                    "source_table_count": source_summary.table_count,
                    "hidden_table_count": hidden_summary.table_count,
                    "source_configuration_generated_at": (
                        None
                        if source_summary.configuration_generated_at is None
                        else source_summary.configuration_generated_at.isoformat()
                    ),
                    "hidden_configuration_generated_at": (
                        None
                        if hidden_summary.configuration_generated_at is None
                        else hidden_summary.configuration_generated_at.isoformat()
                    ),
                },
            )
        )
    return tuple(diagnostics)


@dataclass(frozen=True, slots=True)
class RepositoryImportRepositoryRefReadbackValidator:
    dolt: DoltCli | None = None

    def __post_init__(self) -> None:
        if self.dolt is None:
            object.__setattr__(self, "dolt", DoltCli())

    def validate(
        self,
        *,
        repo_dir: Path,
        source_snapshot: SnapshotMaterializationResult,
        plan: RepositoryImportPlan,
        repository_ref: str,
    ) -> RepositoryImportReadbackResult:
        if source_snapshot.table_set is None:
            raise ValueError("source_snapshot must include a table_set")
        if plan.validation_policy == RepositoryImportValidationPolicy.DISABLED:
            return RepositoryImportReadbackResult(
                status=RepositoryImportValidationResult.SKIPPED,
                readback_snapshot_digest=None,
                table_results=tuple(),
                diagnostics=tuple(),
            )
        if plan.validation_policy == RepositoryImportValidationPolicy.VERIFY_HIDDEN_SUMMARY_CATALOG:
            return self._validate_hidden_summary_catalog(
                repo_dir=repo_dir,
                source_snapshot=source_snapshot,
                plan=plan,
            )

        try:
            current_snapshot = self._materialize_current_snapshot(
                repo_dir=repo_dir,
                repository_id=plan.repository_id,
                repository_ref=repository_ref,
                requested_tables=plan.table_names,
            )
        except CommandError as exc:
            diagnostic = DiagnosticRecord(
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
            return RepositoryImportReadbackResult(
                status=RepositoryImportValidationResult.FAILED,
                readback_snapshot_digest=None,
                table_results=tuple(),
                diagnostics=(diagnostic,),
                failure_phase=RepositoryImportFailurePhase.READBACK_FAILED,
                failure_reason=exc.output_summary,
            )
        except ValueError as exc:
            diagnostic = DiagnosticRecord(
                code="repository-import.readback.materialization-mismatch",
                message="repository ref materialization did not match the hidden summary",
                phase="validation",
                severity="ERROR",
                details={"reason": str(exc)},
            )
            return RepositoryImportReadbackResult(
                status=RepositoryImportValidationResult.FAILED,
                readback_snapshot_digest=None,
                table_results=tuple(),
                diagnostics=(diagnostic,),
                failure_phase=RepositoryImportFailurePhase.VALIDATION_MISMATCH,
                failure_reason=str(exc),
            )
        return self.validate_materialized_snapshot(
            source_snapshot=source_snapshot,
            current_snapshot=current_snapshot,
            plan=plan,
        )

    def validate_materialized_snapshot(
        self,
        *,
        source_snapshot: SnapshotMaterializationResult,
        current_snapshot: SnapshotMaterializationResult,
        plan: RepositoryImportPlan,
    ) -> RepositoryImportReadbackResult:
        if source_snapshot.table_set is None:
            raise ValueError("source_snapshot must include a table_set")
        if current_snapshot.table_set is None:
            raise ValueError("current_snapshot must include a table_set")

        diagnostics: list[DiagnosticRecord] = list(current_snapshot.diagnostics)
        table_results: list[RepositoryImportReadbackTableResult] = []
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
                target_table_name = canonical_identifier(plan_table.target_table_name or plan_table.table_name)
                current_table = current_snapshot.table_set.tables.get(target_table_name)
                validation_outcome = self._validate_table(
                    source_table=source_table,
                    current_table=current_table,
                    target_table_name=target_table_name,
                    validate_summary=validate_summary,
                    validate_row_counts=validate_row_counts,
                    validate_rows=(
                        plan.validation_policy == RepositoryImportValidationPolicy.VERIFY_TABLE_DIGESTS
                        and canonical_identifier(plan_table.table_name) in validation_table_names
                    ),
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
                readback_snapshot_digest=source_snapshot.summary.snapshot_digest,
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

    def _validate_hidden_summary_catalog(
        self,
        *,
        repo_dir: Path,
        source_snapshot: SnapshotMaterializationResult,
        plan: RepositoryImportPlan,
    ) -> RepositoryImportReadbackResult:
        diagnostics: list[DiagnosticRecord] = []
        table_results: list[RepositoryImportReadbackTableResult] = []
        try:
            hidden_summary = self._read_hidden_summary(repo_dir)
            diagnostics.extend(
                _hidden_summary_diagnostics(
                    source_summary=source_snapshot.summary,
                    hidden_summary=hidden_summary,
                )
            )
            visible_table_names = set(self.dolt.list_table_names(repo_dir))
            business_table_names = {
                table_name
                for table_name in visible_table_names
                if table_name != HIDDEN_SNAPSHOT_SUMMARY_TABLE_NAME
            }
            plan_table_names = set(plan.table_names)
            missing_tables = sorted(plan_table_names - business_table_names)
            extra_tables = sorted(business_table_names - plan_table_names)
            if missing_tables or extra_tables:
                diagnostics.append(
                    DiagnosticRecord(
                        code="repository-import.readback.catalog-table-set-mismatch",
                        message="repository catalog physical table set does not match the import plan",
                        phase="validation",
                        severity="ERROR",
                        details={
                            "missing_tables": missing_tables,
                            "extra_tables": extra_tables,
                        },
                    )
                )

            existing_plan_table_names = tuple(sorted(plan_table_names & business_table_names))
            columns_by_table = self.dolt.describe_tables(repo_dir, existing_plan_table_names)
            row_counts_by_table = self.dolt.count_rows_batch(repo_dir, existing_plan_table_names)
            for plan_table in plan.tables:
                table_results.append(
                    self._validate_hidden_summary_catalog_table(
                        plan_table=plan_table,
                        columns_by_table=columns_by_table,
                        row_counts_by_table=row_counts_by_table,
                    )
                )
                diagnostics.extend(table_results[-1].diagnostics)
        except CommandError as exc:
            diagnostic = DiagnosticRecord(
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
            return RepositoryImportReadbackResult(
                status=RepositoryImportValidationResult.FAILED,
                readback_snapshot_digest=None,
                table_results=tuple(table_results),
                diagnostics=(diagnostic,),
                failure_phase=RepositoryImportFailurePhase.READBACK_FAILED,
                failure_reason=exc.output_summary,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            diagnostic = DiagnosticRecord(
                code="repository-import.readback.hidden-summary-invalid",
                message="hidden snapshot summary validation failed",
                phase="validation",
                severity="ERROR",
                details={"reason": str(exc)},
            )
            diagnostics.append(diagnostic)

        all_matched = all(table_result.matched for table_result in table_results)
        has_errors = any(diagnostic.severity == "ERROR" for diagnostic in diagnostics)
        if all_matched and not has_errors:
            return RepositoryImportReadbackResult(
                status=RepositoryImportValidationResult.PASSED,
                readback_snapshot_digest=source_snapshot.summary.snapshot_digest,
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
            failure_reason=failure_reason or "hidden summary catalog validation mismatch",
        )

    def _read_hidden_summary(self, repo_dir: Path) -> SnapshotSummary:
        rows = self.dolt.select_rows(repo_dir, HIDDEN_SNAPSHOT_SUMMARY_TABLE_NAME)
        if len(rows) != 1:
            raise ValueError("hidden snapshot summary table must contain exactly one row")
        row = rows[0]
        if tuple(canonical_identifier(column) for column in row) != HIDDEN_SNAPSHOT_SUMMARY_TABLE_COLUMNS:
            actual_columns = tuple(canonical_identifier(column) for column in row)
            if set(actual_columns) != set(HIDDEN_SNAPSHOT_SUMMARY_TABLE_COLUMNS):
                raise ValueError("hidden snapshot summary table schema does not match the expected contract")
        summary_key = row.get("summary_key")
        if summary_key != HIDDEN_SNAPSHOT_SUMMARY_TABLE_KEY:
            raise ValueError("hidden snapshot summary key mismatch")
        schema_version = row.get("schema_version")
        if schema_version != HIDDEN_SNAPSHOT_SUMMARY_TABLE_SCHEMA_VERSION:
            raise ValueError("hidden snapshot summary table schema version mismatch")
        summary_json = row.get("summary_json")
        if not isinstance(summary_json, str) or not summary_json.strip():
            raise ValueError("hidden snapshot summary payload must be a non-empty string")
        summary_digest = row.get("summary_digest")
        expected_digest = DigestRef.from_bytes(summary_json.encode("utf-8")).to_payload()
        if summary_digest != expected_digest:
            raise ValueError("hidden snapshot summary digest mismatch")
        payload = json.loads(summary_json)
        if not isinstance(payload, Mapping):
            raise ValueError("hidden snapshot summary payload must be a JSON object")
        return SnapshotSummary.from_payload(payload)

    def _validate_hidden_summary_catalog_table(
        self,
        *,
        plan_table,
        columns_by_table: Mapping[str, Sequence[Mapping[str, object]]],
        row_counts_by_table: Mapping[str, int],
    ) -> RepositoryImportReadbackTableResult:
        source_descriptor = plan_table.descriptor
        table_name = canonical_identifier(plan_table.table_name)
        target_table_name = canonical_identifier(plan_table.target_table_name or table_name)
        expected_columns = tuple(column.name for column in source_descriptor.columns)
        diagnostics: list[DiagnosticRecord] = []
        actual_row_count = 0
        expected_schema_digest = _schema_digest(
            table_name=table_name,
            column_names=expected_columns,
            compare_key_columns=source_descriptor.compare_key_columns or expected_columns,
            table_ruleset_version=source_descriptor.table_ruleset_version,
            scalar_encoding_version=source_descriptor.scalar_encoding_version,
            row_materialization_profile=source_descriptor.row_materialization_profile,
        )
        readback_schema_digest = None
        try:
            describe_rows = tuple(columns_by_table.get(target_table_name, ()))
            if not describe_rows:
                raise KeyError(target_table_name)
            actual_columns, _primary_key_columns = _describe_table_columns(describe_rows)
            actual_column_names = tuple(column.name for column in actual_columns)
            readback_schema_digest = _schema_digest(
                table_name=table_name,
                column_names=actual_column_names,
                compare_key_columns=source_descriptor.compare_key_columns or expected_columns,
                table_ruleset_version=source_descriptor.table_ruleset_version,
                scalar_encoding_version=source_descriptor.scalar_encoding_version,
                row_materialization_profile=source_descriptor.row_materialization_profile,
            )
            if target_table_name not in row_counts_by_table:
                raise KeyError(target_table_name)
            actual_row_count = row_counts_by_table[target_table_name]
            if set(actual_column_names) != set(expected_columns):
                diagnostics.append(
                    DiagnosticRecord(
                        code="repository-import.readback.schema-columns-mismatch",
                        message="readback schema column set does not match the source snapshot",
                        phase="validation",
                        severity="ERROR",
                        details={
                            "table_name": table_name,
                            "expected_columns": sorted(expected_columns),
                            "actual_columns": sorted(actual_column_names),
                        },
                    )
                )
            if expected_schema_digest != readback_schema_digest:
                diagnostics.append(
                    DiagnosticRecord(
                        code="repository-import.readback.schema-digest-mismatch",
                        message="readback schema digest does not match the source snapshot",
                        phase="validation",
                        severity="ERROR",
                        details={
                            "table_name": table_name,
                            "expected_schema_digest": expected_schema_digest.to_payload(),
                            "actual_schema_digest": (
                                readback_schema_digest.to_payload()
                                if readback_schema_digest is not None
                                else None
                            ),
                        },
                    )
                )
            if source_descriptor.row_count != actual_row_count:
                diagnostics.append(
                    DiagnosticRecord(
                        code="repository-import.readback.row-count-mismatch",
                        message="readback row count does not match the source snapshot",
                        phase="validation",
                        severity="ERROR",
                        details={
                            "table_name": table_name,
                            "expected_row_count": source_descriptor.row_count,
                            "actual_row_count": actual_row_count,
                        },
                    )
                )
        except CommandError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            diagnostics.append(
                DiagnosticRecord(
                    code="repository-import.readback.table-metadata-invalid",
                    message="readback table metadata validation failed",
                    phase="validation",
                    severity="ERROR",
                    details={"table_name": table_name, "reason": str(exc)},
                )
            )

        return RepositoryImportReadbackTableResult(
            table_name=table_name,
            target_table_name=target_table_name,
            matched=not diagnostics,
            expected_row_count=source_descriptor.row_count,
            actual_row_count=actual_row_count,
            expected_schema_digest=expected_schema_digest,
            readback_schema_digest=readback_schema_digest,
            expected_row_digest=None,
            readback_row_digest=None,
            diagnostics=tuple(diagnostics),
        )

    def _materialize_current_snapshot(
        self,
        *,
        repo_dir: Path,
        repository_id: str,
        repository_ref: str,
        requested_tables: Sequence[str],
    ) -> SnapshotMaterializationResult:
        backend = _RepositoryImportRepositoryBackend(
            repo_dir=repo_dir,
            dolt=self.dolt or DoltCli(),
        )
        provider = LocalRepositoryTableAccessProvider(
            backend=backend,
            cache=RepositoryServerTableCache(repo_dir / ".backend_vnext" / "repository-server-cache"),
        )
        return materialize_repository_ref(
            RepositoryRefMaterializationInput(
                repository_ref=RepositoryRef(
                    repository_id=repository_id,
                    repository_ref=repository_ref,
                ),
                repository_table_access_provider=provider,
                requested_tables=tuple(requested_tables),
                materialization_policy="READERS_REQUIRED",
            )
        )

    def _validate_table(
        self,
        *,
        source_table,
        current_table,
        target_table_name: str,
        validate_summary: bool,
        validate_row_counts: bool,
        validate_rows: bool,
    ) -> _TableValidationOutcome:
        expected_columns = tuple(column.name for column in source_table.descriptor.columns)
        expected_row_count = source_table.descriptor.row_count
        expected_schema_digest = None
        readback_schema_digest = None
        expected_row_digest = None
        readback_row_digest = None
        schema_diagnostics: list[DiagnosticRecord] = []
        row_diagnostics: list[DiagnosticRecord] = []
        actual_row_count = 0

        if current_table is None:
            schema_diagnostics.append(
                DiagnosticRecord(
                    code="repository-import.readback.table-missing",
                    message="readback table is missing from the materialized repository ref",
                    phase="validation",
                    severity="ERROR",
                    details={
                        "table_name": source_table.descriptor.table_name,
                        "target_table_name": target_table_name,
                    },
                )
            )
            matched = False
            current_columns = expected_columns
        else:
            current_columns = tuple(column.name for column in current_table.descriptor.columns)
            actual_row_count = current_table.descriptor.row_count

        if validate_summary:
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
                column_names=current_columns,
                compare_key_columns=source_table.descriptor.compare_key_columns or expected_columns,
                table_ruleset_version=source_table.descriptor.table_ruleset_version,
                scalar_encoding_version=source_table.descriptor.scalar_encoding_version,
                row_materialization_profile=source_table.descriptor.row_materialization_profile,
            )
            if set(current_columns) != set(expected_columns):
                schema_diagnostics.append(
                    DiagnosticRecord(
                        code="repository-import.readback.schema-columns-mismatch",
                        message="readback schema column set does not match the source snapshot",
                        phase="validation",
                        severity="ERROR",
                        details={
                            "table_name": source_table.descriptor.table_name,
                            "expected_columns": sorted(expected_columns),
                            "actual_columns": sorted(current_columns),
                        },
                    )
                )
        expected_summary_entry = _table_summary_entry(
            table_name=source_table.descriptor.table_name,
            target_table_name=target_table_name,
            row_count=expected_row_count,
            schema_digest=expected_schema_digest,
        )

        if validate_rows and current_table is not None:
            source_rows = _normalize_rows(
                tuple(source_table.reader.iter_rows()),
                source_table.descriptor.columns,
            )
            current_row_tuples = tuple(tuple(row) for row in current_table.reader.iter_rows())
            current_row_rows = _normalize_rows(
                _reorder_rows_to_columns(
                    current_row_tuples,
                    current_columns,
                    expected_columns,
                ),
                source_table.descriptor.columns,
            )
            expected_row_digest = _rows_digest(
                source_rows,
                column_names=expected_columns,
            )
            readback_row_digest = _rows_digest(
                current_row_rows,
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

        matched = not (schema_diagnostics or row_diagnostics)
        if validate_summary and expected_schema_digest != readback_schema_digest:
            matched = False
            schema_diagnostics.append(
                DiagnosticRecord(
                    code="repository-import.readback.schema-digest-mismatch",
                    message="readback schema digest does not match the source snapshot",
                    phase="validation",
                    severity="ERROR",
                    details={
                        "table_name": source_table.descriptor.table_name,
                        "expected_schema_digest": expected_schema_digest.to_payload() if expected_schema_digest is not None else None,
                        "actual_schema_digest": readback_schema_digest.to_payload() if readback_schema_digest is not None else None,
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
                        "expected_row_digest": expected_row_digest.to_payload() if expected_row_digest is not None else None,
                        "actual_row_digest": readback_row_digest.to_payload() if readback_row_digest is not None else None,
                    },
                )
            )

        actual_summary_entry = _table_summary_entry(
            table_name=source_table.descriptor.table_name,
            target_table_name=target_table_name,
            row_count=actual_row_count,
            schema_digest=readback_schema_digest if validate_summary else None,
        )

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


class _RepositoryImportRepositoryBackend(RepositoryBackend):
    def __init__(
        self,
        *,
        repo_dir: Path,
        dolt: DoltCli,
        table_rule_registry: TableRuleRegistry | None = None,
    ) -> None:
        self.repo_dir = Path(repo_dir)
        self.dolt = dolt
        self.table_rule_registry = table_rule_registry or default_table_rule_registry()

    def resolve_ref(
        self,
        repository_id: str,
        repository_ref: str,
        timeout_policy: object | None = None,
    ) -> RepositoryResolvedRef:
        del timeout_policy
        return RepositoryResolvedRef(
            repository_id=repository_id,
            repository_ref=repository_ref,
            resolved_commit_hash=repository_ref,
            repository_server_contract_version=LOCAL_REPOSITORY_SERVER_CONTRACT_VERSION,
            dolt_version=None,
        )

    def load_catalog(self, resolved_ref: RepositoryResolvedRef) -> RepositoryTableCatalog:
        tables: dict[str, RepositoryTableCatalogTable] = {}
        table_names = list(_show_table_names(self.dolt.show_tables(self.repo_dir)))
        if HIDDEN_SNAPSHOT_SUMMARY_TABLE_NAME not in {
            canonical_identifier(table_name) for table_name in table_names
        }:
            try:
                self.dolt.describe_table(self.repo_dir, HIDDEN_SNAPSHOT_SUMMARY_TABLE_NAME)
            except (CommandError, KeyError):
                pass
            else:
                table_names.append(HIDDEN_SNAPSHOT_SUMMARY_TABLE_NAME)
        for table_name in table_names:
            columns, primary_key_columns = _describe_table_columns(
                self.dolt.describe_table(self.repo_dir, table_name),
            )
            row_count = self.dolt.count_rows(self.repo_dir, table_name)
            key_rule = self.table_rule_registry.key_rule_for_table(
                table_name,
                primary_key_columns=primary_key_columns,
            )
            effective_primary_key_columns = (
                tuple(key_rule.compare_key_columns)
                if key_rule is not None and key_rule.compare_key_columns
                else tuple(primary_key_columns)
            )
            table = RepositoryTableCatalogTable(
                table_name=canonical_identifier(table_name),
                display_table_name=table_name,
                columns=columns,
                primary_key_columns=effective_primary_key_columns,
                row_count=row_count,
                repository_table_version=None,
                table_root_hash=_stable_table_root_hash(
                    resolved_ref.repository_id,
                    resolved_ref.repository_ref,
                    resolved_ref.resolved_commit_hash,
                    canonical_identifier(table_name),
                ),
            )
            tables[table.table_name] = table
        return RepositoryTableCatalog(
            repository_id=resolved_ref.repository_id,
            repository_ref=resolved_ref.repository_ref,
            resolved_commit_hash=resolved_ref.resolved_commit_hash,
            repository_server_contract_version=resolved_ref.repository_server_contract_version,
            tables=tables,
            dolt_version=None,
        )

    def open_table_reader(
        self,
        resolved_ref: RepositoryResolvedRef,
        table_name: str,
        catalog: RepositoryTableCatalog | None = None,
    ) -> TupleRepositoryTableReader:
        effective_catalog = catalog or self.load_catalog(resolved_ref)
        table = effective_catalog.table(table_name)
        rows = self.dolt.select_rows(
            self.repo_dir,
            table.table_name,
            order_by_columns=table.primary_key_columns or table.column_order,
            binary_order_by_columns=table.primary_key_columns or table.column_order,
        )
        normalized_rows = tuple(
            tuple(row.get(column_name) for column_name in table.column_order)
            for row in rows
        )
        return TupleRepositoryTableReader(catalog_table=table, rows=normalized_rows)

    def export_table_artifact(
        self,
        resolved_ref: RepositoryResolvedRef,
        table_name: str,
        export_format: str,
        catalog: RepositoryTableCatalog | None = None,
    ) -> RepositoryTableExportArtifact:
        effective_catalog = catalog or self.load_catalog(resolved_ref)
        table = effective_catalog.table(table_name)
        rows = self.dolt.select_rows(
            self.repo_dir,
            table.table_name,
            order_by_columns=table.primary_key_columns or table.column_order,
            binary_order_by_columns=table.primary_key_columns or table.column_order,
        )
        payload = {
            "repository_id": resolved_ref.repository_id,
            "repository_ref": resolved_ref.repository_ref,
            "resolved_commit_hash": resolved_ref.resolved_commit_hash,
            "table_name": table.table_name,
            "export_format": export_format.strip().upper(),
            "table": table.to_payload(),
            "rows": rows,
        }
        artifact_bytes = canonical_json_bytes(payload)
        artifact_path = self.repo_dir / ".backend_vnext" / "repository-server-cache" / "export" / f"{table.table_name}.{export_format.strip().lower()}.json"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_bytes(artifact_bytes)
        return RepositoryTableExportArtifact(
            repository_id=resolved_ref.repository_id,
            repository_ref=resolved_ref.repository_ref,
            resolved_commit_hash=resolved_ref.resolved_commit_hash,
            table_name=table.table_name,
            export_format=export_format,
            path=artifact_path,
            content_digest=DigestRef.from_bytes(artifact_bytes),
            content_size_bytes=len(artifact_bytes),
            table_root_hash=table.table_root_hash,
        )

    def close_session(self, resolved_ref: RepositoryResolvedRef) -> None:
        del resolved_ref


def _stable_table_root_hash(
    repository_id: str,
    repository_ref: str,
    resolved_commit_hash: str,
    table_name: str,
) -> str:
    return DigestRef.from_payload(
        {
            "parts": (
                repository_id,
                repository_ref,
                resolved_commit_hash,
                table_name,
            )
        }
    ).to_payload()


def _show_table_names(rows: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    table_names: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise TypeError("show tables output must contain mappings")
        table_name = row.get("Table")
        if table_name is None and row:
            table_name = next(iter(row.values()))
        if table_name is None:
            raise ValueError("show tables output row is missing a table name")
        table_names.append(canonical_identifier(str(table_name)))
    return tuple(table_names)


def _describe_table_columns(
    rows: Sequence[Mapping[str, object]],
) -> tuple[tuple[RepositoryTableColumn, ...], tuple[str, ...]]:
    columns: list[RepositoryTableColumn] = []
    primary_key_columns: list[str] = []
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise TypeError("describe table output must contain mappings")
        field_name = row.get("Field")
        if field_name is None:
            raise ValueError("describe table output is missing Field")
        column_name = canonical_identifier(str(field_name))
        column = RepositoryTableColumn(
            name=column_name,
            ordinal=ordinal,
            display_name=str(field_name),
            scalar_type=_optional_text(row.get("Type")),
            nullable=_nullable_from_describe(row.get("Null")),
            raw_type=_optional_text(row.get("Type")),
        )
        columns.append(column)
        key_value = str(row.get("Key") or "")
        if "PRI" in key_value.upper():
            primary_key_columns.append(column_name)
    return tuple(columns), tuple(primary_key_columns)


def _optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _nullable_from_describe(value: object | None) -> bool | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if text == "YES":
        return True
    if text == "NO":
        return False
    return None


def _reorder_rows_to_columns(
    rows: Sequence[Sequence[object]],
    row_columns: Sequence[str],
    target_columns: Sequence[str],
) -> tuple[tuple[object, ...], ...]:
    normalized_rows: list[tuple[object, ...]] = []
    row_column_names = tuple(canonical_identifier(column_name) for column_name in row_columns)
    target_column_names = tuple(canonical_identifier(column_name) for column_name in target_columns)
    for row in rows:
        row_map = {
            row_column_names[index]: row[index]
            for index in range(min(len(row_column_names), len(row)))
        }
        normalized_rows.append(tuple(row_map.get(column_name) for column_name in target_column_names))
    return tuple(normalized_rows)
