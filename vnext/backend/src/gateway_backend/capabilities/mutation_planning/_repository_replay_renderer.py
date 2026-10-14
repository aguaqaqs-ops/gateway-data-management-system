"""Deterministic repository replay SQL renderer for ChangeSet closures."""

from __future__ import annotations

import base64
import math
import re
import struct
from dataclasses import dataclass
from typing import Literal

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

    for mutation in mutations:
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
                pending_insert_bytes = len(prefix)
            pending_insert_values.append(row_values)
            pending_insert_bytes += len(row_values) + additional_separator_bytes
            if (
                len(pending_insert_values) >= _MAX_INSERT_ROWS_PER_STATEMENT
                or pending_insert_bytes >= _MAX_INSERT_STATEMENT_BYTES
            ):
                flush_inserts()
            continue

        flush_inserts()
        if mutation.operation is RowMutationOperation.DELETE and not mutation.canonical_storage_key.columns:
            if mutation.canonical_table in cleared_keyless_tables:
                continue
            cleared_keyless_tables.add(mutation.canonical_table)
            append(
                f"DELETE FROM {_quote_identifier(mutation.canonical_table)};\n".encode("utf-8")
            )
        else:
            append(_render_mutation(mutation))
    flush_inserts()
    return b"".join(parts)


class _RenderSizeError(Exception):
    """Rendered output would exceed the replay byte cap."""


def _render_mutation(mutation: ChangeSetMutation) -> bytes:
    table = _quote_identifier(mutation.canonical_table)
    if mutation.operation is RowMutationOperation.DELETE:
        where = _key_predicate(mutation.canonical_storage_key)
        return f"DELETE FROM {table} WHERE {where};\n".encode("utf-8")
    if mutation.operation is RowMutationOperation.UPDATE:
        if mutation.after_image is None:
            raise _RenderCapabilityError("UPDATE requires after_image")
        key_columns = {column for column, _ in mutation.canonical_storage_key.columns}
        assignments = _assignment_list(mutation.after_image, exclude=key_columns)
        where = _key_predicate(mutation.canonical_storage_key)
        return f"UPDATE {table} SET {assignments} WHERE {where};\n".encode("utf-8")
    if mutation.after_image is None:
        raise _RenderCapabilityError("INSERT requires after_image")
    columns = _quoted_column_list(mutation.after_image)
    values = _value_list(mutation.after_image)
    return f"INSERT INTO {table} ({columns}) VALUES ({values});\n".encode("utf-8")


def _quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier or "/" in identifier or "\\" in identifier:
        raise _RenderCapabilityError("invalid SQL identifier")
    return "`" + identifier.replace("`", "``") + "`"


def _quoted_column_list(image: PersistedRowImage) -> str:
    return ", ".join(_quote_identifier(column) for column, _ in image.columns)


def _assignment_list(image: PersistedRowImage, *, exclude: set[str]) -> str:
    assignments: list[str] = []
    for column, cell in image.columns:
        if column in exclude:
            continue
        assignments.append(
            f"{_quote_identifier(column)}={_render_literal(cell, label=column)}"
        )
    if not assignments:
        raise _RenderCapabilityError("UPDATE requires at least one SET assignment")
    return ", ".join(assignments)


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

