//! Closed formal registry of Shared Kernel stable error codes.

use core::fmt;

use thiserror::Error;

/// Normative stable error code strings compared by conformance harnesses.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum CanonicalErrorCode {
    InvalidUtf8,
    InvalidUnicode,
    UnicodeNoncharacter,
    JcsSyntaxInvalid,
    JcsDuplicateMember,
    JcsNumberOutOfRange,
    JcsNonFiniteNumber,
    IdentifierEmpty,
    IdentifierCollision,
    TypeMismatch,
    IntegerOutOfRange,
    DecimalInvalid,
    FloatNonFinite,
    TemporalInvalid,
    TimeOutOfRange,
    AnomalyInvalid,
    ScalarTagUnknown,
    ScalarTagReserved,
    FrameTruncated,
    Uleb128NonMinimal,
    Uleb128Overflow,
    FrameLengthInvalid,
    CollectionSemanticsUnknown,
    CollectionDuplicateItem,
    CollectionDuplicateKey,
}

impl CanonicalErrorCode {
    /// Formal wire / vector string for this code.
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::InvalidUtf8 => "CANONICAL_INVALID_UTF8",
            Self::InvalidUnicode => "CANONICAL_INVALID_UNICODE",
            Self::UnicodeNoncharacter => "CANONICAL_UNICODE_NONCHARACTER",
            Self::JcsSyntaxInvalid => "CANONICAL_JCS_SYNTAX_INVALID",
            Self::JcsDuplicateMember => "CANONICAL_JCS_DUPLICATE_MEMBER",
            Self::JcsNumberOutOfRange => "CANONICAL_JCS_NUMBER_OUT_OF_RANGE",
            Self::JcsNonFiniteNumber => "CANONICAL_JCS_NON_FINITE_NUMBER",
            Self::IdentifierEmpty => "CANONICAL_IDENTIFIER_EMPTY",
            Self::IdentifierCollision => "CANONICAL_IDENTIFIER_COLLISION",
            Self::TypeMismatch => "CANONICAL_TYPE_MISMATCH",
            Self::IntegerOutOfRange => "CANONICAL_INTEGER_OUT_OF_RANGE",
            Self::DecimalInvalid => "CANONICAL_DECIMAL_INVALID",
            Self::FloatNonFinite => "CANONICAL_FLOAT_NON_FINITE",
            Self::TemporalInvalid => "CANONICAL_TEMPORAL_INVALID",
            Self::TimeOutOfRange => "CANONICAL_TIME_OUT_OF_RANGE",
            Self::AnomalyInvalid => "CANONICAL_ANOMALY_INVALID",
            Self::ScalarTagUnknown => "CANONICAL_SCALAR_TAG_UNKNOWN",
            Self::ScalarTagReserved => "CANONICAL_SCALAR_TAG_RESERVED",
            Self::FrameTruncated => "CANONICAL_FRAME_TRUNCATED",
            Self::Uleb128NonMinimal => "CANONICAL_ULEB128_NON_MINIMAL",
            Self::Uleb128Overflow => "CANONICAL_ULEB128_OVERFLOW",
            Self::FrameLengthInvalid => "CANONICAL_FRAME_LENGTH_INVALID",
            Self::CollectionSemanticsUnknown => "CANONICAL_COLLECTION_SEMANTICS_UNKNOWN",
            Self::CollectionDuplicateItem => "CANONICAL_COLLECTION_DUPLICATE_ITEM",
            Self::CollectionDuplicateKey => "CANONICAL_COLLECTION_DUPLICATE_KEY",
        }
    }

    /// All registry members in formal document order.
    pub const fn all() -> &'static [Self] {
        FORMAL_STABLE_ERROR_CODES
    }
}

