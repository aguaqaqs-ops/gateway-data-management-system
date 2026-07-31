"""Stream binary framing contract tests."""

from __future__ import annotations

import hashlib
import struct

import pytest

from gateway_repository_contracts.enums import StreamFrameFamily
from gateway_repository_contracts.errors import RepositoryContractError, RepositoryContractErrorCode
from gateway_repository_contracts.stream import (
    STREAM_BATCH_MAX_BYTES,
    STREAM_FRAME_VERSION,
    CurrentStreamHeaderMetadata,
    EmptyFrameMetadata,
    StreamCheckpointMetadata,
    StreamEndMetadata,
    StreamDecoderFinish,
    StreamEnvelope,
    StreamErrorMetadata,
    StreamFrame,
    StreamFrameDecoder,
    VersionedStreamHeaderMetadata,
    compute_frames_raw_sha256,
    decode_stream,
    encode_stream,
    encode_stream_frames,
    validate_stream_sequence,
)
from gateway_repository_contracts._jcs import encode_jcs_bytes
from gateway_repository_contracts._json import CONTROL_JSON_MAX_BYTES
from gateway_repository_contracts._stream_codec import (
    decode_frame_wire_bytes,
    encode_frame_wire_bytes,
)

VALID_UUID_V7 = "01234567-89ab-7cde-8f01-23456789abcd"
_INCARNATION = "incarnation-1"
_SCHEMA_DIGEST = "a" * 64
_QUERY_DIGEST = "b" * 64


def _digest_prefix(frames_prefix: tuple[StreamFrame, ...]) -> str:
    hasher = hashlib.sha256()
    for frame in frames_prefix:
        hasher.update(frame.to_wire_bytes())
    return hasher.hexdigest()


def _versioned_header(*, table_name: str = "main/release-1") -> StreamFrame:
    metadata = VersionedStreamHeaderMetadata(
        repository_id=VALID_UUID_V7,
        repository_incarnation_id=_INCARNATION,
        table_name=table_name,
        declared_schema_digest=_SCHEMA_DIGEST,
        query_options_digest=_QUERY_DIGEST,
        snapshot_commit_id="commit-1",
    )
    return StreamFrame(
        frame_family=StreamFrameFamily.STREAM_HEADER,
        frame_version=STREAM_FRAME_VERSION,
        metadata=metadata,
    )


def _current_header() -> StreamFrame:
    metadata = CurrentStreamHeaderMetadata(
        repository_id=VALID_UUID_V7,
        repository_incarnation_id=_INCARNATION,
        table_name="main/release-1",
        declared_schema_digest=_SCHEMA_DIGEST,
        query_options_digest=_QUERY_DIGEST,
        current_table_generation_id="gen-table-1",
    )
    return StreamFrame(
        frame_family=StreamFrameFamily.STREAM_HEADER,
        frame_version=STREAM_FRAME_VERSION,
        metadata=metadata,
    )


def _batch(payload: bytes = b"\x00\x01arrow") -> StreamFrame:
    return StreamFrame(
        frame_family=StreamFrameFamily.ARROW_BATCH,
        frame_version=STREAM_FRAME_VERSION,
        metadata=EmptyFrameMetadata(),
        payload=payload,
    )


def _end(frames_prefix: tuple[StreamFrame, ...], *, row_count: int = 1) -> StreamFrame:
    return StreamFrame(
        frame_family=StreamFrameFamily.STREAM_END,
        frame_version=STREAM_FRAME_VERSION,
        metadata=StreamEndMetadata(
            frames_raw_sha256=_digest_prefix(frames_prefix), final_row_count=row_count
        ),
    )


def _error() -> StreamFrame:
    return StreamFrame(
        frame_family=StreamFrameFamily.STREAM_ERROR,
        frame_version=STREAM_FRAME_VERSION,
        metadata=StreamErrorMetadata(error_code="STREAM_READ_FAILED", message="failed"),
    )


