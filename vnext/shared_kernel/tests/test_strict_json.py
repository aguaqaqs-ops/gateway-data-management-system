"""Strict JSON loader regression tests."""

from __future__ import annotations

import pytest

from gateway_shared_kernel.testing.strict_json import (
    DuplicateMemberError,
    NonJsonConstantError,
    loads_object_rejecting_duplicates,
)


def test_rejects_nan_and_infinity_constants() -> None:
    with pytest.raises(NonJsonConstantError):
        loads_object_rejecting_duplicates('{"x":NaN}')
    with pytest.raises(NonJsonConstantError):
        loads_object_rejecting_duplicates('{"x":Infinity}')
    with pytest.raises(NonJsonConstantError):
        loads_object_rejecting_duplicates('{"x":-Infinity}')


def test_rejects_nested_duplicate_members() -> None:
    with pytest.raises(DuplicateMemberError):
        loads_object_rejecting_duplicates('{"a":{"k":1,"k":2}}')
