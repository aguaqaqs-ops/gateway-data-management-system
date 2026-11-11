"""One complete semantic task projection for native requests and cache identity.

Authority (operation, commit, reader and artifact paths) stays with the caller.
All dataclass fields are semantic by default; only the explicit display fields
below are removed. New task/plan fields require classification before reuse.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.comparison.contracts import (
    standard_identity_is_keyless,
    ArtifactScope, ComparisonMode, ComparisonPlan, RecordsDetailPolicy,
    SchemaEvolution, TableComparisonTask, COMPARISON_CONTRACT_VERSION,
    RECORDS_ARTIFACT_CONTRACT_VERSION, RECORDS_CLOSURE_CONTRACT_VERSION,
    ORDERED_DIFF_CONTRACT_VERSION, BLANK_COMPARISON_CONTRACT_VERSION,
)
from gateway_backend.capabilities.comparison.errors import StandardComparisonError
from gateway_backend.capabilities.comparison.row_encoding import (
    _can_table_early_exit, _is_columns_added, _schema_changes_from_view,
    _schema_diagnostics, _schema_view,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BlankRowProvenance, DegradedReason, MaterializationStage, SnapshotTable,
    SnapshotTableDescriptor, SnapshotColumnDescriptor,
    SCALAR_ENCODING_VERSION, COMPARISON_PROJECTION_CONTRACT_VERSION,
)

from gateway_backend.capabilities.snapshot_materialization import ArrowSnapshotTableReader
from gateway_backend.capabilities.comparison.standard import STANDARD_COMPARISON_ALGORITHM_VERSION
from gateway_backend.capabilities.comparison.native import comparison_format_versions
from gateway_backend.capabilities.table_rules.contracts import CanonicalKeyPolicy

TABLE_CACHE_FORMAT = "comparison-table-cache/v1"
TASK_INPUT_VERSION = "comparison-table-task/v1"
MAX_TASK_INPUT_BYTES = 16 * 1024**2
_TASK_FIELDS = frozenset({
    "table_name", "before_descriptor", "current_descriptor", "before_table",
    "current_table", "artifact_scope", "policy",
})
_PLAN_FIELDS = frozenset({
    "pair_id", "before", "current", "rule_set", "mode", "tasks", "diagnostics",
    "options", "contract_versions",
})
_DISPLAY_FIELDS: dict[type[Any], frozenset[str]] = {
    SnapshotTableDescriptor: frozenset({"display_table_name"}),
    SnapshotColumnDescriptor: frozenset({"display_name"}),
}


def semantic_value(value: Any) -> Any:
    """Preserve every semantic field, including names inside schema/rules."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, DigestRef):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        omitted = _DISPLAY_FIELDS.get(type(value), frozenset())
        return {field.name: semantic_value(getattr(value, field.name))
                for field in fields(value) if field.name not in omitted}
    if isinstance(value, tuple | list):
        return [semantic_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): semantic_value(item) for key, item in value.items()}
    if value is None or type(value) in {str, int, bool}:
        return value
    raise ValueError(f"unclassified semantic value: {type(value).__name__}")


def _fits(value: Any, remaining: list[int], depth: int = 0) -> bool:
    remaining[0] -= 4096
    if depth > 24 or remaining[0] < 0:
        return False
    if isinstance(value, str | bytes):
        remaining[0] -= len(value) * 256
    elif isinstance(value, Enum):
        return _fits(value.value, remaining, depth + 1)
    elif is_dataclass(value) and not isinstance(value, type):
        return all(_fits(getattr(value, f.name), remaining, depth + 1) for f in fields(value))
    elif isinstance(value, tuple | list):
        return all(_fits(item, remaining, depth + 1) for item in value)
    elif isinstance(value, dict):
        return all(_fits(key, remaining, depth + 1) and _fits(item, remaining, depth + 1)
                   for key, item in value.items())
    elif value is not None and type(value) not in {int, bool}:
        return False
    return remaining[0] >= 0


