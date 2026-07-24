//! Production value types for Shared Canonical Encoding.

use core::fmt;

use thiserror::Error;

const DIGEST_REF_PREFIX: &str = "sha256:";
const SHA256_HEX_LEN: usize = 64;
const RAW_DIGEST_LEN: usize = 32;

/// Structural construction failure (not a normative stable encoding code).
#[derive(Debug, Clone, PartialEq, Eq, Error)]
#[error("{0}")]
pub struct TypeConstructionError(String);

impl TypeConstructionError {
    fn new(message: impl Into<String>) -> Self {
        Self(message.into())
    }
}

/// Closed declared-type registry, Rust-idiomatic enum form.
///
/// Prefer the validated constructors below. Direct variant construction is
/// possible for pattern matching, but [`DeclaredType::validate`] / normalize
/// reject out-of-range widths.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DeclaredType {
    Null,
    Boolean,
    SignedInteger { bits: u8 },
    UnsignedInteger { bits: u8 },
    Decimal { precision: u8, scale: u8 },
    Float32,
    Float64,
    String,
    Binary,
    Bit { bit_width: u8 },
    Date,
    DateTime,
    Timestamp,
    TimeDuration,
    SourceLiteralAnomaly,
}

const INTEGER_BITS: &[u8] = &[8, 16, 24, 32, 64];

impl DeclaredType {
    pub fn null() -> Self {
        Self::Null
    }

    pub fn boolean() -> Self {
        Self::Boolean
    }

    pub fn signed_integer(bits: u8) -> Result<Self, TypeConstructionError> {
        if !INTEGER_BITS.contains(&bits) {
            return Err(TypeConstructionError::new(
                "integer declared type requires bits in {8,16,24,32,64}",
            ));
        }
        Ok(Self::SignedInteger { bits })
    }

    pub fn unsigned_integer(bits: u8) -> Result<Self, TypeConstructionError> {
        if !INTEGER_BITS.contains(&bits) {
            return Err(TypeConstructionError::new(
                "integer declared type requires bits in {8,16,24,32,64}",
            ));
        }
        Ok(Self::UnsignedInteger { bits })
    }

    pub fn decimal(precision: u8, scale: u8) -> Result<Self, TypeConstructionError> {
        if !(1..=65).contains(&precision) || !(0..=30).contains(&scale) {
            return Err(TypeConstructionError::new(
                "decimal precision/scale out of owner range",
            ));
        }
        if scale > precision {
            return Err(TypeConstructionError::new(
                "decimal scale must be <= precision",
            ));
        }
        Ok(Self::Decimal { precision, scale })
    }

    pub fn float32() -> Self {
        Self::Float32
    }

    pub fn float64() -> Self {
        Self::Float64
    }

    pub fn string() -> Self {
        Self::String
    }

    pub fn binary() -> Self {
        Self::Binary
    }

    pub fn bit(bit_width: u8) -> Result<Self, TypeConstructionError> {
        if !(1..=64).contains(&bit_width) {
            return Err(TypeConstructionError::new(
                "bit declared type requires bit_width in 1..=64",
            ));
        }
        Ok(Self::Bit { bit_width })
    }

    pub fn date() -> Self {
        Self::Date
    }

    pub fn datetime() -> Self {
        Self::DateTime
    }

    pub fn timestamp() -> Self {
        Self::Timestamp
    }

    pub fn time_duration() -> Self {
        Self::TimeDuration
    }

    pub fn source_literal_anomaly() -> Self {
        Self::SourceLiteralAnomaly
    }

