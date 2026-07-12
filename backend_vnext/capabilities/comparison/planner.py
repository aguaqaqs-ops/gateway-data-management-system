from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
import re

from ...core.digests import DigestRef
from ...core.diagnostics import DiagnosticRecord
from ...core.identifiers import canonical_identifier
from ..table_rules import enters_comparison_for_static_role
from .digest import build_comparison_digest
from .models import (
    ComparisonComputeInput,
    ComparisonInput,
    ComparisonPlan,
    ComparisonRole,
    ComparisonTableStatus,
    TableRulesetSnapshot,
    TableRulesetTableRule,
)
from .ruleset_registry import TableRulesetRegistry, build_hardcoded_table_ruleset_registry


SUMMARY_EARLY_EXIT_PROVIDER = "SUMMARY_EARLY_EXIT"
SNAPSHOT_TABLE_COMPARE_PROVIDER = "SNAPSHOT_TABLE_COMPARE"
ORDERED_TABLE_COMPARE_PROVIDER = "ORDERED_TABLE_COMPARE"
BROWSE_ONLY_PROVIDER = "BROWSE_ONLY"
DOLT_NATIVE_PROVIDER = "DOLT_NATIVE"
ORDERED_TABLE_COMPARE_UNSUPPORTED_PROVIDER = ORDERED_TABLE_COMPARE_PROVIDER
SKIPPED_PROVIDER = "SKIPPED"