impl fmt::Display for CanonicalErrorCode {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// Complete formal stable-error registry (must equal owning contract).
pub const FORMAL_STABLE_ERROR_CODES: &[CanonicalErrorCode] = &[
    CanonicalErrorCode::InvalidUtf8,
    CanonicalErrorCode::InvalidUnicode,
    CanonicalErrorCode::UnicodeNoncharacter,
    CanonicalErrorCode::JcsSyntaxInvalid,
    CanonicalErrorCode::JcsDuplicateMember,
    CanonicalErrorCode::JcsNumberOutOfRange,
    CanonicalErrorCode::JcsNonFiniteNumber,
    CanonicalErrorCode::IdentifierEmpty,
    CanonicalErrorCode::IdentifierCollision,
    CanonicalErrorCode::TypeMismatch,
    CanonicalErrorCode::IntegerOutOfRange,
    CanonicalErrorCode::DecimalInvalid,
    CanonicalErrorCode::FloatNonFinite,
    CanonicalErrorCode::TemporalInvalid,
    CanonicalErrorCode::TimeOutOfRange,
    CanonicalErrorCode::AnomalyInvalid,
    CanonicalErrorCode::ScalarTagUnknown,
    CanonicalErrorCode::ScalarTagReserved,
    CanonicalErrorCode::FrameTruncated,
    CanonicalErrorCode::Uleb128NonMinimal,
    CanonicalErrorCode::Uleb128Overflow,
    CanonicalErrorCode::FrameLengthInvalid,
    CanonicalErrorCode::CollectionSemanticsUnknown,
    CanonicalErrorCode::CollectionDuplicateItem,
    CanonicalErrorCode::CollectionDuplicateKey,
];

/// Production failure carrying a normative stable error code.
///
/// Messages are diagnostic only and do not participate in conformance.
#[derive(Debug, Clone, PartialEq, Eq, Error)]
#[error("{code}")]
pub struct CanonicalEncodingError {
    code: CanonicalErrorCode,
    message: String,
}

impl CanonicalEncodingError {
    pub fn new(code: CanonicalErrorCode) -> Self {
        Self {
            code,
            message: String::new(),
        }
    }

    pub fn with_message(code: CanonicalErrorCode, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
        }
    }

    pub fn code(&self) -> CanonicalErrorCode {
        self.code
    }

    pub fn stable_code(&self) -> &'static str {
        self.code.as_str()
    }

    pub fn message(&self) -> &str {
        &self.message
    }
}

#[cfg(test)]
mod tests {
    use super::{CanonicalErrorCode, FORMAL_STABLE_ERROR_CODES};
    use std::collections::BTreeSet;

    const EXPECTED_CODES: &[&str] = &[
        "CANONICAL_INVALID_UTF8",
        "CANONICAL_INVALID_UNICODE",
        "CANONICAL_UNICODE_NONCHARACTER",
        "CANONICAL_JCS_SYNTAX_INVALID",
        "CANONICAL_JCS_DUPLICATE_MEMBER",
        "CANONICAL_JCS_NUMBER_OUT_OF_RANGE",
        "CANONICAL_JCS_NON_FINITE_NUMBER",
        "CANONICAL_IDENTIFIER_EMPTY",
        "CANONICAL_IDENTIFIER_COLLISION",
        "CANONICAL_TYPE_MISMATCH",
        "CANONICAL_INTEGER_OUT_OF_RANGE",
        "CANONICAL_DECIMAL_INVALID",
        "CANONICAL_FLOAT_NON_FINITE",
        "CANONICAL_TEMPORAL_INVALID",
        "CANONICAL_TIME_OUT_OF_RANGE",
        "CANONICAL_ANOMALY_INVALID",
        "CANONICAL_SCALAR_TAG_UNKNOWN",
        "CANONICAL_SCALAR_TAG_RESERVED",
        "CANONICAL_FRAME_TRUNCATED",
        "CANONICAL_ULEB128_NON_MINIMAL",
        "CANONICAL_ULEB128_OVERFLOW",
        "CANONICAL_FRAME_LENGTH_INVALID",
        "CANONICAL_COLLECTION_SEMANTICS_UNKNOWN",
        "CANONICAL_COLLECTION_DUPLICATE_ITEM",
        "CANONICAL_COLLECTION_DUPLICATE_KEY",
    ];

    #[test]
    fn stable_error_registry_matches_formal_contract() {
        let actual: BTreeSet<&str> = FORMAL_STABLE_ERROR_CODES
            .iter()
            .map(|code| code.as_str())
            .collect();
        let expected: BTreeSet<&str> = EXPECTED_CODES.iter().copied().collect();
        assert_eq!(actual, expected);
        assert_eq!(FORMAL_STABLE_ERROR_CODES.len(), EXPECTED_CODES.len());
        assert_eq!(CanonicalErrorCode::all().len(), EXPECTED_CODES.len());
    }

    #[test]
    fn stable_error_registry_has_no_duplicate_strings() {
        let mut seen = BTreeSet::new();
        for code in FORMAL_STABLE_ERROR_CODES {
            assert!(
                seen.insert(code.as_str()),
                "duplicate stable code string: {}",
                code.as_str()
            );
        }
    }
}
