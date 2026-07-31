"""Private binary stream frame codec (v1)."""

from __future__ import annotations

import hashlib
import json
import struct
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from gateway_repository_contracts._jcs import encode_jcs_bytes
from gateway_repository_contracts._json import CONTROL_JSON_MAX_BYTES, parse_json_document
from gateway_repository_contracts.enums import StreamFrameFamily
from gateway_repository_contracts.errors import RepositoryContractError, RepositoryContractErrorCode
from gateway_repository_contracts._stream_metadata import (
    EmptyFrameMetadata,
    StreamCheckpointMetadata,
    StreamEndMetadata,
    StreamErrorMetadata,
    StreamFrameMetadata,
    decode_stream_header_metadata,
)

if TYPE_CHECKING:
    from gateway_repository_contracts.stream import StreamEnvelope, StreamFrame

STREAM_FRAME_HEADER_SIZE = 6
_FRAME_VERSION = 1
_TERMINAL_FAMILIES = frozenset({StreamFrameFamily.STREAM_END, StreamFrameFamily.STREAM_ERROR})

_FAMILY_TO_ID: dict[StreamFrameFamily, int] = {
    StreamFrameFamily.STREAM_HEADER: 1,
    StreamFrameFamily.ARROW_BATCH: 2,
    StreamFrameFamily.CHECKPOINT: 3,
    StreamFrameFamily.STREAM_END: 4,
    StreamFrameFamily.STREAM_ERROR: 5,
}
_ID_TO_FAMILY: dict[int, StreamFrameFamily] = {value: key for key, value in _FAMILY_TO_ID.items()}


def _metadata_to_jcs_bytes(metadata: StreamFrameMetadata) -> bytes:
    return encode_jcs_bytes(metadata.to_wire_dict(), max_bytes=CONTROL_JSON_MAX_BYTES)


def _decode_metadata_jcs(payload: bytes) -> object:
    try:
        return parse_json_document(payload)
    except RepositoryContractError:
        raise
    except json.JSONDecodeError as exc:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_JSON_SYNTAX_INVALID,
            "invalid metadata JSON",
        ) from exc


def _validate_canonical_control_body(body: bytes, metadata: StreamFrameMetadata) -> None:
    canonical = encode_jcs_bytes(metadata.to_wire_dict(), max_bytes=CONTROL_JSON_MAX_BYTES)
    if body != canonical:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_JSON_SYNTAX_INVALID,
            "control frame metadata must be canonical JCS",
        )


def _validate_frame_body_length(frame_family: StreamFrameFamily, body_length: int) -> None:
    from gateway_repository_contracts.stream import STREAM_BATCH_MAX_BYTES

    if frame_family is StreamFrameFamily.ARROW_BATCH:
        if body_length == 0:
            raise RepositoryContractError(
                RepositoryContractErrorCode.STREAM_INVALID_PAYLOAD,
                "ARROW_BATCH payload must be non-empty bytes",
            )
        if body_length > STREAM_BATCH_MAX_BYTES:
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_PAYLOAD_TOO_LARGE,
                "ARROW_BATCH payload exceeds maximum size",
            )
        return
    if body_length > CONTROL_JSON_MAX_BYTES:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_PAYLOAD_TOO_LARGE,
            "control frame payload exceeds maximum size",
        )


def _require_immutable_bytes(value: object, *, label: str) -> bytes:
    if type(value) is not bytes:
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            f"{label} must be immutable bytes",
        )
    return bytes(value)


def _validate_frame_header(
    frame_version: int, family_id: int, body_length: int
) -> StreamFrameFamily:
    from gateway_repository_contracts.stream import STREAM_FRAME_VERSION

    if frame_version != STREAM_FRAME_VERSION:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_VERSION_MISMATCH,
            "frame_version mismatch",
        )
    frame_family = _ID_TO_FAMILY.get(family_id)
    if frame_family is None:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_UNKNOWN_FRAME,
            "unknown frame family id",
        )
    _validate_frame_body_length(frame_family, body_length)
    return frame_family


_WireBuffer = bytes | bytearray | memoryview


def _peek_complete_frame_size(buffer: _WireBuffer, *, offset: int = 0) -> int | None:
    if offset + STREAM_FRAME_HEADER_SIZE > len(buffer):
        return None
    frame_version, family_id, body_length = struct.unpack_from(">BBI", buffer, offset)
    frame_family = _validate_frame_header(frame_version, family_id, body_length)
    del frame_family
    total = STREAM_FRAME_HEADER_SIZE + int(body_length)
    if offset + total > len(buffer):
        return None
    return total


