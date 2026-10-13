"""Safety checks for aggregate real dump preview assertions."""

from __future__ import annotations

from typing import Any

import pytest

from benchmarks.real_dump_journey import (
    JourneyFailure,
    _history_facts_failure_detail,
    _history_surface_ref,
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

HISTORY_BUNDLE_SURFACE_REF_FAILURES: tuple[tuple[str, dict[str, Any]], ...] = (
    ("missing pair", {"pairs": []}),
    ("multiple pairs", {"pairs": [{"pair_id": "p0"}, {"pair_id": "p1"}]}),
    ("missing closure entries", {"pairs": [{"pair_id": "p0"}]}),
    (
        "missing surface artifact",
        {"pairs": [{"pair_id": "p0"}], "closure_entries": []},
    ),
    (
        "missing artifact ref",
        {
            "pairs": [{"pair_id": "p0"}],
            "closure_entries": [
                {"kind": "SURFACE", "logical_path": "pairs/p0/comparison-surface.json"}
            ],
        },
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


def test_history_bundle_surface_reference_is_selected_from_its_single_pair() -> None:
    surface_ref = {
        "artifact_id": "surface-abc",
        "media_type": "application/json",
        "raw_sha256": "sha256:" + "a" * 64,
        "size_bytes": 12,
    }

    bundle = {
        "pairs": [{"pair_id": "op-p0"}],
        "closure_entries": [
            {
                "kind": "RECORDS_CLOSURE",
                "logical_path": "pairs/op-p0/comparison/records/closure.json",
                "artifact_ref": {},
            },
            {
                "kind": "SURFACE",
                "logical_path": "pairs/op-p0/comparison-surface.json",
                "artifact_ref": surface_ref,
            },
        ],
    }

    assert _history_surface_ref(bundle) == surface_ref


def test_history_facts_failure_reports_a_fixed_validation_message() -> None:
    assert (
        _history_facts_failure_detail(
            "Traceback (most recent call last):\nSystemExit: "
            "blank records do not match net skeleton interval occupancy changes\n"
        )
        == "blank records do not match net skeleton interval occupancy changes"
    )


def test_history_facts_failure_does_not_echo_untrusted_exception_text() -> None:
    detail = _history_facts_failure_detail(
        "Traceback (most recent call last):\nKeyError: 'sensitive-row-value'\n"
    )

    assert detail.startswith("remote KeyError; stderr_sha256=")
    assert "sensitive-row-value" not in detail


def test_history_facts_failure_reports_sanitized_exception_location() -> None:
    detail = _history_facts_failure_detail(
        'S2B_HISTORY_DIAGNOSTIC={"exception":"KeyError",'
        '"frame":{"file":"<string> odd","line":166,"function":"<module> odd"},'
        '"key":{"kind":"field","value":"no"}}\n'
    )

    assert detail == "remote KeyError; at <string>_odd:166 in <module>_odd; key=field:no"


def test_history_facts_failure_reports_missing_traceback_frames() -> None:
    detail = _history_facts_failure_detail(
        'S2B_HISTORY_DIAGNOSTIC={"exception":"KeyError",'
        '"traceback_frame_count":0,"key":{"kind":"redacted",'
        '"sha256":"1a28676a200ccdab"}}\n'
    )

    assert detail == "remote KeyError; traceback_frames=0; key_sha256=1a28676a200ccdab"


@pytest.mark.parametrize(
    ("case", "bundle"),
    HISTORY_BUNDLE_SURFACE_REF_FAILURES,
    ids=[case for case, _bundle in HISTORY_BUNDLE_SURFACE_REF_FAILURES],
)
def test_history_bundle_rejects_an_invalid_surface_reference(
    case: str,
    bundle: dict[str, Any],
) -> None:
    del case
    with pytest.raises(JourneyFailure):
        _history_surface_ref(bundle)


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
