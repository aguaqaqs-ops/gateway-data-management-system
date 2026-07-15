#![forbid(unsafe_code)]

use thiserror::Error;

#[derive(Debug, Error, PartialEq, Eq)]
pub enum ComputeError {
    #[error("integer overflow while doubling value")]
    IntegerOverflow,
}

pub fn double_nullable_i64(values: &[Option<i64>]) -> Result<Vec<Option<i64>>, ComputeError> {
    values
        .iter()
        .map(|value| {
            value
                .map(|number| number.checked_mul(2).ok_or(ComputeError::IntegerOverflow))
                .transpose()
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::double_nullable_i64;

    #[test]
    fn doubles_values_and_preserves_nulls() {
        assert_eq!(
            double_nullable_i64(&[Some(2), None, Some(-3)]),
            Ok(vec![Some(4), None, Some(-6)])
        );
    }
}
