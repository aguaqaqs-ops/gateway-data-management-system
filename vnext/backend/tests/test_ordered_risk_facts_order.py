"""Ordered risk uses Comparison facts order through both cache layers."""
from __future__ import annotations


import json
from contextlib import closing
from dataclasses import replace
from typing import Any
from pathlib import Path

import pytest

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.comparison import native
from gateway_backend.capabilities.comparison.cache_codec import ComparisonCacheCodec
from gateway_backend.capabilities.comparison.production import compare_plan_native
from gateway_backend.capabilities.risk_evaluation.contracts import OrderedTailBounds
from gateway_backend.capabilities.risk_evaluation import (
    AnnotationDetailPolicy, RiskEvaluationInput, RiskExecutionPolicy, RiskOptions,
    RiskRulesetSnapshot, V1_RISK_RULE_SPECS,
)
from gateway_backend.capabilities.table_access import current_kernel_context
from tests.support.comparison_s3_c_inputs import plan
from tests.support.comparison_s3_e_live import canonical_bound
from tests.support.comparison_cache_inputs import complete_canonical_bound
from tests.test_comparison_cache import _identity
from tests.test_risk_candidate_cache import _Candidates, _evaluate_with_operation

pytestmark = pytest.mark.unit


def _ordered_plan() -> Any:
    ddl = "CREATE TABLE t (gid BIGINT NULL, no INT NULL, name TEXT); INSERT INTO t VALUES "
    sides = []
    for current in (False, True):
        rows = []
        position = 1
        ids = [1, 5, 3, 4, 2, 6, 10, 8, 9, 7, 11, 12] if current else list(range(1, 13))
        for gid in ids:
            name = "new" if current and gid in (3, 9) else "old"
            rows.append(f"({gid},{position},'{name}')")
            position += 1
            for _ in range((1 if gid % 2 else 3) if current else 2):
                rows.append(f"(NULL,{position},NULL)")
                position += 1
        sides.append(complete_canonical_bound(canonical_bound(ddl + ','.join(rows) + ';'), ordered=True))
    return plan(*sides, ordered=True)


def _rows(handle: Any, family: str, *, facts: bool = False) -> list[dict[str, Any]]:
    with closing(handle.facts_batches(family) if facts else handle.risk_record_batches(family)) as reader:
        rows = [row for batch in reader for row in batch.to_pylist()]
    return [json.loads(row['row_jcs']) for row in rows] if facts else rows


def test_replacement_partner_projection_survives_cache_restore() -> None:
    ddl = "CREATE TABLE t (gid BIGINT NULL, no INT NULL, name TEXT); INSERT INTO t VALUES "
    before = complete_canonical_bound(canonical_bound(
        ddl + "(1,1,'a'),(2,2,'b'),(3,3,'c'),(4,4,'d');"), ordered=True)
    current = complete_canonical_bound(canonical_bound(
        ddl + "(1,1,'a'),(NULL,2,NULL),(2,3,'b'),(13,4,'x'),(14,5,'y');"), ordered=True)
    planned = plan(before, current, ordered=True)
    identity = _identity(planned)
    context = current_kernel_context()
    assert context is not None
    product = compare_plan_native(planned, retain_cache_candidates=True)
    try:
        cold = _rows(product.handles['t'], 'ORDERED')
        partners = [row for row in cold if row['replacement_before_identity'] is not None]
        assert [(row['current_position'], row['replacement_before_position']) for row in partners] == [
            (4, 3), (5, 4)]
        payload = product.encode_cache_candidate('t', identity, context)
    finally:
        product.close()
    operation = native.begin_records_operation(native_budget_bytes=context.memory.available_bytes // 2,
        cancel_probe=context.cancel_probe, deadline_monotonic=None)
    handle = None
    try:
        _, handle = ComparisonCacheCodec.restore(payload, identity, planned.tasks[0], operation, context)
        assert handle is not None
        operation.seal()
        assert _rows(handle, 'ORDERED') == cold
    finally:
        if handle is not None:
            handle.close()
        operation.close()
        payload.close()


