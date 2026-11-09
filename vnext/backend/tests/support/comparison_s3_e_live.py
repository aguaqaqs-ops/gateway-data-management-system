"""Small canonical Arrow inputs for live comparison and records consumers."""

from __future__ import annotations

from contextlib import closing
from dataclasses import replace

from gateway_backend.artifacts import ArtifactStorePort
from gateway_backend.capabilities.comparison import (
    BoundSnapshotInput, ComparisonPlan, ComparisonRequest, DetailedFactsResult,
    RecordsDetailPolicy, plan_comparison,
)
from gateway_backend.capabilities.comparison.artifacts import (
    RecordsPublicationContext, RecordsPublicationPolicy, publish_records_closure_arrow,
)
from gateway_backend.capabilities.comparison.production import NativeComparison, compare_plan_native
from gateway_backend.capabilities.snapshot_materialization import snapshot_table_from_arrow
from gateway_backend.capabilities.snapshot_materialization._reader import BoundSnapshotTableReader
from gateway_backend.capabilities.table_rules.contracts import TableArtifactScope
from tests.support.comparison_s3_c_inputs import bound, canonical_stream
from tests.support.table_rules import comparison_ruleset_for, ordered_record, standard_rule_record


def canonical_bound(sql: str) -> BoundSnapshotInput:
    source = bound(sql)
    assert source.table_set is not None
    tables = []
    for table in source.table_set.tables:
        assert isinstance(table.reader, BoundSnapshotTableReader)
        with closing(canonical_stream(table)) as stream:
            backing = stream.read_all()
        tables.append(snapshot_table_from_arrow(
            table.descriptor, backing, table.reader.source_descriptor(),
            ordered=table.ordered_metadata,
        ))
    return replace(source, table_set=replace(source.table_set, tables=tuple(tables)))


def native_product(
    before_sql: str,
    current_sql: str,
    *,
    ordered: bool = False,
    compare_excluded_columns: tuple[str, ...] = (),
    artifact_scope: TableArtifactScope = TableArtifactScope.ALL_CHANGES,
    detail_policy: RecordsDetailPolicy = RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES,
) -> NativeComparison:
    before, current = canonical_bound(before_sql), canonical_bound(current_sql)
    rule = (
        ordered_record(r"^t$", compare_excluded_columns=compare_excluded_columns)
        if ordered else standard_rule_record(
            "t", compare_excluded_columns=compare_excluded_columns,
            artifact_scope=artifact_scope,
        )
    )
    planned = plan_comparison(ComparisonRequest(
        pair_id="s3-e-live-consumer", before=before, current=current,
        rule_set=comparison_ruleset_for(rule),
        options=() if detail_policy is RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES else (
            ("row_diff_detail_policy", detail_policy.value),
        ),
    ))
    assert isinstance(planned, ComparisonPlan)
    return compare_plan_native(planned)


def publish_product(
    product: NativeComparison,
    store: ArtifactStorePort,
    *,
    policy: RecordsPublicationPolicy | None = None,
    context: RecordsPublicationContext | None = None,
    detail_policy: RecordsDetailPolicy = RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES,
) -> DetailedFactsResult:
    assert isinstance(product.result, DetailedFactsResult)
    return publish_records_closure_arrow(
        product.result, product.handles, store, policy=policy, context=context,
        detail_policy=detail_policy,
    )