def encode_frame_wire_bytes(frame: StreamFrame) -> bytes:
    from gateway_repository_contracts.stream import (
        STREAM_BATCH_MAX_BYTES,
        STREAM_FRAME_VERSION,
        StreamFrame,
    )

    if not isinstance(frame, StreamFrame):
        raise RepositoryContractError(
            RepositoryContractErrorCode.WIRE_INVALID_VALUE,
            "frame must be StreamFrame",
        )
    family_id = _FAMILY_TO_ID.get(frame.frame_family)
    if family_id is None:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_UNKNOWN_FRAME,
            "unknown frame family",
        )
    if frame.frame_version != STREAM_FRAME_VERSION:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_VERSION_MISMATCH,
            "frame_version mismatch",
        )
    if frame.frame_family is StreamFrameFamily.ARROW_BATCH:
        if frame.payload is None:
            raise RepositoryContractError(
                RepositoryContractErrorCode.STREAM_INVALID_PAYLOAD,
                "ARROW_BATCH payload must be non-empty bytes",
            )
        payload = _require_immutable_bytes(frame.payload, label="ARROW_BATCH payload")
        if len(payload) == 0:
            raise RepositoryContractError(
                RepositoryContractErrorCode.STREAM_INVALID_PAYLOAD,
                "ARROW_BATCH payload must be non-empty bytes",
            )
        if len(payload) > STREAM_BATCH_MAX_BYTES:
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_PAYLOAD_TOO_LARGE,
                "ARROW_BATCH payload exceeds maximum size",
            )
    else:
        payload = _metadata_to_jcs_bytes(frame.metadata)
    header = struct.pack(">BBI", _FRAME_VERSION, family_id, len(payload))
    return header + payload


def _decode_control_metadata(
    frame_family: StreamFrameFamily,
    body: bytes,
) -> StreamFrameMetadata:
    metadata: StreamFrameMetadata
    if frame_family is StreamFrameFamily.STREAM_HEADER:
        metadata = decode_stream_header_metadata(_decode_metadata_jcs(body))
    elif frame_family is StreamFrameFamily.CHECKPOINT:
        metadata = StreamCheckpointMetadata.from_wire_dict(_decode_metadata_jcs(body))
    elif frame_family is StreamFrameFamily.STREAM_END:
        metadata = StreamEndMetadata.from_wire_dict(_decode_metadata_jcs(body))
    elif frame_family is StreamFrameFamily.STREAM_ERROR:
        metadata = StreamErrorMetadata.from_wire_dict(_decode_metadata_jcs(body))
    else:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_UNKNOWN_FRAME,
            "unknown frame family",
        )
    _validate_canonical_control_body(body, metadata)
    return metadata


def decode_frame_wire_bytes(
    payload: _WireBuffer,
    *,
    offset: int = 0,
    raw_wire: bytes | None = None,
) -> tuple[StreamFrame, int]:
    from gateway_repository_contracts.stream import STREAM_FRAME_VERSION, StreamFrame

    if offset + STREAM_FRAME_HEADER_SIZE > len(payload):
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_INVALID_PAYLOAD,
            "truncated frame header",
        )
    frame_version, family_id, body_length = struct.unpack_from(">BBI", payload, offset)
    frame_family = _validate_frame_header(frame_version, family_id, body_length)
    body_start = offset + STREAM_FRAME_HEADER_SIZE
    body_end = body_start + body_length
    if body_end > len(payload):
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_INVALID_PAYLOAD,
            "truncated frame payload",
        )
    body = bytes(payload[body_start:body_end])
    next_offset = body_end
    wire_bytes = raw_wire if raw_wire is not None else bytes(payload[offset:body_end])
    if frame_family is StreamFrameFamily.ARROW_BATCH:
        metadata: StreamFrameMetadata = EmptyFrameMetadata()
        batch_payload = body
    else:
        metadata = _decode_control_metadata(frame_family, body)
        batch_payload = None
    frame = StreamFrame(
        frame_family=frame_family,
        frame_version=STREAM_FRAME_VERSION,
        metadata=metadata,
        payload=batch_payload,
        wire_bytes=wire_bytes,
    )
    return frame, next_offset


def _frame_for_envelope_storage(frame: StreamFrame) -> StreamFrame:
    from gateway_repository_contracts.stream import STREAM_FRAME_VERSION, StreamFrame

    if frame.frame_family is StreamFrameFamily.ARROW_BATCH:
        return StreamFrame(
            frame_family=frame.frame_family,
            frame_version=STREAM_FRAME_VERSION,
            metadata=EmptyFrameMetadata(),
            payload=b"\x00",
            wire_bytes=frame.wire_bytes,
        )
    return frame


