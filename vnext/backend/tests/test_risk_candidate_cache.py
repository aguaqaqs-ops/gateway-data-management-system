"""Risk candidate replay against the frozen emit/check control sequence."""

from __future__ import annotations

import json
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from typing import Any, cast

import pytest
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.artifacts import ArtifactRef, ArtifactStorePort, InMemoryArtifactStore
from gateway_backend.capabilities.comparison.contracts import (
    ComparisonRecordsClosure, ComparisonTableFact, ComparisonTableStatus, OrderedRecord,
    RecordsArtifactFamily, RecordsClosureEntry,
)
from gateway_backend.capabilities.risk_evaluation import (
    RiskEvaluationInput, RiskEvaluationResult, RiskEvaluationStatus,
    RiskExecutionContext, RiskExecutionPolicy,
    RiskOptions, RiskRuleId, RiskTarget, RiskTargetType, evaluate_risk,
)
from gateway_backend.capabilities.risk_evaluation.candidates import (
    CHECK_RECORDS_CLOSURE,
    DecodedRiskCandidates,
    RiskCandidateEvent,
    RiskEmitEvent,
    decode_risk_candidates,
    encode_risk_candidates,
    optional_candidate_input,
)
from gateway_backend.capabilities.risk_evaluation._facts import extract_risk_facts
from gateway_backend.capabilities.table_access import OperationMemoryBudget, current_kernel_context
from tests.test_comparison_s3_contract_vectors import _added_rows, _input

pytestmark = pytest.mark.unit


_PORTABLE_DOCUMENT: dict[str, Any] = {
    "complete": True,
    "events": [
        {"kind": "CHECK_RECORDS_CLOSURE", "ordinal": 0},
        {
            "evidence": [["count", 2], ["known", True], ["note", None]],
            "kind": "EMIT", "ordinal": 1, "rule_id": "ROW_ADDED",
            "target": {
                "before_row_identity": None, "changed_columns": ["value"],
                "coverage": None, "current_row_identity": None,
                "position": None, "position_range": None,
                "row_identity": "sha256:" + "1" * 64, "target_type": "ROW",
            },
        },
    ],
    "format": "risk-table-candidates/v1", "task_digest": "risk-key",
}


def test_portable_candidates_preserve_independent_events_and_current_binding() -> None:
    from gateway_shared_kernel import DigestRef
    operation = current_kernel_context()
    assert operation is not None
    events = (
        CHECK_RECORDS_CLOSURE,
        RiskEmitEvent(
            RiskRuleId.ROW_ADDED,
            RiskTarget(RiskTargetType.ROW, table_name="old", row_identity=DigestRef("sha256:" + "1" * 64), changed_columns=("value",)),
            (("count", 2), ("known", True), ("note", None)),
        ),
    )
    encoded = encode_risk_candidates(events, "risk-key", operation)
    assert encoded is not None
    try:
        assert json.loads(encoded.raw) == _PORTABLE_DOCUMENT
        decoded = decode_risk_candidates(encoded.raw, "risk-key", operation)
        try:
            assert decoded.events[0] == CHECK_RECORDS_CLOSURE
            event = decoded.events[1]
            assert isinstance(event, RiskEmitEvent)
            assert event.target.table_name is None
            assert event.bind_target("current").to_document() == {
                **_PORTABLE_DOCUMENT["events"][1]["target"], "table_name": "current",
            }
            assert event.evidence == (("count", 2), ("known", True), ("note", None))
        finally:
            decoded.close()
    finally:
        encoded.close()


_BAD_CANDIDATE_FIELDS = (
    ("complete", False), ("format", "unknown"), ("task_digest", "other"),
    ("events", [{"kind": "CHECK_RECORDS_CLOSURE", "ordinal": 1}]),
    ("events", [{"kind": "CHECK_RECORDS_CLOSURE", "ordinal": True}]),
    ("events", [{"kind": "CHECK_RECORDS_CLOSURE", "ordinal": 0, "validated": True}]),
    ("events", [{"kind": "UNKNOWN", "ordinal": 0}]),
)


