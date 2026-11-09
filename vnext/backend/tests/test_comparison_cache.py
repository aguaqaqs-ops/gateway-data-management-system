"""Single owner for neutral identity, codec and current records restoration."""
from __future__ import annotations

import json
from contextlib import closing
from dataclasses import replace
from typing import Any

import pytest
from gateway_shared_kernel import raw_blob_digest

from gateway_backend.capabilities.comparison import native
from gateway_backend.capabilities.comparison.cache_codec import ComparisonCacheCodec
from gateway_backend.capabilities.comparison.contracts import (
    ComparisonPlan, ComparisonStorageFacts, DetailedFactsResult, RecordsArtifactFamily,
)
from gateway_backend.capabilities.comparison.production import compare_plan_native
from gateway_backend.capabilities.comparison.row_encoding import _table_digest_payload
from gateway_backend.capabilities.comparison.task_input import (
    NotCacheable, TableTaskIdentity, build_table_task_identity,
)
from gateway_backend.capabilities.comparison.artifacts import (
    RecordsPublicationContext, RecordsPublicationPolicy, _schema_for, _write_arrow_parquet,
)
from gateway_backend.capabilities.table_access import current_kernel_context
from tests.support.comparison_s3_c_inputs import plan
from tests.support.comparison_s3_e_live import canonical_bound
from tests.support.comparison_cache_inputs import complete_canonical_bound
from tests.support.comparison_s3_e_frozen import frozen_case

pytestmark = pytest.mark.unit

_STANDARD = (
    "CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL); INSERT INTO t VALUES (1, 'before');",
    "CREATE TABLE t (id BIGINT PRIMARY KEY, note TEXT NULL); INSERT INTO t VALUES (1, NULL);",
)
_ORDERED = (
    "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);"
    "INSERT INTO t VALUES (1,1,'a'),(NULL,2,'x'),(2,3,'b'),(3,4,'c');",
    "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);"
    "INSERT INTO t VALUES (1,1,'a'),(3,2,'c'),(2,3,'b'),(NULL,4,'x');",
)


def _planned(ordered: bool = False) -> ComparisonPlan:
    source = _ORDERED if ordered else _STANDARD
    return plan(complete_canonical_bound(canonical_bound(source[0]), ordered=ordered),
                complete_canonical_bound(canonical_bound(source[1]), ordered=ordered), ordered=ordered)


def _identity(planned: ComparisonPlan) -> TableTaskIdentity:
    identity = build_table_task_identity(planned, planned.tasks[0], repository_id="replacement-fixture", artifact_scope="scope")
    assert isinstance(identity, TableTaskIdentity)
    return identity


IDENTITY_MUTATIONS = (
    "direction", "row_count", "content", "schema", "compare_key", "policy", "scope",
    "repository", "detail", "diagnostics", "storage",
)


@pytest.mark.parametrize("change", IDENTITY_MUTATIONS)
def test_complete_task_identity_changes_for_every_semantic_input(change: str) -> None:
    planned = _planned()
    task = planned.tasks[0]
    current = task.current_descriptor
    policy = task.policy
    assert current is not None and policy is not None
    reference = _identity(planned)
    repository, scope = "replacement-fixture", "scope"
    if change == "direction":
        task = replace(task, before_descriptor=task.current_descriptor, current_descriptor=task.before_descriptor,
                       before_table=task.current_table, current_table=task.before_table)
    elif change in {"row_count", "content", "schema", "compare_key"}:
        if change == "row_count":
            updated = replace(current, row_count=current.row_count + 1)
        elif change == "content":
            updated = replace(current, raw_content_digest=raw_blob_digest(b"different-content"))
        elif change == "schema":
            updated = replace(current, compare_schema_digest=raw_blob_digest(b"different-schema"))
        else:
            updated = replace(current, compare_key_columns=())
        task = replace(task, current_descriptor=updated, current_table=None)
    elif change == "policy":
        task = replace(task, policy=replace(policy, compare_excluded_columns=("note",)))
    elif change == "scope":
        scope = "other"
    elif change == "repository":
        repository = "other"
    elif change == "detail":
        planned = replace(planned, options=(("row_diff_detail_policy", "CHANGED_COLUMNS"),))
    elif change == "diagnostics":
        planned = replace(planned, diagnostics=("different-diagnostic",))
    elif change == "storage":
        facts = policy.storage_facts_current
        assert facts is not None
        task = replace(task, policy=replace(policy, storage_facts_current=replace(
            facts, storage_projection_version="another-actual-projection-version")))
    actual = build_table_task_identity(planned, task, repository_id=repository, artifact_scope=scope)
    assert isinstance(actual, NotCacheable) or actual.task_digest != reference.task_digest