@pytest.mark.parametrize('counts_only', (False, True))
def test_ordered_facts_projection_and_risk_replay_preserve_order_digest_and_caps(
    counts_only: bool, tmp_path: Path, db_path: Path,
) -> None:
    planned = _ordered_plan()
    identity = _identity(planned)
    context = current_kernel_context()
    assert context is not None
    product = compare_plan_native(planned, retain_cache_candidates=True)
    assert product.result.facts is not None
    facts = product.result.facts
    cold = product.handles['t']
    payload = product.encode_cache_candidate('t', identity, context)
    expected = {family: _rows(cold, family, facts=True) for family in ('ORDERED', 'BLANK')}
    projections = {family: _rows(cold, family) for family in expected}
    for family, rows in projections.items():
        assert len(rows) > 1
        for row, fact in zip(rows, expected[family], strict=True):
            for key, value in row.items():
                if key.startswith('replacement_before_'):
                    continue  # risk-only pairing evidence is absent from public records
                reference = fact['interval'][key] if family == 'BLANK' and key != 'record_kind' else fact[key]
                assert ('sha256:' + value.hex() if isinstance(value, bytes) else value) == reference
        with closing(cold.record_batches(family)) as reader:
            artifact = [row for batch in reader for row in batch.to_pylist()]
        if family == 'ORDERED':
            assert [(r['record_kind'], r['current_position'], r['before_position']) for r in artifact] != [
                (r['record_kind'], r['current_position'], r['before_position']) for r in rows]
        else:
            assert [r['interval']['before_start'] for r in artifact] != [r['before_start'] for r in rows]
    options = RiskOptions(annotation_detail_policy=(AnnotationDetailPolicy.COUNTS_ONLY if counts_only
                                                   else AnnotationDetailPolicy.TARGETS_WITH_EVIDENCE))
    source = RiskEvaluationInput(comparison_facts=facts, risk_ruleset=RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS),
        risk_options=options, ordered_record_views={'t': cold}, ordered_tail_bounds={'t': OrderedTailBounds(36, 36, 36, 36, True)})

    def evaluate(source: RiskEvaluationInput, cap: int) -> tuple[Any, list[Any]]:
        store = InMemoryArtifactStore()
        result = _evaluate_with_operation(source, artifact_store=store, execution_policy=RiskExecutionPolicy(max_annotations_per_table=cap or 1000, max_annotations_per_pair=1 if cap == 0 else 10000))
        assert result.risk_evaluation is not None, result.diagnostics
        documents = [json.loads(store.locate(item.content_ref)) for item in result.annotation_artifacts]
        return (result.status, result.risk_evaluation.risk_evaluation_digest, result.diagnostics), documents

    baseline = {cap: evaluate(source, cap) for cap in (0, 1, 1000)}
    if not counts_only:
        annotations = baseline[1000][1][0]['annotations']
        assert [row['target']['position'] for row in annotations if row['reasons'][0]['rule_id'] == 'ORDERED_MOVE'] == [
            row['current_position'] for row in expected['ORDERED'] if row['record_kind'] == 'ORDERED_ROW_MOVED']
        assert [row['target']['position_range'] for row in annotations if 'BLANK_INTERVAL' in row['reasons'][0]['rule_id']] == [
            [row['interval'][side + '_start'], row['interval'][side + '_end']]
            for row in expected['BLANK'] for side in ['current' if row['record_kind'] == 'BLANK_INSERT_INTERVAL' else 'before']]
    product.close()
    from gateway_backend.artifacts.computation_cache import CacheOperationOwner
    from gateway_backend.capabilities.comparison.persistence import encode_persistent_comparison, decode_persistent_comparison
    from gateway_backend.infrastructure.control_db.computation_cache import ControlDbComputationCache
    from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
    from tests.support.artifact_layout import open_test_store
    persistent = ControlDbComputationCache(lambda: ControlDbUnitOfWork(db_path), open_test_store(tmp_path / 'cache'))
    owner = CacheOperationOwner('preview-operation', 'facts-order')
    entry, blobs = encode_persistent_comparison(payload)
    assert persistent.store(entry, blobs, owner=owner, checkpoint=context.checkpoint, reserve=context.memory.reserve)
    payload.close()
    lease = persistent.lookup_and_pin(entry.key, owner=owner, checkpoint=context.checkpoint, reserve=context.memory.reserve)
    assert lease is not None
    with closing(lease):
        payload = decode_persistent_comparison(lease, identity, context)
    operation = native.begin_records_operation(native_budget_bytes=context.memory.available_bytes // 2,
        cancel_probe=context.cancel_probe, deadline_monotonic=None)
    handle = None
    cache = _Candidates()
    try:
        _, handle = ComparisonCacheCodec.restore(payload, identity, planned.tasks[0], operation, context)
        assert handle is not None
        operation.seal()
        assert {family: _rows(handle, family) for family in expected} == projections
        restored = replace(source, ordered_record_views={'t': handle})
        assert {cap: evaluate(restored, cap) for cap in (0, 1, 1000)} == baseline
        cached = replace(restored, risk_cache_session=cache, risk_task_keys={'t': 't-key'})
        assert evaluate(cached, 1000) == baseline[1000]
        assert cache.events is not None
        assert {cap: evaluate(cached, cap) for cap in (0, 1, 1000)} == baseline
    finally:
        cache.close()
        if handle is not None:
            handle.close()
        operation.close()
        payload.close()
        persistent.release_operation_pins(owner)