def _envelope(*frames: StreamFrame) -> StreamEnvelope:
    return StreamEnvelope(frames=frames)


def test_binary_round_trip_header_to_end() -> None:
    header = _versioned_header()
    end = _end((header,))
    wire = encode_stream((header, end))
    parsed = decode_stream(wire)
    assert parsed.frames[0].frame_family is StreamFrameFamily.STREAM_HEADER
    assert parsed.frames[-1].frame_family is StreamFrameFamily.STREAM_END


def test_binary_round_trip_with_batch() -> None:
    header = _versioned_header()
    batch = _batch()
    end = _end((header, batch), row_count=42)
    parsed = decode_stream(encode_stream((header, batch, end)))
    assert parsed.frames[1].payload == b"\x00\x01arrow"
    assert isinstance(parsed.frames[1].payload, bytes)


def test_unicode_table_name_header() -> None:
    header = _versioned_header(table_name="Tabelle")
    end = _end((header,))
    parsed = decode_stream(encode_stream((header, end)))
    meta = parsed.frames[0].metadata
    assert isinstance(meta, VersionedStreamHeaderMetadata)
    assert meta.table_name == "tabelle"


def test_current_header_binding() -> None:
    header = _current_header()
    end = _end((header,))
    decode_stream(encode_stream((header, end)))


def test_checkpoint_path() -> None:
    header = _versioned_header()
    checkpoint = StreamFrame(
        frame_family=StreamFrameFamily.CHECKPOINT,
        frame_version=STREAM_FRAME_VERSION,
        metadata=StreamCheckpointMetadata(cursor_token="cursor-opaque"),
    )
    end = _end((header, checkpoint))
    validate_stream_sequence((header, checkpoint, end))


def test_stream_error_terminal_path() -> None:
    header = _versioned_header()
    validate_stream_sequence((header, _error()))


def test_missing_terminal_fails_on_decode() -> None:
    header = _versioned_header()
    wire = header.to_wire_bytes() + _batch().to_wire_bytes()
    with pytest.raises(RepositoryContractError) as exc:
        decode_stream(wire)
    assert exc.value.code is RepositoryContractErrorCode.STREAM_INCOMPLETE


def test_digest_mismatch_fails() -> None:
    header = _versioned_header()
    bad_end = StreamFrame(
        frame_family=StreamFrameFamily.STREAM_END,
        frame_version=STREAM_FRAME_VERSION,
        metadata=StreamEndMetadata(frames_raw_sha256="0" * 64, final_row_count=0),
    )
    with pytest.raises(RepositoryContractError) as exc:
        StreamEnvelope(frames=(header, bad_end))
    assert exc.value.code is RepositoryContractErrorCode.STREAM_INTEGRITY_MISMATCH


def test_truncated_frame_fails() -> None:
    header = _versioned_header()
    end = _end((header,))
    wire = bytearray(encode_stream((header, end)))
    wire.pop()
    with pytest.raises(RepositoryContractError) as exc:
        decode_stream(bytes(wire))
    assert exc.value.code is RepositoryContractErrorCode.STREAM_INCOMPLETE


def test_bit_flip_fails_integrity() -> None:
    header = _versioned_header()
    end = _end((header,))
    wire = bytearray(encode_stream((header, end)))
    wire[-1] ^= 0x01
    with pytest.raises(RepositoryContractError):
        decode_stream(bytes(wire))


def test_frame_after_terminal_fails() -> None:
    header = _versioned_header()
    end = _end((header,))
    with pytest.raises(RepositoryContractError) as exc:
        validate_stream_sequence((header, end, _batch()))
    assert exc.value.code is RepositoryContractErrorCode.STREAM_FRAME_AFTER_TERMINAL


def test_external_list_mutation_does_not_invalidate_envelope() -> None:
    header = _versioned_header()
    end = _end((header,))
    frames_list: list[StreamFrame] = [header, end]
    envelope = StreamEnvelope(frames=tuple(frames_list))
    frames_list.clear()
    assert len(envelope.frames) == 2


