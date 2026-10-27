"""Deterministic repository replay SQL renderer for ChangeSet closures."""

from __future__ import annotations

import base64
import math
import re
import struct
from dataclasses import dataclass
from typing import Callable, Literal

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.capabilities.mutation_planning.contracts import (
    MAX_REPLAY_SQL_BYTES,
    RENDERER_CAPABILITY_CONTRACT_VERSION,
    CanonicalCellValue,
    CanonicalStorageKey,
    ChangeSetClosure,
    ChangeSetMutation,
    MutationFailureCode,
    MutationTargetKind,
    PersistedRowImage,
    RendererCapabilityDeclaration,
    RowMutationOperation,
    validate_canonical_cell_value,
)

_REPOSITORY_REPLAY_CAPABILITY_VERSION = "v1"
_REPOSITORY_REPLAY_DIALECT = "mysql-repository-replay/v1"
_SUPPORTED_OPERATIONS = ("DELETE", "INSERT", "UPDATE")
_SUPPORTED_CELL_KINDS = (
    "bit",
    "binary",
    "boolean",
    "date",
    "datetime",
    "decimal",
    "float32",
    "float64",
    "null",
    "signed-integer",
    "string",
    "time-duration",
    "timestamp",
    "unsigned-integer",
)
_FLOAT32_BITS_RE = re.compile(r"^[0-9a-f]{8}$")
_FLOAT64_BITS_RE = re.compile(r"^[0-9a-f]{16}$")
_ASCII_FLOAT_RE = re.compile(
    r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"
)
_MAX_INSERT_ROWS_PER_STATEMENT = 256
_MAX_INSERT_STATEMENT_BYTES = 4 * 1024 * 1024
_MAX_DELETE_ROWS_PER_STATEMENT = 256
_MAX_DELETE_STATEMENT_BYTES = 4 * 1024 * 1024
_MAX_UPDATE_ROWS_PER_STATEMENT = 256
_MAX_UPDATE_STATEMENT_BYTES = 4 * 1024 * 1024

ReplayRenderStatus = Literal["READY", "FAILED"]


@dataclass(frozen=True, slots=True)
class ReplayRenderOutcome:
    status: ReplayRenderStatus
    sql_bytes: bytes | None = None
    failure_code: MutationFailureCode | None = None
    sql_digest: DigestRef | None = None


def repository_replay_capability_payload() -> dict[str, object]:
    return {
        "dialect": _REPOSITORY_REPLAY_DIALECT,
        "identifier_quoting": "backtick",
        "supported_cell_kinds": list(_SUPPORTED_CELL_KINDS),
        "supported_operations": list(_SUPPORTED_OPERATIONS),
    }


def compute_repository_replay_capability_digest() -> DigestRef:
    return raw_blob_digest(
        canonicalize_json_value(repository_replay_capability_payload())
    )


REPOSITORY_REPLAY_RENDERER_CAPABILITY = RendererCapabilityDeclaration(
    target_kind=MutationTargetKind.CANONICAL_REPOSITORY_REPLAY,
    capability_version=_REPOSITORY_REPLAY_CAPABILITY_VERSION,
    capability_digest=compute_repository_replay_capability_digest(),
    capability_contract_version=RENDERER_CAPABILITY_CONTRACT_VERSION,
)


def render_change_set_replay(
    closure: ChangeSetClosure,
    *,
    expected_renderer_capability: RendererCapabilityDeclaration | None = None,
) -> ReplayRenderOutcome:
    manifest_capability = closure.manifest.renderer_capability
    expected = expected_renderer_capability or REPOSITORY_REPLAY_RENDERER_CAPABILITY
    if manifest_capability != expected:
        return _failed(MutationFailureCode.TARGET_CAPABILITY_UNSUPPORTED)
    if manifest_capability.target_kind is not MutationTargetKind.CANONICAL_REPOSITORY_REPLAY:
        return _failed(MutationFailureCode.TARGET_CAPABILITY_UNSUPPORTED)
    for mutation in closure.mutations:
        if _mutation_has_unsupported_cells(mutation):
            return _failed(MutationFailureCode.TARGET_CAPABILITY_UNSUPPORTED)
    try:
        sql_bytes = _render_mutations(closure.mutations)
    except _RenderCapabilityError:
        return _failed(MutationFailureCode.TARGET_CAPABILITY_UNSUPPORTED)
    except _RenderSizeError:
        return _failed(MutationFailureCode.RESOURCE_EXCEEDED)
    if len(sql_bytes) > MAX_REPLAY_SQL_BYTES:
        return _failed(MutationFailureCode.RESOURCE_EXCEEDED)
    return ReplayRenderOutcome(
        status="READY",
        sql_bytes=sql_bytes,
        sql_digest=raw_blob_digest(sql_bytes),
    )


