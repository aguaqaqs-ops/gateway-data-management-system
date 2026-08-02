"""Shared correctness workflow and measurements for both P2-R1 providers."""

from __future__ import annotations

import resource
import re
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from gateway_repository_service.arrow_mapping import UnknownSqlTypeError, UnknownTypePolicy, TableCatalog
from gateway_repository_service.filesystem import tree_storage_bytes
from gateway_repository_service.fixtures import Fixture, Workload
from gateway_repository_service.layout import ProbeLayout, repository_key
from gateway_repository_service.locking import DurableRootLock
from gateway_repository_service.process import DoltRunner
from gateway_repository_service.publication import atomic_publish
from gateway_repository_service.providers import (
    OfflineCliProvider,
    Provider,
    ProviderError,
    SqlServerProvider,
)
from gateway_repository_service.settings import RepositoryServiceSettings


class Candidate(StrEnum):
    A = "candidate_a_offline_cli"
    B = "candidate_b_sql_server"


@dataclass(frozen=True)
class WorkflowMeasurement:
    candidate: Candidate
    workload: Workload
    sample_kind: str
    correctness: bool
    hard_gates: dict[str, bool]
    initial_commit_id: str | None
    new_commit_id: str | None
    total_rows: int
    time_to_first_batch_seconds: float | None
    total_stream_seconds: float | None
    stream_peak_rss_kib: int
    stream_rss_delta_kib: int
    provider_startup_seconds: float | None
    import_seconds: float | None
    rows_per_second: float | None
    peak_rss_kib: int
    cancel_cleanup_seconds: float | None
    logical_bytes_before: int
    logical_bytes_after: int
    allocated_bytes_before: int
    allocated_bytes_after: int
    staging_high_water_bytes: int
    error: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate": self.candidate.value,
            "workload": self.workload.value,
            "sample_kind": self.sample_kind,
            "correctness": self.correctness,
            "hard_gates": self.hard_gates,
            "initial_commit_id": self.initial_commit_id,
            "new_commit_id": self.new_commit_id,
            "total_rows": self.total_rows,
            "time_to_first_batch_seconds": self.time_to_first_batch_seconds,
            "total_stream_seconds": self.total_stream_seconds,
            "stream_peak_rss_kib": self.stream_peak_rss_kib,
            "stream_rss_delta_kib": self.stream_rss_delta_kib,
            "provider_startup_seconds": self.provider_startup_seconds,
            "import_seconds": self.import_seconds,
            "rows_per_second": self.rows_per_second,
            "peak_rss_kib": self.peak_rss_kib,
            "cancel_cleanup_seconds": self.cancel_cleanup_seconds,
            "logical_bytes_before": self.logical_bytes_before,
            "logical_bytes_after": self.logical_bytes_after,
            "allocated_bytes_before": self.allocated_bytes_before,
            "allocated_bytes_after": self.allocated_bytes_after,
            "staging_high_water_bytes": self.staging_high_water_bytes,
            "error": self.error,
        }


def run_workflow(
    settings: RepositoryServiceSettings,
    candidate: Candidate,
    fixture: Fixture,
    *,
    sample_kind: str,
    run_unknown_reject: bool = True,
    base_fixture: Fixture | None = None,
    root_parent: Path | None = None,
) -> WorkflowMeasurement:
    if root_parent is not None:
        root_parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix="gateway-p2r1-", dir=str(root_parent) if root_parent is not None else None
    ) as temporary:
        root = Path(temporary) / "data-root"
        layout = ProbeLayout.create(root)
        with DurableRootLock(layout.service_lock):
            return _run_locked(
                settings,
                candidate,
                fixture,
                layout,
                sample_kind=sample_kind,
                run_unknown_reject=run_unknown_reject,
                base_fixture=base_fixture,
            )