def test_blank_net_delete_keeps_full_old_interval_and_single_deleted_count() -> None:
    ddl = 'CREATE TABLE t (gid BIGINT NULL, no INT NULL, name TEXT); INSERT INTO t VALUES '
    before = "(1,1,'a'),(2,2,'b'),(NULL,3,NULL),(NULL,4,NULL),(5,5,'c'),(NULL,6,NULL),(NULL,7,NULL),(8,8,'d');"
    current = "(1,1,'a'),(NULL,2,NULL),(NULL,3,NULL),(2,4,'b'),(NULL,5,NULL),(NULL,6,NULL),(5,7,'c'),(NULL,8,NULL),(8,9,'d');"
    planned = plan(*(complete_canonical_bound(canonical_bound(ddl + rows), ordered=True)
                     for rows in (before, current)), ordered=True)
    with closing(compare_plan_native(planned)) as product:
        records = _rows(product.handles['t'], 'BLANK')
        inserted, = [r for r in records if r['record_kind'] == 'BLANK_INSERT_INTERVAL']
        deleted, = [r for r in records if r['record_kind'] == 'BLANK_DELETE_INTERVAL']
        assert (inserted['current_start'], inserted['current_end'], inserted['row_count']) == (2, 3, 2)
        assert (deleted['before_start'], deleted['before_end'], deleted['current_start'],
                deleted['current_end'], deleted['row_count']) == (6, 7, 8, 8, 1)


def test_ordered_counts_only_aggregates_name_changes_before_applying_cap() -> None:
    ddl = 'CREATE TABLE t (gid BIGINT NULL, no INT NULL, name TEXT); INSERT INTO t VALUES '
    planned = plan(*(complete_canonical_bound(canonical_bound(ddl + rows), ordered=True) for rows in (
        "(1,1,'a'),(2,2,'b');", "(1,1,'x'),(2,2,'y');")), ordered=True)
    with closing(compare_plan_native(planned)) as product:
        assert product.result.facts is not None
        source = RiskEvaluationInput(comparison_facts=product.result.facts,
            risk_ruleset=RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS), ordered_record_views=product.handles,
            risk_options=RiskOptions(annotation_detail_policy=AnnotationDetailPolicy.COUNTS_ONLY))
        result = _evaluate_with_operation(source, execution_policy=RiskExecutionPolicy(max_annotations_per_table=1))
        assert result.status.value == 'READY'
        assert result.risk_report is not None
        assert result.risk_report.tables[0].annotation_count == 1
        assert not result.annotation_artifacts