    /// Formal kind string (vector / anomaly descriptor shape).
    pub fn kind_str(&self) -> &'static str {
        match self {
            Self::Null => "null",
            Self::Boolean => "boolean",
            Self::SignedInteger { .. } => "signed-integer",
            Self::UnsignedInteger { .. } => "unsigned-integer",
            Self::Decimal { .. } => "decimal",
            Self::Float32 => "float32",
            Self::Float64 => "float64",
            Self::String => "string",
            Self::Binary => "binary",
            Self::Bit { .. } => "bit",
            Self::Date => "date",
            Self::DateTime => "datetime",
            Self::Timestamp => "timestamp",
            Self::TimeDuration => "time-duration",
            Self::SourceLiteralAnomaly => "source-literal-anomaly",
        }
    }

    /// Re-check v1 owner width / precision / scale bounds.
    pub fn validate(&self) -> Result<(), TypeConstructionError> {
        match self {
            Self::SignedInteger { bits } | Self::UnsignedInteger { bits } => {
                if !INTEGER_BITS.contains(bits) {
                    return Err(TypeConstructionError::new(
                        "integer declared type requires bits in {8,16,24,32,64}",
                    ));
                }
            }
            Self::Decimal { precision, scale } => {
                if !(1..=65).contains(precision) || !(0..=30).contains(scale) {
                    return Err(TypeConstructionError::new(
                        "decimal precision/scale out of owner range",
                    ));
                }
                if scale > precision {
                    return Err(TypeConstructionError::new(
                        "decimal scale must be <= precision",
                    ));
                }
            }
            Self::Bit { bit_width } => {
                if !(1..=64).contains(bit_width) {
                    return Err(TypeConstructionError::new(
                        "bit declared type requires bit_width in 1..=64",
                    ));
                }
            }
            Self::Null
            | Self::Boolean
            | Self::Float32
            | Self::Float64
            | Self::String
            | Self::Binary
            | Self::Date
            | Self::DateTime
            | Self::Timestamp
            | Self::TimeDuration
            | Self::SourceLiteralAnomaly => {}
        }
        Ok(())
    }
}

/// UTF-8 logical literal input.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Utf8LogicalLiteral {
    pub text: String,
}

/// Raw-byte logical literal input.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RawLogicalLiteral {
    pub raw_bytes: Vec<u8>,
}

