"""Bind real Preview assembly output to its immutable review closure for both modes."""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from gateway_backend.application.submission.review_result import load_preview_review_closure
from gateway_backend.artifacts.bounded_store import BoundedArtifactStorePort
from gateway_backend.artifacts.bundle_download import BundleIntegrityError
from gateway_backend.domain.workspace.models import InputCompleteness
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
import tests.support.preview_job_harness as preview_harness
from tests.support.preview_job_harness import build_preview_harness
from tests.test_preview_job_assemble import (
    _run_through_publish, _HarnessArtifactRefLookup, _HarnessBoundedArtifactStore,
)

pytestmark = [pytest.mark.unit, pytest.mark.integration]


@pytest.mark.parametrize("mode", (InputCompleteness.FULL, InputCompleteness.MODIFIED_ONLY))
def test_real_preview_review_pairs_match_final_bundle_and_ready(
    mode: InputCompleteness, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("BASELINE_SQL", "INITIAL_SQL", "MODIFIED_SQL"):
        monkeypatch.setattr(preview_harness, name, getattr(preview_harness, name)
            + "CREATE TABLE empty_review(id BIGINT PRIMARY KEY);\n")
    harness = build_preview_harness(tmp_path, input_completeness=mode)
    _run_through_publish(harness, "op-bound-review")
    with ControlDbUnitOfWork(harness.db_path, read_only=True) as uow:
        workspace = uow.workspace.get_workspace(harness.upload_revision.workspace_id)
        assert workspace is not None and workspace.current_preview_result_id is not None
        preview = uow.workspace.get_preview_result(workspace.current_preview_result_id)
        assert preview is not None
    lookup = _HarnessArtifactRefLookup(harness.artifact_store)
    store = cast(BoundedArtifactStorePort, _HarnessBoundedArtifactStore(harness.artifact_store))
    refs = load_preview_review_closure(preview, lookup=lookup, store=store)
    expected = ("baseline_to_initial", "initial_to_modified") if mode is InputCompleteness.FULL else ("initial_to_modified",)
    assert tuple(pair.pair_id for pair in preview.comparison_pairs) == expected
    assert preview.bundle_artifact_id in {ref.artifact_id for ref in refs}
    # The exact navigation document in the immutable review closure is the same
    # producer output used by Preview; no review-side emptiness reconstruction.
    documents = []
    for ref in refs:
        if ref.media_type != "application/json":
            continue
        raw = json.loads(harness.artifact_store.locate(ref))
        if isinstance(raw, dict) and raw.get("contract_version") == "backend-vnext/business-navigation/v5":
            documents.append(raw)
    assert len(documents) >= len(expected)
    for document in documents:
        items = [item for group in document["groups"] for item in group["items"]
                 if any(tab["table_id"] == "empty_review" for tab in item["tabs"])]
        assert len(items) == 1
        assert items[0]["tabs"][0]["empty"] is True
        assert items[0]["summary"] == {"change_kinds": [], "risk_level": None, "nonempty_tab_count": 0, "change_complete": True, "risk_complete": True}
    changed = preview.comparison_pairs[-1].model_copy(update={"comparison_digest": "sha256:" + "0" * 64})
    bad = replace(preview, comparison_pairs=(*preview.comparison_pairs[:-1], changed))
    with pytest.raises(BundleIntegrityError, match="binding"):
        load_preview_review_closure(bad, lookup=lookup, store=store)
