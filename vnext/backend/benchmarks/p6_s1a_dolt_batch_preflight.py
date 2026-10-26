"""Preflight batched mutation SQL forms against the pinned Dolt CLI.

This synthetic-only tool keeps its Dolt repository, command file, and JSON report
under the caller-provided log directory. It deliberately does not remove files
or Dolt refs. It compares row-wise replay with batched DELETE+INSERT, upsert,
and CASE UPDATE forms for single-key, composite-key, and GID_NO_V1-like tables.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Sequence, TypeVar

_EXPECTED_DOLT_VERSION = "2.1.11"
_BATCH_ROWS = 256
_BATCH_BYTES = 4 * 1024 * 1024
_BASE_ROWS = 1024
_UPDATE_KEYS = tuple(range(0, 256))
_DELETE_KEYS = tuple(range(256, 512))
_INSERT_KEYS = tuple(range(1024, 1280))
_FORMS = ("delete_insert", "upsert", "case_update")
_AUTHOR = "S1a Preflight <s1a-preflight@gateway.invalid>"
_Item = TypeVar("_Item")


@dataclass(frozen=True, slots=True)
class _Table:
    name: str
    key_columns: tuple[str, ...]
    value_columns: tuple[str, ...]
    create_sql: str
    ordered: bool = False


_TABLES = (
    _Table(
        name="preflight_single",
        key_columns=("id",),
        value_columns=("payload",),
        create_sql=(
            "CREATE TABLE `preflight_single` ("
            "`id` BIGINT NOT NULL, `payload` LONGTEXT NOT NULL, "
            "PRIMARY KEY (`id`))"
        ),
    ),
    _Table(
        name="preflight_composite",
        key_columns=("k1", "k2"),
        value_columns=("payload",),
        create_sql=(
            "CREATE TABLE `preflight_composite` ("
            "`k1` INT NOT NULL, `k2` INT NOT NULL, `payload` LONGTEXT NOT NULL, "
            "PRIMARY KEY (`k1`, `k2`))"
        ),
    ),
    _Table(
        name="preflight_gid_ordered",
        key_columns=("gid",),
        value_columns=("no", "payload"),
        create_sql=(
            "CREATE TABLE `preflight_gid_ordered` ("
            "`gid` BIGINT UNSIGNED NOT NULL, `no` INT NOT NULL, "
            "`payload` LONGTEXT NOT NULL, PRIMARY KEY (`gid`))"
        ),
        ordered=True,
    ),
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _run(
    arguments: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        arguments,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(arguments)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def _sql_file(db_path: Path, env: dict[str, str], sql: str) -> float:
    command_path = db_path.parent / "current.sql"
    command_path.write_text(sql, encoding="utf-8")
    started = time.perf_counter()
    _run(("dolt", "sql", "--file", str(command_path)), cwd=db_path, env=env)
    return time.perf_counter() - started


def _query(db_path: Path, env: dict[str, str], sql: str) -> str:
    return _run(
        ("dolt", "sql", "--result-format=csv", "--query", sql),
        cwd=db_path,
        env=env,
    ).stdout


def _dolt_version(env: dict[str, str]) -> str:
    output = _run(("dolt", "version"), env=env).stdout
    match = re.search(r"dolt version ([0-9.]+)", output)
    if match is None:
        raise RuntimeError(f"could not parse Dolt version: {output.strip()}")
    return match.group(1)


def _key(table: _Table, index: int) -> tuple[int, ...]:
    if table.name == "preflight_single":
        return (index,)
    if table.name == "preflight_composite":
        return (index // 64, index % 64)
    return (4_000_000_000 + index,)


def _key_sql(key: tuple[int, ...]) -> str:
    if len(key) == 1:
        return str(key[0])
    return "(" + ", ".join(str(value) for value in key) + ")"


def _row_values(table: _Table, index: int, stage: str) -> tuple[str, ...]:
    key = _key(table, index)
    if table.ordered:
        no = index if stage == "base" else (10_000 + index if stage == "updated" else 20_000 + index)
        payload = f"{stage}-{index}"
        return (*map(str, key), str(no), _literal(payload))
    return (*map(str, key), _literal(f"{stage}-{index}"))


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _insert_statement(table: _Table, rows: Sequence[tuple[str, ...]]) -> str:
    columns = (*table.key_columns, *table.value_columns)
    column_sql = ", ".join(f"`{column}`" for column in columns)
    row_sql = ", ".join("(" + ", ".join(row) + ")" for row in rows)
    return f"INSERT INTO `{table.name}` ({column_sql}) VALUES {row_sql};\n"


def _upsert_statement(table: _Table, rows: Sequence[tuple[str, ...]]) -> str:
    update_sql = ", ".join(
        f"`{column}`=VALUES(`{column}`)" for column in table.value_columns
    )
    return _insert_statement(table, rows).removesuffix(";\n") + f" ON DUPLICATE KEY UPDATE {update_sql};\n"


def _key_predicate(
    table: _Table,
    keys: Sequence[tuple[int, ...]],
    *,
    composite_form: str,
) -> str:
    if len(table.key_columns) == 1:
        column = table.key_columns[0]
        return f"`{column}` IN (" + ",".join(str(key[0]) for key in keys) + ")"
    if composite_form == "tuple_in":
        columns = "(" + ",".join(f"`{column}`" for column in table.key_columns) + ")"
        values = ",".join(_key_sql(key) for key in keys)
        return f"{columns} IN ({values})"
    return " OR ".join(
        "(" + " AND ".join(
            f"`{column}`={value}" for column, value in zip(table.key_columns, key, strict=True)
        ) + ")"
        for key in keys
    )


def _statement_batches(
    items: Sequence[_Item],
    render: Callable[[Sequence[_Item]], str],
) -> tuple[str, ...]:
    batches: list[str] = []
    pending: list[_Item] = []
    for item in items:
        candidate = [*pending, item]
        candidate_sql = render(candidate)
        if pending and (
            len(pending) >= _BATCH_ROWS
            or len(candidate_sql.encode("utf-8")) > _BATCH_BYTES
        ):
            batches.append(render(pending))
            pending = []
            candidate_sql = render((item,))
        if len(candidate_sql.encode("utf-8")) > _BATCH_BYTES:
            raise RuntimeError("one mutation row exceeds the 4 MiB statement limit")
        pending.append(item)
    if pending:
        batches.append(render(pending))
    if any(len(sql.encode("utf-8")) > _BATCH_BYTES for sql in batches):
        raise RuntimeError("generated statement exceeded the 4 MiB byte limit")
    return tuple(batches)


def _delete_batches(
    table: _Table,
    keys: Sequence[tuple[int, ...]],
    *,
    composite_form: str,
) -> tuple[str, ...]:
    def render(items: Sequence[tuple[int, ...]]) -> str:
        return (
            f"DELETE FROM `{table.name}` WHERE "
            f"{_key_predicate(table, items, composite_form=composite_form)};\n"
        )

    return _statement_batches(list(keys), render)


def _insert_batches(
    table: _Table,
    indices_and_stages: Sequence[tuple[int, str]],
    *,
    upsert: bool,
) -> tuple[str, ...]:
    def render(items: Sequence[tuple[int, str]]) -> str:
        rows = [_row_values(table, index, stage) for index, stage in items]
        return _upsert_statement(table, rows) if upsert else _insert_statement(table, rows)

    return _statement_batches(list(indices_and_stages), render)


def _case_update_batches(
    table: _Table,
    indices: Sequence[int],
    *,
    composite_form: str,
    payload_override: str | None = None,
) -> tuple[str, ...]:
    def render(items: Sequence[int]) -> str:
        typed_indices = list(items)
        assignments: list[str] = []
        for column in table.value_columns:
            choices = []
            for index in typed_indices:
                key = _key(table, index)
                predicate = " AND ".join(
                    f"`{key_column}`={value}"
                    for key_column, value in zip(table.key_columns, key, strict=True)
                )
                if column == "payload":
                    value = _literal(payload_override if payload_override is not None else f"updated-{index}")
                else:
                    value = str(10_000 + index)
                choices.append(f"WHEN {predicate} THEN {value}")
            fallback = f"`{column}`"
            assignments.append(f"`{column}`=CASE {' '.join(choices)} ELSE {fallback} END")
        where = _key_predicate(
            table,
            [_key(table, index) for index in typed_indices],
            composite_form=composite_form,
        )
        return f"UPDATE `{table.name}` SET {', '.join(assignments)} WHERE {where};\n"

    return _statement_batches(list(indices), render)


def _rowwise_sql(table: _Table) -> tuple[str, tuple[int, ...]]:
    statements: list[str] = []
    for index in _UPDATE_KEYS:
        key = _key(table, index)
        predicate = " AND ".join(
            f"`{column}`={value}"
            for column, value in zip(table.key_columns, key, strict=True)
        )
        values = _row_values(table, index, "updated")
        assignments = ", ".join(
            f"`{column}`={value}"
            for column, value in zip(table.value_columns, values[len(table.key_columns) :], strict=True)
        )
        statements.append(f"UPDATE `{table.name}` SET {assignments} WHERE {predicate};\n")
    for index in _DELETE_KEYS:
        key = _key(table, index)
        predicate = " AND ".join(
            f"`{column}`={value}"
            for column, value in zip(table.key_columns, key, strict=True)
        )
        statements.append(f"DELETE FROM `{table.name}` WHERE {predicate};\n")
    for index in _INSERT_KEYS:
        statements.append(_insert_statement(table, (_row_values(table, index, "inserted"),)))
    return "".join(statements), tuple(len(statement.encode("utf-8")) for statement in statements)


def _render_form(table: _Table, form: str, *, composite_form: str) -> tuple[str, tuple[int, ...]]:
    statements: list[str] = []
    if form == "delete_insert":
        delete_keys = [_key(table, index) for index in (*_UPDATE_KEYS, *_DELETE_KEYS)]
        statements.extend(_delete_batches(table, delete_keys, composite_form=composite_form))
        statements.extend(
            _insert_batches(
                table,
                [*((index, "updated") for index in _UPDATE_KEYS), *((index, "inserted") for index in _INSERT_KEYS)],
                upsert=False,
            )
        )
    elif form == "upsert":
        statements.extend(
            _delete_batches(
                table,
                [_key(table, index) for index in _DELETE_KEYS],
                composite_form=composite_form,
            )
        )
        statements.extend(
            _insert_batches(
                table,
                [*((index, "updated") for index in _UPDATE_KEYS), *((index, "inserted") for index in _INSERT_KEYS)],
                upsert=True,
            )
        )
    elif form == "case_update":
        statements.extend(
            _delete_batches(
                table,
                [_key(table, index) for index in _DELETE_KEYS],
                composite_form=composite_form,
            )
        )
        statements.extend(
            _case_update_batches(table, _UPDATE_KEYS, composite_form=composite_form)
        )
        statements.extend(
            _insert_batches(
                table,
                [(index, "inserted") for index in _INSERT_KEYS],
                upsert=False,
            )
        )
    else:
        raise ValueError(f"unknown candidate form {form}")
    sizes = tuple(len(statement.encode("utf-8")) for statement in statements)
    if any(size > _BATCH_BYTES for size in sizes):
        raise RuntimeError(f"{form} emitted a statement above 4 MiB")
    return "".join(statements), sizes


def _indexed_plan(db_path: Path, env: dict[str, str], table: _Table, keys: Sequence[tuple[int, ...]]) -> tuple[str, str]:
    predicate = _key_predicate(table, keys, composite_form="tuple_in")
    result = _run(
        ("dolt", "sql", "--query", f"EXPLAIN ANALYZE SELECT * FROM `{table.name}` WHERE {predicate}"),
        cwd=db_path,
        env=env,
        check=False,
    )
    plan = result.stdout + result.stderr
    if result.returncode == 0 and _plan_has_pk_index(plan, table):
        return "tuple_in", plan.strip()
    if len(table.key_columns) == 1:
        raise RuntimeError(f"EXPLAIN ANALYZE did not show a primary-key lookup for {table.name}: {plan}")
    predicate = _key_predicate(table, keys, composite_form="or_equals")
    result = _run(
        ("dolt", "sql", "--query", f"EXPLAIN ANALYZE SELECT * FROM `{table.name}` WHERE {predicate}"),
        cwd=db_path,
        env=env,
        check=False,
    )
    plan = result.stdout + result.stderr
    if result.returncode != 0 or not _plan_has_pk_index(plan, table):
        raise RuntimeError(f"EXPLAIN ANALYZE found no primary-key lookup for {table.name}: {plan}")
    return "or_equals", plan.strip()


def _plan_has_pk_index(plan: str, table: _Table) -> bool:
    lowered = plan.lower()
    if "indexedtableaccess(" + table.name.lower() + ")" not in lowered:
        return False
    return all(f"{table.name.lower()}.{column.lower()}" in lowered for column in table.key_columns)


def _base_sql() -> str:
    statements = [table.create_sql + ";\n" for table in _TABLES]
    for table in _TABLES:
        for start in range(0, _BASE_ROWS, _BATCH_ROWS):
            rows = [
                _row_values(table, index, "base")
                for index in range(start, min(start + _BATCH_ROWS, _BASE_ROWS))
            ]
            statements.append(_insert_statement(table, rows))
    return "".join(statements)


def _commit(db_path: Path, env: dict[str, str], message: str) -> str:
    _run(("dolt", "add", "--all"), cwd=db_path, env=env)
    _run(
        (
            "dolt",
            "commit",
            "--allow-empty",
            "--message",
            message,
            f"--author={_AUTHOR}",
        ),
        cwd=db_path,
        env=env,
    )
    log = _run(("dolt", "log", "-n", "1", "--oneline"), cwd=db_path, env=env).stdout
    match = re.search(r"^([0-9a-z]{32})\b", log.strip())
    if match is None:
        raise RuntimeError(f"could not parse Dolt commit hash from {log.strip()}")
    return match.group(1)


def _table_hash(db_path: Path, env: dict[str, str], table: _Table) -> str:
    output = _query(db_path, env, f"SELECT DOLT_HASHOF_TABLE('{table.name}') AS table_hash")
    values = [line.strip() for line in output.splitlines() if line.strip()]
    if len(values) < 2:
        raise RuntimeError(f"DOLT_HASHOF_TABLE returned no hash for {table.name}: {output}")
    return values[1].split(",", 1)[0]


def _diff_counts(
    db_path: Path,
    env: dict[str, str],
    table: _Table,
    base_commit: str,
    target_commit: str,
) -> dict[str, int]:
    output = _query(
        db_path,
        env,
        "SELECT diff_type, COUNT(*) AS row_count "
        f"FROM `dolt_diff_{table.name}` "
        f"WHERE from_commit='{base_commit}' AND to_commit='{target_commit}' "
        "GROUP BY diff_type",
    )
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    counts: dict[str, int] = {}
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) >= 2:
            try:
                counts[parts[0]] = int(parts[1])
            except ValueError:
                continue
    return counts


def _create_branch(db_path: Path, env: dict[str, str], base_commit: str, label: str) -> str:
    branch = f"s1a-preflight-{label}-{uuid.uuid4().hex[:8]}"
    _run(("dolt", "branch", branch, base_commit), cwd=db_path, env=env)
    _run(("dolt", "checkout", branch), cwd=db_path, env=env)
    return branch


def _run_branch(
    *,
    db_path: Path,
    env: dict[str, str],
    base_commit: str,
    table: _Table,
    label: str,
    sql: str,
    sizes: Sequence[int],
) -> dict[str, object]:
    branch = _create_branch(db_path, env, base_commit, label)
    execution_seconds = _sql_file(db_path, env, sql)
    target_commit = _commit(db_path, env, label)
    return {
        "branch": branch,
        "target_commit": target_commit,
        "execution_seconds": round(execution_seconds, 6),
        "statement_count": len(sizes),
        "max_statement_bytes": max(sizes, default=0),
        "total_sql_bytes": sum(sizes),
        "table_hash": _table_hash(db_path, env, table),
        "diff_counts": _diff_counts(db_path, env, table, base_commit, target_commit),
    }


def _rowwise_byte_sql(table: _Table, payload: str) -> tuple[str, tuple[int, ...]]:
    key = _key(table, 0)
    predicate = " AND ".join(
        f"`{column}`={value}"
        for column, value in zip(table.key_columns, key, strict=True)
    )
    row = _row_values(table, 0, "updated")
    values = list(row[len(table.key_columns) :])
    values[-1] = _literal(payload)
    assignments = ", ".join(
        f"`{column}`={value}"
        for column, value in zip(table.value_columns, values, strict=True)
    )
    sql = f"UPDATE `{table.name}` SET {assignments} WHERE {predicate};\n"
    return sql, (len(sql.encode("utf-8")),)


def _byte_form_sql(
    table: _Table,
    form: str,
    payload: str,
    *,
    composite_form: str,
) -> tuple[str, tuple[int, ...]]:
    key = _key(table, 0)
    if form == "delete_insert":
        delete = _delete_batches(table, [key], composite_form=composite_form)
        values = list(_row_values(table, 0, "updated"))
        values[-1] = _literal(payload)
        insert = _insert_statement(table, (tuple(values),))
        statements = (*delete, insert)
    elif form == "upsert":
        values = list(_row_values(table, 0, "updated"))
        values[-1] = _literal(payload)
        statements = (_upsert_statement(table, (tuple(values),)),)
    elif form == "case_update":
        statements = _case_update_batches(
            table,
            (0,),
            composite_form=composite_form,
            payload_override=payload,
        )
    else:
        raise ValueError(form)
    sizes = tuple(len(statement.encode("utf-8")) for statement in statements)
    if any(size > _BATCH_BYTES for size in sizes):
        raise RuntimeError(f"{form} exceeded the 4 MiB byte limit in byte-boundary case")
    return "".join(statements), sizes


def _run_table(
    db_path: Path,
    env: dict[str, str],
    base_commit: str,
    table: _Table,
) -> dict[str, object]:
    lookup_indices = (*_UPDATE_KEYS, *_DELETE_KEYS)
    lookup_keys = [_key(table, index) for index in lookup_indices]
    composite_form, explain_plan = _indexed_plan(db_path, env, table, lookup_keys)
    reference_sql, reference_sizes = _rowwise_sql(table)
    reference = _run_branch(
        db_path=db_path,
        env=env,
        base_commit=base_commit,
        table=table,
        label=f"{table.name}-rowwise",
        sql=reference_sql,
        sizes=reference_sizes,
    )
    expected_counts = {"modified": len(_UPDATE_KEYS), "removed": len(_DELETE_KEYS), "added": len(_INSERT_KEYS)}
    if reference["diff_counts"] != expected_counts:
        raise RuntimeError(f"row-wise diff classes mismatch for {table.name}: {reference['diff_counts']}")

    row_results: dict[str, list[dict[str, object]]] = {}
    for form in _FORMS:
        form_sql, sizes = _render_form(table, form, composite_form=composite_form)
        samples: list[dict[str, object]] = []
        for repetition in range(1, 4):
            sample = _run_branch(
                db_path=db_path,
                env=env,
                base_commit=base_commit,
                table=table,
                label=f"{table.name}-{form}-rows-{repetition}",
                sql=form_sql,
                sizes=sizes,
            )
            sample["hash_matches_rowwise"] = sample["table_hash"] == reference["table_hash"]
            sample["diff_matches_rowwise"] = sample["diff_counts"] == expected_counts
            if not sample["hash_matches_rowwise"] or not sample["diff_matches_rowwise"]:
                raise RuntimeError(f"{form} did not match row-wise result for {table.name}: {sample}")
            samples.append(sample)
        row_results[form] = samples

    byte_payload = "x" * (_BATCH_BYTES - 256)
    byte_reference_sql, byte_reference_sizes = _rowwise_byte_sql(table, byte_payload)
    byte_reference = _run_branch(
        db_path=db_path,
        env=env,
        base_commit=base_commit,
        table=table,
        label=f"{table.name}-rowwise-bytes",
        sql=byte_reference_sql,
        sizes=byte_reference_sizes,
    )
    if byte_reference["diff_counts"] != {"modified": 1}:
        raise RuntimeError(f"byte-boundary row-wise diff mismatch for {table.name}")
    byte_results: dict[str, dict[str, object]] = {}
    for form in _FORMS:
        byte_sql, byte_sizes = _byte_form_sql(
            table,
            form,
            byte_payload,
            composite_form=composite_form,
        )
        sample = _run_branch(
            db_path=db_path,
            env=env,
            base_commit=base_commit,
            table=table,
            label=f"{table.name}-{form}-bytes",
            sql=byte_sql,
            sizes=byte_sizes,
        )
        sample["hash_matches_rowwise"] = sample["table_hash"] == byte_reference["table_hash"]
        sample["diff_matches_rowwise"] = sample["diff_counts"] == {"modified": 1}
        if not sample["hash_matches_rowwise"] or not sample["diff_matches_rowwise"]:
            raise RuntimeError(f"{form} byte-boundary result differs for {table.name}: {sample}")
        byte_results[form] = sample

    return {
        "table": table.name,
        "key_columns": list(table.key_columns),
        "ordered_gid_no_v1": table.ordered,
        "composite_predicate": composite_form,
        "explain_analyze_select_plan": explain_plan,
        "row_limit_case": {
            "update_rows": len(_UPDATE_KEYS),
            "delete_rows": len(_DELETE_KEYS),
            "insert_rows": len(_INSERT_KEYS),
            "reference": reference,
            "candidates": row_results,
        },
        "byte_limit_case": {
            "payload_bytes": len(byte_payload.encode("utf-8")),
            "statement_limit_bytes": _BATCH_BYTES,
            "reference": byte_reference,
            "candidates": byte_results,
        },
    }


def run(run_root: Path) -> dict[str, object]:
    run_root = run_root.resolve()
    if run_root.exists() and any(run_root.iterdir()):
        raise RuntimeError(f"run directory is not empty: {run_root}")
    run_root.mkdir(parents=True, exist_ok=True)
    home_path = run_root / "home"
    home_path.mkdir()
    db_path = run_root / "dolt-repository"
    db_path.mkdir()
    env = dict(os.environ)
    env["HOME"] = str(home_path)
    env["LC_ALL"] = "C.UTF-8"
    env["TZ"] = "UTC"
    dolt_home = home_path / ".dolt"
    dolt_home.mkdir()
    (dolt_home / "config_global.json").write_text(
        json.dumps({"versioncheck.disabled": "true", "metrics.disabled": "true"}),
        encoding="utf-8",
    )

    started_at = _now()
    version = _dolt_version(env)
    if version != _EXPECTED_DOLT_VERSION:
        raise RuntimeError(
            f"Dolt version {version} does not match pinned version {_EXPECTED_DOLT_VERSION}"
        )
    head_result = _run(("git", "rev-parse", "HEAD"), cwd=Path(__file__).resolve().parents[3])
    head = head_result.stdout.strip()
    _run(("dolt", "config", "--global", "--add", "user.name", "S1a Preflight"), env=env)
    _run(("dolt", "config", "--global", "--add", "user.email", "s1a-preflight@gateway.invalid"), env=env)
    _run(("dolt", "init"), cwd=db_path, env=env)
    _sql_file(db_path, env, _base_sql())
    base_commit = _commit(db_path, env, "S1a synthetic Dolt batch preflight base")

    tables = [_run_table(db_path, env, base_commit, table) for table in _TABLES]
    finished_at = _now()
    return {
        "schema_version": "phase6-s1a-dolt-batch-preflight/v1",
        "hostname": socket.gethostname(),
        "head": head,
        "started_at_utc": started_at,
        "finished_at_utc": finished_at,
        "dolt_version": version,
        "expected_dolt_version": _EXPECTED_DOLT_VERSION,
        "batch_row_limit": _BATCH_ROWS,
        "batch_statement_byte_limit": _BATCH_BYTES,
        "base_commit": base_commit,
        "tables": tables,
        "result": "PASS",
        "dolt_branches_retained": True,
        "temporary_files_retained": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    started = _now()
    print(f"hostname={socket.gethostname()}", flush=True)
    print(f"started_at_utc={started}", flush=True)
    print(f"head={_run(('git', 'rev-parse', 'HEAD'), cwd=Path(__file__).resolve().parents[3]).stdout.strip()}", flush=True)
    try:
        result = run(args.run_root)
    except Exception as exc:
        failure = {
            "schema_version": "phase6-s1a-dolt-batch-preflight/v1",
            "hostname": socket.gethostname(),
            "started_at_utc": started,
            "finished_at_utc": _now(),
            "result": "FAIL",
            "error": str(exc),
            "temporary_files_retained": True,
            "dolt_branches_retained": True,
        }
        args.run_root.mkdir(parents=True, exist_ok=True)
        (args.run_root / "report.json").write_text(
            json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"preflight_error={exc}", file=sys.stderr, flush=True)
        print(f"finished_at_utc={_now()}", flush=True)
        print("exit_code=1", flush=True)
        return 1
    report_path = args.run_root.resolve() / "report.json"
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"dolt_version={result['dolt_version']}", flush=True)
    print(f"result={result['result']}", flush=True)
    print(f"report={report_path}", flush=True)
    print(f"finished_at_utc={_now()}", flush=True)
    print("exit_code=0", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
