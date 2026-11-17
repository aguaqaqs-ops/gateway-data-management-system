"""Exact-key observation delegates real SQLite cache and preserves clone source."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from gateway_shared_kernel import raw_blob_digest

from benchmarks import comparison_correctness_history_supplement as supplement
from benchmarks.comparison_correctness_cache_probe import Reference
from benchmarks.real_dump_journey import JourneyFailure
from gateway_backend.artifacts import ArtifactRef, artifact_ref_to_dict
from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
from gateway_backend.artifacts.snapshot_table_export_cache import SnapshotTableArtifactCacheKey
from gateway_backend.infrastructure.control_db.database import (
    ControlDbUnitOfWork,
    initialize_control_db,
)
from gateway_backend.infrastructure.control_db.snapshot_export_cache import (
    ControlDbSnapshotTableExportCache,
)

pytestmark = pytest.mark.unit
TRACE_FAULTS = (
    "cold-hit",
    "no-store",
    "warm-miss",
    "warm-store",
    "wrong-operation",
    "wrong-key",
    "missing-end",
    "extra-phase",
)
CLONE_FAULTS = ("foreign-file", "marker", "symlink")


def _targets() -> list[supplement.Target]:
    result = []
    for name in ("iec104_cfg", "b1_n11_iec104_syx_list"):
        raw = name.encode()
        ref = ArtifactRef(
            build_artifact_id(ArtifactLocation.EXPORT, "supplement-test", name),
            "application/vnd.apache.parquet",
            len(raw),
            raw_blob_digest(raw),
        )
        result.append(
            supplement.Target(
                table_name=name,
                repository_id="repository-test",
                row_layout_digest=raw_blob_digest(raw + b"layout").value,
                writer_version=1,
                cache_ref=Reference.model_validate(artifact_ref_to_dict(ref)),
                row_count=1,
            )
        )
    return result


def test_observer_forwards_actual_sqlite_miss_store_and_hit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    db = tmp_path / "control.sqlite"
    initialize_control_db(db)
    targets = _targets()
    cache = supplement.observed_cache_type(targets)(lambda: ControlDbUnitOfWork(db))

    @supplement.observe_history
    def demand(
        payload: object, deps: object, sides: dict[str, object]
    ) -> dict[SnapshotTableArtifactCacheKey, ArtifactRef]:
        result = cache.lookup_many(tuple(target.key() for target in targets))
        for target in targets:
            if target.key() not in result:
                cache.store_many(((target.key(), target.cache_ref.to_ref()),))
        return dict(result)

    print("code=claim_succeeded operation_id=cold")
    assert (
        demand(
            SimpleNamespace(repository_id="repository-test"), None, {"left": None, "right": None}
        )
        == {}
    )
    print("code=claim_succeeded operation_id=warm")
    assert demand(
        SimpleNamespace(repository_id="repository-test"), None, {"left": None, "right": None}
    ) == {target.key(): target.cache_ref.to_ref() for target in targets}
    trace = capsys.readouterr().out
    proof = supplement.validate_trace(trace, targets, ["cold", "warm"], ["left", "right"])
    assert len(proof) == 10
    with ControlDbUnitOfWork(db, read_only=True) as uow:
        assert uow.snapshot_table_export_cache.lookup_many(
            tuple(target.key() for target in targets)
        ) == {target.key(): target.cache_ref.to_ref() for target in targets}


def _trace(targets: list[supplement.Target]) -> list[str]:
    lines = []
    for phase, operation in ((1, "cold"), (2, "warm")):
        lines.append("code=claim_succeeded operation_id=" + operation)
        base: dict[str, Any] = dict(
            phase=phase, repository_id="repository-test", commits=["left", "right"]
        )
        lines.append(supplement._PREFIX + supplement.Event(event="begin", **base).model_dump_json())
        for target in targets:
            scoped = dict(
                base,
                table_name=target.table_name,
                row_layout_digest=target.row_layout_digest,
                writer_version=1,
            )
            lines.append(
                supplement._PREFIX
                + supplement.Event(
                    event="lookup", ref=None if phase == 1 else target.cache_ref, **scoped
                ).model_dump_json()
            )
            if phase == 1:
                lines.append(
                    supplement._PREFIX
                    + supplement.Event(
                        event="store", ref=target.cache_ref, **scoped
                    ).model_dump_json()
                )
        lines.append(supplement._PREFIX + supplement.Event(event="end", **base).model_dump_json())
    return lines


@pytest.mark.parametrize("fault", TRACE_FAULTS)
def test_trace_rejects_missing_or_conflicting_per_key_proof(fault: str) -> None:
    targets = _targets()
    lines = _trace(targets)
    assert supplement.validate_trace("\n".join(lines), targets, ["cold", "warm"], ["left", "right"])
    if fault == "wrong-operation":
        lines[0] = "code=claim_succeeded operation_id=other"
    else:
        events = [
            (i, supplement.Event.model_validate_json(line.split(supplement._PREFIX)[1]))
            for i, line in enumerate(lines)
            if supplement._PREFIX in line
        ]
        if fault == "missing-end":
            lines.pop(next(i for i, event in events if event.phase == 1 and event.event == "end"))
        elif fault == "no-store":
            lines = [
                line
                for line in lines
                if not (supplement._PREFIX in line and '"event":"store"' in line)
            ]
        else:
            phase = 2 if fault in {"warm-miss", "warm-store"} else 1
            index, event = next(
                (i, e) for i, e in events if e.phase == phase and e.event == "lookup"
            )
            update: dict[str, object] = {}
            if fault == "cold-hit":
                update["ref"] = targets[0].cache_ref
            elif fault == "warm-miss":
                update["ref"] = None
            elif fault == "warm-store":
                update["event"] = "store"
            elif fault == "wrong-key":
                update["row_layout_digest"] = raw_blob_digest(b"wrong").value
            else:
                update["phase"] = 3
            lines[index] = supplement._PREFIX + event.model_copy(update=update).model_dump_json()
    with pytest.raises(JourneyFailure):
        supplement.validate_trace("\n".join(lines), targets, ["cold", "warm"], ["left", "right"])


def _clone_dirs(tmp_path: Path) -> tuple[Path, Path]:
    source, destination = tmp_path / "source", tmp_path / "clone"
    for root in (source, destination):
        (root / "be-export").mkdir(parents=True)
        (root / "be-export/.gateway-storage.json").write_text('{"storage_id":"same"}')
    (source / "be-export/payload").write_bytes(b"source bytes")
    return source, destination


def test_clone_preserves_source_bytes_and_new_storage_markers(tmp_path: Path) -> None:
    source, destination = _clone_dirs(tmp_path)
    before = supplement.tree_manifest(source)
    marker_inode = (destination / "be-export/.gateway-storage.json").stat().st_ino
    assert supplement.clone_roots(source, destination) == before
    assert supplement.tree_manifest(source) == supplement.tree_manifest(destination) == before
    assert (destination / "be-export/.gateway-storage.json").stat().st_ino == marker_inode
    (destination / "be-export/payload").write_bytes(b"clone-only mutation")
    assert supplement.tree_manifest(source) == before


@pytest.mark.parametrize("fault", CLONE_FAULTS)
def test_clone_rejects_foreign_data_marker_mismatch_and_symlink(tmp_path: Path, fault: str) -> None:
    source, destination = _clone_dirs(tmp_path)
    if fault == "foreign-file":
        (destination / "be-export/foreign").write_bytes(b"preserve")
    elif fault == "marker":
        (destination / "be-export/.gateway-storage.json").write_text('{"storage_id":"other"}')
    else:
        (source / "be-export/link").symlink_to(source / "be-export/payload")
    with pytest.raises(JourneyFailure):
        supplement.clone_roots(source, destination)


@pytest.mark.parametrize("ordered", (False, True), ids=("ordinary", "ordered"))
def test_observer_sees_real_history_cold_export_then_warm_lookup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    ordered: bool,
) -> None:
    from gateway_backend.application.history import compare_jobs
    from gateway_backend.artifacts import InMemoryArtifactStore
    from gateway_shared_kernel import DigestRef
    from tests.test_history_compare_jobs import _history_snapshot_bundle_data
    from tests.support.http_workspace_harness import BASELINE_HEAD
    from tests.support.history_compare_job_harness import (
        REPOSITORY_ID,
        build_history_compare_harness,
        ordered_syx_catalog_table,
        run_full_history_compare_job,
    )
    from tests.support.repository_ref_materialization import (
        FakeRepositoryTableAccessProvider,
        catalog_table,
        int_id_column,
        make_catalog,
    )

    left, right = BASELINE_HEAD.business_baseline_commit_id, "commit-observed-current"
    table = (
        ordered_syx_catalog_table()
        if ordered
        else catalog_table("t", (int_id_column(),), primary_key=("id",), row_count=1)
    )
    rows = ((1, 1, "one"),) if ordered else ((1,),)
    store = InMemoryArtifactStore()
    previous = None
    snapshots = []
    targets: list[supplement.Target] = []
    for name in ("seed", "cold", "warm"):
        providers = {
            commit: FakeRepositoryTableAccessProvider(
                catalog=make_catalog(
                    (table,) if present else (),
                    repository_id=REPOSITORY_ID,
                    ref=commit,
                    commit=commit,
                ),
                rows={table.table_name: rows} if present else {},
                current_commit=commit,
            )
            for commit, present in ((left, False), (right, True))
        }
        current = build_history_compare_harness(
            tmp_path / name,
            db_path=None if previous is None else previous.db_path,
            artifact_store=store,
            node_specs=(
                (BASELINE_HEAD.business_baseline_node_id, left),
                ("bn-observed-" + name, right),
            ),
            custom_providers=providers,
            idempotency_key="observed-" + name,
        )

        def factory() -> ControlDbUnitOfWork:
            return ControlDbUnitOfWork(current.db_path)

        cache_type = (
            ControlDbSnapshotTableExportCache
            if name == "seed"
            else supplement.observed_cache_type(targets)
        )
        deps = replace(current.deps, snapshot_export_cache=cache_type(factory))
        _, handlers, _, bound = compare_jobs.history_compare_composition_bundle(deps)
        current.deps, current.handlers, current.publication_uow_factory = (
            bound,
            dict(handlers),
            bound.control_transaction_factory,
        )
        run_full_history_compare_job(current)
        if name == "seed":
            with ControlDbUnitOfWork(current.db_path) as uow:
                row = uow.connection.execute(
                    "SELECT repository_id,row_layout_digest,parquet_writer_contract_version,artifact_id,media_type,size_bytes,raw_sha256 FROM snapshot_table_export_cache"
                ).fetchone()
                assert row is not None
                repository, layout, version, artifact, media, size, sha = row
                ref = Reference(
                    artifact_id=artifact, media_type=media, size_bytes=size, raw_sha256=sha
                )
                targets = [
                    supplement.Target(
                        table_name=table.table_name,
                        repository_id=repository,
                        row_layout_digest=layout,
                        writer_version=version,
                        cache_ref=ref,
                        row_count=1,
                    )
                ]
                key = SnapshotTableArtifactCacheKey(DigestRef(layout), repository, version)
                assert uow.snapshot_table_export_cache.discard_if_same(key, ref.to_ref())
            monkeypatch.setattr(
                compare_jobs,
                "_ensure_history_demands_once",
                supplement.observe_history(compare_jobs._ensure_history_demands_once),
            )
            capsys.readouterr()
        else:
            snapshots.append(_history_snapshot_bundle_data(current)[0])
        previous = current
    events = [
        supplement.Event.model_validate_json(line.split(supplement._PREFIX)[1])
        for line in capsys.readouterr().out.splitlines()
        if supplement._PREFIX in line
    ]
    cold = [event for event in events if event.phase == 1 and event.event == "lookup"]
    warm = [event for event in events if event.phase == 2 and event.event == "lookup"]
    assert cold and cold[0].ref is None
    assert any(
        event.phase == 1 and event.event == "store" and event.ref == targets[0].cache_ref
        for event in events
    )
    assert warm and all(event.ref == targets[0].cache_ref for event in warm)
    assert not any(event.phase == 2 and event.event == "store" for event in events)
    assert snapshots[0] == snapshots[1]


def test_worker_probe_loads_by_file_without_benchmark_import_path(tmp_path: Path) -> None:
    import os
    import subprocess
    import sys
    import benchmarks.comparison_correctness_cache_probe as probe

    source = Path(probe.__file__)
    result = subprocess.run(
        [sys.executable, str(source), "--help"],
        cwd=tmp_path,
        env=dict(os.environ, PYTHONPATH=str(source.parents[1] / "src")),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "worker" in result.stdout and "cache" in result.stdout
