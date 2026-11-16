"""Preview canonical binding and artifact fixtures shared across backend tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from tests.support.configuration_facts import make_configuration_facts
from functools import lru_cache

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore, artifact_ref_to_dict
from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
from gateway_backend.capabilities.snapshot_materialization.contracts import MaterializationPolicy
from gateway_backend.capabilities.storage_projection import (
    CANONICALIZATION_MANIFEST_MEDIA_TYPE,
    durable_manifest_bytes,
    project_canonical_arrow_table_set,
)
from gateway_backend.capabilities.table_rules import migrated_table_ruleset_snapshot
from gateway_backend.domain.workspace.models import (
    PreviewArtifactRef,
    PreviewCanonicalBindings, PreviewResult, UploadRevision,
)
from gateway_backend.infrastructure.control_db.database import ControlDbUnitOfWork
from tests.support.snapshot_materialization import materialize_arrow_sql
from gateway_backend.capabilities.snapshot_materialization import materialize_canonical_snapshot
from gateway_backend.capabilities.table_access.contracts import ParserInvocationContext, NeverCancel


@dataclass(frozen=True, slots=True)
class CanonicalArtifactFixture:
    bindings: PreviewCanonicalBindings
    refs: tuple[ArtifactRef, ...]
    payloads: dict[str, bytes]
    snapshot_table_ref: ArtifactRef
    snapshot_digest: str


@lru_cache(maxsize=1)
def make_canonical_artifact_fixture(repository_id: str = "repo-1") -> CanonicalArtifactFixture:
    snapshot_store = InMemoryArtifactStore()
    materialized = materialize_arrow_sql(
        "CREATE TABLE `net_cfg` (`board` VARCHAR NOT NULL, `link_no` INT NOT NULL, "
        "PRIMARY KEY (`board`, `link_no`)); INSERT INTO `net_cfg` VALUES ('eth0', 1);",
        policy=MaterializationPolicy.READERS_REQUIRED,
        artifact_store=snapshot_store,
    )
    if materialized.table_set is None or len(materialized.table_set.tables) != 1:
        raise AssertionError("canonical fixture SQL must materialize one table")
    projected = project_canonical_arrow_table_set(materialized.table_set, migrated_table_ruleset_snapshot(), presentation=materialized.presentation)
    assert materialized.snapshot is not None
    canonical = materialize_canonical_snapshot(materialized.snapshot, projected.tables, artifact_store=snapshot_store,
        context=ParserInvocationContext(NeverCancel()), repository_id=repository_id)
    assert canonical.table_set is not None
    table = canonical.table_set.tables[0]
    if table.artifact is None:
        raise AssertionError("canonical fixture table must have durable artifacts")
    snapshot_table_ref = table.artifact.manifest_ref
    if projected.manifest is None or projected.manifest.manifest_digest is None:
        raise AssertionError("canonical fixture must project a manifest")
    manifest_bytes = durable_manifest_bytes(projected.manifest)
    manifest_ref = ArtifactRef(
        artifact_id=build_artifact_id(ArtifactLocation.DURABLE, "test-fixture", "3fa9d814b79a37769b3c0669ad245741b4dbeb66df53bb2a0bc95aca1b313248"),
        media_type=CANONICALIZATION_MANIFEST_MEDIA_TYPE,
        size_bytes=len(manifest_bytes),
        raw_sha256=raw_blob_digest(manifest_bytes),
    )
    closure_bytes = canonicalize_json_value(
        {
            "contract_version": "backend-vnext/preview/canonical-table-set-closure/v1",
            "tables": [
                {
                    "table_name": table.descriptor.table_name,
                    "manifest_ref": artifact_ref_to_dict(snapshot_table_ref),
                }
            ],
        }
    )
    closure_ref = ArtifactRef(
        artifact_id=build_artifact_id(ArtifactLocation.DURABLE, "test-fixture", "3e05636aa9b041e486150f3ba350caaa9db6578825fc54f4b58f3963e3dcf99e"),
        media_type="application/jcs",
        size_bytes=len(closure_bytes),
        raw_sha256=raw_blob_digest(closure_bytes),
    )
    bindings = PreviewCanonicalBindings(
        rules_semantically_equal=True,
        initial_canonical_state_digest=DigestRef("sha256:" + "4" * 64),
        configuration_facts=make_configuration_facts(repository_id=repository_id, rules_digest=projected.manifest.ruleset_digest.value),
        canonical_table_set_closure_ref=PreviewArtifactRef(
            artifact_id=closure_ref.artifact_id,
            media_type=closure_ref.media_type,
            size_bytes=closure_ref.size_bytes,
            raw_sha256=closure_ref.raw_sha256,
        ),
        canonical_table_set_closure_digest=closure_ref.raw_sha256,
        canonicalization_manifest_ref=PreviewArtifactRef(
            artifact_id=manifest_ref.artifact_id,
            media_type=manifest_ref.media_type,
            size_bytes=manifest_ref.size_bytes,
            raw_sha256=manifest_ref.raw_sha256,
        ),
        canonicalization_manifest_digest=projected.manifest.manifest_digest,
        baseline_canonical_state_digest=DigestRef("sha256:" + "4" * 64),
        modified_canonical_state_digest=DigestRef("sha256:" + "5" * 64),
        storage_projection_ruleset_digest=projected.manifest.ruleset_digest,
    )
    refs = (closure_ref, manifest_ref, snapshot_table_ref, *table.artifact.manifest.row_file_refs)
    payloads = {ref.artifact_id: snapshot_store.locate(ref) for ref in refs[2:]}
    payloads[manifest_ref.artifact_id] = manifest_bytes
    payloads[closure_ref.artifact_id] = closure_bytes
    return CanonicalArtifactFixture(
        bindings=bindings,
        refs=tuple(refs),
        payloads=payloads,
        snapshot_table_ref=snapshot_table_ref,
        snapshot_digest=table.artifact.manifest.snapshot_digest.value,
    )


def make_preview_canonical_bindings(
    repository_id: str = "repo-1", *, generated_source_ids: bool = False,
) -> PreviewCanonicalBindings:
    bindings = make_canonical_artifact_fixture(repository_id).bindings
    if not generated_source_ids:
        return bindings
    facts = bindings.configuration_facts
    return replace(bindings, configuration_facts=replace(
        facts,
        initial=replace(facts.initial, source_artifact_id=build_artifact_id(ArtifactLocation.DURABLE, "test-fixture", "22822f127d0974f80593e94b220507ff6c54df1c3b6fc3bdf591ee44808e26cf")),
        modified=replace(facts.modified, source_artifact_id=build_artifact_id(ArtifactLocation.DURABLE, "test-fixture", "ba818a521fed3b2757a17badbc09fd4393d77f7c1c1887a65a74edb8905fe303")),
    ))


def seed_completed_preview_operation(
    unit_of_work: ControlDbUnitOfWork, preview: PreviewResult, upload_revision: UploadRevision,
) -> None:
    """Persist the same scope and payload bindings required of a completed Preview job."""
    from gateway_backend.application.preview_jobs import PREVIEW_JOB_CONTRACT_VERSION, PREVIEW_JOB_KIND
    from gateway_backend.application.workspace.preview import build_preview_job_payload
    from gateway_backend.operations.contracts import OPERATION_RUNTIME_CONTRACT_VERSION

    payload = build_preview_job_payload(
        workspace_id=preview.workspace_id, upload_revision=upload_revision,
        repository_id=preview.repository_id, business_baseline_node_id=preview.business_baseline_node_id,
        business_baseline_commit_id=preview.business_baseline_commit_id,
        baseline_head_version=preview.baseline_head_version, idempotency_key="preview-key",
        comparison_ruleset_digest="sha256:rules",
    )
    unit_of_work.connection.execute(
        """INSERT INTO operation_records (
            operation_id, contract_version, optimistic_version, job_kind, job_contract_version,
            job_payload, job_payload_ref, business_refs, artifact_refs, repository_operation_id,
            checkpoint_ref, ready_closure_ref, status, diagnostic, cancel_requested,
            created_at_us, updated_at_us, completed_at_us
        ) VALUES (?, ?, 0, ?, ?, ?, NULL, ?, ?, NULL, NULL, NULL, 'SUCCEEDED', NULL, 0, 1, 1, 1)""",
        (preview.operation_id, OPERATION_RUNTIME_CONTRACT_VERSION, PREVIEW_JOB_KIND,
         PREVIEW_JOB_CONTRACT_VERSION, payload, canonicalize_json_value([
             {"kind": "workspace", "value": preview.workspace_id},
             {"kind": "upload_revision", "value": preview.upload_revision_id},
         ]), b"[]"),
    )
