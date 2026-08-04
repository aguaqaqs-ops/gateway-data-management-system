"""Exec'd child entry point for one isolated P2-R1 workflow sample."""

from __future__ import annotations

import os
import pickle
import sys
from pathlib import Path
from uuid import uuid4

from gateway_repository_service.workflow import (
    _run_offline_discard_in_process,
    _run_workflow_in_process,
)


def main() -> None:
    payload_path = Path(sys.argv[1])
    result_path = Path(sys.argv[2])
    with payload_path.open("rb") as handle:
        payload = pickle.load(handle)
    operation = payload.pop("worker_operation", "workflow")
    if operation == "discard":
        discard_payload = {
            key: payload[key]
            for key in ("settings", "fixture", "sample_kind", "root_parent")
        }
        measurement: object = _run_offline_discard_in_process(**discard_payload)
    elif operation == "workflow":
        measurement = _run_workflow_in_process(**payload)
    else:
        raise ValueError(f"unknown worker operation: {operation}")
    temporary = result_path.with_name(f".{result_path.name}.{uuid4().hex}.tmp")
    with temporary.open("wb") as handle:
        pickle.dump(measurement, handle, protocol=pickle.HIGHEST_PROTOCOL)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, result_path)
    directory_fd = os.open(result_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


if __name__ == "__main__":
    main()
