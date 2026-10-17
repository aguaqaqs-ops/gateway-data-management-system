"""Business SQL+XML composition, identity, preservation, and atomicity tests."""

from __future__ import annotations

from pathlib import Path

from gateway_backend.capabilities.composite_signal.contracts import (
    COMPOSITE_SIGNAL_POINT_TABLE,
    CompositeSignalPointRow,
    CompositeSignalResult,
    CompositeSignalStatus,
    empty_composite_logic_source,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    MaterializationDiagnosticCode,
    MaterializationPolicy,
    SnapshotMaterializationStatus,
)
from gateway_backend.capabilities.table_access.contracts import ParseStatus, ParserInvocationContext
from tests.support.snapshot_materialization import (
    load_sql,
    materialize_business,
    materialize_sql,
    summary_payload,
)
from tests.support.table_access_fixtures import load_text as load_table_access_text
from tests.support.table_access_xml import parse_xml_text

_MINIMAL_XML = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "golden"
    / "composite-signal"
    / "xml"
    / "valid"
    / "s3-minimal-logic"
    / "input.xml"
)
_EMPTY_XML = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "golden"
    / "composite-signal"
    / "xml"
    / "valid"
    / "s3-empty-logic-set"
    / "input.xml"
)
_SPECIAL_SQL = "business/valid/s3-special-device/input.sql"


class CountCancel:
    def __init__(self, trip_after: int) -> None:
        self.trip_after = trip_after
        self.calls = 0

    def is_set(self) -> bool:
        self.calls += 1
        return self.calls >= self.trip_after


def _minimal_xml() -> str:
    return _MINIMAL_XML.read_text(encoding="utf-8")


def _empty_xml() -> str:
    return _EMPTY_XML.read_text(encoding="utf-8")


def test_business_bind_publishes_derived_table_without_rewriting_sql() -> None:
    sql = load_sql(_SPECIAL_SQL)
    result = materialize_business(sql, _minimal_xml(), policy=MaterializationPolicy.READERS_REQUIRED)
    sql_only = materialize_sql(sql, policy=MaterializationPolicy.READERS_REQUIRED)
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.snapshot is not None
    assert result.summary is not None
    assert sql_only.summary is not None
    names = [table.table_name for table in result.summary.tables]
    assert names[-1] == COMPOSITE_SIGNAL_POINT_TABLE
    assert "device" in names
    assert "device_st" in names
    derived = next(table for table in result.summary.tables if table.table_name == COMPOSITE_SIGNAL_POINT_TABLE)
    assert derived.row_count == 2
    assert derived.primary_key_columns == ("source_table", "point_gid")
    assert derived.compare_key_columns == ("source_table", "point_gid")
    source_table_column = next(column for column in derived.columns if column.name == "source_table")
    assert source_table_column.scalar_type == "VARCHAR(64)"
    sql_tables = {table.table_name: table for table in sql_only.summary.tables}
    for table in result.summary.tables:
        if table.table_name == COMPOSITE_SIGNAL_POINT_TABLE:
            continue
        original = sql_tables[table.table_name]
        assert table.raw_content_digest == original.raw_content_digest
        assert table.row_count == original.row_count
    assert result.table_set is not None
    derived_reader = next(
        table.reader for table in result.table_set.tables if table.descriptor.table_name == COMPOSITE_SIGNAL_POINT_TABLE
    )
    assert derived_reader is not None
    rows = tuple(derived_reader.iter_rows())
    assert len(rows) == 2
    device_reader = next(
        table.reader for table in result.table_set.tables if table.descriptor.table_name == "device_st"
    )
    assert device_reader is not None
    device_rows = tuple(device_reader.iter_rows())
    assert len(device_rows) == 3


def test_sql_only_empty_and_present_xml_identities_differ() -> None:
    sql = load_sql(_SPECIAL_SQL)
    sql_only = materialize_sql(sql)
    missing = materialize_business(sql)
    present_empty = materialize_business(sql, _empty_xml())
    present_logic = materialize_business(sql, _minimal_xml())
    assert sql_only.snapshot is not None
    assert missing.snapshot is not None
    assert present_empty.snapshot is not None
    assert present_logic.snapshot is not None
    identities = {
        sql_only.snapshot.snapshot_digest,
        missing.snapshot.snapshot_digest,
        present_empty.snapshot.snapshot_digest,
        present_logic.snapshot.snapshot_digest,
    }
    assert len(identities) == 4
    assert missing.snapshot.source_context.composite_logic_source_digest == (
        empty_composite_logic_source().composite_logic_source_digest
    )
    assert sql_only.snapshot.source_context.composite_logic_source_digest is None


def test_business_digest_is_deterministic() -> None:
    sql = load_sql(_SPECIAL_SQL)
    xml = _minimal_xml()
    left = materialize_business(sql, xml)
    right = materialize_business(sql, xml)
    assert summary_payload(left) == summary_payload(right)


