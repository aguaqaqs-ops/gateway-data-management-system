use std::collections::HashSet;

use gateway_shared_kernel::{
    DeclaredType, SemanticDigest, canonicalize_identifier, canonicalize_jcs,
};
use serde_json::{Map, Value};

use crate::contract::{
    ARROW_MAPPING_SCHEMA_VERSION, CANONICAL_ENCODING_VERSION, CONTRACT_ID, REQUEST_SCHEMA_VERSION,
    SEMANTIC_VERSION,
};
use crate::errors::{ComputeFailure, ComputeFailureCode};
use crate::schema_digest::table_schema_digest;

#[derive(Debug, Clone)]
pub struct DeclaredSchemaField {
    pub name: String,
    pub nullable: bool,
    pub declared_type: DeclaredType,
}

#[derive(Debug, Clone)]
pub struct ParsedRequest {
    fields: Vec<DeclaredSchemaField>,
    table_schema_digest: SemanticDigest,
}

impl ParsedRequest {
    pub fn fields(&self) -> &[DeclaredSchemaField] {
        &self.fields
    }

    pub fn table_schema_digest(&self) -> &SemanticDigest {
        &self.table_schema_digest
    }

    pub(crate) fn validate_digest_binding(&self) -> Result<(), ComputeFailure> {
        let expected = table_schema_digest(&self.fields)?;
        if expected != self.table_schema_digest {
            return Err(ComputeFailure::new(
                ComputeFailureCode::ComputeRequestSchemaInvalid,
            ));
        }
        Ok(())
    }
}

pub fn parse_request(request_jcs: &[u8]) -> Result<ParsedRequest, ComputeFailure> {
    let canonical = canonicalize_jcs(request_jcs)
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::ComputeRequestSchemaInvalid))?;
    let root: Value = serde_json::from_slice(&canonical)
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::ComputeRequestSchemaInvalid))?;
    let object = root
        .as_object()
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::ComputeRequestSchemaInvalid))?;
    validate_closed_object(
        object,
        &[
            "request_schema_version",
            "contract_binding",
            "canonical_encoding_version",
            "arrow_mapping_schema_version",
            "declared_table_schema",
        ],
    )?;

    let request_schema_version = required_u32(object, "request_schema_version")?;
    if request_schema_version != REQUEST_SCHEMA_VERSION {
        return Err(ComputeFailure::new(
            ComputeFailureCode::ComputeRequestSchemaInvalid,
        ));
    }

    validate_contract_binding(required_object(object, "contract_binding")?)?;

    let canonical_encoding_version = required_u32(object, "canonical_encoding_version")?;
    if canonical_encoding_version != CANONICAL_ENCODING_VERSION {
        return Err(ComputeFailure::new(
            ComputeFailureCode::ComputeCanonicalVersionUnsupported,
        ));
    }

    let arrow_mapping_schema_version = required_u32(object, "arrow_mapping_schema_version")?;
    if arrow_mapping_schema_version != ARROW_MAPPING_SCHEMA_VERSION {
        return Err(ComputeFailure::new(
            ComputeFailureCode::ComputeArrowMappingVersionUnsupported,
        ));
    }

    let declared_table_schema = required_object(object, "declared_table_schema")?;
    validate_closed_object(declared_table_schema, &["fields"])?;
    let fields_value = required_array(declared_table_schema, "fields")?;
    let mut fields = Vec::with_capacity(fields_value.len());
    for field_value in fields_value {
        let field_object = field_value
            .as_object()
            .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::ComputeRequestSchemaInvalid))?;
        validate_closed_object(field_object, &["name", "nullable", "semantic_type"])?;
        let name = required_string(field_object, "name")?;
        let nullable = required_bool(field_object, "nullable")?;
        let semantic_type = required_object(field_object, "semantic_type")?;
        let declared_type = parse_declared_type(semantic_type)?;
        fields.push(DeclaredSchemaField {
            name,
            nullable,
            declared_type,
        });
    }

    check_canonical_name_collisions(&fields)?;

    let table_schema_digest = table_schema_digest(&fields)?;
    Ok(ParsedRequest {
        fields,
        table_schema_digest,
    })
}

