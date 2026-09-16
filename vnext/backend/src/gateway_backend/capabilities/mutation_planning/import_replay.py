"""Public import mutation replay materialization for RepositoryImportArtifact."""

from __future__ import annotations

from gateway_backend.capabilities.mutation_planning._digest import (
    key_bytes_for_ordering,
    row_digest_from_image,
)
from gateway_backend.capabilities.mutation_planning.contracts import (
    CanonicalStorageKey,
    MutationKeyedRow,
    MutationTableSnapshot,
    PersistedRowImage,
)
from gateway_backend.capabilities.storage_projection.contracts import ImportReplayTableSnapshot


class ImportReplayError(ValueError):
    """Raised when snapshot import replay materialization fails."""


def build_import_mutation_snapshots(
    projection_snapshots: tuple[ImportReplayTableSnapshot, ...],
) -> tuple[MutationTableSnapshot, ...]:
    snapshots: list[MutationTableSnapshot] = []
    for projection_snapshot in projection_snapshots:
        retained = projection_snapshot.manifest_table.retained_columns
        keyed_rows: list[MutationKeyedRow] = []
        for row in projection_snapshot.rows:
            image = PersistedRowImage(columns=row.image_columns)
            keyed_rows.append(
                MutationKeyedRow(
                    key=CanonicalStorageKey(columns=row.key_columns),
                    image=image,
                    row_digest=row_digest_from_image(image, retained_columns=retained),
                )
            )
        keyed_rows.sort(key=lambda item: key_bytes_for_ordering(item.key))
        snapshots.append(
            MutationTableSnapshot(
                manifest_table=projection_snapshot.manifest_table,
                storage_view=projection_snapshot.storage_view,
                rows=tuple(keyed_rows),
            )
        )
    return tuple(snapshots)
