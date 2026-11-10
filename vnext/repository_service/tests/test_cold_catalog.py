"""Bounded catalog queries and concurrent immutable-catalog reads."""

from __future__ import annotations

import json
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from gateway_repository_service.arrow_mapping import TableCatalog
from gateway_repository_service.candidate_a.dolt_cli import CandidateADoltCli, DoltCliError
from gateway_repository_service.candidate_a.ref_validation import opaque_commit_literal
from gateway_repository_service.candidate_a.sql import quote_identifier
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import CommandResult, DoltRunner
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.versioned_read import application


@pytest.fixture
def cli(tmp_path: Path) -> CandidateADoltCli:
    layout = DurableLayout.create_for_probe(tmp_path / "root")
    repository = layout.staging_artifacts / "repo"
    repository.mkdir()
    return CandidateADoltCli(RepositoryServiceSettings(), layout, repository, MagicMock(spec=DoltRunner))


@pytest.mark.parametrize("table_count", (0, 1, 16, 17))
def test_catalog_batches_bind_ordinals_without_relying_on_result_order(
    cli: CandidateADoltCli, table_count: int,
) -> None:
    names = [f"table `{index}" for index in range(table_count)]
    batches = [names[start:start + 16] for start in range(0, table_count, 16)]
    literal = opaque_commit_literal("immutable ' token")
    statements: list[str] = []

    def query(kind: str, sql: str) -> list[dict[str, Any]]:
        if kind == "catalog_tables":
            return [{"Tables_in_repo": name, "Table_type": "BASE TABLE"} for name in names]
        assert kind == "catalog_counts"
        statements.append(sql)
        batch = next(batch for batch in batches if sql.startswith(
            f"SELECT 0 AS ordinal, COUNT(*) AS row_count FROM {quote_identifier(batch[0])} AS OF "
        ))
        assert sql == "\nUNION ALL\n".join(
            f"SELECT {ordinal} AS ordinal, COUNT(*) AS row_count FROM {quote_identifier(name)} AS OF {literal}"
            for ordinal, name in enumerate(batch)
        ) + ";\n"
        return [{"ordinal": ordinal, "row_count": names.index(name)}
                for ordinal, name in reversed(list(enumerate(batch)))]

    with patch.object(cli, "query_json", side_effect=query), patch.object(
        cli, "_load_table_schema", side_effect=lambda name, _literal: TableCatalog(name, (), 0),
    ):
        catalog = cli.catalog_at("immutable ' token")
    assert {table.name: table.row_count for table in catalog} == dict(zip(names, range(table_count), strict=True))
    assert [table.name for table in catalog] == sorted(names)
    assert len(statements) == len(batches)


COUNT_BINDING_FAULTS: tuple[list[dict[str, Any]], ...] = (
    [],
    [{"ordinal": 0, "row_count": 1}],
    [{"ordinal": 0, "row_count": 1}, {"ordinal": 0, "row_count": 2}],
    *([dict[str, Any](ordinal=ordinal, row_count=1), dict[str, Any](ordinal=1, row_count=2)]
      for ordinal in (True, "0", 0.0, -1, 2, None)),
    [{"ordinal": 0, "row_count": -1}, {"ordinal": 1, "row_count": 2}],
    [{"ordinal": 0, "row_count": True}, {"ordinal": 1, "row_count": 2}],
    [{"ordinal": 0, "row_count": 1, "extra": 0}, {"ordinal": 1, "row_count": 2}],
    [{"row_count": 1}, {"ordinal": 1, "row_count": 2}],
)


@pytest.mark.parametrize("rows", COUNT_BINDING_FAULTS)
def test_count_binding_failure_does_not_cache_partial_catalog(
    cli: CandidateADoltCli, rows: list[dict[str, Any]],
) -> None:
    result = CommandResult("catalog_counts", 0, 0, json.dumps(rows).encode(), b"", b"")
    names = [{"Tables_in_repo": name, "Table_type": "BASE TABLE"} for name in ("a", "b")]
    original_query = cli.query_json

    def query(kind: str, sql: str) -> list[dict[str, Any]]:
        return names if kind == "catalog_tables" else original_query(kind, sql)

    with patch.object(cli, "query_json", side_effect=query), patch.object(
        cli, "_load_table_schema", side_effect=lambda name, _literal: TableCatalog(name, (), 0),
    ), patch.object(cli, "run_cli", return_value=result) as run:
        with pytest.raises(DoltCliError):
            cli.catalog_at("target")
        assert cli._get_cached_catalog("target") is None
        run.return_value = CommandResult(
            "catalog_counts", 0, 0,
            b'[{"ordinal":0,"row_count":1},{"ordinal":1,"row_count":2}]', b"", b"",
        )
        assert cli.catalog_at("target") == (TableCatalog("a", (), 1), TableCatalog("b", (), 2))
        assert run.call_count == 2
        assert run.call_args.args[2] == cli.settings.metadata_timeout_seconds


