"""Preview canonical binding and artifact fixtures shared across backend tests."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from gateway_shared_kernel import DigestRef, raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value

from gateway_backend.artifacts import ArtifactRef, InMemoryArtifactStore, artifact_ref_to_dict
from gateway_backend.capabilities.snapshot_materialization.contracts import MaterializationPolicy
from gateway_backend.capabilities.storage_projection import (
    CANONICALIZATION_MANIFEST_MEDIA_TYPE,
    durable_manifest_bytes,
    project_canonical_table_set,
)
from gateway_backend.capabilities.table_rules import migrated_table_ruleset_snapshot
from gateway_backend.domain.workspace.models import (
    PreviewArtifactRef,
    PreviewCanonicalBindings,
)
from tests.support.snapshot_materialization import materialize_sql


@dataclass(frozen=True, slots=True)
class CanonicalArtifactFixture:
    bindings: PreviewCanonicalBindings
    refs: tuple[ArtifactRef, ...]
    payloads: dict[str, bytes]
    snapshot_table_ref: ArtifactRef
    snapshot_digest: str


@lru_cache(maxsize=1)
def make_canonical_artifact_fixture() -> CanonicalArtifactFixture:
    snapshot_store = InMemoryArtifactStore()
    materialized = materialize_sql(
        "CREATE TABLE `net_cfg` (`board` VARCHAR NOT NULL, `link_no` INT NOT NULL, "
        "PRIMARY KEY (`board`, `link_no`)); INSERT INTO `net_cfg` VALUES ('eth0', 1);",
        policy=MaterializationPolicy.ARTIFACTS_REQUIRED,
        artifact_store=snapshot_store,
    )
    if materialized.table_set is None or len(materialized.table_set.tables) != 1:
        raise AssertionError("canonical fixture SQL must materialize one table")
    table = materialized.table_set.tables[0]
    if table.artifact is None:
        raise AssertionError("canonical fixture table must have durable artifacts")
    snapshot_table_ref = table.artifact.manifest_ref
    projected = project_canonical_table_set(
        materialized.table_set,
        migrated_table_ruleset_snapshot(),
    )
    if projected.manifest is None or projected.manifest.manifest_digest is None:
        raise AssertionError("canonical fixture must project a manifest")
    manifest_bytes = durable_manifest_bytes(projected.manifest)
    manifest_ref = ArtifactRef(
        artifact_id="preview-canonical-manifest-fixture",
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
        artifact_id="preview-canonical-closure-fixture",
        media_type="application/jcs",
        size_bytes=len(closure_bytes),
        raw_sha256=raw_blob_digest(closure_bytes),
    )
    bindings = PreviewCanonicalBindings(
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


def make_preview_canonical_bindings() -> PreviewCanonicalBindings:
    return make_canonical_artifact_fixture().bindings
