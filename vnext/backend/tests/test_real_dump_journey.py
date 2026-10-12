"""Safety checks for aggregate real dump preview assertions."""

from __future__ import annotations

from typing import Any

import pytest

from benchmarks.real_dump_journey import (
    JourneyFailure,
    _keyless_fallback_table_names,
)

pytestmark = pytest.mark.unit

REPEAT_KEYLESS_FAILURES = (
    (
        "changed table",
        {"diagnostics": {"diagnostics_summary": "KEYLESS_FALLBACK"}, "change_kind": "MODIFIED"},
    ),
    (
        "missing hint",
        {"diagnostics": {"diagnostics_summary": ""}, "change_kind": "UNCHANGED"},
    ),
)


def _surface(table: dict[str, Any]) -> dict[str, Any]:
    return {"surface_id": "preview-pair", "tables": [table]}


def test_preview_finds_distinct_keyless_fallback_tables_across_pairs() -> None:
    surfaces = [
        _surface(
            {
                "table_name": "fallback_a",
                "change_kind": "ADDED_TABLE",
                "diagnostics": {"diagnostics_summary": ["KEYLESS_FALLBACK"]},
            }
        ),
        _surface(
            {
                "table_name": "fallback_a",
                "change_kind": "UNCHANGED",
                "diagnostics": {"diagnostics_summary": "KEYLESS_FALLBACK"},
            }
        ),
        _surface(
            {
                "table_name": "keyed_table",
                "change_kind": "UNCHANGED",
                "diagnostics": {"diagnostics_summary": ""},
            }
        ),
    ]

    names = _keyless_fallback_table_names(surfaces, label="test Preview")

    assert names == ("fallback_a",)


def test_preview_fails_when_key_missing_is_reported() -> None:
    surfaces = [
        _surface(
            {
                "table_name": "fallback_a",
                "change_kind": "DEGRADED",
                "diagnostics": {"diagnostics_summary": ["KEY_MISSING"]},
            }
        )
    ]

    with pytest.raises(JourneyFailure, match="KEY_MISSING"):
        _keyless_fallback_table_names(surfaces, label="test Preview")


@pytest.mark.parametrize(
    ("case", "table_state"),
    REPEAT_KEYLESS_FAILURES,
    ids=[case for case, _state in REPEAT_KEYLESS_FAILURES],
)
def test_repeat_preview_requires_same_unchanged_keyless_tables(
    case: str,
    table_state: dict[str, Any],
) -> None:
    del case
    surface = _surface(
        {
            "table_name": "fallback_a",
            **table_state,
        }
    )

    with pytest.raises(JourneyFailure):
        _keyless_fallback_table_names(
            [surface],
            label="repeat Preview",
            expected_names=("fallback_a",),
            require_unchanged=True,
        )
