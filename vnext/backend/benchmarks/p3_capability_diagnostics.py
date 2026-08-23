"""Measurement-only Phase 3 concurrency and cancellation diagnostics.

This runner is intentionally outside the production package and ordinary CI.  It exercises only
the component/multi-pair layer: the public Arrow batch/provider seam with 1/2/4/8 independent
pairs and the public SQL parser cancellation seam.  Cross-capability artifact chains and
production/reference provider comparison are explicitly out of scope and deferred to later
phases with confirmed consumers.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any

import pyarrow as pa
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.capabilities.comparison import (
    ComparisonBatchRequest,
    PythonReferenceBatchProvider,
)
from gateway_backend.capabilities.snapshot_materialization import (
    InMemorySnapshotTableBatchReader,
    MaterializationStage,
    ROW_MATERIALIZATION_PROFILE,
    SCALAR_ENCODING_VERSION,
    SnapshotColumnDescriptor,
    SnapshotTableDescriptor,
)
from gateway_backend.capabilities.table_access.contracts import (
    PARSER_INPUT_CONTRACT_VERSION,
    ParseStatus,
    ParserDiagnosticCode,
    ParserInvocationContext,
    SqlParseRequest,
    SqlSourceInput,
)
from gateway_backend.capabilities.table_access.sql import parse_sql


@dataclass(frozen=True, slots=True)
class PairObservation:
    queue_wait_ms: float
    execution_ms: float
    row_count: int


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=100_000)
    parser.add_argument("--batch-rows", type=int, default=4_096)
    parser.add_argument("--pairs", default="1,2,4,8")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--cancel-statements", type=int, default=200_000)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def _positive(value: int, label: str) -> int:
    if value < 1:
        raise ValueError(f"{label} must be positive")
    return value


def _pair_counts(raw: str) -> tuple[int, ...]:
    values = tuple(_positive(int(item), "pair count") for item in raw.split(","))
    if not values or len(values) != len(set(values)):
        raise ValueError("pairs must contain unique positive integers")
    return values


def _descriptor(row_count: int) -> SnapshotTableDescriptor:
    return SnapshotTableDescriptor(
        table_name="benchmark_rows",
        display_table_name="benchmark_rows",
        columns=(
            SnapshotColumnDescriptor("id", "id", False, "SIGNED_INTEGER"),
            SnapshotColumnDescriptor("value", "value", False, "SIGNED_INTEGER"),
        ),
        primary_key_columns=("id",),
        compare_key_columns=("id",),
        row_count=row_count,
        materialization_stage=MaterializationStage.FINAL,
        compare_schema_digest=raw_blob_digest(b"p3-benchmark-schema-v1"),
        table_ruleset_version=1,
        row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
        scalar_encoding_version=SCALAR_ENCODING_VERSION,
        raw_content_digest=raw_blob_digest(f"p3-benchmark-rows:{row_count}".encode()),
    )


def _batches(row_count: int, batch_rows: int) -> tuple[pa.RecordBatch, ...]:
    batches: list[pa.RecordBatch] = []
    for start in range(0, row_count, batch_rows):
        stop = min(start + batch_rows, row_count)
        identifiers = pa.array(range(start, stop), type=pa.int64())
        values = pa.array((item * 17 for item in range(start, stop)), type=pa.int64())
        batches.append(pa.record_batch([identifiers, values], names=("id", "value")))
    return tuple(batches)


def _run_pair(
    submitted_at: float,
    descriptor: SnapshotTableDescriptor,
    batches: tuple[pa.RecordBatch, ...],
) -> PairObservation:
    started_at = time.perf_counter()
    reader = InMemorySnapshotTableBatchReader(descriptor, batches)
    result = PythonReferenceBatchProvider().execute(
        ComparisonBatchRequest(
            table_name=descriptor.table_name,
            descriptor=descriptor,
            reader=reader,
        )
    )
    row_count = sum(batch.num_rows for batch in result.output_stream)
    finished_at = time.perf_counter()
    if row_count != descriptor.row_count:
        raise RuntimeError("provider returned an unexpected row count")
    return PairObservation(
        queue_wait_ms=(started_at - submitted_at) * 1_000,
        execution_ms=(finished_at - started_at) * 1_000,
        row_count=row_count,
    )


def _summary(values: list[float]) -> dict[str, float]:
    return {
        "min": min(values),
        "mean": statistics.fmean(values),
        "max": max(values),
    }


def _measure_pairs(
    pair_count: int,
    repetitions: int,
    descriptor: SnapshotTableDescriptor,
    batches: tuple[pa.RecordBatch, ...],
) -> dict[str, Any]:
    # One untimed execution stabilizes imports, allocation paths and the provider seam.
    _run_pair(time.perf_counter(), descriptor, batches)
    samples: list[dict[str, Any]] = []
    for _ in range(repetitions):
        rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        cpu_before = time.process_time()
        wall_before = time.perf_counter()
        observations: list[PairObservation] = []
        with ThreadPoolExecutor(max_workers=pair_count) as executor:
            futures: list[Future[PairObservation]] = []
            for _pair_index in range(pair_count):
                submitted_at = time.perf_counter()
                futures.append(
                    executor.submit(_run_pair, submitted_at, descriptor, batches)
                )
            observations.extend(future.result() for future in futures)
        wall_seconds = time.perf_counter() - wall_before
        cpu_seconds = time.process_time() - cpu_before
        rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        samples.append(
            {
                "wall_seconds": wall_seconds,
                "cpu_seconds": cpu_seconds,
                "peak_rss_kib": rss_after,
                "peak_rss_delta_kib": max(0, rss_after - rss_before),
                "queue_wait_ms": _summary(
                    [observation.queue_wait_ms for observation in observations]
                ),
                "execution_ms": _summary(
                    [observation.execution_ms for observation in observations]
                ),
                "rows_processed": sum(observation.row_count for observation in observations),
            }
        )
    return {
        "pair_count": pair_count,
        "worker_count": pair_count,
        "samples": samples,
    }


def _cancellation_observation(statement_count: int) -> dict[str, Any]:
    cancel_requested = Event()
    started = Event()
    inserts = "".join(f"INSERT INTO t VALUES ({index});\n" for index in range(statement_count))
    sql = f"CREATE TABLE t (id BIGINT NOT NULL PRIMARY KEY);\n{inserts}".encode()
    digest = raw_blob_digest(sql)
    request = SqlParseRequest(
        source=SqlSourceInput(
            document_content_digest=digest,
            sql_source_digest=digest,
            parser_input_contract_version=PARSER_INPUT_CONTRACT_VERSION,
            encoding="utf-8",
            source_size_bytes=len(sql),
        ),
        sql_utf8=sql,
        context=ParserInvocationContext(cancel_requested),
    )

    def run() -> tuple[ParseStatus, tuple[ParserDiagnosticCode, ...]]:
        started.set()
        result = parse_sql(request)
        return result.status, tuple(item.code for item in result.diagnostics)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run)
        started.wait()
        time.sleep(0.001)
        cancel_started = time.perf_counter()
        cancel_requested.set()
        status, diagnostics = future.result()
        latency_ms = (time.perf_counter() - cancel_started) * 1_000
    cancelled = (
        status is ParseStatus.FAILED and ParserDiagnosticCode.PARSER_CANCELLED in diagnostics
    )
    if not cancelled:
        raise RuntimeError("cancellation workload completed without observing cancellation")
    return {
        "statement_count": statement_count,
        "source_bytes": len(sql),
        "latency_ms": latency_ms,
        "status": status.value,
        "diagnostic": ParserDiagnosticCode.PARSER_CANCELLED.value,
    }


def _revision() -> str:
    completed = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _measurement_record(
    *,
    revision: str,
    rows: int,
    batch_rows: int,
    pairs: tuple[int, ...],
    repetitions: int,
    cancellation_statements: int,
) -> dict[str, Any]:
    return {
        "question": (
            "Does the public comparison batch provider seam scale under independent in-memory "
            "pairs, and does the SQL parser observe cooperative cancellation?"
        ),
        "capacity_target": "not_applicable",
        "dataset_id": "synthetic-arrow-int64-pairs/v1",
        "dataset_revision": revision,
        "component_versions": {
            "python": sys.version.split()[0],
            "gateway_backend_revision": revision,
            "comparison_provider": "python-reference-batch-v1",
            "parser_contract": PARSER_INPUT_CONTRACT_VERSION,
        },
        "deployment_topology": (
            "local developer host; in-process component diagnostic; no Repository Service or "
            "artifact-store staging path"
        ),
        "resource_limits": "host default; no explicit CPU/memory cgroup",
        "workload": (
            f"synthetic Arrow int64 pairs at {rows} rows/pair, {batch_rows} rows/batch, "
            f"pair counts {','.join(str(item) for item in pairs)}, {repetitions} repetitions; "
            f"plus {cancellation_statements} SQL statements for cancellation latency"
        ),
        "warm_cold_setup": (
            "immutable Arrow batches built once; one untimed warm-up per pair count; setup "
            "excluded from measured samples"
        ),
        "summary_method": (
            "per sample: min/mean/max over pair observations for queue wait and execution; "
            "wall/cpu/rss from enclosing repetition"
        ),
        "correctness_result": (
            "pass; provider row counts match descriptor; cancellation returned "
            "FAILED/PARSER_CANCELLED"
        ),
    }


def _applicability_scope() -> dict[str, Any]:
    return {
        "layer": "component_multi_pair",
        "cross_capability": {
            "status": "deferred",
            "owner_phase": "P5/P6/P7",
            "reason": (
                "no confirmed P5 end-to-end consumer, capacity target, or production comparison "
                "provider candidate at P3 exit"
            ),
        },
        "provider_comparison": {
            "status": "deferred",
            "owner_phase": "P6/P7",
            "reason": (
                "only PythonReferenceBatchProvider exists; no production provider selection gate "
                "or differential baseline is authorized in P3"
            ),
        },
        "staging_high_water": {
            "status": "not_applicable",
            "reason": (
                "runner uses pre-built in-memory Arrow batches; artifact-store staging is not "
                "exercised"
            ),
        },
    }


def main() -> int:
    args = _arguments()
    rows = _positive(args.rows, "rows")
    batch_rows = _positive(args.batch_rows, "batch_rows")
    repetitions = _positive(args.repetitions, "repetitions")
    cancellation_statements = _positive(args.cancel_statements, "cancel_statements")
    pairs = _pair_counts(args.pairs)
    descriptor = _descriptor(rows)
    batches = _batches(rows, batch_rows)
    batch_bytes = sum(batch.nbytes for batch in batches)
    revision = _revision()
    result = {
        "schema_version": "gateway-vnext/p3-capability-diagnostics/v2",
        "measurement_only": True,
        "revision": revision,
        "measurement_record": _measurement_record(
            revision=revision,
            rows=rows,
            batch_rows=batch_rows,
            pairs=pairs,
            repetitions=repetitions,
            cancellation_statements=cancellation_statements,
        ),
        "applicability_scope": _applicability_scope(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
        },
        "dataset": {
            "id": "synthetic-arrow-int64-pairs/v1",
            "rows_per_pair": rows,
            "batch_rows": batch_rows,
            "batch_count": len(batches),
            "bytes_per_pair": batch_bytes,
        },
        "provider": "python-reference-batch-v1",
        "setup": "immutable Arrow batches built once; one warm-up per pair count; setup excluded",
        "pair_runs": [
            _measure_pairs(pair_count, repetitions, descriptor, batches)
            for pair_count in pairs
        ],
        "cancellation": _cancellation_observation(cancellation_statements),
        "limitations": [
            "component/multi-pair diagnostic only; not cross-capability or end-to-end P5 workload",
            "in-memory Arrow boundary does not exercise artifact-store or Repository I/O",
            "Python reference provider result does not select a production provider",
            "ru_maxrss is the process lifetime high-water mark reported by Linux",
            "staging high-water is not applicable because no staging path is exercised",
        ],
    }
    document = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.write_text(document, encoding="utf-8")
    sys.stdout.write(document)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
