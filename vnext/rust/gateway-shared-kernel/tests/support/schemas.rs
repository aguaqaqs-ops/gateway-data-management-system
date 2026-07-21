//! JSON Schema Draft 2020-12 validation (test-only; mirrors Python `testing.schemas`).

use std::collections::HashMap;
use std::fs;
use std::path::Path;
use std::sync::OnceLock;

use jsonschema::{Registry, Validator};
use serde_json::Value;

use super::paths::{CASE_SCHEMA_FILE_BY_ID, SCHEMA_FILES, schema_root};

#[derive(Debug)]
pub struct SchemaValidationError {
    message: String,
}

impl std::fmt::Display for SchemaValidationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for SchemaValidationError {}

struct SchemaValidators {
    _registry: Registry<'static>,
    manifest: Validator,
    case_by_id: HashMap<&'static str, Validator>,
}

static VALIDATORS: OnceLock<Result<SchemaValidators, String>> = OnceLock::new();

fn schema_validation_error(message: impl Into<String>) -> SchemaValidationError {
    SchemaValidationError {
        message: message.into(),
    }
}

fn load_schema_document(path: &Path) -> Result<Value, SchemaValidationError> {
    let text = fs::read_to_string(path).map_err(|error| {
        schema_validation_error(format!("failed to read schema {}: {error}", path.display()))
    })?;
    serde_json::from_str(&text).map_err(|error| {
        schema_validation_error(format!(
            "failed to parse schema {}: {error}",
            path.display()
        ))
    })
}

fn build_registry() -> Result<Registry<'static>, SchemaValidationError> {
    let root = schema_root();
    let mut registry = Registry::new();
    for file_name in SCHEMA_FILES {
        let path = root.join(file_name);
        let document = load_schema_document(&path)?;
        let schema_id = document
            .get("$id")
            .and_then(Value::as_str)
            .ok_or_else(|| {
                schema_validation_error(format!("schema {} missing $id", path.display()))
            })?
            .to_string();
        registry = registry.add(&schema_id, document).map_err(|error| {
            schema_validation_error(format!("failed to register schema {schema_id}: {error}"))
        })?;
    }
    registry.prepare().map_err(|error| {
        schema_validation_error(format!("schema registry prepare failed: {error}"))
    })
}

fn build_validators() -> Result<SchemaValidators, SchemaValidationError> {
    let registry = build_registry()?;
    let options = jsonschema::options().with_registry(&registry);

    let manifest_schema = load_schema_document(&schema_root().join("vector-set.schema.json"))?;
    let manifest = options.build(&manifest_schema).map_err(|error| {
        schema_validation_error(format!("manifest schema compile failed: {error}"))
    })?;

    let mut case_by_id = HashMap::new();
    for &(case_schema_id, file_name) in CASE_SCHEMA_FILE_BY_ID {
        let schema = load_schema_document(&schema_root().join(file_name))?;
        let validator = options.build(&schema).map_err(|error| {
            schema_validation_error(format!(
                "case schema {case_schema_id} compile failed: {error}"
            ))
        })?;
        case_by_id.insert(case_schema_id, validator);
    }

    Ok(SchemaValidators {
        _registry: registry,
        manifest,
        case_by_id,
    })
}

fn validators() -> Result<&'static SchemaValidators, SchemaValidationError> {
    VALIDATORS
        .get_or_init(|| build_validators().map_err(|error| error.to_string()))
        .as_ref()
        .map_err(|message| schema_validation_error(message.clone()))
}

/// Validate `vector-set.json` against the formal manifest schema.
pub fn validate_vector_set_manifest(manifest: &Value) -> Result<(), SchemaValidationError> {
    let validators = validators()?;
    if let Err(error) = validators.manifest.validate(manifest) {
        return Err(schema_validation_error(format!(
            "vector-set.json schema validation failed: {error}"
        )));
    }
    Ok(())
}

/// Validate one case envelope against its file-specific schema.
pub fn validate_case_envelope(
    case_schema_id: &str,
    case: &Value,
) -> Result<(), SchemaValidationError> {
    let validators = validators()?;
    let validator = validators.case_by_id.get(case_schema_id).ok_or_else(|| {
        schema_validation_error(format!("unknown case_schema_id {case_schema_id:?}"))
    })?;
    if let Err(error) = validator.validate(case) {
        return Err(schema_validation_error(format!(
            "case schema validation failed for {case_schema_id}: {error}"
        )));
    }
    Ok(())
}