@dataclass(frozen=True, slots=True)
class TableTaskInputV1:
    """Fields are semantic; resources and current publication bindings are absent.

    ``native_policy`` is the exact request consumed by the Rust algorithm.
    ``semantic_jcs`` additionally binds both descriptors, storage facts, resolved
    policy/rules and versions, diagnostics, detail and server-resolved scope.
    """
    kind: str
    native_kind: str
    native_policy_jcs: bytes
    semantic_jcs: bytes
    detail_policy: RecordsDetailPolicy

    def native_policy(self) -> str:
        return self.native_policy_jcs.decode("utf-8")


@dataclass(frozen=True, slots=True)
class TableTaskIdentity:
    repository_id: str
    artifact_scope: str
    task_digest: DigestRef
    task_input: TableTaskInputV1


@dataclass(frozen=True, slots=True)
class NotCacheable:
    reason: str


def standard_policy(task: TableComparisonTask, schema: Any) -> dict[str, object]:
    policy = task.policy
    assert policy is not None
    return {
        "selected_columns": list(schema.selected),
        "effective_key_before": list(schema.before_key),
        "effective_key_current": list(schema.current_key),
        "compare_excluded_columns": list(policy.compare_excluded_columns),
        "incompatible_columns": list(schema.incompatible),
        "emit_add_delete": task.artifact_scope is ArtifactScope.ALL_CHANGES,
        "columns_added": _is_columns_added(schema),
        "mode": ("keyless" if standard_identity_is_keyless(schema.before_key, schema.current_key,
                 policy.allow_keyless_key_transition) else "keyed"),
        "schema_diagnostics": _schema_diagnostics(schema, policy),
    }


def standard_identity_policy(task: TableComparisonTask) -> dict[str, object]:
    """Return the same standard codec policy used by this comparison task."""
    before, current, policy = task.before_descriptor, task.current_descriptor, task.policy
    if before is None or current is None or policy is None:
        raise ValueError("standard identity policy requires both descriptors and its comparison policy")
    return standard_policy(task, _schema_view(before, current, policy))


def ordered_policy(task: TableComparisonTask, schema: Any, *, unchanged: bool = False) -> dict[str, object]:
    policy = task.policy
    assert policy is not None and policy.ordered_policy is not None
    ordered = policy.ordered_policy
    before, current = task.before_descriptor, task.current_descriptor
    assert before is not None and current is not None

    def provenance(table: SnapshotTable | None) -> str:
        if table is None or table.ordered_metadata is None:
            raise StandardComparisonError("ORDERED_PROVENANCE_MISSING")
        value = table.ordered_metadata.blank_provenance
        if value is BlankRowProvenance.SOURCE_MISSING_STABLE_KEY:
            return "source"
        if value is BlankRowProvenance.CANONICAL_PSEUDO_GID:
            return "canonical"
        raise StandardComparisonError("ORDERED_PROVENANCE_INVALID")

    changes = _schema_changes_from_view(schema, policy)
    return {
        **standard_policy(task, schema),
        "table_name": task.table_name,
        "policy_version": ordered.policy_version,
        "policy_digest": None if ordered.policy_digest is None else ordered.policy_digest.value,
        "value_columns": list(ordered.value_columns),
        "digest_value_columns": list(ordered.value_columns),
        "schema_changed": (before.business_schema_digest != current.business_schema_digest
                           and changes.schema_evolution is not SchemaEvolution.COLUMNS_ADDED),
        "raw_content_changed": before.raw_content_digest != current.raw_content_digest,
        "before_blank_provenance": provenance(task.current_table if unchanged else task.before_table),
        "current_blank_provenance": provenance(task.current_table),
        "schema_changes": {
            "before_only_columns": list(changes.before_only_columns),
            "current_only_columns": list(changes.current_only_columns),
            "selected_columns": list(changes.selected_columns),
            "effective_compare_key_before": list(changes.effective_compare_key_before),
            "effective_compare_key_current": list(changes.effective_compare_key_current),
            "effective_compare_key_changed": changes.effective_compare_key_changed,
            "incompatible_columns": list(changes.incompatible_columns),
            "change_source": None if changes.change_source is None else changes.change_source.value,
        },
    }