def test_task_identity_ignores_only_outer_binding_and_reader_authority() -> None:
    planned = _planned()
    original = _identity(planned)
    rebound = replace(planned, pair_id="another-current-pair", tasks=(replace(
        planned.tasks[0], before_table=None, current_table=None,
    ),))
    assert _identity(rebound).task_digest == original.task_digest
    task = planned.tasks[0]
    assert task.before_table is not None and task.current_table is not None
    # Keep descriptor/provenance semantics while dropping only resource owners.
    resources_released = replace(planned, pair_id="another-current-pair", tasks=(replace(
        task,
        before_table=replace(task.before_table, reader=None, artifact=None, batch_reader=None),
        current_table=replace(task.current_table, reader=None, artifact=None, batch_reader=None),
    ),))
    assert _identity(resources_released).task_digest == original.task_digest
    assert original.task_digest.value.startswith("sha256:")
    assert original.task_input.native_policy_jcs == original.task_input.native_policy().encode()


@pytest.mark.parametrize("ordered", (False, True))
def test_neutral_round_trip_matches_independent_facts_and_parquet(ordered: bool) -> None:
    planned = _planned(ordered)
    identity = _identity(planned)
    context = current_kernel_context()
    assert context is not None
    product = compare_plan_native(planned, retain_cache_candidates=True)
    assert isinstance(product.result, DetailedFactsResult) and product.result.facts is not None
    cold_fact, = product.result.facts.tables
    payload = product.encode_cache_candidate("t", identity, context)
    product.close()
    operation = native.begin_records_operation(native_budget_bytes=context.memory.available_bytes // 2,
        cancel_probe=context.cancel_probe, deadline_monotonic=context.deadline_monotonic)
    handle = None
    try:
        fact, handle = ComparisonCacheCodec.restore(payload, identity, planned.tasks[0], operation, context)
        assert handle is not None
        metadata = _table_digest_payload(fact)
        digest = handle.table_fact_digest(json.dumps(metadata, separators=(",", ":")), 8 * 1024**2)
        nodeid = "tests/test_comparison_s3_c_arrow.py::" + (
            "test_ordered_and_blank_arrow_and_complete_fact_replay_match_frozen_python" if ordered
            else "test_native_standard_arrow_and_complete_facts_match_pre_c_source")
        expected: dict[str, Any] = frozen_case(nodeid)
        assert digest == expected["tables"][0]["table_fact_digest"]
        assert cold_fact.table_fact_digest is not None
        assert digest == cold_fact.table_fact_digest.value
        operation.seal()
        frozen_records = {entry["family"]: entry for entry in expected["records"]}
        for family in payload.families:
            with closing(handle.record_batches(family)) as reader:
                batches = tuple(reader)
                raw = _write_arrow_parquet(batches,
                    _schema_for(RecordsArtifactFamily(family), None, identity.task_input.detail_policy),
                    RecordsPublicationPolicy(), RecordsPublicationContext())
            if family in frozen_records:
                assert raw_blob_digest(raw).value == "sha256:" + frozen_records[family]["raw_sha256"]
                assert handle.family_summary(family)[1] == frozen_records[family]["content_digest"]
        assert context.memory.high_water_bytes <= context.memory.limit_bytes
    finally:
        if handle is not None:
            handle.close()
        operation.close()
        payload.close()


