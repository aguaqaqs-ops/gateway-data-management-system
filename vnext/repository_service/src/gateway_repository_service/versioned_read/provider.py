"""Candidate A offline CLI adapter for commit-pinned private reads."""

from __future__ import annotations

import csv
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import Lock
from uuid import UUID
from typing import NoReturn
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_contracts import UnknownTypePolicy
from gateway_repository_service.arrow_mapping import CompiledTablePlan, SqlValueConversionError, TableCatalog
from gateway_repository_service.candidate_a.dolt_cli import CandidateADoltCli, _require_exactly_one_row, value
from gateway_repository_service.candidate_a.errors import CandidateAError, DoltCliStreamCancelledError
from gateway_repository_service.candidate_a.ref_validation import IMPORT_MAIN_REF
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import DoltRunner, ProcessBoundaryError, ProcessStreamCancelledError
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.diagnostics import log_event
from gateway_repository_service.versioned_import.locks import RepositoryLockRegistry
from gateway_repository_service.versioned_read.errors import (
    RepositoryBusyError,
    CommitNotFoundError,
    MainRefNotFoundError,
    ProviderUnavailableError,
    ReadStreamCancelledError,
)
from gateway_repository_service.versioned_read.ports import CancellationCallback

_READ_PROVIDER_FAULTS = (
    CandidateAError,
    ProcessBoundaryError,
    ValueError,
    TypeError,
    IndexError,
    OSError,
    csv.Error,
    UnicodeDecodeError,
    TimeoutError,
)

_STREAM_PROVIDER_FAULTS = _READ_PROVIDER_FAULTS


_UNAVAILABLE_MESSAGE = "versioned read provider is unavailable"
_CANCELLED_MESSAGE = "versioned read stream was cancelled"


def _as_read_stream_cancelled() -> ReadStreamCancelledError:
    return ReadStreamCancelledError(_CANCELLED_MESSAGE)


def _as_provider_unavailable(exc: BaseException) -> ProviderUnavailableError | ReadStreamCancelledError:
    if isinstance(exc, ProviderUnavailableError):
        return exc
    if isinstance(exc, ReadStreamCancelledError):
        return exc
    if isinstance(exc, TimeoutError):
        return ProviderUnavailableError(_UNAVAILABLE_MESSAGE)
    if isinstance(exc, (ProcessStreamCancelledError, DoltCliStreamCancelledError)):
        return _as_read_stream_cancelled()
    if isinstance(
        exc,
        (
            CandidateAError,
            ProcessBoundaryError,
            ValueError,
            TypeError,
            IndexError,
            OSError,
            csv.Error,
            UnicodeDecodeError,
        ),
    ):
        return ProviderUnavailableError(_UNAVAILABLE_MESSAGE)
    return ProviderUnavailableError(_UNAVAILABLE_MESSAGE)


def _raise_provider_unavailable(exc: BaseException) -> NoReturn:
    raise _as_provider_unavailable(exc) from None