def build_table_task_input(
    plan: ComparisonPlan, task: TableComparisonTask, *, include_identity: bool = True,
) -> TableTaskInputV1:
    """The native request and the persistent key consume this same projection."""
    if ({field.name for field in fields(TableComparisonTask)} != _TASK_FIELDS
            or {field.name for field in fields(ComparisonPlan)} != _PLAN_FIELDS):
        raise ValueError("new task/plan fields need semantic classification")
    before, current, policy = task.before_descriptor, task.current_descriptor, task.policy
    detail_value = dict(plan.options).get(
        "row_diff_detail_policy", RecordsDetailPolicy.FULL_BEFORE_AFTER_VALUES.value,
    )
    if not isinstance(detail_value, str):
        raise ValueError("row_diff_detail_policy is invalid")
    detail = RecordsDetailPolicy(detail_value)
    kind, native_kind, request = "metadata", "standard", {}
    if before is not None and current is not None and policy is not None:
        schema = _schema_view(before, current, policy)
        changes = _schema_changes_from_view(schema, policy)
        if policy.comparison_role in {"BROWSE_ONLY", "SNAPSHOT_ONLY"}:
            if changes.schema_evolution is SchemaEvolution.COLUMNS_ADDED:
                kind = "nonrecord-shared-multiset"
                request = standard_policy(task, schema)
                request.update(mode="keyless", effective_key_before=[], effective_key_current=[],
                               compare_excluded_columns=[], emit_add_delete=False,
                               columns_added=True, schema_diagnostics=[])
        elif policy.ordered_policy is not None:
            unchanged = _can_table_early_exit(before, current, policy)
            kind = "ordered-current-summary" if unchanged else "row-comparison"
            native_kind = "ordered"
            request = ordered_policy(task, schema, unchanged=unchanged)
        elif not _can_table_early_exit(before, current, policy) and not (
            schema.key_invalid or schema.key_changed or not schema.selected
        ):
            kind = "row-comparison"
            request = standard_policy(task, schema)
    if not include_identity:
        return TableTaskInputV1(kind, native_kind, canonicalize_json_value(request), b"", detail)
    projection = {
        "version": TASK_INPUT_VERSION, "cache_format": TABLE_CACHE_FORMAT,
        "versions": {
            "comparison": COMPARISON_CONTRACT_VERSION,
            "standard_algorithm": STANDARD_COMPARISON_ALGORITHM_VERSION,
            "ordered_contract": ORDERED_DIFF_CONTRACT_VERSION,
            "blank_contract": BLANK_COMPARISON_CONTRACT_VERSION,
            "records": RECORDS_ARTIFACT_CONTRACT_VERSION,
            "records_closure": RECORDS_CLOSURE_CONTRACT_VERSION,
            "projection": COMPARISON_PROJECTION_CONTRACT_VERSION,
            "scalar": SCALAR_ENCODING_VERSION, "native_formats": list(comparison_format_versions()),
        },
        "direction": "BEFORE_TO_CURRENT", "kind": kind,
        "before": semantic_value(before), "current": semantic_value(current),
        "business_schema_before": None if before is None else before.business_schema_digest.value,
        "business_schema_current": None if current is None else current.business_schema_digest.value,
        "before_ordered": semantic_value(None if native_kind != "ordered" or task.before_table is None
                                         else task.before_table.ordered_metadata),
        "current_ordered": semantic_value(None if native_kind != "ordered" or task.current_table is None
                                          else task.current_table.ordered_metadata),
        "policy": semantic_value(policy), "rules": semantic_value(plan.rule_set),
        "mode": plan.mode.value, "options": semantic_value(plan.options),
        "contracts": semantic_value(plan.contract_versions), "diagnostics": list(plan.diagnostics),
        "artifact_scope": task.artifact_scope.value, "native_policy": request,
        "detail_policy": detail.value,
    }
    return TableTaskInputV1(kind, native_kind, canonicalize_json_value(request),
                            canonicalize_json_value(projection), detail)


