"""Deterministic same-schema W2 SQL scaler and S6 result-record schema.

W2 is synthetic boundary evidence. It keeps W1 CREATE TABLE statements unchanged,
replicates INSERT rows with PK transforms, and must not add manifest fields or
raise package/canonicalization versions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

GENERATOR_VERSION = "p2-r6-w2-scaler-v1"
DEFAULT_SEED = "p2-r6-ext-w1-medium"
SCHEMA_VERSION = "p2-r6-s6-capacity-v1"
TARGET_REPLAY_BYTES = 192 * 1024 * 1024
MIN_REPLAY_BYTES = 180 * 1024 * 1024
MAX_REPLAY_BYTES = 199 * 1024 * 1024
REPLAY_HARD_CAP_BYTES = 200 * 1024 * 1024
INTEGER_REPLICA_SPAN = 1_000_000
VARCHAR_REPLICA_PREFIX = "r{replica:02d}_"

PkStrategy = Literal["integer", "varchar", "none"]

_INSERT_HEAD = re.compile(r"^INSERT INTO `([^`]+)` VALUES ", re.IGNORECASE)
_CREATE_HEAD = re.compile(r"^CREATE TABLE `([^`]+)` \(", re.IGNORECASE)
_INT_TYPE = re.compile(
    r"^(?:TINY|SMALL|MEDIUM|BIG)?INT(?:\(\d+\))?(?:\s+UNSIGNED)?$",
    re.IGNORECASE,
)
_VARCHAR_TYPE = re.compile(
    r"^(?:(?:VAR)?CHAR\(\d+\)|TINYTEXT|TEXT|MEDIUMTEXT|LONGTEXT)$",
    re.IGNORECASE,
)
_FORBIDDEN_KEY_PARTS = (
    "raw_sql",
    "replay_sql",
    "secret",
    "password",
    "bearer",
    "token",
    "private_key",
)
_REQUIRED_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "candidate_sha",
        "synthetic",
        "dataset_id",
        "package_bytes",
        "package_sha256",
        "canonicalization_manifest_digest",
        "settings",
        "timings",
        "layers",
        "result",
        "cleanup",
    }
)
_REQUIRED_SETTINGS_KEYS = frozenset(
    {
        "max_upload_bytes",
        "max_decompressed_tar_stream_bytes",
        "max_total_expanded_entry_bytes",
        "max_replay_sql_bytes",
        "record_batch_bytes",
        "min_free_disk_bytes",
        "import_headroom_bytes",
        "max_concurrent_uploads",
        "max_import_workers",
        "max_concurrent_row_streams",
    }
)
_REQUIRED_LAYER_KEYS = frozenset(
    {
        "raw_upload_bytes",
        "package_bytes",
        "decoded_manifest_bytes",
        "decoded_replay_sql_bytes",
        "record_batch_bytes_limit",
        "peak_durable_root_bytes",
        "peak_rss_kib",
    }
)
_INTEGER_LIMITS = {
    "TINYINT": (127, 255),
    "SMALLINT": (32767, 65535),
    "MEDIUMINT": (8388607, 16777215),
    "INT": (2147483647, 4294967295),
    "INTEGER": (2147483647, 4294967295),
    "BIGINT": (9223372036854775807, 18446744073709551615),
}


class SyntheticW2Error(ValueError):
    """Raised when W2 scaling or an S6 result record fails closed."""


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    name: str
    sql_type: str


@dataclass(frozen=True, slots=True)
class TableScalePlan:
    name: str
    columns: tuple[ColumnSpec, ...]
    primary_key: tuple[str, ...]
    strategy: PkStrategy
    pk_indexes: tuple[int, ...]
    scaled: bool
    skip_reason: str | None = None


def integer_limit(sql_type: str) -> tuple[int, int] | None:
    stripped = sql_type.strip()
    unsigned = "UNSIGNED" in stripped.upper()
    base = stripped.split("(", 1)[0].split()[0].upper()
    limits = _INTEGER_LIMITS.get(base)
    if limits is None:
        return None
    signed, unsigned_max = limits
    return (unsigned_max, unsigned_max) if unsigned else (signed, signed)


def classify_pk_strategy(sql_type: str) -> PkStrategy:
    compact = " ".join(sql_type.split())
    if _INT_TYPE.match(compact):
        return "integer"
    if _VARCHAR_TYPE.match(compact):
        return "varchar"
    return "none"


def replica_integer(value: int, replica: int, *, span: int = INTEGER_REPLICA_SPAN) -> int:
    if replica < 0:
        raise SyntheticW2Error("replica must be non-negative")
    if replica == 0:
        return value
    return value + replica * span


def replica_varchar(value: str, replica: int) -> str:
    if replica < 0:
        raise SyntheticW2Error("replica must be non-negative")
    if replica == 0:
        return value
    return VARCHAR_REPLICA_PREFIX.format(replica=replica) + value


def validate_replay_size(size_bytes: int) -> None:
    if size_bytes >= REPLAY_HARD_CAP_BYTES:
        raise SyntheticW2Error(
            f"W2 replay.sql must stay under the 200 MiB hard cap: {size_bytes} bytes"
        )
    if size_bytes < MIN_REPLAY_BYTES:
        raise SyntheticW2Error(
            f"W2 replay.sql is below the 180 MiB band: {size_bytes} bytes"
        )
    if size_bytes > MAX_REPLAY_BYTES:
        raise SyntheticW2Error(
            f"W2 replay.sql is above the 199 MiB band: {size_bytes} bytes"
        )


def validate_s6_result_record(payload: object) -> None:
    if not isinstance(payload, dict):
        raise SyntheticW2Error("S6 result record must be an object")
    keys = {str(key) for key in payload}
    missing = sorted(_REQUIRED_RECORD_KEYS - keys)
    if missing:
        raise SyntheticW2Error(f"S6 result record missing keys: {missing}")
    extra_forbidden = [
        key
        for key in keys
        if any(part in key.lower() for part in _FORBIDDEN_KEY_PARTS)
    ]
    if extra_forbidden:
        raise SyntheticW2Error(f"S6 result record has forbidden keys: {extra_forbidden}")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise SyntheticW2Error("S6 result record schema_version mismatch")
    if not isinstance(payload.get("synthetic"), bool):
        raise SyntheticW2Error("S6 result record synthetic must be a boolean")
    settings = payload.get("settings")
    if not isinstance(settings, dict):
        raise SyntheticW2Error("S6 result record settings must be an object")
    missing_settings = sorted(_REQUIRED_SETTINGS_KEYS - {str(key) for key in settings})
    if missing_settings:
        raise SyntheticW2Error(f"S6 result record settings missing keys: {missing_settings}")
    layers = payload.get("layers")
    if not isinstance(layers, dict):
        raise SyntheticW2Error("S6 result record layers must be an object")
    missing_layers = sorted(_REQUIRED_LAYER_KEYS - {str(key) for key in layers})
    if missing_layers:
        raise SyntheticW2Error(f"S6 result record layers missing keys: {missing_layers}")
    result = payload.get("result")
    if result not in {"pass", "fail"}:
        raise SyntheticW2Error("S6 result record result must be pass or fail")


def _split_top_level(body: str, *, separator: str = ",") -> list[str]:
    items: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    index = 0
    while index < len(body):
        char = body[index]
        if quote is not None:
            if char == quote:
                if quote == "'" and index + 1 < len(body) and body[index + 1] == "'":
                    index += 2
                    continue
                quote = None
            elif char == "\\" and index + 1 < len(body):
                index += 2
                continue
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == separator and depth == 0:
            items.append(body[start:index].strip())
            start = index + 1
        index += 1
    tail = body[start:].strip()
    if tail:
        items.append(tail)
    return items


def parse_create_table(statement: str) -> TableScalePlan:
    match = _CREATE_HEAD.match(statement.strip())
    if match is None:
        raise SyntheticW2Error("CREATE TABLE statement is malformed")
    name = match.group(1)
    open_paren = statement.find("(")
    close_engine = re.search(r"\)\s*ENGINE\s*=", statement, re.IGNORECASE)
    if open_paren < 0 or close_engine is None:
        raise SyntheticW2Error(f"CREATE TABLE body is malformed for {name}")
    body = statement[open_paren + 1 : close_engine.start()]
    columns: list[ColumnSpec] = []
    primary_key: tuple[str, ...] = ()
    for item in _split_top_level(body):
        if item.upper().startswith("PRIMARY KEY"):
            key_match = re.search(r"\((.*)\)", item, re.DOTALL)
            if key_match is None:
                raise SyntheticW2Error(f"PRIMARY KEY is malformed for {name}")
            primary_key = tuple(
                part.strip().strip("`")
                for part in _split_top_level(key_match.group(1))
                if part.strip()
            )
            continue
        upper = item.upper()
        if upper.startswith(("UNIQUE", "KEY", "INDEX", "CONSTRAINT", "FOREIGN")):
            continue
        col_match = re.match(r"`([^`]+)`\s+(.+)", item, re.DOTALL)
        if col_match is None:
            continue
        sql_type = col_match.group(2).split(" COMMENT ")[0]
        sql_type = sql_type.split(" DEFAULT ")[0]
        sql_type = re.split(r"\s+NOT\s+NULL|\s+NULL", sql_type, maxsplit=1)[0]
        sql_type = " ".join(sql_type.split())
        columns.append(ColumnSpec(col_match.group(1), sql_type))
        if "PRIMARY KEY" in item.upper() and not primary_key:
            primary_key = (col_match.group(1),)
    pk_indexes = tuple(
        next(index for index, column in enumerate(columns) if column.name == pk_name)
        for pk_name in primary_key
        if any(column.name == pk_name for column in columns)
    )
    if not primary_key:
        return TableScalePlan(name, tuple(columns), (), "none", (), True, None)
    first_pk = next(column for column in columns if column.name == primary_key[0])
    strategy = classify_pk_strategy(first_pk.sql_type)
    if strategy == "none":
        return TableScalePlan(
            name,
            tuple(columns),
            primary_key,
            "none",
            pk_indexes,
            False,
            "primary key type is not integer or character",
        )
    return TableScalePlan(name, tuple(columns), primary_key, strategy, pk_indexes, True, None)


def parse_sql_value(token: str) -> object:
    stripped = token.strip()
    if stripped.upper() == "NULL":
        return None
    if stripped.startswith("'") and stripped.endswith("'"):
        inner = stripped[1:-1].replace("''", "'").replace("\\'", "'")
        return inner
    if re.fullmatch(r"-?\d+", stripped):
        return int(stripped)
    return stripped


def format_sql_value(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        raise SyntheticW2Error("boolean SQL values are not supported")
    if isinstance(value, int):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def split_value_tuples(values_blob: str) -> list[list[str]]:
    tuples: list[list[str]] = []
    index = 0
    length = len(values_blob)
    while index < length:
        while index < length and values_blob[index] in " \t\r\n,":
            index += 1
        if index >= length:
            break
        if values_blob[index] != "(":
            raise SyntheticW2Error("INSERT VALUES tuple must start with '('")
        index += 1
        fields: list[str] = []
        field_start = index
        quote: str | None = None
        depth = 0
        while index < length:
            char = values_blob[index]
            if quote is not None:
                if char == quote:
                    if quote == "'" and index + 1 < length and values_blob[index + 1] == "'":
                        index += 2
                        continue
                    quote = None
                elif char == "\\" and index + 1 < length:
                    index += 2
                    continue
                index += 1
                continue
            if char in {"'", '"'}:
                quote = char
                index += 1
                continue
            if char == "(":
                depth += 1
            elif char == ")" and depth == 0:
                fields.append(values_blob[field_start:index].strip())
                index += 1
                break
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 0:
                fields.append(values_blob[field_start:index].strip())
                field_start = index + 1
            index += 1
        else:
            raise SyntheticW2Error("INSERT VALUES tuple is not closed")
        tuples.append(fields)
    return tuples


def transform_tuple_tokens(
    tokens: list[str],
    plan: TableScalePlan,
    replica: int,
) -> list[str] | None:
    if replica == 0 or not plan.scaled or plan.strategy == "none" or not plan.pk_indexes:
        return list(tokens)
    rewritten = list(tokens)
    pk_index = plan.pk_indexes[0]
    if pk_index >= len(rewritten):
        return None
    parsed = parse_sql_value(rewritten[pk_index])
    if parsed is None:
        return rewritten
    if plan.strategy == "integer":
        if not isinstance(parsed, int):
            return None
        column = plan.columns[pk_index]
        limit = integer_limit(column.sql_type)
        next_value = replica_integer(parsed, replica)
        if limit is not None and next_value > limit[0]:
            return None
        rewritten[pk_index] = format_sql_value(next_value)
        return rewritten
    if not isinstance(parsed, str):
        return None
    rewritten[pk_index] = format_sql_value(replica_varchar(parsed, replica))
    return rewritten


def _iter_dump_chunks(sql: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    in_create = False
    for line in sql.splitlines(keepends=True):
        stripped = line.lstrip()
        if in_create:
            current.append(line)
            if re.search(r"\)\s*ENGINE\s*=", line, re.IGNORECASE) and line.rstrip().endswith(";"):
                chunks.append("".join(current))
                current = []
                in_create = False
            continue
        if stripped.upper().startswith("CREATE TABLE "):
            in_create = True
            current = [line]
            continue
        if stripped.upper().startswith("INSERT INTO "):
            chunks.append(line)
            continue
        chunks.append(line)
    if current:
        chunks.append("".join(current))
    return chunks


def build_table_plans(sql: str) -> dict[str, TableScalePlan]:
    plans: dict[str, TableScalePlan] = {}
    for chunk in _iter_dump_chunks(sql):
        if chunk.lstrip().upper().startswith("CREATE TABLE "):
            plan = parse_create_table(chunk.rstrip().rstrip(";"))
            plans[plan.name] = plan
    return plans


def scale_insert_rows(statement: str, plan: TableScalePlan, replica: int) -> tuple[str, list[str]] | None:
    stripped = statement.strip()
    if stripped.endswith(";"):
        stripped = stripped[:-1]
    match = _INSERT_HEAD.match(stripped)
    if match is None:
        raise SyntheticW2Error("INSERT statement is malformed")
    values_blob = stripped[match.end() :]
    rewritten_rows: list[str] = []
    for tokens in split_value_tuples(values_blob):
        transformed = transform_tuple_tokens(tokens, plan, replica)
        if transformed is None:
            return None
        rewritten_rows.append("(" + ",".join(transformed) + ")")
    return match.group(1), rewritten_rows


def format_insert_statement(table: str, rows: list[str]) -> str:
    if not rows:
        raise SyntheticW2Error("INSERT statement requires at least one row")
    return f"INSERT INTO `{table}` VALUES {','.join(rows)};\n"


def build_scaled_replay_sql(
    source_sql: str,
    *,
    target_bytes: int = TARGET_REPLAY_BYTES,
    min_bytes: int = MIN_REPLAY_BYTES,
    max_bytes: int = MAX_REPLAY_BYTES,
    seed: str = DEFAULT_SEED,
    enforce_production_band: bool = True,
) -> tuple[bytes, dict[str, object]]:
    del seed
    if target_bytes < min_bytes or target_bytes > max_bytes:
        raise SyntheticW2Error("W2 size target is outside the configured band")
    if max_bytes >= REPLAY_HARD_CAP_BYTES:
        raise SyntheticW2Error("W2 size band must stay under the 200 MiB hard cap")
    plans = build_table_plans(source_sql)
    chunks = _iter_dump_chunks(source_sql)
    parts: list[bytes] = []
    unscaled: list[str] = []
    scaled_tables: list[str] = []

    def current_size() -> int:
        return sum(len(part) for part in parts)

    for chunk in chunks:
        parts.append(chunk.encode("utf-8"))

    replica = 1
    while current_size() < target_bytes:
        progressed = False
        for chunk in chunks:
            if current_size() >= target_bytes:
                break
            stripped = chunk.lstrip()
            if not stripped.upper().startswith("INSERT INTO "):
                continue
            match = _INSERT_HEAD.match(stripped.strip())
            if match is None:
                continue
            table = match.group(1)
            plan = plans.get(table)
            if plan is None or not plan.scaled:
                if table not in unscaled:
                    unscaled.append(table)
                continue
            scaled = scale_insert_rows(chunk, plan, replica)
            if scaled is None:
                if table not in unscaled:
                    unscaled.append(table)
                continue
            table_name, rows = scaled
            remaining = max_bytes - current_size()
            if remaining <= 0:
                break
            prefix = f"INSERT INTO `{table_name}` VALUES ".encode("utf-8")
            selected: list[str] = []
            encoded_rows: list[bytes] = []
            for row in rows:
                candidate = row.encode("utf-8")
                extra = len(candidate) + (1 if selected else 0) + 2
                if len(prefix) + sum(len(item) for item in encoded_rows) + extra > remaining:
                    break
                if current_size() + len(prefix) + sum(len(item) for item in encoded_rows) + extra >= (
                    REPLAY_HARD_CAP_BYTES
                ):
                    break
                selected.append(row)
                encoded_rows.append(candidate)
            if not selected:
                continue
            statement = format_insert_statement(table_name, selected).encode("utf-8")
            if current_size() + len(statement) >= REPLAY_HARD_CAP_BYTES:
                continue
            if current_size() + len(statement) > max_bytes:
                continue
            parts.append(statement)
            progressed = True
            if table_name not in scaled_tables:
                scaled_tables.append(table_name)
        if current_size() >= target_bytes:
            break
        if not progressed:
            if min_bytes <= current_size() <= max_bytes:
                break
            raise SyntheticW2Error(
                "W2 scaler could not reach the replay size band without exceeding the hard cap"
            )
        replica += 1
        if replica > 16:
            raise SyntheticW2Error("W2 scaler exceeded the replica bound")

    payload = b"".join(parts)
    if enforce_production_band:
        validate_replay_size(len(payload))
    elif len(payload) < min_bytes or len(payload) > max_bytes:
        raise SyntheticW2Error(
            f"W2 replay.sql {len(payload)} bytes is outside {min_bytes}-{max_bytes}"
        )
    elif len(payload) >= REPLAY_HARD_CAP_BYTES:
        raise SyntheticW2Error("W2 replay.sql must stay under the 200 MiB hard cap")
    payload.decode("utf-8")
    report = {
        "generator_version": GENERATOR_VERSION,
        "source_sql_bytes": len(source_sql.encode("utf-8")),
        "replay_sql_bytes": len(payload),
        "replicas_emitted": replica,
        "scaled_tables": scaled_tables,
        "unscaled_tables": unscaled,
        "table_count": len(plans),
    }
    return payload, report
