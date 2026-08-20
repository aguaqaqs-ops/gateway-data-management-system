"""Helpers for Storage Projection tests. Not a production projector."""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from gateway_shared_kernel import DigestRef, NullScalar, SignedIntegerScalar, StringScalar, UnsignedIntegerScalar

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    ROW_MATERIALIZATION_PROFILE,
    SCALAR_ENCODING_VERSION,
    ArtifactSourceBinding,
    MaterializationStage,
    SnapshotColumnDescriptor,
    SnapshotColumnValueCounts,
    SnapshotTableDescriptor,
)
from gateway_backend.capabilities.table_access.contracts import SourceCell, SourceRow, SqlSetValue

_DIGEST = DigestRef("sha256:" + "11" * 32)


class FakeSnapshotTableReader:
    def __init__(
        self,
        descriptor: SnapshotTableDescriptor,
        rows: tuple[SourceRow, ...] = (),
        *,
        iter_error: BaseException | None = None,
    ) -> None:
        self._descriptor = descriptor
        self._rows = rows
        self._iter_error = iter_error
        self.closed = False

    def descriptor(self) -> SnapshotTableDescriptor:
        return self._descriptor

    def iter_rows(self) -> Iterator[SourceRow]:
        if self._iter_error is not None:
            raise self._iter_error
        return iter(self._rows)

    def count_column_values(self, column_name: str) -> SnapshotColumnValueCounts:
        raise AssertionError("storage projection tests do not read column counts")

    def close(self) -> None:
        self.closed = True

    def reopen(self) -> FakeSnapshotTableReader:
        return FakeSnapshotTableReader(self._descriptor, self._rows, iter_error=self._iter_error)


def dummy_digest() -> DigestRef:
    return _DIGEST


def digest_ref(fill: str) -> DigestRef:
    return DigestRef("sha256:" + fill * 32)


def int_column(name: str, *, nullable: bool = False) -> SnapshotColumnDescriptor:
    return SnapshotColumnDescriptor(
        name=name,
        display_name=name,
        nullable=nullable,
        scalar_type="INT",
    )


def varchar_column(name: str, *, nullable: bool = False) -> SnapshotColumnDescriptor:
    return SnapshotColumnDescriptor(
        name=name,
        display_name=name,
        nullable=nullable,
        scalar_type="VARCHAR",
    )


def uint_column(name: str, *, nullable: bool = False) -> SnapshotColumnDescriptor:
    return SnapshotColumnDescriptor(
        name=name,
        display_name=name,
        nullable=nullable,
        scalar_type="INT UNSIGNED",
    )


def enum_column(name: str, sql_type: str, *, nullable: bool = False) -> SnapshotColumnDescriptor:
    return SnapshotColumnDescriptor(
        name=name,
        display_name=name,
        nullable=nullable,
        scalar_type=sql_type,
    )


def set_column(name: str, sql_type: str, *, nullable: bool = False) -> SnapshotColumnDescriptor:
    return SnapshotColumnDescriptor(
        name=name,
        display_name=name,
        nullable=nullable,
        scalar_type=sql_type,
    )


def table_descriptor(
    name: str,
    columns: Sequence[SnapshotColumnDescriptor],
    *,
    primary_key_columns: tuple[str, ...],
    row_count: int,
    raw_content_digest: DigestRef | None = None,
    compare_schema_digest: DigestRef | None = None,
    materialization_stage: MaterializationStage = MaterializationStage.FINAL,
    degraded_reason: object = None,
) -> SnapshotTableDescriptor:
    digest = dummy_digest()
    values: dict[str, object] = {
        "table_name": name,
        "display_table_name": name,
        "columns": tuple(columns),
        "primary_key_columns": primary_key_columns,
        "compare_key_columns": primary_key_columns,
        "row_count": row_count,
        "materialization_stage": materialization_stage,
        "compare_schema_digest": compare_schema_digest or digest,
        "table_ruleset_version": 1,
        "row_materialization_profile": ROW_MATERIALIZATION_PROFILE,
        "scalar_encoding_version": SCALAR_ENCODING_VERSION,
    }
    if raw_content_digest is not None:
        values["raw_content_digest"] = raw_content_digest
    elif materialization_stage is MaterializationStage.FINAL and degraded_reason is None:
        values["raw_content_digest"] = digest
    if degraded_reason is not None:
        values["degraded_reason"] = degraded_reason
    return SnapshotTableDescriptor(**values)  # type: ignore[arg-type]


def table_input(
    name: str = "net_cfg",
    *,
    columns: Sequence[SnapshotColumnDescriptor] | None = None,
    primary_key_columns: tuple[str, ...] | None = None,
    rows: tuple[SourceRow, ...] = (),
    raw_content_digest: DigestRef | None = None,
    snapshot_digest: DigestRef | None = None,
    materialization_stage: MaterializationStage | None = None,
    degraded_reason: object = None,
    iter_error: BaseException | None = None,
    row_count: int | None = None,
) -> tuple[FakeSnapshotTableReader, ArtifactSourceBinding]:
    if columns is None:
        descriptor = SnapshotTableDescriptor(
            table_name=name,
            display_table_name=name,
            columns=(
                SnapshotColumnDescriptor(name="board", display_name="board", nullable=False),
                SnapshotColumnDescriptor(name="link_no", display_name="link_no", nullable=False),
                SnapshotColumnDescriptor(name="no", display_name="no", nullable=True),
            ),
            primary_key_columns=("board", "link_no"),
            compare_key_columns=("board", "link_no"),
            row_count=0,
            materialization_stage=MaterializationStage.FINAL,
            compare_schema_digest=_DIGEST,
            table_ruleset_version=1,
            row_materialization_profile=ROW_MATERIALIZATION_PROFILE,
            scalar_encoding_version=SCALAR_ENCODING_VERSION,
            raw_content_digest=_DIGEST,
        )
        reader = FakeSnapshotTableReader(descriptor, rows, iter_error=iter_error)
        binding = ArtifactSourceBinding(snapshot_digest=snapshot_digest or _DIGEST, descriptor=descriptor)
        return reader, binding
    descriptor = table_descriptor(
        name,
        columns,
        primary_key_columns=primary_key_columns or (),
        row_count=len(rows) if row_count is None else row_count,
        raw_content_digest=raw_content_digest,
        materialization_stage=materialization_stage or MaterializationStage.FINAL,
        degraded_reason=degraded_reason,
    )
    reader = FakeSnapshotTableReader(descriptor, rows, iter_error=iter_error)
    binding = ArtifactSourceBinding(snapshot_digest=snapshot_digest or _DIGEST, descriptor=descriptor)
    return reader, binding


def int_cell(value: int) -> SignedIntegerScalar:
    return SignedIntegerScalar(decimal=str(value))


def varchar_cell(value: str) -> StringScalar:
    return StringScalar(text=value)


def uint_cell(value: int) -> UnsignedIntegerScalar:
    return UnsignedIntegerScalar(decimal=str(value))


def set_cell(*members: str) -> SqlSetValue:
    return SqlSetValue(members=members)


def null_cell() -> NullScalar:
    return NullScalar()


def as_row(*cells: SourceCell) -> SourceRow:
    return tuple(cells)
