"""Unit tests for compiled Arrow table plans and single normalization."""

from __future__ import annotations

import datetime as dt
import decimal
import traceback
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import pyarrow as pa  # type: ignore[import-untyped]
import pytest

from gateway_repository_contracts import UnknownTypePolicy
from gateway_repository_service.arrow_mapping import (
    ColumnCatalog,
    CompiledTablePlan,
    NormalizedRow,
    SqlValueConversionError,
    TableCatalog,
    UnknownSqlTypeError,
    arrow_type,
    compile_table_plan,
    record_batch,
)
from gateway_repository_service.candidate_a.dolt_cli import CandidateADoltCli
from gateway_repository_service.candidate_a.sql import _tagged_select_list
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import CommandResult, DoltRunner
from gateway_repository_service.settings import RepositoryServiceSettings


def _table(
    name: str,
    columns: tuple[ColumnCatalog, ...],
    row_count: int = 0,
) -> TableCatalog:
    return TableCatalog(name=name, columns=columns, row_count=row_count)


def test_compile_table_plan_calls_arrow_type_once_per_column() -> None:
    columns = (
        ColumnCatalog("a", "INT", False, 1),
        ColumnCatalog("b", "BIGINT", True, None),
        ColumnCatalog("c", "VARCHAR(32)", True, None),
    )
    catalog = _table("records", columns)
    call_count = 0

    def counting_arrow_type(sql_type: str, policy: UnknownTypePolicy) -> tuple[pa.DataType, dict[bytes, bytes]]:
        nonlocal call_count
        call_count += 1
        return arrow_type(sql_type, policy)

    with patch(
        "gateway_repository_service.arrow_mapping.arrow_type",
        side_effect=counting_arrow_type,
    ):
        plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)

    assert call_count == len(columns)
    assert plan.expected_schema == pa.schema([column_plan.field for column_plan in plan.columns])


def test_normalize_and_record_batch_converter_count_equals_rows_times_columns() -> None:
    columns = (
        ColumnCatalog("id", "INT", False, 1),
        ColumnCatalog("flag", "BOOLEAN", True, None),
    )
    catalog = _table("records", columns)
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    converter_calls = 0
    spied_columns = []
    for column_plan in plan.columns:
        original = column_plan.converter

        def make_wrapped(conv: Callable[[object], object]) -> Callable[[object], object]:
            def wrapped(raw: object) -> object:
                nonlocal converter_calls
                converter_calls += 1
                return conv(raw)

            return wrapped

        spied_columns.append(
            column_plan.__class__(
                field=column_plan.field,
                column=column_plan.column,
                converter=make_wrapped(original),
                hex_cell=column_plan.hex_cell,
                bit_width=column_plan.bit_width,
            )
        )
    spied_plan = CompiledTablePlan(
        catalog=plan.catalog,
        columns=tuple(spied_columns),
        expected_schema=plan.expected_schema,
    )

    raw_rows = [(1, "1"), (2, "0"), (3, "1")]
    normalized = [spied_plan.normalize_row(row) for row in raw_rows]
    spied_plan.record_batch(normalized)

    assert converter_calls == len(raw_rows) * len(columns)


def test_record_batch_schema_matches_plan_expected_schema() -> None:
    catalog = _table(
        "records",
        (
            ColumnCatalog("id", "INT UNSIGNED", False, 1),
            ColumnCatalog("payload", "BINARY(4)", True, None),
        ),
    )
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    batch = plan.record_batch([plan.normalize_row((42, "0x0102"))])
    assert batch.schema.equals(plan.expected_schema)


def test_sql_value_conversion_error_includes_table_without_raw_value() -> None:
    catalog = _table("records", (ColumnCatalog("event_date", "DATE", True, None),), 1)
    with pytest.raises(SqlValueConversionError) as exc_info:
        record_batch(catalog, [("not-a-date",)], UnknownTypePolicy.STRINGIFY)
    assert exc_info.value.table == "records"
    assert exc_info.value.column == "event_date"
    assert "not-a-date" not in str(exc_info.value)


NULLABLE_VIOLATIONS = (
    ("INT", False, None),
    ("BIGINT", False, None),
    ("BOOLEAN", False, None),
)


