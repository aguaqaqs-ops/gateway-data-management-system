"""Ordered gid/no v1 identity: real range, blank pseudo allocation, continuous no."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from gateway_shared_kernel import (
    NullScalar,
    SignedIntegerScalar,
    StringScalar,
    UnsignedIntegerScalar,
)

from gateway_backend.capabilities.storage_projection.contracts import ProjectionDiagnosticCode

GID_REAL_MIN = 1
GID_REAL_MAX = 3_999_999_999
GID_PSEUDO_MIN = 4_000_000_000
GID_PSEUDO_MAX = 4_294_967_295


class OrderedProjectionError(Exception):
    def __init__(self, code: ProjectionDiagnosticCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class OrderedTableProjection:
    rows: tuple[tuple[object, ...], ...]
    real_count: int
    pseudo_count: int
    facts: tuple[dict[str, int], ...]


def project_ordered_rows(
    rows: Sequence[tuple[object, ...]],
    *,
    gid_index: int,
    no_index: int,
    allow_existing_pseudo: bool = False,
) -> OrderedTableProjection:
    parsed: list[tuple[int, int | None, tuple[object, ...]]] = []
    nos: set[int] = set()
    real_gids: set[int] = set()
    for row in rows:
        no_value = _parse_no(row[no_index])
        if no_value in nos:
            raise OrderedProjectionError(
                ProjectionDiagnosticCode.ROW_INTEGRITY,
                "ordered no is not unique",
            )
        nos.add(no_value)
        gid_value = _parse_gid_source(
            row[gid_index],
            allow_existing_pseudo=allow_existing_pseudo,
        )
        if gid_value is not None and gid_value < GID_PSEUDO_MIN:
            if gid_value in real_gids:
                raise OrderedProjectionError(
                    ProjectionDiagnosticCode.KEY_DUPLICATE,
                    "canonical key is not unique",
                )
            real_gids.add(gid_value)
        parsed.append((no_value, gid_value, row))
    row_count = len(parsed)
    if nos != set(range(1, row_count + 1)):
        raise OrderedProjectionError(
            ProjectionDiagnosticCode.ROW_INTEGRITY,
            "ordered no must be the continuous range 1..N",
        )
    parsed.sort(key=lambda item: item[0])
    next_pseudo = GID_PSEUDO_MIN
    projected: list[tuple[object, ...]] = []
    facts: list[dict[str, int]] = []
    pseudo_count = 0
    for no_value, gid_value, row in parsed:
        allocated = gid_value
        if allocated is None:
            if next_pseudo > GID_PSEUDO_MAX:
                raise OrderedProjectionError(
                    ProjectionDiagnosticCode.ROW_INTEGRITY,
                    "pseudo gid range is exhausted",
                )
            allocated = next_pseudo
            next_pseudo += 1
            pseudo_count += 1
        elif allocated >= GID_PSEUDO_MIN:
            if allocated != next_pseudo:
                raise OrderedProjectionError(
                    ProjectionDiagnosticCode.ROW_INTEGRITY,
                    "canonical pseudo gid does not match ordered allocation",
                )
            next_pseudo += 1
            pseudo_count += 1
        rewritten = list(row)
        rewritten[gid_index] = UnsignedIntegerScalar(decimal=str(allocated))
        projected.append(tuple(rewritten))
        facts.append({"gid": allocated, "no": no_value})
    return OrderedTableProjection(
        rows=tuple(projected),
        real_count=len(real_gids),
        pseudo_count=pseudo_count,
        facts=tuple(facts),
    )


def _parse_no(cell: object) -> int:
    value = _parse_integer_cell(cell, blank_is_none=False)
    if value is None or value < 1:
        raise OrderedProjectionError(
            ProjectionDiagnosticCode.ROW_INTEGRITY,
            "ordered no is missing",
        )
    return value


def _parse_gid_source(cell: object, *, allow_existing_pseudo: bool = False) -> int | None:
    value = _parse_integer_cell(cell, blank_is_none=True)
    if value is None:
        return None
    if GID_REAL_MIN <= value <= GID_REAL_MAX:
        return value
    if GID_PSEUDO_MIN <= value <= GID_PSEUDO_MAX:
        if allow_existing_pseudo:
            return value
        raise OrderedProjectionError(
            ProjectionDiagnosticCode.ROW_INTEGRITY,
            "source gid is in the reserved pseudo range",
        )
    raise OrderedProjectionError(
        ProjectionDiagnosticCode.ROW_INTEGRITY,
        "source gid is outside the real range",
    )


def _parse_integer_cell(cell: object, *, blank_is_none: bool) -> int | None:
    if isinstance(cell, NullScalar):
        if blank_is_none:
            return None
        return None
    if isinstance(cell, StringScalar):
        if cell.text == "":
            return None
        raise OrderedProjectionError(
            ProjectionDiagnosticCode.ROW_INTEGRITY,
            "ordered integer cell is not numeric",
        )
    if isinstance(cell, (SignedIntegerScalar, UnsignedIntegerScalar)):
        try:
            value = int(cell.decimal, 10)
        except ValueError as exc:
            raise OrderedProjectionError(
                ProjectionDiagnosticCode.ROW_INTEGRITY,
                "ordered integer cell is not numeric",
            ) from exc
        if blank_is_none and value == 0:
            return None
        if value < 0:
            raise OrderedProjectionError(
                ProjectionDiagnosticCode.ROW_INTEGRITY,
                "ordered integer cell must not be negative",
            )
        return value
    raise OrderedProjectionError(
        ProjectionDiagnosticCode.UNSUPPORTED_TABLE,
        "ordered integer cell is not a typed scalar",
    )
