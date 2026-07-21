//! Read-only vector-set closure validation (test-only; mirrors Python `testing.closure`).

use std::collections::BTreeSet;
use std::fmt;
use std::fs;
use std::io;
use std::path::Path;

use gateway_shared_kernel::{
    CanonicalEncodingError, DigestKind, canonicalize_jcs, raw_blob_digest, semantic_digest,
};
use serde_json::{Map, Value};

use super::dispatch::{DispatchMismatch, dispatch_case};
use super::fs_safety::{
    FsSafetyError, assert_no_symlink_ancestors, assert_regular_directory, assert_regular_file,
};
use super::paths::{JSONL_FILES, case_schema_id_for_path};
use super::schemas::{SchemaValidationError, validate_case_envelope, validate_vector_set_manifest};
use super::strict_json::{StrictJsonError, loads_object_rejecting_duplicates};

#[derive(Debug)]
pub struct ClosureValidationError {
    message: String,
}

impl std::fmt::Display for ClosureValidationError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for ClosureValidationError {}

/// Validate manifest, JSONL integrity, ordering, content digest, and optionally execute cases.
///
/// Per-file case order: parse line → strict JSON → schema validate → JCS → ordering/uniqueness.
pub fn validate_vector_set(
    root: &Path,
    execute_cases: bool,
) -> Result<Map<String, Value>, ClosureValidationError> {
    assert_no_symlink_ancestors(root, "vector root").map_err(closure_from_fs)?;
    assert_regular_directory(root, "vector root").map_err(closure_from_fs)?;

    if !root.exists() {
        return Err(closure_error(format!(
            "vector root does not exist: {}",
            root.display()
        )));
    }

    let manifest_path = root.join("vector-set.json");
    assert_regular_file(&manifest_path, "vector-set.json").map_err(closure_from_fs)?;

    let manifest_text = fs::read_to_string(&manifest_path)
        .map_err(|source| closure_error(format!("failed to read vector-set.json: {source}")))?;
    let manifest_map = loads_object_rejecting_duplicates(manifest_text.trim_end_matches('\n'))
        .map_err(closure_from_strict_json("vector-set.json"))?;
    let manifest_value = Value::Object(manifest_map.clone());
    validate_vector_set_manifest(&manifest_value).map_err(closure_from_schema)?;

    let files = manifest_map
        .get("files")
        .and_then(Value::as_array)
        .ok_or_else(|| closure_error("manifest files must be an array"))?;

    let mut all_cases: Vec<Value> = Vec::new();
    let mut seen_ids: BTreeSet<String> = BTreeSet::new();

    for (index, entry) in files.iter().enumerate() {
        let entry_obj = entry
            .as_object()
            .ok_or_else(|| closure_error(format!("files[{index}] must be an object")))?;
        let path_name = entry_string(entry_obj, "path")?;
        let case_schema_id = entry_string(entry_obj, "case_schema_id")?;
        let case_count = entry_u64(entry_obj, "case_count")?;
        let size_bytes = entry_u64(entry_obj, "size_bytes")?;
        let raw_sha256 = entry_string(entry_obj, "raw_sha256")?;

        let expected_schema = case_schema_id_for_path(path_name).ok_or_else(|| {
            closure_error(format!("unknown JSONL path in manifest: {path_name:?}"))
        })?;
        if expected_schema != case_schema_id {
            return Err(closure_error(format!(
                "case_schema_id mismatch for {path_name}: {case_schema_id}"
            )));
        }

        let file_path = root.join(path_name);
        assert_regular_file(&file_path, path_name).map_err(closure_from_fs)?;

        let raw = fs::read(&file_path)
            .map_err(|source| closure_error(format!("failed to read {path_name}: {source}")))?;
        let raw_len = u64::try_from(raw.len())
            .map_err(|_| closure_error(format!("{path_name} size exceeds u64 on this target")))?;
        if raw_len != size_bytes {
            return Err(closure_error(format!(
                "size_bytes mismatch for {path_name}"
            )));
        }
        let digest = raw_blob_digest(&raw).map_err(|error| {
            closure_error(format!("raw_blob_digest failed for {path_name}: {error}"))
        })?;
        if digest.as_str() != raw_sha256 {
            return Err(closure_error(format!(
                "raw_sha256 mismatch for {path_name}"
            )));
        }

        let cases = parse_and_validate_jsonl(&raw, path_name, case_schema_id)?;
        let case_count_usize = usize::try_from(case_count).map_err(|_| {
            closure_error(format!(
                "case_count for {path_name} exceeds usize on this target"
            ))
        })?;
        if cases.len() != case_count_usize {
            return Err(closure_error(format!(
                "case_count mismatch for {path_name}"
            )));
        }
        assert_sorted_unique_case_ids(&cases, path_name, &mut seen_ids)?;
        all_cases.extend(cases);
    }

    assert_file_order(files)?;
    assert_content_digest(&manifest_map)?;

    if execute_cases {
        for case in &all_cases {
            let case_id = case
                .get("case_id")
                .and_then(Value::as_str)
                .unwrap_or("<unknown>");
            if let Err(error) = dispatch_case(case) {
                return Err(closure_error(format!(
                    "case execution failed for {case_id:?}: {error}"
                )));
            }
        }
    }

    Ok(manifest_map)
}

