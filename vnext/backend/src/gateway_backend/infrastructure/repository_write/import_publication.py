"""RepositoryImportArtifact v1 writer and Submit import publication adapter."""

from __future__ import annotations

import hashlib
import base64
from collections.abc import Callable
from dataclasses import replace

from gateway_shared_kernel import (
    DateTimeScalar,
    DateScalar,
    TimestampScalar,
    TimeDurationScalar,
    DecimalScalar,
    BooleanScalar,
    BinaryScalar,
    BitScalar,
    DigestRef,
    Float32Scalar,
    Float64Scalar,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    UnsignedIntegerScalar,
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
    ImportReplayError as MutationImportReplayError,
    CanonicalStorageKey,
    MutationKeyedRow,
    MutationPolicy,
    MutationTableSnapshot,
    PersistedRowImage,
    TableMutationKind,
    build_import_mutation_snapshots,
    plan_import_mutation,
    render_planned_import_mutation_dml,
)
from gateway_backend.capabilities.snapshot_materialization import (
    SqlSetValue,
    enum_set_labels_for_sql_spelling,
    materialize_repository_ref,
    open_snapshot_table_artifact,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ArtifactSourceBinding,
    CanonicalBinding,
    CanonicalTableIdentity,
    MaterializationPolicy,
    MaterializationStage,
    RepositoryRef,
    RepositoryRefMaterializationRequest,
    RepositoryTableAccessProvider,
    SnapshotMaterializationStatus,
    SnapshotTable,
    SnapshotTableDescriptor,
    SnapshotTableReader,
)
from gateway_backend.capabilities.mutation_planning._digest import (
    key_bytes_for_ordering,
    row_digest_from_image,
)
from gateway_backend.capabilities.table_access.contracts import (
    ParserInvocationContext,
)
from gateway_backend.capabilities.storage_projection import (
    MANIFEST_ENTRY_NAME,
    PACKAGE_VERSION,
    ImportReplayError as ProjectionImportReplayError,
    ProjectionTable,
    ProjectionInvocationContext,
    ProjectionDiagnostic,
    CanonicalizationManifest,
    ProjectionStatus,
    ProjectionTableInput,
    ProjectionResult,
    PublicationError,
    STORAGE_PROJECTION_VERSION,
    RepositoryImportArtifactInput,
    RepositoryImportColumn,
    RepositoryImportTable,
    REPLAY_SQL_ENTRY_NAME,
    WrittenImportPackage,
    NeverCancel,
    open_canonicalization_manifest,
    publish_canonicalization,
    render_repository_import_schema_replay_sql,
    validate_repository_import_package,
)
from gateway_backend.capabilities.storage_projection.contracts import (
    CanonicalizationManifestTable,
    ImportReplayKeyedRow,
    ImportReplayTableSnapshot,
)
from gateway_backend.capabilities.table_rules import (
    CanonicalKeyPolicy,
    ORDERED_IDENTITY_COLUMN,
    ORDERED_POSITION_COLUMN,
    OrderedPolicy,
    StorageRuleView,
    migrated_table_ruleset_snapshot,
)
from gateway_backend.capabilities.table_rules.contracts import TABLE_RULESET_VERSION
from gateway_backend.domain.submission.models import BackendArtifactRef, BuilderMutationPolicy

__all__ = [
    "MANIFEST_ENTRY_NAME",
    "REPLAY_SQL_ENTRY_NAME",
    "RepositoryImportArtifactError",
    "SubmitImportPublicationAdapter",
    "WrittenImportPackage",
]


