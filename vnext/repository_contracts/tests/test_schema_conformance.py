"""Python metadata output conformance against packaged JSON Schemas."""

from __future__ import annotations

import base64
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from gateway_repository_contracts.enums import (
    EffectClassification,
    FailureCategory,
    RecoveryAction,
)
from gateway_repository_contracts.identities import (
    ArtifactId,
    CommitId,
    CursorToken,
    RefName,
    RepositoryId,
)
from gateway_repository_contracts.problem import (
    PROBLEM_SCHEMA_VERSION,
    FailureDescriptor,
    RepositoryProblemDetails,
)
from gateway_repository_contracts.stream import (
    STREAM_FRAME_VERSION,
    CurrentStreamHeaderMetadata,
    EmptyFrameMetadata,
    StreamCheckpointMetadata,
    StreamEndMetadata,
    StreamEnvelope,
    StreamFrame,
    StreamFrameFamily,
    VersionedStreamHeaderMetadata,
    encode_stream,
)
from gateway_repository_contracts.wire import load_schema_resource

VALID_UUID_V7 = "01234567-89ab-7cde-8f01-23456789abcd"
_INCARNATION = "incarnation-1"
_SCHEMA_DIGEST = "a" * 64
_QUERY_DIGEST = "b" * 64


def _schema_registry() -> Registry:
    metadata = load_schema_resource("stream-metadata-v1.schema.json")
    envelope = load_schema_resource("stream-envelope-v1.schema.json")
    registry: Registry = Registry()
    registry = registry.with_resource(
        metadata["$id"],
        Resource.from_contents(metadata, default_specification=DRAFT202012),
    )
    return cast(
        Registry,
        registry.with_resource(
            envelope["$id"],
            Resource.from_contents(envelope, default_specification=DRAFT202012),
        ),
    )


def _metadata_validator() -> Draft202012Validator:
    schema = load_schema_resource("stream-metadata-v1.schema.json")
    return Draft202012Validator(schema, registry=_schema_registry())


def _envelope_validator() -> Draft202012Validator:
    schema = load_schema_resource("stream-envelope-v1.schema.json")
    return Draft202012Validator(schema, registry=_schema_registry())


def _validate_stream_metadata(def_name: str, instance: object) -> None:
    schema = load_schema_resource("stream-metadata-v1.schema.json")
    Draft202012Validator(
        {"$ref": f"{schema['$id']}#/$defs/{def_name}"},
        registry=_schema_registry(),
    ).validate(instance)


def _frame_document(frame: StreamFrame) -> dict[str, object]:
    document: dict[str, object] = {
        "frame_version": frame.frame_version,
        "frame_family": frame.frame_family.value,
        "metadata": frame.metadata.to_wire_dict(),
    }
    if frame.payload is not None:
        document["payload_base64url"] = (
            base64.urlsafe_b64encode(frame.payload).decode("ascii").rstrip("=")
        )
    return document


def _envelope_document(frames: tuple[StreamFrame, ...]) -> dict[str, object]:
    return {
        "envelope_version": 1,
        "frames": [_frame_document(frame) for frame in frames],
    }


def _identity_leaf_schema(schema: dict[str, Any], def_name: str) -> dict[str, Any]:
    defs = cast(dict[str, Any], schema["$defs"])
    ref = defs[def_name]
    if isinstance(ref, dict) and "$ref" in ref:
        ref_path = str(ref["$ref"]).rsplit("/", maxsplit=1)[-1]
        return cast(dict[str, Any], defs[ref_path])
    return cast(dict[str, Any], ref)


def _validate_identity_wire(def_name: str, wire: str) -> None:
    schema = load_schema_resource("identities-v1.schema.json")
    Draft202012Validator(_identity_leaf_schema(schema, def_name)).validate(wire)


def _problem_validator() -> Draft202012Validator:
    return Draft202012Validator(load_schema_resource("problem-v1.schema.json"))