fn assert_file_order(files: &[Value]) -> Result<(), ClosureValidationError> {
    let actual: Vec<&str> = files
        .iter()
        .map(|entry| {
            entry
                .as_object()
                .and_then(|obj| obj.get("path"))
                .and_then(Value::as_str)
                .ok_or_else(|| closure_error("files[].path must be a string"))
        })
        .collect::<Result<Vec<_>, _>>()?;
    if actual != JSONL_FILES {
        return Err(closure_error(
            "files[] path order must match fixed JSONL order",
        ));
    }
    Ok(())
}

fn parse_and_validate_jsonl(
    raw: &[u8],
    path_name: &str,
    case_schema_id: &str,
) -> Result<Vec<Value>, ClosureValidationError> {
    if raw.is_empty() {
        return Ok(Vec::new());
    }
    if !raw.ends_with(b"\n") {
        return Err(closure_error(format!("{path_name} must end with LF")));
    }
    let text = std::str::from_utf8(raw)
        .map_err(|error| closure_error(format!("{path_name} is not valid UTF-8: {error}")))?;
    if text.contains('\r') {
        return Err(closure_error(format!(
            "{path_name} must use LF line endings only"
        )));
    }

    let mut lines: Vec<&str> = text.split('\n').collect();
    if lines.last() == Some(&"") {
        lines.pop();
    }

    let mut cases = Vec::with_capacity(lines.len());
    for (index, line) in lines.iter().enumerate() {
        if line.is_empty() {
            return Err(closure_error(format!(
                "{path_name} contains empty line at {index}"
            )));
        }
        let object = loads_object_rejecting_duplicates(line).map_err(closure_from_strict_json(
            &format!("{path_name} line {index}"),
        ))?;
        let case_value = Value::Object(object);
        validate_case_envelope(case_schema_id, &case_value).map_err(|error| {
            closure_error(format!(
                "{path_name} line {index} schema validation failed: {error}"
            ))
        })?;
        let canonical = canonicalize_jcs(line.as_bytes()).map_err(|error| {
            closure_error(format!(
                "{path_name} line {index} is not JCS-canonical: {error}"
            ))
        })?;
        if canonical != line.as_bytes() {
            return Err(closure_error(format!(
                "{path_name} line {index} is not JCS-canonical"
            )));
        }
        cases.push(case_value);
    }
    Ok(cases)
}

fn assert_sorted_unique_case_ids(
    cases: &[Value],
    path_name: &str,
    seen_ids: &mut BTreeSet<String>,
) -> Result<(), ClosureValidationError> {
    let mut ids: Vec<String> = Vec::with_capacity(cases.len());
    for case in cases {
        let case_id = case
            .get("case_id")
            .and_then(Value::as_str)
            .ok_or_else(|| closure_error(format!("{path_name} case missing case_id")))?
            .to_string();
        ids.push(case_id);
    }
    let mut sorted = ids.clone();
    sorted.sort_by(|left, right| left.as_bytes().cmp(right.as_bytes()));
    if ids != sorted {
        return Err(closure_error(format!(
            "{path_name} case_id order is not ASCII-sorted"
        )));
    }
    for case_id in ids {
        if !seen_ids.insert(case_id.clone()) {
            return Err(closure_error(format!("duplicate case_id {case_id:?}")));
        }
    }
    Ok(())
}

