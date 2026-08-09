"""Tests for commit-pinned Candidate A read provider and application."""

from __future__ import annotations

import json
import sqlite3
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
)
from gateway_repository_service.candidate_a.ref_validation import (
    opaque_commit_literal,
    validate_commit_id,
)
from gateway_repository_service.candidate_a.sql import quote_identifier
from gateway_repository_service.control_db import CONTROL_DB_USER_VERSION, ControlStore
from gateway_repository_service.layout import DurableLayout, repository_key
from gateway_repository_service.mutation_fingerprints import create_repository_fingerprint_v1
from gateway_repository_service.mutation_store import (
    IdempotencyScope,
    MutationStore,
    configure_connection,
)
from gateway_repository_service.process import CommandResult, DoltRunner
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
from gateway_repository_service.versioned_read.provider import CandidateAReadProvider
from support.lifecycle_harness import lifecycle_settings

ReadRepoFixture = tuple[
    DurableLayout,
    RepositoryServiceSettings,
    DoltRunner,
    CandidateAReadProvider,
    OfflineCliProvider,
]


@pytest.mark.parametrize(
    ("token", "expected_literal"),
    (
        ("not-a-dolt-hash'; DROP TABLE t; --", "'not-a-dolt-hash''; DROP TABLE t; --'"),
        (r"back\slash-token", r"'back\slash-token'"),
        ("plain'quote", "'plain''quote'"),
        ("opaque-token", "'opaque-token'"),
    ),
)
def test_opaque_commit_literal_quotes_without_provider_grammar(
    token: str,
    expected_literal: str,
) -> None:
    assert opaque_commit_literal(token) == expected_literal
    assert opaque_commit_literal(token).startswith("'")
    assert opaque_commit_literal(token).endswith("'")
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

    def query_json(kind: str, sql: str, *, revision: str | None = None) -> list[dict[str, Any]]:
        del revision
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

    def query_json(kind: str, sql: str, *, revision: str | None = None) -> list[dict[str, Any]]:
        del revision
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
    ) -> list[pa.RecordBatch]:
        del commit_id, catalog, policy, cancellation
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


def test_dolt_cli_batch_loop_cancel_maps_to_read_stream_cancelled() -> None:
    provider = CandidateAReadProvider(
        RepositoryServiceSettings(),
        DurableLayout.create(Path("/tmp/unused")),
        Path("/tmp/unused"),
        MagicMock(spec=DoltRunner),
    )
    table = TableCatalog(
        "records",
        (ColumnCatalog("id", "BIGINT", False, 1),),
        1,
    )
    cancel_after = 0

    def cancel_soon() -> bool:
        nonlocal cancel_after
        cancel_after += 1
        return cancel_after >= 2

    def cancelled_stream(*args: object, **kwargs: object) -> Iterator[pa.RecordBatch]:
        del args, kwargs

        def _gen() -> Iterator[pa.RecordBatch]:
            yield pa.record_batch({"id": pa.array([1], type=pa.int64())})
            raise DoltCliError("row stream cancelled")

        return _gen()

    with patch.object(provider._cli, "stream_table_at", side_effect=cancelled_stream):
        with patch.object(provider._cli, "commit_exists", return_value=True):
            with pytest.raises(ReadStreamCancelledError, match="cancelled") as exc_info:
                list(
                    provider.stream_table_at(
                        "opaque-commit",
                        table,
                        UnknownTypePolicy.REJECT,
                        cancellation=cancel_soon,
                    )
                )
    assert exc_info.value.__cause__ is None


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
def test_branch_movement_keeps_pinned_commit_immutable(read_repo: ReadRepoFixture) -> None:
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
    offline.replay(
        _write_sql(
            layout,
            "advance.sql",
            "INSERT INTO items (id, label) VALUES (2, 'moved-main');\n",
        )
    )
    _commit_changes(offline, "gateway-versioned-import operation_id=00000000-0000-4000-8000-000000000011")
    assert read_provider.read_ref("main") != c1
    pinned_catalog = read_provider.catalog_at(c1)
    pinned_table = next(table for table in pinned_catalog if table.name == "items")
    assert pinned_table.row_count == 1
    pinned_ids = {
        int(batch.column("id")[row].as_py())
        for batch in read_provider.stream_table_at(c1, pinned_table, UnknownTypePolicy.REJECT)
        for row in range(batch.num_rows)
    }
    assert pinned_ids == {1}


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


@pytest.mark.integration
def test_malformed_commit_exists_metadata_is_unavailable(read_repo: ReadRepoFixture) -> None:
    _, _, _, read_provider, _ = read_repo
    stdout = json.dumps(
        {
            "rows": [{"commit_hash": "a"}, {"commit_hash": "b"}],
            "columns": [{"name": "commit_hash"}],
        }
    ).encode()
    with patch.object(
        read_provider._cli,
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
            read_provider.commit_exists("a")