class RepositoryImportArtifactError(ValueError):
    """Raised when a v1 import package cannot be written."""


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
    ) -> None:
        self._repository_provider_factory = repository_provider_factory

    def build_and_publish(
        self,
        *,
        build_input: PrepareImportBuildInput,
        store: ArtifactStorePort,
    ) -> PrepareImportPublicationResult:
        projection_inputs = _open_projection_inputs(build_input.snapshot_tables, store=store)
        try:
            return self._build_and_publish_from_inputs(
                build_input=build_input,
                store=store,
                projection_inputs=projection_inputs,
            )
        finally:
            for item in projection_inputs:
                try:
                    item.reader.close()
                except Exception:
                    continue

    def _build_and_publish_from_inputs(
        self,
        *,
        build_input: PrepareImportBuildInput,
        store: ArtifactStorePort,
        projection_inputs: tuple[ProjectionTableInput, ...],
    ) -> PrepareImportPublicationResult:
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
        projection, projection_snapshots = _build_frozen_projection(
            build_input,
            projection_inputs,
            frozen_manifest=frozen_manifest,
            mutation_table_names=frozenset(changed_names),
            store=store,
        )
        if projection.import_input is None:
            raise SubmitImportPublicationError("frozen projection import input is missing")
        try:
            after_by_name = {item.manifest_table.name: item for item in build_import_mutation_snapshots(projection_snapshots)}
            changed_after = tuple(
                after_by_name[name]
                for name in sorted(changed_names, key=lambda item: item.encode("utf-8"))
                if name in after_by_name
            )
            before_rows = self._materialize_parent_rows(
                build_input,
                parent_manifest=parent_manifest,
                current_manifest=frozen_manifest,
                changed_names=changed_names,
            )
            before_manifest_tables = {item.name: item for item in parent_manifest.tables}
            before_snapshots: list[MutationTableSnapshot] = []
            for name in sorted(changed_names, key=lambda item: item.encode("utf-8")):
                before_table = before_manifest_tables.get(name)
                if before_table is None:
                    continue
                before_snapshots.append(
                    before_rows.get(name) or _empty_mutation_snapshot(before_table)
                )
            planned = plan_import_mutation(
                projection,
                changed_after,
                repository_base_digest=DigestRef(build_input.repository_base_digest),
                before_manifest=parent_manifest,
                before_snapshots=tuple(before_snapshots),
                mutation_policy=MutationPolicy.ADAPTIVE_PATCH,
            )
            rebuild_tables = (
                ()
                if planned.plan is None
                else tuple(
                    summary.canonical_table
                    for summary in planned.plan.table_summaries
                    if summary.operation is TableMutationKind.REBUILD_TABLE
                )
            )
            rebuild_set = set(rebuild_tables)
            schema_import_input = RepositoryImportArtifactInput(
                package_version=projection.import_input.package_version,
                canonicalization_manifest_digest=projection.import_input.canonicalization_manifest_digest,
                tables=tuple(
                    table for table in projection.import_input.tables if table.name in rebuild_set
                ),
            )
            schema_sql = render_repository_import_schema_replay_sql(
                schema_import_input,
                removed_tables=build_input.removed_tables,
            )
            mutation_dml = render_planned_import_mutation_dml(
                planned,
                rebuild_tables=rebuild_tables,
            )
            replay_sql = schema_sql + mutation_dml
        except (ProjectionImportReplayError, MutationImportReplayError) as exc:
            raise SubmitImportPublicationError(str(exc)) from exc
        published = publish_canonicalization(
            projection,
            store=store,
            replay_sql=replay_sql,
            context=ProjectionInvocationContext(cancel_requested=NeverCancel()),
        )
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

    def _materialize_parent_rows(
        self,
        build_input: PrepareImportBuildInput,
        *,
        parent_manifest: CanonicalizationManifest,
        current_manifest: CanonicalizationManifest,
        changed_names: tuple[str, ...],
    ) -> dict[str, MutationTableSnapshot]:
        if (
            build_input.parent_is_initial
            or parent_manifest.storage_projection_version != STORAGE_PROJECTION_VERSION
        ):
            return {}
        parent_tables = {item.name: item for item in parent_manifest.tables}
        current_tables = {item.name: item for item in current_manifest.tables}
        read_names = tuple(
            name
            for name in changed_names
            if name in parent_tables
            and name in current_tables
            and _patch_comparable(parent_tables[name], current_tables[name])
        )
        if not read_names:
            return {}
        if self._repository_provider_factory is None:
            raise SubmitImportPublicationError("Repository parent row provider is unavailable")
        runtime_ruleset = migrated_table_ruleset_snapshot()
        if runtime_ruleset.ruleset_digest != parent_manifest.ruleset_digest:
            raise SubmitImportPublicationError("parent manifest ruleset does not match runtime ruleset")
        binding = _canonical_binding_from_manifest(parent_manifest)
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
            context=ParserInvocationContext(NeverCancel()),
            requested_tables=read_names,
        )
        result = materialize_repository_ref(request)
        if result.status is not SnapshotMaterializationStatus.COMPLETE or result.table_set is None:
            diagnostic = result.diagnostics[0] if result.diagnostics else None
            raise SubmitImportPublicationError(
                "parent rows could not be materialized"
                if diagnostic is None
                else diagnostic.message
            )
        return _mutation_snapshots_from_repository(
            result.table_set.tables,
            parent_tables=parent_tables,
        )

    def read_back_package(
        self,
        *,
        checkpoint: PrepareImportCheckpoint,
        store: ArtifactStorePort,
    ) -> bytes:
        ref = ArtifactRef(
            artifact_id=checkpoint.backend_import_artifact_ref.artifact_id,
            media_type=checkpoint.backend_import_artifact_ref.media_type,
            size_bytes=checkpoint.backend_import_artifact_ref.size_bytes,
            raw_sha256=DigestRef(checkpoint.backend_import_artifact_ref.raw_sha256),
        )
        try:
            payload = store.locate(ref)
        except ManifestVerificationError as exc:
            raise SubmitImportPublicationError(str(exc) or "import package is missing or corrupt") from exc
        if raw_blob_digest(payload).value != checkpoint.package_raw_sha256:
            raise SubmitImportPublicationError("read-back package raw SHA mismatch")
        if len(payload) != checkpoint.package_raw_size:
            raise SubmitImportPublicationError("read-back package size mismatch")
        return payload

    def verify_checkpoint_semantic_binding(
        self,
        *,
        checkpoint: PrepareImportCheckpoint,
        store: ArtifactStorePort,
    ) -> None:
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