@pytest.mark.parametrize(("sql_type", "nullable", "raw_value"), NULLABLE_VIOLATIONS)
def test_non_nullable_column_rejects_null(
    sql_type: str,
    nullable: bool,
    raw_value: object,
) -> None:
    catalog = _table(
        "records",
        (ColumnCatalog("value", sql_type, nullable, 1),),
    )
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    with pytest.raises(SqlValueConversionError) as exc_info:
        plan.normalize_row((raw_value,))
    assert exc_info.value.table == "records"


MEDIUMINT_BOUNDARY_CASES = (
    ("MEDIUMINT", -8388608, False),
    ("MEDIUMINT", 8388607, False),
    ("MEDIUMINT", -8388609, True),
    ("MEDIUMINT", 8388608, True),
    ("MEDIUMINT UNSIGNED", 0, False),
    ("MEDIUMINT UNSIGNED", 16777215, False),
    ("MEDIUMINT UNSIGNED", -1, True),
    ("MEDIUMINT UNSIGNED", 16777216, True),
)


@pytest.mark.parametrize(("sql_type", "value", "should_fail"), MEDIUMINT_BOUNDARY_CASES)
def test_mediumint_logical_range(
    sql_type: str,
    value: int,
    should_fail: bool,
) -> None:
    catalog = _table("records", (ColumnCatalog("value", sql_type, False, 1),))
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    if should_fail:
        with pytest.raises(SqlValueConversionError):
            plan.normalize_row((value,))
    else:
        normalized = plan.normalize_row((value,))
        assert normalized.values[0] == value


BIT_BOUNDARY_CASES = (
    ("BIT(1)", "0x00", False),
    ("BIT(1)", "0x01", False),
    ("BIT(7)", "0x7f", False),
    ("BIT(7)", "0x80", True),
    ("BIT(8)", "0xff", False),
    ("BIT(9)", "0x0001", False),
    ("BIT(9)", "0x0200", True),
    ("BIT(64)", "0x" + "ff" * 8, False),
)


@pytest.mark.parametrize(("sql_type", "raw_value", "should_fail"), BIT_BOUNDARY_CASES)
def test_bit_width_and_unused_high_bits(
    sql_type: str,
    raw_value: str,
    should_fail: bool,
) -> None:
    catalog = _table("records", (ColumnCatalog("flags", sql_type, True, None),))
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    if should_fail:
        with pytest.raises(SqlValueConversionError):
            plan.normalize_row((raw_value,))
    else:
        plan.normalize_row((raw_value,))


def test_bit_value_exceeding_declared_width_fails() -> None:
    catalog = _table("records", (ColumnCatalog("flags", "BIT(4)", True, None),))
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    with pytest.raises(SqlValueConversionError):
        plan.normalize_row(("0x1234",))


def test_decimal128_and_decimal256_conversion() -> None:
    catalog = _table(
        "records",
        (
            ColumnCatalog("small", "DECIMAL(10,2)", True, None),
            ColumnCatalog("large", "DECIMAL(40,2)", True, None),
        ),
    )
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    normalized = plan.normalize_row(("123.45", "99999999999999999999999999999999.99"))
    assert normalized.values[0] == decimal.Decimal("123.45")
    assert normalized.values[1] == decimal.Decimal("99999999999999999999999999999999.99")
    batch = plan.record_batch([normalized])
    assert batch.schema.field("small").type == pa.decimal128(10, 2)
    assert batch.schema.field("large").type == pa.decimal256(40, 2)


def test_temporal_fsp_and_timestamp_timezone() -> None:
    catalog = _table(
        "records",
        (
            ColumnCatalog("event_time", "TIME(6)", True, None),
            ColumnCatalog("event_dt", "DATETIME(3)", True, None),
            ColumnCatalog("event_ts", "TIMESTAMP(6)", True, None),
        ),
    )
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    normalized = plan.normalize_row(
        (
            "12:34:56.123456",
            "2024-01-02 03:04:05.123",
            "2024-01-02 03:04:05.123456",
        )
    )
    assert normalized.values[0] == dt.timedelta(hours=12, minutes=34, seconds=56, microseconds=123456)
    assert normalized.values[1] == dt.datetime(2024, 1, 2, 3, 4, 5, 123000)
    timestamp = normalized.values[2]
    assert isinstance(timestamp, dt.datetime)
    assert timestamp.tzinfo == dt.timezone.utc


