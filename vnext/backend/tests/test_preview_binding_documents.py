"""The modified durable Preview binding rejects coercions, omissions and extra fields."""

from __future__ import annotations

import json
from typing import Any

import pytest

from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_backend.infrastructure.control_db.sqlite_workspace import (
    preview_result_to_row,
    preview_result_from_row,
)
from tests.test_submit_transactions import _preview_result

pytestmark = pytest.mark.unit
_DOCUMENT_FAULTS = (
    ("extra", ("unexpected",), "value"),
    ("integer-string", ("baseline_head_version",), "3"),
    ("integer-bool", ("baseline_head_version",), True),
    ("nested-ref-extra", ("canonical", "canonical_table_set_closure_ref", "extra"), 1),
    ("pair-digest-number", ("comparison_pairs", 0, "comparison_digest"), 17),
    ("pair-extra", ("comparison_pairs", 0, "extra"), "x"),
)


def _row() -> dict[str, Any]:
    values = preview_result_to_row(_preview_result("workspace-document"))
    return dict(
        zip(
            (
                "preview_result_id",
                "workspace_id",
                "upload_revision_id",
                "generation",
                "repository_id",
                "binding",
                "operation_id",
                "created_at_us",
            ),
            values,
            strict=True,
        )
    )


@pytest.mark.parametrize(
    "label,path,value", _DOCUMENT_FAULTS, ids=[fault[0] for fault in _DOCUMENT_FAULTS]
)
def test_preview_binding_rejects_coercion_and_extra_fields(
    label: str, path: tuple[str | int, ...], value: Any
) -> None:
    del label
    row = _row()
    document = json.loads(row["binding"])
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    row["binding"] = canonicalize_json_value(document)
    with pytest.raises(ValueError):
        preview_result_from_row(row)


def test_preview_binding_requires_new_pair_binding_and_roundtrips_exactly() -> None:
    row = _row()
    preview = preview_result_from_row(row)
    assert preview_result_to_row(preview) == tuple(row.values())
    document = json.loads(row["binding"])
    del document["comparison_pairs"]
    row["binding"] = canonicalize_json_value(document)
    with pytest.raises(ValueError):
        preview_result_from_row(row)
