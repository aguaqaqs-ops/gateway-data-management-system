"""Production canonical projection: one Rust kernel and owned Python metadata."""

from __future__ import annotations

from gateway_backend.capabilities.table_presentation.metadata import PresentationMetadata

from dataclasses import replace

from gateway_shared_kernel import DigestRef

from gateway_backend.capabilities.snapshot_materialization import (
    operation_business_budgets, snapshot_arrow_input, snapshot_table_from_arrow,
    current_kernel_context, source_descriptor_from_arrow, compare_schema_digest,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BlankRowProvenance, SnapshotColumnDescriptor, SnapshotTable, SnapshotTableOrderedMetadata, SnapshotTableSet,
)
from gateway_backend.capabilities.storage_projection._digest import compute_manifest_digest, compute_schema_digest
from gateway_backend.capabilities.storage_projection.contracts import (
    CANONICALIZATION_MANIFEST_CONTRACT, STORAGE_PROJECTION_VERSION, MAX_DIAGNOSTICS,
    CanonicalProjectionResult, CanonicalizationManifest, CanonicalizationManifestTable,
    ProjectionDiagnostic, ProjectionDiagnosticCode, ProjectionDiagnosticSeverity, ProjectionStatus,
)
from gateway_backend.capabilities.storage_projection.native import project_arrow_table
from gateway_backend.capabilities.storage_projection.view import derive_storage_rule_view, StorageViewError
from gateway_backend.capabilities.table_rules import resolve_table_rule
from gateway_backend.capabilities.table_rules.contracts import OrderedPolicy, TableRulesetSnapshot


def project_canonical_arrow_table_set(raw: SnapshotTableSet, ruleset: TableRulesetSnapshot, *,
    presentation: PresentationMetadata = PresentationMetadata(),
) -> CanonicalProjectionResult:
    context = current_kernel_context()
    if context is None or ruleset.ruleset_digest is None:
        raise ValueError("canonical projection requires the operation context and complete ruleset")
    tables: list[SnapshotTable] = []
    manifest_tables: list[CanonicalizationManifestTable] = []
    diagnostics: list[ProjectionDiagnostic] = []
    omitted = 0
    try:
        for table in sorted(raw.tables, key=lambda item: item.descriptor.table_name.encode("utf-8")):
            context.checkpoint()
            descriptor = table.descriptor
            record = resolve_table_rule(ruleset, descriptor.table_name, primary_key_columns=descriptor.primary_key_columns).record
            try:
                view = derive_storage_rule_view(record, descriptor)
            except StorageViewError as exc:
                if len(diagnostics) < MAX_DIAGNOSTICS:
                    diagnostics.append(ProjectionDiagnostic(exc.code, ProjectionDiagnosticSeverity.ERROR,
                                                            exc.message, descriptor.table_name))
                else:
                    omitted += 1
                continue
            if view is None:
                continue
            with snapshot_arrow_input(table) as (metadata, control):
                result = project_arrow_table(metadata, descriptor, view, canonicalized_input=False,
                    cancel_probe=control.cancel_probe, budgets=operation_business_budgets(),
                    deadline_monotonic=control.deadline_monotonic, pool_threads=control.threads)
            for item in result["diagnostics"]:
                if len(diagnostics) < MAX_DIAGNOSTICS:
                    diagnostics.append(ProjectionDiagnostic(ProjectionDiagnosticCode(item["code"]),
                        ProjectionDiagnosticSeverity(item["severity"]), item["message"], item["table"], item["column"]))
                else:
                    omitted += 1
            omitted += result["omitted_diagnostic_count"]
            output = result["output"]
            if output is None:
                continue
            arrow = output["tables"][0]
            with arrow["arrow_stream"] as stream:
                arrays = stream.read_all()
            columns = tuple(SnapshotColumnDescriptor(c["canonical_name"], c["display_name"], c["nullable"], c["sql_type"])
                            for c in arrow["columns"])
            digest = DigestRef(output["raw_content_digest"])
            schema_digest = compute_schema_digest(columns=[{"name": c.name, "nullable": c.nullable, "sql_type": c.scalar_type}
                                                           for c in columns], primary_key=view.canonical_key_columns)
            bound = replace(descriptor, columns=columns, primary_key_columns=view.canonical_key_columns,
                compare_key_columns=view.canonical_key_columns, row_count=arrays.num_rows, raw_content_digest=digest,
                compare_schema_digest=compare_schema_digest(descriptor.table_name, tuple(c.name for c in columns), view.canonical_key_columns),
                degraded_reason=None, diagnostics=())
            ordered = SnapshotTableOrderedMetadata(BlankRowProvenance.CANONICAL_PSEUDO_GID) if view.ordered_policy is OrderedPolicy.GID_NO_V1 else None
            tables.append(snapshot_table_from_arrow(bound, arrays, source_descriptor_from_arrow(arrow), ordered=ordered,
                                                    execution_context=control))
            manifest_tables.append(CanonicalizationManifestTable(
                name=view.canonical_table, source_row_count=descriptor.row_count, canonical_row_count=arrays.num_rows,
                canonical_key_policy=view.canonical_key_policy, ordered_policy=view.ordered_policy,
                retained_columns=view.retained_columns, structural_columns=view.structural_columns,
                dropped_columns=view.dropped_columns, canonical_key_columns=view.canonical_key_columns,
                source_schema_digest=descriptor.compare_schema_digest, canonical_schema_digest=schema_digest,
                content_digest=digest, gid_real_count=output["gid_real_count"], gid_pseudo_count=output["gid_pseudo_count"],
            ))
        context.checkpoint()
        if diagnostics:
            for table in tables:
                if table.reader is not None:
                    table.reader.close()
                if table.batch_reader is not None:
                    table.batch_reader.close()
            return CanonicalProjectionResult(ProjectionStatus.FAILED, (), omitted, diagnostics=tuple(diagnostics))
        manifest = CanonicalizationManifest(CANONICALIZATION_MANIFEST_CONTRACT, STORAGE_PROJECTION_VERSION,
            ruleset.ruleset_id, ruleset.ruleset_version, ruleset.ruleset_digest, raw.snapshot_digest, tuple(manifest_tables),
            presentation.project((t.name, t.retained_columns) for t in manifest_tables))
        manifest = replace(manifest, manifest_digest=compute_manifest_digest(manifest))
        return CanonicalProjectionResult(ProjectionStatus.COMPLETE, tuple(tables), 0, manifest=manifest)
    except BaseException:
        for table in tables:
            if table.reader is not None:
                table.reader.close()
            if table.batch_reader is not None:
                table.batch_reader.close()
        raise
