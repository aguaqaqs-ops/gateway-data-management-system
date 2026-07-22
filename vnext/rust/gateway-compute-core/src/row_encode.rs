use gateway_shared_kernel::{DeclaredType, EncodedRow, RowField, TypedScalar, encode_row};

use crate::errors::ComputeFailure;

/// Encode a row for compute, adapting nullable null slots to kernel `DeclaredType::Null`
/// for encoding only. Original declared types remain on the input fields for schema digest.
pub fn encode_row_for_compute(fields: &[RowField]) -> Result<EncodedRow, ComputeFailure> {
    let adapted: Vec<RowField> = fields.iter().map(adapt_field_for_encoding).collect();
    encode_row(&adapted).map_err(Into::into)
}

fn adapt_field_for_encoding(field: &RowField) -> RowField {
    let encoding_declared_type = if is_nullable_null_slot(field) {
        DeclaredType::null()
    } else {
        field.declared_type.clone()
    };
    RowField {
        name: field.name.clone(),
        declared_type: encoding_declared_type,
        typed_value: field.typed_value.clone(),
    }
}

fn is_nullable_null_slot(field: &RowField) -> bool {
    matches!(field.typed_value, TypedScalar::Null(_))
        && !matches!(field.declared_type, DeclaredType::Null)
}

#[cfg(test)]
mod tests {
    use gateway_shared_kernel::{
        BooleanScalar, DeclaredType, EncodedRow, NullScalar, RowField, StringScalar, TypedScalar,
        encode_row,
    };

    use super::encode_row_for_compute;

    fn assert_encoded_rows_equal(left: &EncodedRow, right: &EncodedRow) {
        assert_eq!(left.row_frame(), right.row_frame());
        assert_eq!(left.raw_hash(), right.raw_hash());
        assert_eq!(left.digest_ref(), right.digest_ref());
    }

    #[test]
    fn nullable_null_slot_matches_kernel_encode_row() -> Result<(), String> {
        let fields = vec![RowField {
            name: "flag".to_string(),
            declared_type: DeclaredType::boolean(),
            typed_value: TypedScalar::Null(NullScalar),
        }];
        let expected = encode_row(&[RowField {
            declared_type: DeclaredType::null(),
            ..fields[0].clone()
        }])
        .map_err(|error| error.to_string())?;
        let actual = encode_row_for_compute(&fields).map_err(|error| format!("{error:?}"))?;
        assert_encoded_rows_equal(&actual, &expected);
        Ok(())
    }

    #[test]
    fn non_null_row_matches_kernel_encode_row() -> Result<(), String> {
        let fields = vec![
            RowField {
                name: "a".to_string(),
                declared_type: DeclaredType::boolean(),
                typed_value: TypedScalar::Boolean(BooleanScalar { value: true }),
            },
            RowField {
                name: "z".to_string(),
                declared_type: DeclaredType::string(),
                typed_value: TypedScalar::String(StringScalar {
                    text: "x".to_string(),
                }),
            },
        ];
        let expected = encode_row(&fields).map_err(|error| error.to_string())?;
        let actual = encode_row_for_compute(&fields).map_err(|error| format!("{error:?}"))?;
        assert_encoded_rows_equal(&actual, &expected);
        Ok(())
    }
}
