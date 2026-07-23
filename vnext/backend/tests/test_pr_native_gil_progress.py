"""WP4 R4 PR-NATIVE wheel-path GIL progress probe."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable

import pyarrow as pa
import pytest

from gateway_backend.compute import canonical_row_hashes_v1

pytestmark = pytest.mark.pr_native

MIN_PROGRESS_TICKS = 1_000
_ROW_COUNT = 4_096


def _request_jcs(fields: list[dict[str, object]]) -> bytes:
    payload = {
        "request_schema_version": 1,
        "contract_binding": {
            "contract_id": "gateway-vnext.canonical-row-hash-compute-boundary",
            "semantic_version": "1.0.0",
        },
        "canonical_encoding_version": 1,
        "arrow_mapping_schema_version": 1,
        "declared_table_schema": {"fields": fields},
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()


def _large_multi_batch_reader(row_count: int) -> pa.RecordBatchReader:
    schema = pa.schema([pa.field("v", pa.int32(), nullable=False)])
    batches: list[pa.RecordBatch] = []
    remaining = row_count
    value = 0
    while remaining > 0:
        chunk = min(256, remaining)
        batches.append(
            pa.record_batch(
                [pa.array(list(range(value, value + chunk)), type=pa.int32())],
                schema=schema,
            )
        )
        value += chunk
        remaining -= chunk
    return pa.RecordBatchReader.from_batches(schema, batches)


def _measure_compute_window_progress(compute: Callable[[], None]) -> int:
    """Count worker ticks only during the compute callable window."""

    barrier = threading.Barrier(2)
    counter = {"ticks": 0}
    stop = threading.Event()
    baseline = {"ticks": 0}

    def bump() -> None:
        barrier.wait()
        while not stop.is_set():
            counter["ticks"] += 1

    worker = threading.Thread(target=bump, daemon=True)
    worker.start()
    try:
        barrier.wait()
        baseline["ticks"] = counter["ticks"]
        compute()
    finally:
        stop.set()
        worker.join(timeout=2.0)

    return counter["ticks"] - baseline["ticks"]


def test_wheel_path_python_thread_progresses_during_compute() -> None:
    if os.environ.get("GATE_PR_NATIVE") != "1":
        pytest.skip("wheel GIL probe runs under gate.sh native only")

    fields = [
        {"name": "v", "nullable": False, "semantic_type": {"kind": "signed-integer", "bits": 32}}
    ]
    request_jcs = _request_jcs(fields)
    reader = _large_multi_batch_reader(_ROW_COUNT)

    def run_native_compute() -> None:
        _output, result_jcs = canonical_row_hashes_v1(request_jcs, reader)
        assert b'"row_count":"4096"' in result_jcs

    delta_ticks = _measure_compute_window_progress(run_native_compute)
    assert delta_ticks >= MIN_PROGRESS_TICKS, {"delta_ticks": delta_ticks}


def test_gil_probe_rejects_instant_fake_compute(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.environ.get("GATE_PR_NATIVE") != "1":
        pytest.skip("wheel GIL probe runs under gate.sh native only")

    fields = [
        {"name": "v", "nullable": False, "semantic_type": {"kind": "signed-integer", "bits": 32}}
    ]
    request_jcs = _request_jcs(fields)
    reader = _large_multi_batch_reader(_ROW_COUNT)
    output_schema = pa.schema([pa.field("row_hash", pa.binary(32), nullable=False)])
    fake_result_jcs = b'"row_count":"4096"'

    def instant_fake_compute(
        _request_jcs: bytes,
        _reader: pa.RecordBatchReader,
    ) -> tuple[pa.RecordBatchReader, bytes]:
        return pa.RecordBatchReader.from_batches(output_schema, []), fake_result_jcs

    monkeypatch.setattr(
        "test_pr_native_gil_progress.canonical_row_hashes_v1",
        instant_fake_compute,
    )

    def run_fake_compute() -> None:
        _output, result_jcs = canonical_row_hashes_v1(request_jcs, reader)
        assert result_jcs == fake_result_jcs

    delta_ticks = _measure_compute_window_progress(run_fake_compute)
    assert delta_ticks < MIN_PROGRESS_TICKS, {"delta_ticks": delta_ticks}
