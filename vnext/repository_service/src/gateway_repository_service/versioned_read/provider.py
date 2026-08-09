"""Candidate A offline CLI adapter for commit-pinned private reads."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_contracts import UnknownTypePolicy
from gateway_repository_service.arrow_mapping import CompiledTablePlan, SqlValueConversionError, TableCatalog
from gateway_repository_service.candidate_a.dolt_cli import CandidateADoltCli, _require_exactly_one_row, value
from gateway_repository_service.candidate_a.errors import CandidateAError
from gateway_repository_service.candidate_a.ref_validation import IMPORT_MAIN_REF
from gateway_repository_service.layout import DurableLayout
from gateway_repository_service.process import DoltRunner, ProcessBoundaryError
from gateway_repository_service.settings import RepositoryServiceSettings
from gateway_repository_service.versioned_read.errors import (
    CommitNotFoundError,
    MainRefNotFoundError,
    ProviderUnavailableError,
    ReadStreamCancelledError,
    redact_provider_message,
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
)

_STREAM_PROVIDER_FAULTS = _READ_PROVIDER_FAULTS


def _as_provider_unavailable(exc: BaseException) -> ProviderUnavailableError:
    if isinstance(exc, ProviderUnavailableError):
        return exc
    if isinstance(exc, ProcessBoundaryError) and str(exc) == "stream cancelled":
        return ReadStreamCancelledError("versioned read stream was cancelled")
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
        return ProviderUnavailableError(redact_provider_message(str(exc)))
    return ProviderUnavailableError("versioned read provider is unavailable")


class CandidateAReadProvider:
    """Production-owned Candidate A adapter for commit-pinned private reads."""

    def __init__(
        self,
        settings: RepositoryServiceSettings,
        layout: DurableLayout,
        repository: Path,
        runner: DoltRunner,
    ) -> None:
        self._settings = settings
        self._layout = layout
        self._repository = repository
        self._runner = runner
        self._cli = CandidateADoltCli(settings, layout, repository, runner)

    def read_ref(self, ref_name: str) -> str:
        if ref_name != IMPORT_MAIN_REF:
            raise MainRefNotFoundError("versioned read ref is not supported")
        try:
            rows = self._cli.query_json(
                "read_ref",
                f"SELECT HASHOF('{IMPORT_MAIN_REF}') AS commit_id;\n",
            )
            row = _require_exactly_one_row(rows, "read_ref")
            raw = value(row, "commit_id", 0)
            if not isinstance(raw, str) or raw == "":
                raise MainRefNotFoundError("versioned read ref is not available")
            return raw
        except MainRefNotFoundError:
            raise
        except _READ_PROVIDER_FAULTS as exc:
            raise _as_provider_unavailable(exc) from exc

    def commit_exists(self, commit_id: str) -> bool:
        try:
            return self._cli.commit_exists(commit_id)
        except _READ_PROVIDER_FAULTS as exc:
            raise _as_provider_unavailable(exc) from exc

    def catalog_at(self, commit_id: str) -> tuple[TableCatalog, ...]:
        try:
            if not self._cli.commit_exists(commit_id):
                raise CommitNotFoundError("versioned read commit was not found")
            return self._cli.catalog_at(commit_id)
        except CommitNotFoundError:
            raise
        except _READ_PROVIDER_FAULTS as exc:
            raise _as_provider_unavailable(exc) from exc

    def stream_table_at(
        self,
        commit_id: str,
        table: TableCatalog,
        policy: UnknownTypePolicy,
        *,
        table_plan: CompiledTablePlan | None = None,
        cancellation: CancellationCallback | None = None,
    ) -> Iterator[pa.RecordBatch]:
        try:
            if not self._cli.commit_exists(commit_id):
                raise CommitNotFoundError("versioned read commit was not found")
            iterator = self._cli.stream_table_at(
                commit_id,
                table,
                policy,
                table_plan=table_plan,
                cancellation=cancellation,
            )
        except CommitNotFoundError:
            raise
        except SqlValueConversionError:
            raise
        except _STREAM_PROVIDER_FAULTS as exc:
            raise _as_provider_unavailable(exc) from exc

        def _emit() -> Iterator[pa.RecordBatch]:
            try:
                for batch in iterator:
                    yield batch
            except SqlValueConversionError:
                raise
            except _STREAM_PROVIDER_FAULTS as exc:
                raise _as_provider_unavailable(exc) from exc

        return _emit()