def test_versioned_header_rejects_wrong_store_kind_in_wire() -> None:
    payload = {
        "repository_id": VALID_UUID_V7,
        "repository_incarnation_id": _INCARNATION,
        "store_kind": "CURRENT",
        "table_name": "t",
        "declared_schema_digest": _SCHEMA_DIGEST,
        "query_options_digest": _QUERY_DIGEST,
        "snapshot_commit_id": "commit-1",
    }
    with pytest.raises(RepositoryContractError):
        VersionedStreamHeaderMetadata.from_wire_dict(payload)


def test_current_header_rejects_wrong_store_kind_in_wire() -> None:
    payload = {
        "repository_id": VALID_UUID_V7,
        "repository_incarnation_id": _INCARNATION,
        "store_kind": "VERSIONED",
        "table_name": "t",
        "declared_schema_digest": _SCHEMA_DIGEST,
        "query_options_digest": _QUERY_DIGEST,
        "current_table_generation_id": "gen-1",
    }
    with pytest.raises(RepositoryContractError):
        CurrentStreamHeaderMetadata.from_wire_dict(payload)


def test_cross_binding_metadata_decode_rejected() -> None:
    bad = {
        "repository_id": VALID_UUID_V7,
        "repository_incarnation_id": _INCARNATION,
        "store_kind": "VERSIONED",
        "table_name": "t",
        "declared_schema_digest": _SCHEMA_DIGEST,
        "query_options_digest": _QUERY_DIGEST,
        "snapshot_commit_id": "commit-1",
        "current_table_generation_id": "gen-1",
    }
    from gateway_repository_contracts._stream_metadata import decode_stream_header_metadata

    with pytest.raises(RepositoryContractError):
        decode_stream_header_metadata(bad)


def test_numeric_commit_id_rejected() -> None:
    payload = {
        "repository_id": VALID_UUID_V7,
        "repository_incarnation_id": _INCARNATION,
        "store_kind": "VERSIONED",
        "table_name": "t",
        "declared_schema_digest": _SCHEMA_DIGEST,
        "query_options_digest": _QUERY_DIGEST,
        "snapshot_commit_id": 123,
    }
    with pytest.raises(RepositoryContractError):
        VersionedStreamHeaderMetadata.from_wire_dict(payload)


def test_missing_incarnation_rejected() -> None:
    payload = {
        "repository_id": VALID_UUID_V7,
        "store_kind": "VERSIONED",
        "table_name": "t",
        "declared_schema_digest": _SCHEMA_DIGEST,
        "query_options_digest": _QUERY_DIGEST,
        "snapshot_commit_id": "commit-1",
    }
    with pytest.raises(RepositoryContractError):
        VersionedStreamHeaderMetadata.from_wire_dict(payload)


def test_batch_max_size_boundary() -> None:
    payload = b"x" * STREAM_BATCH_MAX_BYTES
    header = _versioned_header()
    batch = _batch(payload)
    end = _end((header, batch))
    decode_stream(encode_stream((header, batch, end)))


def test_batch_over_max_size_rejected() -> None:
    with pytest.raises(RepositoryContractError):
        _batch(b"x" * (STREAM_BATCH_MAX_BYTES + 1))


def test_compute_frames_raw_sha256_matches_end_metadata() -> None:
    header = _versioned_header()
    batch = _batch()
    end = _end((header, batch), row_count=7)
    end_meta = end.metadata
    assert isinstance(end_meta, StreamEndMetadata)
    assert compute_frames_raw_sha256((header, batch, end)) == end_meta.frames_raw_sha256


def test_incremental_digest_matches_join() -> None:
    header = _versioned_header()
    batch = _batch()
    end = _end((header, batch))
    assert compute_frames_raw_sha256((header, batch, end)) == _digest_prefix((header, batch))


