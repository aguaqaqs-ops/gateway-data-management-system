"""Risk candidate replay against the frozen emit/check control sequence."""

from __future__ import annotations

from contextlib import ExitStack
from dataclasses import replace

import pytest
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore
from gateway_backend.capabilities.comparison.contracts import (
    ComparisonRecordsClosure, ComparisonTableFact, ComparisonTableStatus, OrderedRecord,
    RecordsArtifactFamily, RecordsClosureEntry,
)
from gateway_backend.capabilities.risk_evaluation import (
    RiskEvaluationInput, RiskEvaluationStatus, RiskExecutionContext, RiskExecutionPolicy,
    RiskOptions, evaluate_risk,
)
from tests.test_comparison_s3_contract_vectors import _added_rows, _input

pytestmark = pytest.mark.unit


class _Clock:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> float:
        self.calls += 1
        return self.calls / 1000.0


class _CancelAfterChecks:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.calls = 0

    def is_set(self) -> bool:
        self.calls += 1
        return self.calls >= self.limit


class _Candidates:
    def __init__(self) -> None:
        self.remaining_uses = {"t-key": 2}
        self.events: tuple[object, ...] | None = None
        self.charges: ExitStack | None = None
        self.hits = 0

    def risk_lookup(self, task_key: str, risk_key: str) -> tuple[object, ...] | None:
        assert task_key == "t-key" and risk_key
        if self.events is not None:
            self.hits += 1
        return self.events

    def risk_store(
        self, task_key: str, risk_key: str,
        events: tuple[object, ...], charges: ExitStack,
    ) -> bool:
        assert task_key == "t-key" and risk_key and self.events is None
        self.events = events
        self.charges = charges
        return True

    def risk_evict(self, task_key: str, risk_key: str) -> None:
        assert task_key == "t-key" and risk_key
        self.events = None
        if self.charges is not None:
            self.charges.close()
            self.charges = None

    def close(self) -> None:
        if self.charges is not None:
            self.charges.close()
            self.charges = None


class _RecordsAccess:
    def __init__(self, closure: ComparisonRecordsClosure) -> None:
        self.closure = closure
        self.calls = 0

    def get_records_closure(self) -> ComparisonRecordsClosure:
        self.calls += 1
        return self.closure

    def get_ordered_records(self, table_name: str) -> tuple[OrderedRecord, ...]:
        raise AssertionError(f"ordered records unexpectedly requested: {table_name}")


def _closure_for(source: RiskEvaluationInput, *, wrong_digest: bool = False) -> ComparisonRecordsClosure:
    facts = source.comparison_facts
    digest = raw_blob_digest(b"s3-d-closure")
    ref = ArtifactRef("s3-d-closure-ref", "application/octet-stream", 0, digest)
    return ComparisonRecordsClosure(
        comparison_digest=(raw_blob_digest(b"wrong-pair") if wrong_digest
                           else facts.comparison_digest),
        facts_core_digest=facts.facts_core_digest,
        records=(RecordsClosureEntry(
            table_name="t", family=RecordsArtifactFamily.STANDARD,
            records_ref=ref, records_manifest_ref=ref,
            records_manifest_digest=digest, records_content_digest=digest,
            record_count=0,
        ),),
        closure_manifest_digest=digest,
    )


def test_cached_filtered_emit_still_hits_current_pair_cap_in_same_clock_order() -> None:
    # SCHEMA_CHANGED emits a visible table annotation, then ROW_ADDED emits
    # a filtered low-risk candidate. On the second run, cap=1 must reject the
    # filtered Emit before level filtering and discard all partial annotations.
    table = replace(
        _added_rows("t", 1), status=ComparisonTableStatus.SCHEMA_CHANGED,
        table_fact_digest=raw_blob_digest(b"s3-d-risk-cache-table"),
    )
    source = _input((table,), options=RiskOptions(include_low_risk=False))
    cache = _Candidates()
    cached_input = replace(source, risk_cache_session=cache, risk_task_keys={"t": "t-key"})
    try:
        warm_clock = _Clock()
        warm = evaluate_risk(
            cached_input, artifact_store=InMemoryArtifactStore(),
            execution_context=RiskExecutionContext(clock=warm_clock),
        )
        assert warm.status is RiskEvaluationStatus.READY
        assert cache.events is not None and len(cache.events) >= 2

        cap = RiskExecutionPolicy(max_annotations_per_pair=1)
        hit_clock = _Clock()
        hit = evaluate_risk(
            cached_input, artifact_store=InMemoryArtifactStore(),
            execution_policy=cap, execution_context=RiskExecutionContext(clock=hit_clock),
        )
        miss_clock = _Clock()
        miss = evaluate_risk(
            source, artifact_store=InMemoryArtifactStore(),
            execution_policy=cap, execution_context=RiskExecutionContext(clock=miss_clock),
        )
        assert cache.hits == 1
        assert hit.status is miss.status is RiskEvaluationStatus.DEGRADED
        assert hit.risk_evaluation is not None and miss.risk_evaluation is not None
        assert hit.risk_evaluation.risk_evaluation_digest == miss.risk_evaluation.risk_evaluation_digest
        assert hit.risk_closure is None and miss.risk_closure is None
        assert hit_clock.calls == miss_clock.calls
    finally:
        cache.close()