def _empty_mutation_snapshot(
    manifest_table: CanonicalizationManifestTable,
) -> MutationTableSnapshot:
    return MutationTableSnapshot(
        manifest_table=manifest_table,
        storage_view=_storage_view_from_frozen_table(manifest_table),
        rows=(),
    )


def _mutation_snapshots_from_repository(
    tables: tuple[SnapshotTable, ...],
    *,
    parent_tables: dict[str, CanonicalizationManifestTable],
) -> dict[str, MutationTableSnapshot]:
    snapshots: dict[str, MutationTableSnapshot] = {}
    for table in tables:
        name = table.descriptor.table_name
        manifest_table = parent_tables.get(name)
        if manifest_table is None:
            raise SubmitImportPublicationError("materialized parent table is absent from its manifest")
        reader = table.reader
        if reader is None:
            raise SubmitImportPublicationError(f"parent table {name} has no row reader")
        columns = table.descriptor.columns
        indexes = {column.name: index for index, column in enumerate(columns)}
        rows: list[MutationKeyedRow] = []
        try:
            if tuple(indexes) != manifest_table.retained_columns:
                raise SubmitImportPublicationError(
                    f"parent table {name} schema does not match its manifest"
                )
            for row in reader.iter_rows():
                if type(row) is not tuple or len(row) != len(columns):
                    raise SubmitImportPublicationError(f"parent table {name} row shape is invalid")
                image_columns: list[tuple[str, dict[str, object]]] = []
                for column_name in sorted(
                    manifest_table.retained_columns,
                    key=lambda item: item.encode("utf-8"),
                ):
                    column = columns[indexes[column_name]]
                    if column.scalar_type is None:
                        raise SubmitImportPublicationError(
                            f"parent table {name} column {column_name} has no scalar type"
                        )
                    image_columns.append(
                        (
                            column_name,
                            _mutation_cell_from_frozen_artifact(
                                row[indexes[column_name]],
                                column.scalar_type,
                            ),
                        )
                    )
                image = PersistedRowImage(columns=tuple(image_columns))
                image_by_name = {column: value for column, value in image_columns}
                key_columns = tuple(
                    (column, dict(image_by_name[column]))
                    for column in sorted(
                        manifest_table.canonical_key_columns,
                        key=lambda item: item.encode("utf-8"),
                    )
                )
                rows.append(
                    MutationKeyedRow(
                        key=CanonicalStorageKey(columns=key_columns),
                        image=image,
                        row_digest=row_digest_from_image(
                            image,
                            retained_columns=manifest_table.retained_columns,
                        ),
                    )
                )
        except SubmitImportPublicationError:
            raise
        except Exception as exc:
            raise SubmitImportPublicationError(f"parent table {name} rows are invalid") from exc
        finally:
            reader.close()
        rows.sort(key=lambda item: (key_bytes_for_ordering(item.key), item.row_digest.value))
        snapshots[name] = MutationTableSnapshot(
            manifest_table=manifest_table,
            storage_view=_storage_view_from_frozen_table(manifest_table),
            rows=tuple(rows),
        )
    return snapshots


