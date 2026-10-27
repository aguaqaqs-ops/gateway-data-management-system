"""SQL-to-Snapshot golden, digest invariance, and ruleset tests."""

from __future__ import annotations

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    DegradedReason,
    MaterializationPolicy,
    MaterializationStage,
    SnapshotMaterializationStatus,
)
from gateway_backend.capabilities.source_package_staging.contracts import (
    NeverCancel,
    PackageKind,
    SourcePackageInput,
    StagingInvocationContext,
    StagingTransport,
    resolve_sql_dump_source,
)
from gateway_backend.capabilities.source_package_staging.staging import stage_source_package
from gateway_backend.capabilities.table_access.contracts import NeverCancel as ParserNeverCancel
from gateway_backend.capabilities.table_access.contracts import ParserInvocationContext
from gateway_backend.capabilities.table_access.sql import parse_sql
from gateway_backend.capabilities.table_rules.contracts import (
    TABLE_RULESET_VERSION,
    TableCompareKey,
    TableRulesetSnapshot,
)
from gateway_shared_kernel import NullScalar, SignedIntegerScalar, StringScalar, raw_blob_digest
from tests.support.snapshot_materialization import (
    load_expected,
    load_sql,
    materialize_sql,
    parse_fixture,
    summary_payload,
)
from tests.support.source_package_fixtures import pack_tar_gz
from tests.support.table_access_sql import sql_request

GOLDEN_CASES = (
    "sql/valid/s2-minimal-create-insert",
    "sql/valid/s2-duplicate-rows",
    "sql/valid/s2-keyless",
    "sql/valid/s2-null-and-types",
    "sql/partial/s2-unknown-type-mixed",
)


def test_golden_sql_to_snapshot_cases() -> None:
    for case in GOLDEN_CASES:
        result = materialize_sql(parse_fixture(f"{case}/input.sql"))
        assert summary_payload(result) == load_expected(f"{case}/expected.json"), case


def test_malformed_document_is_failed_without_snapshot() -> None:
    expected = load_expected("sql/malformed/s2-document-failed/expected.json")
    result = materialize_sql(parse_fixture("sql/malformed/s2-document-failed/input.sql"))
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.summary is None
    assert result.table_set is None
    assert [item.code.value for item in result.diagnostics] == expected["diagnostics"]


def test_row_order_does_not_change_content_digests() -> None:
    first = (
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, name VARCHAR(8) NULL);"
        "INSERT INTO t VALUES (1, 'a'), (2, 'b');"
    )
    second = (
        "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, name VARCHAR(8) NULL);"
        "INSERT INTO t VALUES (2, 'b'), (1, 'a');"
    )
    left = materialize_sql(first)
    right = materialize_sql(second)
    assert left.snapshot is not None and right.snapshot is not None
    assert left.snapshot.snapshot_digest == right.snapshot.snapshot_digest
    assert left.summary is not None and right.summary is not None
    assert left.summary.tables[0].raw_content_digest == right.summary.tables[0].raw_content_digest


def test_package_kind_does_not_enter_sql_snapshot_identity() -> None:
    sql = load_sql("sql/valid/s2-minimal-create-insert/input.sql").encode("utf-8")
    store = InMemoryArtifactStore()
    staged = stage_source_package(
        SourcePackageInput(
            package_kind=PackageKind.TAR_GZ,
            transport=StagingTransport.IDENTITY,
            context=StagingInvocationContext(NeverCancel()),
            payload=pack_tar_gz({"sql/dbcfg.sql": sql}),
        ),
        store,
    )
    assert staged.required_sql_document_ref is not None
    dump = resolve_sql_dump_source(staged.required_sql_document_ref)
    parsed = parse_sql(
        sql_request(sql, ParserInvocationContext(ParserNeverCancel()))
    )
    packaged = materialize_sql(parsed, sql_source_digest=dump.sql_source_digest)
    raw = materialize_sql(sql)
    assert packaged.snapshot is not None and raw.snapshot is not None
    assert packaged.snapshot.snapshot_digest == raw.snapshot.snapshot_digest
    assert dump.sql_source_digest == raw_blob_digest(sql)


def test_duplicate_rows_are_preserved() -> None:
    result = materialize_sql(parse_fixture("sql/valid/s2-duplicate-rows/input.sql"))
    assert result.summary is not None
    table = result.summary.tables[0]
    assert table.row_count == 3
    assert table.degraded_reason is DegradedReason.DUPLICATE_EFFECTIVE_KEY


def test_keyless_table_is_not_given_a_surrogate_key() -> None:
    result = materialize_sql(parse_fixture("sql/valid/s2-keyless/input.sql"))
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.summary is not None
    table = result.summary.tables[0]
    assert table.compare_key_columns == ()
    assert table.primary_key_columns == ()
    assert table.degraded_reason is DegradedReason.KEYLESS


def test_ruleset_compare_key_overrides_ddl_pk() -> None:
    sql = (
        "CREATE TABLE orders (id INT NOT NULL PRIMARY KEY, code VARCHAR(8) NOT NULL);"
        "INSERT INTO orders VALUES (1, 'a'), (2, 'a');"
    )
    ruleset = TableRulesetSnapshot(
        table_ruleset_version=TABLE_RULESET_VERSION,
        compare_keys=(TableCompareKey(canonical_table="orders", key_columns=("code",)),),
    )
    result = materialize_sql(sql, ruleset=ruleset)
    assert result.summary is not None
    table = result.summary.tables[0]
    assert table.primary_key_columns == ("id",)
    assert table.compare_key_columns == ("code",)
    assert table.degraded_reason is DegradedReason.DUPLICATE_EFFECTIVE_KEY


def test_null_and_scalar_types_are_preserved_on_reader() -> None:
    result = materialize_sql(
        parse_fixture("sql/valid/s2-null-and-types/input.sql"),
        policy=MaterializationPolicy.READERS_REQUIRED,
    )
    assert result.table_set is not None
    reader = result.table_set.tables[0].reader
    assert reader is not None
    rows = tuple(reader.iter_rows())
    assert isinstance(rows[0][0], SignedIntegerScalar)
    assert rows[0][0].decimal == "1"
    assert isinstance(rows[0][1], StringScalar)
    assert rows[0][3] == NullScalar()
    assert rows[1][1] == NullScalar()


def test_cache_miss_rebuild_matches_digest() -> None:
    sql = load_sql("sql/valid/s2-minimal-create-insert/input.sql")
    first = materialize_sql(sql)
    second = materialize_sql(sql)
    assert first.snapshot is not None and second.snapshot is not None
    assert first.snapshot.snapshot_digest == second.snapshot.snapshot_digest
    assert first.snapshot.snapshot_id != second.snapshot.snapshot_id


def test_provisional_omits_raw_content_digest() -> None:
    result = materialize_sql(
        parse_fixture("sql/valid/s2-minimal-create-insert/input.sql"),
        stage=MaterializationStage.PROVISIONAL,
    )
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.cache_trust_level.value == "PROVISIONAL"
    assert result.summary is not None
    assert result.summary.tables[0].raw_content_digest is None
