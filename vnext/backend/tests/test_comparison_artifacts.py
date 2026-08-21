"""S5 records artifact, closure and publication contract tests."""

from __future__ import annotations

import json

import pytest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore, put_with_built_ref
from gateway_backend.capabilities.comparison import (
    CancelledResult,
    DetailedFactsResult,
    RecordsArtifactFamily,
    RecordsCancelled,
    RecordsDetailPolicy,
    RecordsPublicationContext,
    RecordsPublicationPolicy,
    compare_plan,
    open_records_closure,
    publish_records_closure,
    read_records_artifact,
    rewrite_closure_refs,
)
from tests.test_comparison_ordered import _plan as ordered_plan
from tests.test_comparison_standard import _plan as standard_plan

pytestmark = pytest.mark.unit


def _standard_result(*, same: bool = False) -> DetailedFactsResult:
    before = """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 'before');
    """
    current = before if same else """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, NULL);
    """
    result = compare_plan(standard_plan(before, current))
    assert isinstance(result, DetailedFactsResult)
    return result


def _ordered_result_with_standard_and_moves() -> DetailedFactsResult:
    before = """
        CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 1, 'a'), (2, 2, 'b'), (3, 3, 'c');
    """
    current = """
        CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (2, 1, 'b'), (3, 2, 'z'), (1, 3, 'a');
    """
    result = compare_plan(ordered_plan(before, current))
    assert isinstance(result, DetailedFactsResult)
    assert result.facts is not None
    table = result.facts.tables[0]
    assert len(table.records) == 1
    assert table.ordered_extension is not None
    assert len(table.ordered_extension.records) == 4
    return result


def test_publish_and_reopen_standard_records_preserves_typed_null() -> None:
    store = InMemoryArtifactStore()
    published = publish_records_closure(_standard_result(), store)

    assert isinstance(published, DetailedFactsResult)
    assert published.facts is not None
    assert published.facts.records_ref is not None
    assert published.records_closure is not None
    assert len(published.records_closure.records) == 1
    entry = published.records_closure.records[0]
    assert entry.family is RecordsArtifactFamily.STANDARD
    manifest = json.loads(store.locate(entry.records_manifest_ref))
    assert "comparison_digest" not in manifest
    closure_payload = json.loads(store.locate(published.facts.records_ref))
    assert closure_payload["comparison_digest"] == published.facts.comparison_digest.value
    
    reopened = open_records_closure(store, published.facts.records_ref)
    rows = read_records_artifact(store, reopened.records[0])
    assert rows[0]["record_kind"] == "ROW_MODIFIED"
    values = rows[0]["current_values"]
    assert isinstance(values, list)
    assert isinstance(values[0], dict)
    value = values[0]["value"]
    assert isinstance(value, dict)
    assert value["kind"] == "null"
    assert reopened.comparison_digest == published.facts.comparison_digest
    assert reopened.facts_core_digest == published.facts.facts_core_digest


def test_publish_uses_independent_ordered_and_blank_artifacts() -> None:
    before = """
        CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 1, 'a'), (NULL, 2, 'x'), (2, 3, 'b');
    """
    current = """
        CREATE TABLE t (gid BIGINT NULL, no INT NULL, value VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 1, 'a'), (2, 2, 'b'), (NULL, 3, 'x');
    """
    result = compare_plan(ordered_plan(before, current))
    assert isinstance(result, DetailedFactsResult)

    published = publish_records_closure(result, InMemoryArtifactStore())
    assert isinstance(published, DetailedFactsResult)
    assert published.records_closure is not None
    assert {entry.family for entry in published.records_closure.records} == {
        RecordsArtifactFamily.ORDERED,
        RecordsArtifactFamily.BLANK,
    }


def test_unchanged_detailed_pair_publishes_a_valid_empty_closure() -> None:
    store = InMemoryArtifactStore()
    published = publish_records_closure(_standard_result(same=True), store)

    assert isinstance(published, DetailedFactsResult)
    assert published.records_closure is not None
    assert published.records_closure.records == ()
    assert published.facts is not None and published.facts.records_ref is not None
    assert open_records_closure(store, published.facts.records_ref).records == ()


