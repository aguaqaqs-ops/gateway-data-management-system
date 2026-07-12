from __future__ import annotations

from collections.abc import Mapping
import json

from ...core.digests import DigestRef, canonical_json_bytes
from ...repository_server.ref_session import RepositoryRefSession
from .models import SnapshotSummary
from .versions import SNAPSHOT_SUMMARY_SCHEMA_VERSION


HIDDEN_SNAPSHOT_SUMMARY_TABLE_NAME = "__backend_vnext_snapshot_summary__"
HIDDEN_SNAPSHOT_SUMMARY_TABLE_KEY = "FINAL"
HIDDEN_SNAPSHOT_SUMMARY_TABLE_SCHEMA_VERSION = (
    "backend-vnext/hidden-snapshot-summary-table/v1"
)
HIDDEN_SNAPSHOT_SUMMARY_TABLE_COLUMNS = (
    "summary_key",
    "schema_version",
    "summary_digest",
    "summary_json",
)


def build_hidden_summary_replay_sql(summary: SnapshotSummary) -> str:
    if summary.materialization_stage != "FINAL":
        raise ValueError("hidden snapshot summary replay requires a FINAL summary")
    payload = summary.to_payload()
    summary_json = canonical_json_bytes(payload).decode("utf-8")
    summary_digest = DigestRef.from_bytes(summary_json.encode("utf-8")).to_payload()
    column_list = ", ".join(f"`{column}`" for column in HIDDEN_SNAPSHOT_SUMMARY_TABLE_COLUMNS)
    return (
        f"DROP TABLE IF EXISTS `{HIDDEN_SNAPSHOT_SUMMARY_TABLE_NAME}`;\n"
        f"CREATE TABLE `{HIDDEN_SNAPSHOT_SUMMARY_TABLE_NAME}` (\n"
        "  `summary_key` varchar(64) NOT NULL,\n"
        "  `schema_version` varchar(128) NOT NULL,\n"
        "  `summary_digest` char(71) NOT NULL,\n"
        "  `summary_json` longtext NOT NULL,\n"
        "  PRIMARY KEY (`summary_key`)\n"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;\n"
        f"INSERT INTO `{HIDDEN_SNAPSHOT_SUMMARY_TABLE_NAME}` ({column_list}) VALUES\n"
        f"  ({_render_sql_literal(HIDDEN_SNAPSHOT_SUMMARY_TABLE_KEY)}, "
        f"{_render_sql_literal(HIDDEN_SNAPSHOT_SUMMARY_TABLE_SCHEMA_VERSION)}, "
        f"{_render_sql_literal(summary_digest)}, "
        f"{_render_sql_literal(summary_json)});\n"
    )


def read_hidden_summary_snapshot(
    session: RepositoryRefSession,
) -> SnapshotSummary:
    catalog = session.get_catalog()
    try:
        catalog_table = catalog.table(HIDDEN_SNAPSHOT_SUMMARY_TABLE_NAME)
    except KeyError as exc:
        raise ValueError("hidden snapshot summary table is missing from the repository ref") from exc
    if tuple(column.name for column in catalog_table.columns) != HIDDEN_SNAPSHOT_SUMMARY_TABLE_COLUMNS:
        raise ValueError("hidden snapshot summary table schema does not match the expected contract")
    reader = session.open_table_reader(HIDDEN_SNAPSHOT_SUMMARY_TABLE_NAME)
    try:
        rows = tuple(tuple(row) for row in reader.stream_rows())
    finally:
        reader.close()
    if len(rows) != 1:
        raise ValueError("hidden snapshot summary table must contain exactly one row")
    row = rows[0]
    row_map = dict(zip(HIDDEN_SNAPSHOT_SUMMARY_TABLE_COLUMNS, row, strict=True))
    summary_key = row_map["summary_key"]
    if summary_key != HIDDEN_SNAPSHOT_SUMMARY_TABLE_KEY:
        raise ValueError("hidden snapshot summary key mismatch")
    schema_version = row_map["schema_version"]
    if schema_version != HIDDEN_SNAPSHOT_SUMMARY_TABLE_SCHEMA_VERSION:
        raise ValueError("hidden snapshot summary table schema version mismatch")
    summary_json = row_map["summary_json"]
    if not isinstance(summary_json, str) or not summary_json.strip():
        raise ValueError("hidden snapshot summary payload must be a non-empty string")
    summary_digest = row_map["summary_digest"]
    if not isinstance(summary_digest, str) or not summary_digest.strip():
        raise ValueError("hidden snapshot summary digest must be a non-empty string")
    expected_digest = DigestRef.from_bytes(summary_json.encode("utf-8")).to_payload()
    if summary_digest != expected_digest:
        raise ValueError("hidden snapshot summary digest mismatch")
    summary_payload = json.loads(summary_json)
    if not isinstance(summary_payload, Mapping):
        raise ValueError("hidden snapshot summary payload must be a JSON object")
    summary = SnapshotSummary.from_payload(summary_payload)
    if summary.summary_contract_version != SNAPSHOT_SUMMARY_SCHEMA_VERSION:
        raise ValueError("hidden snapshot summary contract version mismatch")
    return summary


def read_hidden_summary_snapshot_payload(
    session: RepositoryRefSession,
) -> dict[str, object]:
    return read_hidden_summary_snapshot(session).to_payload()


def _render_sql_literal(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return "'" + _escape_sql_string(value) + "'"
    return "'" + _escape_sql_string(str(value)) + "'"


def _escape_sql_string(value: str) -> str:
    pieces: list[str] = []
    for ch in value:
        if ch == "\\":
            pieces.append("\\\\")
        elif ch == "'":
            pieces.append("''")
        elif ch == "\0":
            pieces.append("\\0")
        elif ch == "\b":
            pieces.append("\\b")
        elif ch == "\n":
            pieces.append("\\n")
        elif ch == "\r":
            pieces.append("\\r")
        elif ch == "\t":
            pieces.append("\\t")
        else:
            pieces.append(ch)
    return "".join(pieces)
