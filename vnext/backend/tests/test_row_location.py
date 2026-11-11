"""Final-file position, occurrence and missing-snapshot context authority."""
from __future__ import annotations

from contextlib import closing
from dataclasses import replace
import json
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq  # type: ignore[import-untyped]
import pytest

from gateway_shared_kernel import raw_blob_digest
from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore
from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
from gateway_backend.capabilities.comparison.contracts import RecordsArtifactFamily, ComparisonPlan, ComparisonRequest
from gateway_backend.capabilities.comparison import plan_comparison
from gateway_backend.capabilities.comparison.production import compare_plan_native
from gateway_backend.capabilities.row_location.producer import LOCATOR_SCHEMA, prepare_row_locations, publish_row_locations
from gateway_backend.capabilities.snapshot_materialization import export_snapshot_table_parquet
from gateway_backend.capabilities.surface_assembly.contracts import SurfaceTableRefs
from tests.support.comparison_cache_inputs import complete_canonical_bound
from tests.support.comparison_s3_c_inputs import plan
from tests.support.table_rules import comparison_ruleset_for, fallback_record
from gateway_backend.capabilities.table_rules.contracts import CanonicalKeyPolicy
from tests.support.comparison_s3_e_live import canonical_bound, publish_product


_CASES = (
    ("keyed", "CREATE TABLE t (id BIGINT PRIMARY KEY, gid BIGINT, note TEXT);",
     "(1,7,'old'),(2,8,'delete')", "(1,7,'new'),(3,9,'add')"),
    ("keyless", "CREATE TABLE t (id BIGINT, gid BIGINT, note TEXT);",
     "(1,7,'same')", "(1,7,'same'),(1,7,'same'),(1,7,'same')"),
    ("mixed", "CREATE TABLE t (id BIGINT PRIMARY KEY, gid BIGINT, note TEXT, u BIGINT UNSIGNED, "
     "d DECIMAL(10,2), f FLOAT, g DOUBLE, e ENUM('甲','乙'), s SET('a','b'), b BINARY(2), n INT NULL);",
     "(1,7,'old',18446744073709551615,12.34,1.5,2.5,'甲','a,b',X'00ff',NULL)",
     "(1,7,'new',18446744073709551615,12.34,1.5,2.5,'甲','a,b',X'00ff',NULL)"),
)


def _rewrite(store: InMemoryArtifactStore, ref: ArtifactRef, *, corrupt: bool = False) -> ArtifactRef:
    table = pq.read_table(pa.BufferReader(store.locate(ref)))
    indices = list(reversed(range(table.num_rows)))
    if corrupt and len(indices) > 1:
        indices[-1] = indices[0]
    table = table.take(pa.array(indices, type=pa.int64()))
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink, row_group_size=1)
    raw = sink.getvalue().to_pybytes()
    changed = replace(ref, artifact_id=build_artifact_id(ArtifactLocation.EXPORT, "test-reordered-file", raw_blob_digest(raw).value),
        raw_sha256=raw_blob_digest(raw), size_bytes=len(raw))
    return store.put(raw, changed)


@pytest.mark.parametrize(("label", "ddl", "before_values", "current_values"), _CASES)
@pytest.mark.parametrize("include_before", (False, True))
def test_locator_uses_final_row_groups_and_typed_missing_side_context(
    label: str, ddl: str, before_values: str, current_values: str, include_before: bool,
) -> None:
    before = complete_canonical_bound(canonical_bound(ddl + "INSERT INTO t VALUES " + before_values + ";"))
    current = complete_canonical_bound(canonical_bound(ddl + "INSERT INTO t VALUES " + current_values + ";"))
    if label == "keyless":
        def keyless(source: Any) -> Any:
            fact, = source.storage_facts
            return replace(source, storage_facts=(replace(fact, storage_rule_view=replace(
                fact.storage_rule_view, canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS)),))
        before, current = keyless(before), keyless(current)
    planned = (plan_comparison(ComparisonRequest(pair_id="keyless-locator", before=before, current=current,
        rule_set=comparison_ruleset_for(fallback_record()))) if label == "keyless" else plan(before, current))
    assert isinstance(planned, ComparisonPlan)
    store = InMemoryArtifactStore()
    task, = planned.tasks
    assert task.before_table is not None and task.current_table is not None
    before_ref: ArtifactRef | None = export_snapshot_table_parquet(task.before_table, store=store, repository_id="replacement-fixture")
    current_ref = export_snapshot_table_parquet(task.current_table, store=store, repository_id="replacement-fixture")
    assert before_ref is not None
    before_ref = _rewrite(store, before_ref) if include_before else None
    current_ref = _rewrite(store, current_ref)
    with closing(compare_plan_native(planned)) as product:
        published = publish_product(product, store)
        assert published.records_closure is not None
        entry = next(e for e in published.records_closure.records if e.family is RecordsArtifactFamily.STANDARD)
        located = prepare_row_locations(task, entry, product.handles["t"],
            SurfaceTableRefs(before_ref, current_ref), store, filter_column="gid")
        locator_ref = publish_row_locations(located, store, filtered=True)
        assert locator_ref is not None
        file = pq.ParquetFile(pa.BufferReader(store.locate(locator_ref)))
        assert file.schema_arrow.equals(LOCATOR_SCHEMA, check_metadata=True)
        rows: list[dict[str, Any]] = file.read().to_pylist()
        assert [r["row_identity"] for r in rows] == sorted(r["row_identity"] for r in rows)
        records = {r.row_identity: r for r in located.records}
        assert len(rows) == (3 if label == "keyed" else 2 if label == "keyless" else 1)
        final_tables = {"current": pq.read_table(pa.BufferReader(store.locate(current_ref))).to_pylist()}
        if before_ref is not None:
            final_tables["before"] = pq.read_table(pa.BufferReader(store.locate(before_ref))).to_pylist()
        for row in rows:
            record = records["sha256:" + row["row_identity"].hex()]
            for side in ("before", "current"):
                values = getattr(record, side)
                index = row[side + "_row_index"]
                context = row[side + "_filter_context_json"]
                if values is None:
                    assert index is None and context is None
                elif side in final_tables:
                    assert type(index) is int and context is None
                    assert int(final_tables[side][index]["gid"]) == values["gid"]
                else:
                    assert index is None and json.loads(context) == values
        if label == "keyless":
            assert {r["current_row_index"] for r in rows} == {1, 2}
            assert all(r["before_row_index"] is None and r["before_filter_context_json"] is None for r in rows)


def test_locator_rejects_ambiguous_or_impossible_final_row_matches() -> None:
    ddl = "CREATE TABLE t (id BIGINT PRIMARY KEY, gid BIGINT, note TEXT);"
    before = complete_canonical_bound(canonical_bound(ddl + "INSERT INTO t VALUES (1,7,'old'),(2,8,'same');"))
    current = complete_canonical_bound(canonical_bound(ddl + "INSERT INTO t VALUES (1,7,'new'),(2,8,'same');"))
    planned = plan(before, current)
    task, = planned.tasks
    assert task.current_table is not None
    store = InMemoryArtifactStore()
    exported = export_snapshot_table_parquet(task.current_table, store=store, repository_id="replacement-fixture")
    corrupt = _rewrite(store, exported, corrupt=True)
    with closing(compare_plan_native(planned)) as product:
        published = publish_product(product, store)
        assert published.records_closure is not None
        entry, = published.records_closure.records
        with pytest.raises(ValueError, match="no unique final/canonical row|multiple physical rows"):
            prepare_row_locations(task, entry, product.handles["t"], SurfaceTableRefs(None, corrupt), store, filter_column="gid")