pub fn canonical_field_name(field: &DeclaredSchemaField) -> Result<String, ComputeFailure> {
    canonicalize_identifier(&field.name)
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))
}

pub(crate) fn check_canonical_name_collisions(
    fields: &[DeclaredSchemaField],
) -> Result<(), ComputeFailure> {
    let mut seen = HashSet::new();
    for field in fields {
        let canonical = canonical_field_name(field)?;
        if !seen.insert(canonical) {
            return Err(ComputeFailure::new(
                ComputeFailureCode::CanonicalValueInvalid,
            ));
        }
    }
    Ok(())
}

fn validate_contract_binding(object: &Map<String, Value>) -> Result<(), ComputeFailure> {
    validate_closed_object(object, &["contract_id", "semantic_version"])?;
    let contract_id = required_string(object, "contract_id")?;
    let semantic_version = required_string(object, "semantic_version")?;
    if contract_id != CONTRACT_ID {
        return Err(ComputeFailure::new(
            ComputeFailureCode::ComputeContractVersionUnsupported,
        ));
    }
    if semantic_version != SEMANTIC_VERSION {
        return Err(ComputeFailure::new(
            ComputeFailureCode::ComputeContractVersionUnsupported,
        ));
    }
    Ok(())
}

fn parse_declared_type(object: &Map<String, Value>) -> Result<DeclaredType, ComputeFailure> {
    validate_closed_object(object, declared_type_keys(object)?)?;
    let kind = required_string(object, "kind")?;
    let declared = match kind.as_str() {
        "null" => DeclaredType::null(),
        "boolean" => DeclaredType::boolean(),
        "signed-integer" => DeclaredType::signed_integer(required_u8(object, "bits")?)
            .map_err(|_| ComputeFailure::new(ComputeFailureCode::ComputeRequestSchemaInvalid))?,
        "unsigned-integer" => DeclaredType::unsigned_integer(required_u8(object, "bits")?)
            .map_err(|_| ComputeFailure::new(ComputeFailureCode::ComputeRequestSchemaInvalid))?,
        "decimal" => DeclaredType::decimal(
            required_u8(object, "precision")?,
            required_u8(object, "scale")?,
        )
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::ComputeRequestSchemaInvalid))?,
        "float32" => DeclaredType::float32(),
        "float64" => DeclaredType::float64(),
        "string" => DeclaredType::string(),
        "binary" => DeclaredType::binary(),
        "bit" => DeclaredType::bit(required_u8(object, "bit_width")?)
            .map_err(|_| ComputeFailure::new(ComputeFailureCode::ComputeRequestSchemaInvalid))?,
        "date" => DeclaredType::date(),
        "datetime" => DeclaredType::datetime(),
        "timestamp" => DeclaredType::timestamp(),
        "time-duration" => DeclaredType::time_duration(),
        "source-literal-anomaly" => DeclaredType::source_literal_anomaly(),
        _ => {
            return Err(ComputeFailure::new(
                ComputeFailureCode::ComputeRequestSchemaInvalid,
            ));
        }
    };
    declared
        .validate()
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::ComputeRequestSchemaInvalid))?;
    Ok(declared)
}

fn declared_type_keys(object: &Map<String, Value>) -> Result<&[&str], ComputeFailure> {
    let kind = required_string(object, "kind")?;
    Ok(match kind.as_str() {
        "null"
        | "boolean"
        | "float32"
        | "float64"
        | "string"
        | "binary"
        | "date"
        | "datetime"
        | "timestamp"
        | "time-duration"
        | "source-literal-anomaly" => &["kind"],
        "signed-integer" | "unsigned-integer" => &["kind", "bits"],
        "decimal" => &["kind", "precision", "scale"],
        "bit" => &["kind", "bit_width"],
        _ => {
            return Err(ComputeFailure::new(
                ComputeFailureCode::ComputeRequestSchemaInvalid,
            ));
        }
    })
}

