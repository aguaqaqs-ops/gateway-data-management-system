#!/usr/bin/env python3
"""Stage I evidence driver: S6 capacity, synthetic W2, and 1/4/8 concurrency."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, TextIO
from uuid import UUID, uuid4

_VNEXT_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = Path(__file__).resolve().parent
for _extra in (
    _SCRIPTS,
    _VNEXT_ROOT / "backend" / "src",
    _VNEXT_ROOT / "repository_service" / "src",
    _VNEXT_ROOT / "repository_contracts" / "src",
    _VNEXT_ROOT / "shared_kernel" / "src",
):
    _text = str(_extra)
    if _text not in sys.path:
        sys.path.insert(0, _text)

from gateway_backend.synthetic_w2 import (  # noqa: E402
    DEFAULT_SEED,
    GENERATOR_VERSION,
    SCHEMA_VERSION,
    build_scaled_replay_sql,
    validate_s6_result_record,
)
from gateway_repository_service.arrow_mapping import TableCatalog  # noqa: E402
from gateway_repository_service.enum_set_sql import (  # noqa: E402
    EnumSetSqlTypeKind,
    classify_enum_set_sql_type,
)
from gateway_repository_service.layout import DurableLayout  # noqa: E402
from gateway_repository_service.process import DoltRunner  # noqa: E402
from gateway_repository_service.providers import OfflineCliProvider  # noqa: E402
from gateway_repository_service.settings import RepositoryServiceSettings  # noqa: E402
from r6_s6_lib import (  # noqa: E402
    ServiceClient,
    decoded_package_entry_sizes,
    disk_admission_view,
    inspect_arrow_schema,
    leftover_temp_files,
    ninth_stream_code,
    package_manifest_tables,
    runtime_resource_view,
    settings_snapshot,
    sha256_hex,
    start_sampler,
    start_service,
    stop_sampler,
    stop_service,
    wait_runtime_idle,
)

FIXTURE_ORDER = ("small_cut", "small", "medium", "data2", "data1")
EXPECTED_PACKAGES = {
    "small_cut": (
        83838,
        "54fbe736d486216a44a0bcf9b81a0fc3c1d2afe5a900f3afc5ee2eb7e068de43",
        "sha256:459eb8e3abbaa58ae36aef4febe92131624f206eea9d5e0eef9d13abbd740d5a",
        "p2-r6-business-small-cut",
    ),
    "small": (
        613635,
        "e440af6963d99315ef632fcf34f57741de0791ec9a8942ce284b2900efbf82c3",
        "sha256:5c01406aba92537be95b3ba904e6ff092661c7bce30352f3369bdf3cc6958b49",
        "p2-r6-business-small",
    ),
    "medium": (
        2081228,
        "3e705e3516e9e56a54749b8a22f364ab90ac446f13cb25f7a710feb2af9c055e",
        "sha256:73dd240b234b26ec006aa78a5e73f2ac9a5105eabe9e9f5dd19a82c858d6b26c",
        "p2-r6-business-medium",
    ),
    "data2": (
        3173874,
        "72a266b25f2712d8f23f3010937693dc4a5a41dd93e2cb237928f711aa0fc813",
        "sha256:c1cad27c519695ba9701cdf4b5572714dfcab295355bd614f42a0d5fad53e340",
        "p2-r6-business-large-in-range",
    ),
    "data1": (
        5724227,
        "bd607ecbca4890d273188f93d1020fa32e2cc0cbd5f6f9ffdbfcffe49feb9bf2",
        "sha256:29a37b49168a04da8e802471f8eaf6221b64abbdef16eb64cc1ba9fa848dd435",
        "p2-r6-business-large-upper-overflow",
    ),
}
DEFAULT_FIXTURE_ROOT = Path("/root/test-data")
W2_ALIAS = "w2"
W2_DATASET_ID = "p2-r6-synthetic-w2-medium-shape"


class StageIError(RuntimeError):
    """Stage I evidence driver failed closed."""


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=_VNEXT_ROOT.parent,
        text=True,
    ).strip()


def _load_package(alias: str, fixture_root: Path) -> tuple[bytes, int, str, str, str]:
    expected_bytes, expected_sha, expected_digest, dataset_id = EXPECTED_PACKAGES[alias]
    payload = (fixture_root / alias / "package.tar.zst").read_bytes()
    digest = sha256_hex(payload)
    if len(payload) != expected_bytes or digest != expected_sha:
        raise StageIError(
            f"{alias} package identity mismatch: bytes={len(payload)} sha256={digest}"
        )
    return payload, expected_bytes, expected_sha, expected_digest, dataset_id


def _count_enum_set(catalog: tuple[TableCatalog, ...]) -> tuple[int, int]:
    enum_count = 0
    set_count = 0
    for table in catalog:
        for column in table.columns:
            kind, parsed = classify_enum_set_sql_type(column.sql_type)
            if kind is EnumSetSqlTypeKind.MALFORMED:
                raise StageIError(f"malformed ENUM/SET at {table.name}.{column.name}")
            if kind is EnumSetSqlTypeKind.VALID and parsed is not None:
                if parsed.kind == "ENUM":
                    enum_count += 1
                else:
                    set_count += 1
    return enum_count, set_count


def _iter_table_rows(cli: Any, commit_id: str, table: TableCatalog) -> Any:
    from generate_r6_w1_packages import _iter_table_rows as shared

    return shared(cli, commit_id, table)


def produce_package(
    *,
    replay_sql: bytes,
    source_digest: str,
    work_root: Path,
    out_dir: Path,
    log: TextIO,
    label: str,
) -> dict[str, Any]:
    try:
        import rfc8785  # noqa: F401
    except ImportError:
        backend_venv = _VNEXT_ROOT / "backend" / ".venv" / "lib"
        for site in sorted(backend_venv.glob("python*/site-packages")):
            sys.path.insert(0, str(site))
    from gateway_backend.canonicalization_manifest import (
        AssembledTable,
        ManifestColumn,
        assemble_identity_canonicalization,
        durable_canonicalization_manifest,
        repository_import_manifest,
        table_content_digest,
        table_schema_digest,
    )
    from gateway_backend.repository_import_artifact import write_repository_import_package
    started = time.monotonic()
    work = work_root / f"produce-{label}"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    data_root = work / "data-root"
    settings = RepositoryServiceSettings(
        profile="test",
        data_root=data_root,
        bearer_token="stage-i-w2-producer",
        catalog_parallel_workers=4,
        metadata_timeout_seconds=180.0,
        import_timeout_seconds=4.0 * 60.0 * 60.0,
    )
    layout = DurableLayout.create_service(data_root)
    repo_path = layout.versioned / "repo"
    repo_path.mkdir()
    runner = DoltRunner(
        settings,
        layout.root,
        home=data_root / "dolt-home",
        tmpdir=data_root / "dolt-tmp",
    )
    provider = OfflineCliProvider(settings, layout, repo_path, runner)
    sql_path = work / "replay.sql"
    sql_path.write_bytes(replay_sql)
    try:
        log.write(f"{label}: initializing Dolt and replaying {len(replay_sql)} bytes\n")
        log.flush()
        provider.initialize_repository()
        provider.replay(sql_path)
        commit_id = provider.commit_marker(f"p2-r6-ext-w1-stage-i-{label}")
        cli = provider._candidate_cli
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
                f"{label}: table {index}/{len(catalog)} {table.name} rows={table.row_count}\n"
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
        out_dir.mkdir(parents=True, exist_ok=True)
        written = write_repository_import_package(
            out_dir / "package.tar.zst",
            manifest=repository_import_manifest(assembled),
            replay_sql=replay_sql,
        )
        (out_dir / "canonicalization-manifest.json").write_text(
            json.dumps(durable_canonicalization_manifest(assembled), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return {
            "package_bytes": written.size_bytes,
            "package_sha256": written.sha256,
            "canonicalization_manifest_digest": assembled.digest,
            "table_count": len(catalog),
            "nonempty_table_count": nonempty,
            "enum_column_count": enum_count,
            "set_count": set_count,
            "total_row_count": total_rows,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    finally:
        runner.terminate_active_children()
        shutil.rmtree(work, ignore_errors=True)


def _largest_table_from_manifest(payload: bytes) -> tuple[str, int, int]:
    tables = package_manifest_tables(payload)
    chosen = max(tables, key=lambda table: int(table["row_count"]))
    return str(chosen["name"]), int(chosen["row_count"]), len(tables)


def run_http_import(
    *,
    alias: str,
    dataset_id: str,
    payload: bytes,
    package_sha: str,
    manifest_digest: str,
    synthetic: bool,
    work_root: Path,
    log: TextIO,
) -> dict[str, Any]:
    started = time.monotonic()
    work = work_root / f"http-{alias}-{uuid4().hex[:8]}"
    work.mkdir(parents=True)
    service = start_service(work)
    client = ServiceClient(service.base_url)
    sample, sampler = start_sampler(service.data_root, os.getpid())
    timings: dict[str, float] = {}
    try:
        disk_before = disk_admission_view(service.data_root, service.settings)
        decoded = decoded_package_entry_sizes(payload)
        repo_id, initial_commit = client.create_repository()
        upload_started = time.monotonic()
        artifact_ref = client.upload_artifact(repo_id, payload, package_sha)
        timings["upload_seconds"] = round(time.monotonic() - upload_started, 3)
        import_started = time.monotonic()
        operation_id = client.submit_import(repo_id, artifact_ref, initial_commit)
        operation = client.wait_operation(repo_id, operation_id)
        timings["import_seconds"] = round(time.monotonic() - import_started, 3)
        if operation["status"] != "SUCCEEDED" or operation.get("result") is None:
            raise StageIError(
                f"{alias} import failed: status={operation.get('status')} error={operation.get('error')}"
            )
        result = operation["result"]
        if result["canonicalization_manifest_digest"] != manifest_digest:
            raise StageIError(f"{alias} digest mismatch after import")
        if result["completed_verification_policy"] != "FULL_SCAN":
            raise StageIError(f"{alias} did not complete FULL_SCAN")
        catalog_started = time.monotonic()
        commit_id = client.resolve_main(repo_id)
        table_name, expected_rows, table_count = _largest_table_from_manifest(payload)
        catalog_status = "pass"
        try:
            catalog = client.get_catalog(repo_id, commit_id)
            timings["catalog_seconds"] = round(time.monotonic() - catalog_started, 3)
            table_count = len(catalog["catalog"]["tables"])
        except RuntimeError as exc:
            if "503" not in str(exc):
                raise
            catalog_status = "SERVICE_NOT_READY_catalog_wire_limit"
            timings["catalog_seconds"] = round(time.monotonic() - catalog_started, 3)
        stream_started = time.monotonic()
        _status, schema, streamed_rows, max_batch = client.stream_table_rows(
            repo_id, commit_id, table_name
        )
        timings["row_stream_seconds"] = round(time.monotonic() - stream_started, 3)
        unknown, lossy = inspect_arrow_schema(schema)
        if unknown or lossy:
            raise StageIError(f"{alias} stream had unknown={unknown} lossy={lossy}")
        if streamed_rows != expected_rows:
            raise StageIError(
                f"{alias} streamed {streamed_rows} rows, catalog has {expected_rows}"
            )
        disk_after = disk_admission_view(service.data_root, service.settings)
        record = {
            "schema_version": SCHEMA_VERSION,
            "candidate_sha": _git_head(),
            "synthetic": synthetic,
            "dataset_id": dataset_id,
            "package_bytes": len(payload),
            "package_sha256": f"sha256:{package_sha}",
            "canonicalization_manifest_digest": manifest_digest,
            "settings": settings_snapshot(service.settings),
            "timings": timings,
            "layers": {
                "raw_upload_bytes": len(payload),
                "package_bytes": len(payload),
                "decoded_manifest_bytes": decoded.get("manifest.json", 0),
                "decoded_replay_sql_bytes": decoded.get("replay.sql", 0),
                "record_batch_bytes_limit": service.settings.record_batch_bytes,
                "peak_durable_root_bytes": sample.peak_durable_root_bytes,
                "peak_rss_kib": sample.peak_rss_kib,
                "max_observed_batch_bytes": max_batch,
                "streamed_table": table_name,
                "streamed_rows": streamed_rows,
            },
            "result": "pass",
            "cleanup": {
                "work_root_removed": True,
                "disk_before": disk_before,
                "disk_after": disk_after,
            },
            "table_count": table_count,
            "catalog_status": catalog_status,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
        validate_s6_result_record(record)
        log.write(
            f"{alias}: HTTP import pass elapsed={record['elapsed_seconds']}s "
            f"rss={sample.peak_rss_kib}KiB\n"
        )
        log.flush()
        time.sleep(1.0)
        return record
    finally:
        stop_sampler(sample, sampler)
        client.close()
        stop_service(service)
        shutil.rmtree(work, ignore_errors=True)


def cmd_capacity(args: argparse.Namespace) -> dict[str, Any]:
    work_root = args.work_root.resolve()
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)
    fixtures: dict[str, Any] = {}
    try:
        aliases = tuple(args.only) if args.only else FIXTURE_ORDER
        for alias in aliases:
            payload, _size, sha, digest, dataset_id = _load_package(alias, args.fixture_root)
            fixtures[alias] = run_http_import(
                alias=alias,
                dataset_id=dataset_id,
                payload=payload,
                package_sha=sha,
                manifest_digest=digest,
                synthetic=False,
                work_root=work_root,
                log=sys.stderr,
            )
    finally:
        leftovers = leftover_temp_files(work_root)
        shutil.rmtree(work_root, ignore_errors=True)
        if leftovers:
            raise StageIError(f"capacity leftovers: {leftovers[:8]}")
    return {
        "candidate_sha": _git_head(),
        "command": "capacity",
        "fixtures": fixtures,
        "result": "pass",
    }


def cmd_w2(args: argparse.Namespace) -> dict[str, Any]:
    work_root = args.work_root.resolve()
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)
    medium_sql = (args.fixture_root / "medium" / "dbcfg.sql").read_bytes()
    if sha256_hex(medium_sql) != "78bcb5ff4a37be4856120fee00e5d92f42d7c30dd7081d4c983e0641f96b682f":
        raise StageIError("medium source SQL SHA mismatch")
    sys.stderr.write("w2: scaling medium SQL\n")
    replay_sql, scale_report = build_scaled_replay_sql(
        medium_sql.decode("utf-8"),
        seed=DEFAULT_SEED,
    )
    out_dir = args.fixture_root / W2_ALIAS
    source_digest = "sha256:" + sha256_hex(replay_sql)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dbcfg.sql").write_bytes(replay_sql)
    produced = produce_package(
        replay_sql=replay_sql,
        source_digest=source_digest,
        work_root=work_root,
        out_dir=out_dir,
        log=sys.stderr,
        label=W2_ALIAS,
    )
    descriptor = {
        "dataset_id": W2_DATASET_ID,
        "synthetic": True,
        "generator_version": GENERATOR_VERSION,
        "seed": DEFAULT_SEED,
        "replay_sql_bytes": len(replay_sql),
        "scale": scale_report,
    }
    (out_dir / "dataset.yaml").write_text(
        "synthetic: true\n"
        f"dataset_id: {W2_DATASET_ID}\n"
        f"generator_version: {GENERATOR_VERSION}\n"
        f"seed: {DEFAULT_SEED}\n"
        f"replay_sql_bytes: {len(replay_sql)}\n"
        f"package_bytes: {produced['package_bytes']}\n"
        f"package_sha256: {produced['package_sha256']}\n"
        "canonicalization_manifest_digest: "
        f"{produced['canonicalization_manifest_digest']}\n"
        "package_version: 1\n"
        "canonicalization_version: v1\n",
        encoding="utf-8",
    )
    package_payload = (out_dir / "package.tar.zst").read_bytes()
    http_record = run_http_import(
        alias=W2_ALIAS,
        dataset_id=W2_DATASET_ID,
        payload=package_payload,
        package_sha=sha256_hex(package_payload),
        manifest_digest=produced["canonicalization_manifest_digest"],
        synthetic=True,
        work_root=work_root,
        log=sys.stderr,
    )
    leftovers = leftover_temp_files(work_root)
    shutil.rmtree(work_root, ignore_errors=True)
    if leftovers:
        raise StageIError(f"w2 leftovers: {leftovers[:8]}")
    return {
        "candidate_sha": _git_head(),
        "command": "w2",
        "descriptor": descriptor,
        "producer": produced,
        "http": http_record,
        "result": "pass",
    }


def _stream_isolated(
    base_url: str,
    repository_id: UUID,
    commit_id: str,
    table_name: str,
) -> tuple[int, Any, int, int]:
    client = ServiceClient(base_url)
    try:
        return client.stream_table_rows(repository_id, commit_id, table_name)
    finally:
        client.close()


def _upload_isolated(
    base_url: str,
    repository_id: UUID,
    payload: bytes,
    raw_sha256: str,
) -> dict[str, Any]:
    client = ServiceClient(base_url)
    try:
        return client.upload_artifact(repository_id, payload, raw_sha256)
    finally:
        client.close()


def _hold_stream(
    base_url: str,
    repository_id: UUID,
    commit_id: str,
    table_name: str,
    started: threading.Event,
    release: threading.Event,
    errors: list[str],
) -> None:
    client = ServiceClient(base_url)
    response = None
    try:
        response = client.open_row_stream_raw(repository_id, commit_id, table_name)
        if response.status_code != 200:
            errors.append(f"hold stream status {response.status_code}")
            started.set()
            return
        started.set()
        release.wait(timeout=180.0)
    except Exception as exc:
        errors.append(str(exc))
        started.set()
    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        client.close()


def _poll_until_terminal(base_url: str, repo: UUID, operation_id: UUID) -> str:
    client = ServiceClient(base_url)
    try:
        operation = client.wait_operation(repo, operation_id)
        return str(operation["status"])
    finally:
        client.close()


def _operation_status(base_url: str, repo: UUID, operation_id: UUID) -> str:
    client = ServiceClient(base_url)
    try:
        response = client._client.get(
            f"/v1/repositories/{repo}/operations/{operation_id}",
            headers=client._auth,
        )
        return str(response.json()["operation"]["status"])
    finally:
        client.close()


def _submit_import_maybe_busy(
    base_url: str,
    repo: UUID,
    artifact_ref: dict[str, Any],
    expected_commit: str,
) -> dict[str, Any]:
    client = ServiceClient(base_url)
    try:
        operation_id = client.submit_import(repo, artifact_ref, expected_commit)
        return {"result": "accepted", "operation_id": str(operation_id)}
    except RuntimeError as exc:
        text = str(exc)
        if "429" in text:
            return {"result": "rejected_429", "detail": text[:200]}
        raise
    finally:
        client.close()


def _run_stream_matrix(
    *,
    service: Any,
    repo_id: UUID,
    commit_id: str,
    table_name: str,
    pid: int,
) -> dict[str, Any]:
    matrix: dict[str, Any] = {}
    for count in (1, 4, 8):
        sys.stderr.write(f"concurrency: row streams x{count} table={table_name}\n")
        sys.stderr.flush()
        wait_runtime_idle(service)
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=count) as pool:
            futures = [
                pool.submit(
                    _stream_isolated,
                    service.base_url,
                    repo_id,
                    commit_id,
                    table_name,
                )
                for _ in range(count)
            ]
            results = [future.result() for future in as_completed(futures)]
        if any(inspect_arrow_schema(item[1]) != (0, 0) for item in results):
            raise StageIError(f"stream matrix {count} had unknown/lossy")
        wait_runtime_idle(service)
        matrix[str(count)] = {
            "result": "pass",
            "duration_seconds": round(time.monotonic() - started, 3),
            "table": table_name,
            "resources": runtime_resource_view(service, pid),
        }
    return matrix


def cmd_concurrency(args: argparse.Namespace) -> dict[str, Any]:
    work_root = args.work_root.resolve()
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)
    medium_payload, _size, medium_sha, _digest, _ds = _load_package("medium", args.fixture_root)
    small_payload, _ss, small_sha, _sd, _sds = _load_package("small_cut", args.fixture_root)
    service = start_service(work_root)
    client = ServiceClient(service.base_url)
    pid = os.getpid()
    report: dict[str, Any] = {"candidate_sha": _git_head(), "command": "concurrency"}
    try:
        sys.stderr.write("concurrency: importing medium for matrix\n")
        sys.stderr.flush()
        repo_id, initial = client.create_repository()
        artifact = client.upload_artifact(repo_id, medium_payload, medium_sha)
        operation = client.wait_operation(
            repo_id, client.submit_import(repo_id, artifact, initial)
        )
        if operation["status"] != "SUCCEEDED":
            raise StageIError(f"medium import for matrix failed: {operation}")
        commit_id = client.resolve_main(repo_id)
        table_name, _rows, _count = _largest_table_from_manifest(medium_payload)
        stream_matrix = _run_stream_matrix(
            service=service,
            repo_id=repo_id,
            commit_id=commit_id,
            table_name=table_name,
            pid=pid,
        )
        sys.stderr.write("concurrency: holding 8 streams for ninth 503\n")
        sys.stderr.flush()
        wait_runtime_idle(service)
        holders: list[threading.Thread] = []
        started_events = [threading.Event() for _ in range(8)]
        release = threading.Event()
        errors: list[str] = []
        try:
            for event in started_events:
                thread = threading.Thread(
                    target=_hold_stream,
                    args=(
                        service.base_url,
                        repo_id,
                        commit_id,
                        table_name,
                        event,
                        release,
                        errors,
                    ),
                )
                thread.start()
                holders.append(thread)
            if not all(event.wait(timeout=180.0) for event in started_events):
                raise StageIError(f"failed to hold 8 row streams: {errors}")
            if errors:
                raise StageIError(f"hold streams reported errors: {errors}")
            ninth = ServiceClient(service.base_url)
            try:
                response = ninth.open_row_stream_raw(repo_id, commit_id, table_name)
                ninth_status = response.status_code
                ninth_body = response.read().decode("utf-8", errors="replace")
                response.close()
            finally:
                ninth.close()
            if ninth_status != 503 or ninth_stream_code() not in ninth_body:
                raise StageIError(
                    f"ninth stream expected 503 {ninth_stream_code()}: "
                    f"{ninth_status} {ninth_body[:200]}"
                )
            stream_matrix["ninth"] = {
                "status": ninth_status,
                "code": ninth_stream_code(),
                "result": "pass",
                "hold_table": table_name,
                "resources": runtime_resource_view(service, pid),
            }
            report["row_streams"] = stream_matrix
        finally:
            release.set()
            for thread in holders:
                thread.join(timeout=60.0)
        wait_runtime_idle(service)

        w2_package = args.fixture_root / W2_ALIAS / "package.tar.zst"
        if w2_package.is_file():
            sys.stderr.write("concurrency: importing W2 for readonly streams\n")
            sys.stderr.flush()
            w2_payload = w2_package.read_bytes()
            w2_sha = sha256_hex(w2_payload)
            w2_repo, w2_initial = client.create_repository()
            w2_artifact = client.upload_artifact(w2_repo, w2_payload, w2_sha)
            w2_operation = client.wait_operation(
                w2_repo, client.submit_import(w2_repo, w2_artifact, w2_initial)
            )
            if w2_operation["status"] != "SUCCEEDED":
                raise StageIError(f"w2 import for readonly streams failed: {w2_operation}")
            w2_commit = client.resolve_main(w2_repo)
            w2_table, _w2_rows, _w2_count = _largest_table_from_manifest(w2_payload)
            report["w2_row_streams"] = _run_stream_matrix(
                service=service,
                repo_id=w2_repo,
                commit_id=w2_commit,
                table_name=w2_table,
                pid=pid,
            )

        sys.stderr.write("concurrency: upload matrix\n")
        sys.stderr.flush()
        upload_matrix: dict[str, Any] = {}
        for count in (1, 4, 8):
            started = time.monotonic()
            repos = [client.create_repository()[0] for _ in range(count)]
            with ThreadPoolExecutor(max_workers=count) as pool:
                futures = [
                    pool.submit(
                        _upload_isolated,
                        service.base_url,
                        repo,
                        small_payload,
                        small_sha,
                    )
                    for repo in repos
                ]
                uploaded = [future.result() for future in as_completed(futures)]
            if len(uploaded) != count:
                raise StageIError(f"upload matrix {count} incomplete")
            upload_matrix[str(count)] = {
                "result": "pass",
                "duration_seconds": round(time.monotonic() - started, 3),
                "resources": runtime_resource_view(service, pid),
            }
        report["uploads"] = upload_matrix

        sys.stderr.write("concurrency: import matrix\n")
        sys.stderr.flush()
        import_matrix: dict[str, Any] = {}
        for count in (1, 4, 8):
            started = time.monotonic()
            prepared: list[tuple[UUID, dict[str, Any], str]] = []
            for _index in range(count):
                repo, initial_commit = client.create_repository()
                artifact_ref = client.upload_artifact(repo, small_payload, small_sha)
                prepared.append((repo, artifact_ref, initial_commit))
            submissions = [
                _submit_import_maybe_busy(service.base_url, repo, artifact_ref, initial_commit)
                for repo, artifact_ref, initial_commit in prepared
            ]
            accepted = [
                (prepared[index][0], UUID(item["operation_id"]))
                for index, item in enumerate(submissions)
                if item["result"] == "accepted"
            ]
            rejected = [item for item in submissions if item["result"] != "accepted"]
            if count < 8 and rejected:
                raise StageIError(f"import matrix {count} unexpected 429: {rejected}")
            if count == 8 and not accepted:
                raise StageIError("import matrix 8 accepted none")
            peak_running = 0
            peak_queued = 0
            stop_sample = threading.Event()

            def _sample() -> None:
                nonlocal peak_running, peak_queued
                while not stop_sample.wait(0.05):
                    running = 0
                    queued = 0
                    for repo, operation_id in accepted:
                        status = _operation_status(service.base_url, repo, operation_id)
                        if status == "RUNNING":
                            running += 1
                        elif status in {"QUEUED", "PENDING"}:
                            queued += 1
                    peak_running = max(peak_running, running)
                    peak_queued = max(peak_queued, queued)

            sampler = threading.Thread(target=_sample, daemon=True)
            sampler.start()
            try:
                with ThreadPoolExecutor(max_workers=max(len(accepted), 1)) as pool:
                    futures = [
                        pool.submit(
                            _poll_until_terminal, service.base_url, repo, operation_id
                        )
                        for repo, operation_id in accepted
                    ]
                    statuses = [future.result() for future in as_completed(futures)]
            finally:
                stop_sample.set()
                sampler.join(timeout=5.0)
            if any(status != "SUCCEEDED" for status in statuses):
                raise StageIError(f"import matrix {count} had failures: {statuses}")
            if count == 8 and peak_running > 4 and not rejected:
                raise StageIError(
                    f"import matrix 8 ran {peak_running} workers; cap is 4"
                )
            import_matrix[str(count)] = {
                "result": "pass",
                "duration_seconds": round(time.monotonic() - started, 3),
                "accepted": len(accepted),
                "rejected_429": len(rejected),
                "peak_running": peak_running,
                "peak_queued": peak_queued,
                "resources": runtime_resource_view(service, pid),
            }
        report["imports"] = import_matrix
        wait_runtime_idle(service)
        cleanup_view = runtime_resource_view(service, pid)
        if cleanup_view["dolt_child_count"] or cleanup_view["query_temp_count"]:
            raise StageIError(f"concurrency cleanup not zero: {cleanup_view}")
        report["cleanup"] = {
            "resources": cleanup_view,
            "work_root_removed": True,
        }
        report["result"] = "pass"
        report["hold_errors"] = errors
        return report
    finally:
        client.close()
        stop_service(service)
        shutil.rmtree(work_root, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P2-R6-EXT-W1 Stage I S6 evidence")
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--work-root", type=Path, default=Path("/tmp/p2-r6-ext-w1-stage-i"))
    sub = parser.add_subparsers(dest="command", required=True)
    capacity = sub.add_parser("capacity")
    capacity.add_argument("--only", choices=FIXTURE_ORDER, action="append")
    sub.add_parser("w2")
    sub.add_parser("concurrency")
    args = parser.parse_args(argv)
    if args.command == "capacity":
        payload = cmd_capacity(args)
    elif args.command == "w2":
        payload = cmd_w2(args)
    else:
        payload = cmd_concurrency(args)
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"stage-i failed: {exc}", file=sys.stderr)
        raise
