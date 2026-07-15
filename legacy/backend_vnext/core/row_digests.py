from __future__ import annotations

from collections.abc import Iterable, Sequence
import hashlib

from .digests import DigestRef, canonical_json_bytes
from .identifiers import canonical_identifier
from .scalar_encoding import normalize_snapshot_row


def stable_rows_digest(
    rows: Iterable[Sequence[object]],
    column_names: Sequence[str],
) -> DigestRef:
    """Return the stable row digest for already-normalized row values.

    The digest contract is the canonical JSON digest of ``{"rows": sorted_rows}``.
    Internally we keep only per-row canonical bytes while sorting, which avoids
    building a second large nested Python object for wide/large tables.
    """
    canonical_column_names = tuple(canonical_identifier(column_name) for column_name in column_names)
    if len(set(canonical_column_names)) != len(canonical_column_names):
        raise ValueError("column_names must resolve to unique canonical names")

    row_payloads: list[bytes] = []
    for row_index, row in enumerate(rows):
        if len(row) != len(canonical_column_names):
            raise ValueError(
                f"row {row_index} has {len(row)} values but expected {len(canonical_column_names)}"
            )
        row_payload = tuple(
            sorted(
                (
                    (canonical_column_names[position], row[position])
                    for position in range(len(canonical_column_names))
                ),
                key=lambda item: item[0],
            )
        )
        row_payloads.append(canonical_json_bytes(row_payload))

    return _digest_sorted_row_payloads(row_payloads)


def stable_snapshot_rows_digest(
    rows: Iterable[Sequence[object]],
    columns: Sequence[object],
) -> DigestRef:
    """Normalize raw snapshot rows and return the stable row digest."""
    column_names = tuple(canonical_identifier(getattr(column, "name", "")) for column in columns)
    if len(set(column_names)) != len(column_names):
        raise ValueError("columns must resolve to unique canonical names")

    row_payloads: list[bytes] = []
    for row_index, row in enumerate(rows):
        try:
            normalized_row = normalize_snapshot_row(row, columns)
        except ValueError as exc:
            raise ValueError(f"row {row_index}: {exc}") from exc
        row_payload = tuple(
            sorted(
                (
                    (column_names[position], normalized_row[position])
                    for position in range(len(column_names))
                ),
                key=lambda item: item[0],
            )
        )
        row_payloads.append(canonical_json_bytes(row_payload))
    return _digest_sorted_row_payloads(row_payloads)


def _digest_sorted_row_payloads(row_payloads: list[bytes]) -> DigestRef:
    hasher = hashlib.sha256()
    hasher.update(b'{"rows":[')
    for index, row_payload in enumerate(sorted(row_payloads)):
        if index:
            hasher.update(b",")
        hasher.update(row_payload)
    hasher.update(b"]}")
    return DigestRef.from_hex(hasher.hexdigest())