/// Logical literal prior to typed normalization.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum LogicalLiteral {
    Utf8(Utf8LogicalLiteral),
    Raw(RawLogicalLiteral),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NullScalar;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BooleanScalar {
    pub value: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SignedIntegerScalar {
    pub decimal: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct UnsignedIntegerScalar {
    pub decimal: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DecimalScalar {
    pub decimal: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Float32Scalar {
    pub bits_hex: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Float64Scalar {
    pub bits_hex: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StringScalar {
    pub text: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BinaryScalar {
    pub raw_bytes: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BitScalar {
    pub raw_bytes: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DateScalar {
    pub text: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DateTimeScalar {
    pub text: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TimestampScalar {
    pub text: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TimeDurationScalar {
    pub text: String,
}

/// v1 anomaly envelope fields (exact four-key object).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AnomalyScalar {
    pub declared_type: DeclaredType,
    pub raw_base64url: String,
    pub raw_encoding: String,
    pub reason: String,
}

/// Closed typed scalar value prior to framing.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TypedScalar {
    Null(NullScalar),
    Boolean(BooleanScalar),
    SignedInteger(SignedIntegerScalar),
    UnsignedInteger(UnsignedIntegerScalar),
    Decimal(DecimalScalar),
    Float32(Float32Scalar),
    Float64(Float64Scalar),
    String(StringScalar),
    Binary(BinaryScalar),
    Bit(BitScalar),
    Date(DateScalar),
    DateTime(DateTimeScalar),
    Timestamp(TimestampScalar),
    TimeDuration(TimeDurationScalar),
    Anomaly(AnomalyScalar),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EncodedScalar {
    pub payload: Vec<u8>,
    pub scalar_frame: Vec<u8>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct NormalizedScalar {
    pub typed_value: TypedScalar,
    pub payload: Vec<u8>,
    pub scalar_frame: Vec<u8>,
}

/// Closed formal registry of semantic digest kinds.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum DigestKind {
    Row,
    RawContent,
    CollectionItem,
    VectorSet,
    TableSchema,
    ScenarioInput,
    ScenarioFixture,
    RunEvidence,
}

impl DigestKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Row => "row",
            Self::RawContent => "raw-content",
            Self::CollectionItem => "collection-item",
            Self::VectorSet => "vector-set",
            Self::TableSchema => "table-schema",
            Self::ScenarioInput => "scenario-input",
            Self::ScenarioFixture => "scenario-fixture",
            Self::RunEvidence => "run-evidence",
        }
    }

    pub const fn all() -> &'static [Self] {
        FORMAL_DIGEST_KINDS
    }
}

impl fmt::Display for DigestKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// Complete formal digest-kind registry.
pub const FORMAL_DIGEST_KINDS: &[DigestKind] = &[
    DigestKind::Row,
    DigestKind::RawContent,
    DigestKind::CollectionItem,
    DigestKind::VectorSet,
    DigestKind::TableSchema,
    DigestKind::ScenarioInput,
    DigestKind::ScenarioFixture,
    DigestKind::RunEvidence,
];

/// Wire digest reference: `sha256:` + 64 lowercase hex characters.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct DigestRef {
    value: String,
}

impl DigestRef {
    pub fn parse(value: impl Into<String>) -> Result<Self, TypeConstructionError> {
        let value = value.into();
        if !value.starts_with(DIGEST_REF_PREFIX) {
            return Err(TypeConstructionError::new(
                "DigestRef must start with sha256:",
            ));
        }
        let hex = &value[DIGEST_REF_PREFIX.len()..];
        if hex.len() != SHA256_HEX_LEN {
            return Err(TypeConstructionError::new(
                "DigestRef must be sha256: + 64 lowercase hex characters",
            ));
        }
        if !hex.bytes().all(is_lowercase_hex) {
            return Err(TypeConstructionError::new(
                "DigestRef hex must be lowercase [0-9a-f]",
            ));
        }
        Ok(Self { value })
    }

    pub fn from_raw_digest(raw_digest: &[u8]) -> Result<Self, TypeConstructionError> {
        if raw_digest.len() != RAW_DIGEST_LEN {
            return Err(TypeConstructionError::new(
                "raw digest must be exactly 32 bytes",
            ));
        }
        let mut value = String::with_capacity(DIGEST_REF_PREFIX.len() + SHA256_HEX_LEN);
        value.push_str(DIGEST_REF_PREFIX);
        for byte in raw_digest {
            value.push(HEX_LOWER[(byte >> 4) as usize]);
            value.push(HEX_LOWER[(byte & 0x0f) as usize]);
        }
        Ok(Self { value })
    }

    pub fn as_str(&self) -> &str {
        &self.value
    }

    pub fn raw_digest(&self) -> Result<[u8; RAW_DIGEST_LEN], TypeConstructionError> {
        let hex = &self.value[DIGEST_REF_PREFIX.len()..];
        let mut out = [0u8; RAW_DIGEST_LEN];
        for (index, chunk) in hex.as_bytes().chunks(2).enumerate() {
            let high = match chunk.first().copied().and_then(hex_nibble) {
                Some(value) => value,
                None => {
                    return Err(TypeConstructionError::new("DigestRef hex is invalid"));
                }
            };
            let low = match chunk.get(1).copied().and_then(hex_nibble) {
                Some(value) => value,
                None => {
                    return Err(TypeConstructionError::new("DigestRef hex is invalid"));
                }
            };
            out[index] = (high << 4) | low;
        }
        Ok(out)
    }
}

impl fmt::Display for DigestRef {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.value)
    }
}

/// Domain-separated semantic digest result.
///
/// Fields are private so `raw_digest` and `digest_ref` stay consistent; construct
/// only via [`SemanticDigest::from_raw`] / [`SemanticDigest::try_new`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SemanticDigest {
    kind: DigestKind,
    raw_digest: [u8; RAW_DIGEST_LEN],
    digest_ref: DigestRef,
}

impl SemanticDigest {
    pub fn from_raw(
        kind: DigestKind,
        raw_digest: [u8; RAW_DIGEST_LEN],
    ) -> Result<Self, TypeConstructionError> {
        let digest_ref = DigestRef::from_raw_digest(&raw_digest)?;
        Ok(Self {
            kind,
            raw_digest,
            digest_ref,
        })
    }

    pub fn try_new(
        kind: DigestKind,
        raw_digest: [u8; RAW_DIGEST_LEN],
        digest_ref: DigestRef,
    ) -> Result<Self, TypeConstructionError> {
        let expected = DigestRef::from_raw_digest(&raw_digest)?;
        if digest_ref != expected {
            return Err(TypeConstructionError::new(
                "digest_ref must match raw_digest",
            ));
        }
        Ok(Self {
            kind,
            raw_digest,
            digest_ref,
        })
    }

    pub fn kind(&self) -> DigestKind {
        self.kind
    }

    pub fn raw_digest(&self) -> &[u8; RAW_DIGEST_LEN] {
        &self.raw_digest
    }

    pub fn digest_ref(&self) -> &DigestRef {
        &self.digest_ref
    }
}

/// One row field prior to canonical identifier ordering and framing.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RowField {
    pub name: String,
    pub declared_type: DeclaredType,
    pub typed_value: TypedScalar,
}

/// Canonical row frame plus row semantic digest.
///
/// Fields are private so `raw_hash` and `digest_ref` stay consistent; construct
/// only via [`EncodedRow::try_new`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EncodedRow {
    row_frame: Vec<u8>,
    raw_hash: [u8; RAW_DIGEST_LEN],
    digest_ref: DigestRef,
}

impl EncodedRow {
    pub fn try_new(
        row_frame: Vec<u8>,
        raw_hash: [u8; RAW_DIGEST_LEN],
        digest_ref: DigestRef,
    ) -> Result<Self, TypeConstructionError> {
        let expected = DigestRef::from_raw_digest(&raw_hash)?;
        if digest_ref != expected {
            return Err(TypeConstructionError::new("digest_ref must match raw_hash"));
        }
        Ok(Self {
            row_frame,
            raw_hash,
            digest_ref,
        })
    }

    pub fn row_frame(&self) -> &[u8] {
        &self.row_frame
    }

    pub fn raw_hash(&self) -> &[u8; RAW_DIGEST_LEN] {
        &self.raw_hash
    }

    pub fn digest_ref(&self) -> &DigestRef {
        &self.digest_ref
    }
}

/// Closed collection semantics registry.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum CollectionSemantics {
    Sequence,
    Multiset,
    Set,
    KeyedCollection,
}

