"""Phase 6 V6: differential between the Python SQL parser and the Rust prototype.

Test and measurement tool only; not imported by production code.

Both sides are reduced to the same "parse canonical form" (see
``vnext/rust/gateway-compute-core/src/table_access/canonical.rs``): per table
the descriptor (names, columns, declared types, primary key), the row count,
and per column the typed values as ``(type mark, payload)`` in row order. The
Python side is produced here from ``parse_sql``; the Rust side by the
``table_access_parse`` example. ``compare`` reports counts and the first
difference as table, column, row and the two type marks -- never values, so
it can run on real data (DC22).

Subcommands::

    python-canonical --sql dump.sql --out py.pcf [--summary-out s.json]
    compare --left py.pcf --right rs.pcf
    corpus --rust-bin table_access_parse --workdir DIR
    real --sql dump.sql --rust-bin table_access_parse --workdir DIR [--threads 1,8]

Measurement inputs (extract-sql, make-2x) and throughput runs live in
``p6_v6_measure_inputs.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import mmap
import os
import socket
import struct
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gateway_backend.capabilities.table_access.contracts import (
    PARSER_INPUT_CONTRACT_VERSION,
    NeverCancel,
    ParseResult,
    ParserInvocationContext,
    SourceCell,
    SourceColumnDescriptor,
    SqlParseRequest,
    SqlSetValue,
    SqlSourceInput,
)
from gateway_backend.capabilities.table_access.sql import parse_sql
from gateway_shared_kernel import DeclaredType, NullScalar, encode_typed_scalar, raw_blob_digest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
VNEXT_ROOT = BACKEND_ROOT.parent
GOLDEN_SQL_ROOT = VNEXT_ROOT / "fixtures" / "golden" / "table-access" / "sql"

MAGIC = b"GDMSPCF1"
FORMAT = "gateway.table-access.parse-canonical"
VERSION = 1
MARKS: dict[str, int] = {
    "null": 0x00,
    "boolean": 0x01,
    "signed-integer": 0x10,
    "unsigned-integer": 0x11,
    "decimal": 0x12,
    "float32": 0x13,
    "float64": 0x14,
    "string": 0x20,
    "binary": 0x21,
    "bit": 0x22,
    "date": 0x30,
    "datetime": 0x31,
    "timestamp": 0x32,
    "time-duration": 0x33,
    "set": 0x40,
}
MARK_NAMES = {value: key for key, value in MARKS.items()}


# --------------------------------------------------------------------------
# Python reference -> canonical form


def _request(sql: bytes) -> SqlParseRequest:
    digest = raw_blob_digest(sql)
    return SqlParseRequest(
        source=SqlSourceInput(
            document_content_digest=digest,
            sql_source_digest=digest,
            parser_input_contract_version=PARSER_INPUT_CONTRACT_VERSION,
            encoding="utf-8",
            source_size_bytes=len(sql),
        ),
        sql_utf8=sql,
        context=ParserInvocationContext(NeverCancel()),
    )


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _block(value: object) -> bytes:
    payload = _json_bytes(value)
    return struct.pack(">I", len(payload)) + payload


def _declared_json(declared: DeclaredType | None) -> dict[str, object] | None:
    if declared is None:
        return None
    out: dict[str, object] = {"kind": declared.kind.value}
    for name in ("bits", "precision", "scale", "bit_width"):
        value = getattr(declared, name)
        if value is not None:
            out[name] = value
    return out


def _column_json(column: SourceColumnDescriptor) -> dict[str, object]:
    return {
        "canonical_name": column.canonical_name,
        "declared_type": _declared_json(column.declared_type),
        "display_name": column.display_name,
        "labels": None if column.enum_or_set_labels is None else list(column.enum_or_set_labels),
        "logical_type": column.logical_type.value,
        "nullable": column.nullable,
        "ordinal": column.ordinal,
        "sql_type": column.sql_type,
    }


def _cell(cell: SourceCell, column: SourceColumnDescriptor) -> tuple[int, bytes]:
    if isinstance(cell, SqlSetValue):
        return MARKS["set"], ",".join(cell.members).encode()
    if isinstance(cell, NullScalar):
        return MARKS["null"], b""
    declared = column.declared_type
    if declared is None:
        raise ValueError("non-null value in a column without declared type")
    payload = encode_typed_scalar(declared, cell).payload
    return MARKS[str(cell.kind)], payload


@dataclass
class PythonCanonical:
    data: bytes
    status: str
    diagnostic_codes: list[str]
    diagnostics: list[list[Any]]
    parse_seconds: float
    read_seconds: float
    tables: list[dict[str, Any]] = field(default_factory=list)


def python_canonical(sql: bytes) -> PythonCanonical:
    started = time.perf_counter()
    result: ParseResult = parse_sql(_request(sql))
    parse_seconds = time.perf_counter() - started
    started = time.perf_counter()
    parts = [MAGIC]
    parts.append(
        _block(
            {
                "format": FORMAT,
                "status": result.status.value,
                "table_count": len(result.tables),
                "version": VERSION,
            }
        )
    )
    tables: list[dict[str, Any]] = []
    for parsed in result.tables:
        descriptor = parsed.descriptor
        columns = descriptor.columns
        rows = list(parsed.reader.iter_rows()) if parsed.reader is not None else None
        parts.append(
            _block(
                {
                    "canonical_name": descriptor.canonical_name,
                    "columns": [_column_json(column) for column in columns],
                    "display_name": descriptor.display_name,
                    "primary_key": list(descriptor.primary_key_canonical_names),
                    "reader_ready": descriptor.reader_ready and parsed.reader is not None,
                    "row_count": None if rows is None else len(rows),
                }
            )
        )
        tables.append(
            {"name": descriptor.canonical_name, "ready": rows is not None, "rows": len(rows or ())}
        )
        if rows is None:
            continue
        for column in columns:
            chunk = bytearray(b"C")
            chunk += struct.pack(">I", column.ordinal)
            for row in rows:
                mark, payload = _cell(row[column.ordinal], column)
                chunk.append(mark)
                chunk += struct.pack(">I", len(payload))
                chunk += payload
            parts.append(bytes(chunk))
    read_seconds = time.perf_counter() - started
    return PythonCanonical(
        data=b"".join(parts),
        status=result.status.value,
        diagnostic_codes=[item.code.value for item in result.diagnostics],
        diagnostics=[[item.code.value, item.byte_offset, item.table] for item in result.diagnostics],
        parse_seconds=parse_seconds,
        read_seconds=read_seconds,
        tables=tables,
    )


# --------------------------------------------------------------------------
# Canonical form reader and comparison


class CanonicalReader:
    def __init__(self, data: bytes | mmap.mmap) -> None:
        self.view = memoryview(data)
        if bytes(self.view[:8]) != MAGIC:
            raise ValueError("not a parse canonical file")
        self.pos = 8
        self.header = self._json()
        if self.header.get("format") != FORMAT or self.header.get("version") != VERSION:
            raise ValueError("unsupported canonical format")

    def _u32(self) -> int:
        (value,) = struct.unpack_from(">I", self.view, self.pos)
        self.pos += 4
        return int(value)

    def _json(self) -> dict[str, Any]:
        length = self._u32()
        value = json.loads(bytes(self.view[self.pos : self.pos + length]))
        self.pos += length
        if type(value) is not dict:
            raise ValueError("canonical block is not an object")
        return value

    def tables(self) -> Iterator[dict[str, Any]]:
        for _ in range(int(self.header["table_count"])):
            yield self._json()

    def column_start(self, ordinal: int) -> None:
        if bytes(self.view[self.pos : self.pos + 1]) != b"C":
            raise ValueError("column marker missing")
        self.pos += 1
        if self._u32() != ordinal:
            raise ValueError("column ordinal out of order")

    def value(self) -> tuple[int, memoryview]:
        mark = self.view[self.pos]
        self.pos += 1
        length = self._u32()
        payload = self.view[self.pos : self.pos + length]
        self.pos += length
        return int(mark), payload

    def skip_table_values(self, table: dict[str, Any]) -> None:
        if not table.get("reader_ready"):
            return
        for column in table["columns"]:
            self.column_start(int(column["ordinal"]))
            for _ in range(int(table["row_count"])):
                self.value()


@dataclass
class Difference:
    table: str
    column: str | None
    row: int | None
    left_mark: str | None
    right_mark: str | None
    field: str


def _mark_name(mark: int) -> str:
    return MARK_NAMES.get(mark, f"0x{mark:02x}")


def compare_canonical(left_data: bytes | mmap.mmap, right_data: bytes | mmap.mmap) -> dict[str, Any]:
    left = CanonicalReader(left_data)
    right = CanonicalReader(right_data)
    report: dict[str, Any] = {
        "byte_identical": bytes(left.view) == bytes(right.view),
        "left_sha256": hashlib.sha256(left.view).hexdigest(),
        "right_sha256": hashlib.sha256(right.view).hexdigest(),
        "status": [left.header["status"], right.header["status"]],
        "tables_compared": 0,
        "rows_compared": 0,
        "values_compared": 0,
        "differences": 0,
        "first_difference": None,
        "per_table": [],
    }
    first: Difference | None = None

    def note(difference: Difference, count: int = 1) -> None:
        nonlocal first
        report["differences"] += count
        if first is None:
            first = difference

    if left.header["status"] != right.header["status"]:
        note(Difference("<document>", None, None, None, None, "status"))
    if left.header["table_count"] != right.header["table_count"]:
        note(Difference("<document>", None, None, None, None, "table_count"))
    for left_table, right_table in zip(left.tables(), right.tables(), strict=False):
        name = str(left_table["canonical_name"])
        table_diffs = 0
        header_keys = sorted(set(left_table) | set(right_table))
        header_mismatch = [key for key in header_keys if left_table.get(key) != right_table.get(key)]
        if header_mismatch:
            for key in header_mismatch:
                note(Difference(name, None, None, None, None, f"table.{key}"))
            table_diffs += len(header_mismatch)
            left.skip_table_values(left_table)
            right.skip_table_values(right_table)
            report["per_table"].append({"table": name, "rows": None, "differences": table_diffs})
            report["tables_compared"] += 1
            continue
        rows = int(left_table["row_count"] or 0)
        if left_table.get("reader_ready"):
            for column in left_table["columns"]:
                ordinal = int(column["ordinal"])
                left.column_start(ordinal)
                right.column_start(ordinal)
                for row in range(rows):
                    left_mark, left_payload = left.value()
                    right_mark, right_payload = right.value()
                    report["values_compared"] += 1
                    if left_mark != right_mark or left_payload != right_payload:
                        table_diffs += 1
                        note(
                            Difference(
                                name,
                                str(column["canonical_name"]),
                                row,
                                _mark_name(left_mark),
                                _mark_name(right_mark),
                                "value",
                            )
                        )
            report["rows_compared"] += rows
        report["tables_compared"] += 1
        report["per_table"].append({"table": name, "rows": rows, "differences": table_diffs})
    if first is not None:
        report["first_difference"] = first.__dict__
    return report


def _read_file(path: Path) -> bytes:
    return path.read_bytes()


# --------------------------------------------------------------------------
# Rust side


def run_rust(
    rust_bin: Path,
    sql_path: Path,
    canonical_out: Path,
    *,
    threads: str,
    chunk_bytes: str,
    repeat: int = 1,
) -> dict[str, Any]:
    command = [
        str(rust_bin),
        "--input",
        str(sql_path),
        "--threads",
        threads,
        "--chunk-bytes",
        chunk_bytes,
        "--repeat",
        str(repeat),
        "--canonical",
        "write",
        "--canonical-out",
        str(canonical_out),
    ]
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"rust parser failed: {completed.stderr.strip()}")
    summary: dict[str, Any] = json.loads(completed.stdout)
    return summary


# --------------------------------------------------------------------------
# Corpus (layer 1 subset plus synthetic literal-class cases)


def _test_constants() -> dict[str, Any]:
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    parser_tests = importlib.import_module("tests.test_table_access_sql_parser")
    reject_tests = importlib.import_module("tests.test_table_access_sql_rejects")
    reader_tests = importlib.import_module("tests.test_table_access_sql_reader")
    return {
        "golden": tuple(parser_tests.SQL_GOLDEN_CASES),
        "set_shapes": tuple(parser_tests.MYSQLDUMP_SET_SHAPES),
        "statement_rejects": tuple(item[0] for item in reject_tests.SQL_STATEMENT_REJECTS),
        "type_malformed": tuple(reject_tests.SQL_TYPE_MALFORMED_SHAPES),
        "value_illegal": tuple(item[0] for item in reject_tests.SQL_VALUE_ILLEGAL_SHAPES),
        "reader_sql": reader_tests._SQL,
    }


_WIDE_TABLE = (
    "CREATE TABLE `w` (\n"
    "  `id` int(11) NOT NULL AUTO_INCREMENT,\n"
    "  `i8` tinyint(4) DEFAULT NULL,\n"
    "  `u32` int(10) unsigned DEFAULT '0',\n"
    "  `u64` bigint(20) unsigned DEFAULT NULL,\n"
    "  `f` float DEFAULT NULL,\n"
    "  `d` double(16,4) DEFAULT NULL,\n"
    "  `m` decimal(65,30) DEFAULT NULL,\n"
    "  `s` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT '' COMMENT 'name, (x)',\n"
    "  `t` text,\n"
    "  `b` blob,\n"
    "  `bt` bit(10) DEFAULT b'0',\n"
    "  `dt` datetime(6) DEFAULT NULL,\n"
    "  `ts` timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n"
    "  `tm` time DEFAULT NULL,\n"
    "  `dd` date DEFAULT NULL,\n"
    "  `e` enum('on','off','it''s') DEFAULT 'on',\n"
    "  `st` set('a','b','c') DEFAULT '',\n"
    "  `j` json DEFAULT NULL,\n"
    "  `bo` tinyint(1) NOT NULL DEFAULT '0',\n"
    "  PRIMARY KEY (`id`),\n"
    "  UNIQUE KEY `uk_s` (`s`(10)),\n"
    "  KEY `k_dt` (`dt`)\n"
    ") ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COMMENT='wide';\n"
)

_WIDE_ROW_OK = (
    "(1,-128,4294967295,18446744073709551615,-0.0,1.5e-3,"
    "-000123.450000000000000000000000000000,'a\\nb\\'c\\\\d''e\\0\\Z\\%\\_','中文\U0001F600','\\0\\xff',"
    "b'1000000001','2024-01-02 03:04:05.120000','2024-01-02 03:04:05','-838:59:59','2024-02-29',"
    "'it''s','c,a','{\"k\": [1, 2.5, null, NaN]}',1)"
)
_WIDE_ROW_NULLS = (
    "(2,NULL,0,NULL,3.4028235e38,-1E-300,0.000000000000000000000000000001,'',NULL,x'00FF',"
    "0x3,NULL,'1970-01-01 00:00:01.000001',NULL,NULL,'off','',NULL,0)"
)


def _wide(rows: str, *, boilerplate: bool = True) -> str:
    head = "/*!40101 SET NAMES utf8mb4 */;\n/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;\n"
    lock = "LOCK TABLES `w` WRITE;\n/*!40000 ALTER TABLE `w` DISABLE KEYS */;\n"
    tail = "/*!40000 ALTER TABLE `w` ENABLE KEYS */;\nUNLOCK TABLES;\n"
    body = f"INSERT INTO `w` VALUES {rows};\n"
    if not boilerplate:
        return _WIDE_TABLE + body
    return head + "DROP TABLE IF EXISTS `w`;\n" + _WIDE_TABLE + lock + body + tail


def _one(column: str, *values: str) -> str:
    return f"CREATE TABLE `t` (`c` {column});\nINSERT INTO `t` VALUES " + ",".join(
        f"({value})" for value in values
    ) + ";\n"


def _many_rows(count: int) -> str:
    rows = ",".join(
        f"({index},'row {index}, with (parens) and ''quotes''\n second line',{index}.5)"
        for index in range(count)
    )
    return (
        "CREATE TABLE `m` (`id` int NOT NULL, `s` text, `f` double, PRIMARY KEY (`id`));\n"
        f"INSERT INTO `m` VALUES {rows};\nINSERT INTO `m` (`f`, `s`, `id`) VALUES (1e0,'x',{count});\n"
    )


LITERAL_CLASS_CASES: tuple[tuple[str, str], ...] = (
    ("wide-table-all-literal-classes", _wide(_WIDE_ROW_OK + "," + _WIDE_ROW_NULLS)),
    ("wide-table-crlf", _wide(_WIDE_ROW_OK + ",\n" + _WIDE_ROW_NULLS).replace("\n", "\r\n")),
    ("wide-table-no-boilerplate", _wide(_WIDE_ROW_NULLS, boilerplate=False)),
    ("escapes", _one("varchar(32)", r"'\\'", r"'\''", r"'\"'", r"'\n\r\t\b\0\Z'", r"'\a\%\_'", "''''", "'a''b'")),
    ("multibyte", _one("text", "'é'", "'中文'", "'\U0001F600'", r"'\é'", "'ä''ö'")),
    ("quoted-newlines", _one("text", "'line1\nline2'", "'a\r\nb'", "'\n'", "';\n-- not a comment\n'")),
    ("noncharacter-string", _one("text", "'﷐'")),
    ("hex-in-blob", _one("blob", "x'0102'", "X'abc'", "0xDEADBEEF", "0x1", "x''", "x'41 42'")),
    ("hex-in-text", _one("varchar(8)", "x'4142'", "0x41")),
    ("hex-in-text-invalid-utf8", _one("varchar(8)", "x'ff'")),
    ("bit-literals", _one("bit(16)", "b'1'", "b''", "0b101", "b'0000000000000001'", "x'0001'", "'ab'", "0", "1", "10", "101", "2")),
    ("bit-overflow", _one("bit(4)", "b'11111'")),
    ("bit-decimal-number", _one("bit(8)", "255")),
    ("bit-text-in-varchar", _one("varchar(8)", "b'0101'", "0b11")),
    ("binary-keyword", _one("blob", "TRUE", "123", "-1.5")),
    ("integers", _one("bigint", "0", "-0", "+7", "007", "-9223372036854775808", "9223372036854775807", "'12'", "x'31'")),
    ("integer-out-of-range", _one("tinyint", "128")),
    ("unsigned-negative-zero", _one("int unsigned", "-0")),
    ("integer-float-text", _one("int", "1.0")),
    ("floats", _one("float", "-0.0", "0", "1e38", "1.17549435e-38", "1e-45", "3.14159", ".5", "5.", "+2E+2", "'1.5'")),
    ("doubles", _one("double", "-0.0", "1.7976931348623157e308", "4.9e-324", "2.2250738585072014e-308", "1e-400", "0.1", "123456789012345678901234567890")),
    ("float-overflow", _one("float", "1e39")),
    ("double-overflow", _one("double", "1e309")),
    ("float32-double-rounding", _one("float", "1.000000059604644775390626", "1.000000178813934326171874")),
    ("decimals", _one("decimal(65,30)", "0", "-0", "-0.000", "12345678901234567890123456789012345.123456789012345678901234567890", ".5", "-.5", "'001.100'")),
    ("decimal-exponent", _one("decimal(10,2)", "1e2")),
    ("decimal-scale-overflow", _one("decimal(10,2)", "1.234")),
    ("decimal-default-precision", "CREATE TABLE `t` (`c` decimal);\n"),
    ("dates", _one("date", "'2024-02-29'", "'0001-01-01'", "'9999-12-31'")),
    ("zero-date", _one("date", "'0000-00-00'")),
    ("zero-datetime", _one("datetime", "'0000-00-00 00:00:00'")),
    ("datetimes", _one("datetime(6)", "'2024-01-02 03:04:05'", "'2024-01-02T03:04:05.5'", "' 2024-01-02 03:04:05.000000 '")),
    ("timestamps", _one("timestamp(3)", "'2024-01-02 03:04:05.100'", "'2024-01-02T03:04:05Z'")),
    ("times", _one("time(6)", "'00:00:00'", "'-00:00:00.0'", "'838:59:59'", "'-12:34:56.789'", "'100:00:00'")),
    ("time-out-of-range", _one("time", "'839:00:00'")),
    ("booleans", _one("boolean", "TRUE", "false", "1", "0", "'1'", "'true'")),
    ("boolean-illegal", _one("boolean", "2")),
    ("enum-values", _one("enum('','a','b c')", "''", "'a'", "'b c'", "NULL")),
    ("enum-undeclared", _one("enum('a')", "'A'")),
    ("set-values", _one("set('x','y','z')", "''", "'z,x'", "'y'", "NULL")),
    ("set-duplicate", _one("set('x','y')", "'x,x'")),
    ("json-values", _one("json", "'{}'", "'[1, \"a\", {\"b\": null}]'", "'\"\\\\ud800\"'", "'-Infinity'", "'  1  '")),
    ("json-invalid", _one("json", "'{\"a\": 1,}'")),
    ("null-not-null", "CREATE TABLE `t` (`c` int NOT NULL);\nINSERT INTO `t` VALUES (NULL);\n"),
    ("null-in-every-type", _wide("(3,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,'2000-01-01 00:00:00',NULL,NULL,NULL,NULL,NULL,1)")),
    ("comments-everywhere", "/* lead */ -- line\n# hash\nCREATE /* c */ TABLE `t` ( -- x\n `a` int NOT /* y */ NULL, `b` text\n);\nINSERT INTO `t` VALUES /* v */ (1, 'a' /* z */ ) , -- n\n (2,'b');\n"),
    ("conditional-comments", "/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;\n/*!50503 SET NAMES utf8mb4 */;\n/*!40103 SET TIME_ZONE='+00:00' */;\nCREATE TABLE `t` (`a` int);\n/*!40000 ALTER TABLE `t` DISABLE KEYS */;\nINSERT INTO `t` VALUES (1);\n/*!40000 ALTER TABLE `t` ENABLE KEYS */;\n/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;\n"),
    ("inline-conditional-comment-rejected", "CREATE TABLE `t` (`a` int /*!50000 NULL */);\n"),
    ("lock-tables-boilerplate", "CREATE TABLE `t` (`a` int);\nLOCK TABLES `t` WRITE, `t` AS x READ LOCAL;\nINSERT INTO `t` VALUES (1),(2);\nUNLOCK TABLES;\n"),
    ("column-list-permutation", "CREATE TABLE `t` (`a` int, `b` text, `c` double);\nINSERT INTO `t` (`c`,`a`,`b`) VALUES (1.5,1,'x'),(2.5,2,'y');\n"),
    ("backtick-identifiers", "CREATE TABLE `we``ird` (`co``l` int, `中` text);\nINSERT INTO `we``ird` VALUES (1,'a');\n"),
    ("schema-qualified", "CREATE TABLE `db`.`t` (`a` int);\nINSERT INTO `db`.`t` VALUES (1);\n"),
    ("binary-prefix-rejected", _one("blob", "_binary 'abc'")),
    ("default-in-values", _one("int", "DEFAULT")),
    ("trailing-comma-in-values", _one("int", "1,")),
    ("empty-tuple", _one("int", "")),
    ("unclosed-string", "CREATE TABLE `t` (`a` text);\nINSERT INTO `t` VALUES ('abc);\n"),
    ("double-quoted-string-rejected", _one("text", '"abc"')),
    ("on-duplicate-key", "CREATE TABLE `t` (`a` int);\nINSERT INTO `t` VALUES (1) ON DUPLICATE KEY UPDATE a=1;\n"),
    ("unknown-insert-target", "INSERT INTO `nope` VALUES (1);\n"),
    ("many-rows-for-chunking", _many_rows(400)),
    ("two-tables-one-bad", "CREATE TABLE `ok` (`a` int);\nINSERT INTO `ok` VALUES (1);\nCREATE TABLE `bad` (`y` year);\nINSERT INTO `bad` VALUES (2024);\n"),
    ("empty-document", ""),
    ("only-comments", "-- nothing\n/* here */\n;;\n"),
)


# Cases where the Rust prototype follows the Shared Canonical Encoding
# contract and the Python reference does not (reported, not fixed here).
KNOWN_REFERENCE_DEVIATIONS = frozenset({"literal:float32-double-rounding"})


def corpus_cases() -> list[tuple[str, str]]:
    constants = _test_constants()
    cases: list[tuple[str, str]] = []
    for case_dir in constants["golden"]:
        cases.append((f"golden:{case_dir}", (GOLDEN_SQL_ROOT.parent / case_dir / "input.sql").read_text("utf-8")))
    for index, sql in enumerate(constants["set_shapes"]):
        cases.append((f"test:mysqldump-set-shape-{index}", sql))
    for index, sql in enumerate(constants["statement_rejects"]):
        cases.append((f"test:statement-reject-{index}", sql))
    for index, sql_type in enumerate(constants["type_malformed"]):
        cases.append((f"test:type-malformed-{index}", f"CREATE TABLE t (`c` {sql_type} NULL);"))
    for index, sql in enumerate(constants["value_illegal"]):
        cases.append((f"test:value-illegal-{index}", sql))
    cases.append(("test:reader-sql", constants["reader_sql"]))
    cases.append(
        (
            "test:insert-permutation",
            "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, name VARCHAR(8) NULL);"
            "INSERT INTO t (name, id) VALUES ('z', 9);",
        )
    )
    for name, sql in (
        ("test:duplicate-table", "CREATE TABLE t (id INT NOT NULL PRIMARY KEY);CREATE TABLE IF NOT EXISTS t (id INT NOT NULL PRIMARY KEY);"),
        ("test:column-collision", "CREATE TABLE t (`Id` INT NOT NULL, `id` INT NULL);"),
        ("test:duplicate-pk", "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, PRIMARY KEY (id));"),
        ("test:row-shape", "CREATE TABLE t (id INT NOT NULL PRIMARY KEY); INSERT INTO t VALUES (1, 2);"),
        ("test:partial", "CREATE TABLE ok (id INT NOT NULL PRIMARY KEY); INSERT INTO ok VALUES (1);CREATE TABLE bad (`y` YEAR NULL);"),
        ("test:unknown-year", "CREATE TABLE t (`y` YEAR NULL);"),
    ):
        cases.append((name, sql))
    for name, sql in LITERAL_CLASS_CASES:
        cases.append((f"literal:{name}", sql))
    return cases


def first_diagnostic_difference(python: list[list[Any]], rust: list[dict[str, Any]]) -> dict[str, Any] | None:
    """First differing `(code, byte_offset, table)` entry; messages are not compared."""
    rust_items = [[item["code"], item["byte_offset"], item["table"]] for item in rust]
    for index in range(max(len(python), len(rust_items))):
        left = python[index] if index < len(python) else None
        right = rust_items[index] if index < len(rust_items) else None
        if left != right:
            return {"index": index, "python": left, "rust": right}
    return None


def run_corpus(rust_bin: Path, workdir: Path) -> dict[str, Any]:
    workdir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for index, (name, sql) in enumerate(corpus_cases()):
        data = sql.encode("utf-8")
        sql_path = workdir / f"case-{index:03d}.sql"
        sql_path.write_bytes(data)
        python_side = python_canonical(data)
        rust_out = workdir / f"case-{index:03d}.rs.pcf"
        rust_summary = run_rust(rust_bin, sql_path, rust_out, threads="1,4", chunk_bytes="1048576,16,1")
        report = compare_canonical(python_side.data, rust_out.read_bytes())
        rust_result = rust_summary["result"]
        failure = rust_result.get("document_failure")
        rust_codes = [item["code"] for item in rust_result["diagnostics"]]
        diagnostic_difference = first_diagnostic_difference(python_side.diagnostics, rust_result["diagnostics"])
        results.append(
            {
                "case": name,
                "known_reference_deviation": name in KNOWN_REFERENCE_DEVIATIONS,
                "status": python_side.status,
                "values_compared": report["values_compared"],
                "differences": report["differences"],
                "first_difference": report["first_difference"],
                "byte_identical": report["byte_identical"],
                "rust_deterministic": rust_summary["deterministic"],
                "python_codes": sorted(set(python_side.diagnostic_codes)),
                "rust_codes": sorted(set(rust_codes)),
                "rust_document_failure": None if failure is None else failure["code"],
                "error_code_match": (failure is None or failure["code"] in python_side.diagnostic_codes)
                and (bool(rust_codes) == bool(python_side.diagnostic_codes)),
                "diagnostics_equal": diagnostic_difference is None,
                "first_diagnostic_difference": diagnostic_difference,
            }
        )
    return {
        "cases": len(results),
        "cases_with_differences": sum(
            1 for item in results if item["differences"] and not item["known_reference_deviation"]
        ),
        "known_deviation_cases": [
            {"case": item["case"], "differences": item["differences"]}
            for item in results
            if item["known_reference_deviation"]
        ],
        "values_compared": sum(item["values_compared"] for item in results),
        "all_deterministic": all(item["rust_deterministic"] for item in results),
        "error_code_mismatches": [item["case"] for item in results if not item["error_code_match"]],
        "diagnostic_mismatches": [
            {"case": item["case"], "first": item["first_diagnostic_difference"]}
            for item in results
            if not item["diagnostics_equal"]
        ],
        "results": results,
    }


# --------------------------------------------------------------------------
# Real data


def run_real(sql_path: Path, rust_bin: Path, workdir: Path, threads: str, chunk_bytes: str) -> dict[str, Any]:
    workdir.mkdir(parents=True, exist_ok=True)
    os.chmod(workdir, 0o700)
    data = sql_path.read_bytes()
    python_side = python_canonical(data)
    python_out = workdir / (sql_path.stem + ".py.pcf")
    python_out.write_bytes(python_side.data)
    os.chmod(python_out, 0o600)
    rust_out = workdir / (sql_path.stem + ".rs.pcf")
    rust_summary = run_rust(rust_bin, sql_path, rust_out, threads=threads, chunk_bytes=chunk_bytes)
    os.chmod(rust_out, 0o600)
    report = compare_canonical(python_side.data, rust_out.read_bytes())
    return {
        "hostname": socket.gethostname(),
        "input": sql_path.name,
        "input_bytes": len(data),
        "input_sha256": hashlib.sha256(data).hexdigest(),
        "python_status": python_side.status,
        "python_parse_seconds": round(python_side.parse_seconds, 3),
        "python_read_seconds": round(python_side.read_seconds, 3),
        "python_tables": len(python_side.tables),
        "python_rows": sum(int(item["rows"]) for item in python_side.tables),
        "rust_configs": rust_summary["configs"],
        "rust_deterministic": rust_summary["deterministic"],
        "rust_peak_rss_kib": rust_summary["peak_rss_kib"],
        "python_diagnostic_codes": sorted(set(python_side.diagnostic_codes)),
        "first_diagnostic_difference": first_diagnostic_difference(
            python_side.diagnostics, rust_summary["result"]["diagnostics"]
        ),
        "comparison": report,
    }


# --------------------------------------------------------------------------


def _emit(value: object, path: str | None) -> None:
    text = json.dumps(value, indent=2, ensure_ascii=False, default=str)
    if path:
        Path(path).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("python-canonical")
    p.add_argument("--sql", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--summary-out")
    p = sub.add_parser("compare")
    p.add_argument("--left", required=True)
    p.add_argument("--right", required=True)
    p.add_argument("--summary-out")
    p = sub.add_parser("corpus")
    p.add_argument("--rust-bin", required=True)
    p.add_argument("--workdir", required=True)
    p.add_argument("--summary-out")
    p = sub.add_parser("real")
    p.add_argument("--sql", required=True)
    p.add_argument("--rust-bin", required=True)
    p.add_argument("--workdir", required=True)
    p.add_argument("--threads", default="1,8")
    p.add_argument("--chunk-bytes", default="1048576,65536")
    p.add_argument("--summary-out")
    args = parser.parse_args(argv)

    if args.command == "python-canonical":
        result = python_canonical(Path(args.sql).read_bytes())
        Path(args.out).write_bytes(result.data)
        _emit(
            {
                "status": result.status,
                "parse_seconds": result.parse_seconds,
                "read_seconds": result.read_seconds,
                "tables": result.tables,
                "diagnostic_codes": result.diagnostic_codes,
                "canonical_sha256": hashlib.sha256(result.data).hexdigest(),
            },
            args.summary_out,
        )
        return 0
    if args.command == "compare":
        report = compare_canonical(_read_file(Path(args.left)), _read_file(Path(args.right)))
        _emit(report, args.summary_out)
        return 0 if report["differences"] == 0 else 1
    if args.command == "corpus":
        summary = run_corpus(Path(args.rust_bin), Path(args.workdir))
        _emit(summary, args.summary_out)
        return 0 if summary["cases_with_differences"] == 0 and summary["all_deterministic"] else 1
    if args.command == "real":
        summary = run_real(Path(args.sql), Path(args.rust_bin), Path(args.workdir), args.threads, args.chunk_bytes)
        _emit(summary, args.summary_out)
        return 0 if summary["comparison"]["differences"] == 0 and summary["rust_deterministic"] else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
