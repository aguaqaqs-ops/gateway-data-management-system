"""Cross-capability stream contract and binary frame validation."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Self, cast

from gateway_repository_contracts._stream_codec import (
    StreamFrameDecoder,
    decode_frame_wire_bytes,
    encode_frame_wire_bytes,
    encode_stream_bytes,
    encode_stream_frames,
)
from gateway_repository_contracts._stream_metadata import (
    CurrentStreamHeaderMetadata,
    EmptyFrameMetadata,
    StreamCheckpointMetadata,
    StreamEndMetadata,
    StreamErrorMetadata,
    StreamFrameMetadata,
    StreamHeaderMetadata,
    VersionedStreamHeaderMetadata,
    validate_table_name,
)
from gateway_repository_contracts.enums import (
    STREAM_FRAME_FAMILIES,
    StreamFrameFamily,
)
from gateway_repository_contracts.errors import RepositoryContractError, RepositoryContractErrorCode

STREAM_FRAME_VERSION = 1
STREAM_BATCH_MAX_BYTES = 67_108_864

_TERMINAL_FAMILIES = frozenset({StreamFrameFamily.STREAM_END, StreamFrameFamily.STREAM_ERROR})
_DATA_FAMILIES = frozenset({StreamFrameFamily.ARROW_BATCH, StreamFrameFamily.CHECKPOINT})

__all__ = [
    "STREAM_BATCH_MAX_BYTES",
    "STREAM_FRAME_VERSION",
    "CurrentStreamHeaderMetadata",
    "EmptyFrameMetadata",
    "StreamCheckpointMetadata",
    "StreamDecoderFinish",
    "StreamEndMetadata",
    "StreamEnvelope",
    "StreamErrorMetadata",
    "StreamFrame",
    "StreamFrameDecoder",
    "StreamFrameFamily",
    "StreamHeaderMetadata",
    "VersionedStreamHeaderMetadata",
    "compute_frames_raw_sha256",
    "decode_stream",
    "encode_stream",
    "encode_stream_frames",
    "validate_stream_integrity",
    "validate_stream_sequence",
    "validate_stream_sequence_families",
    "validate_table_name",
]


def _metadata_for_family(frame_family: StreamFrameFamily) -> type[StreamFrameMetadata]:
    if frame_family is StreamFrameFamily.STREAM_HEADER:
        return StreamHeaderMetadata  # type: ignore[return-value]
    if frame_family is StreamFrameFamily.ARROW_BATCH:
        return EmptyFrameMetadata
    if frame_family is StreamFrameFamily.CHECKPOINT:
        return StreamCheckpointMetadata
    if frame_family is StreamFrameFamily.STREAM_END:
        return StreamEndMetadata
    if frame_family is StreamFrameFamily.STREAM_ERROR:
        return StreamErrorMetadata
    raise RepositoryContractError(
        RepositoryContractErrorCode.STREAM_UNKNOWN_FRAME,
        "unknown frame family",
    )


def _validate_frame_metadata(
    frame_family: StreamFrameFamily,
    metadata: StreamFrameMetadata,
) -> None:
    if frame_family is StreamFrameFamily.STREAM_HEADER:
        if not isinstance(metadata, (VersionedStreamHeaderMetadata, CurrentStreamHeaderMetadata)):
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_INVALID_VALUE,
                "metadata shape mismatch for frame family",
            )
        return
    expected = _metadata_for_family(frame_family)
    if type(metadata) is not expected:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            "metadata shape mismatch for frame family",
        )


def _require_immutable_bytes(value: object, *, label: str) -> bytes:
    if type(value) is not bytes:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            f"{label} must be immutable bytes",
        )
    return bytes(value)


def _validate_frame_payload(frame_family: StreamFrameFamily, payload: bytes | None) -> None:
    if frame_family is StreamFrameFamily.ARROW_BATCH:
        if payload is None:
            raise RepositoryContractError(
                RepositoryContractErrorCode.STREAM_INVALID_PAYLOAD,
                "ARROW_BATCH payload must be non-empty bytes",
            )
        immutable = _require_immutable_bytes(payload, label="ARROW_BATCH payload")
        if len(immutable) == 0:
            raise RepositoryContractError(
                RepositoryContractErrorCode.STREAM_INVALID_PAYLOAD,
                "ARROW_BATCH payload must be non-empty bytes",
            )
        if len(immutable) > STREAM_BATCH_MAX_BYTES:
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_PAYLOAD_TOO_LARGE,
                "ARROW_BATCH payload exceeds maximum size",
            )
        return
    if payload is not None:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_INVALID_PAYLOAD,
            "payload only allowed for ARROW_BATCH",
        )


def _freeze_frames(frames: Sequence[StreamFrame]) -> tuple[StreamFrame, ...]:
    frozen = tuple(frames)
    for frame in frozen:
        if type(frame) is not StreamFrame:
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_INVALID_VALUE,
                "frames must contain StreamFrame instances",
            )
    return frozen


def compute_frames_raw_sha256(frames: Sequence[StreamFrame]) -> str:
    """Compute integrity digest over canonical encoded wire bytes of all non-terminal frames."""
    if not frames:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_INCOMPLETE,
            "stream missing frames",
        )
    terminal = frames[-1].frame_family
    if terminal not in _TERMINAL_FAMILIES:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_INCOMPLETE,
            "stream missing terminal frame",
        )
    hasher = hashlib.sha256()
    for frame in frames[:-1]:
        hasher.update(encode_frame_wire_bytes(frame))
    return hasher.hexdigest()


@dataclass(frozen=True, slots=True)
class StreamFrame:
    frame_family: StreamFrameFamily
    frame_version: int
    metadata: StreamFrameMetadata
    payload: bytes | None = None

    def __post_init__(self) -> None:
        if self.frame_version != STREAM_FRAME_VERSION:
            raise RepositoryContractError(
                RepositoryContractErrorCode.STREAM_VERSION_MISMATCH,
                "frame_version mismatch",
            )
        _validate_frame_metadata(self.frame_family, self.metadata)
        if self.payload is not None:
            object.__setattr__(
                self,
                "payload",
                _require_immutable_bytes(self.payload, label="ARROW_BATCH payload"),
            )
        _validate_frame_payload(self.frame_family, self.payload)

    def to_wire_bytes(self) -> bytes:
        return encode_frame_wire_bytes(self)

    @classmethod
    def from_wire_bytes(cls, payload: bytes, *, offset: int = 0) -> tuple[Self, int]:
        frame, next_offset = decode_frame_wire_bytes(payload, offset=offset)
        return cast(Self, frame), next_offset


@dataclass(frozen=True, slots=True)
class StreamDecoderFinish:
    """Completion receipt after incremental stream decode lifecycle and integrity checks."""

    terminal_family: StreamFrameFamily
    stream_end: StreamEndMetadata | None = None
    stream_error: StreamErrorMetadata | None = None

    def __post_init__(self) -> None:
        if self.terminal_family is StreamFrameFamily.STREAM_END:
            if not isinstance(self.stream_end, StreamEndMetadata) or self.stream_error is not None:
                raise RepositoryContractError(
                    RepositoryContractErrorCode.WIRE_INVALID_VALUE,
                    "STREAM_END receipt requires stream_end metadata only",
                )
            return
        if self.terminal_family is StreamFrameFamily.STREAM_ERROR:
            if (
                not isinstance(self.stream_error, StreamErrorMetadata)
                or self.stream_end is not None
            ):
                raise RepositoryContractError(
                    RepositoryContractErrorCode.WIRE_INVALID_VALUE,
                    "STREAM_ERROR receipt requires stream_error metadata only",
                )
            return
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            "terminal_family must be STREAM_END or STREAM_ERROR",
        )


@dataclass
class _StreamSequenceState:
    header_seen: bool = False
    terminal_seen: bool = False
    terminal_count: int = 0
    frame_index: int = 0
    terminal_family: StreamFrameFamily | None = None


def accept_stream_frame_family(state: _StreamSequenceState, family: StreamFrameFamily) -> None:
    """Incrementally validate one frame family; raise on lifecycle violation."""
    if family not in STREAM_FRAME_FAMILIES:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_UNKNOWN_FRAME,
            "unknown frame family",
        )
    if state.terminal_seen:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_FRAME_AFTER_TERMINAL,
            "frame after terminal",
        )
    if family is StreamFrameFamily.STREAM_HEADER:
        if state.header_seen:
            raise RepositoryContractError(
                RepositoryContractErrorCode.STREAM_DUPLICATE_HEADER,
                "STREAM_HEADER must appear exactly once",
            )
        state.header_seen = True
    elif family in _TERMINAL_FAMILIES:
        if state.frame_index == 0:
            raise RepositoryContractError(
                RepositoryContractErrorCode.STREAM_INVALID_SEQUENCE,
                "terminal cannot be first frame",
            )
        state.terminal_seen = True
        state.terminal_count += 1
        state.terminal_family = family
    elif family in _DATA_FAMILIES and state.frame_index == 0:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_INVALID_SEQUENCE,
            "data frame before header",
        )
    state.frame_index += 1


def validate_stream_sequence_state_complete(state: _StreamSequenceState) -> StreamFrameFamily:
    """Validate incremental sequence state is complete at stream end."""
    if not state.header_seen:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_INCOMPLETE,
            "stream missing header",
        )
    if not state.terminal_seen or state.terminal_family is None:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_INCOMPLETE,
            "stream missing terminal frame",
        )
    if state.terminal_count > 1:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_TERMINAL_CONFLICT,
            "multiple terminal frames",
        )
    return state.terminal_family


@dataclass(frozen=True, slots=True)
class StreamEnvelope:
    frames: tuple[StreamFrame, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "frames", _freeze_frames(self.frames))
        validate_stream_sequence(self.frames)
        validate_stream_integrity(self.frames)

    def to_wire_bytes(self) -> bytes:
        return encode_stream_bytes(self.frames)

    @classmethod
    def from_wire_bytes(cls, payload: bytes) -> Self:
        return cast(Self, decode_stream(payload))


def encode_stream(frames: Sequence[StreamFrame]) -> bytes:
    """Encode a validated stream to binary wire bytes."""
    frozen = _freeze_frames(frames)
    StreamEnvelope(frames=frozen)
    out = bytearray()
    for chunk in encode_stream_frames(frozen):
        out.extend(chunk)
    return bytes(out)


def decode_stream(payload: bytes) -> StreamEnvelope:
    """Decode binary wire bytes into a validated stream envelope."""
    decoder = StreamFrameDecoder()
    frames = list(decoder.feed(payload))
    decoder.finish()
    return StreamEnvelope(frames=tuple(frames))


def validate_stream_sequence_families(families: Sequence[StreamFrameFamily]) -> None:
    """Validate stream frame lifecycle rules from frame family sequence."""
    if not families:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_INCOMPLETE,
            "stream missing header",
        )
    if families[0] is not StreamFrameFamily.STREAM_HEADER:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_INVALID_SEQUENCE,
            "first frame must be STREAM_HEADER",
        )
    state = _StreamSequenceState()
    for family in families:
        accept_stream_frame_family(state, family)
    validate_stream_sequence_state_complete(state)


def validate_stream_sequence(frames: Sequence[StreamFrame]) -> None:
    """Validate stream frame lifecycle rules at contract level."""
    validate_stream_sequence_families([frame.frame_family for frame in frames])


def validate_stream_integrity(frames: Sequence[StreamFrame]) -> None:
    """Validate STREAM_END digest and row count metadata."""
    if not frames:
        return
    terminal = frames[-1]
    if terminal.frame_family is not StreamFrameFamily.STREAM_END:
        return
    if not isinstance(terminal.metadata, StreamEndMetadata):
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            "STREAM_END metadata invalid",
        )
    expected = compute_frames_raw_sha256(frames)
    if terminal.metadata.frames_raw_sha256 != expected:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_INTEGRITY_MISMATCH,
            "frames_raw_sha256 mismatch",
        )
