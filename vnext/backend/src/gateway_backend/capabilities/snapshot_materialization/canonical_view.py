"""Operation-owned canonical Arrow view shared by comparison and storage."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack
from typing import Protocol

import pyarrow as pa

from gateway_backend.capabilities.snapshot_materialization.arrow import (
    ArrowSnapshotTableReader, operation_codec_budgets,
)
from gateway_backend.capabilities.snapshot_materialization.canonical_store import (
    canonical_comparison_profile, check_canonical_descriptor_budget,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    SnapshotTable, normalize_sql_type_spelling,
)
from gateway_backend.capabilities.snapshot_materialization.sql_declared_types import (
    try_declared_type_for_sql_spelling,
)
from gateway_backend.capabilities.table_access import current_kernel_context, TableAccessError


class CanonicalInputOwner(Protocol):
    def close(self) -> None: ...


class _FreshViewOwner:
    def __init__(self, charges: tuple[object, ...]) -> None:
        self._charges = charges

    def close(self) -> None:
        charges = self._charges
        self._charges = ()
        with ExitStack() as stack:
            for charge in reversed(charges):
                close = getattr(charge, "close", None)
                if callable(close):
                    stack.callback(close)


def _has_canonical_profile_metadata(schema: pa.Schema) -> bool:
    return ((schema.metadata is not None
             and b"gdds.canonical_mapping_version" in schema.metadata)
            or any(field.metadata is not None
                   and b"gdds.canonical_type" in field.metadata
                   for field in schema))


def fresh_canonical_view_budget(table: SnapshotTable) -> tuple[int, int]:
    """Bound only a writer-verified fresh canonical view before native M split."""
    reader = table.reader
    if (not isinstance(reader, ArrowSnapshotTableReader)
            or not reader.canonical_comparison_verified):
        return 0, 0
    try:
        schema = reader.arrow_schema
        batch_count = reader.arrow_batch_count_upper
    except TableAccessError:
        return 0, 0
    if _has_canonical_profile_metadata(schema):
        return 0, 0
    columns = table.descriptor.columns
    source_bytes = sum(
        256 + len(column.name) + len(column.display_name)
        + len(column.scalar_type or "") for column in columns
    )
    descriptor_upper = 0
    try:
        budgets = operation_codec_budgets()
        context = current_kernel_context()
        assert context is not None
        budgets["max_codec_peak_bytes"] = context.memory.limit_bytes
        descriptor_upper = 8 * check_canonical_descriptor_budget(table.descriptor, budgets)
    except MemoryError:
        pass
    metadata_upper = max(
        65536 + 64 * source_bytes + 16384 * len(columns), descriptor_upper,
    )
    rows = table.descriptor.row_count
    batches = batch_count + (rows + 65535) // 65536
    bit_upper = 0
    for column in columns:
        declared = try_declared_type_for_sql_spelling(
            normalize_sql_type_spelling(column.scalar_type or "UNKNOWN")
        )
        if (declared is None or declared.kind.value != "bit"
                or declared.bit_width is None):
            continue
        index = schema.get_field_index(column.name)
        if index < 0 or pa.types.is_fixed_size_binary(schema.field(index).type):
            continue
        width = (declared.bit_width + 7) // 8
        bit_upper += 2 * rows * width + 2 * ((rows + 7) // 8)
        bit_upper += batches * 1024 + 4096
    return metadata_upper, bit_upper


def canonical_comparison_input(
    table: SnapshotTable, *, field_order: tuple[str, ...] | None = None,
) -> tuple[pa.RecordBatchReader, CanonicalInputOwner]:
    """Borrow the persisted IPC profile or a verified fresh writer's bounded view."""
    context = current_kernel_context()
    if context is None:
        raise RuntimeError("canonical Arrow input requires an operation context")
    if not isinstance(table.reader, ArrowSnapshotTableReader):
        raise ValueError("canonical input requires an Arrow reader")
    isolated = table.reader.reopen()
    original: pa.RecordBatchReader | None = None
    try:
        original = isolated.arrow_stream()
        schema = original.schema
        if _has_canonical_profile_metadata(schema):
            # Even partial metadata must reach the native validator unchanged.
            return original, isolated
        if not isolated.canonical_comparison_verified:
            return original, isolated
        metadata_upper, bit_upper = fresh_canonical_view_budget(table)
        profile_charge = context.memory.reserve(metadata_upper)
        try:
            profile, indices = canonical_comparison_profile(
                table.descriptor, schema, metadata_budget_bytes=metadata_upper,
            )
            if field_order is not None:
                # The IPC profile uses UTF8 field-name order, while the
                # verified storage manifest retains declaration order. The
                # already-reserved profile metadata envelope covers this
                # bounded schema/index reorder before any record batches.
                positions = tuple(profile.get_field_index(name) for name in field_order)
                if (len(positions) != len(profile) or len(set(positions)) != len(profile)
                        or any(position < 0 for position in positions)):
                    raise ValueError("canonical view field order differs from frozen descriptor")
                profile = pa.schema([profile.field(position) for position in positions],
                                    metadata=profile.metadata)
                indices = tuple(indices[position] for position in positions)
            for position, source_index in enumerate(indices):
                target = profile.field(position).type
                actual = schema.field(source_index).type
                if actual == target:
                    continue
                if not (pa.types.is_fixed_size_binary(target)
                        and (pa.types.is_binary(actual) or pa.types.is_large_binary(actual))):
                    raise ValueError("canonical comparison view has an unsupported conversion")
            bit_charge = context.memory.reserve(bit_upper) if bit_upper else None
            try:
                def batches() -> Iterator[pa.RecordBatch]:
                    for batch in original:
                        step = 65536 if bit_upper else max(1, batch.num_rows)
                        for start in range(0, max(1, batch.num_rows), step):
                            context.checkpoint()
                            part = batch.slice(start, min(step, batch.num_rows - start))
                            arrays = []
                            for position, source_index in enumerate(indices):
                                array = part.column(source_index)
                                target = profile.field(position).type
                                arrays.append(array if array.type == target else array.cast(target, safe=True))
                            yield pa.RecordBatch.from_arrays(arrays, schema=profile)
                    context.checkpoint()

                view = pa.RecordBatchReader.from_batches(profile, batches())
            except BaseException:
                if bit_charge is not None:
                    bit_charge.close()
                raise
        except BaseException:
            profile_charge.close()
            raise
        return view, _FreshViewOwner(tuple(
            item for item in (original, isolated, bit_charge, profile_charge) if item is not None
        ))
    except BaseException:
        if original is not None:
            original.close()
        isolated.close()
        context.checkpoint()
        raise
