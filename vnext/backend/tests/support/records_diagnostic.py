"""Exercise the standalone records reader outside the autouse operation scope."""

from __future__ import annotations

from contextlib import closing
from contextvars import Context

import pyarrow as pa

from gateway_backend.artifacts import ArtifactStorePort
from gateway_backend.capabilities.comparison.artifacts import read_records_artifact
from gateway_backend.capabilities.comparison.contracts import RecordsClosureEntry


def standalone_records_batches(
    store: ArtifactStorePort, entry: RecordsClosureEntry
) -> tuple[pa.RecordBatch, ...]:
    """Keep the entire diagnostic read and close inside its standalone scope."""

    def collect() -> tuple[pa.RecordBatch, ...]:
        with closing(read_records_artifact(store, entry)) as stream:
            return tuple(stream)

    return Context().run(collect)