def _backend_ref_from_store_ref(ref: ArtifactRef) -> BackendArtifactRef:
    if type(ref) is not ArtifactRef:
        raise SubmitImportPublicationError("published artifact ref is invalid")
    return BackendArtifactRef(
        artifact_id=ref.artifact_id,
        media_type=ref.media_type,
        size_bytes=ref.size_bytes,
        raw_sha256=ref.raw_sha256.value,
    )


def _build_frozen_projection(
    build_input: PrepareImportBuildInput,
    projection_inputs: tuple[ProjectionTableInput, ...],
    *,
    frozen_manifest: CanonicalizationManifest,
    mutation_table_names: frozenset[str],
    store: ArtifactStorePort,
) -> tuple[ProjectionResult, tuple[ImportReplayTableSnapshot, ...]]:
    if (
        frozen_manifest.manifest_digest is None
        or frozen_manifest.manifest_digest.value != build_input.canonicalization_manifest_digest
    ):
        raise SubmitImportPublicationError("frozen canonicalization manifest digest mismatch")
    if frozen_manifest.storage_projection_version != STORAGE_PROJECTION_VERSION:
        raise SubmitImportPublicationError("unsupported frozen storage_projection_version")
    if not frozen_manifest.tables and frozen_manifest.source_artifact_digest.value != (
        build_input.source_artifact_digest
    ):
        raise SubmitImportPublicationError("source_artifact_digest does not match frozen manifest")

    frozen_tables = {item.name: item for item in frozen_manifest.tables}
    inputs_by_name = {item.canonical_table: item for item in projection_inputs}
    expected_names = set(frozen_tables)
    if set(inputs_by_name) != expected_names:
        raise SubmitImportPublicationError("canonical table artifacts do not match frozen manifest")

    projected_tables: list[ProjectionTable] = []
    import_tables: list[RepositoryImportTable] = []
    replay_snapshots: list[ImportReplayTableSnapshot] = []
    reopened_readers: list[SnapshotTableReader] = []
    try:
        for table_name in sorted(expected_names, key=lambda value: value.encode("utf-8")):
            frozen_table = frozen_tables[table_name]
            item = inputs_by_name[table_name]
            if item.artifact is None:
                raise SubmitImportPublicationError(
                    f"canonical table artifact {table_name} is missing its manifest binding"
                )
            try:
                table_ref_payload = store.locate(item.artifact.manifest_ref)
                reader = item.reader.reopen()
                reopened_readers.append(reader)
                descriptor = reader.descriptor()
            except Exception as exc:
                raise SubmitImportPublicationError(
                    f"canonical table artifact {table_name} is unavailable or corrupt"
                ) from exc
            if descriptor != item.source_binding.descriptor:
                raise SubmitImportPublicationError(
                    f"canonical table artifact {table_name} descriptor binding mismatch"
                )
            if descriptor != item.artifact.manifest.descriptor:
                raise SubmitImportPublicationError(
                    f"canonical table artifact {table_name} manifest descriptor mismatch"
                )
            if item.artifact.manifest_ref.raw_sha256.value != raw_blob_digest(table_ref_payload).value:
                raise SubmitImportPublicationError(
                    f"canonical table artifact {table_name} raw SHA mismatch"
                )
            if (
                item.source_binding.snapshot_digest.value != build_input.source_artifact_digest
                or item.artifact.manifest.snapshot_digest.value != build_input.source_artifact_digest
            ):
                raise SubmitImportPublicationError(
                    f"canonical table artifact {table_name} snapshot_digest does not match source binding"
                )
            if (
                descriptor.table_name != table_name
                or descriptor.row_count != frozen_table.canonical_row_count
                or tuple(column.name for column in descriptor.columns)
                != frozen_table.retained_columns
                or descriptor.primary_key_columns != frozen_table.canonical_key_columns
                or descriptor.compare_key_columns != frozen_table.canonical_key_columns
            ):
                raise SubmitImportPublicationError(
                    f"canonical table artifact {table_name} does not match frozen table facts"
                )

            view = _storage_view_from_frozen_table(frozen_table)
            schema_columns = _schema_columns_from_descriptor(descriptor, frozen_table)
            schema_digest = _schema_digest(schema_columns, frozen_table.canonical_key_columns)
            if frozen_table.canonical_schema_digest != schema_digest:
                raise SubmitImportPublicationError(
                    f"canonical table artifact {table_name} schema does not match frozen manifest"
                )
            import_tables.append(
                RepositoryImportTable(
                    name=table_name,
                    columns=tuple(
                        RepositoryImportColumn(
                            name=str(column["name"]),
                            sql_type=str(column["sql_type"]),
                            nullable=bool(column["nullable"]),
                        )
                        for column in schema_columns
                    ),
                    primary_key=frozen_table.canonical_key_columns,
                    row_count=frozen_table.canonical_row_count,
                )
            )
            projected_tables.append(
                ProjectionTable(
                    canonical_table=table_name,
                    storage_view=view,
                    row_count=frozen_table.canonical_row_count,
                    schema_digest=frozen_table.canonical_schema_digest,
                    content_digest=frozen_table.content_digest,
                    fast_row_digest=descriptor.fast_row_digest,
                )
            )
            if table_name in mutation_table_names:
                replay_snapshots.append(
                    ImportReplayTableSnapshot(
                        manifest_table=frozen_table,
                        storage_view=view,
                        rows=_keyed_rows_from_frozen_artifact(
                            reader,
                            descriptor=descriptor,
                            manifest_table=frozen_table,
                        ),
                    )
                )
    finally:
        for reader in reopened_readers:
            try:
                reader.close()
            except Exception:
                continue

    assert frozen_manifest.manifest_digest is not None
    projection = ProjectionResult(
        status=ProjectionStatus.COMPLETE,
        tables=tuple(projected_tables),
        omitted_diagnostic_count=0,
        manifest=frozen_manifest,
        import_input=RepositoryImportArtifactInput(
            package_version=PACKAGE_VERSION,
            canonicalization_manifest_digest=frozen_manifest.manifest_digest,
            tables=tuple(import_tables),
        ),
    )
    return projection, tuple(replay_snapshots)


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


