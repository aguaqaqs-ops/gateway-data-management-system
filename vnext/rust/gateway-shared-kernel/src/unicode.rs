//! Unicode scalar validation shared by JCS, identifiers, and strings.

use crate::errors::{CanonicalEncodingError, CanonicalErrorCode};

pub fn validate_unicode_string(text: &str) -> Result<(), CanonicalEncodingError> {
    for codepoint in text.chars().map(u32::from) {
        if (0xD800..=0xDFFF).contains(&codepoint) {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::InvalidUnicode,
                "string contains lone UTF-16 surrogate",
            ));
        }
        if is_unicode_noncharacter(codepoint) {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::UnicodeNoncharacter,
                "string contains Unicode noncharacter",
            ));
        }
    }
    Ok(())
}

pub fn is_unicode_noncharacter(codepoint: u32) -> bool {
    if (0xFDD0..=0xFDEF).contains(&codepoint) {
        return true;
    }
    (codepoint & 0xFFFE) == 0xFFFE && (0xFFFE..=0x10FFFF).contains(&codepoint)
}

pub fn decode_utf8(raw: &[u8]) -> Result<&str, CanonicalEncodingError> {
    std::str::from_utf8(raw).map_err(|_| {
        CanonicalEncodingError::with_message(
            CanonicalErrorCode::InvalidUtf8,
            "input is not valid UTF-8",
        )
    })
}
