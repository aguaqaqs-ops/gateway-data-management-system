#![forbid(unsafe_code)]

//! Negative closure / vector-root contract tests (R5).

mod support;

use std::fs;
use std::path::{Path, PathBuf};

use gateway_shared_kernel::{DigestKind, raw_blob_digest, semantic_digest};
use serde_json::{Map, Value};

use support::{
    candidate::generate_python_candidate,
    closure::validate_vector_set,
    strict_json::loads_object_rejecting_duplicates,
    temp_dir::TempDirGuard,
    vector_root::{
        VectorRootError, resolve_vector_root_from_os_var, resolve_vector_root_from_path,
    },
};

struct CandidateHarness {
    _guard: TempDirGuard,
    root: PathBuf,
}

#[test]
fn closure_rejects_manifest_duplicate_member() -> Result<(), String> {
    let harness = generate_valid_candidate()?;
    let root = &harness.root;
    let manifest_path = root.join("vector-set.json");
    let text = fs::read_to_string(&manifest_path).map_err(|error| error.to_string())?;
    let trimmed = text.trim_end_matches('\n');
    if !trimmed.ends_with('}') {
        return Err("manifest must end with }".to_string());
    }
    let poisoned = format!(
        "{},\"owner\":\"shared-kernel\"}}",
        &trimmed[..trimmed.len() - 1]
    );
    fs::write(&manifest_path, format!("{poisoned}\n")).map_err(|error| error.to_string())?;
    match validate_vector_set(root, false) {
        Err(error) if error.to_string().contains("duplicate") => Ok(()),
        other => Err(format!("expected duplicate rejection, got {other:?}")),
    }
}

#[test]
fn closure_rejects_manifest_trailing_json() -> Result<(), String> {
    let harness = generate_valid_candidate()?;
    let root = &harness.root;
    let manifest_path = root.join("vector-set.json");
    let text = fs::read_to_string(&manifest_path).map_err(|error| error.to_string())?;
    fs::write(&manifest_path, format!("{text}{{\"x\":1}}")).map_err(|error| error.to_string())?;
    match validate_vector_set(root, false) {
        Err(error) if error.to_string().contains("trailing") => Ok(()),
        other => Err(format!("expected trailing JSON rejection, got {other:?}")),
    }
}

#[test]
fn closure_rejects_manifest_unknown_field() -> Result<(), String> {
    let harness = generate_valid_candidate()?;
    let root = &harness.root;
    let manifest_path = root.join("vector-set.json");
    let text = fs::read_to_string(&manifest_path).map_err(|error| error.to_string())?;
    let poisoned = text.replacen("\"owner\"", "\"unknown_field\":true,\"owner\"", 1);
    fs::write(&manifest_path, poisoned).map_err(|error| error.to_string())?;
    match validate_vector_set(root, false) {
        Err(error) if error.to_string().contains("schema validation failed") => Ok(()),
        other => Err(format!("expected schema rejection, got {other:?}")),
    }
}

#[test]
fn closure_rejects_case_missing_required_field() -> Result<(), String> {
    let harness = generate_valid_candidate()?;
    let root = &harness.root;
    let jcs_path = root.join("jcs.jsonl");
    let line = fs::read_to_string(&jcs_path).map_err(|error| error.to_string())?;
    let poisoned = line.replacen("\"expected\"", "\"missing_expected\"", 1);
    fs::write(&jcs_path, poisoned).map_err(|error| error.to_string())?;
    refresh_jsonl_manifest_entry(root, "jcs.jsonl")?;
    match validate_vector_set(root, false) {
        Err(error) if error.to_string().contains("schema validation failed") => Ok(()),
        other => Err(format!("expected missing field rejection, got {other:?}")),
    }
}

#[test]
fn closure_rejects_expected_and_expected_error_together() -> Result<(), String> {
    let harness = generate_valid_candidate()?;
    let root = &harness.root;
    let invalid_path = root.join("invalid.jsonl");
    let mut lines: Vec<String> = fs::read_to_string(&invalid_path)
        .map_err(|error| error.to_string())?
        .lines()
        .map(str::to_string)
        .collect();
    if lines.is_empty() {
        return Err("invalid.jsonl must contain at least one case".to_string());
    }
    let first = &mut lines[0];
    if !first.contains("\"expected_error\"") {
        return Err("first invalid case must carry expected_error".to_string());
    }
    *first = first.replacen(
        "\"expected_error\"",
        "\"expected\":{\"x\":1},\"expected_error\"",
        1,
    );
    fs::write(&invalid_path, format!("{}\n", lines.join("\n")))
        .map_err(|error| error.to_string())?;
    refresh_jsonl_manifest_entry(root, "invalid.jsonl")?;
    match validate_vector_set(root, false) {
        Err(error) if error.to_string().contains("schema validation failed") => Ok(()),
        other => Err(format!("expected XOR rejection, got {other:?}")),
    }
}

