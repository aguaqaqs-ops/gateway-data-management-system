#![forbid(unsafe_code)]

//! Independent Shared Canonical Encoding production surface.

mod base64url;
mod errors;
mod identifier;
mod jcs;
mod scalar;
mod types;
mod uleb128;
mod unicode;

pub use errors::{CanonicalEncodingError, CanonicalErrorCode, FORMAL_STABLE_ERROR_CODES};
pub use identifier::canonicalize_identifier;
pub use jcs::canonicalize_jcs;
pub use scalar::{encode_typed_scalar, normalize_logical_literal};
pub use types::{
    AnomalyScalar, BinaryScalar, BitScalar, BooleanScalar, CollectionSemantics, DateScalar,
    DateTimeScalar, DecimalScalar, DeclaredType, DigestKind, DigestRef, EncodedCollection,
    EncodedRow, EncodedScalar, FORMAL_COLLECTION_SEMANTICS, FORMAL_DIGEST_KINDS, Float32Scalar,
    Float64Scalar, LogicalLiteral, NormalizedScalar, NullScalar, RawLogicalLiteral, RowField,
    SemanticDigest, SignedIntegerScalar, StringScalar, TimeDurationScalar, TimestampScalar,
    TypeConstructionError, TypedScalar, UnsignedIntegerScalar, Utf8LogicalLiteral,
};