def _try_decode_frame_at(buffer: bytearray, offset: int) -> tuple[int, StreamFrame] | None:
    if offset >= len(buffer):
        return None
    buffer_view = memoryview(buffer)
    frame_size = _peek_complete_frame_size(buffer_view, offset=offset)
    if frame_size is None:
        return None
    raw_frame = bytes(buffer_view[offset : offset + frame_size])
    frame, _ = decode_frame_wire_bytes(
        buffer_view,
        offset=offset,
        raw_wire=raw_frame,
    )
    return frame_size, frame


@dataclass
class StreamFrameDecoder:
    """Incremental stream decoder with lifecycle and integrity validation on finish."""

    _buffer: bytearray = field(default_factory=bytearray, repr=False)
    _sequence_frames: list[StreamFrame] = field(default_factory=list, repr=False)
    _prefix_hasher: Any = field(default_factory=hashlib.sha256, repr=False)
    _finished: bool = field(default=False, repr=False)

    def feed(self, chunk: bytes) -> Iterator[StreamFrame]:
        """Feed wire bytes incrementally and yield complete decoded frames."""
        if self._finished:
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_INVALID_VALUE,
                "decoder already finished",
            )
        if type(chunk) is not bytes:
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_INVALID_VALUE,
                "chunk must be immutable bytes",
            )
        if not chunk:
            return
        self._buffer.extend(chunk)
        consumed = 0
        while consumed < len(self._buffer):
            decoded = _try_decode_frame_at(self._buffer, consumed)
            if decoded is None:
                break
            frame_size, frame = decoded
            raw_frame = frame.wire_bytes
            if raw_frame is None:
                raise RepositoryContractError(
                    RepositoryContractErrorCode.WIRE_INVALID_VALUE,
                    "decoded frame missing wire bytes",
                )
            if frame.frame_family not in _TERMINAL_FAMILIES:
                self._prefix_hasher.update(raw_frame)
            self._sequence_frames.append(_frame_for_envelope_storage(frame))
            consumed += frame_size
            yield frame
        if consumed:
            del self._buffer[:consumed]

    def finish(self) -> StreamEnvelope:
        """Validate stream lifecycle and integrity after all frames were consumed."""
        from gateway_repository_contracts.stream import (
            StreamEndMetadata,
            StreamEnvelope,
            validate_stream_sequence,
        )

        if self._finished:
            raise RepositoryContractError(
                RepositoryContractErrorCode.WIRE_INVALID_VALUE,
                "decoder already finished",
            )
        if self._buffer:
            raise RepositoryContractError(
                RepositoryContractErrorCode.STREAM_INCOMPLETE,
                "incomplete stream bytes",
            )
        frames = tuple(self._sequence_frames)
        validate_stream_sequence(frames)
        terminal = frames[-1]
        if terminal.frame_family is StreamFrameFamily.STREAM_END:
            if not isinstance(terminal.metadata, StreamEndMetadata):
                raise RepositoryContractError(
                    RepositoryContractErrorCode.WIRE_INVALID_VALUE,
                    "STREAM_END metadata invalid",
                )
            if terminal.metadata.frames_raw_sha256 != self._prefix_hasher.hexdigest():
                raise RepositoryContractError(
                    RepositoryContractErrorCode.STREAM_INTEGRITY_MISMATCH,
                    "frames_raw_sha256 mismatch",
                )
        self._finished = True
        return StreamEnvelope(frames=frames, _raw_integrity_verified=True)


def encode_stream_frames(frames: Sequence[StreamFrame]) -> Iterator[bytes]:
    """Yield per-frame wire bytes after full stream validation."""
    from gateway_repository_contracts.stream import StreamEnvelope, _freeze_frames

    frozen = _freeze_frames(frames)
    StreamEnvelope(frames=frozen)
    for frame in frozen:
        yield encode_frame_wire_bytes(frame)


def encode_stream_bytes(frames: tuple[StreamFrame, ...]) -> bytes:
    out = bytearray()
    for chunk in encode_stream_frames(frames):
        out.extend(chunk)
    return bytes(out)


def decode_stream_bytes(payload: bytes) -> tuple[StreamFrame, ...]:
    decoder = StreamFrameDecoder()
    frames = list(decoder.feed(payload))
    decoder.finish()
    return tuple(frames)