def test_cache_restore_rejects_other_scope_before_native_work() -> None:
    planned = _planned()
    identity = _identity(planned)
    context = current_kernel_context()
    assert context is not None
    product = compare_plan_native(planned, retain_cache_candidates=True)
    assert isinstance(product.result, DetailedFactsResult) and product.result.facts is not None
    payload = product.encode_cache_candidate("t", identity, context)
    product.close()
    operation = native.begin_records_operation(native_budget_bytes=64 * 1024**2,
        cancel_probe=context.cancel_probe, deadline_monotonic=context.deadline_monotonic)
    try:
        with pytest.raises(ValueError, match="scope"):
            ComparisonCacheCodec.restore(payload, replace(identity, artifact_scope="another"),
                planned.tasks[0], operation, context)
    finally:
        operation.close()
        payload.close()


STORAGE_MUTATIONS = ("missing", "source_schema", "canonical_schema", "content", "projection",
                     "view", "effective_key", "partial_schema", "partial_projection", "partial_content")


@pytest.mark.parametrize("side", ("before", "current"))
@pytest.mark.parametrize("change", STORAGE_MUTATIONS)
def test_both_canonical_sides_require_complete_bound_storage_facts(side: str, change: str) -> None:
    planned = _planned()
    reference = _identity(planned)
    task = planned.tasks[0]
    policy = task.policy
    assert policy is not None
    facts = policy.storage_facts_before if side == "before" else policy.storage_facts_current
    assert facts is not None
    updated: ComparisonStorageFacts | None
    if change == "missing":
        updated = None
    elif change == "effective_key":
        policy = (replace(policy, effective_key_before=("note",)) if side == "before"
                  else replace(policy, effective_key_current=("note",)))
        updated = facts
    elif change == "view":
        from gateway_backend.capabilities.table_rules.contracts import CanonicalKeyPolicy
        descriptor = task.before_descriptor if side == "before" else task.current_descriptor
        assert descriptor is not None
        view = replace(facts.storage_rule_view, canonical_key_policy=CanonicalKeyPolicy.EXPLICIT,
                       canonical_key_columns=descriptor.primary_key_columns)
        updated = replace(facts, storage_rule_view=view)
    elif change == "source_schema":
        updated = replace(facts, source_schema_digest=raw_blob_digest(b"other-source-schema"))
    elif change == "canonical_schema":
        updated = replace(facts, canonical_schema_digest=raw_blob_digest(b"other-canonical-schema"))
    elif change == "content":
        updated = replace(facts, raw_content_digest=raw_blob_digest(b"other-content"))
    elif change == "projection":
        updated = replace(facts, storage_projection_version="another-valid-projection")
    elif change == "partial_schema":
        updated = replace(facts, canonical_schema_digest=None)
    elif change == "partial_projection":
        updated = replace(facts, storage_projection_version=None)
    else:
        updated = replace(facts, raw_content_digest=None)
    task = replace(task, policy=(replace(policy, storage_facts_before=updated) if side == "before"
                                else replace(policy, storage_facts_current=updated)))
    result = build_table_task_identity(planned, task, repository_id=reference.repository_id, artifact_scope=reference.artifact_scope)
    assert isinstance(result, NotCacheable) or result.task_digest != reference.task_digest


def _encoded(ordered: bool = False) -> tuple[ComparisonPlan, TableTaskIdentity, Any]:
    planned = _planned(ordered)
    identity = _identity(planned)
    context = current_kernel_context()
    assert context is not None
    product = compare_plan_native(planned, retain_cache_candidates=True)
    try:
        assert isinstance(product.result, DetailedFactsResult) and product.result.facts is not None
        return planned, identity, product.encode_cache_candidate("t", identity, context)
    finally:
        product.close()