def test_stream_frame_rejects_bytearray_payload() -> None:
    with pytest.raises(RepositoryContractError):
        StreamFrame(
            frame_family=StreamFrameFamily.ARROW_BATCH,
            frame_version=STREAM_FRAME_VERSION,
            metadata=EmptyFrameMetadata(),
            payload=bytearray(b"arrow"),  # type: ignore[arg-type]
        )


def test_decoder_payload_is_immutable_bytes() -> None:
    header = _versioned_header()
    end = _end((header,))
    wire = encode_stream((header, end))
    decoder = StreamFrameDecoder()
    frames = list(decoder.feed(wire))
    decoder.finish()
    batch = next(frame for frame in frames if frame.frame_family is StreamFrameFamily.STREAM_HEADER)
    assert batch.payload is None
    batch_frame = _batch()
    wire_batch = encode_stream((header, batch_frame, _end((header, batch_frame))))
    decoder2 = StreamFrameDecoder()
    decoded = list(decoder2.feed(wire_batch))
    decoder2.finish()
    payload = next(frame.payload for frame in decoded if frame.payload is not None)
    assert type(payload) is bytes


def test_envelope_wire_unchanged_after_external_buffer_mutation() -> None:
    mutable = bytearray(b"arrow")
    header = _versioned_header()
    batch = StreamFrame(
        frame_family=StreamFrameFamily.ARROW_BATCH,
        frame_version=STREAM_FRAME_VERSION,
        metadata=EmptyFrameMetadata(),
        payload=bytes(mutable),
    )
    end = _end((header, batch))
    envelope = StreamEnvelope(frames=(header, batch, end))
    wire_before = envelope.to_wire_bytes()
    mutable[0] = ord("b")
    assert envelope.to_wire_bytes() == wire_before


def test_decoder_finish_rejects_empty_stream() -> None:
    decoder = StreamFrameDecoder()
    with pytest.raises(RepositoryContractError) as exc:
        decoder.finish()
    assert exc.value.code is RepositoryContractErrorCode.STREAM_INCOMPLETE


def test_decoder_finish_rejects_header_only() -> None:
    header = _versioned_header()
    wire = encode_frame_wire_bytes(header)
    decoder = StreamFrameDecoder()
    list(decoder.feed(wire))
    with pytest.raises(RepositoryContractError) as exc:
        decoder.finish()
    assert exc.value.code is RepositoryContractErrorCode.STREAM_INCOMPLETE


def test_decoder_finish_rejects_duplicate_header() -> None:
    header = _versioned_header()
    wire = encode_frame_wire_bytes(header) + encode_frame_wire_bytes(header)
    decoder = StreamFrameDecoder()
    list(decoder.feed(wire))
    with pytest.raises(RepositoryContractError) as exc:
        decoder.finish()
    assert exc.value.code is RepositoryContractErrorCode.STREAM_DUPLICATE_HEADER


def test_decoder_finish_rejects_wrong_end_digest() -> None:
    header = _versioned_header()
    bad_end = StreamFrame(
        frame_family=StreamFrameFamily.STREAM_END,
        frame_version=STREAM_FRAME_VERSION,
        metadata=StreamEndMetadata(frames_raw_sha256="0" * 64, final_row_count=1),
    )
    wire = encode_frame_wire_bytes(header) + encode_frame_wire_bytes(bad_end)
    decoder = StreamFrameDecoder()
    list(decoder.feed(wire))
    with pytest.raises(RepositoryContractError) as exc:
        decoder.finish()
    assert exc.value.code is RepositoryContractErrorCode.STREAM_INTEGRITY_MISMATCH