def test_binary_and_hex_malformed_values_fail() -> None:
    catalog = _table("records", (ColumnCatalog("payload", "BINARY(4)", True, None),))
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    with pytest.raises(SqlValueConversionError):
        plan.normalize_row(("0x0",))


def test_unknown_type_reject_fails_at_compile() -> None:
    catalog = _table("records", (ColumnCatalog("value", "ENUM('a')", True, None),))
    with pytest.raises(UnknownSqlTypeError):
        compile_table_plan(catalog, UnknownTypePolicy.REJECT)


def test_unknown_stringify_metadata_and_null_preservation() -> None:
    catalog = _table("records", (ColumnCatalog("value", "ENUM('a','b')", True, None),))
    plan = compile_table_plan(catalog, UnknownTypePolicy.STRINGIFY)
    field = plan.expected_schema.field("value")
    assert field.type == pa.large_string()
    assert field.metadata[b"gateway.sql_type"] == b"ENUM('a','b')"
    assert field.metadata[b"gateway.lossy"] == b"true"
    normalized = plan.normalize_row((None,))
    assert normalized.values[0] is None


def test_stringify_known_type_conversion_failure_raises_sql_value_conversion_error() -> None:
    catalog = _table("records", (ColumnCatalog("event_date", "DATE", True, None),))
    with pytest.raises(SqlValueConversionError) as exc_info:
        record_batch(catalog, [("not-a-date",)], UnknownTypePolicy.STRINGIFY)
    assert exc_info.value.table == "records"


def test_normalized_row_logical_byte_accounting() -> None:
    catalog = _table("records", (ColumnCatalog("payload", "VARCHAR(32)", True, None),))
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    normalized = plan.normalize_row(("hello",))
    assert normalized.logical_size_bytes == len("hello".encode("utf-8"))


def test_batch_row_bound_and_flush_boundary() -> None:
    row_bound = 4
    byte_bound = 16
    catalog = _table(
        "records",
        (ColumnCatalog("id", "INT", False, 1),),
        row_count=10,
    )
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    batches: list[pa.RecordBatch] = []
    pending: list[NormalizedRow] = []
    pending_bytes = 0

    for index in range(10):
        normalized = plan.normalize_row((index,))
        row_bytes = normalized.logical_size_bytes
        if pending and (
            len(pending) >= row_bound or pending_bytes + row_bytes > byte_bound
        ):
            batches.append(plan.record_batch(pending))
            pending = []
            pending_bytes = 0
        pending.append(normalized)
        pending_bytes += row_bytes
    if pending:
        batches.append(plan.record_batch(pending))

    assert all(batch.num_rows <= row_bound for batch in batches)
    assert sum(batch.num_rows for batch in batches) == 10


def test_oversized_single_row_occupies_own_batch() -> None:
    byte_bound = 8
    catalog = _table("records", (ColumnCatalog("payload", "VARCHAR(64)", True, None),))
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    small = plan.normalize_row(("tiny",))
    large = plan.normalize_row(("012345678901234567890",))

    batches: list[pa.RecordBatch] = []
    pending: list[NormalizedRow] = [small]
    pending_bytes = small.logical_size_bytes
    if pending_bytes + large.logical_size_bytes > byte_bound:
        batches.append(plan.record_batch(pending))
        pending = []
    if large.logical_size_bytes > byte_bound:
        batches.append(plan.record_batch([large]))
    else:
        pending.append(large)
    if pending:
        batches.append(plan.record_batch(pending))

    assert len(batches) >= 2
    assert any(batch.num_rows == 1 for batch in batches)
    oversized_values = [
        batch.column(0).to_pylist()[0]
        for batch in batches
        if batch.num_rows == 1 and batch.column(0).to_pylist()[0] == "012345678901234567890"
    ]
    assert oversized_values == ["012345678901234567890"]


