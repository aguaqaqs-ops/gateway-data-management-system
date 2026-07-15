from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import json
import os
import re
from pathlib import Path
import socket
import subprocess
import time

from ...core.digests import DigestRef
from ...core.identifiers import canonical_identifier


_SAFE_REF_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_ANSI_ESCAPE_SEQUENCE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
# LOAD DATA through user variables does not preserve SQL NULL vs literal "NULL" cleanly.
_LOAD_DATA_SQL_NULL_SENTINEL = "__BACKEND_VNEXT_SQL_NULL__"
_LOAD_DATA_NULL_LITERAL_SENTINEL = "__BACKEND_VNEXT_NULL_LITERAL__"


@dataclass(frozen=True, slots=True)
class CommandError(RuntimeError):
    tool: str
    command: tuple[str, ...]
    returncode: int
    output_summary: str

    def __str__(self) -> str:
        return (
            f"{self.tool} command failed: "
            f"command={' '.join(self.command)}, exit_code={self.returncode}"
        )


class DoltCli:
    def __init__(self, *, dolt_bin: str = "dolt") -> None:
        self.dolt_bin = dolt_bin

    def run(
        self,
        cwd: Path,
        args: Sequence[str],
        *,
        check: bool = True,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = (self.dolt_bin, *args)
        run_env = os.environ.copy()
        run_env["DOLT_PAGER"] = "cat"
        if env is not None:
            run_env.update(env)
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            input=input_text,
            text=True,
            env=run_env,
        )
        if check and result.returncode != 0:
            raise _command_error("dolt", result)
        return result

    def init_repo(self, repo_dir: Path, *, name: str, email: str) -> None:
        repo_dir.mkdir(parents=True, exist_ok=True)
        if (repo_dir / ".dolt").exists():
            return
        self.run(
            repo_dir,
            ("init", "--name", name, "--email", email),
        )

    def execute_sql_file(self, repo_dir: Path, sql_file: Path) -> None:
        self.run(
            repo_dir,
            ("sql", "-f", str(sql_file)),
        )

    def query_json(self, repo_dir: Path, sql: str) -> tuple[dict[str, object], ...]:
        result = self.run(
            repo_dir,
            ("sql", "-r", "json", "-q", sql),
        )
        payload = json.loads(result.stdout or '{"rows":[]}')
        if not isinstance(payload, dict):
            raise TypeError("dolt json query payload must be an object")
        rows = payload.get("rows", [])
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            raise TypeError("dolt query rows payload must be a list")
        normalized_rows: list[dict[str, object]] = []
        for row in rows:
            if not isinstance(row, dict):
                raise TypeError("dolt query row must be an object")
            normalized_rows.append(dict(row))
        return tuple(normalized_rows)

    def show_tables(self, repo_dir: Path) -> tuple[dict[str, object], ...]:
        return self.query_json(repo_dir, "show tables;")

    def list_table_names(self, repo_dir: Path) -> tuple[str, ...]:
        rows = self.query_json(
            repo_dir,
            "select table_name from information_schema.tables "
            "where table_schema = database() order by table_name;",
        )
        table_names: list[str] = []
        for row in rows:
            value = _row_value(row, "TABLE_NAME", "table_name")
            if value is None:
                continue
            canonical_name = canonical_identifier(str(value))
            if canonical_name:
                table_names.append(canonical_name)
        return tuple(table_names)

    def describe_table(self, repo_dir: Path, table_name: str) -> tuple[dict[str, object], ...]:
        return self.query_json(repo_dir, f"describe {_quote_identifier(table_name)};")

    def describe_tables(
        self,
        repo_dir: Path,
        table_names: Sequence[str],
    ) -> dict[str, tuple[dict[str, object], ...]]:
        normalized_names = _normalize_table_names(table_names)
        if not normalized_names:
            return {}
        table_literals = ", ".join(_sql_literal(table_name) for table_name in normalized_names)
        rows = self.query_json(
            repo_dir,
            "select table_name, column_name, ordinal_position, column_type, "
            "is_nullable, column_key from information_schema.columns "
            f"where table_schema = database() and table_name in ({table_literals}) "
            "order by table_name, ordinal_position;",
        )
        grouped: dict[str, list[dict[str, object]]] = {
            table_name: [] for table_name in normalized_names
        }
        for row in rows:
            table_name = canonical_identifier(str(_row_value(row, "TABLE_NAME", "table_name") or ""))
            if table_name not in grouped:
                continue
            column_name = _row_value(row, "COLUMN_NAME", "column_name")
            if column_name is None:
                continue
            nullable = str(_row_value(row, "IS_NULLABLE", "is_nullable") or "").upper()
            grouped[table_name].append(
                {
                    "Field": str(column_name),
                    "Type": str(_row_value(row, "COLUMN_TYPE", "column_type") or ""),
                    "Null": "YES" if nullable == "YES" else "NO",
                    "Key": str(_row_value(row, "COLUMN_KEY", "column_key") or ""),
                    "Default": None,
                    "Extra": "",
                }
            )
        return {table_name: tuple(rows) for table_name, rows in grouped.items()}

    def select_rows(
        self,
        repo_dir: Path,
        table_name: str,
        *,
        order_by_columns: Sequence[str] = (),
        binary_order_by_columns: Sequence[str] = (),
    ) -> tuple[dict[str, object], ...]:
        order_clause = ""
        if order_by_columns:
            binary_columns = {
                canonical_identifier(column)
                for column in binary_order_by_columns
                if str(column).strip()
            }
            order_clause = " order by " + ", ".join(
                (
                    f"BINARY {_quote_identifier(column)}"
                    if canonical_identifier(column) in binary_columns
                    else _quote_identifier(column)
                )
                for column in order_by_columns
            )
        rows = self.query_json(
            repo_dir,
            f"select * from {_quote_identifier(table_name)}{order_clause};",
        )
        normalized_rows: list[dict[str, object]] = []
        for row in rows:
            normalized_rows.append({canonical_identifier(key): value for key, value in row.items()})
        return tuple(normalized_rows)

    def count_rows(self, repo_dir: Path, table_name: str) -> int:
        rows = self.query_json(
            repo_dir,
            f"select count(*) as row_count from {_quote_identifier(table_name)};",
        )
        if not rows:
            return 0
        value = rows[0].get("row_count")
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def count_rows_batch(
        self,
        repo_dir: Path,
        table_names: Sequence[str],
        *,
        chunk_size: int = 100,
    ) -> dict[str, int]:
        normalized_names = _normalize_table_names(table_names)
        if not normalized_names:
            return {}
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        counts: dict[str, int] = {}
        for start in range(0, len(normalized_names), chunk_size):
            chunk = normalized_names[start : start + chunk_size]
            sql = " union all ".join(
                f"select {_sql_literal(table_name)} as table_name, "
                f"count(*) as row_count from {_quote_identifier(table_name)}"
                for table_name in chunk
            )
            rows = self.query_json(repo_dir, sql)
            for row in rows:
                table_name = canonical_identifier(str(_row_value(row, "TABLE_NAME", "table_name") or ""))
                if table_name not in chunk:
                    continue
                value = _row_value(row, "ROW_COUNT", "row_count")
                try:
                    counts[table_name] = int(value)
                except (TypeError, ValueError):
                    counts[table_name] = 0
        return counts

    def resolve_ref_commit(self, *, repository_id: str, ref: str, repo_dir: Path) -> str | None:
        del repository_id
        cli_ref = _cli_ref_name(ref)
        try:
            rows = self.query_json(repo_dir, f"select hashof({_sql_literal(cli_ref)}) as h;")
        except CommandError as exc:
            if "invalid ref spec" in exc.output_summary.lower():
                return None
            raise
        if not rows:
            return None
        value = rows[0].get("h")
        if not isinstance(value, str) or not value:
            return None
        return value

    def table_import(
        self,
        repo_dir: Path,
        *,
        table_name: str,
        file_path: Path,
        schema_path: Path,
        columns: Sequence[str] | None = None,
        file_type: str | None = None,
        replace: bool = True,
        force: bool = True,
        no_header: bool = False,
        quiet: bool = False,
    ) -> None:
        args: list[str] = ["table", "import"]
        if replace:
            args.append("-c")
        if force:
            args.append("-f")
        args.extend(["--schema", str(schema_path)])
        if no_header:
            args.append("--no-header")
        if columns:
            args.extend(["--columns", ",".join(columns)])
        if file_type:
            args.extend(["--file-type", file_type])
        if quiet:
            args.append("--quiet")
        args.extend([table_name, str(file_path)])
        self.run(repo_dir, tuple(args))

    def add_all(self, repo_dir: Path) -> None:
        self.run(repo_dir, ("add", "."))

    def commit(self, repo_dir: Path, *, message: str, allow_empty: bool = False) -> None:
        args = ["commit"]
        if allow_empty:
            args.append("--allow-empty")
        args.extend(["-m", message])
        self.run(repo_dir, tuple(args))

    def commit_and_get_hash(self, repo_dir: Path, *, message: str) -> str | None:
        self.add_all(repo_dir)
        self.commit(repo_dir, message=message)
        return self.current_head_hash(repo_dir)

    def current_head_hash(self, repo_dir: Path) -> str | None:
        result = self.run(repo_dir, ("log", "--oneline"), check=False)
        if result.returncode != 0:
            return None
        for line in _ANSI_ESCAPE_SEQUENCE.sub("", result.stdout).splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            return stripped.split(maxsplit=1)[0]
        return None

    def checkout(self, repo_dir: Path, ref: str, *, force: bool = False) -> None:
        args = ["checkout"]
        if force:
            args.append("--force")
        args.append(ref)
        self.run(repo_dir, tuple(args))

    def checkout_reset_branch(self, repo_dir: Path, branch_name: str, start_point: str) -> None:
        self.run(repo_dir, ("checkout", "-B", branch_name, start_point))

    def branch_force(self, repo_dir: Path, branch_name: str, commit_hash: str) -> None:
        self.run(repo_dir, ("branch", "-f", branch_name, commit_hash))

    def tag_create(self, repo_dir: Path, tag_name: str, commit_hash: str) -> None:
        self.run(repo_dir, ("tag", tag_name, commit_hash))

    def version(self, repo_dir: Path) -> str:
        result = self.run(repo_dir, ("version",))
        return _extract_version(result.stdout + "\n" + result.stderr)