@pytest.mark.parametrize("failure", ("command", "capture"))
def test_count_query_failure_is_not_retried_per_table(cli: CandidateADoltCli, failure: str) -> None:
    result = CommandResult("catalog_counts", 0, 0, b"[]", b"", b"", stdout_truncated=True)
    original_query = cli.query_json

    def query(kind: str, sql: str) -> list[dict[str, Any]]:
        if kind == "catalog_tables":
            return [{"Tables_in_repo": name, "Table_type": "BASE TABLE"} for name in ("a", "b")]
        return original_query(kind, sql)

    with patch.object(cli, "query_json", side_effect=query), patch.object(
        cli, "_load_table_schema", side_effect=lambda name, _literal: TableCatalog(name, (), 0),
    ), patch.object(cli, "run_cli", return_value=result) as run:
        if failure == "command":
            run.side_effect = DoltCliError("Dolt CLI failed")
        with pytest.raises(DoltCliError):
            cli.catalog_at("target")
        assert run.call_count == 1
        assert cli._get_cached_catalog("target") is None


class _LoaderExit(BaseException):
    pass


@pytest.mark.serial
@pytest.mark.parametrize("outcome", ("cached", "oversize", "loader_error", "loader_exit", "size_error", "publish_exit"))
def test_concurrent_catalog_callers_share_outcome_and_can_retry(
    monkeypatch: pytest.MonkeyPatch, outcome: str,
) -> None:
    cache = application._VersionedCatalogCache()
    key = (uuid4(), "immutable")
    catalog = (TableCatalog("table", (), 1),)
    entered = Event()
    release = Event()
    followers = Barrier(3)
    failure = _LoaderExit("exit") if outcome.endswith("exit") else ValueError("failure")

    class ObservedFuture(Future[tuple[TableCatalog, ...]]):
        def result(self, timeout: float | None = None) -> tuple[TableCatalog, ...]:
            followers.wait(timeout=5)
            return super().result(timeout=5)

    def load() -> tuple[TableCatalog, ...]:
        entered.set()
        assert release.wait(5)
        if outcome.startswith("loader_"):
            raise failure
        return catalog

    original_store = cache._store

    def fail_publication(*args: Any) -> None:
        original_store(*args)
        raise failure

    with monkeypatch.context() as scoped:
        scoped.setattr(application, "Future", ObservedFuture)
        if outcome == "oversize":
            scoped.setattr(application, "_VERSIONED_CATALOG_CACHE_BYTES", 1)
        elif outcome == "size_error":
            scoped.setattr(application, "_catalog_cache_size", MagicMock(side_effect=failure))
        elif outcome == "publish_exit":
            scoped.setattr(cache, "_store", fail_publication)
        with ThreadPoolExecutor(max_workers=3) as pool:
            leader = pool.submit(cache.get_or_load, key, load)
            try:
                assert entered.wait(5)
                unwanted_loader = MagicMock(side_effect=AssertionError("duplicate load"))
                waiting = [pool.submit(cache.get_or_load, key, unwanted_loader) for _ in range(2)]
                followers.wait(timeout=5)
            finally:
                release.set()
            for result in [leader, *waiting]:
                if outcome in ("cached", "oversize"):
                    assert result.result(timeout=5) is catalog
                else:
                    with pytest.raises(type(failure)) as caught:
                        result.result(timeout=5)
                    assert caught.value is failure
            unwanted_loader.assert_not_called()
    assert cache._inflight == {}
    retry = MagicMock(return_value=catalog)
    assert cache.get_or_load(key, retry) is catalog
    assert retry.call_count == (0 if outcome == "cached" else 1)
    assert cache._size_bytes == sum(entry.size_bytes for entry in cache._entries.values())


@pytest.mark.serial
def test_different_catalog_keys_can_load_concurrently() -> None:
    cache = application._VersionedCatalogCache()
    both_loaders = Barrier(2)

    def load() -> tuple[TableCatalog, ...]:
        both_loaders.wait(timeout=5)
        return ()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(cache.get_or_load, (uuid4(), "same-commit"), load) for _ in range(2)]
        assert [result.result(timeout=5) for result in results] == [(), ()]