def _changed_view(payload: Any, name: str, update: Any) -> None:
    import io
    import pyarrow as pa
    views = []
    for view in payload.views:
        if view.name != name:
            views.append(view)
            continue
        with pa.ipc.open_stream(pa.BufferReader(view.raw)) as reader:
            batches = list(reader)
        batch = batches[0]
        batches[0] = update(batch)
        with io.BytesIO() as sink:
            with pa.ipc.new_stream(sink, view.schema) as writer:
                for item in batches:
                    writer.write_batch(item)
            raw = sink.getvalue()
        views.append(replace(view, raw=raw, raw_digest=raw_blob_digest(raw)))
    payload.views = tuple(views)


CACHE_FORMAT_FAULTS = ("missing_rows", "missing_count", "count_type", "count_mismatch",
                       "outcome_count", "empty_schema", "risk_kind", "risk_column", "ordinal")


@pytest.mark.parametrize("fault", CACHE_FORMAT_FAULTS)
def test_neutral_format_faults_are_rejected_before_publication(fault: str) -> None:
    import pyarrow as pa
    from gateway_shared_kernel.jcs import canonicalize_json_value
    planned, identity, payload = _encoded(ordered=fault == "empty_schema")
    context = current_kernel_context()
    assert context is not None
    operation = native.begin_records_operation(native_budget_bytes=128 * 1024**2,
        cancel_probe=context.cancel_probe, deadline_monotonic=context.deadline_monotonic)
    retained = context.memory.used_bytes
    try:
        if fault == "missing_rows":
            payload.native_metadata_json = None
            payload.views = ()
            payload.families = ()
        elif fault in {"missing_count", "count_type", "count_mismatch"}:
            data = json.loads(payload.native_metadata_json)
            if fault == "missing_count":
                data.pop("record_count")
            else:
                data["record_count"] = "one" if fault == "count_type" else 2
            payload.native_metadata_json = json.dumps(data)
        elif fault == "outcome_count":
            data = json.loads(payload.table_fact_jcs)
            data["row_modified_count"] += 1
            payload.table_fact_jcs = canonicalize_json_value(data)
        elif fault == "empty_schema":
            target = next(view for view in payload.views if view.name == "artifact/STANDARD")
            assert target.batch_rows == () and target.raw == b""
            payload.views = tuple(replace(view, schema=pa.schema([("wrong", pa.string())]))
                                  if view is target else view for view in payload.views)
        elif fault in {"risk_kind", "risk_column"}:
            def change_risk(batch: Any) -> Any:
                columns = list(batch.columns)
                if fault == "risk_kind":
                    columns[0] = pa.array(["ROGUE"], type=pa.string())
                else:
                    columns[2] = pa.array([[None]], type=batch.schema.field(2).type)
                return pa.RecordBatch.from_arrays(columns, schema=batch.schema)
            _changed_view(payload, "risk/STANDARD", change_risk)
        else:
            _changed_view(payload, "facts/STANDARD", lambda batch: pa.RecordBatch.from_arrays(
                [pa.array([1], type=pa.uint32()), batch.column(1)], schema=batch.schema))
        with pytest.raises(ValueError):
            ComparisonCacheCodec.restore(payload, identity, planned.tasks[0], operation, context)
        assert context.memory.used_bytes == retained
    finally:
        operation.close()
        payload.close()