fn validate_closed_object(
    object: &Map<String, Value>,
    allowed: &[&str],
) -> Result<(), ComputeFailure> {
    for key in object.keys() {
        if !allowed.contains(&key.as_str()) {
            return Err(ComputeFailure::new(
                ComputeFailureCode::ComputeRequestSchemaInvalid,
            ));
        }
    }
    for key in allowed {
        if !object.contains_key(*key) {
            return Err(ComputeFailure::new(
                ComputeFailureCode::ComputeRequestSchemaInvalid,
            ));
        }
    }
    Ok(())
}

fn required_object<'a>(
    object: &'a Map<String, Value>,
    key: &str,
) -> Result<&'a Map<String, Value>, ComputeFailure> {
    object
        .get(key)
        .and_then(Value::as_object)
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::ComputeRequestSchemaInvalid))
}

fn required_array<'a>(
    object: &'a Map<String, Value>,
    key: &str,
) -> Result<&'a Vec<Value>, ComputeFailure> {
    object
        .get(key)
        .and_then(Value::as_array)
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::ComputeRequestSchemaInvalid))
}

fn required_string(object: &Map<String, Value>, key: &str) -> Result<String, ComputeFailure> {
    object
        .get(key)
        .and_then(Value::as_str)
        .map(str::to_string)
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::ComputeRequestSchemaInvalid))
}

fn required_bool(object: &Map<String, Value>, key: &str) -> Result<bool, ComputeFailure> {
    object
        .get(key)
        .and_then(Value::as_bool)
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::ComputeRequestSchemaInvalid))
}

fn required_u32(object: &Map<String, Value>, key: &str) -> Result<u32, ComputeFailure> {
    object
        .get(key)
        .and_then(Value::as_u64)
        .and_then(|value| u32::try_from(value).ok())
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::ComputeRequestSchemaInvalid))
}

fn required_u8(object: &Map<String, Value>, key: &str) -> Result<u8, ComputeFailure> {
    object
        .get(key)
        .and_then(Value::as_u64)
        .and_then(|value| u8::try_from(value).ok())
        .ok_or_else(|| ComputeFailure::new(ComputeFailureCode::ComputeRequestSchemaInvalid))
}

#[cfg(test)]
#[allow(clippy::assertions_on_constants)]
mod tests {
    use super::*;
    use gateway_shared_kernel::{DeclaredType, DigestKind, semantic_digest};

    #[test]
    fn canonical_collision_rejected() {
        let fields = vec![
            DeclaredSchemaField {
                name: "A".to_string(),
                nullable: false,
                declared_type: DeclaredType::boolean(),
            },
            DeclaredSchemaField {
                name: "a".to_string(),
                nullable: false,
                declared_type: DeclaredType::boolean(),
            },
        ];
        match table_schema_digest(&fields) {
            Err(error) => assert_eq!(error.code, ComputeFailureCode::CanonicalValueInvalid),
            Ok(_) => assert!(false, "collision must be rejected"),
        }
    }

    #[test]
    fn validate_digest_binding_rejects_stale_digest() {
        let fields = vec![DeclaredSchemaField {
            name: "v".to_string(),
            nullable: false,
            declared_type: DeclaredType::boolean(),
        }];
        let stale = match semantic_digest(DigestKind::TableSchema, b"stale") {
            Ok(digest) => digest,
            Err(error) => {
                assert!(false, "digest construction failed: {error:?}");
                return;
            }
        };
        let request = ParsedRequest {
            fields,
            table_schema_digest: stale,
        };
        match request.validate_digest_binding() {
            Err(error) => {
                assert_eq!(error.code, ComputeFailureCode::ComputeRequestSchemaInvalid)
            }
            Ok(()) => assert!(false, "stale digest must be rejected"),
        }
    }
}
