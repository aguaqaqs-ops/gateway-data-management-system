"""Complete small canonical cache inputs using the real IPC writer owner."""
from __future__ import annotations

from dataclasses import replace

from gateway_backend.artifacts import InMemoryArtifactStore
from gateway_backend.capabilities.comparison.contracts import BoundSnapshotInput, ComparisonStorageFacts
from gateway_backend.capabilities.snapshot_materialization import publish_canonical_tables
from gateway_backend.capabilities.snapshot_materialization.contracts import normalize_sql_type_spelling
from gateway_backend.capabilities.storage_projection import compute_schema_digest
from gateway_backend.capabilities.table_rules.contracts import (
    STORAGE_PROJECTION_VERSION, CanonicalKeyPolicy, OrderedPolicy, StorageRuleView,
)


def complete_canonical_bound(source: BoundSnapshotInput, *, ordered: bool = False) -> BoundSnapshotInput:
    assert source.table_set is not None
    tables = publish_canonical_tables(source.table_set.tables,
        snapshot_digest=source.snapshot.snapshot_digest, store=InMemoryArtifactStore(),
        repository_id="replacement-fixture")
    original = {item.storage_rule_view.canonical_table: item for item in source.storage_facts}
    facts = []
    for table in tables:
        descriptor = table.descriptor
        previous = original.get(descriptor.table_name)
        view = previous.storage_rule_view if previous is not None else StorageRuleView(
            canonical_table=descriptor.table_name,
            canonical_key_policy=CanonicalKeyPolicy.DDL_PRIMARY_KEY if descriptor.primary_key_columns else CanonicalKeyPolicy.EXPLICIT_KEYLESS,
            ordered_policy=OrderedPolicy.GID_NO_V1 if ordered else OrderedPolicy.NONE,
            structural_columns=("no",) if ordered else (),
            retained_columns=tuple(column.name for column in descriptor.columns),
            canonical_key_columns=(),
        )
        facts.append(ComparisonStorageFacts(
            storage_rule_view=view,
            source_schema_digest=descriptor.compare_schema_digest if previous is None else previous.source_schema_digest,
            canonical_schema_digest=compute_schema_digest(columns=[{
                "name": column.name, "sql_type": normalize_sql_type_spelling(column.scalar_type or "UNKNOWN"),
                "nullable": column.nullable,
            } for column in descriptor.columns], primary_key=descriptor.primary_key_columns),
            raw_content_digest=descriptor.raw_content_digest,
            storage_projection_version=STORAGE_PROJECTION_VERSION,
        ))
    return replace(source, table_set=replace(source.table_set, tables=tables), storage_facts=tuple(facts))