def test_zero_standard_family_keeps_its_schema_and_empty_risk_projection() -> None:
    planned, identity, payload = _encoded(ordered=True)
    context = current_kernel_context()
    assert context is not None
    operation = native.begin_records_operation(native_budget_bytes=128 * 1024**2,
        cancel_probe=context.cancel_probe, deadline_monotonic=context.deadline_monotonic)
    handle = None
    try:
        _, handle = ComparisonCacheCodec.restore(payload, identity, planned.tasks[0], operation, context)
        assert handle is not None and handle.family_summary("STANDARD")[0] == 0
        with closing(handle.record_batches("STANDARD")) as records, closing(handle.risk_record_batches()) as risk:
            assert records.schema.field(0).name == "table_name"
            assert risk.schema.field(0).name == "record_kind"
            assert list(records) == list(risk) == []
    finally:
        if handle is not None:
            handle.close()
        operation.close()
        payload.close()


def test_set_cache_round_trip_uses_frozen_sequence_frames_and_null_scalar() -> None:
    import pyarrow as pa
    source = (
        "CREATE TABLE t (id BIGINT PRIMARY KEY, flags SET('a','b'), note TEXT);"
        "INSERT INTO t VALUES (1,'a,b',NULL);",
        "CREATE TABLE t (id BIGINT PRIMARY KEY, flags SET('a','b'), note TEXT);"
        "INSERT INTO t VALUES (1,'','x');",
    )
    planned = plan(*(complete_canonical_bound(canonical_bound(sql)) for sql in source))
    identity = _identity(planned)
    context = current_kernel_context()
    assert context is not None
    product = compare_plan_native(planned, retain_cache_candidates=True)
    assert isinstance(product.result, DetailedFactsResult) and product.result.facts is not None
    fact = product.result.facts.tables[0]
    payload = product.encode_cache_candidate("t", identity, context)
    product.close()
    operation = native.begin_records_operation(native_budget_bytes=128 * 1024**2,
        cancel_probe=context.cancel_probe, deadline_monotonic=context.deadline_monotonic)
    handle = None
    try:
        view = next(item for item in payload.views if item.name == "facts/STANDARD")
        with pa.ipc.open_stream(pa.BufferReader(view.raw)) as reader:
            row = json.loads(next(iter(reader)).column(1)[0].as_py())
        # Pre-E a9da0c59277e3179f34d646eabcd9c185917ae05 standard.py:528-555
        # emits modified values only for changed columns; note is NULL -> 'x'.
        assert row["before_values"] == [["flags", "020320016103200162"], ["note", "0000"]]
        assert row["current_values"] == [["flags", "00"], ["note", "200178"]]
        restored, handle = ComparisonCacheCodec.restore(payload, identity, planned.tasks[0], operation, context)
        assert handle is not None and fact.table_fact_digest is not None
        assert handle.table_fact_digest(json.dumps(_table_digest_payload(restored)), 8 * 1024**2) == fact.table_fact_digest.value
    finally:
        if handle is not None:
            handle.close()
        operation.close()
        payload.close()