fn assert_content_digest(manifest: &Map<String, Value>) -> Result<(), ClosureValidationError> {
    let declared = manifest
        .get("vector_set_content_digest")
        .and_then(Value::as_str)
        .ok_or_else(|| closure_error("vector_set_content_digest missing"))?;

    let mut projected = manifest.clone();
    projected.remove("vector_set_content_digest");
    let projected_value = Value::Object(projected);
    let projected_bytes = serde_json_canonicalizer::to_vec(&projected_value).map_err(|error| {
        closure_error(format!(
            "vector-set.json projected body canonicalization failed: {error}"
        ))
    })?;

    let digest = semantic_digest(DigestKind::VectorSet, &projected_bytes)
        .map_err(|error| closure_error(format!("semantic_digest(vector-set) failed: {error}")))?;
    if digest.digest_ref().as_str() != declared {
        return Err(closure_error("vector_set_content_digest mismatch"));
    }
    Ok(())
}

fn entry_string<'a>(
    obj: &'a Map<String, Value>,
    field: &str,
) -> Result<&'a str, ClosureValidationError> {
    obj.get(field)
        .and_then(Value::as_str)
        .ok_or_else(|| closure_error(format!("files entry missing string {field:?}")))
}

fn entry_u64(obj: &Map<String, Value>, field: &str) -> Result<u64, ClosureValidationError> {
    obj.get(field)
        .and_then(Value::as_u64)
        .ok_or_else(|| closure_error(format!("files entry missing integer {field:?}")))
}

fn closure_error(message: impl Into<String>) -> ClosureValidationError {
    ClosureValidationError {
        message: message.into(),
    }
}

fn closure_from_fs(error: FsSafetyError) -> ClosureValidationError {
    ClosureValidationError {
        message: error.to_string(),
    }
}

fn closure_from_strict_json(
    context: &str,
) -> impl FnOnce(StrictJsonError) -> ClosureValidationError + '_ {
    move |error| ClosureValidationError {
        message: format!("{context}: {error}"),
    }
}

fn closure_from_schema(error: SchemaValidationError) -> ClosureValidationError {
    ClosureValidationError {
        message: error.to_string(),
    }
}

impl From<DispatchMismatch> for ClosureValidationError {
    fn from(error: DispatchMismatch) -> Self {
        Self {
            message: error.to_string(),
        }
    }
}

impl From<io::Error> for ClosureValidationError {
    fn from(error: io::Error) -> Self {
        Self {
            message: error.to_string(),
        }
    }
}

impl From<CanonicalEncodingError> for ClosureValidationError {
    fn from(error: CanonicalEncodingError) -> Self {
        Self {
            message: error.to_string(),
        }
    }
}

/// Collect case IDs from JSONL files under `root` (does not execute cases).
pub fn case_ids_from_root(root: &Path) -> Result<Vec<String>, ClosureValidationError> {
    let mut ids = Vec::new();
    for path_name in JSONL_FILES {
        let case_schema_id = case_schema_id_for_path(path_name)
            .ok_or_else(|| closure_error(format!("unknown JSONL path {path_name:?}")))?;
        let raw = fs::read(root.join(path_name))?;
        let cases = parse_and_validate_jsonl(&raw, path_name, case_schema_id)?;
        for case in cases {
            let case_id = case
                .get("case_id")
                .and_then(Value::as_str)
                .ok_or_else(|| closure_error(format!("{path_name} case missing case_id")))?
                .to_string();
            ids.push(case_id);
        }
    }
    ids.sort_by(|left, right| left.as_bytes().cmp(right.as_bytes()));
    Ok(ids)
}
