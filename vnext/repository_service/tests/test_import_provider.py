"""Tests for Candidate A Versioned import provider port and adapter."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import UUID
import csv
import threading

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from gateway_repository_contracts import UnknownTypePolicy
from gateway_repository_service.arrow_mapping import (
    ColumnCatalog,
    TableCatalog,
    UnknownSqlTypeError,
    UnknownTypePolicy as ArrowUnknownTypePolicy,
)
from gateway_repository_service.candidate_a.dolt_cli import DoltCliError
from gateway_repository_service.candidate_a.errors import CandidateAError
from gateway_repository_service.candidate_a.ref_validation import IMPORT_MAIN_REF
from gateway_repository_service.candidate_a.sql import ProviderError, _parse_create_statement
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import CommandResult, DoltRunner, ProcessBoundaryError
from gateway_repository_service.providers import OfflineCliProvider
from gateway_repository_service.versioned_import.errors import ImportProviderError
from gateway_repository_service.versioned_import.models import (
    derive_operation_marker,
    derive_private_ref_name,
)
from gateway_repository_service.versioned_import.ports import (
    CancellationCallback,
    MarkerInspectionAmbiguous,
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

    def replay_sql(
        self,
        private_ref: str,
        replay_path: Path,
        cancellation: CancellationCallback | None = None,
    ) -> None:
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
    provider.replay_sql(private_ref, _staging_replay_path(layout, "replay.sql", table_sql))
    candidate = provider.commit_operation_marker(private_ref, marker)
    return private_ref, marker, expected, candidate


def _malformed_json_command_result(stdout: bytes, command_kind: str) -> CommandResult:
    return CommandResult(
        command_kind=command_kind,
        exit_code=0,
        duration_seconds=0.0,
        stdout=stdout,
        stdout_tail=stdout,
        stderr_tail=b"",
        timed_out=False,
    )


def _run_cli_malformed_json_side_effect(
    import_provider: CandidateAImportProvider,
    stdout: bytes,
    *,
    kinds: frozenset[str],
) -> object:
    original_run_cli = import_provider._cli.run_cli

    def side_effect(
        kind: str,
        args: list[str],
        timeout: float,
        *,
        stdin_path: Path | None = None,
    ) -> CommandResult:
        if kind in kinds:
            return _malformed_json_command_result(stdout, kind)
        return original_run_cli(kind, args, timeout, stdin_path=stdin_path)

    return side_effect


MALFORMED_JSON_SHAPES: tuple[tuple[bytes, str], ...] = (
    (b'{"rows":[],"columns":null}', "Dolt JSON columns was not a list"),
    (b'{"rows":[],"columns":"bad"}', "Dolt JSON columns was not a list"),
    (b'{"rows":"bad","columns":[{"name":"x"}]}', "Dolt JSON rows was not a list"),
)

MARKER_FAULT_JSON_SHAPES: tuple[tuple[bytes, str], ...] = (
    (b'{"rows":[],"columns":null}', "Dolt JSON columns was not a list"),
    (b'{"rows":"bad","columns":[{"name":"x"}]}', "Dolt JSON rows was not a list"),
)


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
    with pytest.raises(ImportProviderError):
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
    before_private = import_provider.read_ref(private_ref)

    candidate = import_provider.commit_operation_marker(private_ref, marker)

    assert import_provider.read_ref("main") == expected
    assert candidate != before_private


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
    with pytest.raises(ImportProviderError, match="staging"):
        import_provider.replay_sql(derive_private_ref_name(OPERATION_ID), outside)


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
        import_provider.replay_sql(private_ref, replay_sql)

    replay_args = next(args for args in captured if "sql" in args)
    assert secret_sql not in " ".join(replay_args)
    assert str(replay_sql) not in " ".join(replay_args)


OPERATION_ID_B = UUID("00000000-0000-4000-8000-0000000000b2")


def test_private_ref_api_rejects_main(import_provider: CandidateAImportProvider) -> None:
    main_hash = import_provider.read_ref(IMPORT_MAIN_REF)
    marker = derive_operation_marker(OPERATION_ID)

    with pytest.raises(ValueError, match="private ref"):
        import_provider.create_private_ref(IMPORT_MAIN_REF, main_hash)
    with pytest.raises(ValueError, match="private ref"):
        import_provider.checkout_private_ref(IMPORT_MAIN_REF)
    with pytest.raises(ValueError, match="private ref"):
        import_provider.commit_operation_marker(IMPORT_MAIN_REF, marker)
    with pytest.raises(ValueError, match="private ref"):
        import_provider.delete_private_ref(IMPORT_MAIN_REF)

    assert import_provider.read_ref(IMPORT_MAIN_REF) == main_hash


def test_private_ref_marker_operation_ids_must_match(
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref = derive_private_ref_name(OPERATION_ID)
    wrong_marker = derive_operation_marker(OPERATION_ID_B)
    expected = import_provider.read_ref(IMPORT_MAIN_REF)
    import_provider.create_private_ref(private_ref, expected)
    import_provider.checkout_private_ref(private_ref)

    with pytest.raises(ValueError, match="operation id mismatch"):
        import_provider.commit_operation_marker(private_ref, wrong_marker)


def test_commit_operation_marker_rejects_main(import_provider: CandidateAImportProvider) -> None:
    marker = derive_operation_marker(OPERATION_ID)
    main_hash = import_provider.read_ref(IMPORT_MAIN_REF)

    with pytest.raises(ValueError, match="private ref"):
        import_provider.commit_operation_marker(IMPORT_MAIN_REF, marker)

    assert import_provider.read_ref(IMPORT_MAIN_REF) == main_hash


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_stream_table_rejects_commit_id_injection_without_side_effect(
    import_provider: CandidateAImportProvider,
) -> None:
    table = TableCatalog(
        "records",
        (ColumnCatalog("id", "BIGINT", False, 0),),
        0,
    )
    malicious = "abc'); CREATE TABLE injected (id BIGINT); SELECT HASHOF('main"
    main_hash = import_provider.read_ref(IMPORT_MAIN_REF)

    with pytest.raises(ValueError, match="commit id"):
        list(import_provider.stream_table(malicious, table, UnknownTypePolicy.STRINGIFY))

    assert import_provider.read_ref(IMPORT_MAIN_REF) == main_hash
    tables = import_provider._cli.query_json("show_tables", "SHOW FULL TABLES;\n")
    table_names = {str(row.get("Tables_in_import-repo", row.get("Table", ""))) for row in tables}
    assert "injected" not in table_names


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_catalog_rejects_commit_id_injection(
    import_provider: CandidateAImportProvider,
) -> None:
    malicious = "abc'); CREATE TABLE injected (id BIGINT); SELECT HASHOF('main"
    main_hash = import_provider.read_ref(IMPORT_MAIN_REF)

    with pytest.raises(ValueError, match="commit id"):
        import_provider.read_catalog(malicious)

    assert import_provider.read_ref(IMPORT_MAIN_REF) == main_hash


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_marker_conflicting_candidates_are_ambiguous(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref, marker, _, _ = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE conflict_a (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    original_query_json = import_provider._cli.query_json

    def conflicting_logs(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        rows = original_query_json(kind, sql, revision=revision)
        if kind == "marker_scan" and revision == private_ref:
            duplicate = dict(rows[0])
            duplicate["commit_hash"] = "other-candidate-hash"
            duplicate["parents"] = "other-parent-hash"
            rows.append(duplicate)
        return rows

    with patch.object(import_provider._cli, "query_json", side_effect=conflicting_logs):
        inspection = import_provider.inspect_marker(marker)

    assert isinstance(inspection, MarkerInspectionAmbiguous)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_marker_missing_ref_is_ambiguous(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, marker, _, _ = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE missing_ref (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(import_provider, "_refs_for_commit", return_value=()):
        inspection = import_provider.inspect_marker(marker)

    assert isinstance(inspection, MarkerInspectionAmbiguous)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_marker_malformed_parents_is_ambiguous(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref, marker, _, _ = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE malformed_parents (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    original_query_json = import_provider._cli.query_json

    def malformed_parents_log(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        rows = original_query_json(kind, sql, revision=revision)
        if kind == "marker_scan" and revision == private_ref:
            rows[0]["parents"] = "parent-a, parent-b"
        return rows

    with patch.object(import_provider._cli, "query_json", side_effect=malformed_parents_log):
        inspection = import_provider.inspect_marker(marker)

    assert isinstance(inspection, MarkerInspectionAmbiguous)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_replay_cancellation_before_start(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref = derive_private_ref_name(OPERATION_ID)
    expected = import_provider.read_ref(IMPORT_MAIN_REF)
    import_provider.create_private_ref(private_ref, expected)
    import_provider.checkout_private_ref(private_ref)
    replay_sql = _staging_replay_path(
        import_layout,
        "cancel.sql",
        "CREATE TABLE cancel_probe (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with pytest.raises(ImportProviderError, match="cancelled"):
        import_provider.replay_sql(private_ref, replay_sql, cancellation=lambda: True)

    assert import_provider.read_ref(IMPORT_MAIN_REF) == expected
    tables = import_provider._cli.query_json("show_tables", "SHOW FULL TABLES;\n")
    table_names = {str(row.get("Tables_in_import-repo", row.get("Table", ""))) for row in tables}
    assert "cancel_probe" not in table_names


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_stream_missing_table_nonzero_is_typed_error(
    import_provider: CandidateAImportProvider,
) -> None:
    main_hash = import_provider.read_ref(IMPORT_MAIN_REF)
    table = TableCatalog(
        "missing_table_probe",
        (ColumnCatalog("id", "BIGINT", False, 0),),
        0,
    )

    with pytest.raises(ImportProviderError):
        list(import_provider.stream_table(main_hash, table, UnknownTypePolicy.STRINGIFY))

    assert import_provider.read_ref(IMPORT_MAIN_REF) == main_hash


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_stream_iteration_error_is_wrapped_as_import_provider_error(
    import_provider: CandidateAImportProvider,
) -> None:
    table = TableCatalog(
        "records",
        (ColumnCatalog("id", "BIGINT", False, 0),),
        0,
    )
    main_hash = import_provider.read_ref(IMPORT_MAIN_REF)

    def failing_stream(*args: object, **kwargs: object) -> Iterator[pa.RecordBatch]:
        def _gen() -> Iterator[pa.RecordBatch]:
            raise DoltCliError("stream failed mid-iteration")
            yield pa.record_batch({"id": pa.array([], type=pa.int64())})  # pragma: no cover

        return _gen()

    with patch.object(import_provider._cli, "stream_table", side_effect=failing_stream):
        with pytest.raises(ImportProviderError, match="stream failed"):
            list(import_provider.stream_table(main_hash, table, UnknownTypePolicy.STRINGIFY))


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_marker_scan_timeout_returns_ambiguous(
    import_provider: CandidateAImportProvider,
) -> None:
    marker = derive_operation_marker(OPERATION_ID)

    with patch.object(
        import_provider._cli,
        "query_json",
        side_effect=DoltCliError("Dolt command failed: marker_scan"),
    ):
        inspection = import_provider.inspect_marker(marker)

    assert isinstance(inspection, MarkerInspectionAmbiguous)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_marker_scan_invalid_json_returns_ambiguous(
    import_provider: CandidateAImportProvider,
) -> None:
    marker = derive_operation_marker(OPERATION_ID)

    def invalid_json_query(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        raise DoltCliError("Dolt metadata was not valid JSON")

    with patch.object(import_provider._cli, "query_json", side_effect=invalid_json_query):
        inspection = import_provider.inspect_marker(marker)

    assert isinstance(inspection, MarkerInspectionAmbiguous)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_catalog_parent_query_failure_is_typed(
    import_provider: CandidateAImportProvider,
) -> None:
    candidate = import_provider.read_ref(IMPORT_MAIN_REF)

    with patch.object(
        import_provider._cli,
        "query_json",
        side_effect=DoltCliError("Dolt command failed: candidate_parent"),
    ):
        with pytest.raises(ImportProviderError, match="candidate_parent"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_marker_null_parent_is_ambiguous(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref, marker, _, _ = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE null_parent (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    original_query_json = import_provider._cli.query_json

    def null_parent_log(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        rows = original_query_json(kind, sql, revision=revision)
        if kind == "marker_scan" and revision == private_ref:
            rows[0]["parents"] = None
        return rows

    with patch.object(import_provider._cli, "query_json", side_effect=null_parent_log):
        inspection = import_provider.inspect_marker(marker)

    assert isinstance(inspection, MarkerInspectionAmbiguous)


def test_import_production_does_not_import_probe_and_probe_does_not_import_versioned_import() -> None:
    import os
    import subprocess
    import sys
    from pathlib import Path

    src_root = Path(__file__).resolve().parents[1] / "src"
    production_script = """