@pytest.mark.parametrize(("field_name", "value"), _BAD_CANDIDATE_FIELDS)
def test_candidate_codec_rejects_incomplete_or_mismatched_values(field_name: str, value: object) -> None:
    from gateway_shared_kernel.jcs import canonicalize_json_value
    operation = current_kernel_context()
    assert operation is not None
    before = operation.memory.available_bytes
    raw = canonicalize_json_value({**_PORTABLE_DOCUMENT, field_name: value})
    with pytest.raises(ValueError):
        decode_risk_candidates(raw, "risk-key", operation)
    assert operation.memory.available_bytes == before


@dataclass
class _CodecStop:
    stop_at: int
    stop_error: type[Exception] = TimeoutError
    memory: OperationMemoryBudget = field(default_factory=lambda: OperationMemoryBudget(64 * 1024**2))
    resources: ExitStack = field(default_factory=ExitStack)
    calls: int = 0

    def checkpoint(self) -> None:
        self.calls += 1
        if self.calls >= self.stop_at:
            raise self.stop_error("current operation stopped codec")


@pytest.mark.parametrize("direction", ("encode", "decode"))
@pytest.mark.parametrize("stop_at", (1, 2))
@pytest.mark.parametrize("stop_error", (InterruptedError, TimeoutError))
def test_empty_candidate_codec_observes_current_control_and_releases_reservations(
    direction: str, stop_at: int, stop_error: type[Exception],
) -> None:
    operation = _CodecStop(stop_at, stop_error)
    before = operation.memory.available_bytes
    with pytest.raises(stop_error, match="current operation stopped"):
        if direction == "encode":
            encode_risk_candidates((), "risk-key", operation)
        else:
            decode_risk_candidates(
                b'{"complete":true,"events":[],"format":"risk-table-candidates/v1","task_digest":"risk-key"}',
                "risk-key", operation,
            )
    assert operation.memory.available_bytes == before


def _candidate_key(source: RiskEvaluationInput, task_key: str = "complete-comparison-task") -> str:
    operation = current_kernel_context()
    assert operation is not None
    item = extract_risk_facts(source.comparison_facts, None)[0]
    candidate, charge = optional_candidate_input(item, source, RiskExecutionPolicy(), task_key, operation)
    assert candidate is not None and charge is not None
    try:
        return candidate.task_digest()
    finally:
        charge.close()


def test_risk_key_uses_neutral_task_rules_options_and_diagnostics() -> None:
    from gateway_backend.capabilities.risk_evaluation import RiskArtifactPolicy, RiskLevel, RiskSeverityPolicy
    source = _input((_added_rows("t", 1),))
    key = _candidate_key(source)
    rebound = replace(source, comparison_facts=replace(
        source.comparison_facts, comparison_digest=raw_blob_digest(b"new-pair"),
        tables=(replace(source.comparison_facts.tables[0], table_fact_digest=raw_blob_digest(b"new-bound-table")),),
    ))
    assert _candidate_key(rebound) == key
    assert _candidate_key(source, "reverse-or-other-scope-task") != key
    changed_rule = replace(source.risk_ruleset.rules[0], severity_policy=RiskSeverityPolicy(default_level=RiskLevel.LOW))
    variants = (
        replace(source, risk_options=replace(source.risk_options, include_low_risk=False)),
        replace(source, artifact_policy=RiskArtifactPolicy(options=(("detail", "different"),))),
        replace(source, comparison_facts=replace(source.comparison_facts, diagnostics=("pair-diagnostic",))),
        replace(source, comparison_facts=replace(source.comparison_facts, tables=(replace(source.comparison_facts.tables[0], diagnostics=("RISK_UNCOVERED_TARGET:new",)),))),
        replace(source, risk_ruleset=replace(source.risk_ruleset, rules=(changed_rule, *source.risk_ruleset.rules[1:]), risk_ruleset_digest=None)),
    )
    assert all(_candidate_key(variant) != key for variant in variants)