class CandidateAReadProvider:
    """Production-owned Candidate A adapter for commit-pinned private reads."""

    def __init__(
        self,
        settings: RepositoryServiceSettings,
        layout: DurableLayout,
        repository: Path,
        runner: DoltRunner,
        *,
        locks: RepositoryLockRegistry | None = None,
        repository_id: UUID | None = None,
    ) -> None:
        self._settings = settings
        self._layout = layout
        self._repository = repository
        self._runner = runner
        if locks is not None and repository_id is None:
            raise ValueError("repository reservation requires repository identity")
        self._locks = locks
        self._repository_id = repository_id
        self._owner = object()
        self._cli = CandidateADoltCli(settings, layout, repository, runner,
            command_owner=self._owner if locks is not None else None)

    def _reserve(self) -> None:
        if self._locks is not None and self._repository_id is not None:
            if not self._locks.try_reserve(self._repository_id):
                raise RepositoryBusyError("repository is busy")

    def _release(self, owner: object) -> None:
        if self._locks is not None and self._repository_id is not None:
            if self._runner.has_owned_children(owner):
                log_event("repository_read_reservation_retained", repository_id=self._repository_id,
                    result="executor_exit_unconfirmed")
                return
            self._locks.release_reservation(self._repository_id)

    @contextmanager
    def _metadata_access(self) -> Iterator[None]:
        self._reserve()
        try:
            yield
        finally:
            self._release(self._owner)

    def read_ref(self, ref_name: str) -> str:
        if ref_name != IMPORT_MAIN_REF:
            raise MainRefNotFoundError("versioned read ref is not supported")
        try:
            with self._metadata_access():
                rows = self._cli.query_json(
                    "read_ref",
                    f"SELECT HASHOF('{IMPORT_MAIN_REF}') AS commit_id;\n",
                )
                row = _require_exactly_one_row(rows, "read_ref")
                raw = value(row, "commit_id", 0)
                if isinstance(raw, str) and raw == "":
                    raise MainRefNotFoundError("versioned read ref is not available")
                if not isinstance(raw, str):
                    raise ProviderUnavailableError(_UNAVAILABLE_MESSAGE)
                return raw
        except MainRefNotFoundError:
            raise
        except _READ_PROVIDER_FAULTS as exc:
            _raise_provider_unavailable(exc)

    def commit_exists(self, commit_id: str) -> bool:
        try:
            with self._metadata_access():
                return self._cli.commit_exists(commit_id)
        except _READ_PROVIDER_FAULTS as exc:
            _raise_provider_unavailable(exc)

    def catalog_at(self, commit_id: str, *, existence_verified: bool = False) -> tuple[TableCatalog, ...]:
        try:
            with self._metadata_access():
                if not existence_verified and not self._cli.commit_exists(commit_id):
                    raise CommitNotFoundError("versioned read commit was not found")
                return self._cli.catalog_at(commit_id)
        except CommitNotFoundError:
            raise
        except _READ_PROVIDER_FAULTS as exc:
            _raise_provider_unavailable(exc)

    def stream_table_at(
        self,
        commit_id: str,
        table: TableCatalog,
        policy: UnknownTypePolicy,
        *,
        table_plan: CompiledTablePlan | None = None,
        cancellation: CancellationCallback | None = None,
        existence_verified: bool = False,
        stream_owner: object | None = None,
    ) -> Iterator[pa.RecordBatch]:
        self._reserve()
        owner = stream_owner if stream_owner is not None else object()
        try:
            if not existence_verified and not self._cli.commit_exists(commit_id):
                raise CommitNotFoundError("versioned read commit was not found")
            iterator = self._cli.stream_table_at(
                commit_id, table, policy, table_plan=table_plan,
                cancellation=cancellation, stream_owner=owner,
            )
            return _ReservedRows(iterator, lambda: self._release(owner),
                lambda: log_event("repository_read_reservation_retained",
                    repository_id=self._repository_id, result="executor_exit_unconfirmed"))
        except BaseException as exc:
            self._release(self._owner)
            if isinstance(exc, (CommitNotFoundError, SqlValueConversionError)):
                raise
            if isinstance(exc, _STREAM_PROVIDER_FAULTS):
                _raise_provider_unavailable(exc)
            raise


class _ReservedRows(Iterator[pa.RecordBatch]):
    """Explicit ownership survives close before first next and failed cleanup.

    A bridge defers release until its producer has actually joined. Other users
    explicitly close this iterator after consumption.
    """

    def __init__(self, iterator: Iterator[pa.RecordBatch], release: Callable[[], None],
                 retain: Callable[[], None]) -> None:
        self._iterator = iterator
        self._release = release
        self._retain = retain
        self._retained = False
        self._closed = False
        self._joined_release = False
        self._released = False
        self._lock = Lock()

    def __iter__(self) -> _ReservedRows:
        return self

    def __next__(self) -> pa.RecordBatch:
        try:
            return next(self._iterator)
        except StopIteration:
            self.close()
            raise
        except SqlValueConversionError:
            raise
        except _STREAM_PROVIDER_FAULTS as exc:
            _raise_provider_unavailable(exc)

    def hold_until_join(self) -> None:
        self._joined_release = True

    def release_after_join(self) -> None:
        if self._closed:
            self._release_once()

    def retain_reservation(self) -> None:
        self._retained = True
        self._retain()

    def _release_once(self) -> None:
        with self._lock:
            if not self._released and not self._retained:
                self._released = True
                self._release()

    def close(self, *, cancelled: bool = False) -> None:
        del cancelled
        if not self._closed:
            close = getattr(self._iterator, "close", None)
            try:
                if callable(close):
                    close()
            except BaseException:
                self.retain_reservation()
                raise
            self._closed = True
        if not self._joined_release:
            self._release_once()