class _RenderCapabilityError(Exception):
    """Cell or identifier cannot be rendered safely."""


def _failed(code: MutationFailureCode) -> ReplayRenderOutcome:
    return ReplayRenderOutcome(status="FAILED", failure_code=code)


def _mutation_has_unsupported_cells(mutation: ChangeSetMutation) -> bool:
    for _, cell in mutation.canonical_storage_key.columns:
        if _cell_kind(cell) == "source-literal-anomaly":
            return True
    if mutation.after_image is not None:
        for _, cell in mutation.after_image.columns:
            if _cell_kind(cell) == "source-literal-anomaly":
                return True
    return False


def _cell_kind(cell: CanonicalCellValue) -> str:
    return str(cell.get("kind", ""))


def _render_mutations(mutations: tuple[ChangeSetMutation, ...]) -> bytes:
    parts: list[bytes] = []
    total = 0
    cleared_keyless_tables: set[str] = set()

    def append(statement: bytes) -> None:
        nonlocal total
        if total + len(statement) > MAX_REPLAY_SQL_BYTES:
            raise _RenderSizeError()
        parts.append(statement)
        total += len(statement)

    pending_insert_values: list[bytes] = []
    pending_insert_identity: tuple[str, tuple[str, ...]] | None = None
    pending_insert_prefix: bytes | None = None
    pending_insert_bytes = 0

    def flush_inserts() -> None:
        nonlocal pending_insert_bytes, pending_insert_identity, pending_insert_prefix
        if not pending_insert_values:
            return
        if pending_insert_prefix is None:
            raise _RenderCapabilityError("INSERT batch prefix is missing")
        append(
            pending_insert_prefix
            + b", ".join(pending_insert_values)
            + b";\n"
        )
        pending_insert_values.clear()
        pending_insert_identity = None
        pending_insert_prefix = None
        pending_insert_bytes = 0

    index = 0
    while index < len(mutations):
        mutation = mutations[index]
        if mutation.operation is RowMutationOperation.INSERT:
            if mutation.after_image is None:
                raise _RenderCapabilityError("INSERT requires after_image")
            identity = (
                mutation.canonical_table,
                tuple(column for column, _ in mutation.after_image.columns),
            )
            prefix = (
                f"INSERT INTO {_quote_identifier(mutation.canonical_table)} "
                f"({_quoted_column_list(mutation.after_image)}) VALUES "
            ).encode("utf-8")
            row_values = f"({_value_list(mutation.after_image)})".encode("utf-8")
            new_batch = pending_insert_identity != identity
            if (
                not new_batch
                and pending_insert_values
                and pending_insert_bytes + 2 + len(row_values) > _MAX_INSERT_STATEMENT_BYTES
            ):
                new_batch = True
            if new_batch:
                flush_inserts()
                pending_insert_identity = identity
            additional_separator_bytes = 2 if pending_insert_values else 0
            if not pending_insert_values:
                pending_insert_prefix = prefix
                pending_insert_bytes = len(prefix) + len(b";\n")
            pending_insert_values.append(row_values)
            pending_insert_bytes += len(row_values) + additional_separator_bytes
            if (
                len(pending_insert_values) >= _MAX_INSERT_ROWS_PER_STATEMENT
            ):
                flush_inserts()
            index += 1
            continue

        flush_inserts()
        if mutation.operation is RowMutationOperation.DELETE and not mutation.canonical_storage_key.columns:
            table = mutation.canonical_table
            while (
                index < len(mutations)
                and mutations[index].canonical_table == table
                and mutations[index].operation is RowMutationOperation.DELETE
                and not mutations[index].canonical_storage_key.columns
            ):
                index += 1
            if table not in cleared_keyless_tables:
                cleared_keyless_tables.add(table)
                append(f"DELETE FROM {_quote_identifier(table)};\n".encode("utf-8"))
            continue

        if mutation.operation is RowMutationOperation.DELETE:
            batch: list[ChangeSetMutation] = []
            while index < len(mutations):
                candidate = mutations[index]
                if (
                    candidate.canonical_table != mutation.canonical_table
                    or candidate.operation is not RowMutationOperation.DELETE
                    or _key_column_names(candidate) != _key_column_names(mutation)
                ):
                    break
                batch.append(candidate)
                index += 1
            for statement in _render_delete_batches(batch):
                append(statement)
            continue

        if mutation.operation is RowMutationOperation.UPDATE:
            batch = []
            mutation_shape = _update_shape(mutation)
            while index < len(mutations):
                candidate = mutations[index]
                if (
                    candidate.canonical_table != mutation.canonical_table
                    or candidate.operation is not RowMutationOperation.UPDATE
                    or _update_shape(candidate) != mutation_shape
                ):
                    break
                batch.append(candidate)
                index += 1
            for statement in _render_update_batches(batch):
                append(statement)
            continue

        raise _RenderCapabilityError("unsupported mutation operation")
    flush_inserts()
    return b"".join(parts)


