"""Comparison-owned manifests over the derived computation-cache reference port."""
from __future__ import annotations

from gateway_backend.artifacts.location import ArtifactLocation, build_artifact_id

import base64
import binascii
from contextlib import ExitStack
from typing import Any

import pyarrow as pa
from gateway_shared_kernel import DigestRef, raw_blob_digest

from gateway_backend.artifacts.computation_cache import (
    ComputationCacheEntry, ComputationCacheKey, ComputationCacheKind,
    ComputationCacheLease, InvalidComputationCachePayload, encode_cache_manifest,
)
from gateway_backend.artifacts.types import ArtifactRef
from gateway_backend.capabilities.comparison.cache_codec import (
    ComparisonCachePayload, ComparisonCacheView, MAX_CACHE_MANIFEST_BYTES,
    MAX_CACHE_ROWS, MAX_CACHE_VIEW_BYTES,
)
from gateway_backend.capabilities.comparison.task_input import TABLE_CACHE_FORMAT, TableTaskIdentity
from gateway_backend.capabilities.snapshot_materialization import KernelExecutionContext


def _ref(raw: bytes, media_type: str) -> ArtifactRef:
    digest = raw_blob_digest(raw)
    return ArtifactRef(build_artifact_id(ArtifactLocation.COMPARISON, "computation-cache", [media_type, digest.value, len(raw)]), media_type, len(raw), digest)


def encode_persistent_comparison(
    payload: ComparisonCachePayload,
) -> tuple[ComputationCacheEntry, tuple[tuple[ArtifactRef, bytes], ...]]:
    """Keep empty schemas in the manifest without publishing empty IPC files."""
    key = ComputationCacheKey(payload.repository_id, ComputationCacheKind.COMPARISON, payload.task_digest)
    members: list[tuple[ArtifactRef, bytes]] = []
    views: list[dict[str, object]] = []
    for view in payload.views:
        member = None
        if view.raw:
            ref = _ref(view.raw, "application/vnd.apache.arrow.stream")
            members.append((ref, view.raw))
            member = len(members) - 1
        views.append({"name": view.name,
            "schema": base64.b64encode(view.schema.serialize().to_pybytes()).decode("ascii"),
            "batch_rows": list(view.batch_rows), "member": member,
            "raw_digest": view.raw_digest.value})
    document: dict[str, object] = {
        "artifact_scope": payload.artifact_scope, "task_kind": payload.task_kind,
        "detail_policy": payload.detail_policy, "complete": payload.complete,
        "table_fact_jcs": payload.table_fact_jcs.decode("utf-8"),
        "native_metadata_json": payload.native_metadata_json,
        "families": list(payload.families), "views": views,
    }
    refs = tuple(ref for ref, _ in members)
    raw = encode_cache_manifest(key, format=TABLE_CACHE_FORMAT, member_refs=refs, payload=document)
    manifest = _ref(raw, "application/json")
    return ComputationCacheEntry(key, TABLE_CACHE_FORMAT, manifest, refs), ((manifest, raw), *members)


def decode_persistent_comparison(
    lease: ComputationCacheLease, identity: TableTaskIdentity, context: KernelExecutionContext,
) -> ComparisonCachePayload:
    """Admit owned IPC bytes before copying borrowed buffers from the cache lease."""
    charges = ExitStack()
    try:
        value: dict[str, Any] = lease.payload
        if (lease.entry.format != TABLE_CACHE_FORMAT
                or set(value) != {"artifact_scope", "task_kind", "detail_policy", "complete",
                    "table_fact_jcs", "native_metadata_json", "families", "views"}
                or value["artifact_scope"] != identity.artifact_scope
                or value["task_kind"] != identity.task_input.kind
                or value["detail_policy"] != identity.task_input.detail_policy.value
                or value["complete"] is not True
                or type(value["table_fact_jcs"]) is not str
                or (value["native_metadata_json"] is not None and type(value["native_metadata_json"]) is not str)
                or type(value["families"]) is not list or type(value["views"]) is not list
                or len(value["views"]) > 7):
            raise ValueError("comparison cache manifest shape mismatch")
        total = sum(ref.size_bytes for ref in lease.entry.member_refs)
        if any(ref.size_bytes > MAX_CACHE_VIEW_BYTES for ref in lease.entry.member_refs):
            raise ValueError("comparison cache view exceeds bound")
        charges.enter_context(context.memory.reserve(4 * MAX_CACHE_MANIFEST_BYTES + total * 2))
        views: list[ComparisonCacheView] = []
        consumed: list[int] = []
        for item in value["views"]:
            context.checkpoint()
            if (type(item) is not dict or set(item) != {"name", "schema", "batch_rows", "member", "raw_digest"}
                    or type(item["name"]) is not str or type(item["schema"]) is not str
                    or type(item["batch_rows"]) is not list
                    or any(type(count) is not int or count < 1 or count > 1024 for count in item["batch_rows"])
                    or sum(item["batch_rows"]) > MAX_CACHE_ROWS
                    or len(item["batch_rows"]) > MAX_CACHE_ROWS):
                raise ValueError("comparison cache view shape mismatch")
            schema = pa.ipc.read_schema(pa.BufferReader(base64.b64decode(item["schema"], validate=True)))
            member = item["member"]
            raw = b""
            if member is not None:
                if type(member) is not int or not 0 <= member < len(lease.entry.member_refs):
                    raise ValueError("comparison cache member index mismatch")
                consumed.append(member)
                ref = lease.entry.member_refs[member]
                if ref.media_type != "application/vnd.apache.arrow.stream":
                    raise ValueError("comparison cache member media type mismatch")
                with lease.open_buffer(ref) as buffer:
                    raw = buffer.to_pybytes()
            if bool(raw) != bool(item["batch_rows"]):
                raise ValueError("comparison cache empty view mismatch")
            views.append(ComparisonCacheView(item["name"], schema, raw,
                DigestRef(item["raw_digest"]), tuple(item["batch_rows"])))
        if consumed != list(range(len(lease.entry.member_refs))):
            raise ValueError("comparison cache members are not exact")
        charges.callback(lease.close)
        return ComparisonCachePayload(identity.repository_id, identity.artifact_scope,
            identity.task_digest, value["task_kind"], value["detail_policy"],
            value["table_fact_jcs"].encode("utf-8"), value["native_metadata_json"],
            tuple(value["families"]), tuple(views), charges=charges)
    except (ValueError, TypeError, KeyError, RecursionError, pa.ArrowException, binascii.Error):
        charges.close()
        raise InvalidComputationCachePayload("invalid comparison-owned cache payload") from None
    except BaseException:
        charges.close()
        raise
