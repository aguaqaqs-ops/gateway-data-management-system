//! Minimal ULEB128 encode/decode for scalar and framing lengths.

use crate::errors::{CanonicalEncodingError, CanonicalErrorCode};

/// Normative maximum payload / length value: `2^63 - 1`.
pub(crate) const MAX_ULEB128_VALUE: u64 = (1 << 63) - 1;

/// Encode `value` as minimal ULEB128.
pub(crate) fn encode_uleb128(value: u64) -> Result<Vec<u8>, CanonicalEncodingError> {
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

/// Decode a minimal ULEB128 starting at `offset`.
///
/// Returns `(value, next_offset)`.
#[allow(dead_code)] // R4/R5 frame validators are the first decode callers.
pub(crate) fn decode_uleb128(
    data: &[u8],
    offset: usize,
) -> Result<(u64, usize), CanonicalEncodingError> {
    if offset > data.len() {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::FrameLengthInvalid,
            "ULEB128 offset out of range",
        ));
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
        match chunk.checked_shl(shift) {
            Some(shifted) => {
                value |= shifted;
            }
            None => {
                return Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::Uleb128Overflow,
                    "ULEB128 overflow",
                ));
            }
        }

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
    if encoded != minimal.as_slice() {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::Uleb128NonMinimal,
            "non-minimal ULEB128 encoding",
        ));
    }

    Ok((value, index))
}

#[cfg(test)]
mod tests {
    use super::{MAX_ULEB128_VALUE, decode_uleb128, encode_uleb128};
    use crate::errors::CanonicalErrorCode;

    #[test]
    fn encode_minimal_samples() -> Result<(), String> {
        let cases = [
            (0u64, vec![0x00]),
            (1, vec![0x01]),
            (127, vec![0x7f]),
            (128, vec![0x80, 0x01]),
            (255, vec![0xff, 0x01]),
            (300, vec![0xac, 0x02]),
        ];
        for (value, expected) in cases {
            let encoded = encode_uleb128(value).map_err(|e| e.to_string())?;
            assert_eq!(encoded, expected);
        }
        Ok(())
    }

    #[test]
    fn decode_roundtrip_and_non_minimal() -> Result<(), String> {
        let encoded = encode_uleb128(300).map_err(|e| e.to_string())?;
        let (value, next) = decode_uleb128(&encoded, 0).map_err(|e| e.to_string())?;
        assert_eq!(value, 300);
        assert_eq!(next, encoded.len());

        match decode_uleb128(&[0x80, 0x00], 0) {
            Err(error) => assert_eq!(error.code(), CanonicalErrorCode::Uleb128NonMinimal),
            Ok(_) => return Err("non-minimal must fail".to_string()),
        }
        Ok(())
    }

    #[test]
    fn decode_truncated() -> Result<(), String> {
        match decode_uleb128(&[0x80], 0) {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::FrameTruncated);
                Ok(())
            }
            Ok(_) => Err("truncated must fail".to_string()),
        }
    }

    #[test]
    fn rejects_overflow_above_max() -> Result<(), String> {
        match encode_uleb128(MAX_ULEB128_VALUE + 1) {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::Uleb128Overflow);
                Ok(())
            }
            Ok(_) => Err("value above 2^63-1 must fail".to_string()),
        }
    }

    #[test]
    fn max_value_roundtrip() -> Result<(), String> {
        let encoded = encode_uleb128(MAX_ULEB128_VALUE).map_err(|e| e.to_string())?;
        let (value, _) = decode_uleb128(&encoded, 0).map_err(|e| e.to_string())?;
        assert_eq!(value, MAX_ULEB128_VALUE);
        Ok(())
    }
}
