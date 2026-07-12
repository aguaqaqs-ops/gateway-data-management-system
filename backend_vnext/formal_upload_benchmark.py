from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys
from time import perf_counter
import uuid

from .artifacts import ArtifactManifest, LocalArtifactStore, StoredArtifact


_BENCHMARK_LOGGER = logging.getLogger("backend_vnext.formal_upload_benchmark")
_BENCHMARK_ENV_VAR = "BACKEND_VNEXT_FORMAL_UPLOAD_BENCHMARK"


def formal_upload_benchmark_enabled() -> bool:
    return os.getenv(_BENCHMARK_ENV_VAR, "").strip().lower() in {"1", "true", "yes", "on"}


class _FormalUploadBenchmarkStreamHandler(logging.StreamHandler):
    """Marker handler so app startup can be safely called multiple times."""


def configure_formal_upload_benchmark_logging() -> None:
    if not formal_upload_benchmark_enabled():
        return
    logger = _BENCHMARK_LOGGER
    logger.setLevel(logging.INFO)
    logger.propagate = True
    if logging.getLogger().handlers or any(
        isinstance(handler, _FormalUploadBenchmarkStreamHandler) for handler in logger.handlers
    ):
        return
    handler = _FormalUploadBenchmarkStreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    logger.addHandler(handler)


def formal_upload_benchmark_run_id() -> str | None:
    if not formal_upload_benchmark_enabled():
        return None
    return f"formal-upload-benchmark:{uuid.uuid4().hex}"


def benchmark_elapsed_ms(started_at: float) -> int:
    return int(round((perf_counter() - started_at) * 1000))


def log_formal_upload_benchmark_event(
    event: str,
    *,
    benchmark_run_id: str | None = None,
    **fields: object,
) -> None:
    if not formal_upload_benchmark_enabled():
        return
    payload = {
        "event": event,
        **({"run_id": benchmark_run_id} if benchmark_run_id is not None else {}),
        **{key: value for key, value in fields.items() if value is not None},
    }
    _BENCHMARK_LOGGER.info(
        "formal_upload_benchmark %s",
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
    )


class BenchmarkingLocalArtifactStore(LocalArtifactStore):
    def __init__(
        self,
        root: Path,
        *,
        benchmark_run_id: str | None,
        event_prefix: str,
        workspace_id: str | None = None,
    ) -> None:
        super().__init__(root)
        self._benchmark_run_id = benchmark_run_id
        self._event_prefix = event_prefix
        self._workspace_id = workspace_id

    def put_bytes(self, manifest: ArtifactManifest, content: bytes) -> StoredArtifact:
        started_at = perf_counter()
        stored = super().put_bytes(manifest, content)
        log_formal_upload_benchmark_event(
            f"{self._event_prefix}.artifact_put",
            benchmark_run_id=self._benchmark_run_id,
            workspace_id=self._workspace_id,
            artifact_kind=manifest.artifact_kind,
            content_size_bytes=manifest.content_size_bytes,
            reused=stored.reused,
            duration_ms=benchmark_elapsed_ms(started_at),
        )
        return stored
