//! Canonical row and collection framing.

use std::collections::HashMap;

use crate::digest::semantic_digest;
use crate::errors::{CanonicalEncodingError, CanonicalErrorCode};
use crate::identifier::canonicalize_identifier;
use crate::scalar::encode_typed_scalar;
use crate::types::{CollectionSemantics, DigestKind, EncodedCollection, EncodedRow, RowField};
use crate::uleb128::encode_uleb128;

/// Encode a row: sort by CanonicalIdentifier UTF-8 bytes, then frame + digest.
pub fn encode_row(fields: &[RowField]) -> Result<EncodedRow, CanonicalEncodingError> {
    let mut prepared: Vec<(Vec<u8>, &RowField)> = Vec::with_capacity(fields.len());
    let mut seen: HashMap<Vec<u8>, &str> = HashMap::with_capacity(fields.len());

    for field in fields {
        let canonical = canonicalize_identifier(&field.name)?;
        let name_utf8 = canonical.into_bytes();
        if let Some(prior) = seen.get(&name_utf8) {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::IdentifierCollision,
                format!(
                    "canonical identifier collision between {prior:?} and {}",
                    field.name
                ),
            ));
        }
        seen.insert(name_utf8.clone(), &field.name);
        prepared.push((name_utf8, field));
    }

    prepared.sort_by(|left, right| left.0.cmp(&right.0));

    let mut parts = encode_uleb128(prepared.len() as u64)?;
    for (name_utf8, field) in &prepared {
        let encoded = encode_typed_scalar(&field.declared_type, &field.typed_value)?;
        parts.extend(encode_uleb128(name_utf8.len() as u64)?);
        parts.extend_from_slice(name_utf8);
        parts.extend_from_slice(&encoded.scalar_frame);
    }

    let row_frame = parts;
    let digest = semantic_digest(DigestKind::Row, &row_frame)?;
    let raw_hash = *digest.raw_digest();
    EncodedRow::try_new(row_frame, raw_hash, digest.digest_ref().clone()).map_err(|error| {
        CanonicalEncodingError::with_message(CanonicalErrorCode::TypeMismatch, error.to_string())
    })
}

/// Encode a collection under explicit [`CollectionSemantics`] (no host-type guessing).
pub fn encode_collection(
    semantics: CollectionSemantics,
    items: Option<&[&[u8]]>,
    entries: Option<&[(&[u8], &[u8])]>,
) -> Result<EncodedCollection, CanonicalEncodingError> {
    let frame = match semantics {
        CollectionSemantics::KeyedCollection => {
            if items.is_some() || entries.is_none() {
                return Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::TypeMismatch,
                    "keyed-collection requires entries and rejects items",
                ));
            }
            encode_keyed_collection(entries.unwrap_or(&[]))?
        }
        CollectionSemantics::Sequence => {
            if entries.is_some() || items.is_none() {
                return Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::TypeMismatch,
                    format!("{} requires items and rejects entries", semantics.as_str()),
                ));
            }
            encode_sequence(items.unwrap_or(&[]))?
        }
        CollectionSemantics::Multiset => {
            if entries.is_some() || items.is_none() {
                return Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::TypeMismatch,
                    format!("{} requires items and rejects entries", semantics.as_str()),
                ));
            }
            encode_hash_collection(items.unwrap_or(&[]), true)?
        }
        CollectionSemantics::Set => {
            if entries.is_some() || items.is_none() {
                return Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::TypeMismatch,
                    format!("{} requires items and rejects entries", semantics.as_str()),
                ));
            }
            encode_hash_collection(items.unwrap_or(&[]), false)?
        }
    };

    Ok(EncodedCollection {
        collection_frame: frame,
    })
}

fn encode_sequence(items: &[&[u8]]) -> Result<Vec<u8>, CanonicalEncodingError> {
    let mut parts = encode_uleb128(items.len() as u64)?;
    for item in items {
        parts.extend(framed_item(item)?);
    }
    Ok(parts)
}

fn encode_hash_collection(
    items: &[&[u8]],
    allow_duplicates: bool,
) -> Result<Vec<u8>, CanonicalEncodingError> {
    let mut hashes: Vec<[u8; 32]> = Vec::with_capacity(items.len());
    for item in items {
        hashes.push(item_hash(item)?);
    }

    hashes.sort();

    if !allow_duplicates {
        for index in 1..hashes.len() {
            if hashes[index] == hashes[index - 1] {
                return Err(CanonicalEncodingError::with_message(
                    CanonicalErrorCode::CollectionDuplicateItem,
                    "set collection rejects duplicate item hashes",
                ));
            }
        }
    }

    let mut parts = encode_uleb128(hashes.len() as u64)?;
    for item_hash in hashes {
        parts.extend_from_slice(&item_hash);
    }
    Ok(parts)
}

