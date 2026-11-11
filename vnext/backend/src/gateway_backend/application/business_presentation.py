"""Feed real comparison, location and Risk evidence to the navigation owner."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
from typing import cast

from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_backend.artifacts import ArtifactStorePort
from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
from gateway_backend.artifacts.store import put_with_built_ref
from gateway_backend.capabilities.business_navigation import (
    NavigationEvidence, NavigationRow, NavigationSide, NavigationTable, build_navigation,
    identity_excluded_sides, reduce_table_risks,
)
from gateway_backend.capabilities.business_navigation.contracts import FILTER_IDENTITY_COLUMNS, Scalar
from gateway_backend.capabilities.business_navigation.producer import maximum_risk
from gateway_backend.capabilities.comparison import native
from gateway_backend.capabilities.comparison.contracts import (
    BoundSnapshotInput, ComparisonFacts, ComparisonMode, ComparisonPlan, ComparisonRecordsClosure,
    ComparisonTableStatus, RecordsArtifactFamily,
)
from gateway_backend.capabilities.risk_evaluation.contracts import RiskAnnotation, RiskLevel, RiskTargetType
from gateway_backend.capabilities.row_location.producer import (
    RowLocationResult, prepare_row_locations, publish_row_locations, identity_batches,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import SnapshotTable
from gateway_backend.capabilities.surface_assembly.contracts import SurfaceArtifactIndexEntry, SurfaceProjectionRef
from gateway_backend.capabilities.table_access import current_kernel_context
from gateway_backend.capabilities.table_presentation.metadata import PresentationMetadata, TablePresentation
from gateway_backend.capabilities.table_presentation.resolver import table_display_name

NAVIGATION_ROW_TABLES = frozenset({"net_cfg", "device", "app_cfg", *FILTER_IDENTITY_COLUMNS})
_REGISTRY_COLUMNS = {
    "net_cfg": ("board", "link_no", "tab_num", "exe", "channel_desc", "protocol_name"),
    "device": ("dev_addr", "gid", "description"),
    "app_cfg": ("app_name", "table_cfg"),
}


class RiskAttribution:
    """Reduce typed transient outcomes while their owning evaluation is live."""
    def __init__(self) -> None:
        self.table_events: list[RiskAnnotation] = []
        self.rows: dict[str, dict[str, RiskLevel]] = {}
        self.complete: dict[str, bool] = {}
        self.any_risk: dict[str, bool] = {}

    def observe(self, name: str, annotations: tuple[RiskAnnotation, ...], complete: bool) -> None:
        context = current_kernel_context()
        if context is None or name in self.complete:
            raise ValueError("risk attribution requires one live outcome per table")
        # Existing annotation objects stay with Risk. Charge our retained map,
        # tuple references and native row digest strings before adding them.
        context.resources.enter_context(context.memory.reserve(len(annotations) * 1024 + 4096))
        self.complete[name] = complete
        self.any_risk[name] = bool(annotations)
        levels: dict[str, RiskLevel] = {}
        for annotation in annotations:
            context.checkpoint()
            target = annotation.target
            if target.target_type in {RiskTargetType.TABLE, RiskTargetType.COMPARISON}:
                self.table_events.append(annotation)
            else:
                for identity in (target.row_identity, target.before_row_identity, target.current_row_identity):
                    if identity is not None:
                        level = maximum_risk(levels.get(identity.value), annotation.risk_level)
                        assert level is not None
                        levels[identity.value] = level
        self.rows[name] = levels


def navigation_row_demands(
    plan: ComparisonPlan, same_complete: Callable[[BoundSnapshotInput, BoundSnapshotInput, str], bool],
) -> tuple[SnapshotTable, ...]:
    """Canonical row demands are separate from export/cache/comparison demands."""
    if plan.before.table_set is None or plan.current.table_set is None:
        raise ValueError("navigation requires canonical table sets")
    demands = []
    for before, bound in ((True, plan.before), (False, plan.current)):
        assert bound.table_set is not None
        for table in bound.table_set.tables:
            name = table.descriptor.table_name
            if name in NAVIGATION_ROW_TABLES and not (
                before and same_complete(plan.before, plan.current, name)
            ):
                demands.append(table)
    return tuple(demands)


def _side(table: SnapshotTable | None, presentation: TablePresentation | None) -> NavigationSide | None:
    if table is None:
        return None
    descriptor = table.descriptor
    names = tuple(column.name for column in descriptor.columns)
    # Keyed whole-row frames request only the shared codec and no occurrence
    # state. They establish canonical whole-row representative ordering.
    policy = canonicalize_json_value({"mode": "keyed", "selected_columns": list(names),
        "effective_key_before": list(names), "effective_key_current": list(names)}).decode()
    wanted = _REGISTRY_COLUMNS.get(descriptor.table_name,
        (FILTER_IDENTITY_COLUMNS[descriptor.table_name],) if descriptor.table_name in FILTER_IDENTITY_COLUMNS else ())

    def rows() -> Iterator[NavigationRow]:
        with_rows = identity_batches(table, policy)
        try:
            for batch, _, order_keys in with_rows:
                positions = {name: batch.schema.get_field_index(name) for name in wanted}
                for index, key in enumerate(order_keys):
                    values = {name: cast(Scalar, batch.column(position)[index].as_py())
                        for name, position in positions.items() if position >= 0}
                    yield NavigationRow(values, key)
        finally:
            with_rows.close()

    return NavigationSide({c.name: c.scalar_type for c in descriptor.columns}, rows,
        descriptor.row_count, table_display_name(descriptor.table_name, None, presentation))


def publish_business_presentation(
    plan: ComparisonPlan, facts: ComparisonFacts, closure: ComparisonRecordsClosure | None,
    handles: dict[str, native.ComparisonRecordsHandle], table_artifacts: tuple[SurfaceArtifactIndexEntry, ...],
    attribution: RiskAttribution, store: ArtifactStorePort, *,
    before_presentation: PresentationMetadata, current_presentation: PresentationMetadata,
    same_complete: Callable[[BoundSnapshotInput, BoundSnapshotInput, str], bool],
) -> tuple[tuple[SurfaceArtifactIndexEntry, ...], SurfaceProjectionRef, dict[str, int]]:
    context = current_kernel_context()
    if context is None:
        raise RuntimeError("business presentation requires the operation context")
    context.checkpoint()
    if plan.before.table_set is None or plan.current.table_set is None:
        raise ValueError("navigation canonical table sets are missing")
    before_tables = {t.descriptor.table_name: t for t in plan.before.table_set.tables}
    current_tables = {t.descriptor.table_name: t for t in plan.current.table_set.tables}
    before_labels = {t.table_name: t for t in before_presentation.tables}
    current_labels = {t.table_name: t for t in current_presentation.tables}
    tasks = {t.table_name: t for t in plan.tasks}
    artifacts = {t.table_name: t for t in table_artifacts}
    entries = {} if closure is None else {e.table_name: e for e in closure.records if e.family is RecordsArtifactFamily.STANDARD}
    table_risks = reduce_table_risks((t.table_name for t in facts.tables), attribution.table_events)
    tables = []
    locations: dict[str, RowLocationResult] = {}
    scanned_rows = locator_bytes = 0
    replacement = facts.comparison_mode is ComparisonMode.DATASET_REPLACEMENT
    for fact in facts.tables:
        context.checkpoint()
        name = fact.table_name
        task = tasks[name]
        excluded = (identity_excluded_sides(task, fact, FILTER_IDENTITY_COLUMNS[name])
            if not replacement and name in FILTER_IDENTITY_COLUMNS else frozenset())
        located = prepare_row_locations(task, entries.get(name), handles.get(name), artifacts[name].table_refs,
            store, filter_column=FILTER_IDENTITY_COLUMNS.get(name) if not excluded else None)
        locations[name] = located
        scanned_rows += located.scanned_rows
        records = tuple(replace(r, risk_level=attribution.rows.get(name, {}).get(r.row_identity)) for r in located.records)
        evidence = NavigationEvidence(
            comparison_succeeded=fact.status is not ComparisonTableStatus.DEGRADED,
            schema_only=fact.status is ComparisonTableStatus.SCHEMA_ONLY_CHANGED,
            degraded=fact.status is ComparisonTableStatus.DEGRADED,
            expected_record_counts=(fact.row_added_count, fact.row_deleted_count, fact.row_modified_count),
            suppressed_added_count=fact.suppressed_added_count,
            suppressed_deleted_count=fact.suppressed_deleted_count,
            locator_complete=located.batch is not None or not any((fact.row_added_count, fact.row_deleted_count, fact.row_modified_count)),
            risk_attribution_complete=attribution.complete.get(name, False),
            records=records, table_risk=table_risks[name], any_table_risk=attribution.any_risk.get(name, False),
        )
        tables.append(NavigationTable(name, name, _side(before_tables.get(name), before_labels.get(name)),
            _side(current_tables.get(name), current_labels.get(name)), evidence=evidence,
            table_change=fact.status in {ComparisonTableStatus.ADDED_TABLE, ComparisonTableStatus.DELETED_TABLE,
                ComparisonTableStatus.SCHEMA_CHANGED, ComparisonTableStatus.SCHEMA_ONLY_CHANGED,
                ComparisonTableStatus.DEGRADED, ComparisonTableStatus.REPLACED},
            unchanged=same_complete(plan.before, plan.current, name), identity_excluded_sides=excluded))
    navigation = build_navigation(tuple(tables), replacement=replacement,
        check=context.checkpoint, reserve=context.memory.reserve, resources=context.resources)
    namespaces = (navigation.document["replacement_sides"].values() if replacement else
        (navigation.document["groups"],))
    filtered_tables = {tab["table_id"] for groups in namespaces for group in groups
        for item in group["items"] for tab in item["tabs"] if tab["row_filter"] is not None}
    for name, located in locations.items():
        locator_ref = publish_row_locations(located, store, filtered=name in filtered_tables)
        artifacts[name] = replace(artifacts[name], row_locator_ref=locator_ref)
        locator_bytes += 0 if locator_ref is None else locator_ref.size_bytes
    payload = navigation.to_bytes()
    digest = raw_blob_digest(payload)
    ref = put_with_built_ref(store, payload,
        artifact_id=build_artifact_id(ArtifactLocation.COMPARISON, "business-navigation", digest.value),
        media_type="application/json")
    diagnostic_ref = None
    if navigation.diagnostics is not None:
        data = canonicalize_json_value(navigation.diagnostics)
        diagnostic_ref = put_with_built_ref(store, data,
            artifact_id=build_artifact_id(ArtifactLocation.COMPARISON, "navigation-diagnostics", raw_blob_digest(data).value),
            media_type="application/json")
    projection = SurfaceProjectionRef("business_navigation", "BUSINESS_NAVIGATION", ref, digest,
        diagnostics_ref=diagnostic_ref)
    return tuple(artifacts[name] for name in sorted(artifacts)), projection, {
        "locator_scanned_rows": scanned_rows, "locator_bytes": locator_bytes,
        "navigation_scanned_rows": navigation.scanned_rows, "navigation_bytes": len(payload),
        "navigation_diagnostic_bytes": 0 if diagnostic_ref is None else diagnostic_ref.size_bytes,
    }
