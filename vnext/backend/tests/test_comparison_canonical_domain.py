"""Canonical comparison semantics shared by uploaded and Repository snapshots."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_backend.application.preview_jobs import (
    _materialize_all_sides,
    decode_preview_payload,
)
from gateway_backend.capabilities.comparison import ComparisonTableStatus
from tests.support.history_compare_oracle import compare_bound_snapshots
from tests.support.preview_job_harness import (
    build_preview_harness,
    decode_payload_object,
)

pytestmark = pytest.mark.unit


def test_identical_uploaded_tables_add_only_empty_composite_table_to_baseline(
    tmp_path: Path,
) -> None:
    harness = build_preview_harness(
        tmp_path,
        canonical_noop=True,
    )
    harness.seed_workspace()
    payload = decode_preview_payload(decode_payload_object(harness))

    sides = _materialize_all_sides(payload, harness.deps)
    facts = compare_bound_snapshots(sides.sides["BASELINE"], sides.sides["INITIAL"])

    assert tuple((table.table_name, table.status) for table in facts.tables) == (
        ("composite_signal_point", ComparisonTableStatus.ADDED_TABLE),
        ("t", ComparisonTableStatus.UNCHANGED),
    )
    assert all(not table.records for table in facts.tables)