impl CollectionSemantics {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Sequence => "sequence",
            Self::Multiset => "multiset",
            Self::Set => "set",
            Self::KeyedCollection => "keyed-collection",
        }
    }

    pub const fn all() -> &'static [Self] {
        FORMAL_COLLECTION_SEMANTICS
    }
}

impl fmt::Display for CollectionSemantics {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// Complete formal collection-semantics registry.
pub const FORMAL_COLLECTION_SEMANTICS: &[CollectionSemantics] = &[
    CollectionSemantics::Sequence,
    CollectionSemantics::Multiset,
    CollectionSemantics::Set,
    CollectionSemantics::KeyedCollection,
];

/// Canonical collection frame only (no owner digest attached).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EncodedCollection {
    pub collection_frame: Vec<u8>,
}

const HEX_LOWER: &[char] = &[
    '0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c', 'd', 'e', 'f',
];

fn is_lowercase_hex(byte: u8) -> bool {
    byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)
}

fn hex_nibble(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::{
        CollectionSemantics, DeclaredType, DigestKind, DigestRef, EncodedCollection, EncodedRow,
        FORMAL_COLLECTION_SEMANTICS, FORMAL_DIGEST_KINDS, NullScalar, RowField, SemanticDigest,
        TypedScalar,
    };
    use std::collections::BTreeSet;

    #[test]
    fn digest_kind_registry_matches_formal_contract() {
        let actual: BTreeSet<&str> = FORMAL_DIGEST_KINDS.iter().map(|k| k.as_str()).collect();
        let expected: BTreeSet<&str> = [
            "row",
            "raw-content",
            "collection-item",
            "vector-set",
            "table-schema",
            "scenario-input",
            "scenario-fixture",
            "run-evidence",
        ]
        .into_iter()
        .collect();
        assert_eq!(actual, expected);
        assert_eq!(DigestKind::all().len(), expected.len());
    }

    #[test]
    fn collection_semantics_registry_matches_formal_contract() {
        let actual: BTreeSet<&str> = FORMAL_COLLECTION_SEMANTICS
            .iter()
            .map(|item| item.as_str())
            .collect();
        let expected: BTreeSet<&str> = ["sequence", "multiset", "set", "keyed-collection"]
            .into_iter()
            .collect();
        assert_eq!(actual, expected);
        assert_eq!(CollectionSemantics::all().len(), expected.len());
    }

    #[test]
    fn digest_ref_from_raw_and_rejects_invalid() -> Result<(), String> {
        let mut raw = [0u8; 32];
        for (index, slot) in raw.iter_mut().enumerate() {
            *slot = index as u8;
        }
        let ref_value = DigestRef::from_raw_digest(&raw)
            .map_err(|error| format!("from_raw_digest must succeed: {error}"))?;
        assert!(ref_value.as_str().starts_with("sha256:"));
        let decoded = ref_value
            .raw_digest()
            .map_err(|error| format!("raw_digest must round-trip: {error}"))?;
        assert_eq!(decoded, raw);

        assert!(DigestRef::from_raw_digest(b"short").is_err());
        assert!(DigestRef::parse(format!("sha256:{}", "0".repeat(63))).is_err());
        assert!(DigestRef::parse(format!("sha256:{}", "A".repeat(64))).is_err());
        Ok(())
    }

    #[test]
    fn semantic_digest_and_encoded_row_consistency() -> Result<(), String> {
        let raw = [1u8; 32];
        let digest = SemanticDigest::from_raw(DigestKind::Row, raw)
            .map_err(|error| format!("SemanticDigest::from_raw must succeed: {error}"))?;
        assert_eq!(digest.kind(), DigestKind::Row);
        assert_eq!(digest.raw_digest(), &raw);
        let decoded = digest
            .digest_ref()
            .raw_digest()
            .map_err(|error| format!("digest_ref must decode: {error}"))?;
        assert_eq!(decoded, raw);

        let row = EncodedRow::try_new(vec![0], raw, digest.digest_ref().clone())
            .map_err(|error| format!("EncodedRow::try_new must succeed: {error}"))?;
        assert_eq!(row.row_frame(), &[0]);
        assert_eq!(row.raw_hash(), &raw);
        assert_eq!(row.digest_ref().as_str(), digest.digest_ref().as_str());

        let other_ref = DigestRef::from_raw_digest(&[2u8; 32])
            .map_err(|error| format!("other DigestRef must construct: {error}"))?;
        assert!(SemanticDigest::try_new(DigestKind::Row, raw, other_ref.clone()).is_err());
        assert!(EncodedRow::try_new(vec![0], raw, other_ref).is_err());
        Ok(())
    }

    #[test]
    fn row_field_and_encoded_collection_shape() {
        let field = RowField {
            name: "Id".to_string(),
            declared_type: DeclaredType::Null,
            typed_value: TypedScalar::Null(NullScalar),
        };
        assert_eq!(field.name, "Id");

        let encoded = EncodedCollection {
            collection_frame: vec![0],
        };
        assert_eq!(encoded.collection_frame, vec![0]);
    }
}
