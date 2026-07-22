use std::collections::{BTreeMap, HashMap, HashSet};

use arrow_schema::{DataType, Field, Schema, TimeUnit};

use gateway_shared_kernel::DeclaredType;

use crate::errors::{ComputeFailure, ComputeFailureCode};
use crate::request::{DeclaredSchemaField, canonical_field_name};

const EXTENSION_NAME_KEY: &str = "ARROW:extension:name";
const EXTENSION_METADATA_KEY: &str = "ARROW:extension:metadata";

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SchemaFailureKind {
    Unsupported,
    Mismatch,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SchemaFailure {
    pub kind: SchemaFailureKind,
}

impl SchemaFailure {
    pub fn into_compute_failure(self) -> ComputeFailure {
        ComputeFailure::new(match self.kind {
            SchemaFailureKind::Unsupported => ComputeFailureCode::ArrowTypeUnsupported,
            SchemaFailureKind::Mismatch => ComputeFailureCode::ArrowSchemaMismatch,
        })
    }
}

pub fn cross_check_stream_schema(
    declared_fields: &[DeclaredSchemaField],
    stream_schema: &Schema,
) -> Result<(), ComputeFailure> {
    scan_schema_rejections(stream_schema)?;

    let mut declared_by_name: BTreeMap<String, &DeclaredSchemaField> = BTreeMap::new();
    for field in declared_fields {
        let canonical = canonical_field_name(field)?;
        if declared_by_name.insert(canonical.clone(), field).is_some() {
            return Err(ComputeFailure::new(
                ComputeFailureCode::CanonicalValueInvalid,
            ));
        }
    }

    if stream_schema.fields().len() != declared_by_name.len() {
        return Err(ComputeFailure::new(ComputeFailureCode::ArrowSchemaMismatch));
    }

    let mut matched = HashSet::new();
    for arrow_field in stream_schema.fields() {
        let canonical = canonical_field_name(&DeclaredSchemaField {
            name: arrow_field.name().clone(),
            nullable: arrow_field.is_nullable(),
            declared_type: DeclaredType::null(),
        })?;
        let Some(declared) = declared_by_name.get(&canonical) else {
            return Err(ComputeFailure::new(ComputeFailureCode::ArrowSchemaMismatch));
        };
        match_declared_to_arrow(declared, arrow_field)?;
        matched.insert(canonical);
    }

    if matched.len() != declared_by_name.len() {
        return Err(ComputeFailure::new(ComputeFailureCode::ArrowSchemaMismatch));
    }
    Ok(())
}

pub fn match_declared_to_arrow(
    declared: &DeclaredSchemaField,
    arrow_field: &Field,
) -> Result<(), ComputeFailure> {
    if has_extension_metadata(arrow_field.metadata()) {
        return Err(ComputeFailure::new(
            ComputeFailureCode::ArrowTypeUnsupported,
        ));
    }
    if arrow_field.is_nullable() != declared.nullable {
        return Err(ComputeFailure::new(ComputeFailureCode::ArrowSchemaMismatch));
    }
    match check_mapping(declared, arrow_field.data_type()) {
        Ok(()) => Ok(()),
        Err(failure) => Err(failure.into_compute_failure()),
    }
}

fn scan_schema_rejections(schema: &Schema) -> Result<(), ComputeFailure> {
    if has_extension_metadata(schema.metadata()) {
        return Err(ComputeFailure::new(
            ComputeFailureCode::ArrowTypeUnsupported,
        ));
    }
    for field in schema.fields() {
        if has_extension_metadata(field.metadata()) {
            return Err(ComputeFailure::new(
                ComputeFailureCode::ArrowTypeUnsupported,
            ));
        }
        if is_rejected_type(field.data_type()) {
            return Err(ComputeFailure::new(
                ComputeFailureCode::ArrowTypeUnsupported,
            ));
        }
    }
    Ok(())
}

fn has_extension_metadata(metadata: &HashMap<String, String>) -> bool {
    metadata.contains_key(EXTENSION_NAME_KEY) || metadata.contains_key(EXTENSION_METADATA_KEY)
}

fn check_mapping(
    declared: &DeclaredSchemaField,
    data_type: &DataType,
) -> Result<(), SchemaFailure> {
    if is_rejected_type(data_type) {
        return Err(SchemaFailure {
            kind: SchemaFailureKind::Unsupported,
        });
    }
    let matches = match (&declared.declared_type, data_type) {
        (DeclaredType::Null, DataType::Null) => declared.nullable,
        (DeclaredType::Boolean, DataType::Boolean) => true,
        (DeclaredType::SignedInteger { bits: 8 }, DataType::Int8) => true,
        (DeclaredType::SignedInteger { bits: 16 }, DataType::Int16) => true,
        (DeclaredType::SignedInteger { bits: 24 }, DataType::Int32) => true,
        (DeclaredType::SignedInteger { bits: 32 }, DataType::Int32) => true,
        (DeclaredType::SignedInteger { bits: 64 }, DataType::Int64) => true,
        (DeclaredType::UnsignedInteger { bits: 8 }, DataType::UInt8) => true,
        (DeclaredType::UnsignedInteger { bits: 16 }, DataType::UInt16) => true,
        (DeclaredType::UnsignedInteger { bits: 24 }, DataType::UInt32) => true,
        (DeclaredType::UnsignedInteger { bits: 32 }, DataType::UInt32) => true,
        (DeclaredType::UnsignedInteger { bits: 64 }, DataType::UInt64) => true,
        (
            DeclaredType::Decimal { precision, scale },
            DataType::Decimal128(arrow_precision, arrow_scale),
        ) => {
            *precision <= 38
                && *precision == *arrow_precision
                && i32::from(*scale) == i32::from(*arrow_scale)
        }
        (
            DeclaredType::Decimal { precision, scale },
            DataType::Decimal256(arrow_precision, arrow_scale),
        ) => {
            *precision >= 39
                && *precision == *arrow_precision
                && i32::from(*scale) == i32::from(*arrow_scale)
        }
        (DeclaredType::Float32, DataType::Float32) => true,
        (DeclaredType::Float64, DataType::Float64) => true,
        (DeclaredType::String, DataType::Utf8) => true,
        (DeclaredType::Binary, DataType::Binary) => true,
        (DeclaredType::Bit { .. }, DataType::Binary) => true,
        (DeclaredType::Date, DataType::Date32) => true,
        (DeclaredType::DateTime, DataType::Timestamp(unit, None)) => *unit == TimeUnit::Microsecond,
        (DeclaredType::Timestamp, DataType::Timestamp(unit, Some(tz))) => {
            *unit == TimeUnit::Microsecond && tz.as_ref() == "UTC"
        }
        (DeclaredType::TimeDuration, DataType::Duration(unit)) => *unit == TimeUnit::Microsecond,
        (DeclaredType::SourceLiteralAnomaly, DataType::Binary) => true,
        (DeclaredType::Null, _) | (_, DataType::Null) => false,
        _ => false,
    };
    if matches {
        Ok(())
    } else if is_rejected_type(data_type) {
        Err(SchemaFailure {
            kind: SchemaFailureKind::Unsupported,
        })
    } else {
        Err(SchemaFailure {
            kind: SchemaFailureKind::Mismatch,
        })
    }
}

pub fn is_rejected_type(data_type: &DataType) -> bool {
    match data_type {
        DataType::LargeUtf8 | DataType::LargeBinary => true,
        DataType::Utf8View | DataType::BinaryView => true,
        DataType::Dictionary(_, _)
        | DataType::Union(_, _)
        | DataType::List(_)
        | DataType::LargeList(_)
        | DataType::ListView(_)
        | DataType::LargeListView(_)
        | DataType::FixedSizeList(_, _)
        | DataType::Struct(_)
        | DataType::Map(_, _) => true,
        DataType::Timestamp(unit, tz) => {
            *unit != TimeUnit::Microsecond
                || tz
                    .as_ref()
                    .is_some_and(|timezone| timezone.as_ref() != "UTC")
        }
        DataType::Duration(unit) => *unit != TimeUnit::Microsecond,
        DataType::Date64 => true,
        DataType::Time32(_) | DataType::Time64(_) | DataType::Interval(_) => true,
        DataType::RunEndEncoded(_, _) => true,
        _ => false,
    }
}

pub fn schemas_equal(left: &Schema, right: &Schema) -> bool {
    left.fields().len() == right.fields().len()
        && metadata_equal(left.metadata(), right.metadata())
        && left
            .fields()
            .iter()
            .zip(right.fields())
            .all(|(left_field, right_field)| fields_equal(left_field, right_field))
}

fn metadata_equal(left: &HashMap<String, String>, right: &HashMap<String, String>) -> bool {
    left == right
}

fn fields_equal(left: &Field, right: &Field) -> bool {
    left.name() == right.name()
        && left.is_nullable() == right.is_nullable()
        && left.data_type() == right.data_type()
        && metadata_equal(left.metadata(), right.metadata())
}
