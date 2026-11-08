"""Single FFI owner for table-level storage mutation facts."""

from __future__ import annotations

from typing import Protocol, cast

from gateway_compute._native import (
    _begin_storage_operation_native,
    _prepare_storage_table_native,
)

from gateway_backend.capabilities.mutation_planning.contracts import (
    StorageNetCounts, StorageTableOperation, StorageTableSideV1, StorageTableSummary,
    StorageTableTaskV1,
)
from gateway_backend.capabilities.storage_projection import (
    require_storage_operation, storage_memory_limit,
)


class _NativeOperation(Protocol):
    def close(self) -> None: ...
    def reconcile(self) -> int: ...


class _NativeHandle(Protocol):
    def summary(self) -> tuple[int, int, tuple[int, int, int] | None, bool, bool, int]: ...
    def close(self) -> None: ...


class NativeStorageTableHandle:
    """Keep native leases until facts and the last Arrow consumer finish."""

    def __init__(self, handle: _NativeHandle, native_operation: _NativeOperation,
                 task: StorageTableTaskV1) -> None:
        self._handle = handle
        self._operation = native_operation
        self._task = task
        self._closed = False

    def summary(self) -> StorageTableSummary:
        if self._closed:
            raise ValueError("storage table handle closed")
        before_rows, after_rows, counts, before_validated, after_validated, _ = self._handle.summary()
        # A metadata-only before side has a validated manifest binding but no
        # parent Arrow to scan. Its net diff remains explicitly unknown.
        before_validated = before_validated or (
            self._task.before is not None and self._task.before.stream is None
        )
        return StorageTableSummary(
            before_rows, after_rows,
            StorageNetCounts(*counts) if counts is not None else None,
            before_validated, after_validated,
        )

    @property
    def patch_locator_count(self) -> int:
        if self._closed:
            raise ValueError("storage table handle closed")
        return self._handle.summary()[5]

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                self._handle.close()
            finally:
                self._operation.close()

    def __enter__(self) -> NativeStorageTableHandle:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _columns(side: StorageTableSideV1 | None) -> tuple[str, ...]:
    return () if side is None else side.manifest_table.retained_columns


def prepare_storage_table(
    task: StorageTableTaskV1, operation: StorageTableOperation,
) -> NativeStorageTableHandle:
    """Consume explicit Arrow streams under the caller's active M and N."""
    active = cast(StorageTableOperation, require_storage_operation(operation))
    before, after = task.before, task.after
    if before is not None and before.stream is not None and before.schema is None:
        raise ValueError("before Arrow schema missing")
    if after is not None and after.stream is None:
        raise ValueError("after Arrow stream missing")
    diff = (
        before is not None and before.stream is not None
        and after is not None and after.stream is not None
        and bool(after.manifest_table.canonical_key_columns)
        and before.manifest_table.canonical_schema_digest == after.manifest_table.canonical_schema_digest
        and before.manifest_table.retained_columns == after.manifest_table.retained_columns
        and before.storage_view == after.storage_view
        and before.storage_projection_version == after.storage_projection_version
        and before.manifest_table.canonical_row_count > 0
    )
    # The caller already owns and charges the unique input Arrow backing. This
    # reservation is a subportion of the same M, used solely for native work.
    native_limit = active.memory.available_bytes
    reservation = active.memory.reserve(native_limit)
    native_operation: _NativeOperation | None = None
    try:
        native_operation = cast(_NativeOperation, _begin_storage_operation_native(
            native_limit, reservation, active.cancel_probe, active.deadline_monotonic,
            active.threads, id(active.memory),
        ))
        handle = cast(_NativeHandle, _prepare_storage_table_native(
            native_operation,
            None if before is None else before.stream,
            None if before is None else before.schema,
            0 if before is None else before.manifest_table.canonical_row_count,
            _columns(before),
            None if after is None else after.stream,
            None if after is None else after.schema,
            0 if after is None else after.manifest_table.canonical_row_count,
            _columns(after),
            () if after is None else after.manifest_table.canonical_key_columns,
            diff, id(active.memory),
        ))
        require_storage_operation(active)
        return NativeStorageTableHandle(handle, native_operation, task)
    except MemoryError as exc:
        if native_operation is not None:
            native_operation.close()
        else:
            reservation.close()
        raise storage_memory_limit(str(exc)) from exc
    except BaseException:
        if native_operation is not None:
            native_operation.close()
        else:
            reservation.close()
        raise
