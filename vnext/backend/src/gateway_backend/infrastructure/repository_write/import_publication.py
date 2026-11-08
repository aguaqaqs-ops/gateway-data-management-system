"""RepositoryImportArtifact v1 writer and Submit import publication adapter."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import replace
from time import monotonic

from gateway_shared_kernel import (
    DigestRef,
    raw_blob_digest,
)
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.application.submission.contracts import (
    PREPARE_IMPORT_CHECKPOINT_SCHEMA,
    PrepareImportBuildInput,
    PrepareImportCheckpoint,
    PrepareImportPublicationResult,
    SnapshotTableBinding,
)
from gateway_backend.application.submission.errors import SubmitImportPublicationError
from gateway_backend.artifacts import ArtifactStorePort, ManifestVerificationError
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.mutation_planning import (
    MutationPolicy,
    MutationThresholdPolicy,
    StorageTableSideV1,
    StorageTableTaskV1,
    TableMutationKind,
    choose_table_mutation,
    prepare_storage_table,
)
from gateway_backend.capabilities.snapshot_materialization import (
    ArtifactPublishError,
    materialize_repository_ref,
    open_snapshot_table_artifact, current_kernel_context,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    CanonicalBinding,
    CanonicalTableIdentity,
    MaterializationPolicy,
    MaterializationStage,
    RepositoryRef,
    RepositoryRefMaterializationRequest, CommittedCanonicalTablesPort,
    RepositoryTableAccessProvider,
    SnapshotMaterializationStatus,
    SnapshotTable,
    SnapshotTableDescriptor,
)
from gateway_backend.capabilities.table_access.contracts import (
    ParserInvocationContext,
)
from gateway_backend.capabilities.storage_projection import (
    MANIFEST_ENTRY_NAME,
    PACKAGE_VERSION,
    ImportReplayError as ProjectionImportReplayError,
    ProjectionTable,
    ProjectionInvocationContext, MAX_MANIFEST_JSON_BYTES, MAX_REPLAY_SQL_BYTES,
    ProjectionDiagnostic,
    CanonicalizationManifest,
    ProjectionStatus,
    ProjectionResult,
    PublicationError,
    STORAGE_PROJECTION_VERSION,
    RepositoryImportArtifactInput,
    RepositoryImportColumn,
    RepositoryImportTable,
    REPLAY_SQL_ENTRY_NAME,
    WrittenImportPackage,
    open_canonicalization_manifest,
    publish_canonicalization,
    render_repository_import_schema_replay_sql,
    validate_repository_import_package,
    open_storage_input,
    StorageInputLease,
    compute_manifest_digest,
)
from gateway_backend.capabilities.storage_projection.contracts import (
    CanonicalizationManifestTable,
)
from gateway_backend.capabilities.table_rules import (
    CanonicalKeyPolicy,
    ORDERED_IDENTITY_COLUMN,
    ORDERED_POSITION_COLUMN,
    OrderedPolicy,
    StorageRuleView,
    migrated_table_ruleset_snapshot,
)
from gateway_backend.capabilities.table_rules.contracts import TABLE_RULESET_VERSION, TableRulesetSnapshot
from gateway_backend.domain.submission.models import BackendArtifactRef, BuilderMutationPolicy

__all__ = [
    "MANIFEST_ENTRY_NAME",
    "REPLAY_SQL_ENTRY_NAME",
    "RepositoryImportArtifactError",
    "SubmitImportPublicationAdapter",
    "WrittenImportPackage",
]

_LOG = logging.getLogger(__name__)


class RepositoryImportArtifactError(ValueError):
    """Raised when a v1 import package cannot be written."""


def _reserve_submit_stage(name: str, upper: int) -> None:
    context = current_kernel_context()
    if context is None:
        raise ValueError("Submit allocation requires an operation kernel context")
    context.checkpoint()
    context.memory.record_stage_admission(name, upper)
    context.resources.enter_context(context.memory.reserve(upper))


def _format_projection_diagnostics(prefix: str, diagnostics: tuple[ProjectionDiagnostic, ...]) -> str:
    if not diagnostics:
        return f"{prefix}: FAILED"
    first = diagnostics[0]
    table_suffix = f" (table={first.table_name})" if first.table_name else ""
    message = f"{prefix}: {first.code.value}: {first.message}{table_suffix}"
    if len(diagnostics) > 1:
        also = "; ".join(
            f"{item.code.value}:{item.message}"
            + (f"@{item.table_name}" if item.table_name else "")
            for item in diagnostics[1:3]
        )
        message += f"; also={also}"
        if len(diagnostics) > 3:
            message += f"; diagnostics={len(diagnostics)}"
    return message


class SubmitImportPublicationAdapter:
    """ADAPTIVE_PATCH adapter over Storage Projection and Mutation Planning."""

    def __init__(
        self,
        *,
        repository_provider_factory: Callable[[str, str], RepositoryTableAccessProvider] | None = None,
        committed_table_factory: Callable[[ArtifactStorePort, str], CommittedCanonicalTablesPort] | None = None,
    ) -> None:
        self._repository_provider_factory = repository_provider_factory
        self._committed_tables = committed_table_factory

    def build_and_publish(
        self,
        *,
        build_input: PrepareImportBuildInput,
        store: ArtifactStorePort,
    ) -> PrepareImportPublicationResult:
        context = current_kernel_context()
        if context is None:
            raise ValueError("Submit publication requires an operation kernel context")
        upper = MAX_MANIFEST_JSON_BYTES * 32 + MAX_REPLAY_SQL_BYTES * 10 + 16 * 1024**2
        context.memory.record_stage_admission("submit-package-replay", upper)
        with context.memory.reserve(upper):
            return self._build_and_publish_from_inputs(build_input=build_input, store=store)

    def _build_and_publish_from_inputs(
        self,
        *,
        build_input: PrepareImportBuildInput,
        store: ArtifactStorePort,
    ) -> PrepareImportPublicationResult:
        context = current_kernel_context()
        if context is None:
            raise ValueError("Submit publication requires an operation kernel context")
        _assert_adaptive_policy(build_input)
        frozen_manifest = _open_frozen_manifest(build_input, store=store)
        parent_manifest = _parent_manifest_for_plan(build_input, frozen_manifest)
        changed_names = _changed_table_names(
            parent_manifest,
            frozen_manifest,
            parent_is_initial=build_input.parent_is_initial,
        )
        expected_removed = tuple(
            sorted(
                {table.name for table in parent_manifest.tables}
                - {table.name for table in frozen_manifest.tables},
                key=lambda item: item.encode("utf-8"),
            )
        )
        if expected_removed != build_input.removed_tables:
            raise SubmitImportPublicationError(
                "removed table set does not match parent and input manifests"
            )
        if (
            frozen_manifest.manifest_digest is None
            or frozen_manifest.manifest_digest.value != build_input.canonicalization_manifest_digest
            or frozen_manifest.storage_projection_version != STORAGE_PROJECTION_VERSION
        ):
            raise SubmitImportPublicationError("frozen canonicalization manifest binding mismatch")
        if not frozen_manifest.tables and frozen_manifest.source_artifact_digest.value != build_input.source_artifact_digest:
            raise SubmitImportPublicationError("source_artifact_digest does not match frozen manifest")
        frozen_by_name = {item.name: item for item in frozen_manifest.tables}
        bindings = {item.table_name: item for item in build_input.snapshot_tables}
        if len(bindings) != len(build_input.snapshot_tables) or set(bindings) != set(frozen_by_name):
            raise SubmitImportPublicationError("canonical table artifacts do not match frozen manifest")
        parent_by_name = {item.name: item for item in parent_manifest.tables}
        changed = set(changed_names)
        parent_read_names = frozenset(
            name for name in changed_names
            if name in frozen_by_name and name in parent_by_name
            and parent_manifest.storage_projection_version == frozen_manifest.storage_projection_version
            and parent_by_name[name].canonical_row_count > 0
            and _patch_comparable(parent_by_name[name], frozen_by_name[name])
        )
        parent_access: tuple[TableRulesetSnapshot, CanonicalBinding, CommittedCanonicalTablesPort] | None = None
        if parent_read_names:
            if self._repository_provider_factory is None or self._committed_tables is None:
                raise SubmitImportPublicationError("Repository parent row access is unavailable")
            parent_ruleset = migrated_table_ruleset_snapshot()
            if parent_ruleset.ruleset_digest != parent_manifest.ruleset_digest:
                raise SubmitImportPublicationError("parent manifest ruleset does not match runtime ruleset")
            parent_access = (
                parent_ruleset, _canonical_binding_from_manifest(parent_manifest),
                self._committed_tables(store, build_input.repository_id),
            )
        projected_tables: list[ProjectionTable] = []
        import_tables: list[RepositoryImportTable] = []
        rebuild_tables: list[str] = []
        dml_chunks: list[bytes] = []
        dml_size = 0
        parent_reads = 0
        storage_noops = 0
        try:
            for name in sorted(frozen_by_name, key=lambda value: value.encode("utf-8")):
                context.checkpoint()
                frozen = frozen_by_name[name]
                table_started = monotonic()
                memory_before = context.memory.used_bytes
                table_metrics: dict[str, object] | None = None
                table = _open_frozen_table(bindings[name], frozen, build_input, store)
                try:
                    import_table, projected = _frozen_table_metadata(table, frozen)
                    import_tables.append(import_table)
                    projected_tables.append(projected)
                    if name not in changed:
                        continue
                    before_manifest_table = parent_by_name.get(name)
                    parent_table: SnapshotTable | None = None
                    before_lease: StorageInputLease | None = None
                    after_lease: StorageInputLease | None = None
                    table_sql_start = dml_size
                    parent_elapsed = 0.0
                    try:
                        if name in parent_read_names:
                            assert parent_access is not None
                            parent_started = monotonic()
                            parent_table = self._materialize_parent_table(
                                build_input, table_name=name, parent_access=parent_access,
                            )
                            parent_elapsed = monotonic() - parent_started
                            parent_reads += 1
                        before_side = None if before_manifest_table is None else StorageTableSideV1(
                            before_manifest_table, _storage_view_from_frozen_table(before_manifest_table),
                            parent_manifest.storage_projection_version,
                            metadata_manifest=parent_manifest,
                        )
                        if parent_table is not None and before_side is not None and before_manifest_table is not None:
                            before_lease = open_storage_input(parent_table, parent_manifest,
                                                              before_manifest_table, context)
                            before_side = replace(before_side, stream=before_lease.stream,
                                                  schema=before_lease.schema, input_owner=before_lease)
                        after_lease = open_storage_input(table, frozen_manifest, frozen, context)
                        after_side = StorageTableSideV1(
                            frozen, _storage_view_from_frozen_table(frozen),
                            frozen_manifest.storage_projection_version,
                            after_lease.stream, after_lease.schema, after_lease, frozen_manifest,
                        )
                        task = StorageTableTaskV1(name, before_side, after_side, import_table)
                        prepare_started = monotonic()
                        with prepare_storage_table(task, context) as handle:
                            summary = handle.summary()
                            decision = choose_table_mutation(
                                task, summary, policy=MutationPolicy.ADAPTIVE_PATCH,
                                threshold=MutationThresholdPolicy(),
                            )
                            prepare_elapsed = monotonic() - prepare_started
                            if decision.operation is TableMutationKind.REBUILD_TABLE:
                                rebuild_tables.append(name)
                            elif decision.operation is TableMutationKind.NOOP:
                                storage_noops += 1
                            render_started = monotonic()
                            for chunk in handle.render(decision):
                                if len(chunk) > MAX_REPLAY_SQL_BYTES - dml_size:
                                    raise SubmitImportPublicationError("repository replay SQL exceeds 200 MiB")
                                dml_chunks.append(chunk)
                                dml_size += len(chunk)
                            render_elapsed = monotonic() - render_started
                            counts = summary.net_counts
                            table_metrics = {
                                "event": "submit_storage_table", "table": name,
                                "decision": decision.operation.value, "reason": decision.reason,
                                "before_rows": summary.before_rows, "after_rows": summary.after_rows,
                                "net_inserted": None if counts is None else counts.inserted,
                                "net_updated": None if counts is None else counts.updated,
                                "net_deleted": None if counts is None else counts.deleted,
                                "parent_read": int(parent_table is not None), "native_calls": 2,
                                "sql_bytes": dml_size - table_sql_start,
                                "parent_seconds": round(parent_elapsed, 6),
                                "storage_diff_seconds": round(prepare_elapsed, 6),
                                "sql_render_seconds": round(render_elapsed, 6),
                            }
                    finally:
                        try:
                            if before_lease is not None:
                                before_lease.close()
                        finally:
                            try:
                                if after_lease is not None:
                                    after_lease.close()
                            finally:
                                if parent_table is not None:
                                    _close_snapshot_table(parent_table)
                finally:
                    _close_snapshot_table(table)
                    if table_metrics is not None:
                        table_metrics["total_seconds"] = round(monotonic() - table_started, 6)
                        table_metrics["memory_before_bytes"] = memory_before
                        table_metrics["memory_after_bytes"] = context.memory.used_bytes
                        table_metrics["memory_high_water_bytes"] = context.memory.high_water_bytes
                        _LOG.info("%s", json.dumps(table_metrics, sort_keys=True, separators=(",", ":")))
            full_import_input = RepositoryImportArtifactInput(
                package_version=PACKAGE_VERSION,
                canonicalization_manifest_digest=frozen_manifest.manifest_digest,
                tables=tuple(import_tables),
            )
            projection = ProjectionResult(
                status=ProjectionStatus.COMPLETE,
                tables=tuple(projected_tables),
                omitted_diagnostic_count=0,
                manifest=frozen_manifest,
                import_input=full_import_input,
            )
            rebuild_set = set(rebuild_tables)
            schema_import_input = RepositoryImportArtifactInput(
                package_version=full_import_input.package_version,
                canonicalization_manifest_digest=full_import_input.canonicalization_manifest_digest,
                tables=tuple(
                    table for table in full_import_input.tables if table.name in rebuild_set
                ),
            )
            schema_sql = render_repository_import_schema_replay_sql(
                schema_import_input,
                removed_tables=build_input.removed_tables,
                context=context,
            )
            if len(schema_sql) > MAX_REPLAY_SQL_BYTES - dml_size:
                raise SubmitImportPublicationError("repository replay SQL exceeds 200 MiB")
            replay_sql = schema_sql + b"".join(dml_chunks)
            _LOG.info("%s", json.dumps({
                "event": "submit_storage_summary",
                "manifest_candidates": len(changed_names), "storage_noops": storage_noops,
                "replay_tables": len(changed_names) - len(build_input.removed_tables) - storage_noops,
                "parent_reads": parent_reads, "ddl_bytes": len(schema_sql),
                "dml_bytes": dml_size, "sql_bytes": len(replay_sql),
                "memory_used_bytes": context.memory.used_bytes,
                "memory_high_water_bytes": context.memory.high_water_bytes,
            }, sort_keys=True, separators=(",", ":")))
        except SubmitImportPublicationError:
            raise
        except (ProjectionImportReplayError, ValueError) as exc:
            raise SubmitImportPublicationError(str(exc)) from exc
        context.checkpoint()
        publish_started = monotonic()
        published = publish_canonicalization(
            projection,
            store=store,
            replay_sql=replay_sql,
            context=ProjectionInvocationContext(cancel_requested=context.cancel_probe, deadline_monotonic=context.deadline_monotonic),
        )
        context.checkpoint()
        _LOG.info("%s", json.dumps({
            "event": "submit_package_publish", "elapsed_seconds": round(monotonic() - publish_started, 6),
            "sql_bytes": len(replay_sql), "memory_used_bytes": context.memory.used_bytes,
            "memory_high_water_bytes": context.memory.high_water_bytes,
            "status": published.status.value,
        }, sort_keys=True, separators=(",", ":")))
        if published.status is not ProjectionStatus.COMPLETE or published.publication is None:
            raise SubmitImportPublicationError(
                _format_projection_diagnostics(
                    "canonical publication failed",
                    published.diagnostics,
                )
            )
        publication = published.publication
        package_ref = _backend_ref_from_store_ref(publication.package_ref)
        manifest_ref = _backend_ref_from_store_ref(publication.manifest_ref)
        checkpoint = PrepareImportCheckpoint(
            schema_version=PREPARE_IMPORT_CHECKPOINT_SCHEMA,
            attempt_id=build_input.submit_attempt_id,
            canonical_table_set_closure_ref=build_input.canonical_table_set_closure_ref.artifact_id,
            canonical_table_set_closure_digest=build_input.canonical_table_set_closure_digest,
            input_canonicalization_manifest_ref=(
                build_input.canonicalization_manifest_ref.artifact_id
            ),
            input_canonicalization_manifest_digest=build_input.canonicalization_manifest_digest,
            expected_parent_commit_id=build_input.expected_parent_commit_id,
            parent_manifest_digest=build_input.parent_manifest_digest,
            parent_is_initial=build_input.parent_is_initial,
            removed_tables=build_input.removed_tables,
            canonicalization_manifest_ref=manifest_ref,
            canonicalization_manifest_digest=publication.manifest_digest.value,
            backend_import_artifact_ref=package_ref,
            package_raw_size=package_ref.size_bytes,
            package_raw_sha256=package_ref.raw_sha256,
            builder_mutation_policy=build_input.builder_mutation_policy,
        )
        return PrepareImportPublicationResult(checkpoint=checkpoint, replay=False)

    def _materialize_parent_table(
        self,
        build_input: PrepareImportBuildInput,
        *,
        table_name: str,
        parent_access: tuple[TableRulesetSnapshot, CanonicalBinding, CommittedCanonicalTablesPort],
    ) -> SnapshotTable:
        if self._repository_provider_factory is None:
            raise SubmitImportPublicationError("Repository parent row provider is unavailable")
        runtime_ruleset, binding, committed_tables = parent_access
        context = current_kernel_context()
        if context is None:
            raise ValueError("Submit parent reads require an operation kernel context")
        request = RepositoryRefMaterializationRequest(
            repository_ref=RepositoryRef(
                repository_id=build_input.repository_id,
                ref=build_input.expected_parent_commit_id,
            ),
            provider=self._repository_provider_factory(
                build_input.repository_id,
                build_input.expected_parent_commit_id,
            ),
            ruleset=runtime_ruleset,
            canonical_binding=binding,
            table_ruleset_version=TABLE_RULESET_VERSION,
            materialization_stage=MaterializationStage.FINAL,
            policy=MaterializationPolicy.READERS_REQUIRED,
            context=ParserInvocationContext(context.cancel_probe, context.deadline_monotonic),
            requested_tables=(table_name,),
            committed_tables=committed_tables,
        )
        result = materialize_repository_ref(request)
        if result.status is not SnapshotMaterializationStatus.COMPLETE or result.table_set is None:
            diagnostic = result.diagnostics[0] if result.diagnostics else None
            raise SubmitImportPublicationError(
                "parent rows could not be materialized"
                if diagnostic is None
                else diagnostic.message
            )
        if (
            result.snapshot is None
            or result.snapshot.source_context is None
            or result.snapshot.source_context.resolved_commit_hash != build_input.expected_parent_commit_id
            or len(result.table_set.tables) != 1
            or result.table_set.tables[0].descriptor.table_name != table_name
        ):
            for table in result.table_set.tables:
                _close_snapshot_table(table)
            raise SubmitImportPublicationError("parent rows do not match the frozen exact commit")
        return result.table_set.tables[0]

    def read_back_package(
        self,
        *,
        checkpoint: PrepareImportCheckpoint,
        store: ArtifactStorePort,
    ) -> bytes:
        started = monotonic()
        ref = ArtifactRef(
            artifact_id=checkpoint.backend_import_artifact_ref.artifact_id,
            media_type=checkpoint.backend_import_artifact_ref.media_type,
            size_bytes=checkpoint.backend_import_artifact_ref.size_bytes,
            raw_sha256=DigestRef(checkpoint.backend_import_artifact_ref.raw_sha256),
        )
        _reserve_submit_stage("submit-package-readback-bytes", ref.size_bytes * 2 + 128 * 1024)
        try:
            payload = store.locate(ref)
        except ManifestVerificationError as exc:
            raise SubmitImportPublicationError(str(exc) or "import package is missing or corrupt") from exc
        if raw_blob_digest(payload).value != checkpoint.package_raw_sha256:
            raise SubmitImportPublicationError("read-back package raw SHA mismatch")
        if len(payload) != checkpoint.package_raw_size:
            raise SubmitImportPublicationError("read-back package size mismatch")
        _LOG.info("%s", json.dumps({
            "event": "submit_package_readback", "elapsed_seconds": round(monotonic() - started, 6),
            "package_bytes": len(payload),
        }, sort_keys=True, separators=(",", ":")))
        return payload

    def verify_checkpoint_semantic_binding(
        self,
        *,
        checkpoint: PrepareImportCheckpoint,
        store: ArtifactStorePort,
    ) -> None:
        started = monotonic()
        context = current_kernel_context()
        if context is None:
            raise ValueError("Submit verification requires an operation kernel context")
        upper = MAX_MANIFEST_JSON_BYTES * 32 + MAX_REPLAY_SQL_BYTES * 6 + 16 * 1024**2
        context.memory.record_stage_admission("submit-package-verify", upper)
        with context.memory.reserve(upper):
            manifest_ref = ArtifactRef(
                artifact_id=checkpoint.canonicalization_manifest_ref.artifact_id,
                media_type=checkpoint.canonicalization_manifest_ref.media_type,
                size_bytes=checkpoint.canonicalization_manifest_ref.size_bytes,
                raw_sha256=DigestRef(checkpoint.canonicalization_manifest_ref.raw_sha256),
            )
            try:
                manifest = open_canonicalization_manifest(store, manifest_ref)
            except PublicationError as exc:
                raise SubmitImportPublicationError(str(exc)) from exc
            if manifest.manifest_digest is None:
                raise SubmitImportPublicationError("stored manifest is missing manifest_digest")
            semantic_digest = manifest.manifest_digest.value
            if semantic_digest != checkpoint.canonicalization_manifest_digest:
                raise SubmitImportPublicationError(
                    "checkpoint semantic manifest digest does not match stored manifest"
                )
            package_ref = ArtifactRef(
                artifact_id=checkpoint.backend_import_artifact_ref.artifact_id,
                media_type=checkpoint.backend_import_artifact_ref.media_type,
                size_bytes=checkpoint.backend_import_artifact_ref.size_bytes,
                raw_sha256=DigestRef(checkpoint.backend_import_artifact_ref.raw_sha256),
            )
            try:
                package_payload = store.locate(package_ref)
            except ManifestVerificationError as exc:
                raise SubmitImportPublicationError(str(exc) or "import package is missing or corrupt") from exc
            import_input = validate_repository_import_package(package_payload)
            if import_input.canonicalization_manifest_digest.value != checkpoint.canonicalization_manifest_digest:
                raise SubmitImportPublicationError(
                    "package manifest digest does not match checkpoint semantic digest"
                )
        _LOG.info("%s", json.dumps({
            "event": "submit_checkpoint_verify", "elapsed_seconds": round(monotonic() - started, 6),
            "package_bytes": package_ref.size_bytes,
        }, sort_keys=True, separators=(",", ":")))


def _assert_adaptive_policy(build_input: PrepareImportBuildInput) -> None:
    if build_input.builder_mutation_policy is not BuilderMutationPolicy.ADAPTIVE_PATCH:
        raise SubmitImportPublicationError("builder_mutation_policy must be ADAPTIVE_PATCH")


def _parent_manifest_for_plan(
    build_input: PrepareImportBuildInput,
    current_manifest: CanonicalizationManifest,
) -> CanonicalizationManifest:
    if build_input.parent_is_initial:
        if build_input.parent_manifest is not None or build_input.parent_manifest_digest is not None:
            raise SubmitImportPublicationError("INITIAL parent must not carry a canonical manifest")
        return CanonicalizationManifest(
            contract_version=current_manifest.contract_version,
            storage_projection_version=current_manifest.storage_projection_version,
            ruleset_id=current_manifest.ruleset_id,
            ruleset_version=current_manifest.ruleset_version,
            ruleset_digest=current_manifest.ruleset_digest,
            source_artifact_digest=current_manifest.source_artifact_digest,
            tables=(),
            manifest_digest=DigestRef("sha256:" + "0f" * 32),
        )
    parent_manifest = build_input.parent_manifest
    if (
        parent_manifest is None
        or parent_manifest.manifest_digest is None
        or parent_manifest.manifest_digest.value != build_input.parent_manifest_digest
        or compute_manifest_digest(parent_manifest) != parent_manifest.manifest_digest
    ):
        raise SubmitImportPublicationError("parent manifest does not match its frozen digest")
    return parent_manifest


def _changed_table_names(
    before: CanonicalizationManifest,
    after: CanonicalizationManifest,
    *,
    parent_is_initial: bool,
) -> tuple[str, ...]:
    before_tables = {table.name: table for table in before.tables}
    after_tables = {table.name: table for table in after.tables}
    if parent_is_initial or before.storage_projection_version != after.storage_projection_version:
        names = before_tables.keys() | after_tables.keys()
    else:
        names = {
            name
            for name in before_tables.keys() | after_tables.keys()
            if name not in before_tables
            or name not in after_tables
            or not _manifest_table_identity_equal(
                before_tables[name],
                after_tables[name],
            )
        }
    return tuple(sorted(names, key=lambda item: item.encode("utf-8")))


def _manifest_table_identity_equal(
    before: CanonicalizationManifestTable,
    current: CanonicalizationManifestTable,
) -> bool:
    return (
        before.canonical_row_count == current.canonical_row_count
        and before.source_schema_digest == current.source_schema_digest
        and before.canonical_schema_digest == current.canonical_schema_digest
        and before.content_digest == current.content_digest
        and _storage_views_compatible(
            _storage_view_from_frozen_table(before),
            _storage_view_from_frozen_table(current),
        )
    )


def _patch_comparable(
    before: CanonicalizationManifestTable,
    current: CanonicalizationManifestTable,
) -> bool:
    view = _storage_view_from_frozen_table(before)
    return (
        before.canonical_schema_digest is not None
        and before.canonical_schema_digest == current.canonical_schema_digest
        and _storage_views_compatible(
            view,
            _storage_view_from_frozen_table(current),
        )
        and view.canonical_key_policy
        not in {CanonicalKeyPolicy.NONE, CanonicalKeyPolicy.EXPLICIT_KEYLESS}
        and bool(view.canonical_key_columns)
        and view.ordered_policy in {OrderedPolicy.NONE, OrderedPolicy.GID_NO_V1}
    )


def _storage_views_compatible(left: StorageRuleView, right: StorageRuleView) -> bool:
    return (
        left.canonical_key_policy == right.canonical_key_policy
        and left.ordered_policy == right.ordered_policy
        and left.retained_columns == right.retained_columns
        and left.canonical_key_columns == right.canonical_key_columns
        and left.dropped_columns == right.dropped_columns
        and left.structural_columns == right.structural_columns
    )


def _canonical_binding_from_manifest(manifest: CanonicalizationManifest) -> CanonicalBinding:
    if any(
        table.source_schema_digest is None
        or table.canonical_schema_digest is None
        or table.content_digest is None
        for table in manifest.tables
    ):
        raise SubmitImportPublicationError("parent manifest is missing table identity facts")
    tables = tuple(
        _storage_view_from_frozen_table(table)
        for table in sorted(manifest.tables, key=lambda item: item.name.encode("utf-8"))
    )
    identities = tuple(
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
    )
    return CanonicalBinding(
        storage_projection_version=manifest.storage_projection_version,
        ruleset_id=manifest.ruleset_id,
        ruleset_version=manifest.ruleset_version,
        ruleset_digest=manifest.ruleset_digest,
        tables=tables,
        table_identities=identities,
    )


def _backend_ref_from_store_ref(ref: ArtifactRef) -> BackendArtifactRef:
    if type(ref) is not ArtifactRef:
        raise SubmitImportPublicationError("published artifact ref is invalid")
    return BackendArtifactRef(
        artifact_id=ref.artifact_id,
        media_type=ref.media_type,
        size_bytes=ref.size_bytes,
        raw_sha256=ref.raw_sha256.value,
    )


def _close_snapshot_table(table: SnapshotTable) -> None:
    try:
        if table.batch_reader is not None:
            table.batch_reader.close()
    finally:
        if table.reader is not None:
            table.reader.close()


def _open_frozen_table(
    binding: SnapshotTableBinding,
    manifest_table: CanonicalizationManifestTable,
    build_input: PrepareImportBuildInput,
    store: ArtifactStorePort,
) -> SnapshotTable:
    try:
        ref = ArtifactRef(
            artifact_id=binding.artifact_id,
            media_type=binding.media_type,
            size_bytes=binding.size_bytes,
            raw_sha256=DigestRef(binding.raw_sha256),
        )
        table = open_snapshot_table_artifact(
            store, ref, repository_id=build_input.repository_id, canonical_required=True,
        )
    except (InterruptedError, TimeoutError, MemoryError):
        raise
    except (ArtifactPublishError, ManifestVerificationError, OSError, ValueError) as exc:
        raise SubmitImportPublicationError(
            f"frozen canonical table {binding.table_name} is unavailable or corrupt"
        ) from exc
    try:
        if table.reader is None or table.artifact is None:
            raise SubmitImportPublicationError("frozen canonical table has no reader or artifact")
        descriptor = table.descriptor
        try:
            raw_manifest = store.locate(table.artifact.manifest_ref)
        except (ManifestVerificationError, OSError) as exc:
            raise SubmitImportPublicationError(
                f"frozen canonical table {binding.table_name} manifest is unavailable or corrupt"
            ) from exc
        if table.artifact.manifest_ref.raw_sha256 != raw_blob_digest(raw_manifest):
            raise SubmitImportPublicationError("frozen canonical table manifest raw SHA mismatch")
        if (
            descriptor.table_name != binding.table_name
            or descriptor.table_name != manifest_table.name
            or descriptor != table.artifact.manifest.descriptor
            or descriptor.row_count != manifest_table.canonical_row_count
            or descriptor.raw_content_digest != manifest_table.content_digest
            or tuple(column.name for column in descriptor.columns) != manifest_table.retained_columns
            or descriptor.primary_key_columns != manifest_table.canonical_key_columns
            or descriptor.compare_key_columns != manifest_table.canonical_key_columns
            or table.artifact.manifest.snapshot_digest.value != build_input.source_artifact_digest
        ):
            raise SubmitImportPublicationError(
                f"canonical table artifact {binding.table_name} does not match frozen facts"
            )
        schema_columns = _schema_columns_from_descriptor(descriptor, manifest_table)
        if _schema_digest(schema_columns, manifest_table.canonical_key_columns) != manifest_table.canonical_schema_digest:
            raise SubmitImportPublicationError(
                f"canonical table artifact {binding.table_name} schema does not match frozen manifest"
            )
        return table
    except BaseException:
        _close_snapshot_table(table)
        raise


def _frozen_table_metadata(
    table: SnapshotTable, manifest_table: CanonicalizationManifestTable,
) -> tuple[RepositoryImportTable, ProjectionTable]:
    descriptor = table.descriptor
    columns = _schema_columns_from_descriptor(descriptor, manifest_table)
    return (
        RepositoryImportTable(
            name=manifest_table.name,
            columns=tuple(
                RepositoryImportColumn(
                    name=str(column["name"]), sql_type=str(column["sql_type"]),
                    nullable=bool(column["nullable"]),
                )
                for column in columns
            ),
            primary_key=manifest_table.canonical_key_columns,
            row_count=manifest_table.canonical_row_count,
        ),
        ProjectionTable(
            canonical_table=manifest_table.name,
            storage_view=_storage_view_from_frozen_table(manifest_table),
            row_count=manifest_table.canonical_row_count,
            schema_digest=manifest_table.canonical_schema_digest,
            content_digest=manifest_table.content_digest,
        ),
    )


def _storage_view_from_frozen_table(table: CanonicalizationManifestTable) -> StorageRuleView:
    view = StorageRuleView(
        canonical_table=table.name,
        canonical_key_policy=table.canonical_key_policy,
        ordered_policy=table.ordered_policy,
        dropped_columns=table.dropped_columns,
        structural_columns=table.structural_columns,
        retained_columns=table.retained_columns,
        canonical_key_columns=table.canonical_key_columns,
    )
    payload = {
        "canonical_key_columns": list(view.canonical_key_columns),
        "canonical_key_policy": view.canonical_key_policy.value,
        "canonical_table": view.canonical_table,
        "dropped_columns": [
            {"name": item.name, "reason": item.reason} for item in view.dropped_columns
        ],
        "ordered_policy": view.ordered_policy.value,
        "retained_columns": list(view.retained_columns),
        "structural_columns": list(view.structural_columns),
    }
    return replace(
        view,
        storage_rule_digest=DigestRef.from_raw_digest(
            hashlib.sha256(canonicalize_json_value(payload)).digest()
        ),
    )


def _schema_columns_from_descriptor(
    descriptor: SnapshotTableDescriptor,
    table: CanonicalizationManifestTable,
) -> list[dict[str, object]]:
    non_null = set(table.canonical_key_columns)
    if table.ordered_policy is OrderedPolicy.GID_NO_V1:
        non_null.add(ORDERED_POSITION_COLUMN)
    result: list[dict[str, object]] = []
    for column in descriptor.columns:
        name = column.name
        sql_type = column.scalar_type
        nullable = column.nullable
        if sql_type is None:
            raise SubmitImportPublicationError(
                f"canonical table descriptor for {table.name} has an invalid column"
            )
        if table.ordered_policy is OrderedPolicy.GID_NO_V1 and name == ORDERED_IDENTITY_COLUMN:
            sql_type = "INT UNSIGNED"
        result.append(
            {
                "name": name,
                "nullable": nullable and name not in non_null,
                "sql_type": sql_type,
            }
        )
    return result


def _schema_digest(
    columns: list[dict[str, object]],
    primary_key: tuple[str, ...],
) -> DigestRef:
    payload = {
        "columns": columns,
        "primary_key": list(primary_key),
    }
    return DigestRef.from_raw_digest(
        hashlib.sha256(canonicalize_json_value(payload)).digest()
    )


def _open_frozen_manifest(
    build_input: PrepareImportBuildInput,
    *,
    store: ArtifactStorePort,
) -> CanonicalizationManifest:
    try:
        return open_canonicalization_manifest(store, build_input.canonicalization_manifest_ref)
    except PublicationError as exc:
        raise SubmitImportPublicationError(str(exc)) from exc
