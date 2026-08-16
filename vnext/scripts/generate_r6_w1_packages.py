#!/usr/bin/env python3
"""Stage F evidence driver: identity-projection v1 packages for five fixtures.

This is Storage Projection evidence tooling. It is not a Repository production
path and does not run ``validate_and_extract_import_package``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

_VNEXT_ROOT = Path(__file__).resolve().parents[1]
for _extra in (
    _VNEXT_ROOT / "backend" / "src",
    _VNEXT_ROOT / "repository_service" / "src",
    _VNEXT_ROOT / "repository_contracts" / "src",
    _VNEXT_ROOT / "shared_kernel" / "src",
):
    _text = str(_extra)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from gateway_backend.canonicalization_manifest import (  # noqa: E402
    AssembledTable,
    ManifestColumn,
    REPOSITORY_IMPORT_MEDIA_TYPE,
    assemble_identity_canonicalization,
    durable_canonicalization_manifest,
    repository_import_manifest,
    table_content_digest,
    table_schema_digest,
)
from gateway_backend.repository_import_artifact import (  # noqa: E402
    write_repository_import_package,
)
from gateway_repository_contracts import UnknownTypePolicy  # noqa: E402
from gateway_repository_service.arrow_mapping import (  # noqa: E402
    TableCatalog,
    compile_table_plan,
)
from gateway_repository_service.candidate_a.dolt_cli import (  # noqa: E402
    CandidateADoltCli,
    write_query,
)
from gateway_repository_service.candidate_a.ref_validation import (  # noqa: E402
    opaque_commit_literal,
)
from gateway_repository_service.candidate_a.sql import (  # noqa: E402
    _parse_tagged_row,
    _tagged_select_list,
    quote_identifier,
)
from gateway_repository_service.enum_set_sql import (  # noqa: E402
    EnumSetSqlTypeKind,
    classify_enum_set_sql_type,
)
from gateway_repository_service.layout import DurableLayout  # noqa: E402
from gateway_repository_service.process import DoltRunner  # noqa: E402
from gateway_repository_service.providers import OfflineCliProvider  # noqa: E402
from gateway_repository_service.settings import RepositoryServiceSettings  # noqa: E402

FIXTURE_ORDER = ("small_cut", "small", "medium", "data2", "data1")
EXPECTED_SOURCE = {
    "small_cut": (1296079, "8fdbd3d207b81e933da9a4812b97239737541e574e7be4777dffa4f0c80ec059"),
    "small": (14956886, "7e858ce1eb9c070814b29e9799548695ee71537f812373a021c5ca9681dce027"),
    "medium": (49323598, "78bcb5ff4a37be4856120fee00e5d92f42d7c30dd7081d4c983e0641f96b682f"),
    "data2": (79446967, "b3089d8a734651eb6dd439f11951699d176b7c1b3794bb55142d4532e8d721e8"),
    "data1": (104957915, "22abb5f2f75c1a9645189e3e68ab95f6047914313059f673d609fe71457c3c35"),
}
DEFAULT_FIXTURE_ROOT = Path("/root/test-data")
_FORMAL_BLOCK_RE = re.compile(r"\nformal_repository_import:\n(?:  .*\n)*")


class StageFError(RuntimeError):
    """Stage F producer failed closed."""


@dataclass(frozen=True)
class FixtureResult:
    alias: str
    source_sql_bytes: int
    source_sql_sha256: str
    table_count: int
    nonempty_table_count: int
    enum_column_count: int
    set_column_count: int
    total_row_count: int
    replay_commit_id: str
    package_bytes: int
    package_sha256: str
    canonicalization_manifest_digest: str
    elapsed_seconds: float


def _git_head() -> str:
    repo = _VNEXT_ROOT.parent
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        text=True,
    ).strip()


def verify_source(alias: str, fixture_root: Path) -> tuple[Path, bytes, str]:
    sql_path = fixture_root / alias / "dbcfg.sql"
    payload = sql_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    payload.decode("utf-8")
    expected_bytes, expected_sha = EXPECTED_SOURCE[alias]
    if len(payload) != expected_bytes or digest != expected_sha:
        raise StageFError(
            f"{alias} source integrity mismatch: bytes={len(payload)} sha256={digest}"
        )
    return sql_path, payload, f"sha256:{digest}"


def _iter_table_rows(
    cli: CandidateADoltCli,
    commit_id: str,
    table: TableCatalog,
) -> Iterator[tuple[object, ...]]:
    plan = compile_table_plan(table, UnknownTypePolicy.REJECT)
    select_list, expected_header = _tagged_select_list(plan)
    order_clause = ""
    if table.primary_key:
        order_by = ", ".join(quote_identifier(name) for name in table.primary_key)
        order_clause = f" ORDER BY {order_by}"
    target_literal = opaque_commit_literal(commit_id)
    query = write_query(
        cli.query_directory,
        (
            f"SELECT {select_list} FROM {quote_identifier(table.name)} "
            f"AS OF {target_literal}{order_clause};\n"
        ),
    )
    stream = cli.runner.stream(
        "row_stream_ordered",
        ["sql", "--result-format=csv", "--binary-as-hex"],
        cwd=cli.repository,
        timeout=cli.settings.import_timeout_seconds,
        stdin_path=query,
    )
    stream_closed = False
    try:

        def decode_line(line: bytes) -> str:
            if len(line) > cli.settings.max_stream_line_bytes:
                raise StageFError(
                    f"tagged CSV encoded line exceeded safety bound for {table.name}"
                )
            return line.decode("utf-8")

        reader = csv.reader((decode_line(line) for line in stream), strict=True)
        header = next(reader, None)
        if header is None:
            result = stream.close()
            stream_closed = True
            if result.exit_code != 0 or result.timed_out or result.cancelled:
                raise StageFError(f"Dolt ordered row stream failed for {table.name}")
            return
        if header != expected_header:
            raise StageFError(f"tagged CSV header mismatch for {table.name}")
        for row in reader:
            parsed = _parse_tagged_row(row, plan)
            yield plan.normalize_row(parsed).values
        result = stream.close()
        stream_closed = True
        if result.exit_code != 0 or result.timed_out or result.cancelled:
            raise StageFError(f"Dolt ordered row stream failed for {table.name}")
    finally:
        if not stream_closed:
            stream.close()
        query.unlink(missing_ok=True)


def _count_enum_set(catalog: tuple[TableCatalog, ...]) -> tuple[int, int]:
    enum_count = 0
    set_count = 0
    for table in catalog:
        for column in table.columns:
            kind, parsed = classify_enum_set_sql_type(column.sql_type)
            if kind is EnumSetSqlTypeKind.MALFORMED:
                raise StageFError(
                    f"malformed ENUM/SET at {table.name}.{column.name}: {column.sql_type}"
                )
            if kind is EnumSetSqlTypeKind.VALID and parsed is not None:
                if parsed.kind == "ENUM":
                    enum_count += 1
                else:
                    set_count += 1
    return enum_count, set_count


def _upsert_dataset_yaml(
    path: Path,
    *,
    package_bytes: int,
    package_sha256: str,
    manifest_digest: str,
) -> None:
    block = (
        "formal_repository_import:\n"
        f"  media_type: {REPOSITORY_IMPORT_MEDIA_TYPE}\n"
        "  package_file: package.tar.zst\n"
        f"  package_bytes: {package_bytes}\n"
        f"  package_sha256: {package_sha256}\n"
        f"  canonicalization_manifest_digest: {manifest_digest}\n"
        "  canonicalization_manifest_file: canonicalization-manifest.json\n"
        "  package_version: 1\n"
        "  canonicalization_version: v1\n"
        "  production_validator_result: not_run\n"
    )
    text = path.read_text(encoding="utf-8")
    text = _FORMAL_BLOCK_RE.sub("\n", text).rstrip() + "\n\n" + block
    path.write_text(text, encoding="utf-8")


def generate_one(
    alias: str,
    *,
    fixture_root: Path,
    work_root: Path,
    log: TextIO,
) -> FixtureResult:
    started = time.monotonic()
    sql_path, replay_sql, source_digest = verify_source(alias, fixture_root)
    work = work_root / alias
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    data_root = work / "data-root"
    settings = RepositoryServiceSettings(
        profile="test",
        data_root=data_root,
        bearer_token="stage-f-producer",
        catalog_parallel_workers=4,
        metadata_timeout_seconds=180.0,
        import_timeout_seconds=4.0 * 60.0 * 60.0,
    )
    layout = DurableLayout.create_service(data_root)
    repo_path = layout.versioned / "repo"
    repo_path.mkdir()
    home = data_root / "dolt-home"
    tmpdir = data_root / "dolt-tmp"
    runner = DoltRunner(settings, layout.root, home=home, tmpdir=tmpdir)
    provider = OfflineCliProvider(settings, layout, repo_path, runner)
    cli = provider._candidate_cli
    try:
        log.write(f"{alias}: initializing Dolt repository\n")
        log.flush()
        provider.initialize_repository()
        log.write(f"{alias}: replaying {sql_path} ({len(replay_sql)} bytes)\n")
        log.flush()
        provider.replay(sql_path)
        commit_id = provider.commit_marker(f"p2-r6-ext-w1-stage-f-{alias}")
        log.write(f"{alias}: replay commit {commit_id}\n")
        log.flush()
        catalog = tuple(
            sorted(cli.catalog_at(commit_id), key=lambda table: table.name.encode("utf-8"))
        )
        enum_count, set_count = _count_enum_set(catalog)
        assembled_tables: list[AssembledTable] = []
        total_rows = 0
        nonempty = 0
        for index, table in enumerate(catalog, start=1):
            columns = tuple(
                ManifestColumn(column.name, column.sql_type, column.nullable)
                for column in table.columns
            )
            log.write(
                f"{alias}: table {index}/{len(catalog)} {table.name} "
                f"rows={table.row_count} cols={len(columns)} "
                f"pk={bool(table.primary_key)}\n"
            )
            log.flush()
            content = table_content_digest(
                columns,
                _iter_table_rows(cli, commit_id, table),
                expected_row_count=table.row_count,
                unordered=not table.primary_key,
            )
            assembled_tables.append(
                AssembledTable(
                    name=table.name,
                    columns=columns,
                    primary_key=table.primary_key,
                    row_count=table.row_count,
                    schema_digest=table_schema_digest(columns, table.primary_key),
                    content_digest=content,
                )
            )
            total_rows += table.row_count
            if table.row_count:
                nonempty += 1
        assembled = assemble_identity_canonicalization(
            source_artifact_digest=source_digest,
            tables=assembled_tables,
        )
        out_dir = fixture_root / alias
        package_path = out_dir / "package.tar.zst"
        manifest_path = out_dir / "canonicalization-manifest.json"
        written = write_repository_import_package(
            package_path,
            manifest=repository_import_manifest(assembled),
            replay_sql=replay_sql,
        )
        manifest_path.write_text(
            json.dumps(durable_canonicalization_manifest(assembled), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        _upsert_dataset_yaml(
            out_dir / "dataset.yaml",
            package_bytes=written.size_bytes,
            package_sha256=written.sha256,
            manifest_digest=assembled.digest,
        )
        elapsed = time.monotonic() - started
        log.write(
            f"{alias}: package {written.size_bytes} bytes {written.sha256} "
            f"digest={assembled.digest} elapsed={elapsed:.1f}s\n"
        )
        log.flush()
        return FixtureResult(
            alias=alias,
            source_sql_bytes=len(replay_sql),
            source_sql_sha256=source_digest,
            table_count=len(catalog),
            nonempty_table_count=nonempty,
            enum_column_count=enum_count,
            set_column_count=set_count,
            total_row_count=total_rows,
            replay_commit_id=commit_id,
            package_bytes=written.size_bytes,
            package_sha256=written.sha256,
            canonicalization_manifest_digest=assembled.digest,
            elapsed_seconds=elapsed,
        )
    finally:
        runner.terminate_active_children()
        shutil.rmtree(work, ignore_errors=True)


def _assert_cleanup(work_root: Path) -> None:
    if work_root.exists():
        leftovers = [path for path in work_root.rglob("*") if path.is_file()]
        if leftovers:
            raise StageFError(f"temporary files remain under {work_root}: {leftovers[:8]}")
        shutil.rmtree(work_root, ignore_errors=True)
    if work_root.exists():
        raise StageFError(f"work root {work_root} was not removed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate P2-R6-EXT-W1 Stage F packages")
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--work-root", type=Path, default=Path("/tmp/p2-r6-ext-w1-stage-f"))
    parser.add_argument("--only", choices=FIXTURE_ORDER, action="append")
    parser.add_argument("--repeat-small-cut", type=int, default=2)
    args = parser.parse_args(argv)
    aliases = tuple(args.only) if args.only else FIXTURE_ORDER
    work_root = args.work_root.resolve()
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)
    results: dict[str, FixtureResult] = {}
    try:
        if "small_cut" in aliases and args.repeat_small_cut >= 2:
            first = generate_one(
                "small_cut",
                fixture_root=args.fixture_root,
                work_root=work_root,
                log=sys.stderr,
            )
            second = generate_one(
                "small_cut",
                fixture_root=args.fixture_root,
                work_root=work_root,
                log=sys.stderr,
            )
            if (
                first.package_sha256 != second.package_sha256
                or first.canonicalization_manifest_digest != second.canonicalization_manifest_digest
            ):
                raise StageFError("small_cut package digest is not reproducible")
            results["small_cut"] = second
            remaining = [alias for alias in aliases if alias != "small_cut"]
        else:
            remaining = list(aliases)
        for alias in remaining:
            results[alias] = generate_one(
                alias,
                fixture_root=args.fixture_root,
                work_root=work_root,
                log=sys.stderr,
            )
    finally:
        _assert_cleanup(work_root)

    payload: dict[str, Any] = {
        "candidate_sha": _git_head(),
        "python_version": sys.version.split()[0],
        "dolt_version": "2.1.11",
        "package_version": 1,
        "canonicalization_version": "v1",
        "production_validator_result": "not_run",
        "fixtures": {
            alias: {
                "source_sql_bytes": result.source_sql_bytes,
                "source_sql_sha256": result.source_sql_sha256,
                "table_count": result.table_count,
                "nonempty_table_count": result.nonempty_table_count,
                "enum_column_count": result.enum_column_count,
                "set_column_count": result.set_column_count,
                "total_row_count": result.total_row_count,
                "replay_commit_id": result.replay_commit_id,
                "package_bytes": result.package_bytes,
                "package_sha256": result.package_sha256,
                "canonicalization_manifest_digest": result.canonicalization_manifest_digest,
                "elapsed_seconds": round(result.elapsed_seconds, 3),
            }
            for alias, result in results.items()
        },
    }
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"stage-f failed: {exc}", file=sys.stderr)
        raise