def test_compatibility_record_batch_converts_each_cell_once() -> None:
    catalog = _table(
        "records",
        (
            ColumnCatalog("id", "INT", False, 1),
            ColumnCatalog("flag", "BOOLEAN", True, None),
        ),
    )
    converter_calls = 0
    original_compile = compile_table_plan

    def counting_compile(
        table_catalog: TableCatalog,
        policy: UnknownTypePolicy,
    ) -> CompiledTablePlan:
        plan = original_compile(table_catalog, policy)
        spied_columns = []
        for column_plan in plan.columns:
            original = column_plan.converter

            def make_wrapped(conv: Callable[[object], object]) -> Callable[[object], object]:
                def wrapped(raw: object) -> object:
                    nonlocal converter_calls
                    converter_calls += 1
                    return conv(raw)

                return wrapped

            spied_columns.append(
                column_plan.__class__(
                    field=column_plan.field,
                    column=column_plan.column,
                    converter=make_wrapped(original),
                    hex_cell=column_plan.hex_cell,
                    bit_width=column_plan.bit_width,
                )
            )
        return CompiledTablePlan(
            catalog=plan.catalog,
            columns=tuple(spied_columns),
            expected_schema=plan.expected_schema,
        )

    with patch(
        "gateway_repository_service.arrow_mapping.compile_table_plan",
        side_effect=counting_compile,
    ):
        record_batch(catalog, [(1, "1"), (2, "0")], UnknownTypePolicy.REJECT)

    assert converter_calls == 4


def test_normalize_row_does_not_call_arrow_type_after_compile() -> None:
    columns = (
        ColumnCatalog("id", "INT", False, 1),
        ColumnCatalog("flag", "BOOLEAN", True, None),
    )
    catalog = _table("records", columns)
    call_count = 0

    def counting_arrow_type(sql_type: str, policy: UnknownTypePolicy) -> tuple[pa.DataType, dict[bytes, bytes]]:
        nonlocal call_count
        call_count += 1
        return arrow_type(sql_type, policy)

    with patch(
        "gateway_repository_service.arrow_mapping.arrow_type",
        side_effect=counting_arrow_type,
    ):
        plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
        calls_after_compile = call_count
        for raw in ((1, "1"), (2, "0"), (3, "1")):
            plan.normalize_row(raw)

    assert calls_after_compile == len(columns)
    assert call_count == calls_after_compile