class MysqlCli:
    def __init__(self, *, mysql_bin: str = "mysql") -> None:
        self.mysql_bin = mysql_bin

    def run(
        self,
        *,
        host: str,
        port: int,
        database: str,
        sql: str,
        local_infile: bool = False,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            self.mysql_bin,
            "--protocol=tcp",
            f"--host={host}",
            f"--port={port}",
            "--user=root",
            f"--database={database}",
        ]
        if local_infile:
            command.append("--local-infile=1")
        command.extend(["-e", sql])
        result = subprocess.run(command, capture_output=True, text=True)
        if check and result.returncode != 0:
            raise _command_error("mysql", result)
        return result

    def health_check(self, *, host: str, port: int, database: str) -> None:
        self.run(
            host=host,
            port=port,
            database=database,
            sql="SELECT 1 AS one;",
        )

    def execute(self, *, host: str, port: int, database: str, sql: str) -> str:
        result = self.run(
            host=host,
            port=port,
            database=database,
            sql=sql,
            local_infile=True,
        )
        return result.stdout

    def create_table(self, *, host: str, port: int, database: str, create_sql: str) -> None:
        self.run(
            host=host,
            port=port,
            database=database,
            sql=create_sql,
            local_infile=True,
        )

    def load_data(
        self,
        *,
        host: str,
        port: int,
        database: str,
        table_name: str,
        file_path: Path,
        columns: Sequence[str],
    ) -> None:
        column_variables = [f"@c{index}" for index, _ in enumerate(columns)]
        set_assignments = ", ".join(
            (
                f"{_quote_identifier(column)} = CASE "
                f"WHEN {variable} = {_sql_literal(_LOAD_DATA_SQL_NULL_SENTINEL)} THEN NULL "
                f"WHEN {variable} = {_sql_literal(_LOAD_DATA_NULL_LITERAL_SENTINEL)} THEN {_sql_literal('NULL')} "
                f"ELSE {variable} END"
            )
            for column, variable in zip(columns, column_variables, strict=True)
        )
        sql = (
            f"LOAD DATA LOCAL INFILE {_sql_literal(str(file_path.resolve()))} "
            f"INTO TABLE {_quote_identifier(table_name)} "
            "FIELDS TERMINATED BY '\\t' ESCAPED BY '\\\\' "
            "LINES TERMINATED BY '\\n' "
            f"({', '.join(column_variables)}) "
            f"SET {set_assignments};"
        )
        self.run(
            host=host,
            port=port,
            database=database,
            sql=sql,
            local_infile=True,
        )