@pytest.mark.parametrize("stop", ("foreign", "cancel", "deadline", "budget"))
def test_restore_uses_only_the_active_operation_budget_and_control(
    stop: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from threading import Event
    from gateway_backend.capabilities.table_access import (
        KernelExecutionContext, OperationMemoryBudget, kernel_execution_scope,
    )
    planned, identity, payload = _encoded()
    source_context = current_kernel_context()
    assert source_context is not None
    source_operation = native.begin_records_operation(native_budget_bytes=64 * 1024**2,
        cancel_probe=source_context.cancel_probe, deadline_monotonic=source_context.deadline_monotonic)
    source_used = source_context.memory.used_bytes
    cancel = Event()
    import time
    deadline = time.monotonic() + 3600.0 if stop == "deadline" else None
    context = KernelExecutionContext(OperationMemoryBudget(128 * 1024**2), cancel, 1, deadline)
    try:
        with kernel_execution_scope(context, new_operation=True):
            operation = source_operation if stop == "foreign" else native.begin_records_operation(
                native_budget_bytes=64 * 1024**2, cancel_probe=cancel, deadline_monotonic=deadline)
            filler = None
            if stop == "cancel":
                cancel.set()
            elif stop == "deadline":
                assert deadline is not None
                fixed_deadline = deadline
                monkeypatch.setattr(time, "monotonic", lambda: fixed_deadline + 1.0)
            elif stop == "budget":
                filler = context.memory.reserve(context.memory.available_bytes - 1)
            retained = context.memory.used_bytes
            try:
                error = {"foreign": ValueError, "cancel": InterruptedError, "deadline": TimeoutError, "budget": MemoryError}[stop]
                with pytest.raises(error):
                    ComparisonCacheCodec.restore(payload, identity, planned.tasks[0], operation, context)
                assert context.memory.used_bytes == retained
                assert source_context.memory.used_bytes == source_used
            finally:
                if filler is not None:
                    filler.close()
                if operation is not source_operation:
                    operation.close()
            assert context.memory.used_bytes == 0
    finally:
        source_operation.close()
        payload.close()


def test_restored_arrow_keeps_its_charge_until_the_last_consumer() -> None:
    from gateway_backend.capabilities.table_access import (
        KernelExecutionContext, OperationMemoryBudget, NeverCancel, kernel_execution_scope,
    )
    planned, identity, payload = _encoded()
    context = KernelExecutionContext(OperationMemoryBudget(128 * 1024**2), NeverCancel(), 1)
    try:
        with kernel_execution_scope(context, new_operation=True):
            operation = native.begin_records_operation(native_budget_bytes=64 * 1024**2,
                cancel_probe=context.cancel_probe, deadline_monotonic=None)
            _, handle = ComparisonCacheCodec.restore(payload, identity, planned.tasks[0], operation, context)
            assert handle is not None
            with closing(handle.record_batches("STANDARD")) as reader:
                retained_table = reader.read_all()
            operation.seal()
            handle.close()
            operation.close()
            payload.close()
            assert context.memory.used_bytes > 0
            del retained_table
            assert context.memory.used_bytes == 0
    finally:
        payload.close()


def test_cache_identity_rejects_a_reader_without_canonical_owner_verification() -> None:
    planned = _planned()
    task = planned.tasks[0]
    unverified = canonical_bound(_STANDARD[0])
    assert unverified.table_set is not None and task.before_table is not None
    invalid = replace(task, before_table=replace(task.before_table,
        reader=unverified.table_set.tables[0].reader))
    result = build_table_task_identity(planned, invalid,
        repository_id="replacement-fixture", artifact_scope="scope")
    assert isinstance(result, NotCacheable)


def test_optional_cache_row_bound_keeps_the_completed_business_result() -> None:
    from gateway_backend.capabilities.comparison.production import _InputCharge, _stream
    from gateway_backend.capabilities.comparison.row_encoding import _schema_view
    planned = _planned()
    identity = _identity(planned)
    task = planned.tasks[0]
    assert task.before_table is not None and task.current_table is not None and task.policy is not None
    assert task.before_descriptor is not None and task.current_descriptor is not None
    context = current_kernel_context()
    assert context is not None
    operation = native.begin_records_operation(native_budget_bytes=128 * 1024**2,
        cancel_probe=context.cancel_probe, deadline_monotonic=context.deadline_monotonic)
    before, before_owner = _stream(task.before_table)
    current, current_owner = _stream(task.current_table)
    handle = None
    try:
        handle = native.compare_records_batches(operation, kind=identity.task_input.native_kind,
            table_name="t", before=before, current=current, policy_json=identity.task_input.native_policy(),
            detail_policy=identity.task_input.detail_policy.value,
            input_owner_charge=_InputCharge((before_owner, current_owner)), max_records=2_000_000,
            max_sort_bytes=128 * 1024**2, max_output_bytes=128 * 1024**2,
            max_input_bytes=context.memory.limit_bytes)
        fact = native.table_fact(task, handle, _schema_view(task.before_descriptor, task.current_descriptor, task.policy))
        metadata = json.dumps(_table_digest_payload(fact))
        expected = frozen_case("tests/test_comparison_s3_c_arrow.py::test_native_standard_arrow_and_complete_facts_match_pre_c_source")["tables"][0]["table_fact_digest"]
        assert handle.table_fact_digest(metadata, 8 * 1024**2) == expected
        retained = context.memory.used_bytes
        with pytest.raises(MemoryError, match="budget exceeded"):
            handle.prepare_cache_views(1)
        handle.discard_cache_views()
        assert context.memory.used_bytes == retained
        assert handle.table_fact_digest(metadata, 8 * 1024**2) == expected
    finally:
        if handle is not None:
            handle.close()
        before.close()
        current.close()
        operation.close()


def test_keyless_duplicate_multiset_survives_cache_restore() -> None:
    import pyarrow as pa
    from gateway_backend.capabilities.comparison import ComparisonRequest, plan_comparison
    from gateway_backend.capabilities.snapshot_materialization.contracts import DegradedReason
    from gateway_backend.capabilities.table_rules.contracts import CanonicalKeyPolicy
    from tests.support.table_rules import comparison_ruleset_for, fallback_record
    sides = []
    for insert_rows in ("('a'),('a'),('b')", "('a'),('b'),('b'),('b')"):
        source = complete_canonical_bound(canonical_bound(
            "CREATE TABLE t (value TEXT); INSERT INTO t VALUES " + insert_rows + ";"))
        facts, = source.storage_facts
        source = replace(source, storage_facts=(replace(facts, storage_rule_view=replace(
            facts.storage_rule_view, canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS)),))
        sides.append(source)
    planned = plan_comparison(ComparisonRequest(pair_id="keyless-cache", before=sides[0], current=sides[1],
        rule_set=comparison_ruleset_for(fallback_record())))
    assert isinstance(planned, ComparisonPlan)
    assert planned.tasks[0].current_descriptor is not None
    assert planned.tasks[0].current_descriptor.degraded_reason is DegradedReason.KEYLESS
    identity = _identity(planned)
    context = current_kernel_context()
    assert context is not None
    product = compare_plan_native(planned, retain_cache_candidates=True)
    assert isinstance(product.result, DetailedFactsResult) and product.result.facts is not None
    fact, = product.result.facts.tables
    assert (fact.row_added_count, fact.row_deleted_count, fact.row_modified_count) == (2, 1, 0)
    payload = product.encode_cache_candidate("t", identity, context)
    product.close()
    operation = native.begin_records_operation(native_budget_bytes=128 * 1024**2,
        cancel_probe=context.cancel_probe, deadline_monotonic=context.deadline_monotonic)
    handle = None
    try:
        view = next(item for item in payload.views if item.name == "facts/STANDARD")
        with pa.ipc.open_stream(pa.BufferReader(view.raw)) as reader:
            fact_rows = [json.loads(raw) for batch in reader for raw in batch.column(1).to_pylist()]
        assert [row["kind"] for row in fact_rows] == ["ROW_ADDED", "ROW_ADDED", "ROW_DELETED"]
        assert len({row["row_identity"] for row in fact_rows}) == 3
        # Pre-E a9da0c59277e3179f34d646eabcd9c185917ae05 standard.py:647-663
        # keyless records carry occurrence identities and empty default values.
        assert [(row["before_values"], row["current_values"]) for row in fact_rows] == [([], [])] * 3
        restored, handle = ComparisonCacheCodec.restore(payload, identity, planned.tasks[0], operation, context)
        assert handle is not None and handle.family_summary("STANDARD")[0] == 3
        assert payload.families == ("STANDARD",)
        assert fact.table_fact_digest is not None
        assert handle.table_fact_digest(json.dumps(_table_digest_payload(restored)), 8 * 1024**2) == fact.table_fact_digest.value
    finally:
        if handle is not None:
            handle.close()
        operation.close()
        payload.close()
