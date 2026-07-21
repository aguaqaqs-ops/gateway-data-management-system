//! Test-only base64url codec for vector fixtures (dev `base64` crate).

use base64::Engine;
use base64::engine::general_purpose::URL_SAFE_NO_PAD;

use gateway_shared_kernel::{CanonicalEncodingError, CanonicalErrorCode};

/// Encode raw bytes as unpadded URL-safe base64 (matches Python testing codec).
pub fn encode_base64url(raw: &[u8]) -> String {
    URL_SAFE_NO_PAD.encode(raw)
}

/// Decode unpadded base64url with canonical round-trip check (matches production rules).
pub fn decode_base64url_strict(text: &str) -> Result<Vec<u8>, CanonicalEncodingError> {
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
    let raw = URL_SAFE_NO_PAD.decode(text).map_err(|_| {
        CanonicalEncodingError::with_message(
            CanonicalErrorCode::AnomalyInvalid,
            "base64url is not decodable",
        )
    })?;
    let encoded = encode_base64url(&raw);
    if encoded != text {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::AnomalyInvalid,
            "base64url is not a canonical unpadded encoding",
        ));
    }
    Ok(raw)
}

fn is_base64url_byte(byte: u8) -> bool {
    byte.is_ascii_alphanumeric() || byte == b'-' || byte == b'_'
}