class _RenderSizeError(Exception):
    """Rendered output would exceed the replay byte cap."""


def _key_column_names(mutation: ChangeSetMutation) -> tuple[str, ...]:
    return tuple(column for column, _ in mutation.canonical_storage_key.columns)


def _update_shape(mutation: ChangeSetMutation) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    if mutation.after_image is None:
        raise _RenderCapabilityError("UPDATE requires after_image")
    return (
        mutation.canonical_table,
        _key_column_names(mutation),
        tuple(column for column, _ in mutation.after_image.columns),
    )


def _key_predicate_batch(keys: tuple[CanonicalStorageKey, ...]) -> str:
    if not keys or not keys[0].columns:
        raise _RenderCapabilityError("batched key predicate requires keyed rows")
    column_names = tuple(column for column, _ in keys[0].columns)
    if any(tuple(column for column, _ in key.columns) != column_names for key in keys):
        raise _RenderCapabilityError("batched keys must use the same columns")
    if len(column_names) == 1:
        values = ",".join(
            _render_literal(key.columns[0][1], label=column_names[0]) for key in keys
        )
        return f"{_quote_identifier(column_names[0])} IN ({values})"
    columns = ",".join(_quote_identifier(column) for column in column_names)
    values = ",".join(
        "("
        + ", ".join(
            _render_literal(cell, label=column)
            for column, cell in key.columns
        )
        + ")"
        for key in keys
    )
    return f"({columns}) IN ({values})"


def _render_delete_batch(mutations: tuple[ChangeSetMutation, ...]) -> bytes:
    if not mutations:
        raise _RenderCapabilityError("DELETE batch cannot be empty")
    first = mutations[0]
    if any(
        item.operation is not RowMutationOperation.DELETE
        or item.canonical_table != first.canonical_table
        or _key_column_names(item) != _key_column_names(first)
        for item in mutations
    ):
        raise _RenderCapabilityError("DELETE batch contains incompatible mutations")
    keys = tuple(item.canonical_storage_key for item in mutations)
    statement = (
        f"DELETE FROM {_quote_identifier(first.canonical_table)} "
        f"WHERE {_key_predicate_batch(keys)};\n"
    )
    return statement.encode("utf-8")


def _render_delete_batches(mutations: list[ChangeSetMutation]) -> tuple[bytes, ...]:
    return _render_limited_mutation_batches(
        mutations,
        row_limit=_MAX_DELETE_ROWS_PER_STATEMENT,
        byte_limit=_MAX_DELETE_STATEMENT_BYTES,
        render=_render_delete_batch,
    )


def _render_update_batch(mutations: tuple[ChangeSetMutation, ...]) -> bytes:
    if not mutations:
        raise _RenderCapabilityError("UPDATE batch cannot be empty")
    first = mutations[0]
    if first.after_image is None:
        raise _RenderCapabilityError("UPDATE requires after_image")
    if any(
        item.operation is not RowMutationOperation.UPDATE
        or _update_shape(item) != _update_shape(first)
        for item in mutations
    ):
        raise _RenderCapabilityError("UPDATE batch contains incompatible mutations")
    key_columns = set(_key_column_names(first))
    updated_columns = tuple(
        column for column, _ in first.after_image.columns if column not in key_columns
    )
    if not updated_columns:
        raise _RenderCapabilityError("UPDATE requires at least one SET assignment")
    image_cells = [dict(item.after_image.columns) for item in mutations if item.after_image is not None]
    assignments: list[str] = []
    for column in updated_columns:
        branches = " ".join(
            f"WHEN {_key_predicate(item.canonical_storage_key)} THEN "
            f"{_render_literal(image[column], label=column)}"
            for item, image in zip(mutations, image_cells, strict=True)
        )
        quoted_column = _quote_identifier(column)
        assignments.append(
            f"{quoted_column}=CASE {branches} ELSE {quoted_column} END"
        )
    where = _key_predicate_batch(
        tuple(item.canonical_storage_key for item in mutations)
    )
    statement = (
        f"UPDATE {_quote_identifier(first.canonical_table)} "
        f"SET {', '.join(assignments)} WHERE {where};\n"
    )
    return statement.encode("utf-8")


def _render_update_batches(mutations: list[ChangeSetMutation]) -> tuple[bytes, ...]:
    return _render_limited_mutation_batches(
        mutations,
        row_limit=_MAX_UPDATE_ROWS_PER_STATEMENT,
        byte_limit=_MAX_UPDATE_STATEMENT_BYTES,
        render=_render_update_batch,
    )


