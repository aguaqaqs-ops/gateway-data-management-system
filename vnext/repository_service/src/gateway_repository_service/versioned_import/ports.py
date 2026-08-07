"""Production port for Candidate A Versioned import provider primitives."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import pyarrow as pa  # type: ignore[import-untyped]

from gateway_repository_contracts import UnknownTypePolicy
from gateway_repository_service.arrow_mapping import TableCatalog

CancellationCallback = Callable[[], bool]


@dataclass(frozen=True)
class MarkerInspectionZero:
    kind: Literal["zero"] = "zero"


@dataclass(frozen=True)
class MarkerInspectionUnique:
    candidate: str
    parent: str
    refs: tuple[str, ...]
    kind: Literal["unique"] = "unique"


@dataclass(frozen=True)
class MarkerInspectionAmbiguous:
    kind: Literal["ambiguous"] = "ambiguous"


MarkerInspection = MarkerInspectionZero | MarkerInspectionUnique | MarkerInspectionAmbiguous


@dataclass(frozen=True)
class PublishMainPublished:
    kind: Literal["published"] = "published"


@dataclass(frozen=True)
class PublishMainMismatch:
    actual: str
    kind: Literal["mismatch"] = "mismatch"


@dataclass(frozen=True)
class PublishMainAmbiguous:
    kind: Literal["ambiguous"] = "ambiguous"


PublishMainResult = PublishMainPublished | PublishMainMismatch | PublishMainAmbiguous


class VersionedImportProvider(Protocol):
    def read_ref(self, ref_name: str) -> str: ...

    def create_private_ref(self, private_ref: str, expected_commit: str) -> None: ...

    def checkout_private_ref(self, private_ref: str) -> None: ...

    def replay_sql(
        self,
        private_ref: str,
        replay_path: Path,
        cancellation: CancellationCallback | None = None,
    ) -> None: ...

    def commit_operation_marker(self, private_ref: str, marker: str) -> str: ...

    def inspect_marker(self, marker: str) -> MarkerInspection: ...

    def read_catalog(self, candidate: str) -> tuple[TableCatalog, ...]: ...

    def read_type_catalog(self, candidate: str) -> tuple[TableCatalog, ...]: ...

    def stream_table(
        self,
        candidate: str,
        table: TableCatalog,
        policy: UnknownTypePolicy,
    ) -> Iterator[pa.RecordBatch]: ...

    def publish_main(self, expected_commit: str, candidate: str) -> PublishMainResult: ...

    def delete_private_ref(
        self,
        private_ref: str,
        expected_candidate: str | None = None,
    ) -> None: ...
