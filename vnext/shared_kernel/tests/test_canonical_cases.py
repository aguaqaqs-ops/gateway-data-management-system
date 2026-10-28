"""Ordinary Python owner tests for the shared canonical case corpus."""

from __future__ import annotations

import pytest

from gateway_shared_kernel.testing.dispatch import dispatch_case

from tests.canonical_cases import load_canonical_cases

_CASES = load_canonical_cases()


def test_canonical_case_set_is_exact_and_nonempty() -> None:
    assert len(_CASES) == 129
    assert len({case["case_id"] for case in _CASES}) == len(_CASES)


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["case_id"])
def test_canonical_case_matches_python_reference(case: dict[str, object]) -> None:
    dispatch_case(case)