@pytest.mark.parametrize("boundary", ("cancel", "deadline"))
def test_cached_risk_rechecks_current_operation_boundary_at_emit(
    boundary: str,
) -> None:
    table = replace(
        _added_rows("t", 1),
        table_fact_digest=raw_blob_digest(b"s3-d-risk-current-boundary"),
    )
    source = _input((table,))
    cache = _Candidates()
    cached_input = replace(source, risk_cache_session=cache, risk_task_keys={"t": "t-key"})
    try:
        warm = evaluate_risk(cached_input, artifact_store=InMemoryArtifactStore())
        assert warm.status is RiskEvaluationStatus.READY
        assert cache.events is not None

        hit_clock, miss_clock = _Clock(), _Clock()
        if boundary == "cancel":
            hit_cancel, miss_cancel = _CancelAfterChecks(3), _CancelAfterChecks(3)
            hit_context = RiskExecutionContext(clock=hit_clock, cancel_requested=hit_cancel)
            miss_context = RiskExecutionContext(clock=miss_clock, cancel_requested=miss_cancel)
        else:
            hit_context = RiskExecutionContext(clock=hit_clock, deadline_monotonic=0.007)
            miss_context = RiskExecutionContext(clock=miss_clock, deadline_monotonic=0.007)
        hit = evaluate_risk(
            cached_input, artifact_store=InMemoryArtifactStore(),
            execution_context=hit_context,
        )
        miss = evaluate_risk(
            source, artifact_store=InMemoryArtifactStore(),
            execution_context=miss_context,
        )
        assert cache.hits == 1
        assert hit.status is miss.status is RiskEvaluationStatus.CANCELLED
        assert hit.diagnostics == miss.diagnostics
        assert hit_clock.calls == miss_clock.calls
        if boundary == "cancel":
            assert hit_cancel.calls == miss_cancel.calls
    finally:
        cache.close()


@pytest.mark.parametrize(
    ("policy", "tables", "cached_name", "expected_counts", "expected_diagnostic"),
    (
        (
            RiskExecutionPolicy(max_annotations_per_table=2, max_annotations_per_pair=3),
            ((_added_rows("a", 3), _added_rows("b", 2), _added_rows("c", 1))),
            "a", (1, 2, 1), "risk table budget exceeded",
        ),
        (
            RiskExecutionPolicy(max_annotations_per_table=2, max_annotations_per_pair=2),
            (_added_rows("a", 3),),
            "a", (0,), "max_annotations_per_pair exceeded",
        ),
        (
            RiskExecutionPolicy(
                max_annotations_per_table=2, max_annotations_per_pair=3,
                max_diagnostics_per_table=1,
            ),
            (
                _added_rows("a", 3, diagnostics=("first", "second")),
                _added_rows("b", 2), _added_rows("c", 1),
            ),
            "b", (0, 0, 0), "max_annotations_per_pair exceeded",
        ),
    ),
)
def test_cached_risk_replays_frozen_table_pair_and_preflight_counting(
    policy: RiskExecutionPolicy,
    tables: tuple[ComparisonTableFact, ...],
    cached_name: str,
    expected_counts: tuple[int, ...],
    expected_diagnostic: str,
) -> None:
    prepared = tuple(
        replace(table, table_fact_digest=raw_blob_digest(b"cache-" + table.table_name.encode()))
        if table.table_name == cached_name else table
        for table in tables
    )
    source = _input(prepared)
    cache = _Candidates()
    cached_input = replace(
        source, risk_cache_session=cache, risk_task_keys={cached_name: "t-key"},
    )
    try:
        warm = evaluate_risk(cached_input, artifact_store=InMemoryArtifactStore())
        assert warm.status is RiskEvaluationStatus.READY
        assert cache.events is not None
        hit = evaluate_risk(
            cached_input, artifact_store=InMemoryArtifactStore(), execution_policy=policy,
        )
        miss = evaluate_risk(
            source, artifact_store=InMemoryArtifactStore(), execution_policy=policy,
        )
        assert cache.hits == 1
        assert hit.status is miss.status is RiskEvaluationStatus.DEGRADED
        assert hit.risk_evaluation is not None and miss.risk_evaluation is not None
        assert hit.risk_evaluation.risk_evaluation_digest == miss.risk_evaluation.risk_evaluation_digest
        assert hit.risk_report is not None and miss.risk_report is not None
        assert tuple(item.annotation_count for item in hit.risk_report.tables) == expected_counts
        assert tuple(item.annotation_count for item in miss.risk_report.tables) == expected_counts
        assert expected_diagnostic in tuple(
            diagnostic for item in hit.risk_report.tables for diagnostic in item.diagnostics
        )
        assert (hit.risk_closure is None) == (miss.risk_closure is None)
    finally:
        cache.close()