class DoltServerSession:
    def __init__(
        self,
        *,
        server_root: Path,
        repository_id: str,
        port: int,
        host: str = "127.0.0.1",
        dolt_bin: str = "dolt",
        mysql_bin: str = "mysql",
        init_name: str = "backend-vnext",
        init_email: str = "backend-vnext@example.invalid",
        startup_timeout_seconds: float = 30.0,
        log_path: Path | None = None,
    ) -> None:
        self.server_root = server_root
        self.repository_id = repository_id
        self.database_name = _safe_database_name(repository_id)
        self.port = port
        self.host = host
        self.dolt = DoltCli(dolt_bin=dolt_bin)
        self.mysql = MysqlCli(mysql_bin=mysql_bin)
        self.init_name = init_name
        self.init_email = init_email
        self.startup_timeout_seconds = startup_timeout_seconds
        self.log_path = log_path or (server_root / "logs" / f"{self.database_name}.server.log")
        self.config_path = server_root / "server.yaml"
        self.repo_dir = self.server_root / self.database_name
        self._process: subprocess.Popen[str] | None = None
        self._log_handle: object | None = None

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        if self.is_running:
            return
        self.server_root.mkdir(parents=True, exist_ok=True)
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        self.dolt.init_repo(self.repo_dir, name=self.init_name, email=self.init_email)
        self._write_config()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_handle = self.log_path.open("a", encoding="utf-8")
        env = os.environ.copy()
        env["DOLT_PAGER"] = "cat"
        self._process = subprocess.Popen(
            (
                self.dolt.dolt_bin,
                "sql-server",
                "--config",
                str(self.config_path),
            ),
            cwd=self.repo_dir,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
        )
        ready = self._wait_for_ready()
        if not ready:
            self._terminate_process(force=True)
            raise CommandError(
                tool="dolt",
                command=(self.dolt.dolt_bin, "sql-server", "--config", str(self.config_path)),
                returncode=-1,
                output_summary=self._read_log_tail(),
            )
        self.mysql.health_check(host=self.host, port=self.port, database=self.database_name)

    def close(self) -> None:
        self._terminate_process(force=False)

    def __enter__(self) -> "DoltServerSession":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def create_table(self, create_sql: str) -> None:
        self.mysql.create_table(
            host=self.host,
            port=self.port,
            database=self.database_name,
            create_sql=create_sql,
        )

    def load_data(self, *, table_name: str, file_path: Path, columns: Sequence[str]) -> None:
        self.mysql.load_data(
            host=self.host,
            port=self.port,
            database=self.database_name,
            table_name=table_name,
            file_path=file_path,
            columns=columns,
        )

    def _write_config(self) -> None:
        content = "\n".join(
            [
                "log_level: info",
                "listener:",
                f"  host: {json.dumps(self.host)}",
                f"  port: {self.port}",
                f"data_dir: {json.dumps(str(self.server_root))}",
                "system_variables:",
                "  local_infile: 1",
            ]
        )
        self.config_path.write_text(content + "\n", encoding="utf-8")

    def _wait_for_ready(self) -> bool:
        deadline = time.monotonic() + self.startup_timeout_seconds
        while time.monotonic() < deadline:
            if self._process is not None and self._process.poll() is not None:
                return False
            if self.log_path.is_file():
                try:
                    log_text = self.log_path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    log_text = ""
                if "Server ready" in log_text:
                    return True
            time.sleep(0.1)
        return False

    def _terminate_process(self, *, force: bool) -> None:
        if self._process is None:
            if self._log_handle is not None:
                try:
                    self._log_handle.close()
                except Exception:
                    pass
                self._log_handle = None
            return
        if self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=10)
            except Exception:
                self._process.kill()
                self._process.wait(timeout=10)
        self._process = None
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None

    def _read_log_tail(self, *, max_lines: int = 80) -> str:
        if not self.log_path.is_file():
            return ""
        try:
            lines = self.log_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            return ""
        tail = lines[-max_lines:]
        return "\n".join(tail)[-4000:]


