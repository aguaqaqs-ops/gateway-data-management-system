"""Independent shared-kernel oracle for the production native identity stream."""
from __future__ import annotations

import json
from contextlib import closing

import pyarrow as pa
import pytest
from gateway_shared_kernel import (
    DeclaredType, DeclaredTypeKind, DigestKind, RowField, SignedIntegerScalar,
    StringScalar, encode_row, semantic_digest,
)
from gateway_shared_kernel.uleb128 import encode_uleb128

from gateway_backend.capabilities.comparison import native
from gateway_backend.capabilities.snapshot_materialization import canonical_comparison_input
from gateway_backend.capabilities.table_access import current_kernel_context
from tests.support.comparison_s3_e_live import canonical_bound


@pytest.mark.parametrize(("keyless", "columns_added"), ((False, False), (True, False), (True, True)))
def test_native_identity_batch_stream_matches_independent_codec(keyless: bool, columns_added: bool) -> None:
    source = canonical_bound("CREATE TABLE t (id BIGINT, note TEXT); INSERT INTO t VALUES (7,'same'),(7,'same'),(7,'same');")
    assert source.table_set is not None
    context = current_kernel_context()
    assert context is not None
    baseline = context.memory.used_bytes
    policy = json.dumps({"mode": "keyless" if keyless else "keyed", "selected_columns": ["note", "id"],
        "effective_key_before": ["id"], "effective_key_current": ["id"],
        "compare_excluded_columns": ["note"], "columns_added": columns_added})
    fields = [RowField("id", DeclaredType(DeclaredTypeKind.SIGNED_INTEGER, bits=64), SignedIntegerScalar("7"))]
    text = RowField("note", DeclaredType(DeclaredTypeKind.STRING), StringScalar("same"))
    full = encode_row([*fields, text])
    if keyless and not columns_added:
        fields.append(text)
    base = encode_row(fields).digest_ref.value
    with closing(native.begin_records_operation(native_budget_bytes=16 * 1024**2,
            cancel_probe=context.cancel_probe, deadline_monotonic=context.deadline_monotonic)) as operation:
        with closing(native.standard_identity_scanner(operation, policy)) as scanner:
            stream, owner = canonical_comparison_input(source.table_set.tables[0])
            with closing(owner), closing(stream):
                offset = 0
                for batch in stream:
                    for index in range(batch.num_rows):
                        part = batch.slice(index, 1)
                        with pa.RecordBatchReader.from_batches(part.schema, [part]) as reader:
                            identities, order_keys = scanner.scan(reader, part.nbytes + 4096)
                        expected = base
                        if keyless and offset:
                            expected = semantic_digest(DigestKind.ROW,
                                b"keyless-row-occurrence:v1\0" + base.encode() + encode_uleb128(offset)).digest_ref.value
                        assert identities == [expected]
                        assert order_keys == [full.row_frame]
                        offset += 1
                assert offset == 3
    assert context.memory.used_bytes == baseline
