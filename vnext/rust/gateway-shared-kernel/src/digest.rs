//! Semantic and raw-blob digest helpers.

use sha2::{Digest, Sha256};

use crate::errors::{CanonicalEncodingError, CanonicalErrorCode};
use crate::types::{DigestKind, DigestRef, SemanticDigest};

const DOMAIN_PREFIX: &[u8] = b"gateway-vnext:";
const DOMAIN_SUFFIX: &[u8] = b":v1\0";

fn domain_prefix(kind: DigestKind) -> Vec<u8> {
    let kind_str = kind.as_str();
    let mut out = Vec::with_capacity(DOMAIN_PREFIX.len() + kind_str.len() + DOMAIN_SUFFIX.len());
    out.extend_from_slice(DOMAIN_PREFIX);
    out.extend_from_slice(kind_str.as_bytes());
    out.extend_from_slice(DOMAIN_SUFFIX);
    out
}

fn digest_ref_from_sha256(raw_digest: [u8; 32]) -> Result<DigestRef, CanonicalEncodingError> {
    DigestRef::from_raw_digest(&raw_digest).map_err(|error| {
        CanonicalEncodingError::with_message(CanonicalErrorCode::TypeMismatch, error.to_string())
    })
}

/// Domain-separated SHA-256 over `gateway-vnext:<kind>:v1\0 || payload`.
pub fn semantic_digest(
    kind: DigestKind,
    payload: &[u8],
) -> Result<SemanticDigest, CanonicalEncodingError> {
    let mut preimage = domain_prefix(kind);
    preimage.extend_from_slice(payload);
    let raw_digest: [u8; 32] = Sha256::digest(&preimage).into();
    SemanticDigest::from_raw(kind, raw_digest).map_err(|error| {
        CanonicalEncodingError::with_message(CanonicalErrorCode::TypeMismatch, error.to_string())
    })
}

/// Direct SHA-256 of raw bytes with no semantic domain prefix.
pub fn raw_blob_digest(raw: &[u8]) -> Result<DigestRef, CanonicalEncodingError> {
    let raw_digest: [u8; 32] = Sha256::digest(raw).into();
    digest_ref_from_sha256(raw_digest)
}

#[cfg(test)]
mod tests {
    use super::{domain_prefix, raw_blob_digest, semantic_digest};
    use crate::base64url::encode_base64url;
    use crate::types::{DigestKind, FORMAL_DIGEST_KINDS};

    const EMPTY_ROW_FRAME: &[u8] = &[0x00];

    #[test]
    fn domain_prefix_matches_formal_contract() {
        for kind in FORMAL_DIGEST_KINDS {
            let prefix = domain_prefix(*kind);
            let expected = format!("gateway-vnext:{}:v1\0", kind.as_str());
            assert_eq!(prefix, expected.as_bytes());
        }
    }

    #[test]
    fn semantic_digest_empty_row_frame_matches_oracle() -> Result<(), String> {
        let digest =
            semantic_digest(DigestKind::Row, EMPTY_ROW_FRAME).map_err(|error| error.to_string())?;
        assert_eq!(
            digest.digest_ref().as_str(),
            "sha256:9ab0cece6f9aea3ad4cb0f7932709eb1482978069a4182cb7a7b43c9917c580e"
        );
        Ok(())
    }

    #[test]
    fn raw_blob_digest_matches_oracle() -> Result<(), String> {
        let digest = raw_blob_digest(b"payload").map_err(|error| error.to_string())?;
        assert_eq!(
            digest.as_str(),
            "sha256:239f59ed55e737c77147cf55ad0c1b030b6d7ee748a7426952f9b852d5a935e5"
        );
        Ok(())
    }

    #[test]
    fn digest_domain_separation() -> Result<(), String> {
        use sha2::{Digest, Sha256};

        let payload = b"same-payload";
        let mut digests = Vec::new();
        for kind in FORMAL_DIGEST_KINDS {
            let digest = semantic_digest(*kind, payload).map_err(|error| error.to_string())?;
            digests.push(*digest.raw_digest());
        }
        for index in 0..digests.len() {
            for other in index + 1..digests.len() {
                assert_ne!(digests[index], digests[other]);
            }
        }

        let raw = raw_blob_digest(payload).map_err(|error| error.to_string())?;
        let raw_content =
            semantic_digest(DigestKind::RawContent, payload).map_err(|error| error.to_string())?;
        let raw_bytes = raw.raw_digest().map_err(|error| error.to_string())?;
        assert_ne!(&raw_bytes, raw_content.raw_digest());
        assert_eq!(
            encode_base64url(&raw_bytes),
            encode_base64url(Sha256::digest(payload).as_slice())
        );
        Ok(())
    }
}