def _render_limited_mutation_batches(
    mutations: list[ChangeSetMutation],
    *,
    row_limit: int,
    byte_limit: int,
    render: Callable[[tuple[ChangeSetMutation, ...]], bytes],
) -> tuple[bytes, ...]:
    statements: list[bytes] = []
    for offset in range(0, len(mutations), row_limit):
        row_limited = mutations[offset : offset + row_limit]
        batch: tuple[ChangeSetMutation, ...] = ()
        rendered_batch: bytes | None = None
        for mutation in row_limited:
            candidate = (*batch, mutation)
            rendered_candidate = render(candidate)
            if batch and len(rendered_candidate) > byte_limit:
                assert rendered_batch is not None
                statements.append(rendered_batch)
                batch = (mutation,)
                rendered_batch = render(batch)
            else:
                batch = candidate
                rendered_batch = rendered_candidate
            if len(batch) >= row_limit:
                assert rendered_batch is not None
                statements.append(rendered_batch)
                batch = ()
                rendered_batch = None
        if batch:
            assert rendered_batch is not None
            statements.append(rendered_batch)
    return tuple(statements)


def _quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier or "/" in identifier or "\\" in identifier:
        raise _RenderCapabilityError("invalid SQL identifier")
    return "`" + identifier.replace("`", "``") + "`"


def _quoted_column_list(image: PersistedRowImage) -> str:
    return ", ".join(_quote_identifier(column) for column, _ in image.columns)


def _value_list(image: PersistedRowImage) -> str:
    return ", ".join(_render_literal(cell, label=column) for column, cell in image.columns)


def _key_predicate(key: CanonicalStorageKey) -> str:
    parts = [
        f"{_quote_identifier(column)}={_render_literal(cell, label=column)}"
        for column, cell in key.columns
    ]
    return " AND ".join(parts)


def _render_literal(cell: CanonicalCellValue, *, label: str) -> str:
    validated = validate_canonical_cell_value(cell, label)
    kind = validated["kind"]
    if kind == "null":
        return "NULL"
    if kind == "boolean":
        return "TRUE" if validated["value"] else "FALSE"
    if kind in {"signed-integer", "unsigned-integer", "decimal"}:
        return str(validated["decimal"])
    if kind == "float32":
        return _format_float_literal(str(validated["bits_hex"]), width=32)
    if kind == "float64":
        return _format_float_literal(str(validated["bits_hex"]), width=64)
    if kind in {"string", "date", "datetime", "timestamp", "time-duration"}:
        return "'" + _escape_string(str(validated["text"])) + "'"
    if kind == "binary":
        raw = _decode_base64url(str(validated["bytes_base64url"]))
        return "X'" + raw.hex().upper() + "'"
    if kind == "bit":
        raw = _decode_base64url(str(validated["bytes_base64url"]))
        digits = "".join(f"{byte:08b}" for byte in raw)
        return f"b'{digits}'"
    raise _RenderCapabilityError(f"unsupported cell kind {kind}")


def _decode_base64url(encoded: str) -> bytes:
    padding = "=" * ((4 - len(encoded) % 4) % 4)
    return base64.urlsafe_b64decode(encoded + padding)


def _escape_string(text: str) -> str:
    escaped: list[str] = []
    for character in text:
        if character == "\\":
            escaped.append("\\\\")
        elif character == "'":
            escaped.append("\\'")
        elif character == "\n":
            escaped.append("\\n")
        elif character == "\r":
            escaped.append("\\r")
        elif character == "\0":
            escaped.append("\\0")
        elif character == "\t":
            escaped.append("\\t")
        else:
            escaped.append(character)
    return "".join(escaped)


def _format_float_literal(bits_hex: str, *, width: int) -> str:
    if width == 32:
        if _FLOAT32_BITS_RE.fullmatch(bits_hex) is None:
            raise _RenderCapabilityError("float32 bits_hex is invalid")
        bits = int(bits_hex, 16)
        value = struct.unpack(">f", struct.pack(">I", bits))[0]
    else:
        if _FLOAT64_BITS_RE.fullmatch(bits_hex) is None:
            raise _RenderCapabilityError("float64 bits_hex is invalid")
        bits = int(bits_hex, 16)
        value = struct.unpack(">d", struct.pack(">Q", bits))[0]
    if not math.isfinite(value):
        raise _RenderCapabilityError("float must be finite")
    text = _ascii_float_text(value)
    if _ASCII_FLOAT_RE.fullmatch(text) is None:
        raise _RenderCapabilityError("float literal is not ASCII float grammar")
    return text


def _ascii_float_text(value: float) -> str:
    if not math.isfinite(value):
        raise _RenderCapabilityError("float must be finite")
    if value == 0.0 and math.copysign(1.0, value) < 0:
        value = 0.0
    text = format(value, ".15g")
    if "e" in text or "E" in text:
        return text
    if "." not in text and "e" not in text.lower():
        return text
    text = text.rstrip("0").rstrip(".")
    return text if text else "0"

