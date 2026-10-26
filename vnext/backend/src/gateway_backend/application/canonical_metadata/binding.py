"""Build the Repository read binding from frozen commit metadata."""

from __future__ import annotations

from gateway_backend.application.canonical_metadata.ports import CommitCanonicalMetadata
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    CanonicalBinding,
    CanonicalTableIdentity,
)
from gateway_backend.capabilities.storage_projection import (
    CanonicalizationManifest,
    CanonicalizationManifestTable,
)
from gateway_backend.capabilities.table_rules.contracts import (
    CanonicalKeyPolicy,
    StorageRuleView,
    TableRulesetSnapshot,
)


def canonical_binding_for_commit(
    metadata: CommitCanonicalMetadata,
    *,
    runtime_ruleset: TableRulesetSnapshot,
) -> CanonicalBinding:
    if type(metadata) is not CommitCanonicalMetadata:
        raise ValueError("metadata must be CommitCanonicalMetadata")
    if type(runtime_ruleset) is not TableRulesetSnapshot:
        raise ValueError("runtime_ruleset must be TableRulesetSnapshot")
    if metadata.initial:
        if runtime_ruleset.ruleset_digest is None:
            raise ValueError("runtime ruleset digest is required for INITIAL binding")
        return CanonicalBinding(
            storage_projection_version=runtime_ruleset.storage_projection_version,
            ruleset_id=runtime_ruleset.ruleset_id,
            ruleset_version=runtime_ruleset.ruleset_version,
            ruleset_digest=runtime_ruleset.ruleset_digest,
            tables=(),
            is_initial=True,
        )
    manifest = metadata.manifest
    if type(manifest) is not CanonicalizationManifest:
        raise ValueError("Submission metadata requires a canonicalization manifest")
    if any(
        table.source_schema_digest is None
        or table.canonical_schema_digest is None
        or table.content_digest is None
        for table in manifest.tables
    ):
        raise ValueError("canonical manifest is missing table identity facts")
    return CanonicalBinding(
        storage_projection_version=manifest.storage_projection_version,
        ruleset_id=manifest.ruleset_id,
        ruleset_version=manifest.ruleset_version,
        ruleset_digest=manifest.ruleset_digest,
        snapshot_digest=metadata.snapshot_digest,
        tables=tuple(
            sorted(
                (_storage_rule_view(table) for table in manifest.tables),
                key=lambda item: item.canonical_table.encode("utf-8"),
            )
        ),
        table_identities=tuple(
            CanonicalTableIdentity(
                canonical_table=table.name,
                row_count=table.canonical_row_count,
                source_schema_digest=table.source_schema_digest,
                canonical_schema_digest=table.canonical_schema_digest,
                raw_content_digest=table.content_digest,
            )
            for table in sorted(manifest.tables, key=lambda item: item.name.encode("utf-8"))
            if (
                table.source_schema_digest is not None
                and table.canonical_schema_digest is not None
                and table.content_digest is not None
            )
        ),
    )


def _storage_rule_view(table: CanonicalizationManifestTable) -> StorageRuleView:
    # Keep manifest schema and content facts out of canonical_binding.
    if type(table) is not CanonicalizationManifestTable:
        raise ValueError("manifest tables must be CanonicalizationManifestTable")
    explicit_key = (
        table.canonical_key_columns
        if table.canonical_key_policy is CanonicalKeyPolicy.EXPLICIT
        else ()
    )
    if table.canonical_key_policy is CanonicalKeyPolicy.EXPLICIT and not explicit_key:
        raise ValueError("EXPLICIT canonical key metadata is empty")
    return StorageRuleView(
        canonical_table=table.name,
        canonical_key_policy=table.canonical_key_policy,
        ordered_policy=table.ordered_policy,
        dropped_columns=table.dropped_columns,
        structural_columns=table.structural_columns,
        canonical_key_columns=explicit_key,
        retained_columns=table.retained_columns,
    )


__all__ = ["canonical_binding_for_commit"]