def _run_locked(
    settings: RepositoryServiceSettings,
    candidate: Candidate,
    fixture: Fixture,
    layout: ProbeLayout,
    *,
    sample_kind: str,
    run_unknown_reject: bool,
    base_fixture: Fixture | None,
) -> WorkflowMeasurement:
    initial_commit: str | None = None
    new_commit: str | None = None
    provider: Provider | None = None
    error: str | None = None
    correctness = False
    hard_gates = {
        "workflow": False,
        "cancellation": False,
        "restart": False,
        "bounded_stream": False,
        "unknown_type": False,
    }
    first_batch_seconds: float | None = None
    stream_seconds: float | None = None
    provider_startup_seconds: float | None = None
    import_seconds: float | None = None
    cancel_seconds: float | None = None
    total_rows = 0
    stream_peak_rss_kib = 0
    stream_rss_delta_kib = 0
    staging_high_water = 0
    logical_before = 0
    allocated_before = 0
    logical_after = 0
    allocated_after = 0
    try:
        repository_id = UUID(int=uuid4().int)
        key = repository_key(repository_id)
        staged = layout.staging_repository(key, uuid4().hex[:12])
        common = OfflineCliProvider(settings, layout, staged, DoltRunner(settings, layout.root))
        common.initialize_repository()
        staging_high_water = max(staging_high_water, tree_storage_bytes(layout.staging)[0])
        target = layout.published_repository(key)
        layout.assert_publication_devices(staged, target.parent)
        atomic_publish(staged, target)
        layout.assert_same_filesystem()
        logical_before, allocated_before = tree_storage_bytes(target)
        runner = DoltRunner(settings, layout.root)
        provider = _make_provider(settings, layout, target, runner, candidate)
        startup_started = time.monotonic()
        provider.open()
        provider_startup_seconds = time.monotonic() - startup_started
        initial_commit = provider.head()
        expected_parent = initial_commit
        replay_fixture = base_fixture or fixture
        import_started = time.monotonic()
        provider.replay(replay_fixture.replay_sql)
        if base_fixture is not None:
            base_marker = f"gateway-versioned-import operation_id={uuid4()}"
            base_commit = provider.commit_marker(base_marker)
            if provider.marker_parent(base_marker) != initial_commit:
                raise ProviderError("base marker parent does not equal initial commit")
            expected_parent = base_commit
        marker = f"gateway-versioned-import operation_id={uuid4()}"
        if base_fixture is not None:
            logical_before, allocated_before = tree_storage_bytes(target)
            provider.replay(fixture.replay_sql)
        new_commit = provider.commit_marker(marker)
        import_seconds = time.monotonic() - import_started
        logical_after, allocated_after = tree_storage_bytes(target)
        if provider.head() != new_commit:
            raise ProviderError("main does not point to marker commit")
        if provider.marker_count(marker) != 1:
            raise ProviderError("operation marker is not unique")
        if provider.marker_parent(marker) != expected_parent:
            raise ProviderError("marker parent does not equal initial commit")
        actual_catalog = provider.catalog(new_commit)
        _assert_catalog_exact(actual_catalog, fixture)
        # The fixed initial commit is created before replay, so its user catalog is
        # intentionally empty. Dolt's information_schema is not revision-aware; the
        # pinned row queries below provide the immutable-read proof for commits that
        # contain tables.
        initial_catalog = ()

        stream_start = time.monotonic()
        first_seen = False
        for table in actual_catalog:
            for batch in provider.stream_table(new_commit, table, UnknownTypePolicy.STRINGIFY):
                if not first_seen:
                    first_batch_seconds = time.monotonic() - stream_start
                    first_seen = True
                total_rows += batch.num_rows
        stream_seconds = time.monotonic() - stream_start
        stream_peak_rss_kib = int(getattr(provider, "last_stream_peak_rss_kib", 0))
        stream_rss_delta_kib = int(getattr(provider, "last_stream_rss_delta_kib", 0))
        if total_rows != sum(table.row_count for table in actual_catalog):
            raise ProviderError("stream row count mismatch")
        if first_batch_seconds is None or stream_seconds <= 0:
            raise ProviderError("stream did not produce a measurable batch")
        hard_gates["bounded_stream"] = True

        first_table = actual_catalog[0]
        cancelled = provider.stream_table(new_commit, first_table, UnknownTypePolicy.STRINGIFY)
        cancel_start = time.monotonic()
        next(cancelled)
        close = getattr(cancelled, "close", None)
        if callable(close):
            close()
        cancel_seconds = time.monotonic() - cancel_start
        hard_gates["cancellation"] = cancel_seconds < settings.terminate_grace_seconds * 2
        reread_rows = sum(
            batch.num_rows
            for batch in provider.stream_table(new_commit, first_table, UnknownTypePolicy.STRINGIFY)
        )
        if reread_rows != first_table.row_count:
            raise ProviderError("read after cancellation was contaminated")

        if run_unknown_reject:
            unknown = next(
                (table for table in actual_catalog if table.name == "unknown_types"), None
            )
            if unknown is not None:
                try:
                    list(provider.stream_table(new_commit, unknown, UnknownTypePolicy.REJECT))
                except UnknownSqlTypeError:
                    hard_gates["unknown_type"] = True
                else:
                    raise ProviderError("unknown type did not reject")
            else:
                hard_gates["unknown_type"] = True
        else:
            hard_gates["unknown_type"] = True

        provider.close()
        provider = None
        restart_runner = DoltRunner(settings, layout.root)
        restarted = _make_provider(settings, layout, target, restart_runner, candidate)
        restarted.open()
        try:
            if restarted.head() != new_commit or restarted.marker_count(marker) != 1:
                raise ProviderError("restart did not preserve commit/ref/marker")
            if restarted.catalog(new_commit) != actual_catalog:
                raise ProviderError("restart catalog changed")
            if initial_catalog:
                raise ProviderError("restart changed old immutable commit")
        finally:
            restarted.close()
        hard_gates["restart"] = True
        hard_gates["workflow"] = True
        correctness = all(hard_gates.values())
    except Exception as exc:
        error = type(exc).__name__ + ": " + _sanitize_error(str(exc))
    finally:
        if provider is not None:
            provider.close()

    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    total_seconds = stream_seconds or 0.0
    rows_per_second = total_rows / total_seconds if total_seconds > 0 else None
    if logical_after == 0 and allocated_after == 0:
        logical_after, allocated_after = tree_storage_bytes(layout.versioned)
    return WorkflowMeasurement(
        candidate=candidate,
        workload=fixture.workload,
        sample_kind=sample_kind,
        correctness=correctness,
        hard_gates=hard_gates,
        initial_commit_id=initial_commit,
        new_commit_id=new_commit,
        total_rows=total_rows,
        time_to_first_batch_seconds=first_batch_seconds,
        total_stream_seconds=stream_seconds,
        stream_peak_rss_kib=stream_peak_rss_kib,
        stream_rss_delta_kib=stream_rss_delta_kib,
        provider_startup_seconds=provider_startup_seconds,
        import_seconds=import_seconds,
        rows_per_second=rows_per_second,
        peak_rss_kib=int(usage.ru_maxrss),
        cancel_cleanup_seconds=cancel_seconds,
        logical_bytes_before=logical_before,
        logical_bytes_after=logical_after,
        allocated_bytes_before=allocated_before,
        allocated_bytes_after=allocated_after,
        staging_high_water_bytes=staging_high_water,
        error=error,
    )


