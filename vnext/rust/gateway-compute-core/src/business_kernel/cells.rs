//! Borrowed Arrow cells and the existing business row preimage.

use arrow_array::{
    Array, BinaryArray, BooleanArray, Float32Array, Float64Array, Int64Array, LargeBinaryArray,
    LargeStringArray, StringArray, UInt64Array,
};
use arrow_schema::DataType;
use gateway_shared_kernel::{
    BinaryScalar, BitScalar, BooleanScalar, CollectionSemantics, DateScalar, DateTimeScalar,
    DecimalScalar, DeclaredType, DigestKind, Float32Scalar, Float64Scalar, NullScalar,
    SignedIntegerScalar, StringScalar, TimeDurationScalar, TimestampScalar, TypedScalar,
    UnsignedIntegerScalar, encode_collection, encode_typed_scalar, encode_uleb128, semantic_digest,
};

use super::{BusinessKernelError, BusinessKernelErrorKind, ColumnDescriptor};
use crate::table_access::SqlLogicalType;

pub(super) fn value_error(message: impl Into<String>) -> BusinessKernelError {
    BusinessKernelError::new(BusinessKernelErrorKind::Value, message)
}

pub(super) fn encoding_error(error: impl std::fmt::Display) -> BusinessKernelError {
    value_error(error.to_string())
}

#[derive(Debug, Clone, Copy)]
pub(super) enum Cell<'a> {
    Null,
    Int(i64),
    UInt(u64),
    Bool(bool),
    F32(f32),
    F64(f64),
    Text(&'a str),
    Binary(&'a [u8]),
}

impl Cell<'_> {
    pub(super) fn scratch_bytes(self, column: &ColumnDescriptor) -> Option<usize> {
        let payload = match self {
            Self::Text(text) => text.len(),
            Self::Binary(bytes) => bytes.len(),
            _ => 32,
        };
        // Includes typed-value, shared encoder payload/frame/preimage copies,
        // SET item vectors and collection copies, with Vec growth slack.
        payload
            .checked_mul(16)?
            .checked_add(
                column
                    .labels
                    .as_ref()
                    .map_or(Some(0), |labels| labels.len().checked_mul(256))?,
            )?
            .checked_add(1024)
    }
}

pub(super) fn accepts(column: &ColumnDescriptor, actual: &DataType) -> bool {
    use DeclaredType as D;
    let string = matches!(actual, DataType::Utf8 | DataType::LargeUtf8);
    match column.logical_type {
        SqlLogicalType::Enum
        | SqlLogicalType::Set
        | SqlLogicalType::Json
        | SqlLogicalType::Unknown => string,
        SqlLogicalType::Standard => match column.declared_type.as_ref() {
            Some(D::SignedInteger { .. }) => *actual == DataType::Int64,
            Some(D::UnsignedInteger { .. }) => *actual == DataType::UInt64,
            Some(D::Boolean) => *actual == DataType::Boolean,
            Some(D::Float32) => *actual == DataType::Float32,
            Some(D::Float64) => *actual == DataType::Float64,
            Some(D::Binary | D::Bit { .. }) => {
                matches!(actual, DataType::Binary | DataType::LargeBinary)
            }
            Some(D::Null) => *actual == DataType::Null,
            Some(_) => string,
            None => false,
        },
    }
}

pub(super) fn read(array: &dyn Array, row: usize) -> Result<Cell<'_>, BusinessKernelError> {
    if array.is_null(row) {
        return Ok(Cell::Null);
    }
    let any = array.as_any();
    macro_rules! primitive {
        ($ty:ty, $variant:ident) => {
            if let Some(values) = any.downcast_ref::<$ty>() {
                return Ok(Cell::$variant(values.value(row)));
            }
        };
    }
    primitive!(Int64Array, Int);
    primitive!(UInt64Array, UInt);
    primitive!(BooleanArray, Bool);
    primitive!(Float32Array, F32);
    primitive!(Float64Array, F64);
    primitive!(StringArray, Text);
    primitive!(LargeStringArray, Text);
    primitive!(BinaryArray, Binary);
    primitive!(LargeBinaryArray, Binary);
    Err(value_error("unsupported Arrow cell type"))
}

pub(super) fn integer(cell: Cell<'_>) -> Option<i128> {
    match cell {
        Cell::Int(value) => Some(i128::from(value)),
        Cell::UInt(value) => Some(i128::from(value)),
        _ => None,
    }
}

pub(super) fn set_members<'a>(
    text: &'a str,
    column: &'a ColumnDescriptor,
) -> Result<Vec<&'a str>, BusinessKernelError> {
    let labels = column
        .labels
        .as_ref()
        .ok_or_else(|| value_error("SET declaration has no labels"))?;
    if text.is_empty() {
        return Ok(Vec::new());
    }
    let members: Vec<&str> = text.split(',').collect();
    for (index, member) in members.iter().enumerate() {
        if !labels.iter().any(|label| label == member) || members[..index].contains(member) {
            return Err(value_error(
                "SET contains an undeclared or duplicate member",
            ));
        }
    }
    Ok(labels
        .iter()
        .filter(|label| members.contains(&label.as_str()))
        .map(String::as_str)
        .collect())
}