def test_decoder_feed_in_chunks_then_finish() -> None:
    header = _versioned_header()
    batch1 = _batch(b"\x01")
    batch2 = _batch(b"\x02")
    end = _end((header, batch1, batch2))
    wire = encode_stream((header, batch1, batch2, end))
    decoder = StreamFrameDecoder()
    fed_frames: list[StreamFrame] = []
    for index in range(0, len(wire), 3):
        fed_frames.extend(decoder.feed(wire[index : index + 3]))
    receipt = decoder.finish()
    assert isinstance(receipt, StreamDecoderFinish)
    assert receipt.terminal_family is StreamFrameFamily.STREAM_END
    assert receipt.stream_end is not None
    assert len(fed_frames) == 4
    assert not hasattr(receipt, "frames")
    assert not hasattr(receipt, "to_wire_bytes")


def test_decode_stream_collected_envelope_round_trips() -> None:
    header = _versioned_header()
    batch = _batch(b"x" * 1024)
    end = _end((header, batch), row_count=1)
    wire = encode_stream((header, batch, end))
    envelope = decode_stream(wire)
    assert envelope.to_wire_bytes() == wire
    batch_frame = next(
        frame for frame in envelope.frames if frame.frame_family is StreamFrameFamily.ARROW_BATCH
    )
    assert batch_frame.payload == b"x" * 1024


def test_decoder_finish_rejects_non_canonical_control_jcs() -> None:
    header = _versioned_header()
    canonical_header_wire = encode_frame_wire_bytes(header)
    header_body = canonical_header_wire[6:]
    padded_body = b" " + header_body + b" "
    tampered_header = canonical_header_wire[:2] + struct.pack(">I", len(padded_body)) + padded_body
    batch = _batch()
    end = _end((header, batch))
    # END digest matches canonical re-encode, but header wire is non-JCS.
    end_wire = encode_frame_wire_bytes(end)
    wire = tampered_header + encode_frame_wire_bytes(batch) + end_wire
    decoder = StreamFrameDecoder()
    with pytest.raises(RepositoryContractError) as exc:
        list(decoder.feed(wire))
    assert exc.value.code is RepositoryContractErrorCode.WIRE_JSON_SYNTAX_INVALID


def test_decoder_raw_digest_detects_wire_tampering() -> None:
    header = _versioned_header()
    batch = _batch()
    end = _end((header, batch))
    wire = bytearray(encode_stream((header, batch, end)))
    header_len = len(encode_frame_wire_bytes(header))
    wire[header_len + 10] ^= 0x01
    decoder = StreamFrameDecoder()
    list(decoder.feed(bytes(wire)))
    with pytest.raises(RepositoryContractError) as exc:
        decoder.finish()
    assert exc.value.code is RepositoryContractErrorCode.STREAM_INTEGRITY_MISMATCH


def test_encode_stream_frames_rejects_incomplete_stream() -> None:
    header = _versioned_header()
    with pytest.raises(RepositoryContractError) as exc:
        list(encode_stream_frames(()))
    assert exc.value.code is RepositoryContractErrorCode.STREAM_INCOMPLETE
    with pytest.raises(RepositoryContractError) as exc:
        list(encode_stream_frames((header,)))
    assert exc.value.code is RepositoryContractErrorCode.STREAM_INCOMPLETE


def test_encode_stream_frames_rejects_wrong_end_digest() -> None:
    header = _versioned_header()
    batch = _batch()
    bad_end = StreamFrame(
        frame_family=StreamFrameFamily.STREAM_END,
        frame_version=STREAM_FRAME_VERSION,
        metadata=StreamEndMetadata(frames_raw_sha256="0" * 64, final_row_count=1),
    )
    with pytest.raises(RepositoryContractError) as exc:
        list(encode_stream_frames((header, batch, bad_end)))
    assert exc.value.code is RepositoryContractErrorCode.STREAM_INTEGRITY_MISMATCH


def test_decoder_rejects_unknown_version_on_header_chunk() -> None:
    header = struct.pack(">BBI", 2, 2, 64 * 1024 * 1024)
    decoder = StreamFrameDecoder()
    with pytest.raises(RepositoryContractError) as exc:
        list(decoder.feed(header))
    assert exc.value.code is RepositoryContractErrorCode.STREAM_VERSION_MISMATCH


