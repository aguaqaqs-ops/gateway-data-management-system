"""Cross-module SQL spelling to DeclaredType mapping guard tests."""

from __future__ import annotations

import pytest
from gateway_shared_kernel import DeclaredTypeKind

from gateway_backend.capabilities.comparison.standard import _declared_type
from gateway_backend.capabilities.snapshot_materialization.scalar_encoding import _declared_type_for
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    declared_type_for_sql_spelling,
)
from gateway_shared_kernel import NullScalar

pytestmark = pytest.mark.unit

_SQL_DECLARED_TYPE_CASES: tuple[tuple[str, DeclaredTypeKind, int | None], ...] = (
    ("INT", DeclaredTypeKind.SIGNED_INTEGER, 32),
    ("INT UNSIGNED", DeclaredTypeKind.UNSIGNED_INTEGER, 32),
    ("BIGINT", DeclaredTypeKind.SIGNED_INTEGER, 64),
    ("BIGINT UNSIGNED", DeclaredTypeKind.UNSIGNED_INTEGER, 64),
    ("TINYINT UNSIGNED", DeclaredTypeKind.UNSIGNED_INTEGER, 8),
    ("VARCHAR(8)", DeclaredTypeKind.STRING, None),
)


@pytest.mark.parametrize(
    ("spelling", "expected_kind", "expected_bits"),
    _SQL_DECLARED_TYPE_CASES,
    ids=tuple(case[0] for case in _SQL_DECLARED_TYPE_CASES),
)
def test_sql_spelling_maps_consistently_across_materialize_and_compare(
    spelling: str,
    expected_kind: DeclaredTypeKind,
    expected_bits: int | None,
) -> None:
    shared = declared_type_for_sql_spelling(spelling)
    materialize_declared, unknown = _declared_type_for(spelling)
    compare_declared = _declared_type(spelling, NullScalar())

    assert shared.kind is expected_kind
    assert shared.bits == expected_bits
    assert unknown is False
    assert materialize_declared == shared
    assert compare_declared == shared
