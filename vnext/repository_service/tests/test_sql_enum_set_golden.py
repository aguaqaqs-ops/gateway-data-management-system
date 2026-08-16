"""Ordinary Repository owner tests for the ENUM/SET golden corpus."""

from typing import Any

import pytest

from support.sql_enum_set_cases import dispatch_sql_enum_set_case, load_sql_enum_set_cases

_CASES = load_sql_enum_set_cases()


def test_sql_enum_set_case_set_is_exact_and_nonempty() -> None:
    assert _CASES
    assert len({case["case_id"] for case in _CASES}) == len(_CASES)


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case["case_id"])
def test_sql_enum_set_case_matches_repository_owner(case: dict[str, Any]) -> None:
    dispatch_sql_enum_set_case(case)