def _complete_side(task: TableComparisonTask, *, before: bool) -> bool:
    descriptor = task.before_descriptor if before else task.current_descriptor
    table = task.before_table if before else task.current_table
    policy = task.policy
    facts = None if policy is None else (policy.storage_facts_before if before else policy.storage_facts_current)
    if descriptor is None:
        return facts is None
    if (descriptor.materialization_stage is not MaterializationStage.FINAL
            or descriptor.raw_content_digest is None
            or descriptor.degraded_reason not in {None, DegradedReason.KEYLESS}
            or facts is None or facts.canonical_schema_digest is None
            or facts.raw_content_digest != descriptor.raw_content_digest
            or not facts.storage_projection_version):
        return False
    view = facts.storage_rule_view
    if (view.canonical_table != descriptor.table_name
            or (set(view.retained_columns) | set(view.structural_columns)) != {column.name for column in descriptor.columns}):
        return False
    if view.canonical_key_policy is CanonicalKeyPolicy.EXPLICIT:
        if not view.canonical_key_columns or view.canonical_key_columns != descriptor.primary_key_columns:
            return False
    elif view.canonical_key_policy in {CanonicalKeyPolicy.DDL_PRIMARY_KEY, CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS}:
        if view.canonical_key_columns and view.canonical_key_columns != descriptor.primary_key_columns:
            return False
        if view.canonical_key_policy is CanonicalKeyPolicy.DDL_PRIMARY_KEY and not descriptor.primary_key_columns:
            return False
    elif view.canonical_key_policy is CanonicalKeyPolicy.EXPLICIT_KEYLESS:
        if view.canonical_key_columns or descriptor.primary_key_columns:
            return False
    else:
        return False
    # Metadata-only exact-commit descriptions have no reader. A present reader
    # must carry the original canonical owner's successful verification proof.
    if table is not None and table.reader is not None:
        reader = table.reader
        if not isinstance(reader, ArrowSnapshotTableReader) or not (
            reader.canonical_comparison_verified or reader.canonical_artifact_read_verified
            or reader.canonical_committed_read_verified
        ):
            return False
    return True


def build_table_task_identity(
    plan: ComparisonPlan, task: TableComparisonTask, *, repository_id: str,
    artifact_scope: str,
) -> TableTaskIdentity | NotCacheable:
    """Caller prepays MAX_TASK_INPUT_BYTES; failure disables only retention."""
    if not repository_id or not artifact_scope or plan.mode is not ComparisonMode.DETAILED:
        return NotCacheable("scope-or-mode")
    if not _fits((task.before_descriptor, task.current_descriptor, task.policy, plan.rule_set,
                  plan.options, plan.contract_versions, plan.diagnostics), [MAX_TASK_INPUT_BYTES]):
        return NotCacheable("metadata-budget")
    if not _complete_side(task, before=True) or not _complete_side(task, before=False):
        return NotCacheable("incomplete-canonical-binding")
    try:
        value = build_table_task_input(plan, task)
    except (ValueError, StandardComparisonError):
        return NotCacheable("incomplete-semantics")
    if value.kind == "metadata":
        return NotCacheable("metadata-only")
    payload = canonicalize_json_value({"repository_id": repository_id,
        "artifact_scope": artifact_scope, "input": value.semantic_jcs.decode("utf-8")})
    if len(payload) * 8 + 4096 > MAX_TASK_INPUT_BYTES:
        return NotCacheable("metadata-budget")
    return TableTaskIdentity(repository_id, artifact_scope,
        raw_blob_digest(b"comparison-table-cache/v1\x00" + payload), value)
