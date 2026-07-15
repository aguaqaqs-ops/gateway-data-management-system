from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import polars as pl

from ...core.digests import DigestRef, canonical_json_bytes
from ...core.diagnostics import DiagnosticRecord
from ...core.identifiers import canonical_identifier
from ...core.scalar_encoding import (
    normalize_json_scalar_value,
    normalize_parquet_scalar_value,
)
from ..snapshot_materialization.models import SnapshotMaterializationResult, SnapshotTable
from ..snapshot_materialization.hidden_summary import build_hidden_summary_replay_sql
from .dolt_cli import (
    CommandError,
    DoltCli,
    DoltServerSession,
    MysqlCli,
    _LOAD_DATA_SQL_NULL_SENTINEL,
    _LOAD_DATA_NULL_LITERAL_SENTINEL,
)
from .import_artifacts import RepositoryImportArtifact, RepositoryImportTableArtifact
from .providers import (
    RepositoryImportExecutionContext,
    RepositoryImportFailurePhase,
    RepositoryImportImportMode,
    RepositoryImportPlan,
    RepositoryImportPlanTable,
    RepositoryImportProvider,
    RepositoryImportResult,
    RepositoryImportSchemaMode,
    RepositoryImportStatus,
    RepositoryImportValidationResult,
)
from .repository_ref_readback import RepositoryImportRepositoryRefReadbackValidator


_CLI_PROVIDERS = {
    RepositoryImportProvider.SINGLE_TABLE_CLI_IMPORT,
    RepositoryImportProvider.MULTI_TABLE_CLI_IMPORT,
    RepositoryImportProvider.PARQUET_IMPORT,
}
_SERVER_PROVIDERS = {
    RepositoryImportProvider.LOAD_DATA,
    RepositoryImportProvider.DOLT_SERVER_BULK_LOAD,
    RepositoryImportProvider.SERVER_SESSION_BULK_LOAD,
}


@dataclass(frozen=True, slots=True)
class _PreparedTable:
    plan_table: RepositoryImportPlanTable
    source_table: SnapshotTable
    table_artifact: RepositoryImportTableArtifact
    schema_path: Path
    data_path: Path
    file_type: str | None = None