def test_candidate_a_stream_compiles_plan_once_per_table(tmp_path: Path) -> None:
    table = _table(
        "records",
        (
            ColumnCatalog("id", "INT", False, 1),
            ColumnCatalog("flag", "BOOLEAN", True, None),
        ),
        row_count=4,
    )
    plan = compile_table_plan(table, UnknownTypePolicy.REJECT)
    _, header = _tagged_select_list(plan)
    stream_lines = [
        ",".join(header),
        "0,1,0,1",
        "0,2,0,0",
        "0,3,1,",
        "0,4,0,1",
    ]
    layout = DurableLayout.create(tmp_path / "root")
    settings = RepositoryServiceSettings()
    repository = layout.staging_artifacts / "stream-repo"
    repository.mkdir(parents=True, exist_ok=True)
    runner = MagicMock(spec=DoltRunner)
    stream = MagicMock()
    stream.__iter__ = MagicMock(
        return_value=iter(line.encode("utf-8") for line in stream_lines)
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
    runner.stream.return_value = stream
    cli = CandidateADoltCli(settings, layout, repository, runner)

    arrow_calls = 0

    def counting_arrow_type(
        sql_type: str,
        policy: UnknownTypePolicy,
    ) -> tuple[pa.DataType, dict[bytes, bytes]]:
        nonlocal arrow_calls
        arrow_calls += 1
        return arrow_type(sql_type, policy)

    with patch(
        "gateway_repository_service.arrow_mapping.arrow_type",
        side_effect=counting_arrow_type,
    ):
        batches = list(
            cli.stream_table(
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                table,
                UnknownTypePolicy.REJECT,
            )
        )

    assert arrow_calls == len(table.columns)
    assert sum(batch.num_rows for batch in batches) == 4
    assert batches[0].schema.field(0).type == pa.int32()


SENTINEL_RAW_VALUE = "SECRET_RAW_SENTINEL_42"


class _StrFailure:
    def __str__(self) -> str:
        raise ValueError(SENTINEL_RAW_VALUE)


class _StrRuntimeFailure:
    def __str__(self) -> str:
        raise RuntimeError(SENTINEL_RAW_VALUE)


MALFORMED_VALUE_FAULTS = (
    ("amount", "DECIMAL(10,2)", SENTINEL_RAW_VALUE, UnknownTypePolicy.REJECT),
    ("event_time", "TIME(6)", "12:34", UnknownTypePolicy.REJECT),
    ("flags", "BIT(7)", "0x80", UnknownTypePolicy.REJECT),
    ("flags", "BIT(4)", "0x1234", UnknownTypePolicy.REJECT),
    ("value", "ENUM('a','b')", _StrFailure(), UnknownTypePolicy.STRINGIFY),
    ("value", "ENUM('a','b')", _StrRuntimeFailure(), UnknownTypePolicy.STRINGIFY),
)


@pytest.mark.parametrize(
    ("column_name", "sql_type", "raw_value", "policy"),
    MALFORMED_VALUE_FAULTS,
)
def test_malformed_provider_values_are_typed_and_redacted(
    column_name: str,
    sql_type: str,
    raw_value: object,
    policy: UnknownTypePolicy,
) -> None:
    catalog = _table(
        "records",
        (ColumnCatalog(column_name, sql_type, True, None),),
    )
    plan = compile_table_plan(catalog, policy)
    with pytest.raises(SqlValueConversionError) as exc_info:
        plan.normalize_row((raw_value,))
    error = exc_info.value
    assert error.table == "records"
    assert error.column == column_name
    assert error.__cause__ is None
    rendered = str(error)
    assert SENTINEL_RAW_VALUE not in rendered
    assert SENTINEL_RAW_VALUE not in repr(error)
    traceback_text = "".join(
        traceback.format_exception(type(error), error, error.__traceback__)
    )
    assert SENTINEL_RAW_VALUE not in traceback_text


def test_unknown_stringify_runtime_str_failure_is_typed_and_redacted() -> None:
    catalog = _table(
        "records",
        (ColumnCatalog("value", "ENUM('a','b')", True, None),),
    )
    plan = compile_table_plan(catalog, UnknownTypePolicy.STRINGIFY)
    with pytest.raises(SqlValueConversionError) as exc_info:
        plan.normalize_row((_StrRuntimeFailure(),))
    error = exc_info.value
    assert error.__cause__ is None
    assert SENTINEL_RAW_VALUE not in str(error)
    assert SENTINEL_RAW_VALUE not in repr(error)


DECIMAL_SCALE_AND_EXPONENT_FAULTS = (
    ("DECIMAL(3,2)", "100", True),
    ("DECIMAL(3,2)", "12.3", True),
    ("DECIMAL(3,0)", "1E+3", True),
    ("DECIMAL(3,2)", "9.99", False),
    ("DECIMAL(3,2)", "0.01", False),
)


@pytest.mark.parametrize(("sql_type", "raw_value", "should_fail"), DECIMAL_SCALE_AND_EXPONENT_FAULTS)
def test_decimal_scale_padding_and_positive_exponent_boundaries(
    sql_type: str,
    raw_value: str,
    should_fail: bool,
) -> None:
    catalog = _table("records", (ColumnCatalog("amount", sql_type, False, 1),))
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    if should_fail:
        with pytest.raises(SqlValueConversionError):
            plan.normalize_row((raw_value,))
    else:
        plan.normalize_row((raw_value,))


def test_decimal128_maximum_precision_boundaries() -> None:
    max_38 = decimal.Decimal("9" * 38)
    max_38_2 = decimal.Decimal("9" * 36 + ".99")
    overflow_38 = decimal.Decimal("1" + "0" * 38)
    catalog_38_0 = _table("records", (ColumnCatalog("value", "DECIMAL(38,0)", False, 1),))
    catalog_38_2 = _table("records", (ColumnCatalog("value", "DECIMAL(38,2)", False, 1),))
    plan_38_0 = compile_table_plan(catalog_38_0, UnknownTypePolicy.REJECT)
    plan_38_2 = compile_table_plan(catalog_38_2, UnknownTypePolicy.REJECT)
    plan_38_0.normalize_row((max_38,))
    plan_38_2.normalize_row((max_38_2,))
    with pytest.raises(SqlValueConversionError):
        plan_38_0.normalize_row((overflow_38,))


def test_decimal256_maximum_precision_boundaries() -> None:
    max_40_0 = decimal.Decimal("9" * 40)
    max_40_2 = decimal.Decimal("9" * 38 + ".99")
    max_65_30 = decimal.Decimal("9" * 35 + "." + "9" * 30)
    catalog_40_0 = _table("records", (ColumnCatalog("value", "DECIMAL(40,0)", False, 1),))
    catalog_40_2 = _table("records", (ColumnCatalog("value", "DECIMAL(40,2)", False, 1),))
    catalog_65_30 = _table("records", (ColumnCatalog("value", "DECIMAL(65,30)", False, 1),))
    compile_table_plan(catalog_40_0, UnknownTypePolicy.REJECT).normalize_row((max_40_0,))
    compile_table_plan(catalog_40_2, UnknownTypePolicy.REJECT).normalize_row((max_40_2,))
    compile_table_plan(catalog_65_30, UnknownTypePolicy.REJECT).normalize_row((max_65_30,))


def test_decimal_lossless_trailing_zero_quantization() -> None:
    catalog = _table("records", (ColumnCatalog("amount", "DECIMAL(10,2)", False, 1),))
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    plan.normalize_row(("1.230",))
    plan.normalize_row(("12.30",))
    with pytest.raises(SqlValueConversionError):
        plan.normalize_row(("12.345",))


def test_datetime_iso_t_separator_without_timezone_is_valid() -> None:
    catalog = _table("records", (ColumnCatalog("event_dt", "DATETIME(6)", True, None),))
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    normalized = plan.normalize_row(("2024-01-02T03:04:05.123456",))
    assert normalized.values[0] == dt.datetime(2024, 1, 2, 3, 4, 5, 123456)


def test_native_temporal_values_enforce_fsp() -> None:
    time_catalog = _table("records", (ColumnCatalog("event_time", "TIME(3)", True, None),))
    datetime_catalog = _table("records", (ColumnCatalog("event_dt", "DATETIME(3)", True, None),))
    timestamp_catalog = _table("records", (ColumnCatalog("event_ts", "TIMESTAMP(3)", True, None),))
    time_plan = compile_table_plan(time_catalog, UnknownTypePolicy.REJECT)
    datetime_plan = compile_table_plan(datetime_catalog, UnknownTypePolicy.REJECT)
    timestamp_plan = compile_table_plan(timestamp_catalog, UnknownTypePolicy.REJECT)
    bad_delta = dt.timedelta(hours=1, minutes=2, seconds=3, microseconds=123456)
    bad_dt = dt.datetime(2024, 1, 2, 3, 4, 5, 123456)
    bad_ts = dt.datetime(2024, 1, 2, 3, 4, 5, 123456, tzinfo=dt.timezone.utc)
    with pytest.raises(SqlValueConversionError):
        time_plan.normalize_row((bad_delta,))
    with pytest.raises(SqlValueConversionError):
        datetime_plan.normalize_row((bad_dt,))
    with pytest.raises(SqlValueConversionError):
        timestamp_plan.normalize_row((bad_ts,))


DEFAULT_FSP_FAULTS = (
    ("TIME", "12:34:56.1", True),
    ("DATETIME", "2024-01-02 03:04:05.1", True),
    ("TIMESTAMP", "2024-01-02 03:04:05.1", True),
    ("TIME", "12:34:56", False),
)


@pytest.mark.parametrize(("sql_type", "raw_value", "should_fail"), DEFAULT_FSP_FAULTS)
def test_temporal_default_fsp_is_zero(
    sql_type: str,
    raw_value: str,
    should_fail: bool,
) -> None:
    catalog = _table("records", (ColumnCatalog("event_time", sql_type, True, None),))
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    if should_fail:
        with pytest.raises(SqlValueConversionError):
            plan.normalize_row((raw_value,))
    else:
        plan.normalize_row((raw_value,))


TIME_GRAMMAR_FAULTS = (
    ("839:00:00", True),
    ("--1:02:03", True),
    ("838:59:59", False),
    ("-838:59:59", False),
)


@pytest.mark.parametrize(("raw_value", "should_fail"), TIME_GRAMMAR_FAULTS)
def test_time_hour_range_and_sign_grammar(raw_value: str, should_fail: bool) -> None:
    catalog = _table("records", (ColumnCatalog("event_time", "TIME(6)", True, None),))
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    if should_fail:
        with pytest.raises(SqlValueConversionError):
            plan.normalize_row((raw_value,))
    else:
        plan.normalize_row((raw_value,))


TEMPORAL_BOUNDARY_FAULTS = (
    ("TIME(3)", "12:34:56.123456", True),
    ("TIME(6)", "12:60:00", True),
    ("DATETIME(6)", "2024-01-02T03:04:05.123456+00:00", True),
    ("TIME(6)", "12:34:56.123456", False),
    ("DATETIME(6)", "2024-01-02 03:04:05.123456", False),
    ("DATETIME(6)", "2024-01-02T03:04:05.123456", False),
    ("TIMESTAMP(6)", "2024-01-02 03:04:05.123456", False),
)


@pytest.mark.parametrize(("sql_type", "raw_value", "should_fail"), TEMPORAL_BOUNDARY_FAULTS)
def test_temporal_values_enforce_fsp_component_ranges_and_timezone(
    sql_type: str,
    raw_value: str,
    should_fail: bool,
) -> None:
    catalog = _table("records", (ColumnCatalog("event_time", sql_type, True, None),))
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    if should_fail:
        with pytest.raises(SqlValueConversionError):
            plan.normalize_row((raw_value,))
    else:
        plan.normalize_row((raw_value,))


INTEGER_AND_DECIMAL_RANGE_FAULTS = (
    ("TINYINT", -128, False),
    ("TINYINT", 127, False),
    ("TINYINT", -129, True),
    ("TINYINT", 128, True),
    ("TINYINT UNSIGNED", 0, False),
    ("TINYINT UNSIGNED", 255, False),
    ("TINYINT UNSIGNED", 256, True),
    ("SMALLINT", -32768, False),
    ("SMALLINT", 32767, False),
    ("SMALLINT", -32769, True),
    ("INT", -2147483648, False),
    ("INT", 2147483647, False),
    ("INT", 2147483648, True),
    ("INT UNSIGNED", 4294967295, False),
    ("INT UNSIGNED", 4294967296, True),
    ("BIGINT", 9223372036854775807, False),
    ("BIGINT", 9223372036854775808, True),
    ("DECIMAL(5,2)", "123.45", False),
    ("DECIMAL(5,2)", "1234.56", True),
    ("DECIMAL(5,2)", "12.345", True),
)


@pytest.mark.parametrize(("sql_type", "raw_value", "should_fail"), INTEGER_AND_DECIMAL_RANGE_FAULTS)
def test_integer_and_decimal_boundaries_fail_during_normalization(
    sql_type: str,
    raw_value: object,
    should_fail: bool,
) -> None:
    catalog = _table("records", (ColumnCatalog("value", sql_type, False, 1),))
    plan = compile_table_plan(catalog, UnknownTypePolicy.REJECT)
    if should_fail:
        with pytest.raises(SqlValueConversionError):
            plan.normalize_row((raw_value,))
    else:
        normalized = plan.normalize_row((raw_value,))
        assert normalized.values[0] is not None


def test_candidate_a_stream_flush_and_oversized_boundaries(tmp_path: Path) -> None:
    table = _table(
        "records",
        (
            ColumnCatalog("id", "INT", False, 1),
            ColumnCatalog("payload", "VARCHAR(64)", True, None),
        ),
        row_count=5,
    )
    plan = compile_table_plan(table, UnknownTypePolicy.REJECT)
    _, header = _tagged_select_list(plan)
    large_payload = "012345678901234567890"
    stream_lines = [
        ",".join(header),
        "0,1,0,tiny",
        "0,2,0,tiny",
        "0,3,0,tiny",
        f"0,4,0,{large_payload}",
        "0,5,0,tiny",
    ]
    layout = DurableLayout.create(tmp_path / "root")
    settings = RepositoryServiceSettings(
        record_batch_rows=2,
        record_batch_bytes=16,
    )
    repository = layout.staging_artifacts / "stream-repo"
    repository.mkdir(parents=True, exist_ok=True)
    runner = MagicMock(spec=DoltRunner)
    stream = MagicMock()
    stream.__iter__ = MagicMock(
        return_value=iter(line.encode("utf-8") for line in stream_lines)
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
    runner.stream.return_value = stream
    cli = CandidateADoltCli(settings, layout, repository, runner)
    batches = list(
        cli.stream_table(
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            table,
            UnknownTypePolicy.REJECT,
        )
    )

    assert sum(batch.num_rows for batch in batches) == 5
    assert len(batches) >= 3
    assert any(batch.num_rows == 1 for batch in batches)
    oversized_batches = [
        batch
        for batch in batches
        if batch.num_rows == 1
        and batch.column("payload").to_pylist()[0] == large_payload
    ]
    assert oversized_batches