pub(super) fn frame(
    column: &ColumnDescriptor,
    cell: Cell<'_>,
) -> Result<Vec<u8>, BusinessKernelError> {
    use DeclaredType as D;
    if matches!(cell, Cell::Null) {
        return encode_typed_scalar(&D::Null, &TypedScalar::Null(NullScalar))
            .map(|encoded| encoded.scalar_frame)
            .map_err(encoding_error);
    }
    if column.logical_type == SqlLogicalType::Set {
        let Cell::Text(text) = cell else {
            return Err(value_error("SET cell must be text"));
        };
        let members = set_members(text, column)?;
        let frames = members
            .iter()
            .map(|member| {
                encode_typed_scalar(
                    &D::String,
                    &TypedScalar::String(StringScalar {
                        text: (*member).to_owned(),
                    }),
                )
                .map(|encoded| encoded.scalar_frame)
                .map_err(encoding_error)
            })
            .collect::<Result<Vec<_>, _>>()?;
        let slices: Vec<&[u8]> = frames.iter().map(Vec::as_slice).collect();
        return encode_collection(CollectionSemantics::Sequence, Some(&slices), None)
            .map(|encoded| encoded.collection_frame)
            .map_err(encoding_error);
    }
    let declared = column
        .declared_type
        .as_ref()
        .ok_or_else(|| value_error("non-null cell has no declared type"))?;
    let typed = match (declared, cell) {
        (D::SignedInteger { .. }, Cell::Int(value)) => {
            TypedScalar::SignedInteger(SignedIntegerScalar {
                decimal: value.to_string(),
            })
        }
        (D::UnsignedInteger { .. }, Cell::UInt(value)) => {
            TypedScalar::UnsignedInteger(UnsignedIntegerScalar {
                decimal: value.to_string(),
            })
        }
        (D::UnsignedInteger { .. }, Cell::Int(value)) if value >= 0 => {
            TypedScalar::UnsignedInteger(UnsignedIntegerScalar {
                decimal: value.to_string(),
            })
        }
        (D::Boolean, Cell::Bool(value)) => TypedScalar::Boolean(BooleanScalar { value }),
        (D::Float32, Cell::F32(value)) => TypedScalar::Float32(Float32Scalar {
            bits_hex: format!("{:08x}", if value == 0.0 { 0 } else { value.to_bits() }),
        }),
        (D::Float64, Cell::F64(value)) => TypedScalar::Float64(Float64Scalar {
            bits_hex: format!("{:016x}", if value == 0.0 { 0 } else { value.to_bits() }),
        }),
        (D::String, Cell::Text(text)) => {
            if column.logical_type == SqlLogicalType::Enum
                && !column
                    .labels
                    .as_ref()
                    .is_some_and(|labels| labels.iter().any(|label| label == text))
            {
                return Err(value_error("ENUM value is not a declared label"));
            }
            TypedScalar::String(StringScalar {
                text: text.to_owned(),
            })
        }
        (D::Decimal { .. }, Cell::Text(text)) => TypedScalar::Decimal(DecimalScalar {
            decimal: text.to_owned(),
        }),
        (D::Date, Cell::Text(text)) => TypedScalar::Date(DateScalar {
            text: text.to_owned(),
        }),
        (D::DateTime, Cell::Text(text)) => TypedScalar::DateTime(DateTimeScalar {
            text: text.to_owned(),
        }),
        (D::Timestamp, Cell::Text(text)) => TypedScalar::Timestamp(TimestampScalar {
            text: text.to_owned(),
        }),
        (D::TimeDuration, Cell::Text(text)) => TypedScalar::TimeDuration(TimeDurationScalar {
            text: text.to_owned(),
        }),
        (D::Binary, Cell::Binary(bytes)) => TypedScalar::Binary(BinaryScalar {
            raw_bytes: bytes.to_vec(),
        }),
        (D::Bit { .. }, Cell::Binary(bytes)) => TypedScalar::Bit(BitScalar {
            raw_bytes: bytes.to_vec(),
        }),
        _ => {
            return Err(value_error(
                "Arrow value does not match declared scalar type",
            ));
        }
    };
    encode_typed_scalar(declared, &typed)
        .map(|encoded| encoded.scalar_frame)
        .map_err(encoding_error)
}

pub(super) fn row_hash(
    columns: &[ColumnDescriptor],
    cells: &[Cell<'_>],
) -> Result<[u8; 32], BusinessKernelError> {
    let mut order: Vec<usize> = (0..columns.len()).collect();
    order.sort_unstable_by(|left, right| {
        columns[*left]
            .canonical_name
            .as_bytes()
            .cmp(columns[*right].canonical_name.as_bytes())
    });
    let mut row = encode_uleb128(columns.len() as u64).map_err(encoding_error)?;
    for index in order {
        let name = columns[index].canonical_name.as_bytes();
        row.extend(encode_uleb128(name.len() as u64).map_err(encoding_error)?);
        row.extend_from_slice(name);
        row.extend(frame(&columns[index], cells[index])?);
    }
    semantic_digest(DigestKind::Row, &row)
        .map(|digest| *digest.raw_digest())
        .map_err(encoding_error)
}
