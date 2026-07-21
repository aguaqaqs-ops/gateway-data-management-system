//! Fixed paths and identifiers for canonical-encoding vector sets (test-only).

use std::path::PathBuf;

/// JSONL file order required by the vector-set manifest.
pub const JSONL_FILES: &[&str] = &["digest.jsonl", "invalid.jsonl", "jcs.jsonl", "scalar.jsonl"];

/// Formal schema files loaded into the Draft 2020-12 registry (must match Python).
pub const SCHEMA_FILES: &[&str] = &[
    "definitions.schema.json",
    "vector-set.schema.json",
    "jcs-case.schema.json",
    "scalar-case.schema.json",
    "digest-case.schema.json",
    "invalid-case.schema.json",
];

/// Case schema id for each JSONL path (must match manifest `case_schema_id`).
pub fn case_schema_id_for_path(path: &str) -> Option<&'static str> {
    match path {
        "digest.jsonl" => Some("gateway-vnext.canonical-encoding.digest-case.v1"),
        "invalid.jsonl" => Some("gateway-vnext.canonical-encoding.invalid-case.v1"),
        "jcs.jsonl" => Some("gateway-vnext.canonical-encoding.jcs-case.v1"),
        "scalar.jsonl" => Some("gateway-vnext.canonical-encoding.scalar-case.v1"),
        _ => None,
    }
}

/// Map case schema id to on-disk schema file name.
pub const CASE_SCHEMA_FILE_BY_ID: &[(&str, &str)] = &[
    (
        "gateway-vnext.canonical-encoding.digest-case.v1",
        "digest-case.schema.json",
    ),
    (
        "gateway-vnext.canonical-encoding.invalid-case.v1",
        "invalid-case.schema.json",
    ),
    (
        "gateway-vnext.canonical-encoding.jcs-case.v1",
        "jcs-case.schema.json",
    ),
    (
        "gateway-vnext.canonical-encoding.scalar-case.v1",
        "scalar-case.schema.json",
    ),
];

/// Candidate marker written by the Python generator (not normative root).
pub const CANDIDATE_MARKER_NAME: &str = "CANDIDATE_PENDING_WP2_CONFIRMATION";

/// Formal JSON Schema root for canonical-encoding vectors.
pub fn schema_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/schemas/shared-kernel/canonical-encoding/v1")
}

/// Fixed normative vector root published in the repository (WP2 R6).
pub fn normative_vector_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/vectors/shared-kernel/canonical-encoding/v1")
}
