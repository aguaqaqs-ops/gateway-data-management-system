"""Public snapshot import replay materialization for RepositoryImportArtifact."""

from __future__ import annotations

from collections.abc import Mapping

from gateway_shared_kernel import (
    DigestRef,
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    UnsignedIntegerScalar,
)

from gateway_backend.capabilities.mutation_planning import (
    REPOSITORY_REPLAY_RENDERER_CAPABILITY,
    CanonicalStorageKey,
    MutationKeyedRow,
    MutationPlanStatus,
    MutationPlanningInput,
    MutationPlanningRequest,
    MutationPolicy,
    MutationProjectionBinding,
    MutationRepositoryBase,
    MutationSourceIdentity,
    MutationTableSnapshot,
    MutationThresholdPolicy,
    PersistedRowImage,
    plan_storage_mutation,
    render_change_set_replay,
)
from gateway_backend.capabilities.mutation_planning._digest import (
    key_bytes_for_ordering,
    row_digest_from_image,
)
from gateway_backend.capabilities.storage_projection._digest import CanonicalColumnCodec
from gateway_backend.capabilities.storage_projection.contracts import (
    CanonicalizationManifest,
    CanonicalizationManifestTable,
    ProjectionRequest,
    ProjectionResult,
    RepositoryImportArtifactInput,
    RepositoryImportTable,
)
from gateway_backend.capabilities.storage_projection.project import (
    _ProjectionFailed,
    _bound_descriptor,
    _retained_schema,
    materialize_canonical_source_rows,
)

class ImportReplayError(ValueError):
    """Raised when snapshot import replay materialization fails."""


def build_import_mutation_snapshots(
    request: ProjectionRequest,
    result: ProjectionResult,
) -> tuple[MutationTableSnapshot, ...]:
    if result.manifest is None:
        raise ImportReplayError("projection manifest is required")
    inputs_by_name = {item.canonical_table: item for item in request.tables}
    manifest_by_name = {table.name: table for table in result.manifest.tables}
    projected_by_name = {table.canonical_table: table for table in result.tables}
    snapshots: list[MutationTableSnapshot] = []
    for table_name in sorted(manifest_by_name):
        manifest_table = manifest_by_name[table_name]
        projected = projected_by_name.get(table_name)
        if projected is None:
            raise ImportReplayError(f"projected table {table_name} is missing")
        item = inputs_by_name.get(table_name)
        if item is None:
            raise ImportReplayError(f"projection input for {table_name} is missing")
        try:
            canonical_rows = materialize_canonical_source_rows(request, item, projected.storage_view)
        except _ProjectionFailed as exc:
            raise ImportReplayError(exc.diagnostic.message) from exc
        descriptor = _bound_descriptor(item, item.source_binding.snapshot_digest)
        _, codecs, retained_indexes = _retained_schema(projected.storage_view, descriptor)
        keyed_rows = _keyed_rows_from_canonical(
            canonical_rows,
            manifest_table=manifest_table,
            codecs=codecs,
            retained_indexes=retained_indexes,
        )
        snapshots.append(
            MutationTableSnapshot(
                manifest_table=manifest_table,
                storage_view=projected.storage_view,
                rows=keyed_rows,
            )
        )
    return tuple(snapshots)


def render_repository_import_replay_sql(
    result: ProjectionResult,
    snapshots: tuple[MutationTableSnapshot, ...],
) -> bytes:
    if result.manifest is None or result.import_input is None:
        raise ImportReplayError("COMPLETE projection is missing manifest or import input")
    ddl = _render_schema_replay(result.import_input)
    dml = _render_mutation_replay_sql(result, snapshots)
    return ddl + dml


def _render_schema_replay(import_input: RepositoryImportArtifactInput) -> bytes:
    parts: list[bytes] = []
    for table in sorted(import_input.tables, key=lambda item: item.name.encode("utf-8")):
        parts.append(_render_drop_create_table(table))
    return b"".join(parts)


def _render_drop_create_table(table: RepositoryImportTable) -> bytes:
    name = _quote_identifier(table.name)
    column_defs: list[str] = []
    for column in table.columns:
        nullability = " NULL" if column.nullable else " NOT NULL"
        column_defs.append(f"{_quote_identifier(column.name)} {column.sql_type}{nullability}")
    if table.primary_key:
        keys = ", ".join(_quote_identifier(key) for key in table.primary_key)
        column_defs.append(f"PRIMARY KEY ({keys})")
    body = ", ".join(column_defs)
    return f"DROP TABLE IF EXISTS {name};\nCREATE TABLE {name} ({body});\n".encode("utf-8")


