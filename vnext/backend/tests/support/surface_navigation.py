"""Minimal valid navigation artifact for Surface/Bundle unit test scaffolding."""
from __future__ import annotations

from typing import TypeVar
from gateway_shared_kernel import raw_blob_digest
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_backend.artifacts import ArtifactRef, ArtifactStorePort
from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id
from gateway_backend.capabilities.business_navigation.contracts import GROUPS, CONTRACT_VERSION
from gateway_backend.capabilities.surface_assembly.contracts import SurfaceProjectionRef

NAVIGATION_BYTES = canonicalize_json_value({"contract_version": CONTRACT_VERSION,
    "groups": [{"group_key": key, "label": label, "items": []} for key, label in GROUPS],
    "replacement_sides": None})
NAVIGATION_REF = ArtifactRef(build_artifact_id(ArtifactLocation.COMPARISON, "test-navigation", "unit-scaffold"),
    "application/json", len(NAVIGATION_BYTES), raw_blob_digest(NAVIGATION_BYTES))
NAVIGATION_PROJECTION = SurfaceProjectionRef("business_navigation", "BUSINESS_NAVIGATION",
    NAVIGATION_REF, NAVIGATION_REF.raw_sha256)
_Store = TypeVar("_Store", bound=ArtifactStorePort)


def seed_navigation(store: _Store) -> _Store:
    store.put(NAVIGATION_BYTES, NAVIGATION_REF)
    return store
