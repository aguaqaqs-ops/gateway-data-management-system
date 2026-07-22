use gateway_shared_kernel::{
    CanonicalEncodingError, DeclaredType, DigestKind, SemanticDigest, canonicalize_identifier,
    canonicalize_jcs, semantic_digest,
};

use crate::errors::{ComputeFailure, ComputeFailureCode};
use crate::request::DeclaredSchemaField;

pub fn table_schema_digest(
    fields: &[DeclaredSchemaField],
) -> Result<SemanticDigest, ComputeFailure> {
    crate::request::check_canonical_name_collisions(fields)?;

    let mut projected: Vec<ProjectedField> = Vec::with_capacity(fields.len());
    for field in fields {
        let canonical_name = canonicalize_identifier(&field.name)
            .map_err(|_| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))?;
        projected.push(ProjectedField {
            name: canonical_name,
            nullable: field.nullable,
            semantic_type: field.declared_type.clone(),
        });
    }
    projected.sort_by(|left, right| left.name.cmp(&right.name));

    let payload = serde_json::json!({
        "fields": projected.iter().map(|field| serde_json::json!({
            "name": field.name,
            "nullable": field.nullable,
            "semantic_type": semantic_type_json(&field.semantic_type),
        })).collect::<Vec<_>>()
    });
    let payload_bytes = serde_json::to_vec(&payload)
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed))?;
    let canonical_payload = canonicalize_jcs(&payload_bytes)
        .map_err(|_| ComputeFailure::new(ComputeFailureCode::CanonicalValueInvalid))?;
    semantic_digest(DigestKind::TableSchema, &canonical_payload).map_err(map_digest_error)
}

fn map_digest_error(_error: CanonicalEncodingError) -> ComputeFailure {
    ComputeFailure::new(ComputeFailureCode::RowHashComputeFailed)
}

fn semantic_type_json(declared_type: &DeclaredType) -> serde_json::Value {
    match declared_type {
        DeclaredType::Null => serde_json::json!({ "kind": "null" }),
        DeclaredType::Boolean => serde_json::json!({ "kind": "boolean" }),
        DeclaredType::SignedInteger { bits } => {
            serde_json::json!({ "kind": "signed-integer", "bits": bits })
        }
        DeclaredType::UnsignedInteger { bits } => {
            serde_json::json!({ "kind": "unsigned-integer", "bits": bits })
        }
        DeclaredType::Decimal { precision, scale } => serde_json::json!({
            "kind": "decimal",
            "precision": precision,
            "scale": scale,
        }),
        DeclaredType::Float32 => serde_json::json!({ "kind": "float32" }),
        DeclaredType::Float64 => serde_json::json!({ "kind": "float64" }),
        DeclaredType::String => serde_json::json!({ "kind": "string" }),
        DeclaredType::Binary => serde_json::json!({ "kind": "binary" }),
        DeclaredType::Bit { bit_width } => {
            serde_json::json!({ "kind": "bit", "bit_width": bit_width })
        }
        DeclaredType::Date => serde_json::json!({ "kind": "date" }),
        DeclaredType::DateTime => serde_json::json!({ "kind": "datetime" }),
        DeclaredType::Timestamp => serde_json::json!({ "kind": "timestamp" }),
        DeclaredType::TimeDuration => serde_json::json!({ "kind": "time-duration" }),
        DeclaredType::SourceLiteralAnomaly => {
            serde_json::json!({ "kind": "source-literal-anomaly" })
        }
    }
}

#[derive(Debug, Clone)]
struct ProjectedField {
    name: String,
    nullable: bool,
    semantic_type: DeclaredType,
}