def test_ref_rewrite_does_not_change_semantic_digests() -> None:
    store = InMemoryArtifactStore()
    published = publish_records_closure(_standard_result(), store)
    assert isinstance(published, DetailedFactsResult)
    assert published.records_closure is not None
    closure = published.records_closure
    entry = closure.records[0]
    rewritten_rows = ArtifactRef(
        "rewritten-records",
        entry.records_ref.media_type,
        entry.records_ref.size_bytes,
        entry.records_ref.raw_sha256,
    )
    rewritten_manifest = ArtifactRef(
        "rewritten-manifest",
        entry.records_manifest_ref.media_type,
        entry.records_manifest_ref.size_bytes,
        entry.records_manifest_ref.raw_sha256,
    )

    rewritten = rewrite_closure_refs(
        closure,
        {
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


def test_store_write_failure_is_fail_closed() -> None:
    result = publish_records_closure(_standard_result(), _RejectingStore())
    assert type(result).__name__ == "FailedResult"
    assert result.facts is None
    assert result.records_closure is None


def test_corrupt_parquet_is_rejected_before_closure_is_consumed() -> None:
    store = _CorruptingStore()
    published = publish_records_closure(_standard_result(), store)
    assert isinstance(published, DetailedFactsResult)
    assert published.records_closure is not None
    store.corrupt_ref = published.records_closure.records[0].records_ref
    assert published.facts is not None and published.facts.records_ref is not None
    with pytest.raises(ValueError, match="records"):
        open_records_closure(store, published.facts.records_ref)


@pytest.mark.parametrize("corrupt_kind", ("manifest", "closure"))
def test_manifest_or_closure_tampering_is_rejected(corrupt_kind: str) -> None:
    store = _CorruptingStore()
    published = publish_records_closure(_standard_result(), store)
    assert isinstance(published, DetailedFactsResult)
    assert published.records_closure is not None
    assert published.facts is not None and published.facts.records_ref is not None
    if corrupt_kind == "manifest":
        store.corrupt_ref = published.records_closure.records[0].records_manifest_ref
        ref = published.facts.records_ref
    else:
        store.corrupt_ref = published.facts.records_ref
        ref = published.facts.records_ref
    with pytest.raises(ValueError, match="(manifest|closure)"):
        open_records_closure(store, ref)


def test_duplicate_closure_entry_is_rejected() -> None:
    store = InMemoryArtifactStore()
    published = publish_records_closure(_standard_result(), store)
    assert isinstance(published, DetailedFactsResult)
    assert published.facts is not None and published.facts.records_ref is not None
    payload = json.loads(store.locate(published.facts.records_ref))
    payload["records"].append(payload["records"][0])
    duplicate_bytes = canonicalize_json_value(payload)
    duplicate_ref = put_with_built_ref(
        store,
        duplicate_bytes,
        artifact_id="duplicate-closure",
        media_type="application/json",
    )
    with pytest.raises(ValueError, match="repeat|closure"):
        open_records_closure(store, duplicate_ref)


def test_records_and_spool_limits_fail_closed() -> None:
    result = publish_records_closure(
        _standard_result(),
        InMemoryArtifactStore(),
        policy=RecordsPublicationPolicy(max_records_artifact_bytes=1, max_spool_bytes=1),
    )
    assert type(result).__name__ == "FailedResult"
    assert result.facts is None
    assert result.records_closure is None


def test_reopen_rejects_records_over_per_table_limit_before_materialization() -> None:
    before = """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 'before'), (2, 'before');
    """
    current = """
        CREATE TABLE t (id INT NOT NULL PRIMARY KEY, note VARCHAR(8) NULL);
        INSERT INTO t VALUES (1, 'current'), (2, 'current');
    """
    result = compare_plan(standard_plan(before, current))
    assert isinstance(result, DetailedFactsResult)
    store = InMemoryArtifactStore()
    published = publish_records_closure(result, store)
    assert isinstance(published, DetailedFactsResult)
    assert published.facts is not None and published.facts.records_ref is not None

    with pytest.raises(ValueError, match="per-table limit"):
        open_records_closure(
            store,
            published.facts.records_ref,
            policy=RecordsPublicationPolicy(max_records_per_table=1),
        )


def test_publish_rejects_combined_record_families_over_table_limit() -> None:
    result = publish_records_closure(
        _ordered_result_with_standard_and_moves(),
        InMemoryArtifactStore(),
        policy=RecordsPublicationPolicy(max_records_per_table=4),
    )

    assert type(result).__name__ == "FailedResult"
    assert result.facts is None
    assert result.records_closure is None


def test_reopen_rejects_combined_record_families_over_table_limit() -> None:
    store = InMemoryArtifactStore()
    published = publish_records_closure(_ordered_result_with_standard_and_moves(), store)
    assert isinstance(published, DetailedFactsResult)
    assert published.facts is not None and published.facts.records_ref is not None

    with pytest.raises(ValueError, match="per-table limit"):
        open_records_closure(
            store,
            published.facts.records_ref,
            policy=RecordsPublicationPolicy(max_records_per_table=4),
        )


@pytest.mark.parametrize(
    "policy",
    (
        RecordsPublicationPolicy(max_manifest_json_bytes=1),
        RecordsPublicationPolicy(max_closure_json_bytes=1),
    ),
)
def test_manifest_and_closure_limits_fail_closed(policy: RecordsPublicationPolicy) -> None:
    result = publish_records_closure(_standard_result(), InMemoryArtifactStore(), policy=policy)
    assert type(result).__name__ == "FailedResult"
    assert result.facts is None
    assert result.records_closure is None


def test_cancellation_returns_no_facts_or_closure() -> None:
    def cancel() -> None:
        raise RecordsCancelled("deadline")

    result = publish_records_closure(
        _standard_result(),
        InMemoryArtifactStore(),
        context=RecordsPublicationContext(checkpoint=cancel),
    )
    assert isinstance(result, CancelledResult)
    assert result.facts is None
    assert result.records_closure is None


@pytest.mark.parametrize(
    "detail_policy",
    (
        RecordsDetailPolicy.COUNTS_ONLY,
        RecordsDetailPolicy.CHANGED_COLUMNS,
        RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES,
    ),
)
def test_detail_policy_is_manifested_without_changing_semantic_digest(
    detail_policy: RecordsDetailPolicy,
) -> None:
    source = _standard_result()
    result = publish_records_closure(
        source,
        InMemoryArtifactStore(),
        detail_policy=detail_policy,
    )
    assert isinstance(result, DetailedFactsResult)
    assert source.facts is not None
    assert result.facts is not None and result.records_closure is not None
    assert result.facts.comparison_digest == source.facts.comparison_digest