def _header_frame() -> StreamFrame:
    return StreamFrame(
        frame_family=StreamFrameFamily.STREAM_HEADER,
        frame_version=STREAM_FRAME_VERSION,
        metadata=VersionedStreamHeaderMetadata(
            repository_id=VALID_UUID_V7,
            repository_incarnation_id=_INCARNATION,
            table_name="main/release-1",
            declared_schema_digest=_SCHEMA_DIGEST,
            query_options_digest=_QUERY_DIGEST,
            snapshot_commit_id="commit-1",
        ),
    )


def _batch_frame() -> StreamFrame:
    return StreamFrame(
        frame_family=StreamFrameFamily.ARROW_BATCH,
        frame_version=STREAM_FRAME_VERSION,
        metadata=EmptyFrameMetadata(),
        payload=b"\x00\x01arrow",
    )


def _end_frame(prefix: tuple[StreamFrame, ...], *, row_count: int = 1) -> StreamFrame:
    import hashlib

    hasher = hashlib.sha256()
    for frame in prefix:
        hasher.update(frame.to_wire_bytes())
    return StreamFrame(
        frame_family=StreamFrameFamily.STREAM_END,
        frame_version=STREAM_FRAME_VERSION,
        metadata=StreamEndMetadata(frames_raw_sha256=hasher.hexdigest(), final_row_count=row_count),
    )


def test_versioned_header_metadata_validates_schema() -> None:
    header = _header_frame()
    meta = header.metadata
    assert isinstance(meta, VersionedStreamHeaderMetadata)
    wire = meta.to_wire_dict()
    _validate_stream_metadata("versionedStreamHeaderMetadata", wire)
    _metadata_validator().validate(wire)


@pytest.mark.parametrize(
    "invalid",
    [None, 42, {}, [], {"unknown": True}, {"cursor_token": "x"}, {"error_code": "E"}],
)
def test_stream_envelope_schema_rejects_invalid_roots(invalid: object) -> None:
    with pytest.raises(ValidationError):
        _envelope_validator().validate(invalid)


def test_stream_envelope_schema_accepts_valid_document() -> None:
    header = _header_frame()
    batch = _batch_frame()
    end = _end_frame((header, batch), row_count=42)
    _envelope_validator().validate(_envelope_document((header, batch, end)))


def test_stream_framing_schema_accepts_snapshot() -> None:
    schema = load_schema_resource("stream-framing-v1.schema.json")
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(
        {
            "framing_version": 1,
            "frame_header_size_bytes": 6,
            "frame_families": {
                "STREAM_HEADER": 1,
                "ARROW_BATCH": 2,
                "CHECKPOINT": 3,
                "STREAM_END": 4,
                "STREAM_ERROR": 5,
            },
            "control_json_max_bytes": 1_048_576,
            "arrow_batch_max_bytes": 67_108_864,
        }
    )


def test_stream_metadata_schema_rejects_empty_object_at_root() -> None:
    with pytest.raises(ValidationError):
        _metadata_validator().validate({})


def test_current_header_metadata_validates_schema() -> None:
    metadata = CurrentStreamHeaderMetadata(
        repository_id=VALID_UUID_V7,
        repository_incarnation_id=_INCARNATION,
        table_name="café",
        declared_schema_digest=_SCHEMA_DIGEST,
        query_options_digest=_QUERY_DIGEST,
        current_table_generation_id="gen-table-1",
    )
    _validate_stream_metadata("currentStreamHeaderMetadata", metadata.to_wire_dict())


def test_stream_end_metadata_validates_schema() -> None:
    header = _header_frame()
    batch = _batch_frame()
    end = _end_frame((header, batch), row_count=42)
    meta = end.metadata
    assert isinstance(meta, StreamEndMetadata)
    _validate_stream_metadata("streamEndMetadata", meta.to_wire_dict())


