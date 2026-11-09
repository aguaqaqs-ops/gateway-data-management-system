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
    ComparisonPlan, DetailedFactsResult,
)
from gateway_backend.capabilities.comparison.production import compare_plan_native
from gateway_backend.capabilities.comparison.row_encoding import _table_digest_payload
from gateway_backend.capabilities.comparison.task_input import (
    NotCacheable, TableTaskIdentity, build_table_task_identity,
)
from gateway_backend.capabilities.comparison.artifacts import (
    RecordsPublicationContext, RecordsPublicationPolicy, _write_arrow_parquet,
)
from gateway_backend.capabilities.table_access import current_kernel_context
from tests.support.comparison_s3_c_inputs import plan
from tests.support.comparison_s3_e_live import canonical_bound
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
    return plan(canonical_bound(source[0]), canonical_bound(source[1]), ordered=ordered)


def _identity(planned: ComparisonPlan) -> TableTaskIdentity:
    identity = build_table_task_identity(planned, planned.tasks[0], repository_id="repository", artifact_scope="scope")
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
    assert current is not None and task.policy is not None
    reference = _identity(planned)
    repository, scope = "repository", "scope"
    if change == "direction":
        task = replace(task, before_descriptor=task.current_descriptor, current_descriptor=task.before_descriptor,
                       before_table=task.current_table, current_table=task.before_table)
    elif change in {"row_count", "content", "schema", "compare_key"}:
        updated = replace(current, **{
            "row_count": {"row_count": current.row_count + 1},
            "content": {"raw_content_digest": raw_blob_digest(b"different-content")},
            "schema": {"compare_schema_digest": raw_blob_digest(b"different-schema")},
            "compare_key": {"compare_key_columns": ()},
        }[change])
        task = replace(task, current_descriptor=updated, current_table=None)
    elif change == "policy":
        task = replace(task, policy=replace(task.policy, compare_excluded_columns=("note",)))
    elif change == "scope":
        scope = "other"
    elif change == "repository":
        repository = "other"
    elif change == "detail":
        planned = replace(planned, options=(("row_diff_detail_policy", "CHANGED_COLUMNS"),))
    elif change == "diagnostics":
        planned = replace(planned, diagnostics=("different-diagnostic",))
    elif change == "storage":
        task = replace(task, policy=replace(task.policy, policy_version="new-storage-policy"))
    actual = build_table_task_identity(planned, task, repository_id=repository, artifact_scope=scope)
    assert isinstance(actual, NotCacheable) or actual.task_digest != reference.task_digest


def test_task_identity_ignores_only_outer_binding_and_reader_authority() -> None:
    planned = _planned()
    original = _identity(planned)
    rebound = replace(planned, pair_id="another-current-pair", tasks=(replace(
        planned.tasks[0], before_table=None, current_table=None,
    ),))
    assert _identity(rebound).task_digest == original.task_digest
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
    payload = ComparisonCacheCodec.encode(product.handles["t"], identity, cold_fact, context)
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
                raw = _write_arrow_parquet(batches, reader.schema,
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
    payload = ComparisonCacheCodec.encode(product.handles["t"], identity, product.result.facts.tables[0], context)
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
