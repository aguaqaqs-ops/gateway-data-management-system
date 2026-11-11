"""Five-column locator shape and one admitted table result."""
from __future__ import annotations
from contextlib import ExitStack
from dataclasses import dataclass, field
import pyarrow as pa
from gateway_backend.capabilities.business_navigation.contracts import FilterRecord

LOCATOR_SCHEMA = pa.schema([
    pa.field("row_identity", pa.binary(32), nullable=False),
    pa.field("before_row_index", pa.int64()), pa.field("current_row_index", pa.int64()),
    pa.field("before_filter_context_json", pa.string()), pa.field("current_filter_context_json", pa.string()),
])


@dataclass(slots=True)
class RowLocationResult:
    records: tuple[FilterRecord, ...]
    scanned_rows: int
    batch: pa.RecordBatch | None
    charges: ExitStack = field(default_factory=ExitStack, repr=False)

    def close(self) -> None:
        # An operation callback may still reference this shell after a table
        # finishes; drop all result backing before returning its admission.
        self.records = ()
        self.batch = None
        self.charges.close()
