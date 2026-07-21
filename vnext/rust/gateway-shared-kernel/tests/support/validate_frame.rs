//! Test-only scalar-frame structural validator for invalid-case coverage.

use gateway_shared_kernel::{CanonicalEncodingError, CanonicalErrorCode};

const TAG_NULL: u8 = 0x00;
const TAG_BOOLEAN: u8 = 0x01;
const TAG_SIGNED_INTEGER: u8 = 0x10;
const TAG_UNSIGNED_INTEGER: u8 = 0x11;
const TAG_DECIMAL: u8 = 0x12;
const TAG_FLOAT32: u8 = 0x13;
const TAG_FLOAT64: u8 = 0x14;
const TAG_STRING: u8 = 0x20;
const TAG_BINARY: u8 = 0x21;
const TAG_DATE: u8 = 0x30;
const TAG_DATETIME: u8 = 0x31;
const TAG_TIMESTAMP: u8 = 0x32;
const TAG_TIME_DURATION: u8 = 0x33;
const TAG_ANOMALY: u8 = 0x7f;

const MAX_ULEB128_VALUE: u64 = (1 << 63) - 1;

/// Validate scalar frame structure; return stable [`CanonicalEncodingError`] on failure.
pub fn validate_scalar_frame(frame: &[u8]) -> Result<(), CanonicalEncodingError> {
    if frame.is_empty() {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::FrameTruncated,
            "scalar frame is empty",
        ));
    }

    let tag = frame[0];
    if !is_assigned_tag(tag) {
        if tag <= 0x7f {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::ScalarTagReserved,
                format!("reserved scalar tag 0x{tag:02x}"),
            ));
        }
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::ScalarTagUnknown,
            format!("unknown scalar tag 0x{tag:02x}"),
        ));
    }

    let (length, offset) = decode_uleb128(frame, 1)?;
    let length_usize = usize::try_from(length).map_err(|_| {
        frame_length_invalid("scalar frame payload length exceeds addressable size")
    })?;
    let end = offset
        .checked_add(length_usize)
        .ok_or_else(|| frame_length_invalid("scalar frame payload length overflow"))?;
    if end > frame.len() {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::FrameTruncated,
            "scalar frame payload truncated",
        ));
    }
    if end < frame.len() {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::FrameLengthInvalid,
            "scalar frame has trailing bytes after payload",
        ));
    }

    let payload = &frame[offset..end];
    check_obvious_payload(tag, payload)
}

fn is_assigned_tag(tag: u8) -> bool {
    matches!(
        tag,
        TAG_NULL
            | TAG_BOOLEAN
            | TAG_SIGNED_INTEGER
            | TAG_UNSIGNED_INTEGER
            | TAG_DECIMAL
            | TAG_FLOAT32
            | TAG_FLOAT64
            | TAG_STRING
            | TAG_BINARY
            | TAG_DATE
            | TAG_DATETIME
            | TAG_TIMESTAMP
            | TAG_TIME_DURATION
            | TAG_ANOMALY
    )
}

fn check_obvious_payload(tag: u8, payload: &[u8]) -> Result<(), CanonicalEncodingError> {
    match tag {
        TAG_NULL => {
            if !payload.is_empty() {
                return Err(frame_length_invalid("null payload must be empty"));
            }
        }
        TAG_BOOLEAN => {
            if payload.len() != 1 || (payload[0] != 0x00 && payload[0] != 0x01) {
                return Err(frame_length_invalid(
                    "boolean payload must be a single 0x00 or 0x01 byte",
                ));
            }
        }
        TAG_SIGNED_INTEGER | TAG_UNSIGNED_INTEGER => {
            if payload.len() != 8 {
                return Err(frame_length_invalid(
                    "integer payload must be exactly 8 bytes",
                ));
            }
        }
        TAG_FLOAT32 => {
            if payload.len() != 4 {
                return Err(frame_length_invalid(
                    "float32 payload must be exactly 4 bytes",
                ));
            }
        }
        TAG_FLOAT64 => {
            if payload.len() != 8 {
                return Err(frame_length_invalid(
                    "float64 payload must be exactly 8 bytes",
                ));
            }
        }
        TAG_DECIMAL | TAG_STRING | TAG_BINARY | TAG_DATE | TAG_DATETIME | TAG_TIMESTAMP
        | TAG_TIME_DURATION | TAG_ANOMALY => {}
        _ => {}
    }
    Ok(())
}

fn frame_length_invalid(message: &str) -> CanonicalEncodingError {
    CanonicalEncodingError::with_message(CanonicalErrorCode::FrameLengthInvalid, message)
}

fn decode_uleb128(data: &[u8], offset: usize) -> Result<(u64, usize), CanonicalEncodingError> {
    if offset > data.len() {
        return Err(frame_length_invalid("ULEB128 offset out of range"));
    }
    if offset == data.len() {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::FrameTruncated,
            "truncated ULEB128",
        ));
    }

    let mut value: u64 = 0;
    let mut shift: u32 = 0;
    let mut index = offset;

    loop {
        if index >= data.len() {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::FrameTruncated,
                "truncated ULEB128",
            ));
        }
        let byte = data[index];
        index += 1;

        if shift >= 63 {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::Uleb128Overflow,
                "ULEB128 overflow",
            ));
        }

        let chunk = u64::from(byte & 0x7f);
        let shifted = chunk.checked_shl(shift).ok_or_else(|| {
            CanonicalEncodingError::with_message(
                CanonicalErrorCode::Uleb128Overflow,
                "ULEB128 overflow",
            )
        })?;
        value |= shifted;

        if value > MAX_ULEB128_VALUE {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::Uleb128Overflow,
                "ULEB128 overflow",
            ));
        }

        if byte & 0x80 == 0 {
            break;
        }

        shift += 7;
        if shift > 63 {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::Uleb128Overflow,
                "ULEB128 overflow",
            ));
        }
    }

    let encoded = &data[offset..index];
    let minimal = encode_uleb128(value)?;
    if encoded != minimal {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::Uleb128NonMinimal,
            "non-minimal ULEB128 encoding",
        ));
    }

    Ok((value, index))
}

fn encode_uleb128(value: u64) -> Result<Vec<u8>, CanonicalEncodingError> {
    if value > MAX_ULEB128_VALUE {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::Uleb128Overflow,
            "ULEB128 length exceeds 2^63-1",
        ));
    }
    if value == 0 {
        return Ok(vec![0x00]);
    }
    let mut out = Vec::new();
    let mut current = value;
    loop {
        let mut byte = (current & 0x7f) as u8;
        current >>= 7;
        if current != 0 {
            byte |= 0x80;
            out.push(byte);
        } else {
            out.push(byte);
            break;
        }
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::validate_scalar_frame;
    use gateway_shared_kernel::CanonicalErrorCode;

    #[test]
    fn rejects_empty_frame() -> Result<(), String> {
        match validate_scalar_frame(&[]) {
            Err(error) if error.code() == CanonicalErrorCode::FrameTruncated => Ok(()),
            other => Err(format!("expected FRAME_TRUNCATED, got {other:?}")),
        }
    }

    #[test]
    fn rejects_reserved_tag() -> Result<(), String> {
        let frame = [0x02, 0x00];
        match validate_scalar_frame(&frame) {
            Err(error) if error.code() == CanonicalErrorCode::ScalarTagReserved => Ok(()),
            other => Err(format!("expected SCALAR_TAG_RESERVED, got {other:?}")),
        }
    }
}