fn encode_keyed_collection(entries: &[(&[u8], &[u8])]) -> Result<Vec<u8>, CanonicalEncodingError> {
    let mut prepared: Vec<(&[u8], &[u8])> = Vec::with_capacity(entries.len());
    let mut seen: HashMap<&[u8], ()> = HashMap::with_capacity(entries.len());

    for (key, value) in entries {
        if seen.contains_key(key) {
            return Err(CanonicalEncodingError::with_message(
                CanonicalErrorCode::CollectionDuplicateKey,
                "keyed-collection rejects duplicate keys",
            ));
        }
        seen.insert(key, ());
        prepared.push((key, value));
    }

    prepared.sort_by(|left, right| left.0.cmp(right.0));

    let mut parts = encode_uleb128(prepared.len() as u64)?;
    for (key, value) in prepared {
        parts.extend(encode_uleb128(key.len() as u64)?);
        parts.extend_from_slice(key);
        parts.extend(encode_uleb128(value.len() as u64)?);
        parts.extend_from_slice(value);
    }
    Ok(parts)
}

fn framed_item(item_bytes: &[u8]) -> Result<Vec<u8>, CanonicalEncodingError> {
    let mut out = encode_uleb128(item_bytes.len() as u64)?;
    out.extend_from_slice(item_bytes);
    Ok(out)
}

fn item_hash(item_bytes: &[u8]) -> Result<[u8; 32], CanonicalEncodingError> {
    let framed = framed_item(item_bytes)?;
    let digest = semantic_digest(DigestKind::CollectionItem, &framed)?;
    Ok(*digest.raw_digest())
}

#[cfg(test)]
mod tests {
    use super::encode_collection;
    use super::encode_row;
    use crate::base64url::encode_base64url;
    use crate::digest::semantic_digest;
    use crate::errors::CanonicalErrorCode;
    use crate::types::{
        BooleanScalar, CollectionSemantics, DeclaredType, DigestKind, NullScalar, RowField,
        TypedScalar,
    };

    fn null_field(name: &str) -> RowField {
        RowField {
            name: name.to_string(),
            declared_type: DeclaredType::Null,
            typed_value: TypedScalar::Null(NullScalar),
        }
    }

    #[test]
    fn empty_row_matches_oracle() -> Result<(), String> {
        let encoded = encode_row(&[]).map_err(|error| error.to_string())?;
        assert_eq!(encode_base64url(encoded.row_frame()), "AA");
        assert_eq!(
            encoded.digest_ref().as_str(),
            "sha256:9ab0cece6f9aea3ad4cb0f7932709eb1482978069a4182cb7a7b43c9917c580e"
        );
        Ok(())
    }

    #[test]
    fn mixed_fields_permutation_invariant() -> Result<(), String> {
        let fields_a = vec![
            null_field("b"),
            RowField {
                name: "A".to_string(),
                declared_type: DeclaredType::Boolean,
                typed_value: TypedScalar::Boolean(BooleanScalar { value: true }),
            },
        ];
        let fields_b = vec![
            RowField {
                name: "A".to_string(),
                declared_type: DeclaredType::Boolean,
                typed_value: TypedScalar::Boolean(BooleanScalar { value: true }),
            },
            null_field("b"),
        ];

        let encoded_a = encode_row(&fields_a).map_err(|error| error.to_string())?;
        let encoded_b = encode_row(&fields_b).map_err(|error| error.to_string())?;
        assert_eq!(encode_base64url(encoded_a.row_frame()), "AgFhAQEBAWIAAA");
        assert_eq!(encoded_a.row_frame(), encoded_b.row_frame());
        assert_eq!(
            encoded_a.digest_ref().as_str(),
            encoded_b.digest_ref().as_str()
        );
        assert_eq!(
            encoded_a.digest_ref().as_str(),
            "sha256:401578531a0add4dd48daa932190b0f1fff21f90cd2378a112c32199b1a80f39"
        );
        Ok(())
    }

