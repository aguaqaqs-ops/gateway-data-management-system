"""Derive StorageRuleView from a resolved record and snapshot descriptor."""

from __future__ import annotations

from dataclasses import replace

from gateway_backend.capabilities.snapshot_materialization.contracts import SnapshotTableDescriptor
from gateway_backend.capabilities.storage_projection._digest import compute_storage_rule_digest
from gateway_backend.capabilities.storage_projection.contracts import ProjectionDiagnosticCode
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    StorageRuleView,
    TableRuleRecord,
    TableStaticRole,
    TableStorageDisposition,
    canonicalize_rule_identifier,
)


class StorageViewError(Exception):
    def __init__(self, code: ProjectionDiagnosticCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def derive_storage_rule_view(
    record: TableRuleRecord,
    descriptor: SnapshotTableDescriptor,
) -> StorageRuleView | None:
    if record.static_role is TableStaticRole.SKIP or record.table_storage is TableStorageDisposition.OMIT:
        return None
    dropped = record.dropped_columns
    dropped_names = {item.name for item in dropped}
    retained = tuple(
        canonicalize_rule_identifier(column.name)
        for column in descriptor.columns
        if canonicalize_rule_identifier(column.name) not in dropped_names
    )
    policy = record.canonical_key_policy
    if policy is CanonicalKeyPolicy.EXPLICIT:
        key_columns = record.compare_key_columns
    elif policy in {
        CanonicalKeyPolicy.DDL_PRIMARY_KEY,
        CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS,
    }:
        key_columns = tuple(
            canonicalize_rule_identifier(name) for name in descriptor.primary_key_columns
        )
    elif policy is CanonicalKeyPolicy.EXPLICIT_KEYLESS:
        key_columns = ()
    else:
        raise StorageViewError(
            ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
            "canonical key policy is not supported",
        )
    descriptor_names = {
        canonicalize_rule_identifier(column.name) for column in descriptor.columns
    }
    retained_names = set(retained)
    if policy is CanonicalKeyPolicy.EXPLICIT_KEYLESS or (
        policy is CanonicalKeyPolicy.DDL_PRIMARY_KEY_OR_KEYLESS and not key_columns
    ):
        pass
    else:
        if not key_columns:
            raise StorageViewError(ProjectionDiagnosticCode.KEY_MISSING, "canonical key is empty")
        for name in key_columns:
            if name in dropped_names:
                raise StorageViewError(
                    ProjectionDiagnosticCode.KEY_MISSING,
                    "canonical key intersects dropped columns",
                )
            if name not in descriptor_names or name not in retained_names:
                raise StorageViewError(
                    ProjectionDiagnosticCode.KEY_MISSING,
                    "canonical key column is missing",
                )
    view = StorageRuleView(
        canonical_table=descriptor.table_name,
        canonical_key_policy=policy,
        ordered_policy=record.ordered_policy,
        dropped_columns=dropped,
        structural_columns=record.structural_columns,
        retained_columns=retained,
        canonical_key_columns=key_columns,
    )
    return replace(view, storage_rule_digest=compute_storage_rule_digest(view))
