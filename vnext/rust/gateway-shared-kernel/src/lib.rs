#![forbid(unsafe_code)]

//! Independent Shared Canonical Encoding production surface.
//!
//! R1 exposes closed registries and typed API shapes only. Encoding functions
//! are intentionally not exported until their review nodes land.

mod errors;
mod types;

pub use errors::{CanonicalEncodingError, CanonicalErrorCode, FORMAL_STABLE_ERROR_CODES};
pub use types::{
    AnomalyScalar, BinaryScalar, BitScalar, BooleanScalar, CollectionSemantics, DateScalar,
    DateTimeScalar, DecimalScalar, DeclaredType, DigestKind, DigestRef, EncodedCollection,
    EncodedRow, EncodedScalar, FORMAL_COLLECTION_SEMANTICS, FORMAL_DIGEST_KINDS, Float32Scalar,
    Float64Scalar, LogicalLiteral, NormalizedScalar, NullScalar, RawLogicalLiteral, RowField,
    SemanticDigest, SignedIntegerScalar, StringScalar, TimeDurationScalar, TimestampScalar,
    TypeConstructionError, TypedScalar, UnsignedIntegerScalar, Utf8LogicalLiteral,
};
