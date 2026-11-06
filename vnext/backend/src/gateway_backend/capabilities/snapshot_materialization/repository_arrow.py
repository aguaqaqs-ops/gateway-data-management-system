"""Bounded physical wire-to-canonical Arrow conversion for retained columns.

Business validation, SET declaration ordering, digest and row sorting remain B's
owners. This only bridges Repository wire physical types already in use.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc  # type: ignore[import-untyped]

from gateway_backend.capabilities.snapshot_materialization.canonical_store import canonical_columns
from gateway_backend.capabilities.snapshot_materialization.contracts import SnapshotTableDescriptor
from gateway_backend.capabilities.table_access import current_kernel_context


@contextmanager
def canonical_repository_stream(
    source: pa.RecordBatchReader, descriptor: SnapshotTableDescriptor, *, budgets: dict[str, int],
) -> Iterator[pa.RecordBatchReader]:
    context = current_kernel_context()
    if context is None:
        raise ValueError("repository Arrow conversion requires an operation kernel context")
    context.checkpoint()
    columns = canonical_columns(descriptor)
    source_names = source.schema.names
    if len(set(source_names)) != len(source_names) or set(source_names) != {column["canonical_name"] for column in columns}:
        raise ValueError("repository Arrow names differ from bound schema")
    conversions: list[tuple[int, str, pa.DataType]] = []
    fields = []
    for column in columns:
        index = source.schema.get_field_index(column["canonical_name"])
        field = source.schema.field(index)
        kind = (column["declared_type"] or {}).get("kind")
        conversion = "identity"
        target = field.type
        if column["logical_type"] == "set":
            if not pa.types.is_list(field.type) or field.type.value_type != pa.string():
                raise ValueError("SET wire type must be list<utf8>")
            conversion, target = "set", pa.string()
        elif kind in ("signed-integer", "unsigned-integer"):
            bits = column["declared_type"]["bits"]
            width = 32 if bits == 24 else bits
            wire_type = getattr(pa, ("uint" if kind == "unsigned-integer" else "int") + str(width))()
            if field.type != wire_type:
                raise ValueError("integer wire type differs from declaration")
            conversion = "cast"
            target = pa.uint64() if kind == "unsigned-integer" else pa.int64()
        elif kind == "datetime":
            if field.type != pa.timestamp("us"):
                raise ValueError("DATETIME wire type must be civil timestamp(us)")
            conversion, target = "datetime", pa.string()
        elif kind == "float32" and field.type != pa.float32():
            raise ValueError("FLOAT wire type differs from declaration")
        elif kind == "float64" and field.type != pa.float64():
            raise ValueError("DOUBLE wire type differs from declaration")
        elif kind == "string" and field.type != pa.string():
            raise ValueError("text wire type differs from declaration")
        elif kind not in ("float32", "float64", "string"):
            raise ValueError("wire type has no canonical storage consumer")
        if field.nullable != column["nullable"]:
            raise ValueError("wire nullability differs from bound declaration")
        fields.append(pa.field(column["canonical_name"], target, nullable=column["nullable"]))
        conversions.append((index, conversion, target))
    schema = pa.schema(fields)

    # Convert before native reads its remaining-M cap. All output reservations
    # remain live until native and its borrowed input stream have completed.
    with ExitStack() as resources:
        batches: list[pa.RecordBatch] = []
        output_live = 0
        for batch in source:
            context.checkpoint()
            # Widening, SET join, DATETIME formatting and two trim arrays overlap
            # with this batch. The source wire mapping has its own reservation.
            conversion_peak = batch.get_total_buffer_size() * 8 + batch.num_rows * (len(columns) * 512 + 1024)
            if output_live + conversion_peak > budgets["max_live_bytes"]:
                raise MemoryError("repository Arrow conversion exceeds live budget")
            with context.memory.reserve(conversion_peak):
                arrays: list[Any] = []
                for index, conversion, target in conversions:
                    array = batch.column(index)
                    if conversion == "cast":
                        array = pc.cast(array, target, safe=True)
                    elif conversion == "set":
                        if pc.list_flatten(array).null_count:
                            raise ValueError("SET wire member must not be null")
                        array = pc.cast(array, pa.list_(pa.string()), safe=True)
                        array = pc.binary_join(array, ",")
                    elif conversion == "datetime":
                        array = pc.strftime(array, format="%Y-%m-%dT%H:%M:%S", locale="C")
                        array = pc.replace_substring_regex(array, pattern=r"(\.[0-9]*[1-9])0+$", replacement=r"\1")
                        array = pc.replace_substring_regex(array, pattern=r"\.0+$", replacement="")
                    arrays.append(array)
                output = pa.RecordBatch.from_arrays(arrays, schema=schema) if arrays else batch.select([])
                del arrays
            output_live += output.get_total_buffer_size()
            if output_live > budgets["max_input_bytes"] or output_live > budgets["max_output_bytes"]:
                raise MemoryError("repository Arrow converted buffers exceed byte budget")
            resources.enter_context(context.memory.retain_arrow(output))
            batches.append(output)
        context.checkpoint()
        with pa.RecordBatchReader.from_batches(schema, batches) as reader:
            yield reader
        context.checkpoint()
