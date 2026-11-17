"""Standalone test observer mounted read-only; only production dependencies.

The observer never supplies cache results: lookup/store delegate to the real
control-DB cache. Phase numbers are process-local diagnostics, correlated with
actual worker claim/HTTP operation IDs by the host supplement consumer.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from gateway_shared_kernel import DigestRef
from pydantic import BaseModel, ConfigDict, TypeAdapter

from gateway_backend.artifacts import ArtifactRef, artifact_ref_from_dict, artifact_ref_to_dict
from gateway_backend.artifacts.snapshot_table_export_cache import SnapshotTableArtifactCacheKey
from gateway_backend.capabilities.snapshot_materialization.client_parquet import _LAYOUT, _REPOSITORY
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.control_db.snapshot_export_cache import ControlDbSnapshotTableExportCache


class _Document(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Reference(_Document):
    artifact_id: str
    media_type: str
    size_bytes: int
    raw_sha256: str

    def to_ref(self) -> ArtifactRef:
        return artifact_ref_from_dict(self.model_dump())


def _check(condition: bool, label: str) -> None:
    if not condition:
        raise RuntimeError(label)


class Target(_Document):
    table_name: str
    repository_id: str
    row_layout_digest: str
    writer_version: int
    cache_ref: Reference
    row_count: int

    def key(self) -> SnapshotTableArtifactCacheKey:
        return SnapshotTableArtifactCacheKey(DigestRef(self.row_layout_digest), self.repository_id, self.writer_version)


class Event(_Document):
    event: Literal["begin", "end", "lookup", "store"]
    phase: int
    repository_id: str
    commits: list[str]
    table_name: str | None = None
    row_layout_digest: str | None = None
    writer_version: int | None = None
    ref: Reference | None = None


TARGETS = TypeAdapter(list[Target])
_PREFIX = "e_history_cache "
_phase: ContextVar[tuple[int, str, tuple[str, ...]] | None] = ContextVar("e_history_cache_phase", default=None)


def _emit(event: Literal["begin", "end", "lookup", "store"], target: Target | None = None, ref: ArtifactRef | None = None) -> None:
    phase = _phase.get()
    if phase is None:
        return
    index, repository, commits = phase
    value = Event(event=event, phase=index, repository_id=repository, commits=list(commits),
        table_name=None if target is None else target.table_name,
        row_layout_digest=None if target is None else target.row_layout_digest,
        writer_version=None if target is None else target.writer_version,
        ref=None if ref is None else Reference.model_validate(artifact_ref_to_dict(ref)))
    print(_PREFIX + value.model_dump_json(), flush=True)


def observed_cache_type(targets: list[Target]) -> type[ControlDbSnapshotTableExportCache]:
    by_key = {target.key(): target for target in targets}
    _check(len(by_key) == len(targets), "representative cache keys are not distinct")

    class ObservedCache(ControlDbSnapshotTableExportCache):
        def lookup_many(self, keys: tuple[SnapshotTableArtifactCacheKey, ...]) -> dict[SnapshotTableArtifactCacheKey, ArtifactRef]:
            result = super().lookup_many(keys)
            for key in keys:
                if key in by_key:
                    _emit("lookup", by_key[key], result.get(key))
            return result

        def store_many(self, entries: tuple[tuple[SnapshotTableArtifactCacheKey, ArtifactRef], ...]) -> None:
            super().store_many(entries)
            for key, ref in entries:
                if key in by_key:
                    _emit("store", by_key[key], ref)

    return ObservedCache


def observe_history[**P, R](function: Callable[P, R]) -> Callable[P, R]:
    count = 0

    @wraps(function)
    def invoke(*args: P.args, **kwargs: P.kwargs) -> R:
        nonlocal count
        # This is the actual History demand function's existing positional
        # payload/sides, not a synthesized operation or cache response.
        payload: Any = args[0]
        sides: Any = args[2]
        count += 1
        token = _phase.set((count, payload.repository_id, tuple(sorted(sides))))
        try:
            _emit("begin")
            result = function(*args, **kwargs)
            _emit("end")
            return result
        finally:
            _phase.reset(token)

    return invoke


def cache_action(targets: list[Target], *, discard: bool) -> list[dict[str, Any]]:
    from gateway_backend.bootstrap.storage_layout import local_store_from_config
    from gateway_backend.settings import BackendSettings
    settings = BackendSettings()  # type: ignore[call-arg]  # Required fields come from the container environment.
    store = local_store_from_config(settings.deployment_config)
    result = []
    for target in targets:
        key, expected = target.key(), target.cache_ref.to_ref()
        # Eviction affects only this clone's exact derived row and its cache
        # protection owner. READY/submission payloads and protections stay put.
        with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as uow:
            actual = uow.snapshot_table_export_cache.lookup_many((key,)).get(key)
            _check(actual == expected, "clone cache ref differs from frozen source")
        if discard:
            with ControlDbUnitOfWork(settings.control_db_path) as uow:
                _check(uow.snapshot_table_export_cache.discard_if_same(key, expected), "exact-key discard lost its expected ref")
            with ControlDbUnitOfWork(settings.control_db_path, read_only=True) as uow:
                _check(key not in uow.snapshot_table_export_cache.lookup_many((key,)), "cold key remains registered")
        raw = store.locate(expected)
        _check(len(raw) == expected.size_bytes and "sha256:" + hashlib.sha256(raw).hexdigest() == expected.raw_sha256.value,
                 "cache payload integrity mismatch")
        file = pq.ParquetFile(pa.BufferReader(raw))
        footer = file.schema_arrow.metadata or {}
        _check(footer[_LAYOUT].decode() == key.row_layout_digest.value
                 and footer[_REPOSITORY].decode() == key.repository_id and file.metadata.num_rows == target.row_count,
                 "cache payload footer binding mismatch")
        result.append({"target": target.model_dump(mode="json"), "registered": not discard,
                       "payload_retained_and_verified": True})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("worker", "cache"))
    parser.add_argument("targets", type=Path)
    parser.add_argument("--discard", action="store_true")
    args = parser.parse_args()
    targets = TARGETS.validate_json(args.targets.read_bytes(), strict=True)
    _check(len(targets) == 2 and {target.table_name for target in targets} == {"iec104_cfg", "b1_n11_iec104_syx_list"}
             and len({target.key() for target in targets}) == 2, "exactly two distinct authorized targets required")
    if args.mode == "cache":
        print(json.dumps(cache_action(targets, discard=args.discard), ensure_ascii=False))
        return
    _check(not args.discard, "worker cannot prepare cache state")
    from gateway_backend.application.history.compare_jobs import assemble as compare_assemble
    from gateway_backend.bootstrap import operation_worker
    setattr(operation_worker, "ControlDbSnapshotTableExportCache", observed_cache_type(targets))
    compare_assemble._ensure_history_demands_once = observe_history(compare_assemble._ensure_history_demands_once)
    raise SystemExit(operation_worker.main())


if __name__ == "__main__":
    main()