def _column_list(columns: Sequence[str]) -> str:
    return ", ".join(_quote_identifier(column) for column in columns)


def _extract_version(output: str) -> str:
    match = re.search(r"(\d+(?:\.\d+){1,3})", output)
    if match is None:
        return output.strip()
    return match.group(1)


def _quote_identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _row_value(row: dict[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in row:
            return row[key]
    return None


def _normalize_table_names(table_names: Sequence[str]) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for table_name in table_names:
        canonical_name = canonical_identifier(str(table_name))
        if not canonical_name or canonical_name in seen:
            continue
        seen.add(canonical_name)
        normalized.append(canonical_name)
    return tuple(normalized)


def _cli_ref_name(ref: str) -> str:
    if ref.startswith("refs/heads/"):
        return ref.removeprefix("refs/heads/")
    if ref.startswith("refs/tags/"):
        return ref.removeprefix("refs/tags/")
    return ref


def _safe_database_name(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("database name must be a non-empty string")
    if _SAFE_REF_SEGMENT.fullmatch(text):
        return text
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    cleaned = cleaned.strip("._-")
    if not cleaned:
        raise ValueError("database name can not be derived from the provided value")
    if not cleaned[0].isalnum():
        cleaned = f"db_{cleaned}"
    return cleaned


def _command_error(tool: str, result: subprocess.CompletedProcess[str]) -> CommandError:
    args = tuple(str(arg) for arg in result.args)
    return CommandError(
        tool=tool,
        command=args[1:] if len(args) > 0 else (),
        returncode=result.returncode,
        output_summary=_summarize_output(_combined_output(result)),
    )


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return "\n".join(part for part in (result.stdout, result.stderr) if part)


def _summarize_output(output: str) -> str:
    return " ".join(output.strip().split())[:240]