def _evaluate_with_operation(
    evaluation_input: RiskEvaluationInput,
    *,
    artifact_store: ArtifactStorePort | None = None,
    execution_policy: RiskExecutionPolicy = RiskExecutionPolicy(),
    execution_context: RiskExecutionContext | None = None,
) -> RiskEvaluationResult:
    operation = current_kernel_context()
    assert operation is not None
    return evaluate_risk(
        evaluation_input,
        artifact_store=artifact_store,
        execution_policy=execution_policy,
        execution_context=replace(
            execution_context or RiskExecutionContext(), operation=operation,
        ),
    )


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
        self.decoded: DecodedRiskCandidates | None = None

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
        operation = current_kernel_context()
        assert operation is not None
        assert all(isinstance(event, (RiskEmitEvent, type(CHECK_RECORDS_CLOSURE))) for event in events)
        # Exercise the real portable codec before every replay, including its
        # neutral target binding and closure control events.
        encoded = encode_risk_candidates(cast(tuple[RiskCandidateEvent, ...], events), risk_key, operation)
        assert encoded is not None
        try:
            self.decoded = decode_risk_candidates(encoded.raw, risk_key, operation)
            self.events = self.decoded.events
        finally:
            encoded.close()
        self.charges = charges
        return True

    def risk_evict(self, task_key: str, risk_key: str) -> None:
        assert task_key == "t-key" and risk_key
        self.events = None
        if self.decoded is not None:
            self.decoded.close()
            self.decoded = None
        if self.charges is not None:
            self.charges.close()
            self.charges = None

    def close(self) -> None:
        if self.decoded is not None:
            self.decoded.close()
            self.decoded = None
        if self.charges is not None:
            self.charges.close()
            self.charges = None


