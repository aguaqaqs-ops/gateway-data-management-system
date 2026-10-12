"""Shared helpers for history compare checkpoint tampering in HTTP tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import cast

from gateway_backend.application.checkpoints import (
    StepCheckpointEnvelope,
    load_checkpoint_envelope,
    load_checkpoint_state_artifact,
    put_checkpoint_envelope,
    put_checkpoint_state_artifact,
)
from gateway_backend.application.history.compare_jobs import (
    HISTORY_COMPARE_ASSEMBLE_STATE_CONTRACT_VERSION,
    HISTORY_COMPARE_ASSEMBLE_STATE_DOCUMENT_TYPE,
)
from gateway_backend.artifacts import (
    ArtifactRef,
    ArtifactStorePort,
    artifact_ref_from_dict,
    artifact_ref_to_dict,
)
from gateway_shared_kernel.jcs import canonicalize_json_value


def rebind_tampered_assemble_checkpoint(
    artifact_store: ArtifactStorePort,
    ref: ArtifactRef,
    *,
    db_path: Path,
    step_id: str,
    field: str,
    value: object,
) -> ArtifactRef:
    """Tamper the assemble state artifact and update its authenticated checkpoint ref."""

    envelope = load_checkpoint_envelope(artifact_store, ref)
    job_state = dict(envelope.job_state)
    state_ref = artifact_ref_from_dict(cast(dict[str, object], job_state["assemble_state_ref"]))
    state_document = load_checkpoint_state_artifact(
        artifact_store,
        state_ref,
        document_type=HISTORY_COMPARE_ASSEMBLE_STATE_DOCUMENT_TYPE,
        contract_version=HISTORY_COMPARE_ASSEMBLE_STATE_CONTRACT_VERSION,
    )
    assemble_state = dict(cast(dict[str, object], state_document["assemble_state"]))
    if field == "bundle_digest":
        assemble_state["bundle_digest"] = value
    else:
        pairs = list(cast(list[object], assemble_state["pairs"]))
        pair0 = dict(cast(dict[str, object], pairs[0]))
        pair0[field] = value
        pairs[0] = pair0
        assemble_state["pairs"] = pairs
    state_document["assemble_state"] = assemble_state
    new_state_ref = put_checkpoint_state_artifact(
        artifact_store,
        state_document,
        artifact_id_prefix="history-compare-assemble-state-tampered",
    )
    job_state["assemble_state_ref"] = artifact_ref_to_dict(new_state_ref)
    tampered = StepCheckpointEnvelope(
        job_kind=envelope.job_kind,
        step_name=envelope.step_name,
        operation_id=envelope.operation_id,
        job_contract_version=envelope.job_contract_version,
        checkpoint_generation=envelope.checkpoint_generation,
        prior_output_refs=envelope.prior_output_refs,
        job_state=job_state,
    )
    new_ref = put_checkpoint_envelope(artifact_store, tampered)
    checkpoint_blob = canonicalize_json_value(artifact_ref_to_dict(new_ref))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE step_records SET checkpoint_ref = ? WHERE step_id = ?",
            (checkpoint_blob, step_id),
        )
        conn.commit()
    return new_ref
