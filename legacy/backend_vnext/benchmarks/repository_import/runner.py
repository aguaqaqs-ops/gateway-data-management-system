from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from platform import platform, python_version
import os
from shutil import which
import subprocess
from time import perf_counter
from uuid import uuid4

from ...capabilities.repository_import import (
    RepositoryImportArtifactBuilder,
    RepositoryImportArtifactLayout,
    RepositoryImportCallerPolicy,
    RepositoryImportExecutionContext,
    RepositoryImportPlan,
    RepositoryImportProvider,
    RepositoryImportProviderRunner,
    RepositoryImportResult,
    RepositoryImportServerMode,
    RepositoryImportValidationPolicy,
    REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY,
    build_physical_repository_import_plan_tables,
)
from ...capabilities.snapshot_materialization.models import (
    SnapshotMaterializationResult,
)
from ...core import BenchmarkRunResult, DiagnosticRecord, canonical_json_bytes
from ...core.identifiers import canonical_identifier
from .._paths import resolve_benchmark_path
from .datasets import (
    RepositoryImportBenchmarkDatasetManifest,
    RepositoryImportBenchmarkDatasetResolution,
    RepositoryImportDatasetManifestBuilder,
    RepositoryImportDatasetResolver,
    RepositoryImportBenchmarkDatasetSpec,
)


DEFAULT_BENCHMARK_PROVIDERS: tuple[RepositoryImportProvider, ...] = (
    RepositoryImportProvider.SQL_DUMP_REPLAY,
    RepositoryImportProvider.SINGLE_TABLE_CLI_IMPORT,
    RepositoryImportProvider.MULTI_TABLE_CLI_IMPORT,
    RepositoryImportProvider.LOAD_DATA,
    RepositoryImportProvider.PARQUET_IMPORT,
    RepositoryImportProvider.DOLT_SERVER_BULK_LOAD,
    RepositoryImportProvider.SERVER_SESSION_BULK_LOAD,
)


class RepositoryImportBenchmarkProfile(str, Enum):
    IMPORT_HEALTH_SMOKE = "IMPORT_HEALTH_SMOKE"
    END_TO_END_COLD = "END_TO_END_COLD"
    IMPORT_ONLY_WARM_ARTIFACT = "IMPORT_ONLY_WARM_ARTIFACT"
    SERVER_SESSION = "SERVER_SESSION"


@dataclass(frozen=True, slots=True)
class RepositoryImportBenchmarkExecutionPlan:
    execution_context: RepositoryImportExecutionContext
    shared_server_session: bool = False


