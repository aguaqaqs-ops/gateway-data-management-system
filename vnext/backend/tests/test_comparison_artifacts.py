"""Records closure and publication contracts on live native Arrow output."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore, put_with_built_ref
from gateway_backend.capabilities.comparison import (
    DetailedFactsResult, RecordsArtifactFamily, RecordsCancelled, RecordsDetailPolicy,
    RecordsPublicationContext, RecordsPublicationPolicy,
    open_records_closure, rewrite_closure_refs,
)
from gateway_backend.capabilities.comparison.artifacts import RecordsPublicationError
from gateway_backend.capabilities.comparison.production import compare_plan_native
from tests.support.comparison_s3_c_inputs import plan
from tests.support.comparison_s3_e_live import canonical_bound, native_product, publish_product
from tests.support.records_diagnostic import standalone_records_batches

pytestmark = pytest.mark.unit

_STANDARD_BEFORE = (
    "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);"
    " INSERT INTO t VALUES (1, 'before');"
)
_STANDARD_CURRENT = (
    "CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);"
    " INSERT INTO t VALUES (1, NULL);"
)
_ORDERED_BEFORE = (
    "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);"
    " INSERT INTO t VALUES (1,1,'a'),(2,2,'b'),(3,3,'c'),(4,4,'d');"
)
_ORDERED_CURRENT = (
    "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);"
    " INSERT INTO t VALUES (4,1,'d'),(3,2,'c'),(2,3,'b'),(1,4,'z');"
)


def _publish_standard(
    store: InMemoryArtifactStore,
    *,
    same: bool = False,
    policy: RecordsPublicationPolicy | None = None,
    context: RecordsPublicationContext | None = None,
) -> tuple[DetailedFactsResult, DetailedFactsResult]:
    product = native_product(
        _STANDARD_BEFORE, _STANDARD_BEFORE if same else _STANDARD_CURRENT,
    )
    try:
        assert isinstance(product.result, DetailedFactsResult)
        return product.result, publish_product(product, store, policy=policy, context=context)
    finally:
        product.close()


def _publish_ordered(
    store: InMemoryArtifactStore,
    *,
    policy: RecordsPublicationPolicy | None = None,
) -> DetailedFactsResult:
    product = native_product(_ORDERED_BEFORE, _ORDERED_CURRENT, ordered=True)
    try:
        return publish_product(product, store, policy=policy)
    finally:
        product.close()


def test_publish_and_reopen_standard_records_preserves_typed_null() -> None:
    store = InMemoryArtifactStore()
    source, published = _publish_standard(store)
    assert source.facts is not None and published.facts is not None
    assert source.facts.comparison_digest == published.facts.comparison_digest
    assert published.facts.records_ref is not None
    assert published.records_closure is not None
    entry, = published.records_closure.records
    assert entry.family is RecordsArtifactFamily.STANDARD
    assert "comparison_digest" not in json.loads(store.locate(entry.records_manifest_ref))
    closure_payload = json.loads(store.locate(published.facts.records_ref))
    assert closure_payload["comparison_digest"] == published.facts.comparison_digest.value
    reopened = open_records_closure(store, published.facts.records_ref)
    rows = [
        row for batch in standalone_records_batches(store, reopened.records[0])
        for row in batch.to_pylist()
    ]
    assert rows[0]["record_kind"] == "ROW_MODIFIED"
    value = rows[0]["current_values"][0]["value"]
    assert value["kind"] == "null"
    assert reopened.comparison_digest == published.facts.comparison_digest
    assert reopened.facts_core_digest == published.facts.facts_core_digest


def test_ordered_publication_uses_independent_record_families() -> None:
    store = InMemoryArtifactStore()
    product = native_product(
        "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);"
        " INSERT INTO t VALUES (1,1,'a'),(NULL,2,'x'),(2,3,'b'),(3,4,'c');",
        "CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);"
        " INSERT INTO t VALUES (1,1,'a'),(3,2,'c'),(2,3,'b'),(NULL,4,'x');",
        ordered=True,
    )
    try:
        published = publish_product(product, store)
    finally:
        product.close()
    assert published.records_closure is not None
    assert {entry.family for entry in published.records_closure.records} == {
        RecordsArtifactFamily.ORDERED, RecordsArtifactFamily.BLANK,
    }


def test_unchanged_pair_publishes_an_empty_closure() -> None:
    store = InMemoryArtifactStore()
    _, published = _publish_standard(store, same=True)
    assert published.records_closure is not None
    assert published.records_closure.records == ()
    assert published.facts is not None and published.facts.records_ref is not None
    assert open_records_closure(store, published.facts.records_ref).records == ()


def test_ref_rewrite_keeps_semantic_and_content_digests() -> None:
    store = InMemoryArtifactStore()
    _, published = _publish_standard(store)
    assert published.records_closure is not None
    closure = published.records_closure
    entry, = closure.records
    rewritten_rows = replace(entry.records_ref, artifact_id="rewritten-records")
    rewritten_manifest = replace(entry.records_manifest_ref, artifact_id="rewritten-manifest")
    rewritten = rewrite_closure_refs(
        closure, {
            entry.records_ref: rewritten_rows,
            entry.records_manifest_ref: rewritten_manifest,
        },
    )
    assert rewritten.comparison_digest == closure.comparison_digest
    assert rewritten.facts_core_digest == closure.facts_core_digest
    assert rewritten.records[0].records_content_digest == entry.records_content_digest
    assert rewritten.records[0].records_manifest_digest == entry.records_manifest_digest
    assert rewritten.closure_manifest_digest != closure.closure_manifest_digest


class _CorruptingStore:
    def __init__(self) -> None:
        self.inner = InMemoryArtifactStore()
        self.corrupt_ref: ArtifactRef | None = None

    def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
        return self.inner.put(raw_bytes, ref)

    def locate(self, ref: ArtifactRef) -> bytes:
        raw = self.inner.locate(ref)
        if self.corrupt_ref == ref:
            return raw[:-1] + bytes((raw[-1] ^ 1,))
        return raw


class _RejectingStore:
    def put(self, raw_bytes: bytes, ref: ArtifactRef) -> ArtifactRef:
        del raw_bytes, ref
        raise OSError("store unavailable")

    def locate(self, ref: ArtifactRef) -> bytes:
        del ref
        raise OSError("store unavailable")


def test_store_write_failure_has_no_published_closure() -> None:
    product = native_product(_STANDARD_BEFORE, _STANDARD_CURRENT)
    try:
        with pytest.raises(OSError, match="store unavailable"):
            publish_product(product, _RejectingStore())
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        assert product.result.facts.records_ref is None
    finally:
        product.close()


def test_corrupt_records_are_rejected_before_closure_use() -> None:
    store = _CorruptingStore()
    product = native_product(_STANDARD_BEFORE, _STANDARD_CURRENT)
    try:
        published = publish_product(product, store)
    finally:
        product.close()
    assert published.records_closure is not None
    assert published.facts is not None and published.facts.records_ref is not None
    store.corrupt_ref = published.records_closure.records[0].records_ref
    with pytest.raises(ValueError, match="records"):
        open_records_closure(store, published.facts.records_ref)


@pytest.mark.parametrize("corrupt_kind", ("manifest", "closure"))
def test_manifest_or_closure_tampering_is_rejected(corrupt_kind: str) -> None:
    store = _CorruptingStore()
    product = native_product(_STANDARD_BEFORE, _STANDARD_CURRENT)
    try:
        published = publish_product(product, store)
    finally:
        product.close()
    assert published.records_closure is not None
    assert published.facts is not None and published.facts.records_ref is not None
    store.corrupt_ref = (
        published.records_closure.records[0].records_manifest_ref
        if corrupt_kind == "manifest" else published.facts.records_ref
    )
    with pytest.raises(ValueError, match="(manifest|closure)"):
        open_records_closure(store, published.facts.records_ref)


def test_duplicate_closure_entry_is_rejected() -> None:
    store = InMemoryArtifactStore()
    _, published = _publish_standard(store)
    assert published.facts is not None and published.facts.records_ref is not None
    payload = json.loads(store.locate(published.facts.records_ref))
    payload["records"].append(payload["records"][0])
    duplicate_bytes = canonicalize_json_value(payload)
    duplicate_ref = put_with_built_ref(
        store, duplicate_bytes, artifact_id="duplicate-closure",
        media_type="application/json",
    )
    with pytest.raises(ValueError, match="repeat|closure"):
        open_records_closure(store, duplicate_ref)


@pytest.mark.parametrize(
    "policy",
    (
        RecordsPublicationPolicy(max_records_artifact_bytes=1, max_spool_bytes=1),
        RecordsPublicationPolicy(max_manifest_json_bytes=1),
        RecordsPublicationPolicy(max_closure_json_bytes=1),
    ),
)
def test_publication_limits_fail_before_returning_a_closure(
    policy: RecordsPublicationPolicy,
) -> None:
    product = native_product(_STANDARD_BEFORE, _STANDARD_CURRENT)
    try:
        with pytest.raises(RecordsPublicationError):
            publish_product(product, InMemoryArtifactStore(), policy=policy)
        assert product.result.facts is not None
        assert product.result.facts.records_ref is None
    finally:
        product.close()


def test_reopen_enforces_per_table_record_limit() -> None:
    store = InMemoryArtifactStore()
    published = _publish_ordered(store)
    assert published.facts is not None and published.facts.records_ref is not None
    with pytest.raises(ValueError, match="per-table limit"):
        open_records_closure(
            store, published.facts.records_ref,
            policy=RecordsPublicationPolicy(max_records_per_table=1),
        )


def test_publication_enforces_combined_family_record_limit() -> None:
    product = native_product(_ORDERED_BEFORE, _ORDERED_CURRENT, ordered=True)
    try:
        with pytest.raises(RecordsPublicationError, match="record"):
            publish_product(
                product, InMemoryArtifactStore(),
                policy=RecordsPublicationPolicy(max_records_per_table=1),
            )
    finally:
        product.close()


def test_metadata_only_publication_enforces_combined_family_record_limit() -> None:
    before = canonical_bound(_ORDERED_BEFORE)
    current = canonical_bound(_ORDERED_CURRENT)
    planned = plan(before, current, ordered=True)
    task = planned.tasks[0]
    assert task.current_table is not None
    planned = replace(planned, tasks=(replace(
        task, current_table=replace(task.current_table, reader=None, batch_reader=None),
    ),))
    product = compare_plan_native(planned)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        assert product.handles == {}
        table, = product.result.facts.tables
        assert len(table.records) + len(table.ordered_extension.records if table.ordered_extension else ()) > 1
        with pytest.raises(RecordsPublicationError, match="per-table limit"):
            publish_product(
                product, InMemoryArtifactStore(),
                policy=RecordsPublicationPolicy(max_records_per_table=1),
            )
        assert product.result.facts.records_ref is None
    finally:
        product.close()


@pytest.mark.parametrize("detail_policy", tuple(RecordsDetailPolicy))
def test_detail_policy_is_manifested_without_changing_comparison_digest(
    detail_policy: RecordsDetailPolicy,
) -> None:
    store = InMemoryArtifactStore()
    product = native_product(_STANDARD_BEFORE, _STANDARD_CURRENT)
    try:
        assert isinstance(product.result, DetailedFactsResult)
        assert product.result.facts is not None
        source_digest = product.result.facts.comparison_digest
        published = publish_product(product, store, detail_policy=detail_policy)
    finally:
        product.close()
    assert published.facts is not None and published.records_closure is not None
    assert published.facts.comparison_digest == source_digest
    entry, = published.records_closure.records
    payload = json.loads(store.locate(entry.records_manifest_ref))
    assert payload["row_diff_detail_policy"] == detail_policy.value


def test_cancellation_and_operation_stop_propagate_without_a_closure() -> None:
    product = native_product(_STANDARD_BEFORE, _STANDARD_CURRENT)
    try:
        def cancelled() -> None:
            raise RecordsCancelled("deadline")
        with pytest.raises(RecordsCancelled, match="deadline"):
            publish_product(
                product, InMemoryArtifactStore(),
                context=RecordsPublicationContext(checkpoint=cancelled),
            )
        assert product.result.facts is not None
        assert product.result.facts.records_ref is None
    finally:
        product.close()


@pytest.mark.parametrize("error_type", (InterruptedError, TimeoutError, MemoryError))
def test_publication_propagates_operation_stop(error_type: type[Exception]) -> None:
    product = native_product(_STANDARD_BEFORE, _STANDARD_CURRENT)
    try:
        def stopped() -> None:
            raise error_type("operation stopped")
        with pytest.raises(error_type, match="operation stopped"):
            publish_product(
                product, InMemoryArtifactStore(),
                context=RecordsPublicationContext(checkpoint=stopped),
            )
    finally:
        product.close()