    #[test]
    fn identifier_collision_rejected() -> Result<(), String> {
        let fields = vec![null_field("Id"), null_field("id")];
        match encode_row(&fields) {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::IdentifierCollision);
                Ok(())
            }
            Ok(_) => Err("collision must fail".to_string()),
        }
    }

    #[test]
    fn semantic_digest_independent_of_encode_row() -> Result<(), String> {
        let encoded = encode_row(&[]).map_err(|error| error.to_string())?;
        let digest = semantic_digest(DigestKind::Row, encoded.row_frame())
            .map_err(|error| error.to_string())?;
        assert_eq!(digest.digest_ref().as_str(), encoded.digest_ref().as_str());
        Ok(())
    }

    #[test]
    fn sequence_collection_matches_oracle() -> Result<(), String> {
        let encoded = encode_collection(
            CollectionSemantics::Sequence,
            Some(&[b"a".as_slice(), b"b".as_slice()]),
            None,
        )
        .map_err(|error| error.to_string())?;
        assert_eq!(
            encode_base64url(&encoded.collection_frame),
            encode_base64url(&[0x02, 0x01, b'a', 0x01, b'b'])
        );
        Ok(())
    }

    #[test]
    fn multiset_collection_matches_oracle() -> Result<(), String> {
        let encoded = encode_collection(
            CollectionSemantics::Multiset,
            Some(&[b"b".as_slice(), b"a".as_slice(), b"a".as_slice()]),
            None,
        )
        .map_err(|error| error.to_string())?;
        assert_eq!(
            encode_base64url(&encoded.collection_frame),
            "Ax-6jgb-9LreOpPbRA97OCZfiqNRnJZKA-qTJj6Wz-yJH7qOBv70ut46k9tED3s4Jl-Ko1GclkoD6pMmPpbP7IkrUM3CxNUSxLQRWMLQOYWwVKETkIy2G6QbNrcnb5f5IQ"
        );
        Ok(())
    }

    #[test]
    fn set_collection_matches_oracle() -> Result<(), String> {
        let encoded = encode_collection(
            CollectionSemantics::Set,
            Some(&[b"c".as_slice(), b"a".as_slice(), b"b".as_slice()]),
            None,
        )
        .map_err(|error| error.to_string())?;
        assert_eq!(
            encode_base64url(&encoded.collection_frame),
            "Ax-6jgb-9LreOpPbRA97OCZfiqNRnJZKA-qTJj6Wz-yJK1DNwsTVEsS0EVjC0DmFsFShE5CMthukGza3J2-X-SHM-y40po7FLde--h51jMtpmh4iVjgthp_GvWtH5KlL9A"
        );
        Ok(())
    }

    #[test]
    fn keyed_collection_matches_oracle() -> Result<(), String> {
        let encoded = encode_collection(
            CollectionSemantics::KeyedCollection,
            None,
            Some(&[
                (b"b".as_slice(), b"2".as_slice()),
                (b"a".as_slice(), b"1".as_slice()),
            ]),
        )
        .map_err(|error| error.to_string())?;
        assert_eq!(encode_base64url(&encoded.collection_frame), "AgFhATEBYgEy");
        Ok(())
    }

    #[test]
    fn set_duplicate_item_rejected() -> Result<(), String> {
        match encode_collection(
            CollectionSemantics::Set,
            Some(&[b"a".as_slice(), b"a".as_slice()]),
            None,
        ) {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::CollectionDuplicateItem);
                Ok(())
            }
            Ok(_) => Err("duplicate set item must fail".to_string()),
        }
    }

    #[test]
    fn keyed_duplicate_key_rejected() -> Result<(), String> {
        match encode_collection(
            CollectionSemantics::KeyedCollection,
            None,
            Some(&[
                (b"k".as_slice(), b"1".as_slice()),
                (b"k".as_slice(), b"2".as_slice()),
            ]),
        ) {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::CollectionDuplicateKey);
                Ok(())
            }
            Ok(_) => Err("duplicate keyed key must fail".to_string()),
        }
    }

    #[test]
    fn keyed_collection_rejects_items() -> Result<(), String> {
        match encode_collection(
            CollectionSemantics::KeyedCollection,
            Some(&[b"a".as_slice()]),
            Some(&[(b"a".as_slice(), b"1".as_slice())]),
        ) {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::TypeMismatch);
                Ok(())
            }
            Ok(_) => Err("keyed-collection with items must fail".to_string()),
        }
    }

    #[test]
    fn sequence_rejects_entries() -> Result<(), String> {
        match encode_collection(
            CollectionSemantics::Sequence,
            Some(&[b"a".as_slice()]),
            Some(&[(b"a".as_slice(), b"1".as_slice())]),
        ) {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::TypeMismatch);
                Ok(())
            }
            Ok(_) => Err("sequence with entries must fail".to_string()),
        }
    }

    #[test]
    fn multiset_permutation_invariant() -> Result<(), String> {
        let items = [b"b".as_slice(), b"a".as_slice(), b"a".as_slice()];
        let reversed = [b"a".as_slice(), b"a".as_slice(), b"b".as_slice()];
        let base = encode_collection(CollectionSemantics::Multiset, Some(&items), None)
            .map_err(|error| error.to_string())?;
        let permuted = encode_collection(CollectionSemantics::Multiset, Some(&reversed), None)
            .map_err(|error| error.to_string())?;
        assert_eq!(base.collection_frame, permuted.collection_frame);
        Ok(())
    }

    #[test]
    fn keyed_permutation_invariant() -> Result<(), String> {
        let entries = [
            (b"b".as_slice(), b"2".as_slice()),
            (b"a".as_slice(), b"1".as_slice()),
        ];
        let reversed = [
            (b"a".as_slice(), b"1".as_slice()),
            (b"b".as_slice(), b"2".as_slice()),
        ];
        let base = encode_collection(CollectionSemantics::KeyedCollection, None, Some(&entries))
            .map_err(|error| error.to_string())?;
        let permuted =
            encode_collection(CollectionSemantics::KeyedCollection, None, Some(&reversed))
                .map_err(|error| error.to_string())?;
        assert_eq!(base.collection_frame, permuted.collection_frame);
        Ok(())
    }

    #[test]
    fn encoded_collection_has_no_digest_field() {
        let encoded = encode_collection(
            CollectionSemantics::Sequence,
            Some(&[b"a".as_slice()]),
            None,
        );
        assert!(encoded.is_ok());
    }
}