def test_canonical_jcs_matches_encode_jcs_bytes() -> None:
    header = _versioned_header()
    wire = encode_frame_wire_bytes(header)
    body = wire[6:]
    assert body == encode_jcs_bytes(header.metadata.to_wire_dict())


def test_encode_stream_frames_yields_per_frame_chunks() -> None:
    header = _versioned_header()
    batch = _batch()
    end = _end((header, batch))
    chunks = list(encode_stream_frames((header, batch, end)))
    assert len(chunks) == 3
    assert b"".join(chunks) == encode_stream((header, batch, end))


def test_oversized_control_encode_rejected() -> None:
    header = _versioned_header()
    error = StreamFrame(
        frame_family=StreamFrameFamily.STREAM_ERROR,
        frame_version=STREAM_FRAME_VERSION,
        metadata=StreamErrorMetadata(error_code="E", message="a" * 1_048_576),
    )
    with pytest.raises(RepositoryContractError):
        encode_frame_wire_bytes(error)
    with pytest.raises(RepositoryContractError):
        encode_stream((header, error))


def test_decode_rejects_oversized_control_body_length() -> None:
    import struct

    header = struct.pack(">BBI", 1, 5, CONTROL_JSON_MAX_BYTES + 1)
    with pytest.raises(RepositoryContractError) as exc:
        decode_frame_wire_bytes(header)
    assert exc.value.code is RepositoryContractErrorCode.WIRE_PAYLOAD_TOO_LARGE


def test_decode_rejects_oversized_batch_body_length() -> None:
    import struct

    header = struct.pack(">BBI", 1, 2, STREAM_BATCH_MAX_BYTES + 1)
    with pytest.raises(RepositoryContractError) as exc:
        decode_frame_wire_bytes(header)
    assert exc.value.code is RepositoryContractErrorCode.WIRE_PAYLOAD_TOO_LARGE


def test_decode_rejects_truncated_frame_header() -> None:
    with pytest.raises(RepositoryContractError) as exc:
        decode_frame_wire_bytes(b"\x01\x01")
    assert exc.value.code is RepositoryContractErrorCode.STREAM_INVALID_PAYLOAD


def test_decode_rejects_truncated_frame_body() -> None:
    import struct

    header = struct.pack(">BBI", 1, 3, 10)
    with pytest.raises(RepositoryContractError) as exc:
        decode_frame_wire_bytes(header + b"\x00\x00")
    assert exc.value.code is RepositoryContractErrorCode.STREAM_INVALID_PAYLOAD


def _max_control_message_length() -> int:
    low = 0
    high = CONTROL_JSON_MAX_BYTES
    while low < high:
        mid = (low + high + 1) // 2
        frame = StreamFrame(
            frame_family=StreamFrameFamily.STREAM_ERROR,
            frame_version=STREAM_FRAME_VERSION,
            metadata=StreamErrorMetadata(error_code="E", message="a" * mid),
        )
        try:
            encode_frame_wire_bytes(frame)
        except RepositoryContractError:
            high = mid - 1
        else:
            low = mid
    return low


def test_control_body_boundary_sizes() -> None:
    max_message = _max_control_message_length()
    fits = StreamFrame(
        frame_family=StreamFrameFamily.STREAM_ERROR,
        frame_version=STREAM_FRAME_VERSION,
        metadata=StreamErrorMetadata(error_code="E", message="a" * max_message),
    )
    encode_frame_wire_bytes(fits)

    too_large = StreamFrame(
        frame_family=StreamFrameFamily.STREAM_ERROR,
        frame_version=STREAM_FRAME_VERSION,
        metadata=StreamErrorMetadata(error_code="E", message="a" * (max_message + 1)),
    )
    with pytest.raises(RepositoryContractError):
        encode_frame_wire_bytes(too_large)