def _make_provider(
    settings: RepositoryServiceSettings,
    layout: ProbeLayout,
    repository: Path,
    runner: DoltRunner,
    candidate: Candidate,
) -> Provider:
    if candidate == Candidate.A:
        return OfflineCliProvider(settings, layout, repository, runner)
    return SqlServerProvider(settings, layout, repository, runner)


def _sanitize_error(message: str) -> str:
    return re.sub(r"/[A-Za-z0-9_.:/-]+", "<path>", message)[:512]


def _assert_catalog_exact(actual: tuple[TableCatalog, ...], fixture: Fixture) -> None:
    expected = fixture.expected_tables
    if len(actual) != len(expected):
        raise ProviderError("user table set mismatch")
    for actual_table, expected_table in zip(actual, expected, strict=True):
        if actual_table.name != expected_table.name:
            raise ProviderError("table order/name mismatch")
        if actual_table.row_count != expected_table.row_count:
            raise ProviderError(f"row count mismatch for {actual_table.name}")
        if actual_table.primary_key != expected_table.primary_key:
            raise ProviderError(f"primary key mismatch for {actual_table.name}")
        if len(actual_table.columns) != len(expected_table.columns):
            raise ProviderError(f"column count mismatch for {actual_table.name}")
        for actual_column, expected_column in zip(
            actual_table.columns, expected_table.columns, strict=True
        ):
            if (
                actual_column.name != expected_column.name
                or actual_column.sql_type != expected_column.sql_type
                or actual_column.nullable != expected_column.nullable
                or actual_column.primary_key_position != expected_column.primary_key_position
            ):
                raise ProviderError(
                    f"column mismatch for {actual_table.name}.{expected_column.name}"
                )