def test_cached_table_time_budget_degrades_at_the_same_emit_check() -> None:
    table = replace(
        _added_rows("t", 2), table_fact_digest=raw_blob_digest(b"time-budget-table"),
    )
    source = _input((table,))
    cache = _Candidates()
    cached_input = replace(source, risk_cache_session=cache, risk_task_keys={"t": "t-key"})
    try:
        assert evaluate_risk(cached_input, artifact_store=InMemoryArtifactStore()).status is RiskEvaluationStatus.READY
        policy = RiskExecutionPolicy(max_risk_table_wall_time_seconds=0.001)
        hit_clock, miss_clock = _Clock(), _Clock()
        hit = evaluate_risk(
            cached_input, artifact_store=InMemoryArtifactStore(), execution_policy=policy,
            execution_context=RiskExecutionContext(clock=hit_clock),
        )
        miss = evaluate_risk(
            source, artifact_store=InMemoryArtifactStore(), execution_policy=policy,
            execution_context=RiskExecutionContext(clock=miss_clock),
        )
        assert cache.hits == 1
        assert hit.status is miss.status is RiskEvaluationStatus.DEGRADED
        assert hit.risk_report is not None and miss.risk_report is not None
        assert hit.risk_report.tables[0].diagnostics == ("risk table budget exceeded",)
        assert hit.risk_evaluation is not None and miss.risk_evaluation is not None
        assert hit.risk_evaluation.risk_evaluation_digest == miss.risk_evaluation.risk_evaluation_digest
        assert hit_clock.calls == miss_clock.calls
    finally:
        cache.close()


@pytest.mark.parametrize("failure", ("missing", "wrong_digest"))
def test_cached_closure_event_checks_the_current_access_at_its_original_point(
    failure: str,
) -> None:
    table = replace(
        _added_rows("t", 1), records=(),
        table_fact_digest=raw_blob_digest(b"closure-event-table"),
    )
    source = _input((table,))
    good_access = _RecordsAccess(_closure_for(source))
    cache = _Candidates()
    cached_input = replace(
        source, records_access=good_access,
        risk_cache_session=cache, risk_task_keys={"t": "t-key"},
    )
    try:
        warm = evaluate_risk(cached_input, artifact_store=InMemoryArtifactStore())
        assert warm.status is RiskEvaluationStatus.READY
        assert cache.events is not None and good_access.calls == 1
        access = None if failure == "missing" else _RecordsAccess(
            _closure_for(source, wrong_digest=True),
        )
        hit = evaluate_risk(
            replace(cached_input, records_access=access),
            artifact_store=InMemoryArtifactStore(),
        )
        miss = evaluate_risk(
            replace(source, records_access=access),
            artifact_store=InMemoryArtifactStore(),
        )
        assert cache.hits == 1
        assert hit.status is miss.status is RiskEvaluationStatus.FAILED
        assert hit.diagnostics == miss.diagnostics
        assert "records closure" in hit.diagnostics[0]
        if access is not None:
            assert access.calls == 2
    finally:
        cache.close()


def test_large_optional_risk_key_safely_misses_with_same_result() -> None:
    table = replace(
        _added_rows("t", 1), table_fact_digest=raw_blob_digest(b"large-risk-key-table"),
    )
    source = _input((table,))
    source = replace(source, comparison_facts=replace(
        source.comparison_facts, diagnostics=("x" * 70_000,),
    ))
    cache = _Candidates()
    cached_input = replace(source, risk_cache_session=cache, risk_task_keys={"t": "t-key"})
    try:
        candidate = evaluate_risk(cached_input, artifact_store=InMemoryArtifactStore())
        baseline = evaluate_risk(source, artifact_store=InMemoryArtifactStore())
        assert candidate.status is baseline.status is RiskEvaluationStatus.READY
        assert candidate.risk_evaluation is not None and baseline.risk_evaluation is not None
        assert candidate.risk_evaluation.risk_evaluation_digest == baseline.risk_evaluation.risk_evaluation_digest
        assert cache.events is None and cache.hits == 0
    finally:
        cache.close()
