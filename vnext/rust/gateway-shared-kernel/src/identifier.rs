//! CanonicalIdentifier ASCII fold.

use crate::errors::{CanonicalEncodingError, CanonicalErrorCode};
use crate::unicode::validate_unicode_string;

/// Fold ASCII A-Z to a-z; no trim and no Unicode case folding.
pub fn canonicalize_identifier(identifier: &str) -> Result<String, CanonicalEncodingError> {
    if identifier.is_empty() {
        return Err(CanonicalEncodingError::with_message(
            CanonicalErrorCode::IdentifierEmpty,
            "identifier must not be empty",
        ));
    }
    validate_unicode_string(identifier)?;
    Ok(identifier
        .chars()
        .map(|ch| ch.to_ascii_lowercase())
        .collect())
}

#[cfg(test)]
mod tests {
    use super::canonicalize_identifier;
    use crate::errors::CanonicalErrorCode;

    #[test]
    fn ascii_case_fold_only() -> Result<(), String> {
        let folded = canonicalize_identifier("AbC_1").map_err(|e| e.to_string())?;
        assert_eq!(folded, "abc_1");
        Ok(())
    }

    #[test]
    fn does_not_trim_or_unicode_fold() -> Result<(), String> {
        assert_eq!(
            canonicalize_identifier("  A").map_err(|e| e.to_string())?,
            "  a"
        );
        assert_eq!(
            canonicalize_identifier("Å").map_err(|e| e.to_string())?,
            "Å"
        );
        Ok(())
    }

    #[test]
    fn rejects_empty() -> Result<(), String> {
        match canonicalize_identifier("") {
            Err(error) => {
                assert_eq!(error.code(), CanonicalErrorCode::IdentifierEmpty);
                Ok(())
            }
            Ok(_) => Err("empty identifier must fail".to_string()),
        }
    }
}
