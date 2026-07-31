"""Private binary stream frame codec (v1)."""

from __future__ import annotations

import json
import struct
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

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


def decode_frame_wire_bytes(payload: bytes, *, offset: int = 0) -> tuple[StreamFrame, int]:
    from gateway_repository_contracts.stream import STREAM_FRAME_VERSION, StreamFrame

    if offset + STREAM_FRAME_HEADER_SIZE > len(payload):
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_INVALID_PAYLOAD,
            "truncated frame header",
        )
    frame_version, family_id, body_length = struct.unpack_from(">BBI", payload, offset)
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
    body_start = offset + STREAM_FRAME_HEADER_SIZE
    body_end = body_start + body_length
    if body_end > len(payload):
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_INVALID_PAYLOAD,
            "truncated frame payload",
        )
    body = bytes(payload[body_start:body_end])
    next_offset = body_end
    if frame_family is StreamFrameFamily.ARROW_BATCH:
        metadata: StreamFrameMetadata = EmptyFrameMetadata()
        batch_payload = body
    elif frame_family is StreamFrameFamily.STREAM_HEADER:
        metadata = decode_stream_header_metadata(_decode_metadata_jcs(body))
        batch_payload = None
    elif frame_family is StreamFrameFamily.CHECKPOINT:
        metadata = StreamCheckpointMetadata.from_wire_dict(_decode_metadata_jcs(body))
        batch_payload = None
    elif frame_family is StreamFrameFamily.STREAM_END:
        metadata = StreamEndMetadata.from_wire_dict(_decode_metadata_jcs(body))
        batch_payload = None
    elif frame_family is StreamFrameFamily.STREAM_ERROR:
        metadata = StreamErrorMetadata.from_wire_dict(_decode_metadata_jcs(body))
        batch_payload = None
    else:
        raise RepositoryContractError(
            RepositoryContractErrorCode.STREAM_UNKNOWN_FRAME,
            "unknown frame family",
        )
    frame = StreamFrame(
        frame_family=frame_family,
        frame_version=STREAM_FRAME_VERSION,
        metadata=metadata,
        payload=batch_payload,
    )
    return frame, next_offset


def _frame_wire_size(buffer: bytes | bytearray, *, offset: int = 0) -> int | None:
    if offset + STREAM_FRAME_HEADER_SIZE > len(buffer):
        return None
    _frame_version, family_id, body_length = struct.unpack_from(">BBI", buffer, offset)
    frame_family = _ID_TO_FAMILY.get(family_id)
    if frame_family is None:
        return STREAM_FRAME_HEADER_SIZE
    try:
        _validate_frame_body_length(frame_family, body_length)
    except RepositoryContractError:
        return STREAM_FRAME_HEADER_SIZE
    total = STREAM_FRAME_HEADER_SIZE + body_length
    if offset + total > len(buffer):
        return None
    return int(total)


@dataclass
class StreamFrameDecoder:
    """Incremental stream decoder with lifecycle and integrity validation on finish."""

    _buffer: bytearray = field(default_factory=bytearray, repr=False)
    _frames: list[StreamFrame] = field(default_factory=list, repr=False)
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
        offset = 0
        while offset < len(self._buffer):
            frame_size = _frame_wire_size(self._buffer, offset=offset)
            if frame_size is None:
                break
            frame, _ = decode_frame_wire_bytes(bytes(self._buffer), offset=offset)
            self._frames.append(frame)
            offset += frame_size
            yield frame
        if offset:
            del self._buffer[:offset]

    def finish(self) -> StreamEnvelope:
        """Validate stream lifecycle and integrity after all frames were consumed."""
        from gateway_repository_contracts.stream import StreamEnvelope

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
        self._finished = True
        return StreamEnvelope(frames=tuple(self._frames))


def encode_stream_frames(frames: Sequence[StreamFrame]) -> Iterator[bytes]:
    """Yield per-frame wire bytes without building the full stream first."""
    for frame in frames:
        yield encode_frame_wire_bytes(frame)


def encode_stream_bytes(frames: tuple[StreamFrame, ...]) -> bytes:
    out = bytearray()
    for chunk in encode_stream_frames(frames):
        out.extend(chunk)
    return bytes(out)


def decode_stream_bytes(payload: bytes) -> tuple[StreamFrame, ...]:
    decoder = StreamFrameDecoder()
    for _frame in decoder.feed(payload):
        pass
    return decoder.finish().frames
