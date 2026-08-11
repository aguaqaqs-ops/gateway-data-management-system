"""Arrow IPC stream byte assertions for versioned read tests."""

from __future__ import annotations

import pyarrow.ipc as pa_ipc  # type: ignore[import-untyped]

ARROW_IPC_STREAM_EOS = b"\xff\xff\xff\xff\x00\x00\x00\x00"


def assert_has_stream_eos(body: bytes) -> None:
    assert body.endswith(ARROW_IPC_STREAM_EOS), "expected Arrow IPC stream EOS trailer"


def assert_lacks_stream_eos(body: bytes) -> None:
    assert not body.endswith(ARROW_IPC_STREAM_EOS), "did not expect Arrow IPC stream EOS trailer"


def count_decoded_rows_without_error(body: bytes) -> int:
    stream = pa_ipc.open_stream(body)
    return sum(batch.num_rows for batch in stream)
