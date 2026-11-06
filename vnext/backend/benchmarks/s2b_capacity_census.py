"""Bounded census of existing parser Arrow buffers for S2b design input.

This reads one allow-listed SQL source at a time and reports the existing S2a
parser's Arrow C Stream buffers. It does not implement or estimate an IPC writer,
canonical projection, or process RSS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from pathlib import Path
from typing import Any

import pyarrow as pa
from gateway_compute._native import _init_kernel_native, _parse_sql_native

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MAX_SQL_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 2 * 1024 * 1024
T1_ARCHIVE = Path("/home/dev/gateway-real-dumps/packages/rd-t1-a-v1.tar.gz")
T1_SQL_SHA256 = "f8da5b9608981f91ba4cef66e593a6e2299386871d53af71ba203802140748f5"
T1_EXPECTED_COUNTS = {"tables": 132, "rows": 6_093, "cells": 151_751}
TYPE_FIXTURE = (
    REPOSITORY_ROOT
    / "vnext/fixtures/golden/snapshot-materialization/sql/valid/s2-null-and-types/input.sql"
)
TYPE_FIXTURE_SHA256 = "6a6d00571cb7d5a631a17b9a1f554f38c43854bf9eac869228ba0ed47f94d0f6"
T1_ARCHIVE_MEMBERS = {"sql/dbcfg.sql", "comps/logic/logics.xml"}


def _sha256_file(path: Path, *, limit: int) -> str:
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as stream:
        while chunk := stream.read(64 * 1024):
            total += len(chunk)
            if total > limit:
                raise ValueError(f"input file exceeds bounded size of {limit} bytes")
            digest.update(chunk)
    return digest.hexdigest()


def _read_t1_sql() -> tuple[bytes, dict[str, object]]:
    archive_size = T1_ARCHIVE.stat().st_size
    if archive_size > MAX_ARCHIVE_BYTES:
        raise ValueError("t1 archive exceeds its bounded compressed size")
    archive_sha256 = _sha256_file(T1_ARCHIVE, limit=MAX_ARCHIVE_BYTES)
    with tarfile.open(T1_ARCHIVE, mode="r|gz") as archive:
        observed_names: list[str] = []
        sql_utf8: bytes | None = None
        for member in archive:
            normalized_name = member.name.lstrip("/")
            observed_names.append(normalized_name)
            if len(observed_names) > len(T1_ARCHIVE_MEMBERS):
                raise ValueError("t1 archive contains more entries than the allow-list")
            if (
                normalized_name not in T1_ARCHIVE_MEMBERS
                or not member.isfile()
                or member.size <= 0
                or member.size > MAX_ARCHIVE_MEMBER_BYTES
            ):
                raise ValueError("t1 archive contains an unsupported or oversized entry")
            if normalized_name == "sql/dbcfg.sql":
                if sql_utf8 is not None or member.size > MAX_SQL_BYTES:
                    raise ValueError("t1 SQL member is duplicated or oversized")
                member_stream = archive.extractfile(member)
                if member_stream is None:
                    raise ValueError("t1 SQL member could not be read")
                with member_stream:
                    sql_utf8 = member_stream.read(MAX_SQL_BYTES + 1)
                if len(sql_utf8) != member.size:
                    raise ValueError("t1 SQL member length differs from its archive header")
        if len(observed_names) != len(T1_ARCHIVE_MEMBERS) or set(observed_names) != T1_ARCHIVE_MEMBERS:
            raise ValueError("t1 archive member set differs from the allow-listed package")
    if sql_utf8 is None or len(sql_utf8) > MAX_SQL_BYTES:
        raise ValueError("t1 SQL member length differs from its bounded archive header")
    sql_sha256 = hashlib.sha256(sql_utf8).hexdigest()
    if sql_sha256 != T1_SQL_SHA256:
        raise ValueError("t1 SQL member SHA256 differs from the verified S2a input")
    return sql_utf8, {
        "sample": "t1-v1-existing-package",
        "source": str(T1_ARCHIVE),
        "archive_bytes": archive_size,
        "archive_sha256": archive_sha256,
        "member": "sql/dbcfg.sql",
        "sql_bytes": len(sql_utf8),
        "sql_sha256": sql_sha256,
        "expected_s2a_parser_counts": T1_EXPECTED_COUNTS,
    }


def _read_type_fixture() -> tuple[bytes, dict[str, object]]:
    fixture = TYPE_FIXTURE.resolve(strict=True)
    if not fixture.is_relative_to(REPOSITORY_ROOT):
        raise ValueError("type fixture resolves outside the repository")
    fixture_size = fixture.stat().st_size
    if fixture_size <= 0 or fixture_size > MAX_SQL_BYTES:
        raise ValueError("type fixture is outside the bounded input size")
    sql_utf8 = fixture.read_bytes()
    if len(sql_utf8) > MAX_SQL_BYTES:
        raise ValueError("type fixture exceeded its bounded input size while reading")
    sql_sha256 = hashlib.sha256(sql_utf8).hexdigest()
    if sql_sha256 != TYPE_FIXTURE_SHA256:
        raise ValueError("type fixture SHA256 differs from the committed fixture")
    return sql_utf8, {
        "sample": "tracked-null-and-types-fixture",
        "source": fixture.relative_to(REPOSITORY_ROOT).as_posix(),
        "sql_bytes": len(sql_utf8),
        "sql_sha256": sql_sha256,
        "expected_parser_counts": {"tables": 1, "rows": 2, "cells": 8},
    }


def _buffer_reference_span(array: pa.Array) -> int:
    return sum(buffer.size for buffer in array.buffers() if buffer is not None)


def _report_int(value: object) -> int:
    if not isinstance(value, int):
        raise RuntimeError("parser buffer report contains a non-integer count")
    return value


def _table_report(table: pa.Table, descriptors: list[dict[str, Any]], index: int) -> dict[str, object]:
    if len(descriptors) != table.num_columns:
        raise ValueError("parser descriptor and Arrow schema column counts differ")
    columns: list[dict[str, object]] = []
    for column_index, (column, descriptor) in enumerate(
        zip(table.columns, descriptors, strict=True)
    ):
        buffer_reference_span = sum(
            _buffer_reference_span(chunk) for chunk in column.chunks
        )
        columns.append(
            {
                "column_index": column_index,
                "logical_type": descriptor["logical_type"],
                "arrow_type": str(column.type),
                "nullable": descriptor["nullable"],
                "rows": len(column),
                "nulls": column.null_count,
                "logical_nbytes": column.nbytes,
                "buffer_reference_span_bytes": buffer_reference_span,
            }
        )
    return {
        "table_index": index,
        "rows": table.num_rows,
        "columns": table.num_columns,
        "logical_nbytes": table.nbytes,
        "unique_backing_buffer_bytes": table.get_total_buffer_size(),
        "column_details": columns,
    }


def _census(sql_utf8: bytes, input_report: dict[str, object]) -> dict[str, object]:
    import threading

    envelope = _parse_sql_native(sql_utf8, threading.Event(), None, 1, None)
    if envelope.get("kind") != "result":
        raise RuntimeError("existing Rust parser returned an error envelope")
    if envelope.get("status") != "COMPLETE":
        raise RuntimeError("bounded census input did not parse completely")
    table_reports: list[dict[str, object]] = []
    for index, item in enumerate(envelope["tables"]):
        stream = item.get("arrow_stream")
        if stream is None:
            raise RuntimeError("ready parser table has no Arrow C Stream")
        table = stream.read_all()
        table_reports.append(_table_report(table, item["columns"], index))
    measured_counts = {
        "tables": len(table_reports),
        "rows": sum(_report_int(table["rows"]) for table in table_reports),
        "cells": sum(
            _report_int(table["rows"]) * _report_int(table["columns"])
            for table in table_reports
        ),
    }
    expected_counts = input_report.get("expected_s2a_parser_counts") or input_report.get(
        "expected_parser_counts"
    )
    if measured_counts != expected_counts:
        raise RuntimeError("measured parser table/row/cell counts differ from the pinned source")
    return {
        "scope": "measured S2a parser Arrow C Stream buffers; not canonical IPC or RSS",
        "parser": {
            "implementation": "gateway_compute._native._parse_sql_native",
            "pool_threads": 1,
            "status": envelope["status"],
            "pyarrow_version": pa.__version__,
        },
        "input": input_report,
        "totals": {
            **measured_counts,
            "logical_nbytes": sum(
                _report_int(table["logical_nbytes"]) for table in table_reports
            ),
            "sum_per_table_unique_backing_buffer_bytes": sum(
                _report_int(table["unique_backing_buffer_bytes"]) for table in table_reports
            ),
        },
        "tables": table_reports,
    }


def main() -> int:
    _init_kernel_native(1)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", choices=("t1-v1", "types-fixture"))
    sample = parser.parse_args().sample
    sql_utf8, input_report = (
        _read_t1_sql() if sample == "t1-v1" else _read_type_fixture()
    )
    result = _census(sql_utf8, input_report)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