#[test]
fn closure_rejects_wrong_operation_for_scalar_file() -> Result<(), String> {
    let harness = generate_valid_candidate()?;
    let root = &harness.root;
    let scalar_path = root.join("scalar.jsonl");
    let line = fs::read_to_string(&scalar_path).map_err(|error| error.to_string())?;
    let poisoned = line.replacen("\"normalize-logical-literal\"", "\"canonicalize-jcs\"", 1);
    fs::write(&scalar_path, poisoned).map_err(|error| error.to_string())?;
    refresh_jsonl_manifest_entry(root, "scalar.jsonl")?;
    match validate_vector_set(root, false) {
        Err(error) if error.to_string().contains("schema validation failed") => Ok(()),
        other => Err(format!("expected wrong-operation rejection, got {other:?}")),
    }
}

#[test]
fn vector_root_rejects_symlink_directory() -> Result<(), String> {
    let guard = TempDirGuard::new("gateway-closure-negative-symlink")?;
    let base = guard.path();
    let real = base.join("real");
    fs::create_dir_all(&real).map_err(|error| error.to_string())?;
    let link = base.join("link");
    std::os::unix::fs::symlink(&real, &link).map_err(|error| error.to_string())?;
    match resolve_vector_root_from_path(&link) {
        Err(VectorRootError::Symlink(_)) => Ok(()),
        other => Err(format!("expected Symlink error, got {other:?}")),
    }
}

#[test]
fn explicit_env_missing_path_fails_without_fallback() -> Result<(), String> {
    let missing = "/definitely/missing/gateway-shared-kernel-vector-root";
    match resolve_vector_root_from_os_var(Some(std::ffi::OsStr::new(missing))) {
        Err(VectorRootError::NotFound(_)) => Ok(()),
        other => Err(format!("expected NotFound for explicit env, got {other:?}")),
    }
}

#[test]
fn explicit_env_empty_fails_without_fallback() -> Result<(), String> {
    match resolve_vector_root_from_os_var(Some(std::ffi::OsStr::new(""))) {
        Err(VectorRootError::EnvEmpty) => Ok(()),
        other => Err(format!("expected EnvEmpty, got {other:?}")),
    }
}

fn generate_valid_candidate() -> Result<CandidateHarness, String> {
    let guard = TempDirGuard::new("gateway-closure-negative")?;
    let root = guard.path().join("candidate");
    generate_python_candidate(&root).map_err(|error| error.to_string())?;
    Ok(CandidateHarness {
        _guard: guard,
        root,
    })
}

fn refresh_jsonl_manifest_entry(root: &Path, path_name: &str) -> Result<(), String> {
    let bytes = fs::read(root.join(path_name)).map_err(|error| error.to_string())?;
    let digest = raw_blob_digest(&bytes).map_err(|error| error.to_string())?;
    let line_count = if bytes.is_empty() {
        0
    } else {
        bytes
            .split(|byte| *byte == b'\n')
            .filter(|line| !line.is_empty())
            .count()
    };

    let manifest_path = root.join("vector-set.json");
    let manifest_text = fs::read_to_string(&manifest_path).map_err(|error| error.to_string())?;
    let mut manifest = loads_object_rejecting_duplicates(manifest_text.trim_end_matches('\n'))
        .map_err(|e| e.to_string())?;
    let files = manifest
        .get_mut("files")
        .and_then(Value::as_array_mut)
        .ok_or_else(|| "manifest files must be an array".to_string())?;
    for entry in files {
        let obj = entry
            .as_object_mut()
            .ok_or_else(|| "files entry must be an object".to_string())?;
        if obj.get("path").and_then(Value::as_str) == Some(path_name) {
            obj.insert(
                "size_bytes".to_string(),
                Value::Number(
                    u64::try_from(bytes.len())
                        .map_err(|_| "size_bytes overflow")?
                        .into(),
                ),
            );
            obj.insert(
                "raw_sha256".to_string(),
                Value::String(digest.as_str().to_string()),
            );
            obj.insert(
                "case_count".to_string(),
                Value::Number(
                    u64::try_from(line_count)
                        .map_err(|_| "case_count overflow")?
                        .into(),
                ),
            );
            break;
        }
    }

    let mut body: Map<String, Value> = manifest.clone();
    body.remove("vector_set_content_digest");
    let projected_bytes = serde_json_canonicalizer::to_vec(&Value::Object(body))
        .map_err(|error| error.to_string())?;
    let content_digest = semantic_digest(DigestKind::VectorSet, &projected_bytes)
        .map_err(|error| error.to_string())?;
    manifest.insert(
        "vector_set_content_digest".to_string(),
        Value::String(content_digest.digest_ref().as_str().to_string()),
    );
    let canonical = serde_json_canonicalizer::to_vec(&Value::Object(manifest))
        .map_err(|error| error.to_string())?;
    let mut out = canonical;
    out.push(b'\n');
    fs::write(&manifest_path, out).map_err(|error| error.to_string())?;
    Ok(())
}