def test_empty_derived_table_is_still_published() -> None:
    sql = "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1);"
    result = materialize_business(sql, _empty_xml())
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.summary is not None
    derived = next(table for table in result.summary.tables if table.table_name == COMPOSITE_SIGNAL_POINT_TABLE)
    assert derived.row_count == 0


def test_business_failure_does_not_publish_snapshot_or_derived_table() -> None:
    sql = load_sql(_SPECIAL_SQL)
    xml = '<Logic_Set><Express Name="missing" Operator_Type="+"><Point Name="x"/></Express></Logic_Set>'
    result = materialize_business(sql, xml)
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.summary is None
    assert result.table_set is None
    assert result.diagnostics[0].code is MaterializationDiagnosticCode.COMPOSITE_LOGIC_FAILED


def test_partial_sql_with_healthy_device_stays_partial() -> None:
    sql = load_sql("business/partial/s3-partial-with-device/input.sql")
    result = materialize_business(sql, _minimal_xml())
    assert result.status is SnapshotMaterializationStatus.PARTIAL
    assert result.snapshot is not None
    assert result.summary is not None
    names = {table.table_name: table for table in result.summary.tables}
    assert COMPOSITE_SIGNAL_POINT_TABLE in names
    assert names[COMPOSITE_SIGNAL_POINT_TABLE].row_count == 1
    assert names["bad"].degraded_reason is not None


def test_failed_device_table_fails_the_whole_business_result() -> None:
    sql = load_sql("business/partial/s3-device-failed/input.sql")
    sql_only = materialize_sql(sql)
    assert sql_only.status is SnapshotMaterializationStatus.PARTIAL
    result = materialize_business(sql, _empty_xml())
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.diagnostics[0].code is MaterializationDiagnosticCode.COMPOSITE_CATALOG_UNAVAILABLE


def test_xml_failure_is_atomic_even_with_healthy_sql() -> None:
    sql = load_sql(_SPECIAL_SQL)
    parsed = parse_xml_text(load_table_access_text("xml/security/s1-doctype-rejected/input.xml"))
    assert parsed.status is ParseStatus.FAILED
    result = materialize_business(sql, parsed)
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.diagnostics[0].code is MaterializationDiagnosticCode.XML_DOCUMENT_FAILED


def test_descriptor_only_omits_business_table_set() -> None:
    result = materialize_business(
        load_sql(_SPECIAL_SQL),
        _minimal_xml(),
        policy=MaterializationPolicy.DESCRIPTOR_ONLY,
    )
    assert result.status is SnapshotMaterializationStatus.COMPLETE
    assert result.table_set is None
    assert result.summary is not None
    assert any(table.table_name == COMPOSITE_SIGNAL_POINT_TABLE for table in result.summary.tables)


def test_artifacts_required_fails_closed() -> None:
    result = materialize_business(
        load_sql(_SPECIAL_SQL),
        _minimal_xml(),
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
    )
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.diagnostics[0].code is MaterializationDiagnosticCode.ARTIFACT_STORE_REQUIRED


def test_identity_violation_fails_without_derived_table() -> None:
    sql = (
        "CREATE TABLE device (gid BIGINT NOT NULL PRIMARY KEY, dev_addr INT NOT NULL, "
        "description VARCHAR(64) NOT NULL);"
        "INSERT INTO device VALUES (1, 1, 'ordinary');"
    )
    result = materialize_business(sql, _empty_xml())
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.diagnostics[0].code is MaterializationDiagnosticCode.COMPOSITE_LOGIC_FAILED


def test_business_materialization_rejects_oversized_composite_source_table(monkeypatch: pytest.MonkeyPatch) -> None:
    from gateway_backend.capabilities.snapshot_materialization import compose

    oversized_row = CompositeSignalPointRow(
        source_table="t" * 65,
        point_gid=1,
        dev_addr=65532,
        device_gid=1,
        point_name="top",
        point_payload_json="{}",
        formula_digest=None,
        formula_ast_json=None,
    )
    monkeypatch.setattr(
        compose,
        "materialize_composite_signal",
        lambda _request: CompositeSignalResult(
            status=CompositeSignalStatus.COMPLETE,
            diagnostics=(),
            rows=(oversized_row,),
        ),
    )

    result = materialize_business(load_sql(_SPECIAL_SQL), _empty_xml())

    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.summary is None
    assert result.table_set is None
    assert result.diagnostics[0].code is MaterializationDiagnosticCode.COMPOSITE_LOGIC_FAILED
    assert result.diagnostics[0].message == (
        "composite source_table exceeds VARCHAR(64) maximum length of 64 characters"
    )


def test_business_cancel_does_not_publish_snapshot() -> None:
    result = materialize_business(
        load_sql(_SPECIAL_SQL),
        _minimal_xml(),
        context=ParserInvocationContext(CountCancel(1)),
    )
    assert result.status is SnapshotMaterializationStatus.FAILED
    assert result.snapshot is None
    assert result.diagnostics[0].code is MaterializationDiagnosticCode.MATERIALIZATION_CANCELLED