import os
import sys
import types
import importlib
from pathlib import Path

src_root = Path(os.environ["SRC_ROOT"])
service_pkg = src_root / "gateway_repository_service"
sys.path.insert(0, str(src_root))

def make_pkg(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module

make_pkg("gateway_repository_service", service_pkg)
make_pkg("gateway_repository_service.versioned_import", service_pkg / "versioned_import")

importlib.import_module("gateway_repository_service.versioned_import.provider")
blocked = (
    "gateway_repository_service.providers",
    "gateway_repository_service.workflow",
)
for name in blocked:
    if name in sys.modules:
        raise SystemExit(name)
raise SystemExit(0)
"""
    probe_script = """
import os
import sys
import types
import importlib
from pathlib import Path

src_root = Path(os.environ["SRC_ROOT"])
service_pkg = src_root / "gateway_repository_service"
sys.path.insert(0, str(src_root))

def make_pkg(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module

make_pkg("gateway_repository_service", service_pkg)

importlib.import_module("gateway_repository_service.providers")
for name in sys.modules:
    if name.startswith("gateway_repository_service.versioned_import"):
        raise SystemExit(name)
raise SystemExit(0)
"""
    env = os.environ.copy()
    env["SRC_ROOT"] = str(src_root)
    production_result = subprocess.run(
        [sys.executable, "-c", production_script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    probe_result = subprocess.run(
        [sys.executable, "-c", probe_script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert production_result.returncode == 0, production_result.stdout + production_result.stderr
    assert probe_result.returncode == 0, probe_result.stdout + probe_result.stderr


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_replay_requires_private_ref(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref = derive_private_ref_name(OPERATION_ID)
    expected = import_provider.read_ref(IMPORT_MAIN_REF)
    import_provider.create_private_ref(private_ref, expected)
    replay_sql = _staging_replay_path(
        import_layout,
        "accidental.sql",
        "CREATE TABLE accidentally_on_main (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with pytest.raises(ImportProviderError, match="private ref checkout"):
        import_provider.replay_sql(private_ref, replay_sql)

    assert import_provider.read_ref(IMPORT_MAIN_REF) == expected
    tables = import_provider._cli.query_json("show_tables", "SHOW FULL TABLES;\n")
    table_names = {
        str(row.get("Tables_in_import-repo", row.get("Table", ""))) for row in tables
    }
    assert "accidentally_on_main" not in table_names


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_private_candidate_after_checkout_main(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref, marker, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE private_only (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    import_provider._run_cli(
        "checkout_main_for_catalog_probe",
        ["checkout", IMPORT_MAIN_REF],
        import_provider._settings.metadata_timeout_seconds,
    )

    catalog = import_provider.read_catalog(candidate)
    assert any(table.name == "private_only" for table in catalog)

    import_provider.checkout_private_ref(private_ref)
    import_provider.delete_private_ref(private_ref, expected_candidate=candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_data_only_increment(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref = derive_private_ref_name(OPERATION_ID)
    marker = derive_operation_marker(OPERATION_ID)
    expected = import_provider.read_ref(IMPORT_MAIN_REF)
    import_provider.create_private_ref(private_ref, expected)
    import_provider.checkout_private_ref(private_ref)
    import_provider.replay_sql(
        private_ref,
        _staging_replay_path(
            import_layout,
            "base_records.sql",
            "CREATE TABLE records (id BIGINT NOT NULL PRIMARY KEY);\nINSERT INTO records VALUES (1);\n",
        ),
    )
    import_provider.commit_operation_marker(private_ref, marker)
    import_provider.replay_sql(
        private_ref,
        _staging_replay_path(import_layout, "update_records.sql", "UPDATE records SET id = 2;\n"),
    )
    candidate = import_provider.commit_operation_marker(private_ref, marker)

    catalog = import_provider.read_catalog(candidate)
    records = next(table for table in catalog if table.name == "records")
    assert records.row_count == 1


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_marker_invalid_parent_is_ambiguous(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref, marker, _, _ = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE invalid_parent (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    original_query_json = import_provider._cli.query_json

    def invalid_parent_log(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        rows = original_query_json(kind, sql, revision=revision)
        if kind == "marker_scan" and revision == private_ref:
            rows[0]["parents"] = "not-a-valid-commit-id!!!"
        return rows

    with patch.object(import_provider._cli, "query_json", side_effect=invalid_parent_log):
        inspection = import_provider.inspect_marker(marker)

    assert isinstance(inspection, MarkerInspectionAmbiguous)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_marker_branch_list_failure_is_ambiguous(
    import_provider: CandidateAImportProvider,
) -> None:
    marker = derive_operation_marker(OPERATION_ID)

    with patch.object(import_provider, "_branch_names", side_effect=ImportProviderError("Dolt branch list failed")):
        inspection = import_provider.inspect_marker(marker)

    assert isinstance(inspection, MarkerInspectionAmbiguous)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_helper_failure_is_typed(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE catalog_fail (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "catalog",
        side_effect=ProviderError("malformed catalog"),
    ):
        with pytest.raises(ImportProviderError, match="malformed catalog"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_stream_timeout_and_parser_failures_are_typed(
    import_provider: CandidateAImportProvider,
) -> None:
    table = TableCatalog(
        "records",
        (ColumnCatalog("id", "BIGINT", False, 0),),
        0,
    )
    candidate = import_provider.read_ref(IMPORT_MAIN_REF)

    def failing_stream(*args: object, **kwargs: object) -> Iterator[pa.RecordBatch]:
        def _gen() -> Iterator[pa.RecordBatch]:
            raise ProcessBoundaryError("stream line exceeded bounded output limit")
            yield pa.record_batch({"id": pa.array([], type=pa.int64())})  # pragma: no cover

        return _gen()

    with patch.object(import_provider._cli, "stream_table", side_effect=failing_stream):
        with pytest.raises(ImportProviderError, match="bounded output"):
            list(import_provider.stream_table(candidate, table, UnknownTypePolicy.STRINGIFY))


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_concurrent_streams_keep_field_limit(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    import csv

    private_ref, marker, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE stream_rows (payload VARCHAR(12000) NOT NULL, id BIGINT NOT NULL PRIMARY KEY);\n"
        "INSERT INTO stream_rows VALUES (REPEAT('x', 10000), 1);\n",
    )
    table = TableCatalog(
        "stream_rows",
        (
            ColumnCatalog("payload", "VARCHAR(12000)", False, None),
            ColumnCatalog("id", "BIGINT", False, 0),
        ),
        1,
    )
    recorded_limits: list[int] = []
    lock = threading.Lock()
    original_stream_table = import_provider._cli.stream_table

    def recording_stream(
        commit_id: str,
        table: TableCatalog,
        policy: ArrowUnknownTypePolicy,
    ) -> Iterator[pa.RecordBatch]:
        with lock:
            recorded_limits.append(csv.field_size_limit())
        return original_stream_table(commit_id, table, policy)

    errors: list[BaseException] = []

    def consume() -> None:
        try:
            with patch.object(import_provider._cli, "stream_table", side_effect=recording_stream):
                list(import_provider.stream_table(candidate, table, UnknownTypePolicy.STRINGIFY))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=consume), threading.Thread(target=consume)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert recorded_limits
    assert all(
        limit >= import_provider._settings.max_stream_line_bytes for limit in recorded_limits
    )


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_marker_process_boundary_is_ambiguous(
    import_provider: CandidateAImportProvider,
) -> None:
    marker = derive_operation_marker(OPERATION_ID)

    with patch.object(
        import_provider,
        "_branch_names",
        side_effect=ProcessBoundaryError("process boundary"),
    ):
        inspection = import_provider.inspect_marker(marker)

    assert isinstance(inspection, MarkerInspectionAmbiguous)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_marker_oserror_is_ambiguous(
    import_provider: CandidateAImportProvider,
) -> None:
    marker = derive_operation_marker(OPERATION_ID)

    with patch.object(
        import_provider._cli,
        "query_json",
        side_effect=OSError("marker metadata process loss"),
    ):
        inspection = import_provider.inspect_marker(marker)

    assert isinstance(inspection, MarkerInspectionAmbiguous)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_empty_create_or_count_is_typed(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE empty_create (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    original_query_json = import_provider._cli.query_json

    def empty_create_rows(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        if kind == "catalog_create":
            return []
        return original_query_json(kind, sql, revision=revision)

    with patch.object(import_provider._cli, "query_json", side_effect=empty_create_rows):
        with pytest.raises(ImportProviderError, match="catalog_create"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_process_boundary_is_typed(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE catalog_boundary (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "query_json",
        side_effect=ProcessBoundaryError("process boundary"),
    ):
        with pytest.raises(ImportProviderError, match="process boundary"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_generic_candidate_a_error_is_typed(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE generic_error (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "catalog",
        side_effect=CandidateAError("generic neutral failure"),
    ):
        with pytest.raises(ImportProviderError, match="generic neutral failure"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_replay_process_boundary_is_typed(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref = derive_private_ref_name(OPERATION_ID)
    expected = import_provider.read_ref(IMPORT_MAIN_REF)
    import_provider.create_private_ref(private_ref, expected)
    import_provider.checkout_private_ref(private_ref)
    replay_sql = _staging_replay_path(
        import_layout,
        "replay_boundary.sql",
        "CREATE TABLE replay_fault (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=ProcessBoundaryError("process boundary"),
    ):
        with pytest.raises(ImportProviderError, match="process boundary"):
            import_provider.replay_sql(private_ref, replay_sql)

    assert import_provider.read_ref(IMPORT_MAIN_REF) == expected


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_ref_process_boundary_is_typed(
    import_provider: CandidateAImportProvider,
) -> None:
    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=ProcessBoundaryError("process boundary"),
    ):
        with pytest.raises(ImportProviderError, match="process boundary"):
            import_provider.read_ref(IMPORT_MAIN_REF)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_multiple_or_malformed_rows(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE malformed_count (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    original_query_json = import_provider._cli.query_json

    def duplicate_count_rows(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        if kind == "catalog_count":
            return [{"row_count": 1}, {"row_count": 2}]
        return original_query_json(kind, sql, revision=revision)

    with patch.object(import_provider._cli, "query_json", side_effect=duplicate_count_rows):
        with pytest.raises(ImportProviderError, match="catalog_count"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_ref_missing_or_invalid_commit_id(
    import_provider: CandidateAImportProvider,
) -> None:
    original_query_json = import_provider._cli.query_json

    def patched_query_json(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        if kind == "read_ref":
            return []
        return original_query_json(kind, sql, revision=revision)

    with patch.object(import_provider._cli, "query_json", side_effect=patched_query_json):
        with pytest.raises(ImportProviderError, match="read_ref"):
            import_provider.read_ref(IMPORT_MAIN_REF)

    def missing_column_rows(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        if kind == "read_ref":
            return [{}]
        return original_query_json(kind, sql, revision=revision)

    with patch.object(import_provider._cli, "query_json", side_effect=missing_column_rows):
        with pytest.raises(ImportProviderError, match="commit_id"):
            import_provider.read_ref(IMPORT_MAIN_REF)

    def null_commit_rows(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        if kind == "read_ref":
            return [{"commit_id": None}]
        return original_query_json(kind, sql, revision=revision)

    with patch.object(import_provider._cli, "query_json", side_effect=null_commit_rows):
        with pytest.raises(ImportProviderError, match="ref hash"):
            import_provider.read_ref(IMPORT_MAIN_REF)

    def invalid_commit_rows(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        if kind == "read_ref":
            return [{"commit_id": "bad hash!"}]
        return original_query_json(kind, sql, revision=revision)

    with patch.object(import_provider._cli, "query_json", side_effect=invalid_commit_rows):
        with pytest.raises(ImportProviderError, match="invalid"):
            import_provider.read_ref(IMPORT_MAIN_REF)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_publish_main_process_boundary_is_ambiguous(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, expected, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE publish_boundary (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    main_before = import_provider.read_ref(IMPORT_MAIN_REF)

    with patch.object(
        import_provider,
        "_run_runner",
        side_effect=ProcessBoundaryError("publish process boundary"),
    ):
        result = import_provider.publish_main(expected, candidate)

    assert isinstance(result, PublishMainAmbiguous)
    assert import_provider.read_ref(IMPORT_MAIN_REF) == main_before


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_current_branch_process_boundary_is_typed(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref = derive_private_ref_name(OPERATION_ID)
    expected = import_provider.read_ref(IMPORT_MAIN_REF)
    import_provider.create_private_ref(private_ref, expected)
    import_provider.checkout_private_ref(private_ref)
    replay_sql = _staging_replay_path(
        import_layout,
        "branch_boundary.sql",
        "CREATE TABLE branch_fault (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    original_run = import_provider._runner.run

    def failing_current_branch(
        command_kind: str,
        args: list[str],
        *,
        cwd: Path,
        timeout: float,
        stdin_path: Path | None = None,
        capture_stdout: bool = False,
    ) -> CommandResult:
        if command_kind == "current_branch":
            raise ProcessBoundaryError("process boundary")
        return original_run(
            command_kind,
            args,
            cwd=cwd,
            timeout=timeout,
            stdin_path=stdin_path,
            capture_stdout=capture_stdout,
        )

    with patch.object(import_provider._runner, "run", side_effect=failing_current_branch):
        with pytest.raises(ImportProviderError, match="process boundary"):
            import_provider.replay_sql(private_ref, replay_sql)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_empty_count_or_null_count_is_typed(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE empty_count (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    original_query_json = import_provider._cli.query_json

    def empty_count_rows(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        if kind == "catalog_count":
            return []
        return original_query_json(kind, sql, revision=revision)

    with patch.object(import_provider._cli, "query_json", side_effect=empty_count_rows):
        with pytest.raises(ImportProviderError, match="catalog_count"):
            import_provider.read_catalog(candidate)

    def null_count_rows(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        if kind == "catalog_count":
            return [{"row_count": None}]
        return original_query_json(kind, sql, revision=revision)

    with patch.object(import_provider._cli, "query_json", side_effect=null_count_rows):
        with pytest.raises(ImportProviderError, match="invalid catalog_count"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_stream_csv_unicode_and_arrow_faults_are_typed(
    import_provider: CandidateAImportProvider,
) -> None:
    table = TableCatalog(
        "records",
        (ColumnCatalog("id", "BIGINT", False, 0),),
        0,
    )
    candidate = import_provider.read_ref(IMPORT_MAIN_REF)

    def failing_stream(exc: BaseException) -> object:
        def side_effect(*args: object, **kwargs: object) -> Iterator[pa.RecordBatch]:
            def _gen() -> Iterator[pa.RecordBatch]:
                raise exc
                yield pa.record_batch({"id": pa.array([], type=pa.int64())})  # pragma: no cover

            return _gen()

        return side_effect

    with patch.object(
        import_provider._cli,
        "stream_table",
        side_effect=failing_stream(csv.Error("malformed csv")),
    ):
        with pytest.raises(ImportProviderError, match="malformed csv"):
            list(import_provider.stream_table(candidate, table, UnknownTypePolicy.STRINGIFY))

    with patch.object(
        import_provider._cli,
        "stream_table",
        side_effect=failing_stream(UnicodeDecodeError("utf-8", b"", 0, 1, "invalid")),
    ):
        with pytest.raises(ImportProviderError, match="invalid"):
            list(import_provider.stream_table(candidate, table, UnknownTypePolicy.STRINGIFY))

    with patch.object(
        import_provider._cli,
        "stream_table",
        side_effect=failing_stream(UnknownSqlTypeError("unknown SQL type")),
    ):
        with pytest.raises(ImportProviderError, match="unknown SQL type"):
            list(import_provider.stream_table(candidate, table, UnknownTypePolicy.STRINGIFY))


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_concurrent_streams_with_over_128k_field(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    payload_len = 140000
    private_ref = derive_private_ref_name(OPERATION_ID)
    marker = derive_operation_marker(OPERATION_ID)
    expected = import_provider.read_ref(IMPORT_MAIN_REF)
    import_provider.create_private_ref(private_ref, expected)
    import_provider.checkout_private_ref(private_ref)
    import_provider.replay_sql(
        private_ref,
        _staging_replay_path(
            import_layout,
            "stream_large_create.sql",
            "CREATE TABLE stream_large (payload LONGTEXT NOT NULL, id BIGINT NOT NULL PRIMARY KEY);\n"
            "INSERT INTO stream_large VALUES ('', 1);\n",
        ),
    )
    for index in range(14):
        import_provider.replay_sql(
            private_ref,
            _staging_replay_path(
                import_layout,
                f"stream_large_fill_{index}.sql",
                "UPDATE stream_large SET payload = CONCAT(payload, REPEAT('x', 10000)) WHERE id = 1;\n",
            ),
        )
    candidate = import_provider.commit_operation_marker(private_ref, marker)
    table = TableCatalog(
        "stream_large",
        (
            ColumnCatalog("payload", "LONGTEXT", False, None),
            ColumnCatalog("id", "BIGINT", False, 0),
        ),
        1,
    )
    default_limit = 131072
    assert csv.field_size_limit() >= import_provider._settings.max_stream_line_bytes
    assert payload_len > default_limit

    recorded_limits: list[int] = []
    lock = threading.Lock()
    original_stream_table = import_provider._cli.stream_table

    def recording_stream(
        commit_id: str,
        table: TableCatalog,
        policy: ArrowUnknownTypePolicy,
    ) -> Iterator[pa.RecordBatch]:
        with lock:
            recorded_limits.append(csv.field_size_limit())
        return original_stream_table(commit_id, table, policy)

    errors: list[BaseException] = []

    def consume() -> None:
        try:
            with patch.object(import_provider._cli, "stream_table", side_effect=recording_stream):
                batches = list(
                    import_provider.stream_table(candidate, table, UnknownTypePolicy.STRINGIFY)
                )
                assert batches
                assert len(batches[0]["payload"][0].as_py()) == payload_len
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=consume), threading.Thread(target=consume)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert recorded_limits
    assert all(
        limit >= import_provider._settings.max_stream_line_bytes for limit in recorded_limits
    )
    import_provider.checkout_private_ref(private_ref)
    import_provider.delete_private_ref(private_ref, expected_candidate=candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_stream_timeout_is_typed(
    import_provider: CandidateAImportProvider,
) -> None:
    table = TableCatalog(
        "records",
        (ColumnCatalog("id", "BIGINT", False, 0),),
        0,
    )
    candidate = import_provider.read_ref(IMPORT_MAIN_REF)

    def timeout_stream(*args: object, **kwargs: object) -> Iterator[pa.RecordBatch]:
        def _gen() -> Iterator[pa.RecordBatch]:
            raise TimeoutError("row_stream exceeded timeout")
            yield pa.record_batch({"id": pa.array([], type=pa.int64())})  # pragma: no cover

        return _gen()

    with patch.object(import_provider._cli, "stream_table", side_effect=timeout_stream):
        with pytest.raises(ImportProviderError, match="timeout"):
            list(import_provider.stream_table(candidate, table, UnknownTypePolicy.STRINGIFY))


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_publish_oserror_is_ambiguous(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, expected, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE publish_os (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    main_before = import_provider.read_ref(IMPORT_MAIN_REF)

    with patch.object(
        import_provider._runner,
        "run",
        side_effect=FileNotFoundError("dolt disappeared"),
    ):
        result = import_provider.publish_main(expected, candidate)

    assert isinstance(result, PublishMainAmbiguous)
    assert import_provider.read_ref(IMPORT_MAIN_REF) == main_before


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_arrow_type_error_is_typed(
    import_provider: CandidateAImportProvider,
) -> None:
    table = TableCatalog(
        "records",
        (ColumnCatalog("id", "BIGINT", False, 0),),
        0,
    )
    candidate = import_provider.read_ref(IMPORT_MAIN_REF)

    def arrow_fault_stream(*args: object, **kwargs: object) -> Iterator[pa.RecordBatch]:
        def _gen() -> Iterator[pa.RecordBatch]:
            raise pa.ArrowTypeError("arrow conversion shape")
            yield pa.record_batch({"id": pa.array([], type=pa.int64())})  # pragma: no cover

        return _gen()

    with patch.object(import_provider._cli, "stream_table", side_effect=arrow_fault_stream):
        with pytest.raises(ImportProviderError, match="arrow conversion"):
            list(import_provider.stream_table(candidate, table, UnknownTypePolicy.STRINGIFY))


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_stream_timeout_closes_once(
    import_provider: CandidateAImportProvider,
) -> None:
    table = TableCatalog(
        "records",
        (ColumnCatalog("id", "BIGINT", False, 0),),
        0,
    )
    candidate = import_provider.read_ref(IMPORT_MAIN_REF)
    stream = MagicMock()
    stream.__iter__ = MagicMock(side_effect=TimeoutError("row_stream exceeded timeout"))
    stream.close.return_value = CommandResult(
        command_kind="row_stream",
        exit_code=0,
        duration_seconds=0.0,
        stdout=b"",
        stdout_tail=b"",
        stderr_tail=b"",
        timed_out=False,
    )

    with patch.object(import_provider._cli.runner, "stream", return_value=stream):
        with pytest.raises(TimeoutError, match="timeout"):
            list(
                import_provider._cli.stream_table(
                    candidate,
                    table,
                    ArrowUnknownTypePolicy.STRINGIFY,
                )
            )

    assert stream.close.call_count == 1


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_catalog_duplicate_parent_rows(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE dup_parent (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    original_query_json = import_provider._cli.query_json

    def duplicate_parent_rows(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        if kind == "candidate_parent":
            return [{"parents": "parent1"}, {"parents": "parent2"}]
        return original_query_json(kind, sql, revision=revision)

    with patch.object(import_provider._cli, "query_json", side_effect=duplicate_parent_rows):
        with pytest.raises(ImportProviderError, match="candidate_parent"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_row_count_rejects_malformed_scalar(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE bad_count (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    original_query_json = import_provider._cli.query_json

    for raw_count in (-1, 1.5, True):
        def malformed_count_rows(
            kind: str,
            sql: str,
            *,
            revision: str | None = None,
        ) -> list[dict[str, object]]:
            if kind == "catalog_count":
                return [{"row_count": raw_count}]
            return original_query_json(kind, sql, revision=revision)

        with patch.object(
            import_provider._cli,
            "query_json",
            side_effect=malformed_count_rows,
        ):
            with pytest.raises(ImportProviderError, match="invalid catalog_count"):
                import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_ref_rejects_whitespace_commit_id(
    import_provider: CandidateAImportProvider,
) -> None:
    original_query_json = import_provider._cli.query_json

    def whitespace_commit_rows(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        if kind == "read_ref":
            return [{"commit_id": " abc "}]
        return original_query_json(kind, sql, revision=revision)

    with patch.object(import_provider._cli, "query_json", side_effect=whitespace_commit_rows):
        with pytest.raises(ImportProviderError, match="invalid"):
            import_provider.read_ref(IMPORT_MAIN_REF)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
@pytest.mark.parametrize(("stdout", "match"), MALFORMED_JSON_SHAPES)
def test_read_ref_malformed_json_metadata_is_typed(
    import_provider: CandidateAImportProvider,
    stdout: bytes,
    match: str,
) -> None:
    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            stdout,
            kinds=frozenset({"read_ref"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match=match):
            import_provider.read_ref(IMPORT_MAIN_REF)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
@pytest.mark.parametrize(("stdout", "match"), MALFORMED_JSON_SHAPES)
def test_read_catalog_malformed_json_metadata_is_typed(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
    stdout: bytes,
    match: str,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE json_catalog (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            stdout,
            kinds=frozenset({"candidate_parent"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match=match):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
@pytest.mark.parametrize(("stdout", "match"), MARKER_FAULT_JSON_SHAPES)
def test_inspect_marker_malformed_json_metadata_is_ambiguous(
    import_provider: CandidateAImportProvider,
    stdout: bytes,
    match: str,
) -> None:
    marker = derive_operation_marker(OPERATION_ID)

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            stdout,
            kinds=frozenset({"marker_scan"}),
        ),
    ):
        inspection = import_provider.inspect_marker(marker)

    assert isinstance(inspection, MarkerInspectionAmbiguous)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
@pytest.mark.parametrize(("stdout", "match"), MARKER_FAULT_JSON_SHAPES)
def test_publish_main_malformed_json_read_is_ambiguous(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
    stdout: bytes,
    match: str,
) -> None:
    _, _, expected, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE json_publish (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            stdout,
            kinds=frozenset({"read_ref"}),
        ),
    ):
        result = import_provider.publish_main(expected, candidate)

    assert isinstance(result, PublishMainAmbiguous)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_tables_rejects_non_list_row(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE json_tables (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    stdout = (
        b'{"rows":[["t1","BASE TABLE"], {"x": 1}], '
        b'"columns":[{"name":"Tables_in_db"},{"name":"Table_type"}]}'
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            stdout,
            kinds=frozenset({"catalog_tables"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="Dolt JSON row was not a list"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_tables_rejects_non_list_columns_even_when_empty(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE json_columns (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rows":[],"columns":"bad"}',
            kinds=frozenset({"catalog_tables"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="Dolt JSON columns was not a list"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
@pytest.mark.parametrize(
    "stdout",
    (
        b'{"rows":[[1]], "columns":[{"name":"row_count"},{"name":"extra"}]}',
        b'{"rows":[[1,2]], "columns":[{"name":"row_count"}]}',
    ),
)
def test_catalog_json_rejects_extra_or_missing_cells(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
    stdout: bytes,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE json_width (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            stdout,
            kinds=frozenset({"catalog_count"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="row width does not match columns"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_count_rejects_extra_cell(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE json_extra_cell (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rows":[[1,2]], "columns":[{"name":"row_count"}]}',
            kinds=frozenset({"catalog_count"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="row width does not match columns"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_count_rejects_extra_field_real_dolt_shape(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE json_object_extra (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rows":[{"row_count":1,"extra":999}]}',
            kinds=frozenset({"catalog_count"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="row schema mismatch"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_scalar_metadata_rejects_positional_multi_cell_row(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE json_positional (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rows":[[1,999]]}',
            kinds=frozenset({"catalog_count"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="row was not an object"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
@pytest.mark.parametrize(
    ("stdout", "kind", "action"),
    (
        (
            b'{"rows":[{"commit_id":"deadbeef","extra":1}]}',
            "read_ref",
            "read_ref",
        ),
        (
            b'{"rows":[{"parents":"deadbeef","extra":1}]}',
            "candidate_parent",
            "read_catalog",
        ),
    ),
)
def test_read_ref_and_candidate_parent_reject_extra_fields(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
    stdout: bytes,
    kind: str,
    action: str,
) -> None:
    if action == "read_catalog":
        _, _, _, candidate = _candidate_on_private_ref(
            import_provider,
            import_layout,
            table_sql="CREATE TABLE json_parent_extra (id BIGINT NOT NULL PRIMARY KEY);\n",
        )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            stdout,
            kinds=frozenset({kind}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="row schema mismatch"):
            if action == "read_ref":
                import_provider.read_ref(IMPORT_MAIN_REF)
            else:
                import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
@pytest.mark.parametrize(
    ("stdout", "kind", "match"),
    (
        (
            b'{"rows":[{"Tables_in_import-repo":"json_show","Table_type":"BASE TABLE","extra":1}]}',
            "catalog_tables",
            "row schema mismatch",
        ),
        (
            b'{"rows":[{"Table":"json_show","Create Table":"CREATE TABLE json_show","extra":1}]}',
            "catalog_create",
            "row schema mismatch",
        ),
        (
            b'{"rows":[{"Table":"wrong_table","Create Table":"CREATE TABLE json_show"}]}',
            "catalog_create",
            "mismatched table name",
        ),
    ),
)
def test_catalog_show_rows_require_exact_schema(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
    stdout: bytes,
    kind: str,
    match: str,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE json_show (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            stdout,
            kinds=frozenset({kind}),
        ),
    ):
        with pytest.raises(ImportProviderError, match=match):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_tables_rejects_broken_table_type(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE broken_type (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rows":[{"Tables_in_import-repo":"hidden_table","Table_type":"BROKEN"}]}',
            kinds=frozenset({"catalog_tables"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="Table_type is not recognized"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_count_rejects_case_colliding_keys(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE case_collision (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rows":[{"ROW_COUNT":1,"row_count":2}]}',
            kinds=frozenset({"catalog_count"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="duplicate column names"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_metadata_json_rejects_duplicate_keys(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE dup_keys (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rows":[{"row_count":1,"row_count":2}]}',
            kinds=frozenset({"catalog_count"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="duplicate keys"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_inspect_marker_null_message_is_ambiguous(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref, marker, _, _ = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE null_message (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    original_query_json = import_provider._cli.query_json

    def null_message_log(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        rows = original_query_json(kind, sql, revision=revision)
        if kind == "marker_scan" and revision == private_ref:
            rows[0]["message"] = None
        return rows

    with patch.object(import_provider._cli, "query_json", side_effect=null_message_log):
        inspection = import_provider.inspect_marker(marker)

    assert isinstance(inspection, MarkerInspectionAmbiguous)
    assert not isinstance(inspection, MarkerInspectionZero)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_inspect_marker_null_ref_name_is_ambiguous(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, marker, _, _ = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE null_ref (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rows":[{"name":null}]}',
            kinds=frozenset({"refs_for_commit"}),
        ),
    ):
        inspection = import_provider.inspect_marker(marker)

    assert isinstance(inspection, MarkerInspectionAmbiguous)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_inspect_marker_extra_field_is_ambiguous(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, marker, _, _ = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE marker_extra (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rows":[{"commit_hash":"deadbeef","message":"ignored","parents":"parent","extra":1}]}',
            kinds=frozenset({"marker_scan"}),
        ),
    ):
        inspection = import_provider.inspect_marker(marker)

    assert isinstance(inspection, MarkerInspectionAmbiguous)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_metadata_rejects_unknown_envelope_fields(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE envelope_extra (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rows":[{"row_count":1}],"error":"warn"}',
            kinds=frozenset({"catalog_count"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="envelope mismatch"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_metadata_rejects_rowdata_fallback(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE rowdata_fallback (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rowData":[{"row_count":1}]}',
            kinds=frozenset({"catalog_count"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="envelope was not recognized"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("commit_hash", " deadbeef "),
        ("parents", " deadbeef "),
    ),
)
def test_inspect_marker_rejects_whitespace_evidence(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
    field: str,
    value: str,
) -> None:
    private_ref, marker, _, _ = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE whitespace_evidence (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    original_query_json = import_provider._cli.query_json

    def whitespace_log(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
    ) -> list[dict[str, object]]:
        rows = original_query_json(kind, sql, revision=revision)
        if kind == "marker_scan" and revision == private_ref:
            for row in rows:
                if row.get("message") == marker:
                    row[field] = value
                    break
        return rows

    with patch.object(import_provider._cli, "query_json", side_effect=whitespace_log):
        inspection = import_provider.inspect_marker(marker)

    assert isinstance(inspection, MarkerInspectionAmbiguous)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_inspect_marker_rejects_whitespace_ref_name(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, marker, _, _ = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE whitespace_ref (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rows":[{"name":" main "}]}',
            kinds=frozenset({"refs_for_commit"}),
        ),
    ):
        inspection = import_provider.inspect_marker(marker)

    assert isinstance(inspection, MarkerInspectionAmbiguous)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_inspect_marker_rejects_duplicate_refs(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, marker, _, _ = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE duplicate_refs (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rows":[{"name":"main"},{"name":"main"}]}',
            kinds=frozenset({"refs_for_commit"}),
        ),
    ):
        inspection = import_provider.inspect_marker(marker)

    assert isinstance(inspection, MarkerInspectionAmbiguous)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_catalog_rejects_whitespace_parent(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE whitespace_parent (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rows":[{"parents":" deadbeef "}]}',
            kinds=frozenset({"candidate_parent"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="candidate parent"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_tables_empty_structured_rejects_wrong_columns(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE empty_tables_schema (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rows":[],"columns":[{"name":"not_table_type"},{"name":"Tables_in_db"}]}',
            kinds=frozenset({"catalog_tables"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="envelope column schema"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_ref_empty_structured_rejects_wrong_columns(
    import_provider: CandidateAImportProvider,
) -> None:
    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rows":[],"columns":[{"name":"not_commit_id"}]}',
            kinds=frozenset({"read_ref"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="envelope column schema"):
            import_provider.read_ref(IMPORT_MAIN_REF)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_candidate_parent_empty_structured_rejects_wrong_columns(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE empty_parent_schema (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rows":[],"columns":[{"name":"not_parents"}]}',
            kinds=frozenset({"candidate_parent"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="envelope column schema"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_metadata_empty_structured_rejects_column_collision(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE empty_column_collision (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            b'{"rows":[],"columns":[{"name":"ROW_COUNT"},{"name":"row_count"}]}',
            kinds=frozenset({"catalog_count"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="duplicate column names"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
@pytest.mark.parametrize(
    "stdout",
    (
        b'{"rows":[{"Table_type":"BASE TABLE","Tables_in":"t"}]}',
        b'{"rows":[],"columns":[{"name":"Table_type"},{"name":"Tables_in_"}]}',
        b'{"rows":[],"columns":[{"name":"Table_type"},{"name":"Tables_inside"}]}',
        b'{"rows":[],"columns":[{"name":"Table_type"},{"name":"Tables_index"}]}',
    ),
)
def test_catalog_tables_rejects_invalid_tables_in_prefix(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
    stdout: bytes,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE bad_tables_prefix (id BIGINT NOT NULL PRIMARY KEY);\n",
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            stdout,
            kinds=frozenset({"catalog_tables"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="Tables_in_"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_catalog_preserves_leading_space_table_name(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE ` leading` (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    names = {table.name for table in import_provider.read_catalog(candidate)}
    assert " leading" in names


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_catalog_preserves_embedded_space_table_name(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE `embedded space` (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    names = {table.name for table in import_provider.read_catalog(candidate)}
    assert "embedded space" in names


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_tables_rejects_duplicate_object_rows(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE duplicate_source (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    stdout = (
        b'[{"Tables_in_import-repo":"duplicate_source","Table_type":"BASE TABLE"},'
        b' {"Tables_in_import-repo":"duplicate_source","Table_type":"BASE TABLE"}]'
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            stdout,
            kinds=frozenset({"catalog_tables"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="duplicate table names"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_tables_rejects_duplicate_structured_rows(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE duplicate_source (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    stdout = (
        b'{"rows":[["duplicate_source","BASE TABLE"],["duplicate_source","BASE TABLE"]],'
        b'"columns":[{"name":"Tables_in_import-repo"},{"name":"Table_type"}]}'
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            stdout,
            kinds=frozenset({"catalog_tables"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="duplicate table names"):
            import_provider.read_catalog(candidate)


@pytest.mark.parametrize(
    ("ddl", "match"),
    (
        ("CREATE TABLE t (`id` BIGINT, `id` BIGINT);", "duplicate column names"),
        ("CREATE TABLE t (`id` BIGINT, PRIMARY KEY (`missing`));", "references unknown column"),
        ("CREATE TABLE t (`id` BIGINT, PRIMARY KEY (`id`, `id`));", "primary key has duplicate"),
    ),
)
def test_parse_create_statement_rejects_invalid_schema_invariants(ddl: str, match: str) -> None:
    with pytest.raises(ProviderError, match=match):
        _parse_create_statement(ddl, 0)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_catalog_rejects_duplicate_column_ddl(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE valid_target (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    stdout = (
        b'{"rows":[{"Table":"valid_target",'
        b'"Create Table":"CREATE TABLE `valid_target` (`id` BIGINT, `id` BIGINT);"}]}'
    )

    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            stdout,
            kinds=frozenset({"catalog_create"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="duplicate column names"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_commit_operation_marker_allows_empty_replay(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref = derive_private_ref_name(OPERATION_ID)
    marker = derive_operation_marker(OPERATION_ID)
    expected = import_provider.read_ref("main")
    import_provider.create_private_ref(private_ref, expected)
    import_provider.checkout_private_ref(private_ref)
    import_provider.replay_sql(
        private_ref,
        _staging_replay_path(import_layout, "empty.sql", ""),
    )
    before = import_provider.read_ref(private_ref)
    candidate = import_provider.commit_operation_marker(private_ref, marker)
    assert candidate != before
    inspection = import_provider.inspect_marker(marker)
    assert isinstance(inspection, MarkerInspectionUnique)
    assert inspection.parent == expected
    assert inspection.candidate == candidate


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_commit_operation_marker_allows_select_one_replay(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    private_ref = derive_private_ref_name(OPERATION_ID)
    marker = derive_operation_marker(OPERATION_ID)
    expected = import_provider.read_ref("main")
    import_provider.create_private_ref(private_ref, expected)
    import_provider.checkout_private_ref(private_ref)
    import_provider.replay_sql(
        private_ref,
        _staging_replay_path(import_layout, "select_one.sql", "SELECT 1;\n"),
    )
    before = import_provider.read_ref(private_ref)
    candidate = import_provider.commit_operation_marker(private_ref, marker)
    assert candidate != before
    inspection = import_provider.inspect_marker(marker)
    assert isinstance(inspection, MarkerInspectionUnique)
    assert inspection.parent == expected


def test_parse_create_statement_accepts_spaced_pk_column_names() -> None:
    table = _parse_create_statement(
        "CREATE TABLE t (`leading id` BIGINT NOT NULL, PRIMARY KEY (`leading id`));",
        0,
    )
    assert [column.name for column in table.columns] == ["leading id"]
    assert table.primary_key == ("leading id",)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_catalog_accepts_spaced_primary_key_column_name(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql=(
            "CREATE TABLE spaced_pk ("
            "`embedded id` BIGINT NOT NULL, PRIMARY KEY (`embedded id`));\n"
        ),
    )
    catalog = import_provider.read_catalog(candidate)
    assert len(catalog) == 1
    assert [column.name for column in catalog[0].columns] == ["embedded id"]
    assert catalog[0].primary_key == ("embedded id",)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_catalog_fulltext_index_not_projected_as_column(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql=(
            "CREATE TABLE ft_body (BODY TEXT, FULLTEXT KEY FT_BODY (BODY));\n"
        ),
    )
    catalog = import_provider.read_catalog(candidate)
    assert len(catalog) == 1
    assert [column.name for column in catalog[0].columns] == ["BODY"]


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_catalog_spatial_index_not_projected_as_column(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql=(
            "CREATE TABLE geom_table (GEOM GEOMETRY NOT NULL, "
            "SPATIAL KEY SP_GEOM (GEOM));\n"
        ),
    )
    catalog = import_provider.read_catalog(candidate)
    assert len(catalog) == 1
    assert [column.name for column in catalog[0].columns] == ["GEOM"]


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_catalog_generated_column_preserves_bigint_type(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql=(
            "CREATE TABLE gen_col (base BIGINT NOT NULL, "
            "derived BIGINT GENERATED ALWAYS AS (base + 1) STORED);\n"
        ),
    )
    catalog = import_provider.read_catalog(candidate)
    assert len(catalog) == 1
    columns = {column.name: column.sql_type for column in catalog[0].columns}
    assert columns["base"] == "BIGINT"
    assert columns["derived"] == "BIGINT"


@pytest.mark.parametrize(
    ("ddl", "match"),
    (
        ("garbage CREATE TABLE t (`id` BIGINT);", "CREATE TABLE"),
        ("CREATE TABLE t (`id` BIGINT));", "unsupported table options"),
        ("CREATE TABLE t (`id` BIGINT,);", "malformed"),
        ("CREATE TABLE t ();", "no columns"),
        ("CREATE TABLE t (`id` BIGINT, PRIMARY KEY ());", "primary key is empty"),
        ("CREATE TABLE t (`id` BIGINT) ENGINE=InnoDB garbage;", "unsupported table options"),
    ),
)
def test_parse_create_statement_rejects_malformed_ddl(ddl: str, match: str) -> None:
    with pytest.raises(ProviderError, match=match):
        _parse_create_statement(ddl, 0)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_catalog_rejects_prefix_garbage_ddl(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE valid_target (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    stdout = (
        b'{"rows":[{"Table":"valid_target",'
        b'"Create Table":"garbage CREATE TABLE `valid_target` (`id` BIGINT);"}]}'
    )
    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            stdout,
            kinds=frozenset({"catalog_create"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="CREATE TABLE"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_read_catalog_rejects_ddl_table_name_mismatch(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE valid_target (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    stdout = (
        b'{"rows":[{"Table":"valid_target",'
        b'"Create Table":"CREATE TABLE `other_target` (`id` BIGINT);"}]}'
    )
    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            stdout,
            kinds=frozenset({"catalog_create"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="DDL table name mismatch"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
@pytest.mark.parametrize(
    "stdout",
    (
        b'{"rows":[{"Table":1,"Create Table":"CREATE TABLE `1` (`id` BIGINT);"}]}',
        b'[{"Table":1,"Create Table":"CREATE TABLE `1` (`id` BIGINT);"}]',
    ),
)
def test_catalog_create_rejects_non_string_table_field(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
    stdout: bytes,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE json_show (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            stdout,
            kinds=frozenset({"catalog_create"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="Table column is missing or invalid"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_tables_rejects_conflicting_column_descriptor_aliases(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE alias_probe (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    stdout = b'{"rows":[],"columns":[{"name":"Table_type","Name":"wrong"}]}'
    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            stdout,
            kinds=frozenset({"catalog_tables"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="conflicting name aliases"):
            import_provider.read_catalog(candidate)


@pytest.mark.skipif(not dolt_available(), reason="dolt executable is unavailable")
def test_catalog_count_rejects_descriptor_case_collision_keys(
    import_layout: DurableLayout,
    import_provider: CandidateAImportProvider,
) -> None:
    _, _, _, candidate = _candidate_on_private_ref(
        import_provider,
        import_layout,
        table_sql="CREATE TABLE descriptor_collision (id BIGINT NOT NULL PRIMARY KEY);\n",
    )
    stdout = b'{"rows":[],"columns":[{"name":"row_count","NAME":"wrong"}]}'
    with patch.object(
        import_provider._cli,
        "run_cli",
        side_effect=_run_cli_malformed_json_side_effect(
            import_provider,
            stdout,
            kinds=frozenset({"catalog_count"}),
        ),
    ):
        with pytest.raises(ImportProviderError, match="duplicate keys"):
            import_provider.read_catalog(candidate)
