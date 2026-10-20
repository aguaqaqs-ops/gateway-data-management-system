"""Table level facts for an explicitly selected dataset replacement."""

from __future__ import annotations

from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.comparison.contracts import (
    ComparisonFacts,
    ComparisonMode,
    ComparisonPlan,
    ComparisonSummary,
    ComparisonTableFact,
    ComparisonTableStatus,
    DatasetReplacementResult,
    PairResultStatus,
)
from gateway_backend.capabilities.comparison.row_encoding import (
    _summary_payload,
    _table_digest_payload,
    _with_table_digest,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    COMPARISON_PROJECTION_CONTRACT_VERSION,
    SCALAR_ENCODING_VERSION,
    SnapshotTableDescriptor,
)

DATASET_REPLACEMENT_ALGORITHM_VERSION = "dataset-replacement/v1"


def compare_dataset_replacement(plan: ComparisonPlan) -> DatasetReplacementResult:
    if type(plan) is not ComparisonPlan:
        raise TypeError("plan must be ComparisonPlan")
    if plan.mode is not ComparisonMode.DATASET_REPLACEMENT:
        raise ValueError("replacement comparison requires DATASET_REPLACEMENT mode")

    tables = tuple(
        _replacement_table_fact(task.table_name, task.before_descriptor, task.current_descriptor)
        for task in plan.tasks
    )
    table_payloads = [_table_digest_payload(item) for item in tables]
    summary = ComparisonSummary(
        status=PairResultStatus.CHANGED,
        table_count=len(tables),
        unchanged_table_count=0,
        changed_table_count=len(tables),
        added_table_count=sum(item.status is ComparisonTableStatus.ADDED_TABLE for item in tables),
        deleted_table_count=sum(item.status is ComparisonTableStatus.DELETED_TABLE for item in tables),
        schema_changed_table_count=0,
        degraded_table_count=0,
        row_added_count=sum(item.row_added_count for item in tables),
        row_deleted_count=sum(item.row_deleted_count for item in tables),
        row_modified_count=0,
        suppressed_added_count=0,
        suppressed_deleted_count=0,
        diagnostics_count=1,
    )
    core_digest = raw_blob_digest(
        canonicalize_json_value(
            {
                "algorithm_version": DATASET_REPLACEMENT_ALGORITHM_VERSION,
                "kind": "comparison-facts-core",
                "summary": _summary_payload(summary),
                "tables": table_payloads,
            }
        )
    )
    ruleset_digest = plan.rule_set.ruleset_digest
    if ruleset_digest is None:
        raise ValueError("comparison ruleset digest is missing")
    envelope = {
        "algorithm_version": DATASET_REPLACEMENT_ALGORITHM_VERSION,
        "before_snapshot_digest": plan.before.snapshot.snapshot_digest.value,
        "comparison_mode": ComparisonMode.DATASET_REPLACEMENT.value,
        "comparison_options": [[key, value] for key, value in plan.options],
        "contract_versions": [[key, value] for key, value in plan.contract_versions],
        "facts_core_digest": core_digest.value,
        "kind": "comparison",
        "current_snapshot_digest": plan.current.snapshot.snapshot_digest.value,
        "projection_contract_version": COMPARISON_PROJECTION_CONTRACT_VERSION,
        "ruleset_digest": ruleset_digest.value,
        "scalar_encoding_version": SCALAR_ENCODING_VERSION,
    }
    comparison_digest = raw_blob_digest(canonicalize_json_value(envelope))
    facts = ComparisonFacts(
        comparison_digest=comparison_digest,
        facts_core_digest=core_digest,
        comparison_contract_version=str(
            dict(plan.contract_versions).get("comparison_contract_version", "unknown")
        ),
        projection_contract_version=COMPARISON_PROJECTION_CONTRACT_VERSION,
        scalar_encoding_version=SCALAR_ENCODING_VERSION,
        before_snapshot_digest=plan.before.snapshot.snapshot_digest,
        current_snapshot_digest=plan.current.snapshot.snapshot_digest,
        comparison_mode=ComparisonMode.DATASET_REPLACEMENT,
        direction="BEFORE_TO_CURRENT",
        summary=summary,
        tables=tables,
        diagnostics=("DATASET_REPLACEMENT",),
    )
    return DatasetReplacementResult(
        pair_id=plan.pair_id,
        status=PairResultStatus.CHANGED,
        facts=facts,
        diagnostics=facts.diagnostics,
    )


def _replacement_table_fact(
    table_name: str,
    before: SnapshotTableDescriptor | None,
    current: SnapshotTableDescriptor | None,
) -> ComparisonTableFact:
    before_descriptor = before
    current_descriptor = current
    if before_descriptor is None and current_descriptor is None:
        raise ValueError("replacement table must exist on at least one side")
    before_rows = 0 if before_descriptor is None else before_descriptor.row_count
    current_rows = 0 if current_descriptor is None else current_descriptor.row_count
    if before_descriptor is None:
        status = ComparisonTableStatus.ADDED_TABLE
    elif current_descriptor is None:
        status = ComparisonTableStatus.DELETED_TABLE
    else:
        status = ComparisonTableStatus.REPLACED
    fact = ComparisonTableFact(
        table_name=table_name,
        status=status,
        before_descriptor=before_descriptor,
        current_descriptor=current_descriptor,
        row_count_before=None if before_descriptor is None else before_rows,
        row_count_current=None if current_descriptor is None else current_rows,
        row_added_count=current_rows,
        row_deleted_count=before_rows,
        content_changed=True,
    )
    return _with_table_digest(fact)

