"""Public contracts owned by the Comparison capability.

S1 owns the language-neutral batch/provider port. S2-S5 add pair, facts and records semantics without
changing this coarse-grained Arrow boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable

import pyarrow as pa

from gateway_backend.capabilities.snapshot_materialization.contracts import (
    BATCH_READER_CONTRACT_VERSION,
    BATCH_SCHEMA_METADATA_VERSION,
    SnapshotTableBatchMetadata,
    SnapshotTableBatchReader,
    SnapshotTableDescriptor,
)

COMPARISON_BATCH_PORT_VERSION = 1


@dataclass(frozen=True, slots=True)
class ComparisonBatchRequest:
    """Provider-neutral request; the request bytes are opaque to the port."""

    table_name: str
    descriptor: SnapshotTableDescriptor
    reader: SnapshotTableBatchReader
    request_jcs: bytes = b""

    def __post_init__(self) -> None:
        if type(self.table_name) is not str or self.table_name == "":
            raise ValueError("table_name must be a non-empty string")
        if self.descriptor.table_name != self.table_name:
            raise ValueError("table_name must match descriptor")
        if not isinstance(self.reader, SnapshotTableBatchReader):
            raise ValueError("reader must implement SnapshotTableBatchReader")
        if type(self.request_jcs) is not bytes:
            raise ValueError("request_jcs must be bytes")


@dataclass(frozen=True, slots=True)
class ComparisonBatchResult:
    """Coarse provider output; semantic facts are owned by later R5 stages."""

    provider_id: str
    output_stream: pa.RecordBatchReader
    result_jcs: bytes
    input_metadata: SnapshotTableBatchMetadata

    def __post_init__(self) -> None:
        if type(self.provider_id) is not str or self.provider_id == "":
            raise ValueError("provider_id must be a non-empty string")
        if not isinstance(self.output_stream, pa.RecordBatchReader):
            raise ValueError("output_stream must be pyarrow.RecordBatchReader")
        if type(self.result_jcs) is not bytes:
            raise ValueError("result_jcs must be bytes")
        if type(self.input_metadata) is not SnapshotTableBatchMetadata:
            raise ValueError("input_metadata must be SnapshotTableBatchMetadata")


@runtime_checkable
class ComparisonBatchProvider(Protocol):
    """Provider port shared by Python reference and Rust native implementations."""

    @property
    def provider_id(self) -> str:
        """Stable diagnostic identifier; it is not a semantic digest input."""

    def execute(self, request: ComparisonBatchRequest) -> ComparisonBatchResult:
        """Consume one Arrow stream and return one coarse-grained Arrow stream."""


NativeBatchCompute = Callable[
    [bytes, pa.RecordBatch | pa.Table | pa.RecordBatchReader],
    tuple[pa.RecordBatchReader, bytes],
]


def validate_batch_reader(reader: object) -> SnapshotTableBatchReader:
    """Validate an injected reader at the provider seam without opening rows."""

    if not isinstance(reader, SnapshotTableBatchReader):
        raise TypeError("reader must implement SnapshotTableBatchReader")
    metadata = reader.metadata()
    if metadata.batch_reader_contract_version != BATCH_READER_CONTRACT_VERSION:
        raise ValueError("unsupported batch reader contract version")
    if metadata.batch_schema_metadata_version != BATCH_SCHEMA_METADATA_VERSION:
        raise ValueError("unsupported batch schema metadata version")
    return reader