@pytest.mark.parametrize('family', ('ORDERED', 'BLANK'))
def test_facts_projection_crosses_batches_and_retains_owner_until_last_borrow(family: str) -> None:
    from gateway_backend.capabilities.table_access import (
        KernelExecutionContext, OperationMemoryBudget, NeverCancel, kernel_execution_scope,
    )
    context = KernelExecutionContext(OperationMemoryBudget(512 * 1024**2), NeverCancel(), 1)
    ddl = 'CREATE TABLE t (gid BIGINT NULL, no INT NULL, name TEXT); INSERT INTO t VALUES '
    sides = []
    for current in (False, True):
        rows = []
        for gid in range(1, 1031):
            rows.append(f"({gid},{gid * 2},'{int(current)}')")
            if current:
                rows.append(f'(NULL,{gid * 2 + 1},NULL)')
        sides.append(complete_canonical_bound(canonical_bound(ddl + ','.join(rows) + ';'), ordered=True))
    planned = plan(*sides, ordered=True)
    with kernel_execution_scope(context, new_operation=True):
        product = compare_plan_native(planned)
        handle = product.handles['t']
        with closing(handle.risk_record_batches(family)) as reader:
            batches = tuple(reader)
        assert [batch.num_rows for batch in batches] == [1024, 6]
        if family == 'ORDERED':
            assert [position for batch in batches for position in batch.column('current_position').to_pylist()] == list(range(2, 2061, 2))
        product.close()
        with pytest.raises(ValueError):
            handle.risk_record_batches(family)
        context.resources.close()
        assert context.memory.used_bytes > 0
        del batches
        assert context.memory.used_bytes == 0


def test_ordered_index_admission_evicts_optional_candidate_before_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    ddl = 'CREATE TABLE t (gid BIGINT NULL, no INT NULL, name TEXT); INSERT INTO t VALUES '
    planned = plan(*(complete_canonical_bound(canonical_bound(ddl + rows), ordered=True) for rows in (
        "(1,1,'a'),(2,2,'b');", "(1,1,'a'),(2,2,'b'),(3,3,'c'),(4,4,'d');")), ordered=True)
    context = current_kernel_context()
    assert context is not None
    with closing(compare_plan_native(planned)) as product:
        assert product.result.facts is not None
        source = RiskEvaluationInput(comparison_facts=product.result.facts,
            risk_ruleset=RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS), ordered_record_views=product.handles,
            ordered_tail_bounds={'t': OrderedTailBounds(2, 4, 2, 4, True)})
        baseline = _evaluate_with_operation(source, artifact_store=InMemoryArtifactStore())
        original = context.memory.reserve

        class OptionalCandidate:
            charge: Any = None
            evicted = False

            def risk_evict_for_output(self) -> None:
                self.evicted = True
                assert self.charge is not None
                self.charge.close()

        candidate = OptionalCandidate()
        injected = False

        def reserve(size: int, *, backing: object | None = None) -> Any:
            nonlocal injected
            if size == 4096 + 2 * 512 and not injected:
                injected = True
                candidate.charge = original(context.memory.available_bytes - size + 1)
            return original(size, backing=backing)

        monkeypatch.setattr(context.memory, 'reserve', reserve)
        try:
            actual = _evaluate_with_operation(replace(source, risk_cache_session=candidate), artifact_store=InMemoryArtifactStore())
            assert injected and candidate.evicted
            assert actual.status == baseline.status
            assert actual.risk_evaluation == baseline.risk_evaluation
        finally:
            if candidate.charge is not None:
                candidate.charge.close()


