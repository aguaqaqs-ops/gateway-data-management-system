"""Hidden FINAL summary fail-closed and cache-validation cases."""

from __future__ import annotations

import dataclasses

import pytest
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationDiagnosticCode,
    MaterializationPolicy,
    SnapshotMaterializationStatus,
)
from gateway_backend.capabilities.table_access.contracts import PARSER_VERSION
from gateway_backend.capabilities.table_rules.contracts import TABLE_RULESET_VERSION
from tests.support.repository_ref_materialization import (
    FakeRepositoryTableAccessProvider,
    catalog_table,
    hidden_summary_for,
    int_id_column,
    make_catalog,
    materialize_ref,
    text_column,
)

HIDDEN_SUMMARY_FAULTS = (
    ("missing", MaterializationDiagnosticCode.HIDDEN_SUMMARY_MISSING),
    ("corrupt", MaterializationDiagnosticCode.HIDDEN_SUMMARY_CORRUPT),
    ("version", MaterializationDiagnosticCode.HIDDEN_SUMMARY_VERSION_MISMATCH),
    ("snapshot_digest", MaterializationDiagnosticCode.HIDDEN_SUMMARY_CORRUPT),
    ("raw_digest", MaterializationDiagnosticCode.HIDDEN_SUMMARY_DIGEST_MISMATCH),
    ("schema", MaterializationDiagnosticCode.HIDDEN_SUMMARY_DIGEST_MISMATCH),
)


def _provider_for(kind: str) -> FakeRepositoryTableAccessProvider:
    table = catalog_table("items", (int_id_column(), text_column("name", 1)))
    rows: dict[str, tuple[tuple[object | None, ...], ...]] = {"items": ((1, "a"),)}
    catalog = make_catalog((table,))
    hidden = hidden_summary_for(catalog, rows)
    if kind == "missing":
        return FakeRepositoryTableAccessProvider(catalog=catalog, hidden=None, rows=rows)
    if kind == "corrupt":
        return FakeRepositoryTableAccessProvider(
            catalog=catalog, hidden=hidden, rows=rows, hidden_corrupt=True
        )
    if kind == "version":
        hidden = hidden_summary_for(
            catalog, rows, table_ruleset_version=TABLE_RULESET_VERSION + 1
        )
        return FakeRepositoryTableAccessProvider(catalog=catalog, hidden=hidden, rows=rows)
    if kind == "snapshot_digest":
        hidden = hidden_summary_for(catalog, rows, mutate_snapshot_digest=True)
        return FakeRepositoryTableAccessProvider(catalog=catalog, hidden=hidden, rows=rows)
    if kind == "raw_digest":
        hidden = hidden_summary_for(catalog, rows, mutate_raw_digest_table="items")
        return FakeRepositoryTableAccessProvider(catalog=catalog, hidden=hidden, rows=rows)
    if kind == "schema":
        shifted = catalog_table(
            "items",
            (int_id_column(), text_column("other", 1)),
        )
        mismatched = make_catalog((shifted,))
        return FakeRepositoryTableAccessProvider(catalog=mismatched, hidden=hidden, rows=rows)
    raise AssertionError(kind)


@pytest.mark.parametrize(("kind", "code"), HIDDEN_SUMMARY_FAULTS)
def test_hidden_summary_faults_fail_closed_without_snapshot(
    kind: str, code: MaterializationDiagnosticCode
) -> None:
    policy = (
        MaterializationPolicy.READERS_REQUIRED
        if kind == "raw_digest"
        else MaterializationPolicy.DESCRIPTOR_ONLY
    )
    result = materialize_ref(_provider_for(kind), policy=policy)
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.summary is None
    assert result.table_set is None
    assert result.diagnostics[0].code is code


def test_parser_version_mismatch_fails_closed() -> None:
    table = catalog_table("items", (int_id_column(),))
    catalog = make_catalog((table,))
    rows = {"items": ((1,),)}
    hidden = hidden_summary_for(catalog, rows, parser_version=PARSER_VERSION)
    provider = FakeRepositoryTableAccessProvider(catalog=catalog, hidden=hidden, rows=rows)
    result = materialize_ref(provider, parser_version=PARSER_VERSION + 1)
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.diagnostics[0].code is (
        MaterializationDiagnosticCode.HIDDEN_SUMMARY_VERSION_MISMATCH
    )


def test_cache_hit_still_validates_hidden_summary() -> None:
    table = catalog_table("items", (int_id_column(), text_column("name", 1)))
    rows = {"items": ((1, "a"),)}
    catalog = make_catalog((table,), cache_hit=True)
    hidden = hidden_summary_for(catalog, rows, mutate_snapshot_digest=True)
    provider = FakeRepositoryTableAccessProvider(catalog=catalog, hidden=hidden, rows=rows)
    result = materialize_ref(provider)
    assert catalog.cache_hit is True
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.diagnostics[0].code is MaterializationDiagnosticCode.HIDDEN_SUMMARY_CORRUPT


def test_cache_hit_success_still_uses_hidden_summary() -> None:
    table = catalog_table("items", (int_id_column(), text_column("name", 1)))
    rows = {"items": ((1, "a"),)}
    catalog = make_catalog((table,), cache_hit=True)
    hidden = hidden_summary_for(catalog, rows)
    provider = FakeRepositoryTableAccessProvider(catalog=catalog, hidden=hidden, rows=rows)
    result = materialize_ref(provider)
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.snapshot is not None
    assert result.snapshot.snapshot_id == hidden.snapshot_id
    assert result.summary is not None
    restored = result.summary.tables[0]
    assert restored.compare_schema_digest == hidden.tables[0].compare_schema_digest
    assert restored.raw_content_digest == hidden.tables[0].raw_content_digest


def test_does_not_rebuild_summary_from_catalog_rows() -> None:
    table = catalog_table("items", (int_id_column(), text_column("name", 1)))
    rows = {"items": ((1, "a"),)}
    catalog = make_catalog((table,))
    hidden = hidden_summary_for(catalog, rows)
    mutated = dataclasses.replace(hidden, snapshot_id="snapffffffffffffffffffffffffffffab")
    # Keep digests identical so a reconstructor would still succeed; identity must
    # come from the hidden payload, not a newly minted snapshot_id.
    provider = FakeRepositoryTableAccessProvider(catalog=catalog, hidden=mutated, rows=rows)
    result = materialize_ref(provider)
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.snapshot is not None
    assert result.snapshot.snapshot_id == "snapffffffffffffffffffffffffffffab"