class _MultiCandidates:
    """Two retained candidates; the second can crowd the first replay."""

    def __init__(self) -> None:
        self.remaining_uses = {"a-key": 2, "b-key": 2}
        self.entries: dict[tuple[str, str], tuple[tuple[object, ...], ExitStack]] = {}
        self.pressure_on_a = False
        self.hits = 0
        self.evictions = 0

    def risk_lookup(self, task_key: str, risk_key: str) -> tuple[object, ...] | None:
        item = self.entries.get((task_key, risk_key))
        if item is None:
            return None
        self.hits += 1
        if self.pressure_on_a and task_key == "a-key":
            self.pressure_on_a = False
            other = next(charges for (key, _), (_, charges) in self.entries.items()
                         if key == "b-key")
            operation = current_kernel_context()
            assert operation is not None
            # The charge is a real reservation in the current M. It becomes
            # reclaimable only when the unrelated B candidate is discarded.
            other.enter_context(operation.memory.reserve(operation.memory.available_bytes - 1024))
        return item[0]

    def risk_store(
        self, task_key: str, risk_key: str,
        events: tuple[object, ...], charges: ExitStack,
    ) -> bool:
        self.entries[(task_key, risk_key)] = (events, charges)
        return True

    def risk_evict(self, task_key: str, risk_key: str) -> None:
        item = self.entries.pop((task_key, risk_key), None)
        if item is not None:
            item[1].close()
            self.evictions += 1

    def risk_evict_for_output(self) -> None:
        for _, charges in self.entries.values():
            charges.close()
            self.evictions += 1
        self.entries.clear()

    def close(self) -> None:
        self.risk_evict_for_output()


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
    ref = ArtifactRef("a1:durable:b3e19e66a50a137e55ff1dfa19ae51ed1bdfbbbb0e17598ceb04ad2173b61449", "application/octet-stream", 0, digest)
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
        warm = _evaluate_with_operation(
            cached_input, artifact_store=InMemoryArtifactStore(),
            execution_context=RiskExecutionContext(clock=warm_clock),
        )
        assert warm.status is RiskEvaluationStatus.READY
        assert cache.events is not None and len(cache.events) >= 2

        cap = RiskExecutionPolicy(max_annotations_per_pair=1)
        hit_clock = _Clock()
        hit = _evaluate_with_operation(
            cached_input, artifact_store=InMemoryArtifactStore(),
            execution_policy=cap, execution_context=RiskExecutionContext(clock=hit_clock),
        )
        miss_clock = _Clock()
        miss = _evaluate_with_operation(
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
        warm = _evaluate_with_operation(cached_input, artifact_store=InMemoryArtifactStore())
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
        hit = _evaluate_with_operation(
            cached_input, artifact_store=InMemoryArtifactStore(),
            execution_context=hit_context,
        )
        miss = _evaluate_with_operation(
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
            "a", (1, 2, 1), "RISK_TABLE_BUDGET_EXCEEDED",
        ),
        (
            RiskExecutionPolicy(max_annotations_per_table=2, max_annotations_per_pair=2),
            (_added_rows("a", 3),),
            "a", (0,), "RISK_ANNOTATION_LIMIT_EXCEEDED",
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
            "b", (0, 0, 0), "RISK_ANNOTATION_LIMIT_EXCEEDED",
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
        warm = _evaluate_with_operation(cached_input, artifact_store=InMemoryArtifactStore())
        assert warm.status is RiskEvaluationStatus.READY
        assert cache.events is not None
        hit = _evaluate_with_operation(
            cached_input, artifact_store=InMemoryArtifactStore(), execution_policy=policy,
        )
        miss = _evaluate_with_operation(
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
        assert _evaluate_with_operation(cached_input, artifact_store=InMemoryArtifactStore()).status is RiskEvaluationStatus.READY
        policy = RiskExecutionPolicy(max_risk_table_wall_time_seconds=0.001)
        hit_clock, miss_clock = _Clock(), _Clock()
        hit = _evaluate_with_operation(
            cached_input, artifact_store=InMemoryArtifactStore(), execution_policy=policy,
            execution_context=RiskExecutionContext(clock=hit_clock),
        )
        miss = _evaluate_with_operation(
            source, artifact_store=InMemoryArtifactStore(), execution_policy=policy,
            execution_context=RiskExecutionContext(clock=miss_clock),
        )
        assert cache.hits == 1
        assert hit.status is miss.status is RiskEvaluationStatus.DEGRADED
        assert hit.risk_report is not None and miss.risk_report is not None
        assert hit.risk_report.tables[0].diagnostics == ("RISK_TABLE_BUDGET_EXCEEDED",)
        assert hit.risk_evaluation is not None and miss.risk_evaluation is not None
        assert hit.risk_evaluation.risk_evaluation_digest == miss.risk_evaluation.risk_evaluation_digest
        assert hit_clock.calls == miss_clock.calls
    finally:
        cache.close()


@pytest.mark.parametrize(
    ("count", "include_low", "policy", "expected_status", "expected_counts", "diagnostic"),
    (
        # First emit completes before .003s; on the next emit both caps have
        # precedence over a time check that would now reach the table budget.
        (2, True, RiskExecutionPolicy(max_annotations_per_table=1, max_annotations_per_pair=1,
            max_risk_table_wall_time_seconds=0.003), RiskEvaluationStatus.DEGRADED, (0,),
            "RISK_ANNOTATION_LIMIT_EXCEEDED"),
        # A filtered candidate does not perform an emit-local time check.
        (1, False, RiskExecutionPolicy(max_risk_table_wall_time_seconds=0.0001),
            RiskEvaluationStatus.READY, (), None),
        # The last retained emit still performs its original post-append check.
        (1, True, RiskExecutionPolicy(max_risk_table_wall_time_seconds=0.001),
            RiskEvaluationStatus.DEGRADED, (1,), "RISK_TABLE_BUDGET_EXCEEDED"),
    ),
)
def test_candidate_replay_preserves_cap_filter_and_last_emit_time_points(
    count: int, include_low: bool, policy: RiskExecutionPolicy,
    expected_status: RiskEvaluationStatus, expected_counts: tuple[int, ...], diagnostic: str | None,
) -> None:
    source = _input((_added_rows("t", count),), options=RiskOptions(include_low_risk=include_low))
    cache = _Candidates()
    cached = replace(source, risk_cache_session=cache, risk_task_keys={"t": "t-key"})
    try:
        assert _evaluate_with_operation(cached, artifact_store=InMemoryArtifactStore()).status is RiskEvaluationStatus.READY
        hit_clock, miss_clock = _Clock(), _Clock()
        hit = _evaluate_with_operation(cached, artifact_store=InMemoryArtifactStore(), execution_policy=policy,
            execution_context=RiskExecutionContext(clock=hit_clock))
        miss = _evaluate_with_operation(source, artifact_store=InMemoryArtifactStore(), execution_policy=policy,
            execution_context=RiskExecutionContext(clock=miss_clock))
        assert hit.status is miss.status is expected_status
        assert cache.hits == 1 and hit_clock.calls == miss_clock.calls
        assert hit.risk_report is not None and miss.risk_report is not None
        assert tuple(table.annotation_count for table in hit.risk_report.tables) == expected_counts
        assert tuple(table.annotation_count for table in miss.risk_report.tables) == expected_counts
        assert hit.risk_evaluation is not None and miss.risk_evaluation is not None
        assert hit.risk_evaluation.risk_evaluation_digest == miss.risk_evaluation.risk_evaluation_digest
        if diagnostic is not None:
            assert diagnostic in tuple(value for table in hit.risk_report.tables for value in table.diagnostics)
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
        warm = _evaluate_with_operation(cached_input, artifact_store=InMemoryArtifactStore())
        assert warm.status is RiskEvaluationStatus.READY
        assert cache.events is not None and good_access.calls == 1
        access = None if failure == "missing" else _RecordsAccess(
            _closure_for(source, wrong_digest=True),
        )
        hit = _evaluate_with_operation(
            replace(cached_input, records_access=access),
            artifact_store=InMemoryArtifactStore(),
        )
        miss = _evaluate_with_operation(
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
        candidate = _evaluate_with_operation(cached_input, artifact_store=InMemoryArtifactStore())
        baseline = _evaluate_with_operation(source, artifact_store=InMemoryArtifactStore())
        assert candidate.status is baseline.status is RiskEvaluationStatus.READY
        assert candidate.risk_evaluation is not None and baseline.risk_evaluation is not None
        assert candidate.risk_evaluation.risk_evaluation_digest == baseline.risk_evaluation.risk_evaluation_digest
        assert cache.events is None and cache.hits == 0
    finally:
        cache.close()


def test_other_optional_candidate_cannot_block_current_risk_output() -> None:
    tables = tuple(replace(
        _added_rows(name, 1),
        table_fact_digest=raw_blob_digest(f"risk-pressure-{name}".encode()),
    ) for name in ("a", "b"))
    source = _input(tables)
    cache = _MultiCandidates()
    cached_input = replace(
        source, risk_cache_session=cache,
        risk_task_keys={"a": "a-key", "b": "b-key"},
    )
    try:
        warm = _evaluate_with_operation(cached_input, artifact_store=InMemoryArtifactStore())
        assert warm.status is RiskEvaluationStatus.READY
        assert len(cache.entries) == 2

        cache.pressure_on_a = True
        current = replace(cached_input, requested_tables=("a",))
        candidate = _evaluate_with_operation(current, artifact_store=InMemoryArtifactStore())
        baseline = _evaluate_with_operation(
            replace(source, requested_tables=("a",)),
            artifact_store=InMemoryArtifactStore(),
        )
        assert cache.hits == 1 and cache.evictions == 2 and cache.entries == {}
        assert candidate.status is baseline.status is RiskEvaluationStatus.READY
        assert candidate.risk_evaluation is not None and baseline.risk_evaluation is not None
        assert candidate.risk_evaluation.risk_evaluation_digest == baseline.risk_evaluation.risk_evaluation_digest
        assert candidate.risk_closure is not None and baseline.risk_closure is not None
        assert candidate.risk_closure.closure_manifest_digest == baseline.risk_closure.closure_manifest_digest
        operation = current_kernel_context()
        assert operation is not None and operation.memory.used_bytes < 128 * 1024**2
    finally:
        cache.close()


def test_other_optional_candidates_cannot_block_cold_annotation_emit() -> None:
    warm_tables = tuple(replace(
        _added_rows(name, 1),
        table_fact_digest=raw_blob_digest(f"cold-pressure-{name}".encode()),
    ) for name in ("a", "b"))
    cache = _MultiCandidates()
    warm_source = replace(
        _input(warm_tables), risk_cache_session=cache,
        risk_task_keys={"a": "a-key", "b": "b-key"},
    )

    class _PressureClock(_Clock):
        def __call__(self) -> float:
            value = super().__call__()
            if self.calls == 4:
                operation = current_kernel_context()
                assert operation is not None
                other = next(charges for (key, _), (_, charges) in cache.entries.items()
                             if key == "b-key")
                # Call 4 is C's table-start clock, after the pair's required
                # admission and before the first cold Emit reservation.
                other.enter_context(operation.memory.reserve(operation.memory.available_bytes - 1024))
            return value

    try:
        warm = _evaluate_with_operation(warm_source, artifact_store=InMemoryArtifactStore())
        assert warm.status is RiskEvaluationStatus.READY and len(cache.entries) == 2
        cold_source = replace(
            _input(warm_tables + (_added_rows("c", 1),)),
            requested_tables=("c",),
        )
        clock = _PressureClock()
        candidate = _evaluate_with_operation(
            replace(cold_source, risk_cache_session=cache),
            artifact_store=InMemoryArtifactStore(),
            execution_context=RiskExecutionContext(clock=clock),
        )
        baseline = _evaluate_with_operation(cold_source, artifact_store=InMemoryArtifactStore())
        assert clock.calls >= 4 and cache.hits == 0
        assert cache.evictions == 2 and cache.entries == {}
        assert candidate.status is baseline.status is RiskEvaluationStatus.READY
        assert candidate.risk_evaluation is not None and baseline.risk_evaluation is not None
        assert candidate.risk_evaluation.risk_evaluation_digest == baseline.risk_evaluation.risk_evaluation_digest
        assert candidate.risk_closure is not None and baseline.risk_closure is not None
        assert candidate.risk_closure.closure_manifest_digest == baseline.risk_closure.closure_manifest_digest
    finally:
        cache.close()


@pytest.mark.parametrize("limit", ("complete", "pair", "artifact"))
def test_attribution_observer_sees_actual_typed_cold_and_replayed_outcomes(limit: str) -> None:
    from gateway_backend.capabilities.risk_evaluation.contracts import RiskAnnotation

    table = replace(_added_rows("t", 1), status=ComparisonTableStatus.SCHEMA_CHANGED,
        table_fact_digest=raw_blob_digest(b"typed-observer"))
    source = _input((table,))
    cache = _Candidates()
    cached = replace(source, risk_cache_session=cache, risk_task_keys={"t": "t-key"})
    policy = (RiskExecutionPolicy(max_annotations_per_pair=1) if limit == "pair" else
              RiskExecutionPolicy(max_annotation_artifact_bytes_per_table=1) if limit == "artifact" else
              RiskExecutionPolicy())
    try:
        warm = _evaluate_with_operation(cached, artifact_store=InMemoryArtifactStore())
        assert warm.status is RiskEvaluationStatus.READY and cache.events is not None
        captured: list[list[tuple[str, tuple[RiskAnnotation, ...], bool]]] = []
        for value in (source, cached):
            events: list[tuple[str, tuple[RiskAnnotation, ...], bool]] = []
            result = _evaluate_with_operation(value, artifact_store=InMemoryArtifactStore(),
                execution_policy=policy, execution_context=RiskExecutionContext(
                    attribution_observer=lambda name, annotations, complete: events.append((name, annotations, complete))))
            assert result.status in {RiskEvaluationStatus.READY, RiskEvaluationStatus.DEGRADED}
            captured.append(events)
        assert captured[0] == captured[1]
        assert len(captured[0]) == 1
        name, annotations, complete = captured[0][0]
        assert name == "t" and complete is (limit == "complete")
        if limit == "pair":
            assert annotations == ()
        else:
            assert annotations and all(type(a) is RiskAnnotation for a in annotations)
            assert any(a.target.target_type is RiskTargetType.TABLE for a in annotations)
        assert cache.hits == 1
    finally:
        cache.close()
