"""Shared helpers for history compare checkpoint tampering in HTTP tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import cast

from gateway_backend.application.checkpoints import StepCheckpointEnvelope, load_checkpoint_envelope
from gateway_backend.artifacts import (
    ArtifactRef,
    ArtifactStorePort,
    InMemoryArtifactStore,
    artifact_ref_to_dict,
)
from gateway_shared_kernel import raw_blob_digest
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
    """Tamper assemble checkpoint bytes, re-sign the ref, and update step_records."""

    envelope = load_checkpoint_envelope(artifact_store, ref)
    job_state = dict(envelope.job_state)
    assemble_state = dict(cast(dict[str, object], job_state["assemble_state"]))
    if field == "bundle_digest":
        assemble_state["bundle_digest"] = value
    else:
        pairs = list(cast(list[object], assemble_state["pairs"]))
        pair0 = dict(cast(dict[str, object], pairs[0]))
        pair0[field] = value
        pairs[0] = pair0
        assemble_state["pairs"] = pairs
    job_state["assemble_state"] = assemble_state
    tampered = StepCheckpointEnvelope(
        job_kind=envelope.job_kind,
        step_name=envelope.step_name,
        operation_id=envelope.operation_id,
        job_contract_version=envelope.job_contract_version,
        checkpoint_generation=envelope.checkpoint_generation,
        prior_output_refs=envelope.prior_output_refs,
        job_state=job_state,
    )
    tampered_bytes = tampered.to_canonical_bytes()
    new_ref = ArtifactRef(
        artifact_id=ref.artifact_id,
        media_type=ref.media_type,
        size_bytes=len(tampered_bytes),
        raw_sha256=raw_blob_digest(tampered_bytes),
    )
    memory_store = cast(InMemoryArtifactStore, artifact_store)
    memory_store._artifacts[ref.artifact_id] = (new_ref, tampered_bytes)  # noqa: SLF001
    checkpoint_blob = canonicalize_json_value(artifact_ref_to_dict(new_ref))
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE step_records SET checkpoint_ref = ? WHERE step_id = ?",
            (checkpoint_blob, step_id),
        )
        conn.commit()
    return new_ref
