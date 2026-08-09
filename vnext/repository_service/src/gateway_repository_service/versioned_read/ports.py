"""Production port for Candidate A commit-pinned read primitives."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Protocol

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_contracts import UnknownTypePolicy
from gateway_repository_service.arrow_mapping import CompiledTablePlan, TableCatalog

CancellationCallback = Callable[[], bool]


class VersionedReadProvider(Protocol):
    def read_ref(self, ref_name: str) -> str: ...

    def commit_exists(self, commit_id: str) -> bool: ...

    def catalog_at(self, commit_id: str, *, existence_verified: bool = False) -> tuple[TableCatalog, ...]: ...

    def stream_table_at(
        self,
        commit_id: str,
        table: TableCatalog,
        policy: UnknownTypePolicy,
        *,
        table_plan: CompiledTablePlan | None = None,
        cancellation: CancellationCallback | None = None,
        existence_verified: bool = False,
    ) -> Iterator[pa.RecordBatch]: ...
