"""Single FFI owner for table-level storage mutation facts."""

from __future__ import annotations

from typing import Protocol, cast

from gateway_compute._native import (
    _begin_storage_operation_native,
    _prepare_storage_table_native,
)

from gateway_backend.capabilities.mutation_planning._decision import (
    keyed_patchable, storage_views_compatible,
)
from gateway_backend.capabilities.mutation_planning.contracts import (
    StorageNetCounts, StorageTableOperation, StorageTableReservation, StorageTableSideV1, StorageTableSummary,
    StorageTableTaskV1, StorageTableDecision, TableMutationKind,
)
from gateway_backend.capabilities.storage_projection import (
    StorageInputLease, require_storage_input_owner, require_storage_operation,
    storage_memory_limit, verify_storage_metadata_manifest,
)


class _NativeOperation(Protocol):
    def close(self) -> None: ...
    def reconcile(self) -> int: ...


class _NativeHandle(Protocol):
    def summary(self) -> tuple[int, int, tuple[int, int, int] | None, bool, bool, int]: ...
    def discard_before(self) -> None: ...
    def close(self) -> None: ...


class NativeStorageTableHandle:
    """Keep native leases until facts and the last Arrow consumer finish."""

    def __init__(self, handle: _NativeHandle, native_operation: _NativeOperation,
                 task: StorageTableTaskV1, before_owner: StorageInputLease | None,
                 after_owner: StorageInputLease | None,
                 metadata_charge: StorageTableReservation) -> None:
        self._handle = handle
        self._operation = native_operation
        self._task = task
        self._before_owner = before_owner
        self._after_owner = after_owner
        self._metadata_charge = metadata_charge
        self._closed = False

    def summary(self) -> StorageTableSummary:
        if self._closed:
            raise ValueError("storage table handle closed")
        before_rows, after_rows, counts, before_validated, after_validated, _ = self._handle.summary()
        # A metadata-only before side has a validated manifest binding but no
        # parent Arrow to scan. Its net diff remains explicitly unknown.
        before_validated = before_validated or (
            self._task.before is not None and self._task.before.metadata_manifest is not None
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

    def apply_decision(self, decision: StorageTableDecision) -> None:
        if self._closed:
            raise ValueError("storage table handle closed")
        if decision.operation is not TableMutationKind.PATCH_DML:
            self._handle.discard_before()
            try:
                self._operation.reconcile()
            finally:
                if self._before_owner is not None:
                    self._before_owner.close()
                    self._before_owner = None

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            try:
                self._handle.close()
            finally:
                try:
                    try:
                        if self._before_owner is not None:
                            self._before_owner.close()
                    finally:
                        if self._after_owner is not None:
                            self._after_owner.close()
                finally:
                    try:
                        self._operation.close()
                    finally:
                        self._metadata_charge.close()

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
    if before is not None and before.stream is None:
        assert before.metadata_manifest is not None
        verify_storage_metadata_manifest(
            before.metadata_manifest, before.manifest_table, before.storage_projection_version,
        )
    if before is not None and before.stream is not None and before.schema is None:
        raise ValueError("before Arrow schema missing")
    if after is not None and after.stream is None:
        raise ValueError("after Arrow stream missing")
    before_owner = None if before is None or before.stream is None else require_storage_input_owner(
        before.input_owner, before.stream, before.schema, active,
    )
    try:
        after_owner = None if after is None or after.stream is None else require_storage_input_owner(
            after.input_owner, after.stream, after.schema, active,
        )
    except BaseException:
        if before_owner is not None:
            before_owner.close()
        raise
    diff = (
        before is not None and before.stream is not None
        and after is not None and after.stream is not None
        and keyed_patchable(after.storage_view)
        and before.manifest_table.canonical_schema_digest == after.manifest_table.canonical_schema_digest
        and before.manifest_table.retained_columns == after.manifest_table.retained_columns
        and storage_views_compatible(before.storage_view, after.storage_view)
        and before.storage_projection_version == after.storage_projection_version
        and before.manifest_table.canonical_row_count > 0
    )
    # Canonical producer bounded metadata is <=16 MiB. Reserve its FFI schema
    # and Vec/String copy envelope before PyO3 extracts those arguments.
    metadata_charge: StorageTableReservation | None = None
    reservation: StorageTableReservation | None = None
    native_operation: _NativeOperation | None = None
    handle: _NativeHandle | None = None
    try:
        metadata_charge = active.memory.reserve(64 * 1024 * 1024)
        # The input Arrow backing is already charged by its verified reader.
        # This native sub-budget shares the same M and survives to last handle.
        native_limit = active.memory.available_bytes
        reservation = active.memory.reserve(native_limit)
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
        if not diff and before_owner is not None:
            before_owner.close()
            before_owner = None
        return NativeStorageTableHandle(handle, native_operation, task, before_owner, after_owner,
                                        metadata_charge)
    except MemoryError as exc:
        if handle is not None:
            handle.close()
        if native_operation is not None:
            native_operation.close()
        elif reservation is not None:
            reservation.close()
        if before_owner is not None:
            before_owner.close()
        if after_owner is not None:
            after_owner.close()
        if metadata_charge is not None:
            metadata_charge.close()
        raise storage_memory_limit(str(exc)) from exc
    except BaseException:
        if handle is not None:
            handle.close()
        if native_operation is not None:
            native_operation.close()
        elif reservation is not None:
            reservation.close()
        if before_owner is not None:
            before_owner.close()
        if after_owner is not None:
            after_owner.close()
        if metadata_charge is not None:
            metadata_charge.close()
        raise