@dataclass(frozen=True, slots=True)
class RepositoryImportBenchmarkMachineProfile:
    machine_profile_id: str
    os_name: str
    cpu_count: int | None = None
    cpu_model: str | None = None
    memory_total_mb: int | None = None
    disk_type: str | None = None
    filesystem: str | None = None
    dolt_version: str | None = None
    python_version: str | None = None
    mysql_client_version: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.machine_profile_id, str) or not self.machine_profile_id.strip():
            raise ValueError("machine_profile_id must be a non-empty string")
        if not isinstance(self.os_name, str) or not self.os_name.strip():
            raise ValueError("os_name must be a non-empty string")
        for field_name in ("cpu_count", "memory_total_mb"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise ValueError(f"{field_name} must be a non-negative integer or None")
        for field_name in ("cpu_model", "disk_type", "filesystem", "dolt_version", "python_version", "mysql_client_version"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{field_name} must be a non-empty string or None")

    def to_payload(self) -> dict[str, object]:
        return {
            "machine_profile_id": self.machine_profile_id,
            "os": self.os_name,
            "cpu_count": self.cpu_count,
            "cpu_model": self.cpu_model,
            "memory_total_mb": self.memory_total_mb,
            "disk_type": self.disk_type,
            "filesystem": self.filesystem,
            "dolt_version": self.dolt_version,
            "python_version": self.python_version,
            "mysql_client_version": self.mysql_client_version,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "RepositoryImportBenchmarkMachineProfile":
        return cls(
            machine_profile_id=str(payload["machine_profile_id"]),
            os_name=str(payload["os"]),
            cpu_count=_optional_int(payload.get("cpu_count")),
            cpu_model=_optional_str(payload.get("cpu_model")),
            memory_total_mb=_optional_int(payload.get("memory_total_mb")),
            disk_type=_optional_str(payload.get("disk_type")),
            filesystem=_optional_str(payload.get("filesystem")),
            dolt_version=_optional_str(payload.get("dolt_version")),
            python_version=_optional_str(payload.get("python_version")),
            mysql_client_version=_optional_str(payload.get("mysql_client_version")),
        )


@dataclass(frozen=True, slots=True)
class RepositoryImportBenchmarkMatrixEntry:
    dataset_id: str
    dataset_kind: str
    profile: RepositoryImportBenchmarkProfile | str
    provider: RepositoryImportProvider | str
    server_mode: RepositoryImportServerMode | str
    requested_tables: tuple[str, ...] = field(default_factory=tuple)
    validation_policy: RepositoryImportValidationPolicy | str = (
        RepositoryImportValidationPolicy.VERIFY_SCHEMA_ROW_COUNT_SUMMARY
    )
    validation_table_names: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for field_name in ("dataset_id", "dataset_kind"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        object.__setattr__(self, "profile", RepositoryImportBenchmarkProfile(self.profile))
        object.__setattr__(self, "provider", RepositoryImportProvider(self.provider))
        object.__setattr__(self, "server_mode", RepositoryImportServerMode(self.server_mode))
        object.__setattr__(self, "validation_policy", RepositoryImportValidationPolicy(self.validation_policy))
        normalized_tables: list[str] = []
        seen: set[str] = set()
        for table_name in self.requested_tables:
            normalized = str(table_name).strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            normalized_tables.append(normalized)
        object.__setattr__(self, "requested_tables", tuple(normalized_tables))
        normalized_validation_tables: list[str] = []
        seen_validation_tables: set[str] = set()
        for table_name in self.validation_table_names:
            normalized = canonical_identifier(str(table_name))
            if not normalized or normalized in seen_validation_tables:
                continue
            seen_validation_tables.add(normalized)
            normalized_validation_tables.append(normalized)
        object.__setattr__(self, "validation_table_names", tuple(normalized_validation_tables))

    def to_payload(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_kind": self.dataset_kind,
            "profile": self.profile.value,
            "provider": self.provider.value,
            "server_mode": self.server_mode.value,
            "requested_tables": list(self.requested_tables),
            "validation_policy": self.validation_policy.value,
            "validation_table_names": list(self.validation_table_names),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "RepositoryImportBenchmarkMatrixEntry":
        requested_tables = payload.get("requested_tables", [])
        if requested_tables is None:
            requested_tables = []
        if not isinstance(requested_tables, list):
            raise TypeError("requested_tables must be a list")
        return cls(
            dataset_id=str(payload["dataset_id"]),
            dataset_kind=str(payload["dataset_kind"]),
            profile=str(payload["profile"]),
            provider=str(payload["provider"]),
            server_mode=str(payload["server_mode"]),
            requested_tables=tuple(str(item) for item in requested_tables),
            validation_policy=str(
                payload.get(
                    "validation_policy",
                    RepositoryImportValidationPolicy.VERIFY_SCHEMA_ROW_COUNT_SUMMARY.value,
                )
            ),
            validation_table_names=tuple(
                str(item)
                for item in (payload.get("validation_table_names") or [])
                if str(item).strip()
            ),
        )


@dataclass(frozen=True, slots=True)
class RepositoryImportBenchmarkMatrix:
    entries: tuple[RepositoryImportBenchmarkMatrixEntry, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        normalized: list[RepositoryImportBenchmarkMatrixEntry] = []
        for entry in self.entries:
            if not isinstance(entry, RepositoryImportBenchmarkMatrixEntry):
                raise TypeError("entries must contain RepositoryImportBenchmarkMatrixEntry values")
            normalized.append(entry)
        object.__setattr__(self, "entries", tuple(normalized))

    def to_payload(self) -> dict[str, object]:
        return {"entries": [entry.to_payload() for entry in self.entries]}

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "RepositoryImportBenchmarkMatrix":
        entries_payload = payload.get("entries", [])
        if entries_payload is None:
            entries_payload = []
        if not isinstance(entries_payload, list):
            raise TypeError("matrix entries payload must be a list")
        return cls(entries=tuple(RepositoryImportBenchmarkMatrixEntry.from_payload(item) for item in entries_payload))


@dataclass(frozen=True, slots=True)
class RepositoryImportBenchmarkSummary:
    run_id: str
    created_at: str
    machine_profile: RepositoryImportBenchmarkMachineProfile
    datasets: tuple[RepositoryImportBenchmarkDatasetManifest, ...]
    profiles: tuple[str, ...]
    providers: tuple[str, ...]
    matrix: RepositoryImportBenchmarkMatrix
    results: tuple[BenchmarkRunResult, ...]
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("run_id must be a non-empty string")
        if not isinstance(self.created_at, str) or not self.created_at.strip():
            raise ValueError("created_at must be a non-empty string")
        if not isinstance(self.machine_profile, RepositoryImportBenchmarkMachineProfile):
            raise TypeError("machine_profile must be a RepositoryImportBenchmarkMachineProfile")
        dataset_manifests: list[RepositoryImportBenchmarkDatasetManifest] = []
        for manifest in self.datasets:
            if not isinstance(manifest, RepositoryImportBenchmarkDatasetManifest):
                raise TypeError("datasets must contain RepositoryImportBenchmarkDatasetManifest values")
            dataset_manifests.append(manifest)
        object.__setattr__(self, "datasets", tuple(dataset_manifests))
        object.__setattr__(self, "profiles", tuple(str(profile) for profile in self.profiles))
        object.__setattr__(self, "providers", tuple(str(provider) for provider in self.providers))
        if not isinstance(self.matrix, RepositoryImportBenchmarkMatrix):
            raise TypeError("matrix must be a RepositoryImportBenchmarkMatrix")
        result_items: list[BenchmarkRunResult] = []
        for result in self.results:
            if not isinstance(result, BenchmarkRunResult):
                raise TypeError("results must contain BenchmarkRunResult values")
            result_items.append(result)
        object.__setattr__(self, "results", tuple(result_items))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics))
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")

    def to_payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "machine_profile": self.machine_profile.to_payload(),
            "datasets": [dataset.to_payload() for dataset in self.datasets],
            "profiles": list(self.profiles),
            "providers": list(self.providers),
            "matrix": self.matrix.to_payload(),
            "results": [result.to_payload() for result in self.results],
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> "RepositoryImportBenchmarkSummary":
        diagnostics_payload = payload.get("diagnostics", [])
        if diagnostics_payload is None:
            diagnostics_payload = []
        if not isinstance(diagnostics_payload, list):
            raise TypeError("summary diagnostics payload must be a list")
        datasets_payload = payload.get("datasets", [])
        if datasets_payload is None:
            datasets_payload = []
        if not isinstance(datasets_payload, list):
            raise TypeError("summary datasets payload must be a list")
        profiles_payload = payload.get("profiles", [])
        providers_payload = payload.get("providers", [])
        if profiles_payload is None:
            profiles_payload = []
        if providers_payload is None:
            providers_payload = []
        if not isinstance(profiles_payload, list) or not isinstance(providers_payload, list):
            raise TypeError("summary profiles/providers payload must be a list")
        results_payload = payload.get("results", [])
        if results_payload is None:
            results_payload = []
        if not isinstance(results_payload, list):
            raise TypeError("summary results payload must be a list")
        return cls(
            run_id=str(payload["run_id"]),
            created_at=str(payload["created_at"]),
            machine_profile=RepositoryImportBenchmarkMachineProfile.from_payload(
                _mapping(payload["machine_profile"])
            ),
            datasets=tuple(
                RepositoryImportBenchmarkDatasetManifest.from_payload(_mapping(item))
                for item in datasets_payload
            ),
            profiles=tuple(str(item) for item in profiles_payload),
            providers=tuple(str(item) for item in providers_payload),
            matrix=RepositoryImportBenchmarkMatrix.from_payload(_mapping(payload["matrix"])),
            results=tuple(BenchmarkRunResult.from_payload(_mapping(item)) for item in results_payload),
            diagnostics=tuple(DiagnosticRecord.from_payload(item) for item in diagnostics_payload),
        )


class RepositoryImportBenchmarkRunner:
    def __init__(
        self,
        *,
        dataset_root: Path,
        run_root: Path,
        result_out: Path | None = None,
        dolt_bin: str = "dolt",
        mysql_bin: str = "mysql",
        machine_profile: RepositoryImportBenchmarkMachineProfile | None = None,
    ) -> None:
        self.dataset_root = resolve_benchmark_path(dataset_root)
        self.run_root = resolve_benchmark_path(run_root)
        self.result_out = result_out if result_out is not None else self.run_root / "report.md"
        self.dolt_bin = dolt_bin
        self.mysql_bin = mysql_bin
        self.machine_profile = machine_profile or detect_local_machine_profile(
            machine_profile_id=_default_machine_profile_id(),
            dolt_bin=self.dolt_bin,
            mysql_bin=self.mysql_bin,
        )
        self.dataset_resolver = RepositoryImportDatasetResolver(self.dataset_root)
        self.dataset_manifest_builder = RepositoryImportDatasetManifestBuilder()
        self.provider_runner = RepositoryImportProviderRunner(
            self.run_root / "repos",
            dolt_bin=self.dolt_bin,
            mysql_bin=self.mysql_bin,
        )
        self.artifact_root = self.run_root / "artifacts"
        self.dataset_output_root = self.run_root / "datasets"
        self.logs_root = self.run_root / "logs"
        self.summary_path = self.run_root / "summary.json"
        self.result_out.parent.mkdir(parents=True, exist_ok=True)
        self.run_root.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        *,
        profiles: Sequence[RepositoryImportBenchmarkProfile | str] = (
            RepositoryImportBenchmarkProfile.IMPORT_HEALTH_SMOKE,
        ),
        providers: Sequence[RepositoryImportProvider | str] | None = None,
        datasets: Sequence[str] | None = None,
        validation_policy: RepositoryImportValidationPolicy | str = (
            RepositoryImportValidationPolicy.VERIFY_SCHEMA_ROW_COUNT_SUMMARY
        ),
        validation_table_names: Sequence[str] | Mapping[str, Sequence[str]] | None = None,
    ) -> RepositoryImportBenchmarkSummary:
        self.run_root.mkdir(parents=True, exist_ok=True)
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        self.dataset_output_root.mkdir(parents=True, exist_ok=True)
        self.logs_root.mkdir(parents=True, exist_ok=True)

        selected_profiles = tuple(_coerce_profile(profile) for profile in profiles)
        selected_providers = tuple(
            _coerce_provider(provider) for provider in (providers or DEFAULT_BENCHMARK_PROVIDERS)
        )
        effective_validation_policy = RepositoryImportValidationPolicy(validation_policy)
        dataset_specs = self.dataset_resolver.resolve(datasets)

        dataset_resolutions: dict[str, RepositoryImportDatasetResolution] = {}
        dataset_manifests: list[RepositoryImportBenchmarkDatasetManifest] = []
        results: list[BenchmarkRunResult] = []
        matrix_entries: list[RepositoryImportBenchmarkMatrixEntry] = []
        diagnostics: list[DiagnosticRecord] = []

        for dataset_spec in dataset_specs:
            resolution = self.dataset_manifest_builder.build(dataset_spec)
            dataset_resolutions[dataset_spec.dataset_id] = resolution
            dataset_manifests.append(resolution.manifest)
            self._write_dataset_resolution(resolution)

        for dataset_spec in dataset_specs:
            resolution = dataset_resolutions[dataset_spec.dataset_id]
            artifact_builder = RepositoryImportArtifactBuilder(
                self.artifact_root / dataset_spec.dataset_id,
                export_formats=(REPOSITORY_IMPORT_ROW_FORMAT_SQL_REPLAY,),
                artifact_layout=RepositoryImportArtifactLayout.REPLAY_ONLY_MINIMAL,
            )
            import_artifact = artifact_builder.build(
                resolution.source_snapshot,
                requested_tables=dataset_spec.requested_tables or None,
            )
            self._write_log(
                f"dataset {dataset_spec.dataset_id}: artifact {import_artifact.manifest_ref.manifest_digest}"
            )

            for profile in selected_profiles:
                for provider in selected_providers:
                    server_mode = _server_mode_for(provider)
                    effective_validation_table_names = _validation_table_names_for_dataset(
                        dataset_spec=dataset_spec,
                        validation_table_names=validation_table_names,
                    )
                    entry = RepositoryImportBenchmarkMatrixEntry(
                        dataset_id=dataset_spec.dataset_id,
                        dataset_kind=dataset_spec.dataset_kind,
                        profile=profile,
                        provider=provider,
                        server_mode=server_mode,
                        requested_tables=dataset_spec.requested_tables,
                        validation_policy=effective_validation_policy,
                        validation_table_names=effective_validation_table_names,
                    )
                    matrix_entries.append(entry)

                    execution_plan = _execution_plan_for_profile(profile)
                    execution_context = execution_plan.execution_context
                    plan = self._build_plan(
                        dataset_spec=dataset_spec,
                        resolution=resolution,
                        provider=provider,
                        server_mode=server_mode,
                        validation_policy=effective_validation_policy,
                        validation_table_names=effective_validation_table_names,
                    )
                    run_result = self._run_provider_entry(
                        plan=plan,
                        source_snapshot=resolution.source_snapshot,
                        import_artifact=import_artifact,
                        provider=provider,
                        execution_plan=execution_plan,
                    )
                    benchmark_result = self._to_benchmark_result(
                        entry=entry,
                        resolution=resolution,
                        import_artifact=import_artifact,
                        run_result=run_result,
                    )
                    results.append(benchmark_result)
                    self._write_log(
                        "result "
                        f"{dataset_spec.dataset_id}/{profile.value}/{provider.value} "
                        f"caller_policy={execution_context.caller_policy.value} "
                        f"status={benchmark_result.status} validation={benchmark_result.validation_result}"
                    )

        summary = RepositoryImportBenchmarkSummary(
            run_id=_build_run_id(),
            created_at=_utc_now_iso(),
            machine_profile=self.machine_profile,
            datasets=tuple(dataset_manifests),
            profiles=tuple(profile.value for profile in selected_profiles),
            providers=tuple(provider.value for provider in selected_providers),
            matrix=RepositoryImportBenchmarkMatrix(entries=tuple(matrix_entries)),
            results=tuple(results),
            diagnostics=tuple(diagnostics),
        )

        from .report import MarkdownReportWriter, SummaryJsonWriter

        SummaryJsonWriter().write(self.summary_path, summary)
        MarkdownReportWriter().write_from_summary_path(self.summary_path, self.result_out)
        return summary

    def _build_plan(
        self,
        *,
        dataset_spec: RepositoryImportBenchmarkDatasetSpec,
        resolution: RepositoryImportBenchmarkDatasetResolution,
        provider: RepositoryImportProvider,
        server_mode: RepositoryImportServerMode,
        validation_policy: RepositoryImportValidationPolicy,
        validation_table_names: Sequence[str],
    ) -> RepositoryImportPlan:
        assert resolution.source_snapshot.table_set is not None
        tables = build_physical_repository_import_plan_tables(resolution.source_snapshot)
        physical_table_names = {table.table_name for table in tables}
        effective_validation_table_names = tuple(
            table_name for table_name in validation_table_names if table_name in physical_table_names
        )
        return RepositoryImportPlan(
            repository_id=dataset_spec.dataset_id,
            base_ref_or_commit="main",
            target_branch_ref=f"refs/heads/{dataset_spec.dataset_id}",
            source_snapshot_id=resolution.source_snapshot.summary.snapshot_id,
            source_snapshot_digest=resolution.source_snapshot.summary.snapshot_digest,
            table_ruleset_version=resolution.source_snapshot.summary.table_ruleset_version,
            provider_preference=provider,
            server_mode=server_mode,
            tables=tables,
            validation_policy=validation_policy,
            validation_table_names=effective_validation_table_names,
        )

    def _to_benchmark_result(
        self,
        *,
        entry: RepositoryImportBenchmarkMatrixEntry,
        resolution: RepositoryImportBenchmarkDatasetResolution,
        import_artifact,
        run_result: RepositoryImportResult,
    ) -> BenchmarkRunResult:
        source_snapshot = resolution.source_snapshot
        source_sql_bytes = len(resolution.source_sql_text.encode("utf-8"))
        row_counts = [
            table.descriptor.row_count
            for table in source_snapshot.table_set.tables.values()
        ] if source_snapshot.table_set is not None else []
        largest_table_row_count = max(row_counts) if row_counts else 0
        return BenchmarkRunResult(
            dataset_id=resolution.spec.dataset_id,
            dataset_kind=resolution.spec.dataset_kind,
            profile=entry.profile.value,
            provider=entry.provider.value,
            status=run_result.status.value,
            validation_result=run_result.validation_result.value,
            server_mode=entry.server_mode.value,
            machine_profile_id=self.machine_profile.machine_profile_id,
            source_sql_digest=resolution.manifest.source_sql_digest,
            source_sql_bytes=source_sql_bytes,
            table_count=resolution.manifest.table_count,
            row_count_total=resolution.manifest.row_count_total,
            largest_table_row_count=largest_table_row_count,
            staging_artifact_bytes=run_result.staging_artifact_bytes,
            parse_duration_ms=run_result.parse_duration_ms,
            staging_duration_ms=run_result.staging_duration_ms,
            server_start_ms=run_result.server_start_ms,
            import_duration_ms=run_result.import_duration_ms,
            commit_duration_ms=run_result.commit_duration_ms,
            validation_duration_ms=run_result.validation_duration_ms,
            cleanup_duration_ms=run_result.cleanup_duration_ms,
            total_duration_ms=run_result.total_duration_ms,
            rows_per_second=run_result.rows_per_second,
            memory_peak=run_result.memory_peak,
            dolt_version=run_result.dolt_version,
            provider_contract_version=run_result.provider_contract_version,
            import_artifact_manifest_digest=import_artifact.manifest_ref.manifest_digest,
            source_snapshot_digest=resolution.source_snapshot.summary.snapshot_digest,
            readback_snapshot_digest=run_result.readback_snapshot_digest,
            commit_hash=run_result.commit_hash,
            failure_phase=(
                None if run_result.failure_phase is None else run_result.failure_phase.value
            ),
            failure_reason=run_result.failure_reason,
            diagnostics=run_result.diagnostics,
        )

    def _run_provider_entry(
        self,
        *,
        plan: RepositoryImportPlan,
        source_snapshot: SnapshotMaterializationResult,
        import_artifact,
        provider: RepositoryImportProvider,
        execution_plan: RepositoryImportBenchmarkExecutionPlan,
    ) -> RepositoryImportResult:
        if execution_plan.shared_server_session and provider == RepositoryImportProvider.SERVER_SESSION_BULK_LOAD:
            session_start = perf_counter()
            server_session = self.provider_runner.open_server_session(plan)
            server_start_ms = _elapsed_ms(session_start)
            try:
                run_result = self.provider_runner.run(
                    plan,
                    source_snapshot,
                    import_artifact,
                    server_session=server_session,
                    execution_context=execution_plan.execution_context,
                )
            finally:
                cleanup_start = perf_counter()
                server_session.close()
                cleanup_duration_ms = _elapsed_ms(cleanup_start)
            total_duration_ms = (
                (run_result.total_duration_ms or 0)
                + server_start_ms
                + cleanup_duration_ms
            )
            return replace(
                run_result,
                server_start_ms=server_start_ms,
                cleanup_duration_ms=cleanup_duration_ms,
                total_duration_ms=total_duration_ms,
            )

        return self.provider_runner.run(
            plan,
            source_snapshot,
            import_artifact,
            execution_context=execution_plan.execution_context,
        )

    def _write_dataset_resolution(self, resolution: RepositoryImportBenchmarkDatasetResolution) -> None:
        dataset_dir = self.dataset_output_root / resolution.spec.dataset_id
        dataset_dir.mkdir(parents=True, exist_ok=True)
        _write_json_file(dataset_dir / "manifest.json", resolution.manifest.to_payload())
        _write_json_file(
            dataset_dir / "snapshot-summary.json",
            canonical_json_bytes(resolution.source_snapshot.summary).decode("utf-8"),
            raw_json_text=True,
        )

    def _write_log(self, message: str) -> None:
        self.logs_root.mkdir(parents=True, exist_ok=True)
        log_path = self.logs_root / "benchmark.log"
        timestamp = datetime.now(timezone.utc).isoformat()
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{timestamp} {message}\n")


def detect_local_machine_profile(
    *,
    machine_profile_id: str,
    dolt_bin: str = "dolt",
    mysql_bin: str = "mysql",
) -> RepositoryImportBenchmarkMachineProfile:
    return RepositoryImportBenchmarkMachineProfile(
        machine_profile_id=machine_profile_id,
        os_name=platform(),
        cpu_count=os.cpu_count(),
        cpu_model=None,
        memory_total_mb=None,
        disk_type=None,
        filesystem=None,
        dolt_version=_probe_version(dolt_bin, ("version",)),
        python_version=python_version(),
        mysql_client_version=_probe_version(mysql_bin, ("--version",)),
    )


def _probe_version(bin_name: str, args: Sequence[str]) -> str | None:
    if which(bin_name) is None:
        return None
    result = subprocess.run(
        (bin_name, *args),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    return _extract_version(output)


def _extract_version(output: str) -> str | None:
    import re

    match = re.search(r"(\d+(?:\.\d+){1,3})", output)
    if match is None:
        return output.strip() or None
    return match.group(1)


def _server_mode_for(provider: RepositoryImportProvider) -> RepositoryImportServerMode:
    if provider == RepositoryImportProvider.SERVER_SESSION_BULK_LOAD:
        return RepositoryImportServerMode.WARM_SESSION
    if provider in {
        RepositoryImportProvider.LOAD_DATA,
        RepositoryImportProvider.DOLT_SERVER_BULK_LOAD,
    }:
        return RepositoryImportServerMode.PER_IMPORT
    return RepositoryImportServerMode.DISABLED


def _execution_plan_for_profile(
    profile: RepositoryImportBenchmarkProfile,
) -> RepositoryImportBenchmarkExecutionPlan:
    if profile in {
        RepositoryImportBenchmarkProfile.IMPORT_HEALTH_SMOKE,
        RepositoryImportBenchmarkProfile.END_TO_END_COLD,
        RepositoryImportBenchmarkProfile.IMPORT_ONLY_WARM_ARTIFACT,
        RepositoryImportBenchmarkProfile.SERVER_SESSION,
    }:
        return RepositoryImportBenchmarkExecutionPlan(
            execution_context=RepositoryImportExecutionContext(
                caller_policy=RepositoryImportCallerPolicy.FINALIZE_WRITE_CALLER,
            ),
            shared_server_session=profile == RepositoryImportBenchmarkProfile.SERVER_SESSION,
        )
    raise ValueError(f"unsupported benchmark profile: {profile}")


def _validation_table_names_for_dataset(
    *,
    dataset_spec: RepositoryImportBenchmarkDatasetSpec,
    validation_table_names: Sequence[str] | Mapping[str, Sequence[str]] | None,
) -> tuple[str, ...]:
    if validation_table_names is None:
        return dataset_spec.validation_table_names
    if isinstance(validation_table_names, Mapping):
        selected = validation_table_names.get(dataset_spec.dataset_id)
        if selected is None:
            return dataset_spec.validation_table_names
        validation_table_names = selected
    normalized: list[str] = []
    seen: set[str] = set()
    for table_name in validation_table_names:
        canonical_table = canonical_identifier(str(table_name))
        if not canonical_table or canonical_table in seen:
            continue
        seen.add(canonical_table)
        normalized.append(canonical_table)
    return tuple(normalized)


def _coerce_provider(provider: RepositoryImportProvider | str) -> RepositoryImportProvider:
    return RepositoryImportProvider(provider)


def _coerce_profile(profile: RepositoryImportBenchmarkProfile | str) -> RepositoryImportBenchmarkProfile:
    return RepositoryImportBenchmarkProfile(profile)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError("expected an integer or null")
    return value


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("expected a mapping")
    return value


def _build_run_id() -> str:
    return f"repository-import-benchmark-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid4().hex[:8]}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_machine_profile_id() -> str:
    hostname = os.uname().nodename if hasattr(os, "uname") else None
    if not hostname:
        hostname = os.environ.get("HOSTNAME") or "local"
    return f"local-{hostname}"


def _write_json_file(path: Path, payload: object, *, raw_json_text: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if raw_json_text:
        if not isinstance(payload, str):
            raise TypeError("raw_json_text payload must be a string")
        path.write_text(payload, encoding="utf-8")
        return
    path.write_bytes(canonical_json_bytes(payload))


def _elapsed_ms(start: float) -> int:
    return max(0, int((perf_counter() - start) * 1000))
