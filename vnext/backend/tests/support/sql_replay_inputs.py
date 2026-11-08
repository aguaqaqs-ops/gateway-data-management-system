"""Structured inputs from independently hand-counted SQL replay vectors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from gateway_shared_kernel import raw_blob_digest

from gateway_backend.capabilities.mutation_planning.contracts import (
    CanonicalStorageKey, ChangeSetClosure, ChangeSetMutation, PersistedRowImage,
    RowMutationOperation,
)
from tests.support.mutation_contracts import change_set_closure


_REPLAY_CAP = Path(__file__).parents[3] / "fixtures/vectors/mutation/sql-replay/v1/replay-cap.json"


def frozen_replay_cap_closure(case_index: int) -> ChangeSetClosure:
    vector: dict[str, Any] = json.loads(_REPLAY_CAP.read_text())
    spec = vector["input"]
    case = vector["cases"][case_index]
    key = spec["key_fill"] * spec["key_text_bytes"]
    key_cell: dict[str, object] = {"kind": "string", "text": key}
    values: tuple[tuple[str, dict[str, object]], ...] = tuple(
        (f"v{index:03d}", {"kind": "string", "text":
                           spec["ordinary_value_text"]
                           + (spec["padding_fill"] * case["last_value_padding_bytes"]
                              if index == spec["non_key_column_count"] - 1 else "")})
        for index in range(spec["non_key_column_count"])
    )
    mutation = ChangeSetMutation(
        canonical_table=spec["canonical_table"], operation=RowMutationOperation.UPDATE,
        canonical_storage_key=CanonicalStorageKey(((spec["canonical_key_column"], key_cell),)),
        before_row_digest=raw_blob_digest(b"before"),
        after_image=PersistedRowImage(((spec["canonical_key_column"], key_cell),) + values),
    )
    return change_set_closure(mutations=(mutation,))
