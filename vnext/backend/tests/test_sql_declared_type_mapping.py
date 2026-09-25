"""Cross-module SQL spelling to DeclaredType mapping guard tests."""

from __future__ import annotations

import pytest
from gateway_shared_kernel import DeclaredTypeKind, NullScalar

from gateway_backend.capabilities.comparison.standard import (
    StandardComparisonError,
    _declared_type,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import (
    SqlDeclaredTypeMappingError,
    declared_type_for_sql_spelling,
)
from gateway_backend.capabilities.snapshot_materialization.scalar_encoding import _declared_type_for

pytestmark = pytest.mark.unit

_SQL_DECLARED_TYPE_POSITIVE_CASES: tuple[
    tuple[str, DeclaredTypeKind, int | None, int | None, int | None],
    ...,
] = (
    ("INT", DeclaredTypeKind.SIGNED_INTEGER, 32, None, None),
    ("INT UNSIGNED", DeclaredTypeKind.UNSIGNED_INTEGER, 32, None, None),
    ("BIGINT", DeclaredTypeKind.SIGNED_INTEGER, 64, None, None),
    ("BIGINT UNSIGNED", DeclaredTypeKind.UNSIGNED_INTEGER, 64, None, None),
    ("TINYINT UNSIGNED", DeclaredTypeKind.UNSIGNED_INTEGER, 8, None, None),
    ("VARCHAR(8)", DeclaredTypeKind.STRING, None, None, None),
    ("SET('a','b')", DeclaredTypeKind.STRING, None, None, None),
    ("DECIMAL", DeclaredTypeKind.DECIMAL, None, 10, 0),
    ("DECIMAL(10)", DeclaredTypeKind.DECIMAL, None, 10, 0),
    ("DECIMAL(10,2)", DeclaredTypeKind.DECIMAL, None, 10, 2),
    ("DECIMAL(10,)", DeclaredTypeKind.DECIMAL, None, 10, 0),
    ("BIT", DeclaredTypeKind.BIT, 1, None, None),
    ("BIT(8)", DeclaredTypeKind.BIT, 8, None, None),
)

_SQL_DECLARED_TYPE_NEGATIVE_CASES: tuple[str, ...] = (
    "FOO",
    "DECIMAL(a,b)",
    "BIT(x)",
)


@pytest.mark.parametrize(
    ("spelling", "expected_kind", "expected_bits", "expected_precision", "expected_scale"),
    _SQL_DECLARED_TYPE_POSITIVE_CASES,
    ids=tuple(case[0] for case in _SQL_DECLARED_TYPE_POSITIVE_CASES),
)
def test_sql_spelling_maps_consistently_across_materialize_and_compare(
    spelling: str,
    expected_kind: DeclaredTypeKind,
    expected_bits: int | None,
    expected_precision: int | None,
    expected_scale: int | None,
) -> None:
    shared = declared_type_for_sql_spelling(spelling)
    materialize_declared, unknown = _declared_type_for(spelling)
    compare_declared = _declared_type(spelling, NullScalar())

    assert shared.kind is expected_kind
    if expected_kind in {DeclaredTypeKind.SIGNED_INTEGER, DeclaredTypeKind.UNSIGNED_INTEGER}:
        assert shared.bits == expected_bits
    if expected_kind is DeclaredTypeKind.BIT:
        assert shared.bit_width == expected_bits
    if expected_kind is DeclaredTypeKind.DECIMAL:
        assert shared.precision == expected_precision
        assert shared.scale == expected_scale
    assert unknown is False
    assert materialize_declared == shared
    assert compare_declared == shared


@pytest.mark.parametrize(
    "spelling",
    _SQL_DECLARED_TYPE_NEGATIVE_CASES,
    ids=_SQL_DECLARED_TYPE_NEGATIVE_CASES,
)
def test_sql_spelling_mapper_rejects_malformed_arguments(spelling: str) -> None:
    with pytest.raises(SqlDeclaredTypeMappingError):
        declared_type_for_sql_spelling(spelling)


@pytest.mark.parametrize(
    "spelling",
    _SQL_DECLARED_TYPE_NEGATIVE_CASES,
    ids=tuple(f"compare-{item}" for item in _SQL_DECLARED_TYPE_NEGATIVE_CASES),
)
def test_compare_declared_type_fail_closed_for_malformed_spelling(spelling: str) -> None:
    with pytest.raises(StandardComparisonError) as exc_info:
        _declared_type(spelling, NullScalar())
    assert str(exc_info.value) == "SCALAR_TYPE_UNKNOWN"