def test_versioned_header_missing_binding_rejected_by_schema() -> None:
    wire = _header_frame().metadata
    assert isinstance(wire, VersionedStreamHeaderMetadata)
    payload = wire.to_wire_dict()
    payload.pop("snapshot_commit_id", None)
    with pytest.raises(ValidationError):
        _validate_stream_metadata("versionedStreamHeaderMetadata", payload)


def test_cross_binding_rejected_by_schema() -> None:
    wire = {
        "repository_id": VALID_UUID_V7,
        "repository_incarnation_id": _INCARNATION,
        "store_kind": "VERSIONED",
        "table_name": "t",
        "declared_schema_digest": _SCHEMA_DIGEST,
        "query_options_digest": _QUERY_DIGEST,
        "snapshot_commit_id": "commit-1",
        "current_table_generation_id": "gen-1",
    }
    with pytest.raises(ValidationError):
        _validate_stream_metadata("versionedStreamHeaderMetadata", wire)


def test_binary_stream_round_trip() -> None:
    header = _header_frame()
    batch = _batch_frame()
    end = _end_frame((header, batch), row_count=42)
    StreamEnvelope.from_wire_bytes(encode_stream((header, batch, end)))


def test_problem_python_output_validates_schema() -> None:
    failure = FailureDescriptor(
        code="REPOSITORY_NOT_READY",
        category=FailureCategory.INVALID_REQUEST,
        phase="ACCEPT",
        recovery=RecoveryAction.RETRY_COMMAND,
        effect=EffectClassification.NOT_APPLIED,
        message="request rejected",
        details={"reason": "not-ready"},
    )
    problem = RepositoryProblemDetails(
        type="about:blank",
        title="Rejected",
        status=400,
        detail="bad request",
        instance="/v1/repositories/x",
        failure=failure,
        request_id="req-1",
        wire_schema_version=PROBLEM_SCHEMA_VERSION,
    )
    _problem_validator().validate(problem.to_wire_dict())


@pytest.mark.parametrize(
    ("def_name", "wire"),
    [
        ("repositoryId", VALID_UUID_V7),
        ("commitId", "commit-provider-token"),
        ("cursorToken", "cursor-opaque"),
        ("refName", "main/release-1"),
    ],
)
def test_identity_wire_samples_validate_schema(def_name: str, wire: str) -> None:
    _validate_identity_wire(def_name, wire)


@pytest.mark.parametrize(
    ("def_name", "wire"),
    [
        ("refName", "_gateway/internal"),
        ("opaqueToken", "café-generation"),
        ("opaqueToken", "a b"),
        ("opaqueToken", "a\tb"),
        ("opaqueToken", "a" * 1025),
        ("cursorToken", "a b"),
        ("cursorToken", "a\tb"),
        ("cursorToken", "a" * 8193),
    ],
)
def test_identity_schema_rejects_invalid_samples(def_name: str, wire: str) -> None:
    schema = load_schema_resource("identities-v1.schema.json")
    with pytest.raises(ValidationError):
        Draft202012Validator(_identity_leaf_schema(schema, def_name)).validate(wire)


def test_identity_types_round_trip_and_validate_schema() -> None:
    samples = {
        "repositoryId": RepositoryId.from_wire(VALID_UUID_V7).to_wire(),
        "artifactId": ArtifactId.from_wire(VALID_UUID_V7).to_wire(),
        "commitId": CommitId.from_wire("commit-1").to_wire(),
        "cursorToken": CursorToken.from_wire("cursor-opaque").to_wire(),
        "refName": RefName.from_wire("refs/heads/main").to_wire(),
    }
    for def_name, wire in samples.items():
        _validate_identity_wire(def_name, wire)


def test_checkpoint_metadata_validates_schema() -> None:
    metadata = StreamCheckpointMetadata(cursor_token="cursor-opaque")
    _validate_stream_metadata("streamCheckpointMetadata", metadata.to_wire_dict())