def _render_mutation_replay_sql(
    result: ProjectionResult,
    snapshots: tuple[MutationTableSnapshot, ...],
) -> bytes:
    manifest = result.manifest
    assert manifest is not None
    empty_manifest = CanonicalizationManifest(
        contract_version=manifest.contract_version,
        storage_projection_version=manifest.storage_projection_version,
        ruleset_id=manifest.ruleset_id,
        ruleset_version=manifest.ruleset_version,
        ruleset_digest=manifest.ruleset_digest,
        source_artifact_digest=manifest.source_artifact_digest,
        tables=(),
        manifest_digest=DigestRef("sha256:" + "0f" * 32),
    )
    binding = MutationProjectionBinding(
        before_storage_projection_digest=manifest.manifest_digest or DigestRef("sha256:" + "00" * 32),
        after_storage_projection_digest=manifest.manifest_digest or DigestRef("sha256:" + "01" * 32),
        before_manifest_digest=empty_manifest.manifest_digest or DigestRef("sha256:" + "02" * 32),
        after_manifest_digest=manifest.manifest_digest or DigestRef("sha256:" + "03" * 32),
        table_ruleset_digest=manifest.ruleset_digest,
    )
    planning_input = MutationPlanningInput(
        mutation_policy=MutationPolicy.REBUILD_ALWAYS,
        projection_binding=binding,
        repository_base=MutationRepositoryBase(
            base_repository_ref_digest=manifest.source_artifact_digest,
        ),
        source_identity=MutationSourceIdentity(
            source_identity_digest=manifest.source_artifact_digest,
        ),
        renderer_capability=REPOSITORY_REPLAY_RENDERER_CAPABILITY,
        threshold_policy=MutationThresholdPolicy(),
    )
    request = MutationPlanningRequest(
        planning_input=planning_input,
        before_manifest=empty_manifest,
        after_manifest=manifest,
        before_tables=(),
        after_tables=snapshots,
        destructive_confirmation_granted=True,
    )
    planned = plan_storage_mutation(request)
    if planned.status is not MutationPlanStatus.READY or planned.change_set_closure is None:
        raise ImportReplayError("mutation planning failed for repository import replay")
    outcome = render_change_set_replay(planned.change_set_closure)
    if outcome.status != "READY" or outcome.sql_bytes is None:
        raise ImportReplayError("replay SQL rendering failed")
    return outcome.sql_bytes


def _keyed_rows_from_canonical(
    canonical_rows: tuple[tuple[object, ...], ...],
    *,
    manifest_table: CanonicalizationManifestTable,
    codecs: Mapping[int, CanonicalColumnCodec],
    retained_indexes: tuple[int, ...],
) -> tuple[MutationKeyedRow, ...]:
    retained = manifest_table.retained_columns
    key_columns = manifest_table.canonical_key_columns
    keyed_rows: list[MutationKeyedRow] = []
    for row in canonical_rows:
        image_columns = _image_columns_for_row(
            row,
            retained=retained,
            codecs=codecs,
            retained_indexes=retained_indexes,
        )
        image = PersistedRowImage(columns=image_columns)
        image_by_name = {name: cell for name, cell in image_columns}
        key_pairs = tuple((column, dict(image_by_name[column])) for column in key_columns)
        keyed_rows.append(
            MutationKeyedRow(
                key=CanonicalStorageKey(columns=key_pairs),
                image=image,
                row_digest=row_digest_from_image(image, retained_columns=retained),
            )
        )
    keyed_rows.sort(key=lambda item: key_bytes_for_ordering(item.key))
    return tuple(keyed_rows)


def _image_columns_for_row(
    row: tuple[object, ...],
    *,
    retained: tuple[str, ...],
    codecs: Mapping[int, CanonicalColumnCodec],
    retained_indexes: tuple[int, ...],
) -> tuple[tuple[str, dict[str, object]], ...]:
    index_by_retained_name = {
        retained_name: source_index
        for source_index, retained_name in zip(retained_indexes, retained, strict=True)
    }
    pairs: list[tuple[str, dict[str, object]]] = []
    for name in sorted(retained):
        source_index = index_by_retained_name[name]
        codec = codecs[source_index]
        cell = row[source_index]
        pairs.append((name, _mutation_cell(cell, codec)))
    return tuple(pairs)


def _mutation_cell(cell: object, codec: CanonicalColumnCodec) -> dict[str, object]:
    if isinstance(cell, NullScalar):
        return {"kind": "null"}
    if codec.family == "enum":
        if not isinstance(cell, StringScalar):
            raise ImportReplayError("ENUM cell must be a string scalar or null")
        return {"kind": "string", "text": cell.text}
    if codec.family == "set":
        members = getattr(cell, "members", None)
        if type(members) is not tuple:
            raise ImportReplayError("SET cell must expose members or be null")
        selected = [label for label in codec.labels if label in set(members)]
        return {"kind": "string", "text": ",".join(selected)}
    if isinstance(cell, UnsignedIntegerScalar):
        return {"kind": "unsigned-integer", "decimal": cell.decimal}
    if isinstance(cell, SignedIntegerScalar):
        return {"kind": "signed-integer", "decimal": cell.decimal}
    if isinstance(cell, StringScalar):
        return {"kind": "string", "text": cell.text}
    raise ImportReplayError("unsupported canonical cell for mutation replay")


def _quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier or "/" in identifier or "\\" in identifier:
        raise ImportReplayError("invalid SQL identifier")
    return "`" + identifier.replace("`", "``") + "`"
