"""Tests for Candidate A Versioned import provider port and adapter."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch
from uuid import UUID

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from gateway_repository_contracts import UnknownTypePolicy
from gateway_repository_service.arrow_mapping import ColumnCatalog, TableCatalog
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import CommandResult, DoltRunner
from gateway_repository_service.providers import OfflineCliProvider, ProviderError
from gateway_repository_service.versioned_import.models import (
    derive_operation_marker,
    derive_private_ref_name,
)
from gateway_repository_service.versioned_import.ports import (
    CancellationCallback,
    MarkerInspectionUnique,
    MarkerInspectionZero,
    PublishMainAmbiguous,
    PublishMainMismatch,
    PublishMainPublished,
)
from gateway_repository_service.versioned_import.provider import CandidateAImportProvider
from support.lifecycle_harness import dolt_available, lifecycle_settings


OPERATION_ID = UUID("00000000-0000-4000-8000-0000000000a1")


class FakeImportProvider:
    """In-memory provider for port contract tests."""

    def __init__(self) -> None:
        self.refs: dict[str, str] = {"main": "commit-main"}
        self.markers: dict[str, tuple[str, str, tuple[str, ...]]] = {}
        self.publish_force_fail = False
        self.publish_readback_mismatch = False

    def read_ref(self, ref_name: str) -> str:
        return self.refs[ref_name]

    def create_private_ref(self, private_ref: str, expected_commit: str) -> None:
        self.refs[private_ref] = expected_commit

    def checkout_private_ref(self, private_ref: str) -> None:
        if private_ref not in self.refs:
            raise RuntimeError("missing private ref")

    def replay_sql(self, replay_path: Path, cancellation: CancellationCallback | None = None) -> None:
        if cancellation is not None and cancellation():
            raise RuntimeError("cancelled")

    def commit_operation_marker(self, private_ref: str, marker: str) -> str:
        parent = self.refs[private_ref]
        candidate = f"candidate-{len(self.markers) + 1}"
        self.refs[private_ref] = candidate
        self.markers[marker] = (candidate, parent, (private_ref,))
        return candidate

    def inspect_marker(self, marker: str) -> object:
        if marker not in self.markers:
            return MarkerInspectionZero()
        candidate, parent, refs = self.markers[marker]
        return MarkerInspectionUnique(candidate=candidate, parent=parent, refs=refs)

    def read_catalog(self, candidate: str) -> tuple[TableCatalog, ...]:
        return (
            TableCatalog(
                "records",
                (ColumnCatalog("id", "BIGINT", False, 0),),
                0,
            ),
        )

    def stream_table(
        self,
        candidate: str,
        table: TableCatalog,
        policy: UnknownTypePolicy,
    ) -> Iterator[pa.RecordBatch]:
        yield pa.record_batch({"id": pa.array([], type=pa.int64())})

    def publish_main(self, expected_commit: str, candidate: str) -> object:
        if self.refs["main"] != expected_commit:
            return PublishMainMismatch(actual=self.refs["main"])
        if self.publish_force_fail:
            return PublishMainAmbiguous()
        if self.publish_readback_mismatch:
            self.refs["main"] = "wrong-readback"
            return PublishMainAmbiguous()
        self.refs["main"] = candidate
        if self.refs["main"] != candidate:
            return PublishMainAmbiguous()
        return PublishMainPublished()

    def delete_private_ref(self, private_ref: str, expected_candidate: str | None = None) -> None:
        if expected_candidate is not None and self.refs.get(private_ref) != expected_candidate:
            raise RuntimeError("candidate mismatch")
        del self.refs[private_ref]


def test_derived_private_ref_and_marker_names() -> None:
    assert derive_private_ref_name(OPERATION_ID) == "gateway-import-000000000000400080000000000000a1"
    assert (
        derive_operation_marker(OPERATION_ID)
        == "gateway-versioned-import operation_id=00000000-0000-4000-8000-0000000000a1"
    )


def test_fake_provider_unique_marker_and_expected_parent() -> None:
    provider = FakeImportProvider()
    private_ref = derive_private_ref_name(OPERATION_ID)
    marker = derive_operation_marker(OPERATION_ID)
    expected = provider.read_ref("main")

    provider.create_private_ref(private_ref, expected)
    provider.checkout_private_ref(private_ref)
    candidate = provider.commit_operation_marker(private_ref, marker)

    inspection = provider.inspect_marker(marker)
    assert isinstance(inspection, MarkerInspectionUnique)
    assert inspection.candidate == candidate
    assert inspection.parent == expected
    assert private_ref in inspection.refs


def test_fake_provider_publish_mismatch_and_successful_update() -> None:
    provider = FakeImportProvider()
    private_ref = derive_private_ref_name(OPERATION_ID)
    marker = derive_operation_marker(OPERATION_ID)
    expected = provider.read_ref("main")

    provider.create_private_ref(private_ref, expected)
    candidate = provider.commit_operation_marker(private_ref, marker)

    provider.refs["main"] = "other-commit"
    mismatch = provider.publish_main(expected, candidate)
    assert isinstance(mismatch, PublishMainMismatch)
    assert mismatch.actual == "other-commit"

    provider.refs["main"] = expected
    published = provider.publish_main(expected, candidate)
    assert isinstance(published, PublishMainPublished)
    assert provider.read_ref("main") == candidate


def test_fake_provider_ambiguous_publish_paths() -> None:
    provider = FakeImportProvider()
    private_ref = derive_private_ref_name(OPERATION_ID)
    marker = derive_operation_marker(OPERATION_ID)
    expected = provider.read_ref("main")
    provider.create_private_ref(private_ref, expected)
    candidate = provider.commit_operation_marker(private_ref, marker)

    provider.publish_force_fail = True
    assert isinstance(provider.publish_main(expected, candidate), PublishMainAmbiguous)

    provider.publish_force_fail = False
    provider.publish_readback_mismatch = True
    assert isinstance(provider.publish_main(expected, candidate), PublishMainAmbiguous)


def test_fake_provider_zero_marker_and_private_cleanup() -> None:
    provider = FakeImportProvider()
    assert isinstance(provider.inspect_marker("missing"), MarkerInspectionZero)

    private_ref = derive_private_ref_name(OPERATION_ID)
    expected = provider.read_ref("main")
    provider.create_private_ref(private_ref, expected)
    candidate = provider.commit_operation_marker(
        private_ref,
        derive_operation_marker(OPERATION_ID),
    )
    provider.delete_private_ref(private_ref, expected_candidate=candidate)
    assert private_ref not in provider.refs


@pytest.fixture
def import_layout(tmp_path: Path) -> DurableLayout:
    settings = lifecycle_settings(tmp_path)
    return DurableLayout.create_for_probe(settings.data_root)


@pytest.fixture
def import_provider(import_layout: DurableLayout) -> CandidateAImportProvider:
    settings = lifecycle_settings(import_layout.root.parent)
    repository = import_layout.staging_artifacts / "import-repo"
    repository.mkdir(parents=True, exist_ok=True)
    runner = DoltRunner(settings, import_layout.root)
    cli = OfflineCliProvider(settings, import_layout, repository, runner)
    cli.initialize_repository()
    return CandidateAImportProvider(settings, import_layout, repository, runner)


def _staging_replay_path(layout: DurableLayout, name: str, sql: str) -> Path:
    path = layout.staging_artifacts / name
    path.write_text(sql, encoding="utf-8")
    return path


def _candidate_on_private_ref(
    provider: CandidateAImportProvider,
    layout: DurableLayout,
    *,
    table_sql: str,
) -> tuple[str, str, str, str]:
    private_ref = derive_private_ref_name(OPERATION_ID)
    marker = derive_operation_marker(OPERATION_ID)
    expected = provider.read_ref("main")
    provider.create_private_ref(private_ref, expected)
    provider.checkout_private_ref(private_ref)
    provider.replay_sql(_staging_replay_path(layout, "replay.sql", table_sql))
    candidate = provider.commit_operation_marker(private_ref, marker)
    return private_ref, marker, expected, candidate


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_dolt_integration_private_ref_marker_publish_and_cleanup(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref, marker, expected, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE records (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    inspection = import_provider.inspect_marker(marker)
    assert isinstance(inspection, MarkerInspectionUnique)
    assert inspection.candidate == candidate
    assert inspection.parent == expected
    assert private_ref in inspection.refs

    catalog = import_provider.read_catalog(candidate)
    assert any(table.name == "records" for table in catalog)

    mismatch = import_provider.publish_main("wrong-expected", candidate)
    assert isinstance(mismatch, PublishMainMismatch)
    assert import_provider.read_ref("main") == expected

    published = import_provider.publish_main(expected, candidate)
    assert isinstance(published, PublishMainPublished)
    assert import_provider.read_ref("main") == candidate

    import_provider.delete_private_ref(private_ref, expected_candidate=candidate)
    with pytest.raises(ProviderError):
        import_provider.read_ref(private_ref)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_inspect_marker_unique_after_main_publish_with_private_ref_retained(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref, marker, expected, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE retained (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    published = import_provider.publish_main(expected, candidate)
    assert isinstance(published, PublishMainPublished)

    inspection = import_provider.inspect_marker(marker)
    assert isinstance(inspection, MarkerInspectionUnique)
    assert inspection.candidate == candidate
    assert private_ref in inspection.refs
    assert "main" in inspection.refs


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_commit_without_checkout_does_not_modify_main(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref = derive_private_ref_name(OPERATION_ID)
    marker = derive_operation_marker(OPERATION_ID)
    expected = import_provider.read_ref("main")

    import_provider.create_private_ref(private_ref, expected)

    with pytest.raises(ProviderError):
        import_provider.commit_operation_marker(private_ref, marker)

    assert import_provider.read_ref("main") == expected


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_ref_rejects_injection_payload(import_provider: CandidateAImportProvider) -> None:
    with pytest.raises(ValueError):
        import_provider.read_ref("main'); CREATE TABLE injected (id BIGINT); SELECT HASHOF('main")


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_create_private_ref_idempotent(
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref = derive_private_ref_name(OPERATION_ID)
    expected = import_provider.read_ref("main")
    import_provider.create_private_ref(private_ref, expected)
    import_provider.create_private_ref(private_ref, expected)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_delete_private_ref_idempotent(import_provider: CandidateAImportProvider) -> None:
    private_ref = derive_private_ref_name(OPERATION_ID)
    expected = import_provider.read_ref("main")
    import_provider.create_private_ref(private_ref, expected)
    import_provider.delete_private_ref(private_ref)
    import_provider.delete_private_ref(private_ref)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_replay_rejects_path_outside_staging(
    import_provider: CandidateAImportProvider,
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.sql"
    outside.write_text("SELECT 1;\n", encoding="utf-8")
    with pytest.raises(ProviderError, match="staging"):
        import_provider.replay_sql(outside)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_dolt_integration_publish_main_ambiguous_on_force_failure(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, marker, expected, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE ambiguous_probe (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    timed_out_result = CommandResult(
        command_kind="publish_main_force",
        exit_code=1,
        duration_seconds=0.1,
        stdout=b"",
        stdout_tail=b"",
        stderr_tail=b"failed",
        timed_out=True,
    )
    original_run = import_provider._runner.run

    def selective_run(
        command_kind: str,
        args: list[str],
        *,
        cwd: Path,
        timeout: float,
        stdin_path: Path | None = None,
        capture_stdout: bool = False,
    ) -> CommandResult:
        if command_kind == "publish_main_force":
            return timed_out_result
        return original_run(
            command_kind,
            args,
            cwd=cwd,
            timeout=timeout,
            stdin_path=stdin_path,
            capture_stdout=capture_stdout,
        )

    with patch.object(import_provider._runner, "run", side_effect=selective_run):
        result = import_provider.publish_main(expected, candidate)

    assert isinstance(result, PublishMainAmbiguous)
    assert import_provider.read_ref("main") == expected


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_publish_main_ambiguous_on_readback_mismatch(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, expected, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE readback_probe (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    original_read_ref = import_provider.read_ref
    readback_calls = 0

    def selective_read_ref(ref_name: str) -> str:
        nonlocal readback_calls
        if ref_name == "main":
            readback_calls += 1
            if readback_calls >= 2:
                return "wrong-readback-commit"
        return original_read_ref(ref_name)

    with patch.object(import_provider, "read_ref", side_effect=selective_read_ref):
        result = import_provider.publish_main(expected, candidate)

    assert isinstance(result, PublishMainAmbiguous)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_dolt_replay_uses_stdin_without_leaking_sql_path(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref = derive_private_ref_name(OPERATION_ID)
    expected = import_provider.read_ref("main")
    import_provider.create_private_ref(private_ref, expected)
    import_provider.checkout_private_ref(private_ref)

    secret_sql = "CREATE TABLE leak_probe (id BIGINT NOT NULL PRIMARY KEY);\n"
    replay_sql = _staging_replay_path(import_layout, "leak.sql", secret_sql)

    captured: list[list[str]] = []
    original_run = import_provider._runner.run

    def recording_run(
        command_kind: str,
        args: list[str],
        *,
        cwd: Path,
        timeout: float,
        stdin_path: Path | None = None,
        capture_stdout: bool = False,
    ) -> CommandResult:
        captured.append(list(args))
        return original_run(
            command_kind,
            args,
            cwd=cwd,
            timeout=timeout,
            stdin_path=stdin_path,
            capture_stdout=capture_stdout,
        )

    with patch.object(import_provider._runner, "run", side_effect=recording_run):
        import_provider.replay_sql(replay_sql)

    replay_args = next(args for args in captured if "sql" in args)
    assert secret_sql not in " ".join(replay_args)
    assert str(replay_sql) not in " ".join(replay_args)