def _keyed_rows_from_frozen_artifact(
    reader: SnapshotTableReader,
    *,
    descriptor: SnapshotTableDescriptor,
    manifest_table: CanonicalizationManifestTable,
) -> tuple[ImportReplayKeyedRow, ...]:
    columns = descriptor.columns
    indexes = {column.name: index for index, column in enumerate(columns)}
    if tuple(indexes) != manifest_table.retained_columns:
        raise SubmitImportPublicationError(
            f"canonical table artifact {manifest_table.name} columns do not match frozen manifest"
        )
    keyed_rows: list[ImportReplayKeyedRow] = []
    observed = 0
    try:
        for row in reader.iter_rows():
            if type(row) is not tuple or len(row) != len(columns):
                raise SubmitImportPublicationError(
                    f"canonical table artifact {manifest_table.name} row width is invalid"
                )
            image_columns: list[tuple[str, dict[str, object]]] = []
            for name in sorted(manifest_table.retained_columns, key=lambda value: value.encode("utf-8")):
                column = columns[indexes[name]]
                sql_type = column.scalar_type
                if sql_type is None:
                    raise SubmitImportPublicationError(
                        f"canonical table artifact {manifest_table.name} is missing scalar type"
                    )
                image_columns.append((name, _mutation_cell_from_frozen_artifact(row[indexes[name]], sql_type)))
            image_by_name = {name: cell for name, cell in image_columns}
            key_columns = tuple(
                (name, dict(image_by_name[name]))
                for name in sorted(
                    manifest_table.canonical_key_columns,
                    key=lambda value: value.encode("utf-8"),
                )
            )
            keyed_rows.append(
                ImportReplayKeyedRow(
                    key_columns=key_columns,
                    image_columns=tuple(image_columns),
                )
            )
            observed += 1
    except SubmitImportPublicationError:
        raise
    except Exception as exc:
        raise SubmitImportPublicationError(
            f"canonical table artifact {manifest_table.name} row data is corrupt"
        ) from exc
    if observed != manifest_table.canonical_row_count:
        raise SubmitImportPublicationError(
            f"canonical table artifact {manifest_table.name} row count does not match frozen manifest"
        )
    return tuple(keyed_rows)