@dataclass(frozen=True, slots=True)
class PlannedTableRoute:
    table_name: str
    provider: str
    status: ComparisonTableStatus | str
    diagnostics: tuple[DiagnosticRecord, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_name", canonical_identifier(self.table_name))
        object.__setattr__(self, "status", ComparisonTableStatus(self.status))
        normalized_diagnostics: list[DiagnosticRecord] = []
        for diagnostic in self.diagnostics:
            if not isinstance(diagnostic, DiagnosticRecord):
                raise TypeError("diagnostics must contain DiagnosticRecord values")
            normalized_diagnostics.append(diagnostic)
        object.__setattr__(self, "diagnostics", tuple(normalized_diagnostics))


@dataclass(frozen=True, slots=True)
class ComparisonPlanner:
    ruleset_registry: TableRulesetRegistry = field(default_factory=build_hardcoded_table_ruleset_registry)

    def plan(self, compute_input: ComparisonComputeInput) -> ComparisonPlan:
        if not isinstance(compute_input, ComparisonComputeInput):
            raise TypeError("compute_input must be a ComparisonComputeInput")

        ruleset = _resolve_ruleset(self.ruleset_registry, compute_input)
        requested_tables = _requested_tables(compute_input)
        before_tables = _summary_table_map(compute_input.before.summary)
        current_tables = _summary_table_map(compute_input.current.summary)
        table_names = _resolve_table_names(requested_tables, before_tables, current_tables)
        pair_can_early_exit = _can_pair_early_exit(
            before=compute_input.before,
            current=compute_input.current,
            ruleset=ruleset,
            requested_tables=requested_tables,
            table_names=table_names,
            comparison_options=compute_input.comparison_options,
            comparison_contract_version=compute_input.comparison_contract_version,
            projection_contract_version=compute_input.projection_contract_version,
            scalar_encoding_version=compute_input.scalar_encoding_version or "",
        )
        pair_can_use_native, native_reason = _can_pair_use_dolt_native(
            before=compute_input.before,
            current=compute_input.current,
        )

        routes: list[PlannedTableRoute] = []
        diagnostics: list[DiagnosticRecord] = []
        summary_early_exit_tables: list[str] = []
        row_compare_tables: list[str] = []

        if native_reason is not None and not pair_can_use_native:
            diagnostics.append(
                DiagnosticRecord(
                    code="comparison.planner.native-eligibility",
                    message="native provider eligibility evaluated",
                    phase="planning",
                    severity="WARNING",
                    details={
                        "reason": native_reason,
                        "repository_id": getattr(
                            compute_input.before.repository_backed_context,
                            "repository_id",
                            None,
                        ),
                    },
                )
            )

        for table_name in table_names:
            route = _plan_table_route(
                table_name=table_name,
                before_table=before_tables.get(table_name),
                current_table=current_tables.get(table_name),
                ruleset=ruleset,
                pair_can_early_exit=pair_can_early_exit,
                pair_can_use_native=pair_can_use_native,
            )
            diagnostics.extend(route.diagnostics)
            if route.provider == SKIPPED_PROVIDER and route.status == ComparisonTableStatus.UNCHANGED:
                continue
            routes.append(route)
            if route.provider == SUMMARY_EARLY_EXIT_PROVIDER:
                summary_early_exit_tables.append(route.table_name)
            elif route.provider not in {SKIPPED_PROVIDER, BROWSE_ONLY_PROVIDER}:
                row_compare_tables.append(route.table_name)

        plan_digest = _build_plan_digest(
            before_snapshot_digest=compute_input.before.snapshot.snapshot_digest,
            current_snapshot_digest=compute_input.current.snapshot.snapshot_digest,
            comparison_contract_version=compute_input.comparison_contract_version,
            projection_contract_version=compute_input.projection_contract_version,
            table_ruleset_version=compute_input.table_ruleset_version or ruleset.ruleset_version,
            scalar_encoding_version=compute_input.scalar_encoding_version or "",
            table_ruleset_digest=ruleset.ruleset_digest,
            requested_tables=requested_tables,
            comparison_options=compute_input.comparison_options,
            table_aliases=tuple(
                alias.payload_for_digest()
                for alias in getattr(compute_input, "table_aliases", ())
            ),
            routes=routes,
            diagnostics=diagnostics,
        )
        return ComparisonPlan(
            comparison_digest=plan_digest,
            summary_early_exit_tables=tuple(summary_early_exit_tables),
            row_compare_tables=tuple(row_compare_tables),
            provider_routes=tuple((route.table_name, route.provider) for route in routes),
            diagnostics=tuple(diagnostics),
        )


def _resolve_ruleset(
    registry: TableRulesetRegistry,
    compute_input: ComparisonComputeInput,
) -> TableRulesetSnapshot:
    if compute_input.table_ruleset is not None:
        return compute_input.table_ruleset
    if compute_input.table_ruleset_version:
        for snapshot in registry.rulesets.values():
            if snapshot.ruleset_version == compute_input.table_ruleset_version:
                return snapshot
    return registry.snapshot()


def _requested_tables(compute_input: ComparisonComputeInput) -> tuple[str, ...]:
    return tuple(
        canonical_identifier(table_name)
        for table_name in compute_input.requested_tables
        if canonical_identifier(table_name)
    )


def _summary_table_map(summary: object) -> dict[str, object]:
    tables = getattr(summary, "tables", ())
    mapping: dict[str, object] = {}
    for table in tables:
        table_name = canonical_identifier(getattr(table, "table_name"))
        if table_name:
            mapping[table_name] = table
    return mapping


def _resolve_table_names(
    requested_tables: Sequence[str],
    before_tables: Mapping[str, object],
    current_tables: Mapping[str, object],
) -> tuple[str, ...]:
    if requested_tables:
        ordered = [table_name for table_name in requested_tables if table_name]
    else:
        ordered = list(before_tables.keys())
        for table_name in current_tables:
            if table_name not in before_tables:
                ordered.append(table_name)
    seen: set[str] = set()
    deduped: list[str] = []
    for table_name in ordered:
        canonical_table_name = canonical_identifier(table_name)
        if not canonical_table_name or canonical_table_name in seen:
            continue
        seen.add(canonical_table_name)
        deduped.append(canonical_table_name)
    return tuple(deduped)


def _can_pair_early_exit(
    *,
    before: ComparisonInput,
    current: ComparisonInput,
    ruleset: TableRulesetSnapshot,
    requested_tables: Sequence[str],
    table_names: Sequence[str],
    comparison_options: object,
    comparison_contract_version: str,
    projection_contract_version: str,
    scalar_encoding_version: str,
) -> bool:
    if before.snapshot.snapshot_digest != current.snapshot.snapshot_digest:
        return False
    if not table_names:
        return False
    return True


def _can_pair_use_dolt_native(
    *,
    before: ComparisonInput,
    current: ComparisonInput,
) -> tuple[bool, str | None]:
    before_context = before.repository_backed_context
    current_context = current.repository_backed_context
    if before_context is None or current_context is None:
        return False, "DOLT_NATIVE_PAIR_CONTEXT_MISSING"
    if before_context.repository_table_access_provider is None or current_context.repository_table_access_provider is None:
        return False, "DOLT_NATIVE_PAIR_CONTEXT_MISSING"

    before_repository_id = getattr(before.snapshot, "repository_id", None)
    current_repository_id = getattr(current.snapshot, "repository_id", None)
    if (
        not isinstance(before_repository_id, str)
        or not before_repository_id.strip()
        or not isinstance(current_repository_id, str)
        or not current_repository_id.strip()
    ):
        return False, "DOLT_NATIVE_PAIR_CONTEXT_MISSING"
    if before_context.repository_id != before_repository_id or current_context.repository_id != current_repository_id:
        return False, "DOLT_NATIVE_PAIR_REPOSITORY_MISMATCH"
    if before_repository_id != current_repository_id:
        return False, "DOLT_NATIVE_PAIR_REPOSITORY_MISMATCH"

    if before_context.repository_server_contract_version != current_context.repository_server_contract_version:
        return False, "DOLT_NATIVE_PAIR_CAPABILITY_UNVERIFIED"
    return True, "DOLT_NATIVE_SELECTED"


def _plan_table_route(
    *,
    table_name: str,
    before_table: object | None,
    current_table: object | None,
    ruleset: TableRulesetSnapshot,
    pair_can_early_exit: bool,
    pair_can_use_native: bool,
) -> PlannedTableRoute:
    rule, selector_kind = _resolve_table_rule(ruleset, table_name)
    diagnostics: list[DiagnosticRecord] = []

    if rule is None:
        if before_table is None and current_table is None:
            diagnostics.append(
                DiagnosticRecord(
                    code="comparison.planner.table-missing",
                    message="table was requested but is absent on both sides",
                    phase="planning",
                    severity="WARNING",
                    details={"table_name": table_name},
                )
            )
            return PlannedTableRoute(
                table_name=table_name,
                provider=SKIPPED_PROVIDER,
                status=ComparisonTableStatus.DEGRADED,
                diagnostics=tuple(diagnostics),
            )
        if before_table is not None and current_table is not None and _raw_table_equal(before_table, current_table):
            return PlannedTableRoute(
                table_name=table_name,
                provider=SUMMARY_EARLY_EXIT_PROVIDER,
                status=ComparisonTableStatus.UNCHANGED,
                diagnostics=tuple(diagnostics),
            )
        if pair_can_use_native and not pair_can_early_exit:
            diagnostics.append(
                DiagnosticRecord(
                    code="comparison.planner.native-route",
                    message="native provider route selected",
                    phase="planning",
                    severity="INFO",
                    details={
                        "table_name": table_name,
                        "provider": DOLT_NATIVE_PROVIDER,
                        "selector_kind": selector_kind,
                    },
                )
            )
            return PlannedTableRoute(
                table_name=table_name,
                provider=DOLT_NATIVE_PROVIDER,
                status=ComparisonTableStatus.MODIFIED,
                diagnostics=tuple(diagnostics),
            )
        return PlannedTableRoute(
            table_name=table_name,
            provider=SUMMARY_EARLY_EXIT_PROVIDER if pair_can_early_exit else SNAPSHOT_TABLE_COMPARE_PROVIDER,
            status=ComparisonTableStatus.UNCHANGED if pair_can_early_exit and before_table is not None and current_table is not None else ComparisonTableStatus.MODIFIED,
            diagnostics=tuple(diagnostics),
        )

    static_role = _normalized_role_name(rule.static_role)

    if static_role == "SKIP":
        diagnostics.append(
            DiagnosticRecord(
                code="comparison.planner.table-filtered",
                message="table ruleset filtered the table out of comparison",
                phase="planning",
                severity="INFO",
                details={"table_name": table_name, "selector_kind": selector_kind},
            )
        )
        return PlannedTableRoute(
            table_name=table_name,
            provider=SKIPPED_PROVIDER,
            status=ComparisonTableStatus.UNCHANGED,
            diagnostics=tuple(diagnostics),
        )

    if static_role == "BROWSE_ONLY":
        if before_table is None and current_table is None:
            diagnostics.append(
                DiagnosticRecord(
                    code="comparison.planner.table-missing",
                    message="browse-only table was requested but is absent on both sides",
                    phase="planning",
                    severity="WARNING",
                    details={
                        "table_name": table_name,
                        "selector_kind": selector_kind,
                        "static_role": static_role,
                    },
                )
            )
            return PlannedTableRoute(
                table_name=table_name,
                provider=SKIPPED_PROVIDER,
                status=ComparisonTableStatus.DEGRADED,
                diagnostics=tuple(diagnostics),
            )
        diagnostics.append(
            DiagnosticRecord(
                code="comparison.planner.browse-only-route",
                message="browse-only table is exposed for table browsing without row comparison",
                phase="planning",
                severity="INFO",
                details={
                    "table_name": table_name,
                    "selector_kind": selector_kind,
                    "static_role": static_role,
                    "provider": BROWSE_ONLY_PROVIDER,
                },
            )
        )
        return PlannedTableRoute(
            table_name=table_name,
            provider=BROWSE_ONLY_PROVIDER,
            status=ComparisonTableStatus.UNCHANGED,
            diagnostics=tuple(diagnostics),
        )

    if not enters_comparison_for_static_role(static_role):
        diagnostics.append(
            DiagnosticRecord(
                code="comparison.planner.table-filtered",
                message="table ruleset filtered the table out of comparison",
                phase="planning",
                severity="INFO",
                details={
                    "table_name": table_name,
                    "selector_kind": selector_kind,
                    "static_role": static_role,
                },
            )
        )
        return PlannedTableRoute(
            table_name=table_name,
            provider=SKIPPED_PROVIDER,
            status=ComparisonTableStatus.UNCHANGED,
            diagnostics=tuple(diagnostics),
        )

    if pair_can_early_exit and before_table is not None and current_table is not None:
        return PlannedTableRoute(
            table_name=table_name,
            provider=SUMMARY_EARLY_EXIT_PROVIDER,
            status=ComparisonTableStatus.UNCHANGED,
            diagnostics=tuple(diagnostics),
        )

    if static_role in {"ORDERED", "ORDERED_DIFF", "ORDERED_TABLE_COMPARE"}:
        if (
            before_table is not None
            and current_table is not None
            and _ordered_table_can_summary_early_exit(before_table, current_table)
        ):
            return PlannedTableRoute(
                table_name=table_name,
                provider=SUMMARY_EARLY_EXIT_PROVIDER,
                status=ComparisonTableStatus.UNCHANGED,
                diagnostics=tuple(diagnostics),
            )
        diagnostics.append(
            DiagnosticRecord(
                code="comparison.planner.ordered-route",
                message="ordered tables are routed to the ordered provider scaffold",
                phase="planning",
                severity="INFO",
                details={
                    "table_name": table_name,
                    "selector_kind": selector_kind,
                    "provider": ORDERED_TABLE_COMPARE_PROVIDER,
                },
            )
        )
        return PlannedTableRoute(
            table_name=table_name,
            provider=ORDERED_TABLE_COMPARE_PROVIDER,
            status=ComparisonTableStatus.DEGRADED,
            diagnostics=tuple(diagnostics),
        )

    if pair_can_use_native and not pair_can_early_exit:
        diagnostics.append(
            DiagnosticRecord(
                code="comparison.planner.native-route",
                message="native provider route selected",
                phase="planning",
                severity="INFO",
                details={
                    "table_name": table_name,
                    "provider": DOLT_NATIVE_PROVIDER,
                    "selector_kind": selector_kind,
                },
            )
        )
        return PlannedTableRoute(
            table_name=table_name,
            provider=DOLT_NATIVE_PROVIDER,
            status=ComparisonTableStatus.MODIFIED,
            diagnostics=tuple(diagnostics),
        )

    if before_table is not None and current_table is not None:
        before_descriptor = before_table
        current_descriptor = current_table
        if _raw_table_equal(before_descriptor, current_descriptor):
            return PlannedTableRoute(
                table_name=table_name,
                provider=SUMMARY_EARLY_EXIT_PROVIDER,
                status=ComparisonTableStatus.UNCHANGED,
                diagnostics=tuple(diagnostics),
            )

    return PlannedTableRoute(
        table_name=table_name,
        provider=SNAPSHOT_TABLE_COMPARE_PROVIDER,
        status=ComparisonTableStatus.MODIFIED,
        diagnostics=tuple(diagnostics),
    )


def _resolve_table_rule(
    ruleset: TableRulesetSnapshot,
    table_name: str,
) -> tuple[TableRulesetTableRule | None, str]:
    canonical_table_name = canonical_identifier(table_name)
    for rule in ruleset.table_rules:
        selector = rule.table_selector.strip()
        if _selector_matches(selector, canonical_table_name):
            return rule, _selector_kind(selector)
    return None, "NONE"


def _selector_matches(selector: str, table_name: str) -> bool:
    if _selector_kind(selector) == "REGEX":
        return re.fullmatch(selector, table_name) is not None
    return canonical_identifier(selector) == table_name


def _selector_kind(selector: str) -> str:
    regex_chars = set(".^$*+?{}[]|()\\")
    if any(char in regex_chars for char in selector):
        return "REGEX"
    return "EXACT"


def _normalized_role_name(value: str) -> str:
    return value.strip().upper()


def _ruleset_has_ordered_tables(
    ruleset: TableRulesetSnapshot,
    table_names: Sequence[str],
) -> bool:
    for table_name in table_names:
        rule, _selector_kind = _resolve_table_rule(ruleset, table_name)
        if rule is not None and _normalized_role_name(rule.static_role) in {"ORDERED", "ORDERED_DIFF", "ORDERED_TABLE_COMPARE"}:
            return True
    return False


def _raw_table_equal(before_descriptor: object, current_descriptor: object) -> bool:
    before_compare_schema = getattr(before_descriptor, "compare_schema_digest", None)
    current_compare_schema = getattr(current_descriptor, "compare_schema_digest", None)
    before_stage = getattr(before_descriptor, "materialization_stage", None)
    current_stage = getattr(current_descriptor, "materialization_stage", None)
    before_row_count = getattr(before_descriptor, "row_count", None)
    current_row_count = getattr(current_descriptor, "row_count", None)
    return (
        before_compare_schema == current_compare_schema
        and before_row_count == current_row_count
        and _table_identity_equal(
            before_descriptor=before_descriptor,
            current_descriptor=current_descriptor,
            before_stage=before_stage,
            current_stage=current_stage,
        )
    )


def _table_identity_equal(
    *,
    before_descriptor: object,
    current_descriptor: object,
    before_stage: str | None,
    current_stage: str | None,
) -> bool:
    before_fast = getattr(before_descriptor, "fast_row_digest", None)
    current_fast = getattr(current_descriptor, "fast_row_digest", None)
    if (
        before_stage != "FINAL"
        or current_stage != "FINAL"
    ) and before_fast is not None and current_fast is not None:
        if before_fast == current_fast:
            return True

    before_canonical = getattr(before_descriptor, "canonical_artifact_ref", None)
    current_canonical = getattr(current_descriptor, "canonical_artifact_ref", None)
    if (
        before_stage == "FINAL"
        and current_stage == "FINAL"
        and before_canonical is not None
        and current_canonical is not None
        and before_canonical == current_canonical
    ):
        return True

    before_layout = getattr(before_descriptor, "row_layout_digest", None)
    current_layout = getattr(current_descriptor, "row_layout_digest", None)
    if before_layout is not None and current_layout is not None and before_layout == current_layout:
        return True

    before_raw = getattr(before_descriptor, "raw_content_digest", None)
    current_raw = getattr(current_descriptor, "raw_content_digest", None)
    return before_raw is not None and before_raw == current_raw


def _ordered_table_can_summary_early_exit(before_descriptor: object, current_descriptor: object) -> bool:
    if not _descriptor_shape_equal_for_ordered_early_exit(before_descriptor, current_descriptor):
        return False
    before_stage = getattr(before_descriptor, "materialization_stage", None)
    current_stage = getattr(current_descriptor, "materialization_stage", None)
    if before_stage == "FINAL" and current_stage == "FINAL":
        before_canonical = getattr(before_descriptor, "canonical_artifact_ref", None)
        current_canonical = getattr(current_descriptor, "canonical_artifact_ref", None)
        if before_canonical is not None and current_canonical is not None and before_canonical == current_canonical:
            return True
        before_business = getattr(before_descriptor, "business_content_digest", None)
        current_business = getattr(current_descriptor, "business_content_digest", None)
        if before_business is not None and before_business == current_business:
            return True
        before_raw = getattr(before_descriptor, "raw_content_digest", None)
        current_raw = getattr(current_descriptor, "raw_content_digest", None)
        return before_raw is not None and before_raw == current_raw
    before_fast = getattr(before_descriptor, "fast_row_digest", None)
    current_fast = getattr(current_descriptor, "fast_row_digest", None)
    return before_fast is not None and before_fast == current_fast


def _descriptor_shape_equal_for_ordered_early_exit(
    before_descriptor: object,
    current_descriptor: object,
) -> bool:
    return (
        getattr(before_descriptor, "compare_schema_digest", None)
        == getattr(current_descriptor, "compare_schema_digest", None)
        and getattr(before_descriptor, "row_count", None)
        == getattr(current_descriptor, "row_count", None)
        and getattr(before_descriptor, "compare_key_columns", None)
        == getattr(current_descriptor, "compare_key_columns", None)
    )


def _build_plan_digest(
    *,
    before_snapshot_digest: DigestRef | str,
    current_snapshot_digest: DigestRef | str,
    comparison_contract_version: str,
    projection_contract_version: str,
    table_ruleset_version: str,
    scalar_encoding_version: str,
    table_ruleset_digest: DigestRef | str | None,
    requested_tables: Sequence[str],
    comparison_options: object,
    routes: Sequence[PlannedTableRoute],
    diagnostics: Sequence[DiagnosticRecord],
    table_aliases: Sequence[object] = (),
) -> DigestRef:
    return DigestRef.from_payload(
        {
            "before_snapshot_digest": DigestRef.parse(str(before_snapshot_digest)).to_payload(),
            "current_snapshot_digest": DigestRef.parse(str(current_snapshot_digest)).to_payload(),
            "comparison_contract_version": comparison_contract_version,
            "projection_contract_version": projection_contract_version,
            "table_ruleset_version": table_ruleset_version,
            "scalar_encoding_version": scalar_encoding_version,
            "table_ruleset_digest": (
                None if table_ruleset_digest is None else DigestRef.parse(str(table_ruleset_digest)).to_payload()
            ),
            "table_aliases": tuple(table_aliases),
            "requested_tables": tuple(canonical_identifier(table_name) for table_name in requested_tables),
            "comparison_options": comparison_options,
            "routes": [
                {
                    "table_name": route.table_name,
                    "provider": route.provider,
                    "status": route.status.value,
                }
                for route in routes
            ],
            "diagnostics": [diagnostic.to_payload() for diagnostic in diagnostics],
        }
    )
