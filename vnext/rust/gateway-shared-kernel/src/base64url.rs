//! Strict unpadded base64url for anomaly envelope fields.

use crate::errors::{CanonicalEncodingError, CanonicalErrorCode};

const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

/// Decode unpadded base64url and require encode→decode round-trip identity.
pub(crate) fn decode_base64url_strict(text: &str) -> Result<Vec<u8>, CanonicalEncodingError> {
    if text.contains('=') || !text.bytes().all(is_base64url_byte) {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::AnomalyInvalid,
            "base64url must use unpadded URL-safe alphabet",
        ));
    }
    if text.len() % 4 == 1 {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::AnomalyInvalid,
            "base64url length modulo 4 must not be 1",
        ));
    }
    let raw = decode_base64url_bytes(text)?;
    let encoded = encode_base64url(&raw);
    if encoded != text {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::AnomalyInvalid,
            "base64url is not a canonical unpadded encoding",
        ));
    }
    Ok(raw)
}

pub(crate) fn encode_base64url(raw: &[u8]) -> String {
    let mut out = String::with_capacity((raw.len() * 4).div_ceil(3));
    let mut index = 0usize;
    while index + 3 <= raw.len() {
        let n = (u32::from(raw[index]) << 16)
            | (u32::from(raw[index + 1]) << 8)
            | u32::from(raw[index + 2]);
        out.push(TABLE[((n >> 18) & 0x3f) as usize] as char);
        out.push(TABLE[((n >> 12) & 0x3f) as usize] as char);
        out.push(TABLE[((n >> 6) & 0x3f) as usize] as char);
        out.push(TABLE[(n & 0x3f) as usize] as char);
        index += 3;
    }
    let rem = raw.len() - index;
    if rem == 1 {
        let n = u32::from(raw[index]) << 16;
        out.push(TABLE[((n >> 18) & 0x3f) as usize] as char);
        out.push(TABLE[((n >> 12) & 0x3f) as usize] as char);
    } else if rem == 2 {
        let n = (u32::from(raw[index]) << 16) | (u32::from(raw[index + 1]) << 8);
        out.push(TABLE[((n >> 18) & 0x3f) as usize] as char);
        out.push(TABLE[((n >> 12) & 0x3f) as usize] as char);
        out.push(TABLE[((n >> 6) & 0x3f) as usize] as char);
    }
    out
}

fn is_base64url_byte(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_'
}

fn decode_base64url_bytes(text: &str) -> Result<Vec<u8>, CanonicalEncodingError> {
    let mut values = Vec::with_capacity(text.len());
    for byte in text.bytes() {
        values.push(match decode_sextet(byte) {
            Some(value) => value,
            None => {
                return Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::AnomalyInvalid,
                    "base64url is not decodable",
                ));
            }
        });
    }
    let mut out = Vec::with_capacity(text.len() * 3 / 4);
    let mut index = 0usize;
    while index + 4 <= values.len() {
        let n = (u32::from(values[index]) << 18)
            | (u32::from(values[index + 1]) << 12)
            | (u32::from(values[index + 2]) << 6)
            | u32::from(values[index + 3]);
        out.push(((n >> 16) & 0xff) as u8);
        out.push(((n >> 8) & 0xff) as u8);
        out.push((n & 0xff) as u8);
        index += 4;
    }
    let rem = values.len() - index;
    if rem == 2 {
        let n = (u32::from(values[index]) << 18) | (u32::from(values[index + 1]) << 12);
        out.push(((n >> 16) & 0xff) as u8);
    } else if rem == 3 {
        let n = (u32::from(values[index]) << 18)
            | (u32::from(values[index + 1]) << 12)
            | (u32::from(values[index + 2]) << 6);
        out.push(((n >> 16) & 0xff) as u8);
        out.push(((n >> 8) & 0xff) as u8);
    } else if rem != 0 {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::AnomalyInvalid,
            "base64url is not decodable",
        ));
    }
    Ok(out)
}

fn decode_sextet(byte: u8) -> Option<u8> {
    match byte {
        b'A'..=b'Z' => Some(byte - b'A'),
        b'a'..=b'z' => Some(byte - b'a' + 26),
        b'0'..=b'9' => Some(byte - b'0' + 52),
        b'-' => Some(62),
        b'_' => Some(63),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::{decode_base64url_strict, encode_base64url};
    use crate::errors::CanonicalErrorCode;

    #[test]
    fn roundtrip_and_rejects_padding_and_mod4_eq_1() -> Result<(), String> {
        assert_eq!(encode_base64url(b"bad"), "YmFk");
        assert_eq!(
            decode_base64url_strict("YmFk").map_err(|e| e.to_string())?,
            b"bad"
        );
        match decode_base64url_strict("A") {
            Err(error) if error.code() == CanonicalErrorCode::AnomalyInvalid => Ok(()),
            other => Err(format!("expected ANOMALY_INVALID, got {other:?}")),
        }
    }
}
