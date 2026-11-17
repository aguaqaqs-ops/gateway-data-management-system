"""Serial registry rows remain available across History's lazy and cached paths."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from gateway_backend.application.checkpoints import load_checkpoint_envelope
from gateway_backend.application.history import compare_jobs
from gateway_backend.application.history.compare_jobs import history_compare_step_id
from gateway_backend.application.pair_pipeline import (
    _same_complete_table_identity,
    run_history_pair_pipeline,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import RepositoryColumn
from gateway_backend.infrastructure.control_db.computation_cache import ControlDbComputationCache
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from gateway_backend.infrastructure.control_db.snapshot_export_cache import (
    ControlDbSnapshotTableExportCache,
)
from tests.support.artifact_layout import open_test_store
from tests.support.history_compare_job_harness import (
    REPOSITORY_ID,
    build_history_compare_harness,
    insert_history_compare_operation,
    run_through_step,
)
from tests.support.http_workspace_harness import BASELINE_HEAD
from tests.support.repository_ref_materialization import (
    FakeRepositoryTableAccessProvider,
    catalog_table,
    make_catalog,
)

pytestmark = pytest.mark.unit


def test_history_loads_serial_registry_rows_for_navigation_on_metadata_and_cache_hits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pair_comparison_metrics: list[dict[str, Any]],
) -> None:
    before_commit = BASELINE_HEAD.business_baseline_commit_id
    current_commit = "commit-serial-current"
    com_columns = tuple(
        RepositoryColumn(name=name, ordinal=i, scalar_type=kind, nullable=False)
        for i, (name, kind) in enumerate(
            (
                ("index", "INT"),
                ("board", "INT"),
                ("com_no", "INT"),
                ("exe", "VARCHAR(32)"),
                ("channel_desc", "VARCHAR(32)"),
                ("protocol_name", "VARCHAR(32)"),
            )
        )
    )
    target_columns = (
        RepositoryColumn(name="id", ordinal=0, scalar_type="INT", nullable=False),
        RepositoryColumn(name="value", ordinal=1, scalar_type="VARCHAR(32)", nullable=False),
    )
    tables = (
        catalog_table("com_cfg", com_columns, primary_key=("index",), row_count=1),
        catalog_table("b4_c7_stdmds_extra", target_columns, primary_key=("id",), row_count=1),
    )

    def provider(commit: str, value: str) -> FakeRepositoryTableAccessProvider:
        catalog = make_catalog(tables, repository_id=REPOSITORY_ID, ref=commit, commit=commit)
        rows = {
            "com_cfg": ((1, 4, 7, "stdmdsCOM", "串口通道", "规约名称"),),
            "b4_c7_stdmds_extra": ((1, value),),
        }
        return FakeRepositoryTableAccessProvider(
            catalog=catalog,
            rows=rows,
            declared_rows=rows,
            current_commit=commit,
            table_comments={"com_cfg": "串口配置", "b4_c7_stdmds_extra": "串口协议表"},
        )

    store = open_test_store(tmp_path / "artifacts")
    captured: list[dict[str, Any]] = []
    original = run_history_pair_pipeline

    def capture(**kwargs: Any) -> Any:
        result = original(**kwargs)
        surface = result.surface_result.surface
        assert surface is not None
        (projection,) = surface.projections
        captured.append(json.loads(store.locate(projection.projection_ref)))
        return result

    monkeypatch.setattr(compare_jobs, "run_history_pair_pipeline", capture)
    previous = None
    for run in ("cold", "warm"):
        providers = {
            before_commit: provider(before_commit, "旧值"),
            current_commit: provider(current_commit, "新值"),
        }
        harness = build_history_compare_harness(
            tmp_path / run,
            db_path=None if previous is None else previous.db_path,
            artifact_store=store,
            node_specs=(
                (BASELINE_HEAD.business_baseline_node_id, before_commit),
                (f"bn-serial-{run}", current_commit),
            ),
            custom_providers=providers,
            idempotency_key=f"serial-registry-{run}",
        )

        def transaction() -> ControlDbUnitOfWork:
            return ControlDbUnitOfWork(harness.db_path)

        deps = replace(
            harness.deps,
            computation_cache=ControlDbComputationCache(transaction, store),
            snapshot_export_cache=ControlDbSnapshotTableExportCache(transaction),
        )
        _, handlers, _, bound_deps = compare_jobs.history_compare_composition_bundle(deps)
        harness.deps = bound_deps
        harness.handlers = dict(handlers)
        harness.publication_uow_factory = bound_deps.control_transaction_factory
        insert_history_compare_operation(harness)
        run_through_step(harness, compare_jobs.HISTORY_COMPARE_MATERIALIZE_HANDLER)
        with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
            step = uow.operations.get_step(
                history_compare_step_id(
                    harness.operation_id, compare_jobs.HISTORY_COMPARE_STEP_MATERIALIZE
                )
            )
        assert step.checkpoint_ref is not None
        envelope = load_checkpoint_envelope(harness.artifact_store, step.checkpoint_ref)
        sides = compare_jobs._sides_from_materialize_checkpoint(
            envelope.job_state, harness.artifact_store, repository_id=REPOSITORY_ID
        )
        for side in sides.values():
            assert side.table_set is not None
            assert all(table.reader is None for table in side.table_set.tables)
        assert _same_complete_table_identity(sides[before_commit], sides[current_commit], "com_cfg")
        pair_comparison_metrics.clear()
        run_through_step(harness, compare_jobs.HISTORY_COMPARE_ASSEMBLE_HANDLER)
        run_through_step(harness, compare_jobs.HISTORY_COMPARE_PUBLISH_HANDLER)
        navigation = captured[-1]
        protocol = next(
            group
            for group in navigation["groups"]
            if group["group_key"] == "COMMUNICATION_PROTOCOLS"
        )
        registry = next(
            item for item in protocol["items"] if item["item_key"] == "protocol:com_cfg"
        )
        channel = next(item for item in protocol["items"] if item["item_key"] == "protocol:b4_c7")
        assert registry["label"] == "串口配置"
        assert channel["label"] == "串口通道 规约名称"
        assert [(tab["table_id"], tab["label"]) for tab in channel["tabs"]] == [
            ("b4_c7_stdmds_extra", "串口协议表")
        ]
        if run == "warm":
            assert sum(metric["comparison"]["cache_hits"] for metric in pair_comparison_metrics) > 0
            assert all(
                provider.last_session is not None and not provider.last_session.table_readers
                for provider in providers.values()
            )
        previous = harness
