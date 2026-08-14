"""Tests for commit-pinned Candidate A read provider and application."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from collections.abc import Iterator
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from gateway_repository_contracts import UnknownTypePolicy
from gateway_repository_service.arrow_mapping import (
    ColumnCatalog,
    CompiledTablePlan,
    TableCatalog,
    compile_table_plan,
)
from gateway_repository_service.candidate_a.dolt_cli import (
    CandidateADoltCli,
    DoltCliError,
    _CATALOG_MEMO_ENTRIES,
    parse_commit_exists_rows,
    value,
)
from gateway_repository_service.candidate_a.errors import DoltCliStreamCancelledError
from gateway_repository_service.candidate_a.ref_validation import (
    opaque_commit_literal,
    validate_commit_id,
)
from gateway_repository_service.candidate_a.sql import _tagged_select_list, quote_identifier
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.mutation_fingerprints import create_repository_fingerprint_v1
from gateway_repository_service.mutation_store import (
    IdempotencyScope,
    MutationStore,
    configure_connection,
)
from gateway_repository_service.process import CommandResult, DoltRunner, ProcessStreamCancelledError, StreamCancellationCheck
from gateway_repository_service.providers import OfflineCliProvider
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.versioned_read.application import VersionedReadApplication
from gateway_repository_service.versioned_read.errors import (
    CommitNotFoundError,
    MainRefNotFoundError,
    ProviderUnavailableError,
    ReadStreamCancelledError,
    RepositoryNotVisibleError,
    TableNotFoundError,
    VersionedReadError,
)
from gateway_repository_service.versioned_read.provider import CandidateAReadProvider, _as_provider_unavailable
from support.lifecycle_harness import lifecycle_settings

ReadRepoFixture = tuple[
    DurableLayout,
    RepositoryServiceSettings,
    DoltRunner,
    CandidateAReadProvider,
    OfflineCliProvider,
]


@pytest.mark.parametrize(
    "token",
    (
        "not-a-dolt-hash'; DROP TABLE t; --",
        r"x\'; CREATE TABLE injected(id INT); --",
        r"back\slash-token",
        "plain'quote",
        "opaque-token",
        "a" * 128,
        "é",
        "Ā",
        "中文",
        "𐀀",
    ),
)
def test_opaque_commit_literal_encodes_without_provider_grammar(token: str) -> None:
    literal = opaque_commit_literal(token)
    if token == "":
        assert literal == "''"
    else:
        byte_codes = ",".join(str(byte) for byte in token.encode("utf-8"))
        assert literal == f"CONCAT(CHAR({byte_codes}))"
        for code in token.encode("utf-8"):
            assert 0 <= code <= 255
    assert ";" not in literal
    assert "\\" not in literal
    assert "'" not in literal
    if token == "not-a-dolt-hash'; DROP TABLE t; --":
        with pytest.raises(ValueError, match="commit id is invalid"):
            validate_commit_id(token)


@pytest.mark.parametrize(
    ("rows", "commit_id", "expected", "match"),
    (
        ([], "abc", False, None),
        (
            [{"commit_hash": "abc"}],
            "abc",
            True,
            None,
        ),
        (
            [{"commit_hash": "abc"}, {"commit_hash": "abc"}],
            "abc",
            None,
            "expected 0 or 1",
        ),
        (
            [{"commit_hash": ""}],
            "abc",
            None,
            "missing or invalid",
        ),
        (
            [{"commit_hash": "other"}],
            "abc",
            None,
            "mismatch",
        ),
    ),
)
def test_parse_commit_exists_rows_matrix(
    rows: list[dict[str, Any]],
    commit_id: str,
    expected: bool | None,
    match: str | None,
) -> None:
    if match is None:
        assert parse_commit_exists_rows(rows, commit_id) is expected
    else:
        with pytest.raises(DoltCliError, match=match):
            parse_commit_exists_rows(rows, commit_id)


def test_catalog_at_does_not_query_parent(tmp_path: Path) -> None:
    layout = DurableLayout.create(tmp_path / "root")
    settings = RepositoryServiceSettings()
    repository = layout.staging_artifacts / "repo"
    repository.mkdir(parents=True, exist_ok=True)
    runner = MagicMock(spec=DoltRunner)
    cli = CandidateADoltCli(settings, layout, repository, runner)
    target = "opaque-token-1"
    captured: list[str] = []

    def query_json(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
        cancellation: StreamCancellationCheck | None = None,
        call_timeout: Any | None = None,
    ) -> list[dict[str, Any]]:
        del revision, cancellation, call_timeout
        captured.append(sql)
        if kind == "catalog_tables":
            return []
        raise AssertionError(f"unexpected query kind {kind}")

    with patch.object(cli, "query_json", side_effect=query_json):
        catalog = cli.catalog_at(target)

    assert catalog == ()
    assert captured == [f"SHOW FULL TABLES AS OF {opaque_commit_literal(target)};\n"]
    assert "parents" not in captured[0]


def test_catalog_at_binds_same_literal_for_schema_and_count(tmp_path: Path) -> None:
    layout = DurableLayout.create(tmp_path / "root")
    settings = RepositoryServiceSettings()
    repository = layout.staging_artifacts / "repo"
    repository.mkdir(parents=True, exist_ok=True)
    runner = MagicMock(spec=DoltRunner)
    cli = CandidateADoltCli(settings, layout, repository, runner)
    target = "token-with spaces"
    literal = opaque_commit_literal(target)
    table = TableCatalog(
        "My Table",
        (
            ColumnCatalog(
                name="id",
                sql_type="BIGINT",
                nullable=False,
                primary_key_position=1,
            ),
        ),
        row_count=1,
    )

    captured_sql: list[str] = []

    def query_json(
        kind: str,
        sql: str,
        *,
        revision: str | None = None,
        cancellation: StreamCancellationCheck | None = None,
        call_timeout: Any | None = None,
    ) -> list[dict[str, Any]]:
        del revision, cancellation, call_timeout
        if kind == "catalog_tables":
            return [
                {
                    "Tables_in_repo": "My Table",
                    "Table_type": "BASE TABLE",
                }
            ]
        if kind == "catalog_create":
            captured_sql.append(sql)
            assert literal in sql
            return [
                {
                    "Table": "My Table",
                    "Create Table": (
                        "CREATE TABLE `My Table` ("
                        "`id` BIGINT NOT NULL, PRIMARY KEY (`id`)"
                        ")"
                    ),
                }
            ]
        if kind == "catalog_count":
            assert literal in sql
            return [{"row_count": 1}]
        raise AssertionError(kind)

    with patch.object(cli, "query_json", side_effect=query_json):
        catalog = cli.catalog_at(target)

    assert catalog == (table,)
    assert quote_identifier("My Table") in captured_sql[0]


def _open_mutation_store(tmp_path: Path) -> MutationStore:
    db_path = tmp_path / "service-state" / "repository-service.sqlite3"
    control_store = ControlStore.open(db_path, expected_version=CONTROL_DB_USER_VERSION, busy_timeout_ms=1000)
    control_store.close()
    connection = sqlite3.connect(db_path)
    configure_connection(connection)
    return MutationStore(connection)


def _visible_repository_setup(
    tmp_path: Path,
) -> tuple[MutationStore, DurableLayout, UUID]:
    settings = lifecycle_settings(tmp_path)
    store = _open_mutation_store(tmp_path)
    layout = DurableLayout.create(settings.data_root)
    repository_id = uuid4()
    scope = IdempotencyScope.for_create()
    key_hash = MutationStore.hash_idempotency_key("read-visible")
    fingerprint = create_repository_fingerprint_v1()
    store.claim_or_lookup(scope, key_hash=key_hash, fingerprint=fingerprint)
    effect = store.allocate_pending(
        scope,
        key_hash=key_hash,
        fingerprint=fingerprint,
        resource_id=repository_id,
    )
    store.mark_succeeded(
        effect.effect_id,
        response_body={
            "repository_id": str(repository_id),
            "default_ref": "main",
            "initial_commit_id": "abc",
        },
    )
    published = layout.published_repository(repository_key(repository_id))
    published.mkdir(parents=True)
    (published / ".dolt").mkdir()
    return store, layout, repository_id


def test_versioned_read_application_rejects_non_main_ref(tmp_path: Path) -> None:
    store, layout, repository_id = _visible_repository_setup(tmp_path)
    provider = MagicMock(spec=CandidateAReadProvider)
    provider.read_ref.side_effect = MainRefNotFoundError("versioned read ref is not supported")

    app = VersionedReadApplication(
        store,
        layout,
        lambda _repository_id: provider,
    )
    with pytest.raises(MainRefNotFoundError):
        app.resolve_main(repository_id)


def test_versioned_read_application_short_circuits_invisible_repository(tmp_path: Path) -> None:
    repository_id = uuid4()
    store = _open_mutation_store(tmp_path)
    layout = DurableLayout.create(tmp_path / "root")
    factory_called = False

    def factory(_repository_id: UUID) -> CandidateAReadProvider:
        nonlocal factory_called
        factory_called = True
        raise AssertionError("provider factory should not run")

    app = VersionedReadApplication(store, layout, factory)
    with pytest.raises(RepositoryNotVisibleError):
        app.get_catalog(repository_id, "opaque-commit")
    assert factory_called is False


def test_open_table_rows_exact_lookup_and_single_plan(tmp_path: Path) -> None:
    store, layout, repository_id = _visible_repository_setup(tmp_path)
    table = TableCatalog(
        "Records",
        (
            ColumnCatalog(
                name="id",
                sql_type="BIGINT",
                nullable=False,
                primary_key_position=1,
            ),
        ),
        row_count=0,
    )
    provider = MagicMock(spec=CandidateAReadProvider)
    provider.commit_exists.return_value = True
    provider.catalog_at.return_value = (table,)
    compile_calls: list[tuple[TableCatalog, UnknownTypePolicy]] = []
    original_compile = compile_table_plan

    def spy_compile(catalog: TableCatalog, policy: UnknownTypePolicy) -> CompiledTablePlan:
        compile_calls.append((catalog, policy))
        return original_compile(catalog, policy)

    received_plan: list[CompiledTablePlan | None] = []

    def stream_table_at(
        commit_id: str,
        catalog: TableCatalog,
        policy: UnknownTypePolicy,
        *,
        table_plan: CompiledTablePlan | None = None,
        cancellation: object = None,
        existence_verified: bool = False,
        stream_owner: object | None = None,
    ) -> list[pa.RecordBatch]:
        del commit_id, catalog, policy, cancellation, stream_owner
        assert existence_verified is True
        received_plan.append(table_plan)
        return []

    provider.stream_table_at.side_effect = stream_table_at

    app = VersionedReadApplication(store, layout, lambda _repository_id: provider)
    with patch("gateway_repository_service.versioned_read.application.compile_table_plan", side_effect=spy_compile):
        plan, rows = app.open_table_rows(
            repository_id,
            "opaque-commit",
            "Records",
            UnknownTypePolicy.REJECT,
        )
    list(rows)
    assert len(compile_calls) == 1
    assert received_plan == [plan]
    provider.catalog_at.assert_called_once_with("opaque-commit", existence_verified=True)
    assert provider.commit_exists.call_count == 1
    with pytest.raises(TableNotFoundError):
        app.open_table_rows(repository_id, "opaque-commit", "records", UnknownTypePolicy.REJECT)


def test_open_table_rows_commit_exists_called_once(tmp_path: Path) -> None:
    store, layout, repository_id = _visible_repository_setup(tmp_path)
    table = TableCatalog(
        "Records",
        (
            ColumnCatalog(
                name="id",
                sql_type="BIGINT",
                nullable=False,
                primary_key_position=1,
            ),
        ),
        row_count=0,
    )
    read_provider = MagicMock(spec=CandidateAReadProvider)
    read_provider.commit_exists.side_effect = lambda commit_id: commit_id == "present-commit"
    read_provider.catalog_at.return_value = (table,)
    read_provider.stream_table_at.return_value = iter(())

    app = VersionedReadApplication(
        store,
        layout,
        lambda _repository_id: read_provider,
    )
    with pytest.raises(CommitNotFoundError):
        app.open_table_rows(
            repository_id,
            "missing-commit",
            "Records",
            UnknownTypePolicy.REJECT,
        )
    assert read_provider.commit_exists.call_count == 1

    read_provider.commit_exists.reset_mock()
    _plan, rows = app.open_table_rows(
        repository_id,
        "present-commit",
        "Records",
        UnknownTypePolicy.REJECT,
    )
    list(rows)
    assert read_provider.commit_exists.call_count == 1
    read_provider.catalog_at.assert_called_once_with("present-commit", existence_verified=True)
    read_provider.stream_table_at.assert_called_once()
    assert read_provider.stream_table_at.call_args.kwargs["existence_verified"] is True


def test_versioned_read_stream_timeout_maps_to_provider_unavailable() -> None:
    provider = CandidateAReadProvider(
        RepositoryServiceSettings(),
        DurableLayout.create(Path("/tmp/unused")),
        Path("/tmp/unused"),
        MagicMock(spec=DoltRunner),
    )
    table = TableCatalog(
        "records",
        (ColumnCatalog("id", "BIGINT", False, 1),),
        0,
    )

    def timeout_stream(*args: object, **kwargs: object) -> Iterator[pa.RecordBatch]:
        del args, kwargs

        def _gen() -> Iterator[pa.RecordBatch]:
            raise TimeoutError("row_stream exceeded timeout")
            yield pa.record_batch({"id": pa.array([], type=pa.int64())})  # pragma: no cover

        return _gen()

    with patch.object(provider._cli, "stream_table_at", side_effect=timeout_stream):
        with patch.object(provider._cli, "commit_exists", return_value=True):
            with pytest.raises(ProviderUnavailableError, match="unavailable") as exc_info:
                list(
                    provider.stream_table_at(
                        "opaque-commit",
                        table,
                        UnknownTypePolicy.REJECT,
                    )
                )
    assert "SELECT" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None


def test_read_stream_cancelled_error_is_not_provider_unavailable() -> None:
    exc = ReadStreamCancelledError("versioned read stream was cancelled")
    assert isinstance(exc, VersionedReadError)
    assert not isinstance(exc, ProviderUnavailableError)


@pytest.mark.parametrize(
    ("exc", "message"),
    (
        (ProcessStreamCancelledError("stream cancelled"), "mutated process cancel text"),
        (ProcessStreamCancelledError("different wording"), "different wording"),
        (DoltCliStreamCancelledError("row stream cancelled"), "mutated dolt cancel text"),
        (DoltCliStreamCancelledError("other cancel reason"), "other cancel reason"),
    ),
)
def test_typed_stream_cancellation_maps_to_read_stream_cancelled_regardless_of_message(
    exc: BaseException,
    message: str,
) -> None:
    del message
    mapped = _as_provider_unavailable(exc)
    assert isinstance(mapped, ReadStreamCancelledError)
    assert mapped.__cause__ is None


def _records_table() -> TableCatalog:
    return TableCatalog(
        "records",
        (ColumnCatalog("id", "BIGINT", False, 1),),
        1,
    )


def _read_provider_with_mock_stream(
    tmp_path: Path,
) -> tuple[CandidateAReadProvider, MagicMock, TableCatalog]:
    layout = DurableLayout.create(tmp_path / "root")
    settings = RepositoryServiceSettings()
    repository = layout.staging_artifacts / "repo"
    repository.mkdir(parents=True, exist_ok=True)
    runner = MagicMock(spec=DoltRunner)
    provider = CandidateAReadProvider(settings, layout, repository, runner)
    return provider, runner, _records_table()


def _csv_stream_mock(header_line: str, data_lines: list[str]) -> MagicMock:
    stream = MagicMock()
    stream.__iter__ = MagicMock(
        return_value=iter((line + "\n").encode() for line in [header_line, *data_lines])
    )
    stream.close.return_value = CommandResult(
        command_kind="row_stream",
        exit_code=0,
        duration_seconds=0.0,
        stdout=b"",
        stdout_tail=b"",
        stderr_tail=b"",
        timed_out=False,
    )
    return stream


def _tagged_csv_lines(table: TableCatalog) -> tuple[str, list[str]]:
    plan = compile_table_plan(table, UnknownTypePolicy.REJECT)
    _, header = _tagged_select_list(plan)
    header_line = ",".join(header)
    data_line = ",".join(value for _ in table.columns for value in ("0", "1"))
    return header_line, [data_line]


def _assert_query_directory_clean(cli: CandidateADoltCli) -> None:
    assert list(cli.query_directory.glob("query-*.sql")) == []


def test_dolt_cli_pre_start_callback_cancel_skips_spawn(tmp_path: Path) -> None:
    provider, runner, table = _read_provider_with_mock_stream(tmp_path)
    callback_calls = 0

    def cancel_immediately() -> bool:
        nonlocal callback_calls
        callback_calls += 1
        return True

    with patch.object(provider._cli, "commit_exists", return_value=True):
        with pytest.raises(ReadStreamCancelledError, match="cancelled") as exc_info:
            list(
                provider.stream_table_at(
                    "opaque-commit",
                    table,
                    UnknownTypePolicy.REJECT,
                    cancellation=cancel_immediately,
                )
            )
    assert callback_calls == 1
    runner.stream.assert_not_called()
    assert exc_info.value.__cause__ is None
    _assert_query_directory_clean(provider._cli)


def test_dolt_cli_pre_start_callback_exception_skips_spawn(tmp_path: Path) -> None:
    provider, runner, table = _read_provider_with_mock_stream(tmp_path)
    callback_calls = 0

    def broken_callback() -> bool:
        nonlocal callback_calls
        callback_calls += 1
        raise RuntimeError("callback failed")

    with patch.object(provider._cli, "commit_exists", return_value=True):
        with pytest.raises(ReadStreamCancelledError, match="cancelled") as exc_info:
            list(
                provider.stream_table_at(
                    "opaque-commit",
                    table,
                    UnknownTypePolicy.REJECT,
                    cancellation=broken_callback,
                )
            )
    assert callback_calls == 1
    runner.stream.assert_not_called()
    assert exc_info.value.__cause__ is None
    _assert_query_directory_clean(provider._cli)


def test_dolt_cli_batch_loop_callback_cancel_maps_to_read_stream_cancelled(tmp_path: Path) -> None:
    provider, runner, table = _read_provider_with_mock_stream(tmp_path)
    header_line, data_lines = _tagged_csv_lines(table)
    stream = _csv_stream_mock(header_line, data_lines)
    runner.stream.return_value = stream
    callback_calls = 0

    def cancel_after_preflight() -> bool:
        nonlocal callback_calls
        callback_calls += 1
        return callback_calls >= 2

    with patch.object(provider._cli, "commit_exists", return_value=True):
        with pytest.raises(ReadStreamCancelledError, match="cancelled") as exc_info:
            list(
                provider.stream_table_at(
                    "opaque-commit",
                    table,
                    UnknownTypePolicy.REJECT,
                    cancellation=cancel_after_preflight,
                )
            )
    assert callback_calls >= 2
    runner.stream.assert_called_once()
    stream.close.assert_called()
    assert exc_info.value.__cause__ is None
    _assert_query_directory_clean(provider._cli)


def test_dolt_cli_batch_loop_callback_exception_maps_to_read_stream_cancelled(tmp_path: Path) -> None:
    provider, runner, table = _read_provider_with_mock_stream(tmp_path)
    header_line, data_lines = _tagged_csv_lines(table)
    stream = _csv_stream_mock(header_line, data_lines)
    runner.stream.return_value = stream
    callback_calls = 0

    def broken_after_preflight() -> bool:
        nonlocal callback_calls
        callback_calls += 1
        if callback_calls >= 2:
            raise RuntimeError("callback failed")
        return False

    with patch.object(provider._cli, "commit_exists", return_value=True):
        with pytest.raises(ReadStreamCancelledError, match="cancelled") as exc_info:
            list(
                provider.stream_table_at(
                    "opaque-commit",
                    table,
                    UnknownTypePolicy.REJECT,
                    cancellation=broken_after_preflight,
                )
            )
    assert callback_calls >= 2
    runner.stream.assert_called_once()
    stream.close.assert_called()
    assert exc_info.value.__cause__ is None
    _assert_query_directory_clean(provider._cli)


def test_read_provider_rejects_non_main_ref() -> None:
    provider = CandidateAReadProvider(
        RepositoryServiceSettings(),
        DurableLayout.create(Path("/tmp/unused")),
        Path("/tmp/unused"),
        MagicMock(spec=DoltRunner),
    )
    with pytest.raises(MainRefNotFoundError, match="not supported"):
        provider.read_ref("feature")


def test_provider_fault_messages_are_redacted() -> None:
    provider = CandidateAReadProvider(
        RepositoryServiceSettings(),
        DurableLayout.create(Path("/tmp/unused")),
        Path("/tmp/unused"),
        MagicMock(spec=DoltRunner),
    )
    with patch.object(
        provider._cli,
        "query_json",
        side_effect=DoltCliError("SELECT * FROM secret WHERE path='/tmp/x'"),
    ):
        with pytest.raises(ProviderUnavailableError, match="unavailable") as exc_info:
            provider.read_ref("main")
    assert "SELECT" not in str(exc_info.value)
    assert "/tmp" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert "SELECT" not in repr(exc_info.value)

    with patch.object(
        provider._cli,
        "query_json",
        side_effect=DoltCliError('Table_type="tenant-secret"'),
    ):
        with pytest.raises(ProviderUnavailableError, match="unavailable") as exc_info:
            provider.read_ref("main")
    assert "tenant-secret" not in str(exc_info.value)
    assert "tenant-secret" not in repr(exc_info.value)
    assert exc_info.value.__cause__ is None


READ_REF_FAULT_SHAPES: tuple[tuple[list[dict[str, object]], type[Exception], str | None], ...] = (
    ([{"commit_id": ""}], MainRefNotFoundError, "not available"),
    ([], ProviderUnavailableError, "unavailable"),
    ([{"commit_id": "abc"}, {"commit_id": "abc"}], ProviderUnavailableError, "unavailable"),
    ([{"commit_id": 1}], ProviderUnavailableError, "unavailable"),
    ([{"commit_id": True}], ProviderUnavailableError, "unavailable"),
    ([{"commit_id": None}], ProviderUnavailableError, "unavailable"),
)


@pytest.mark.parametrize(
    ("rows", "expected_type", "match"),
    READ_REF_FAULT_SHAPES,
)
def test_read_ref_fault_shape_matrix(
    rows: list[dict[str, object]],
    expected_type: type[Exception],
    match: str | None,
) -> None:
    provider = CandidateAReadProvider(
        RepositoryServiceSettings(),
        DurableLayout.create(Path("/tmp/unused")),
        Path("/tmp/unused"),
        MagicMock(spec=DoltRunner),
    )
    with patch.object(provider._cli, "query_json", return_value=rows):
        with pytest.raises(expected_type, match=match):
            provider.read_ref("main")


def test_versioned_read_application_wraps_store_failures(tmp_path: Path) -> None:
    store = _open_mutation_store(tmp_path)
    store._connection.close()
    layout = DurableLayout.create(tmp_path / "root")
    app = VersionedReadApplication(store, layout, lambda _repository_id: MagicMock())
    with pytest.raises(ProviderUnavailableError, match="unavailable"):
        app.get_catalog(uuid4(), "opaque-commit")


def test_versioned_read_application_wraps_factory_oserror(tmp_path: Path) -> None:
    store, layout, repository_id = _visible_repository_setup(tmp_path)

    def failing_factory(_repository_id: UUID) -> CandidateAReadProvider:
        raise OSError("factory failed")

    app = VersionedReadApplication(store, layout, failing_factory)
    with pytest.raises(ProviderUnavailableError, match="unavailable"):
        app.get_catalog(repository_id, "opaque-commit")


def test_malformed_commit_exists_metadata_is_unavailable() -> None:
    provider = CandidateAReadProvider(
        RepositoryServiceSettings(),
        DurableLayout.create(Path("/tmp/unused")),
        Path("/tmp/unused"),
        MagicMock(spec=DoltRunner),
    )
    stdout = json.dumps(
        {
            "rows": [{"commit_hash": "a"}, {"commit_hash": "b"}],
            "columns": [{"name": "commit_hash"}],
        }
    ).encode()
    with patch.object(
        provider._cli,
        "run_cli",
        return_value=CommandResult(
            command_kind="commit_exists",
            exit_code=0,
            duration_seconds=0.0,
            stdout=stdout,
            stdout_tail=stdout,
            stderr_tail=b"",
        ),
    ):
        with pytest.raises(ProviderUnavailableError):
            provider.commit_exists("a")


def _memo_table(name: str) -> TableCatalog:
    column = ColumnCatalog(
        name="id",
        sql_type="BIGINT",
        nullable=False,
        primary_key_position=1,
    )
    return TableCatalog(name=name, columns=(column,), row_count=0)


def test_catalog_at_memo_uses_opaque_target_key(tmp_path: Path) -> None:
    layout = DurableLayout.create(tmp_path / "root")
    settings = RepositoryServiceSettings()
    repository = layout.staging_artifacts / "repo"
    repository.mkdir(parents=True, exist_ok=True)
    runner = MagicMock(spec=DoltRunner)
    cli = CandidateADoltCli(settings, layout, repository, runner)
    for index in range(_CATALOG_MEMO_ENTRIES + 1):
        cli._store_cached_catalog(f"token-{index}", (_memo_table(f"t{index}"),))
    assert cli._get_cached_catalog("token-0") is None
    assert cli._get_cached_catalog(f"token-{_CATALOG_MEMO_ENTRIES}") is not None


@pytest.fixture
def read_repo(
    tmp_path: Path,
) -> tuple[DurableLayout, RepositoryServiceSettings, DoltRunner, CandidateAReadProvider, OfflineCliProvider]:
    settings = lifecycle_settings(tmp_path)
    layout = DurableLayout.create_for_probe(settings.data_root)
    repository = layout.staging_artifacts / "read-repo"
    repository.mkdir(parents=True, exist_ok=True)
    runner = DoltRunner(settings, layout.root)
    offline = OfflineCliProvider(settings, layout, repository, runner)
    offline.initialize_repository()
    read_provider = CandidateAReadProvider(settings, layout, repository, runner)
    return layout, settings, runner, read_provider, offline


def _write_sql(layout: DurableLayout, name: str, sql: str) -> Path:
    path = layout.staging_artifacts / name
    path.write_text(sql, encoding="utf-8")
    return path


def _commit_changes(offline: OfflineCliProvider, marker: str) -> str:
    return offline.commit_marker(marker)


@pytest.mark.integration
def test_read_repo_c0_catalog_is_empty(read_repo: ReadRepoFixture) -> None:
    _, _, _, read_provider, _ = read_repo
    c0 = read_provider.read_ref("main")
    assert read_provider.commit_exists(c0)
    assert read_provider.catalog_at(c0) == ()


@pytest.mark.integration
def test_read_repo_c1_c2_literal_reads(read_repo: ReadRepoFixture) -> None:
    layout, _, _, read_provider, offline = read_repo
    c0 = read_provider.read_ref("main")
    offline.replay(
        _write_sql(
            layout,
            "c1.sql",
            "CREATE TABLE items (id BIGINT NOT NULL PRIMARY KEY, label VARCHAR(32) NOT NULL);\n"
            "INSERT INTO items (id, label) VALUES (1, 'c1-value');\n",
        )
    )
    c1 = _commit_changes(offline, "gateway-versioned-import operation_id=00000000-0000-4000-8000-000000000001")
    offline.replay(
        _write_sql(
            layout,
            "c2.sql",
            "INSERT INTO items (id, label) VALUES (2, 'c2-value');\n",
        )
    )
    c2 = _commit_changes(offline, "gateway-versioned-import operation_id=00000000-0000-4000-8000-000000000002")

    c1_catalog = read_provider.catalog_at(c1)
    c2_catalog = read_provider.catalog_at(c2)
    assert any(table.name == "items" for table in c1_catalog)
    assert next(table for table in c1_catalog if table.name == "items").row_count == 1
    assert next(table for table in c2_catalog if table.name == "items").row_count == 2

    c1_table = next(table for table in c1_catalog if table.name == "items")
    c1_batches = list(
        read_provider.stream_table_at(c1, c1_table, UnknownTypePolicy.REJECT)
    )
    c1_values = {
        int(batch.column("id")[row].as_py())
        for batch in c1_batches
        for row in range(batch.num_rows)
    }
    assert c1_values == {1}

    c2_table = next(table for table in c2_catalog if table.name == "items")
    c2_values = {
        int(batch.column("id")[row].as_py())
        for batch in read_provider.stream_table_at(c2, c2_table, UnknownTypePolicy.REJECT)
        for row in range(batch.num_rows)
    }
    assert c2_values == {1, 2}
    assert c0 != c1 != c2


@pytest.mark.integration
@pytest.mark.serial
def test_branch_movement_keeps_pinned_commit_immutable(
    read_repo: ReadRepoFixture,
    tmp_path: Path,
) -> None:
    layout, _, _, read_provider, offline = read_repo
    offline.replay(
        _write_sql(
            layout,
            "setup.sql",
            "CREATE TABLE items (id BIGINT NOT NULL PRIMARY KEY, label VARCHAR(32) NOT NULL);\n"
            "INSERT INTO items (id, label) VALUES (1, 'pinned');\n",
        )
    )
    c1 = _commit_changes(offline, "gateway-versioned-import operation_id=00000000-0000-4000-8000-000000000010")
    preflight_done = threading.Event()
    release = threading.Event()
    original_exists = read_provider.commit_exists

    def gated_commit_exists(commit_id: str) -> bool:
        exists = original_exists(commit_id)
        if commit_id == c1 and exists:
            preflight_done.set()
            assert release.wait(timeout=5.0)
        return exists

    def advance_main() -> None:
        assert preflight_done.wait(timeout=5.0)
        offline.replay(
            _write_sql(
                layout,
                "advance.sql",
                "INSERT INTO items (id, label) VALUES (2, 'moved-main');\n",
            )
        )
        _commit_changes(offline, "gateway-versioned-import operation_id=00000000-0000-4000-8000-000000000011")
        release.set()

    store, _, repository_id = _visible_repository_setup(tmp_path)
    worker = threading.Thread(target=advance_main)
    worker.start()
    with patch.object(read_provider, "commit_exists", side_effect=gated_commit_exists):
        with patch(
            "gateway_repository_service.versioned_read.application.is_repository_visible",
            return_value=True,
        ):
            app = VersionedReadApplication(store, layout, lambda _id: read_provider)
            _plan, rows = app.open_table_rows(
                repository_id,
                c1,
                "items",
                UnknownTypePolicy.REJECT,
            )
            pinned_ids = {
                int(batch.column("id")[row].as_py())
                for batch in rows
                for row in range(batch.num_rows)
            }
    worker.join(timeout=10.0)
    assert not worker.is_alive()
    assert pinned_ids == {1}
    c2 = read_provider.read_ref("main")
    assert c2 != c1
    c2_catalog = read_provider.catalog_at(c2)
    c2_table = next(table for table in c2_catalog if table.name == "items")
    c2_ids = {
        int(batch.column("id")[row].as_py())
        for batch in read_provider.stream_table_at(c2, c2_table, UnknownTypePolicy.REJECT)
        for row in range(batch.num_rows)
    }
    assert c2_ids == {1, 2}


@pytest.mark.integration
def test_commit_exists_finds_side_branch_commit_while_on_main(read_repo: ReadRepoFixture) -> None:
    layout, settings, runner, read_provider, offline = read_repo
    repository = layout.staging_artifacts / "read-repo"
    runner.run(
        "checkout_side",
        ["checkout", "-b", "side"],
        cwd=repository,
        timeout=settings.metadata_timeout_seconds,
    )
    offline.replay(
        _write_sql(
            layout,
            "side.sql",
            "CREATE TABLE side_items (id BIGINT NOT NULL PRIMARY KEY, label VARCHAR(32) NOT NULL);\n"
            "INSERT INTO side_items (id, label) VALUES (1, 'side-only');\n",
        )
    )
    _commit_changes(
        offline,
        "gateway-versioned-import operation_id=00000000-0000-4000-8000-000000000030",
    )
    side_head_rows = read_provider._cli.query_json(
        "side_head",
        "SELECT HASHOF('HEAD') AS commit_id;\n",
    )
    side_commit = value(side_head_rows[0], "commit_id", 0)
    assert isinstance(side_commit, str)
    runner.run(
        "checkout_main",
        ["checkout", "main"],
        cwd=repository,
        timeout=settings.metadata_timeout_seconds,
    )
    offline.replay(
        _write_sql(
            layout,
            "main_only.sql",
            "CREATE TABLE main_items (id BIGINT NOT NULL PRIMARY KEY, label VARCHAR(32) NOT NULL);\n"
            "INSERT INTO main_items (id, label) VALUES (1, 'main-only');\n",
        )
    )
    _commit_changes(
        offline,
        "gateway-versioned-import operation_id=00000000-0000-4000-8000-000000000031",
    )
    assert read_provider.read_ref("main") != side_commit
    assert read_provider.commit_exists(side_commit)
    side_catalog = read_provider.catalog_at(side_commit)
    side_table = next(table for table in side_catalog if table.name == "side_items")
    side_labels = {
        batch.column("label")[row].as_py()
        for batch in read_provider.stream_table_at(side_commit, side_table, UnknownTypePolicy.REJECT)
        for row in range(batch.num_rows)
    }
    assert side_labels == {"side-only"}


@pytest.mark.integration
@pytest.mark.parametrize("token", ("é", "Ā", "中文", "𐀀"))
def test_opaque_commit_literal_round_trips_unicode_on_real_dolt(
    read_repo: ReadRepoFixture,
    token: str,
) -> None:
    _, _, _, read_provider, _ = read_repo
    literal = opaque_commit_literal(token)
    rows = read_provider._cli.query_json("literal_roundtrip", f"SELECT {literal} AS token;\n")
    assert value(rows[0], "token", 0) == token


@pytest.mark.integration
def test_opaque_commit_literal_blocks_sql_injection(read_repo: ReadRepoFixture) -> None:
    _, _, _, read_provider, _ = read_repo
    malicious = r"x\'; CREATE TABLE injected(id INT); --"
    assert read_provider.commit_exists(malicious) is False
    with pytest.raises(CommitNotFoundError):
        read_provider.catalog_at(malicious)
    main_commit = read_provider.read_ref("main")
    catalog = read_provider.catalog_at(main_commit)
    assert all(table.name != "injected" for table in catalog)


@pytest.mark.integration
def test_missing_commit_and_table(read_repo: ReadRepoFixture, tmp_path: Path) -> None:
    layout, _, _, read_provider, _ = read_repo
    store, vis_layout, repository_id = _visible_repository_setup(tmp_path)
    del vis_layout
    assert read_provider.commit_exists("missing-opaque-commit") is False
    with pytest.raises(CommitNotFoundError):
        read_provider.catalog_at("missing-opaque-commit")
    c0 = read_provider.read_ref("main")
    with patch(
        "gateway_repository_service.versioned_read.application.is_repository_visible",
        return_value=True,
    ):
        app = VersionedReadApplication(store, layout, lambda _id: read_provider)
        with pytest.raises(TableNotFoundError):
            app.open_table_rows(
                repository_id,
                c0,
                "missing_table",
                UnknownTypePolicy.REJECT,
            )


@pytest.mark.integration
def test_exact_identifier_real_dolt(read_repo: ReadRepoFixture, tmp_path: Path) -> None:
    layout, _, _, read_provider, offline = read_repo
    offline.replay(
        _write_sql(
            layout,
            "spaced.sql",
            "CREATE TABLE `My Table` (id BIGINT NOT NULL PRIMARY KEY, label VARCHAR(32) NOT NULL);\n"
            "INSERT INTO `My Table` (id, label) VALUES (1, 'spaced');\n",
        )
    )
    commit_id = _commit_changes(
        offline,
        "gateway-versioned-import operation_id=00000000-0000-4000-8000-000000000020",
    )
    catalog = read_provider.catalog_at(commit_id)
    table = next(table for table in catalog if table.name == "My Table")
    labels = {
        batch.column("label")[row].as_py()
        for batch in read_provider.stream_table_at(commit_id, table, UnknownTypePolicy.REJECT)
        for row in range(batch.num_rows)
    }
    assert labels == {"spaced"}
    store, _, repository_id = _visible_repository_setup(tmp_path)
    with patch(
        "gateway_repository_service.versioned_read.application.is_repository_visible",
        return_value=True,
    ):
        app = VersionedReadApplication(store, layout, lambda _id: read_provider)
        with pytest.raises(TableNotFoundError):
            app.open_table_rows(
                repository_id,
                commit_id,
                "my table",
                UnknownTypePolicy.REJECT,
            )