def test_ordered_index_pressure_discards_current_unpublished_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    context = current_kernel_context()
    assert context is not None
    with closing(compare_plan_native(_ordered_plan())) as product:
        assert product.result.facts is not None
        source = RiskEvaluationInput(comparison_facts=product.result.facts,
            risk_ruleset=RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS), ordered_record_views=product.handles,
            ordered_tail_bounds={'t': OrderedTailBounds(36, 36, 36, 36, True)})
        baseline = _evaluate_with_operation(source, artifact_store=InMemoryArtifactStore())
        cache = _Candidates()
        original = context.memory.reserve
        pressure: Any = None
        retried = False

        def reserve(size: int, *, backing: object | None = None) -> Any:
            nonlocal pressure, retried
            # Moves have already recorded optional events when the row rule
            # admits its index. There is no published candidate to evict yet.
            if size == 4096 and not retried:
                if pressure is None:
                    pressure = original(context.memory.available_bytes - size + 1)
                else:
                    assert context.memory.available_bytes >= size
                    retried = True
                    pressure.close()
            return original(size, backing=backing)

        monkeypatch.setattr(context.memory, 'reserve', reserve)
        try:
            actual = _evaluate_with_operation(replace(source, risk_cache_session=cache, risk_task_keys={'t': 't-key'}),
                                              artifact_store=InMemoryArtifactStore())
            assert retried and cache.events is None
            assert actual.status == baseline.status
            assert actual.risk_evaluation == baseline.risk_evaluation
        finally:
            if pressure is not None:
                pressure.close()
            cache.close()


@pytest.mark.parametrize(('before_rows', 'current_rows', 'before_last', 'current_last', 'reason'), (
    ("(1,1,'a');", "(1,1,'a'),(NULL,2,NULL),(NULL,3,NULL);", 1, 1, "ORDERED_TAIL_BLANK_INTERVAL"),
    ("(1,1,'a'),(NULL,2,NULL),(NULL,3,NULL);", "(1,1,'a');", 1, 1, "ORDERED_TAIL_BLANK_INTERVAL"),
    ("(1,1,'a'),(2,2,'b');", "(1,1,'a'),(NULL,2,NULL),(2,3,'b');", 2, 3, "ORDERED_MIDDLE_BLANK_INTERVAL"),
    ("(1,1,'a');", "(1,1,'a'),(NULL,2,NULL),(2,3,'new');", 1, 1, "ORDERED_TAIL_BLANK_INTERVAL"),
    ("(NULL,1,NULL);", "(NULL,1,NULL),(NULL,3,NULL);", None, None, "ORDERED_TAIL_BLANK_INTERVAL"),
))
def test_tail_bounds_use_retained_real_rows(
    before_rows: str, current_rows: str, before_last: int | None, current_last: int | None, reason: str,
) -> None:
    from gateway_backend.application.pair_pipeline import _ordered_tail_bounds
    ddl = 'CREATE TABLE t (gid BIGINT NULL, no INT NULL, name TEXT); INSERT INTO t VALUES '
    planned = plan(*(complete_canonical_bound(canonical_bound(ddl + rows), ordered=True)
                     for rows in (before_rows, current_rows)), ordered=True)
    with closing(compare_plan_native(planned)) as product:
        assert product.result.facts is not None
        bounds = _ordered_tail_bounds(planned, product.result.facts, product.handles)['t']
        assert bounds.complete
        assert (bounds.before_last_retained_position, bounds.current_last_retained_position) == (before_last, current_last)
        source = RiskEvaluationInput(comparison_facts=product.result.facts,
            risk_ruleset=RiskRulesetSnapshot(rules=V1_RISK_RULE_SPECS),
            ordered_record_views=product.handles, ordered_tail_bounds={'t': bounds})
        result = _evaluate_with_operation(source, artifact_store=InMemoryArtifactStore())
        assert result.risk_report is not None
        assert reason in {code.value for table in result.risk_report.tables for code in table.reason_codes}
        incomplete = _evaluate_with_operation(replace(source,
            ordered_tail_bounds={'t': replace(bounds, complete=False)}), artifact_store=InMemoryArtifactStore())
        assert incomplete.risk_report is not None
        assert 'ORDERED_RISK_UNKNOWN' in {
            code.value for table in incomplete.risk_report.tables for code in table.reason_codes
        }