def _mutation_cell_from_frozen_artifact(cell: object, sql_type: str) -> dict[str, object]:
    if isinstance(cell, NullScalar):
        return {"kind": "null"}
    try:
        enum_set = enum_set_labels_for_sql_spelling(sql_type)
    except ValueError as exc:
        raise SubmitImportPublicationError("frozen canonical column SQL type is invalid") from exc
    if enum_set is not None:
        kind, labels = enum_set
        if kind == "ENUM":
            if not isinstance(cell, StringScalar):
                raise SubmitImportPublicationError("canonical ENUM cell must be a string scalar")
            return {"kind": "string", "text": cell.text}
        if not isinstance(cell, SqlSetValue):
            raise SubmitImportPublicationError("canonical SET cell must be a set scalar")
        selected = set(cell.members)
        return {"kind": "string", "text": ",".join(label for label in labels if label in selected)}
    if isinstance(cell, UnsignedIntegerScalar):
        return {"kind": "unsigned-integer", "decimal": cell.decimal}
    if isinstance(cell, SignedIntegerScalar):
        return {"kind": "signed-integer", "decimal": cell.decimal}
    if isinstance(cell, Float32Scalar):
        return {"kind": "float32", "bits_hex": cell.bits_hex}
    if isinstance(cell, Float64Scalar):
        return {"kind": "float64", "bits_hex": cell.bits_hex}
    if isinstance(cell, BooleanScalar):
        return {"kind": "boolean", "value": cell.value}
    if isinstance(cell, DecimalScalar):
        return {"kind": "decimal", "decimal": cell.decimal}
    if isinstance(cell, BinaryScalar):
        return {
            "kind": "binary",
            "bytes_base64url": base64.urlsafe_b64encode(cell.raw_bytes).decode("ascii").rstrip("="),
        }
    if isinstance(cell, BitScalar):
        return {
            "kind": "bit",
            "bytes_base64url": base64.urlsafe_b64encode(cell.raw_bytes).decode("ascii").rstrip("="),
        }
    if isinstance(cell, StringScalar):
        return {"kind": "string", "text": cell.text}
    if isinstance(cell, DateScalar):
        return {"kind": "date", "text": cell.text}
    if isinstance(cell, DateTimeScalar):
        return {"kind": "datetime", "text": cell.text}
    if isinstance(cell, TimestampScalar):
        return {"kind": "timestamp", "text": cell.text}
    if isinstance(cell, TimeDurationScalar):
        return {"kind": "time-duration", "text": cell.text}
    raise SubmitImportPublicationError("canonical cell type cannot be represented in repository import")


def _open_frozen_manifest(
    build_input: PrepareImportBuildInput,
    *,
    store: ArtifactStorePort,
) -> CanonicalizationManifest:
    try:
        return open_canonicalization_manifest(store, build_input.canonicalization_manifest_ref)
    except PublicationError as exc:
        raise SubmitImportPublicationError(str(exc)) from exc


def _open_projection_inputs(
    bindings: tuple[SnapshotTableBinding, ...],
    *,
    store: ArtifactStorePort,
) -> tuple[ProjectionTableInput, ...]:
    opened: list[ProjectionTableInput] = []
    for binding in bindings:
        manifest_ref = ArtifactRef(
            artifact_id=binding.artifact_id,
            media_type=binding.media_type,
            size_bytes=binding.size_bytes,
            raw_sha256=DigestRef(binding.raw_sha256),
        )
        table = open_snapshot_table_artifact(store, manifest_ref)
        if table.reader is None:
            raise SubmitImportPublicationError(f"snapshot table {binding.artifact_id} has no reader")
        if table.artifact is None:
            raise SubmitImportPublicationError(f"snapshot table {binding.artifact_id} has no artifact")
        if table.descriptor.table_name != binding.table_name:
            raise SubmitImportPublicationError("snapshot table name does not match frozen closure")
        source_binding = ArtifactSourceBinding(
            snapshot_digest=table.artifact.manifest.snapshot_digest,
            descriptor=table.descriptor,
        )
        opened.append(
            ProjectionTableInput(
                canonical_table=table.descriptor.table_name,
                reader=table.reader.reopen() if hasattr(table.reader, "reopen") else table.reader,
                source_binding=source_binding,
                artifact=table.artifact,
                canonicalized_input=True,
            )
        )
    return tuple(opened)