@dataclass(frozen=True, slots=True)
class RepositoryImportProviderRunner:
    work_root: Path
    dolt_bin: str = "dolt"
    mysql_bin: str = "mysql"
    init_name: str = "backend-vnext"
    init_email: str = "backend-vnext@example.invalid"
    dolt: DoltCli = field(init=False, repr=False)
    mysql: MysqlCli = field(init=False, repr=False)

    def __post_init__(self) -> None:
        work_root = self.work_root if isinstance(self.work_root, Path) else Path(self.work_root)
        object.__setattr__(self, "work_root", work_root)
        object.__setattr__(self, "dolt", DoltCli(dolt_bin=self.dolt_bin))
        object.__setattr__(self, "mysql", MysqlCli(mysql_bin=self.mysql_bin))
        self.work_root.mkdir(parents=True, exist_ok=True)

    def open_server_session(
        self,
        plan: RepositoryImportPlan,
        *,
        run_dir: Path | None = None,
    ) -> DoltServerSession:
        if run_dir is None:
            run_dir = self._make_run_dir(plan, suffix="server-session")
        session = DoltServerSession(
            server_root=run_dir / "server-data",
            repository_id=plan.repository_id,
            port=_allocate_port(),
            dolt_bin=self.dolt_bin,
            mysql_bin=self.mysql_bin,
            init_name=self.init_name,
            init_email=self.init_email,
        )
        session.start()
        return session

    def run(
        self,
        plan: RepositoryImportPlan,
        source_snapshot: SnapshotMaterializationResult,
        import_artifact: RepositoryImportArtifact,
        *,
        server_session: DoltServerSession | None = None,
        execution_context: RepositoryImportExecutionContext | None = None,
    ) -> RepositoryImportResult:
        provider = plan.effective_provider
        execution_context = execution_context or RepositoryImportExecutionContext()
        caller_policy = execution_context.caller_policy
        total_start = perf_counter()
        if server_session is not None and execution_context.worktree_context is not None:
            raise ValueError("server_session and worktree_context can not be used together")

        if not caller_policy.executes_import:
            diagnostics = list(source_snapshot.diagnostics)
            diagnostics.append(
                DiagnosticRecord(
                    code="repository-import.caller-policy.skipped",
                    message="repository import skipped for caller policy",
                    phase="prepare",
                    severity="INFO",
                    details={
                        "caller_policy": caller_policy.value,
                        "provider": provider.value,
                    },
                )
            )
            return self._build_result(
                plan=plan,
                provider=provider,
                status=RepositoryImportStatus.SKIPPED,
                validation_result=RepositoryImportValidationResult.SKIPPED,
                commit_hash=None,
                readback_snapshot_digest=None,
                diagnostics=diagnostics,
                failure_phase=None,
                failure_reason=None,
                run_dir=None,
                repo_dir=None,
                import_artifact=import_artifact,
                parse_duration_ms=None,
                staging_duration_ms=None,
                server_start_ms=None,
                import_duration_ms=None,
                commit_duration_ms=None,
                validation_duration_ms=None,
                cleanup_duration_ms=None,
                staging_artifact_bytes=0,
                rows_per_second=None,
                memory_peak=None,
                total_start=total_start,
                imported_table_count=0,
                imported_table_names=tuple(),
            )

        if server_session is not None:
            run_dir = server_session.server_root.parent
            repo_dir = server_session.repo_dir
        elif execution_context.worktree_context is not None:
            run_dir = execution_context.worktree_context.run_dir
            repo_dir = execution_context.worktree_context.repo_dir
            run_dir.mkdir(parents=True, exist_ok=True)
        else:
            run_dir = self._make_run_dir(plan, suffix=provider.value.lower())
            repo_dir = run_dir / "repos" / _safe_path_component(plan.repository_id)

        diagnostics: list[DiagnosticRecord] = list(source_snapshot.diagnostics)
        status = RepositoryImportStatus.FAILED
        validation_result = RepositoryImportValidationResult.SKIPPED
        commit_hash: str | None = None
        readback_snapshot_digest: DigestRef | None = None
        failure_phase: RepositoryImportFailurePhase | None = None
        failure_reason: str | None = None
        parse_duration_ms: int | None = None
        staging_duration_ms: int | None = None
        server_start_ms: int | None = None
        import_duration_ms: int | None = None
        commit_duration_ms: int | None = None
        validation_duration_ms: int | None = None
        cleanup_duration_ms: int | None = None
        staging_artifact_bytes = 0
        rows_per_second: float | None = None
        memory_peak: int | None = None
        owned_server_session = False
        server_session_obj = server_session

        prepare_start = perf_counter()
        try:
            self._validate_plan_and_inputs(
                plan=plan,
                source_snapshot=source_snapshot,
                import_artifact=import_artifact,
            )
        except (TypeError, ValueError) as exc:
            parse_duration_ms = _elapsed_ms(prepare_start)
            diagnostics.append(
                DiagnosticRecord(
                    code="repository-import.prepare.invalid-input",
                    message="repository import inputs are invalid",
                    phase="prepare",
                    severity="ERROR",
                    details={"reason": str(exc)},
                )
            )
            failure_phase = RepositoryImportFailurePhase.PREPARE_FAILED
            failure_reason = str(exc)
            return self._build_result(
                plan=plan,
                provider=provider,
                status=status,
                validation_result=validation_result,
                commit_hash=commit_hash,
                readback_snapshot_digest=readback_snapshot_digest,
                diagnostics=diagnostics,
                failure_phase=failure_phase,
                failure_reason=failure_reason,
                run_dir=run_dir,
                repo_dir=repo_dir,
                import_artifact=import_artifact,
                parse_duration_ms=parse_duration_ms,
                staging_duration_ms=staging_duration_ms,
                server_start_ms=server_start_ms,
                import_duration_ms=import_duration_ms,
                commit_duration_ms=commit_duration_ms,
                validation_duration_ms=validation_duration_ms,
                cleanup_duration_ms=cleanup_duration_ms,
                staging_artifact_bytes=staging_artifact_bytes,
                rows_per_second=rows_per_second,
                memory_peak=memory_peak,
                total_start=total_start,
            )
        parse_duration_ms = _elapsed_ms(prepare_start)

        stage_start = perf_counter()
        try:
            prepared_tables, staged_files = self._prepare_tables(
                plan=plan,
                source_snapshot=source_snapshot,
                import_artifact=import_artifact,
                run_dir=run_dir,
                provider=provider,
            )
        except (CommandError, OSError, ValueError) as exc:
            staging_duration_ms = _elapsed_ms(stage_start)
            diagnostics.append(
                DiagnosticRecord(
                    code="repository-import.staging.failed",
                    message="staging artifacts could not be prepared",
                    phase="staging",
                    severity="ERROR",
                    details={"reason": str(exc)},
                )
            )
            failure_phase = RepositoryImportFailurePhase.STAGING_FAILED
            failure_reason = str(exc)
            return self._build_result(
                plan=plan,
                provider=provider,
                status=status,
                validation_result=validation_result,
                commit_hash=commit_hash,
                readback_snapshot_digest=readback_snapshot_digest,
                diagnostics=diagnostics,
                failure_phase=failure_phase,
                failure_reason=failure_reason,
                run_dir=run_dir,
                repo_dir=repo_dir,
                import_artifact=import_artifact,
                parse_duration_ms=parse_duration_ms,
                staging_duration_ms=staging_duration_ms,
                server_start_ms=server_start_ms,
                import_duration_ms=import_duration_ms,
                commit_duration_ms=commit_duration_ms,
                validation_duration_ms=validation_duration_ms,
                cleanup_duration_ms=cleanup_duration_ms,
                staging_artifact_bytes=staging_artifact_bytes,
                rows_per_second=rows_per_second,
                memory_peak=memory_peak,
                total_start=total_start,
            )
        staging_duration_ms = _elapsed_ms(stage_start)
        staging_artifact_bytes = sum(path.stat().st_size for path in staged_files if path.is_file())

        repo_dir.mkdir(parents=True, exist_ok=True)
        self.dolt.init_repo(repo_dir, name=self.init_name, email=self.init_email)
        if provider not in _SERVER_PROVIDERS:
            try:
                self._prepare_target_branch(repo_dir=repo_dir, plan=plan)
            except CommandError as exc:
                diagnostics.append(
                    DiagnosticRecord(
                        code="repository-import.checkout-target.failed",
                        message="repository import target branch could not be prepared",
                        phase="prepare",
                        severity="ERROR",
                        details={
                            "tool": exc.tool,
                            "command": list(exc.command),
                            "returncode": exc.returncode,
                            "output_summary": exc.output_summary,
                        },
                    )
                )
                failure_phase = RepositoryImportFailurePhase.PREPARE_FAILED
                failure_reason = exc.output_summary
                return self._build_result(
                    plan=plan,
                    provider=provider,
                    status=status,
                    validation_result=validation_result,
                    commit_hash=commit_hash,
                    readback_snapshot_digest=readback_snapshot_digest,
                    diagnostics=diagnostics,
                    run_dir=run_dir,
                    repo_dir=repo_dir,
                    import_artifact=import_artifact,
                    parse_duration_ms=parse_duration_ms,
                    staging_duration_ms=staging_duration_ms,
                    server_start_ms=server_start_ms,
                    import_duration_ms=import_duration_ms,
                    commit_duration_ms=commit_duration_ms,
                    validation_duration_ms=validation_duration_ms,
                    cleanup_duration_ms=cleanup_duration_ms,
                    staging_artifact_bytes=staging_artifact_bytes,
                    rows_per_second=rows_per_second,
                    memory_peak=memory_peak,
                    total_start=total_start,
                )

        import_start = perf_counter()
        try:
            if provider == RepositoryImportProvider.SQL_DUMP_REPLAY:
                self.dolt.execute_sql_file(repo_dir, import_artifact.replay_sql_file.path)
            elif provider in _CLI_PROVIDERS:
                self._run_cli_import(repo_dir=repo_dir, provider=provider, prepared_tables=prepared_tables)
            elif provider in _SERVER_PROVIDERS:
                try:
                    server_session_obj, owned_server_session, server_start_ms = self._ensure_server_session(
                        plan=plan,
                        run_dir=run_dir,
                        server_session=server_session_obj,
                    )
                    repo_dir = server_session_obj.repo_dir
                except CommandError as exc:
                    import_duration_ms = _elapsed_ms(import_start)
                    diagnostics.append(
                        DiagnosticRecord(
                            code="repository-import.server-start.failed",
                            message="server session could not be started",
                            phase="server_start",
                            severity="ERROR",
                            details={
                                "tool": exc.tool,
                                "command": list(exc.command),
                                "returncode": exc.returncode,
                                "output_summary": exc.output_summary,
                            },
                        )
                    )
                    failure_phase = RepositoryImportFailurePhase.SERVER_START_FAILED
                    failure_reason = exc.output_summary
                    return self._build_result(
                        plan=plan,
                        provider=provider,
                        status=status,
                        validation_result=validation_result,
                        commit_hash=commit_hash,
                        readback_snapshot_digest=readback_snapshot_digest,
                        diagnostics=diagnostics,
                        failure_phase=failure_phase,
                        failure_reason=failure_reason,
                        run_dir=run_dir,
                        repo_dir=repo_dir,
                        import_artifact=import_artifact,
                        parse_duration_ms=parse_duration_ms,
                        staging_duration_ms=staging_duration_ms,
                        server_start_ms=server_start_ms,
                        import_duration_ms=import_duration_ms,
                        commit_duration_ms=commit_duration_ms,
                        validation_duration_ms=validation_duration_ms,
                        cleanup_duration_ms=cleanup_duration_ms,
                        staging_artifact_bytes=staging_artifact_bytes,
                        rows_per_second=rows_per_second,
                        memory_peak=memory_peak,
                        total_start=total_start,
                    )
                self._run_server_import(server_session=server_session_obj, prepared_tables=prepared_tables)
            else:
                raise ValueError(f"unsupported provider: {provider.value}")
        except CommandError as exc:
            import_duration_ms = _elapsed_ms(import_start)
            diagnostics.append(
                DiagnosticRecord(
                    code="repository-import.import.failed",
                    message="repository import command failed",
                    phase="import",
                    severity="ERROR",
                    details={
                        "tool": exc.tool,
                        "command": list(exc.command),
                        "returncode": exc.returncode,
                        "output_summary": exc.output_summary,
                    },
                )
            )
            failure_phase = self._failure_phase_for_provider_failure(
                provider=provider,
                default=RepositoryImportFailurePhase.IMPORT_FAILED,
            )
            failure_reason = exc.output_summary
            if owned_server_session and server_session_obj is not None:
                cleanup_duration_ms = self._close_server_session(server_session_obj)
            return self._build_result(
                plan=plan,
                provider=provider,
                status=status,
                validation_result=validation_result,
                commit_hash=commit_hash,
                readback_snapshot_digest=readback_snapshot_digest,
                diagnostics=diagnostics,
                failure_phase=failure_phase,
                failure_reason=failure_reason,
                run_dir=run_dir,
                repo_dir=repo_dir,
                import_artifact=import_artifact,
                parse_duration_ms=parse_duration_ms,
                staging_duration_ms=staging_duration_ms,
                server_start_ms=server_start_ms,
                import_duration_ms=import_duration_ms,
                commit_duration_ms=commit_duration_ms,
                validation_duration_ms=validation_duration_ms,
                cleanup_duration_ms=cleanup_duration_ms,
                staging_artifact_bytes=staging_artifact_bytes,
                rows_per_second=rows_per_second,
                memory_peak=memory_peak,
                total_start=total_start,
            )
        import_duration_ms = _elapsed_ms(import_start)

        hidden_summary_start = perf_counter()
        try:
            self.dolt.run(
                repo_dir,
                ("sql",),
                input_text=build_hidden_summary_replay_sql(source_snapshot.summary),
            )
        except CommandError as exc:
            import_duration_ms += _elapsed_ms(hidden_summary_start)
            diagnostics.append(
                DiagnosticRecord(
                    code="repository-import.hidden-summary.failed",
                    message="hidden snapshot summary could not be written",
                    phase="import",
                    severity="ERROR",
                    details={
                        "tool": exc.tool,
                        "command": list(exc.command),
                        "returncode": exc.returncode,
                        "output_summary": exc.output_summary,
                    },
                )
            )
            failure_phase = RepositoryImportFailurePhase.IMPORT_FAILED
            failure_reason = exc.output_summary
            if owned_server_session and server_session_obj is not None:
                cleanup_duration_ms = self._close_server_session(server_session_obj)
            return self._build_result(
                plan=plan,
                provider=provider,
                status=status,
                validation_result=validation_result,
                commit_hash=commit_hash,
                readback_snapshot_digest=readback_snapshot_digest,
                diagnostics=diagnostics,
                failure_phase=failure_phase,
                failure_reason=failure_reason,
                run_dir=run_dir,
                repo_dir=repo_dir,
                import_artifact=import_artifact,
                parse_duration_ms=parse_duration_ms,
                staging_duration_ms=staging_duration_ms,
                server_start_ms=server_start_ms,
                import_duration_ms=import_duration_ms,
                commit_duration_ms=commit_duration_ms,
                validation_duration_ms=validation_duration_ms,
                cleanup_duration_ms=cleanup_duration_ms,
                staging_artifact_bytes=staging_artifact_bytes,
                rows_per_second=rows_per_second,
                memory_peak=memory_peak,
                total_start=total_start,
            )
        import_duration_ms += _elapsed_ms(hidden_summary_start)

        commit_start = perf_counter()
        try:
            self.dolt.add_all(repo_dir)
            self.dolt.commit(repo_dir, message=plan.commit_message)
            commit_hash = self.dolt.current_head_hash(repo_dir)
            if commit_hash is None:
                raise ValueError("commit hash could not be determined")
        except (CommandError, ValueError) as exc:
            commit_duration_ms = _elapsed_ms(commit_start)
            diagnostics.append(
                DiagnosticRecord(
                    code="repository-import.commit.failed",
                    message="repository commit failed",
                    phase="commit",
                    severity="ERROR",
                    details={"reason": str(exc)},
                )
            )
            failure_phase = RepositoryImportFailurePhase.COMMIT_FAILED
            failure_reason = str(exc)
            if owned_server_session and server_session_obj is not None:
                cleanup_duration_ms = self._close_server_session(server_session_obj)
            return self._build_result(
                plan=plan,
                provider=provider,
                status=status,
                validation_result=validation_result,
                commit_hash=commit_hash,
                readback_snapshot_digest=readback_snapshot_digest,
                diagnostics=diagnostics,
                failure_phase=failure_phase,
                failure_reason=failure_reason,
                run_dir=run_dir,
                repo_dir=repo_dir,
                import_artifact=import_artifact,
                parse_duration_ms=parse_duration_ms,
                staging_duration_ms=staging_duration_ms,
                server_start_ms=server_start_ms,
                import_duration_ms=import_duration_ms,
                commit_duration_ms=commit_duration_ms,
                validation_duration_ms=validation_duration_ms,
                cleanup_duration_ms=cleanup_duration_ms,
                staging_artifact_bytes=staging_artifact_bytes,
                rows_per_second=rows_per_second,
                memory_peak=memory_peak,
                total_start=total_start,
            )
        commit_duration_ms = _elapsed_ms(commit_start)

        validator = RepositoryImportRepositoryRefReadbackValidator(dolt=self.dolt)
        validation_start = perf_counter()
        readback_result = validator.validate(
            repo_dir=repo_dir,
            source_snapshot=source_snapshot,
            plan=plan,
            repository_ref=commit_hash,
        )
        validation_duration_ms = _elapsed_ms(validation_start)
        diagnostics.extend(readback_result.diagnostics)
        readback_snapshot_digest = readback_result.readback_snapshot_digest
        validation_result = readback_result.status
        validation_succeeded = readback_result.status in {
            RepositoryImportValidationResult.PASSED,
            RepositoryImportValidationResult.SKIPPED,
        }
        if validation_succeeded:
            if caller_policy.promotes_target_ref:
                try:
                    self._finalize_target_ref(
                        repo_dir=repo_dir,
                        commit_hash=commit_hash,
                        target_ref=plan.target_branch_ref,
                    )
                except CommandError as exc:
                    diagnostics.append(
                        DiagnosticRecord(
                            code="repository-import.ref.failed",
                            message="repository ref promotion failed",
                            phase="commit",
                            severity="ERROR",
                            details={
                                "tool": exc.tool,
                                "command": list(exc.command),
                                "returncode": exc.returncode,
                                "output_summary": exc.output_summary,
                            },
                        )
                    )
                    failure_phase = RepositoryImportFailurePhase.COMMIT_FAILED
                    failure_reason = exc.output_summary
        else:
            failure_phase = readback_result.failure_phase or RepositoryImportFailurePhase.VALIDATION_MISMATCH
            failure_reason = readback_result.failure_reason

        if validation_succeeded and failure_phase is None:
            status = RepositoryImportStatus.PASSED
        else:
            status = RepositoryImportStatus.FAILED

        if (
            import_duration_ms is not None
            and import_duration_ms > 0
            and source_snapshot.summary.row_count_total is not None
            and source_snapshot.summary.row_count_total > 0
        ):
            rows_per_second = source_snapshot.summary.row_count_total / (import_duration_ms / 1000.0)

        if owned_server_session and server_session_obj is not None:
            cleanup_duration_ms = self._close_server_session(server_session_obj)

        return self._build_result(
            plan=plan,
            provider=provider,
            status=status,
            validation_result=validation_result,
            commit_hash=commit_hash,
            readback_snapshot_digest=readback_snapshot_digest,
            diagnostics=diagnostics,
            failure_phase=failure_phase,
            failure_reason=failure_reason,
            run_dir=run_dir,
            repo_dir=repo_dir,
            import_artifact=import_artifact,
            parse_duration_ms=parse_duration_ms,
            staging_duration_ms=staging_duration_ms,
            server_start_ms=server_start_ms,
            import_duration_ms=import_duration_ms,
            commit_duration_ms=commit_duration_ms,
            validation_duration_ms=validation_duration_ms,
            cleanup_duration_ms=cleanup_duration_ms,
            staging_artifact_bytes=staging_artifact_bytes,
            rows_per_second=rows_per_second,
            memory_peak=memory_peak,
            total_start=total_start,
        )

    def _validate_plan_and_inputs(
        self,
        *,
        plan: RepositoryImportPlan,
        source_snapshot: SnapshotMaterializationResult,
        import_artifact: RepositoryImportArtifact,
    ) -> None:
        if source_snapshot.table_set is None:
            raise ValueError("source_snapshot must include a table_set")
        if source_snapshot.summary.snapshot_digest != source_snapshot.snapshot.snapshot_digest:
            raise ValueError("snapshot digest mismatch between source snapshot and summary")
        if source_snapshot.summary.snapshot_digest != plan.source_snapshot_digest:
            raise ValueError("plan source snapshot digest does not match source snapshot")
        if source_snapshot.summary.table_ruleset_version != plan.table_ruleset_version:
            raise ValueError("plan table ruleset version does not match source snapshot")
        if import_artifact.snapshot_digest != source_snapshot.summary.snapshot_digest:
            raise ValueError("import artifact snapshot digest does not match source snapshot")
        if import_artifact.snapshot_id != source_snapshot.summary.snapshot_id:
            raise ValueError("import artifact snapshot id does not match source snapshot")
        if len(plan.tables) == 0:
            raise ValueError("plan must contain at least one table")

        source_tables = source_snapshot.table_set.tables
        artifact_tables = self._table_artifacts_by_name(import_artifact)
        for plan_table in plan.tables:
            if plan_table.import_mode != RepositoryImportImportMode.REPLACE_TABLE:
                raise ValueError("only REPLACE_TABLE import mode is supported in the first runner phase")
            if plan_table.schema_mode != RepositoryImportSchemaMode.SOURCE_CREATE_SQL:
                raise ValueError("only SOURCE_CREATE_SQL schema mode is supported in the first runner phase")
            if canonical_identifier(plan_table.table_name) != canonical_identifier(
                plan_table.target_table_name or plan_table.table_name
            ):
                raise ValueError("target_table_name must match table_name in the first runner phase")
            if plan_table.table_name not in source_tables:
                raise ValueError(f"plan table {plan_table.table_name} is not present in the source snapshot")
            if plan_table.table_name not in artifact_tables:
                raise ValueError(f"import artifact missing table artifacts for {plan_table.table_name}")
            if plan_table.import_artifact_ref is not None:
                if artifact_tables[plan_table.table_name].manifest_ref != plan_table.import_artifact_ref:
                    raise ValueError(f"import artifact ref mismatch for {plan_table.table_name}")

    def _prepare_tables(
        self,
        *,
        plan: RepositoryImportPlan,
        source_snapshot: SnapshotMaterializationResult,
        import_artifact: RepositoryImportArtifact,
        run_dir: Path,
        provider: RepositoryImportProvider,
    ) -> tuple[tuple[_PreparedTable, ...], tuple[Path, ...]]:
        assert source_snapshot.table_set is not None
        source_tables = source_snapshot.table_set.tables
        artifact_tables = self._table_artifacts_by_name(import_artifact)
        staging_root = run_dir / "artifacts" / provider.value.lower()
        staging_root.mkdir(parents=True, exist_ok=True)

        prepared_tables: list[_PreparedTable] = []
        staged_files: list[Path] = []
        if provider == RepositoryImportProvider.SQL_DUMP_REPLAY:
            staged_files.append(import_artifact.replay_sql_file.path)
            return tuple(prepared_tables), tuple(staged_files)

        for plan_table in plan.tables:
            source_table = source_tables[plan_table.table_name]
            table_artifact = artifact_tables[plan_table.table_name]
            table_dir = staging_root / plan_table.table_name
            table_dir.mkdir(parents=True, exist_ok=True)
            schema_path = table_dir / "schema.sql"
            schema_path.write_text(source_table.raw_create_sql.rstrip("\n") + "\n", encoding="utf-8")
            staged_files.append(schema_path)

            if provider in _CLI_PROVIDERS:
                if provider == RepositoryImportProvider.PARQUET_IMPORT:
                    data_path = table_dir / "rows.parquet"
                    self._write_import_parquet_file(
                        path=data_path,
                        rows=tuple(source_table.reader.iter_rows()),
                        columns=tuple(source_table.descriptor.columns),
                    )
                    file_type = "parquet"
                else:
                    data_path = table_dir / "rows.jsonl"
                    self._write_import_jsonl_file(
                        path=data_path,
                        rows=tuple(source_table.reader.iter_rows()),
                        columns=tuple(source_table.descriptor.columns),
                    )
                    file_type = "jsonl"
                staged_files.append(data_path)
                prepared_tables.append(
                    _PreparedTable(
                        plan_table=plan_table,
                        source_table=source_table,
                        table_artifact=table_artifact,
                        schema_path=schema_path,
                        data_path=data_path,
                        file_type=file_type,
                    )
                )
                continue

            data_path = table_dir / "rows.tsv"
            self._write_server_load_tsv(
                path=data_path,
                rows=tuple(source_table.reader.iter_rows()),
                columns=tuple(_staged_column_name(column) for column in source_table.descriptor.columns),
            )
            staged_files.append(data_path)
            prepared_tables.append(
                _PreparedTable(
                    plan_table=plan_table,
                    source_table=source_table,
                    table_artifact=table_artifact,
                    schema_path=schema_path,
                    data_path=data_path,
                    file_type=None,
                )
            )

        return tuple(prepared_tables), tuple(staged_files)

    def _run_cli_import(
        self,
        *,
        repo_dir: Path,
        provider: RepositoryImportProvider,
        prepared_tables: Sequence[_PreparedTable],
    ) -> None:
        for prepared in prepared_tables:
            if provider == RepositoryImportProvider.PARQUET_IMPORT:
                self.dolt.table_import(
                    repo_dir,
                    table_name=prepared.plan_table.table_name,
                    file_path=prepared.data_path,
                    schema_path=prepared.schema_path,
                    file_type=prepared.file_type or "parquet",
                    replace=True,
                    force=True,
                )
                continue
            self.dolt.table_import(
                repo_dir,
                table_name=prepared.plan_table.table_name,
                file_path=prepared.data_path,
                schema_path=prepared.schema_path,
                file_type=prepared.file_type,
                replace=True,
                force=True,
            )

    def _run_server_import(
        self,
        *,
        server_session: DoltServerSession,
        prepared_tables: Sequence[_PreparedTable],
    ) -> None:
        for prepared in prepared_tables:
            server_session.create_table(prepared.source_table.raw_create_sql)
            server_session.load_data(
                table_name=prepared.plan_table.table_name,
                file_path=prepared.data_path,
                columns=tuple(
                    _staged_column_name(column)
                    for column in prepared.source_table.descriptor.columns
                ),
            )

    def _ensure_server_session(
        self,
        *,
        plan: RepositoryImportPlan,
        run_dir: Path,
        server_session: DoltServerSession | None,
    ) -> tuple[DoltServerSession, bool, int | None]:
        if server_session is None:
            start = perf_counter()
            session = DoltServerSession(
                server_root=run_dir / "server-data",
                repository_id=plan.repository_id,
                port=_allocate_port(),
                dolt_bin=self.dolt_bin,
                mysql_bin=self.mysql_bin,
                init_name=self.init_name,
                init_email=self.init_email,
            )
            session.server_root.mkdir(parents=True, exist_ok=True)
            session.repo_dir.mkdir(parents=True, exist_ok=True)
            session.dolt.init_repo(session.repo_dir, name=session.init_name, email=session.init_email)
            self._prepare_target_branch(repo_dir=session.repo_dir, plan=plan)
            session.start()
            return session, True, _elapsed_ms(start)
        if server_session.is_running:
            return server_session, False, 0
        start = perf_counter()
        server_session.server_root.mkdir(parents=True, exist_ok=True)
        server_session.repo_dir.mkdir(parents=True, exist_ok=True)
        server_session.dolt.init_repo(
            server_session.repo_dir,
            name=server_session.init_name,
            email=server_session.init_email,
        )
        self._prepare_target_branch(repo_dir=server_session.repo_dir, plan=plan)
        server_session.start()
        return server_session, False, _elapsed_ms(start)

    def _close_server_session(self, server_session: DoltServerSession) -> int:
        start = perf_counter()
        server_session.close()
        return _elapsed_ms(start)

    def _finalize_target_ref(
        self,
        *,
        repo_dir: Path,
        commit_hash: str | None,
        target_ref: str,
    ) -> None:
        if commit_hash is None:
            return
        if target_ref.startswith("refs/heads/"):
            self.dolt.branch_force(repo_dir, target_ref.removeprefix("refs/heads/"), commit_hash)
            return
        if target_ref.startswith("refs/tags/"):
            self.dolt.tag_create(repo_dir, target_ref.removeprefix("refs/tags/"), commit_hash)

    def _prepare_target_branch(self, *, repo_dir: Path, plan: RepositoryImportPlan) -> None:
        if plan.target_branch_ref.startswith("refs/heads/"):
            branch_name = plan.target_branch_ref.removeprefix("refs/heads/")
            self.dolt.checkout_reset_branch(repo_dir, branch_name, plan.base_ref_or_commit)
            return
        self.dolt.checkout(repo_dir, plan.base_ref_or_commit, force=True)

    def _build_result(
        self,
        *,
        plan: RepositoryImportPlan,
        provider: RepositoryImportProvider,
        status: RepositoryImportStatus,
        validation_result: RepositoryImportValidationResult,
        commit_hash: str | None,
        readback_snapshot_digest: DigestRef | None,
        diagnostics: Sequence[DiagnosticRecord],
        failure_phase: RepositoryImportFailurePhase | None,
        failure_reason: str | None,
        run_dir: Path | None,
        repo_dir: Path | None,
        import_artifact: RepositoryImportArtifact,
        parse_duration_ms: int | None,
        staging_duration_ms: int | None,
        server_start_ms: int | None,
        import_duration_ms: int | None,
        commit_duration_ms: int | None,
        validation_duration_ms: int | None,
        cleanup_duration_ms: int | None,
        staging_artifact_bytes: int,
        rows_per_second: float | None,
        memory_peak: int | None,
        total_start: float,
        imported_table_count: int | None = None,
        imported_table_names: Sequence[str] | None = None,
    ) -> RepositoryImportResult:
        effective_imported_table_count = (
            len(plan.tables) if imported_table_count is None else imported_table_count
        )
        effective_imported_table_names = (
            plan.table_names if imported_table_names is None else tuple(imported_table_names)
        )
        return RepositoryImportResult(
            repository_id=plan.repository_id,
            target_ref=plan.target_branch_ref,
            commit_hash=commit_hash,
            import_provider=provider,
            status=status,
            validation_result=validation_result,
            imported_table_count=effective_imported_table_count,
            source_snapshot_digest=plan.source_snapshot_digest,
            readback_snapshot_digest=readback_snapshot_digest,
            imported_table_names=effective_imported_table_names,
            server_mode=plan.server_mode,
            provider_contract_version=plan.import_contract_version,
            import_artifact_manifest_digest=import_artifact.manifest_ref.manifest_digest,
            staging_artifact_bytes=staging_artifact_bytes,
            parse_duration_ms=parse_duration_ms,
            staging_duration_ms=staging_duration_ms,
            server_start_ms=server_start_ms,
            import_duration_ms=import_duration_ms,
            commit_duration_ms=commit_duration_ms,
            validation_duration_ms=validation_duration_ms,
            cleanup_duration_ms=cleanup_duration_ms,
            total_duration_ms=_elapsed_ms(total_start),
            rows_per_second=rows_per_second,
            memory_peak=memory_peak,
            dolt_version=self._dolt_version(repo_dir),
            failure_phase=failure_phase,
            failure_reason=failure_reason,
            diagnostics=tuple(diagnostics),
            repository_path=repo_dir,
            run_dir=run_dir,
        )

    def _dolt_version(self, repo_dir: Path | None) -> str | None:
        if repo_dir is None:
            return None
        try:
            return self.dolt.version(repo_dir)
        except CommandError:
            return None

    def _table_artifacts_by_name(
        self,
        import_artifact: RepositoryImportArtifact,
    ) -> dict[str, RepositoryImportTableArtifact]:
        return {table_artifact.table_name: table_artifact for table_artifact in import_artifact.table_artifacts}

    def _write_server_load_tsv(
        self,
        *,
        path: Path,
        rows: Sequence[Sequence[object]],
        columns: Sequence[str],
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            for row in rows:
                encoded = [
                    _escape_load_value(row[index])
                    for index in range(len(columns))
                ]
                handle.write("\t".join(encoded) + "\n")

    def _write_import_jsonl_file(
        self,
        *,
        path: Path,
        rows: Sequence[Sequence[object]],
        columns: Sequence,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                row_payload = {
                    _staged_column_name(column): _normalize_json_value(row[index], column.scalar_type)
                    for index, column in enumerate(columns)
                }
                handle.write(canonical_json_bytes(row_payload).decode("utf-8"))
                handle.write("\n")

    def _write_import_parquet_file(
        self,
        *,
        path: Path,
        rows: Sequence[Sequence[object]],
        columns: Sequence,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if rows:
            row_payloads = [
                {
                    _staged_column_name(column): _normalize_parquet_value(
                        row[index],
                        column.scalar_type,
                    )
                    for index, column in enumerate(columns)
                }
                for row in rows
            ]
            frame = pl.from_dicts(row_payloads, infer_schema_length=None, strict=False).select(
                [_staged_column_name(column) for column in columns]
            )
        else:
            frame = pl.DataFrame(schema={_staged_column_name(column): pl.Null for column in columns})
        frame.write_parquet(path)

    def _failure_phase_for_provider_failure(
        self,
        *,
        provider: RepositoryImportProvider,
        default: RepositoryImportFailurePhase,
    ) -> RepositoryImportFailurePhase:
        del provider
        return default

    def _make_run_dir(self, plan: RepositoryImportPlan, *, suffix: str) -> Path:
        run_id = f"{_safe_path_component(plan.repository_id)}-{suffix}-{uuid4().hex[:8]}"
        run_dir = self.work_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir


def _elapsed_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))


def _allocate_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _safe_path_component(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("path component must be a non-empty string")
    cleaned = "".join(ch if ch.isalnum() or ch in {".", "_", "-"} else "_" for ch in text)
    cleaned = cleaned.strip("._-")
    if not cleaned:
        raise ValueError("path component can not be derived from the provided value")
    return cleaned


def _staged_column_name(column: object) -> str:
    display_name = getattr(column, "display_name", None)
    if isinstance(display_name, str) and display_name:
        return display_name
    name = getattr(column, "name", None)
    if isinstance(name, str) and name:
        return name
    raise ValueError("column must define display_name or name")


def _escape_load_value(value: object) -> str:
    if value is None:
        return _LOAD_DATA_SQL_NULL_SENTINEL
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, str):
        if value.upper() == "NULL":
            return _LOAD_DATA_NULL_LITERAL_SENTINEL
        text = (
            value.replace("\\", r"\\")
            .replace("\t", r"\t")
            .replace("\n", r"\n")
            .replace("\r", r"\r")
        )
        return text
    text = str(value)
    return (
        text.replace("\\", r"\\")
        .replace("\t", r"\t")
        .replace("\n", r"\n")
        .replace("\r", r"\r")
    )


def _normalize_json_value(value: object, scalar_type: str | None) -> object:
    return normalize_json_scalar_value(value, scalar_type)


def _normalize_parquet_value(value: object, scalar_type: str | None) -> object:
    return normalize_parquet_scalar_value(value, scalar_type)
