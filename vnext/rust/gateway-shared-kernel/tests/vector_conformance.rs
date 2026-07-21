#![forbid(unsafe_code)]

//! R5/R6 integration test: load normative vector set, validate closure, dispatch all cases.

mod support;

use std::collections::BTreeSet;
use std::path::PathBuf;

use support::{
    closure::{case_ids_from_root, validate_vector_set},
    paths::normative_vector_root,
    vector_root::{
        VECTOR_ROOT_ENV, VectorRootError, resolve_vector_root_from_env,
        resolve_vector_root_from_path,
    },
};

#[test]
fn rust_vector_conformance_matches_normative_root() -> Result<(), String> {
    let root = resolve_vector_root_for_test()?;
    let manifest = validate_vector_set(&root, true)
        .map_err(|error| format!("vector set validation failed: {error}"))?;

    let case_ids = case_ids_from_root(&root)
        .map_err(|error| format!("failed to collect case ids: {error}"))?;
    if case_ids.is_empty() {
        return Err("vector set must contain at least one case".to_string());
    }
    if case_ids.len() != case_ids.iter().collect::<BTreeSet<_>>().len() {
        return Err("duplicate case_id detected after validation".to_string());
    }

    let manifest_case_count = manifest
        .get("files")
        .and_then(|value| value.as_array())
        .and_then(|files| {
            files
                .iter()
                .filter_map(|entry| entry.get("case_count").and_then(serde_json::Value::as_u64))
                .try_fold(0u64, |acc, count| acc.checked_add(count))
        })
        .ok_or_else(|| "manifest files[].case_count must be present".to_string())?;
    let case_count_usize = usize::try_from(manifest_case_count).map_err(|_| {
        format!("manifest case_count sum {manifest_case_count} exceeds usize on this target")
    })?;
    if case_count_usize != case_ids.len() {
        return Err(format!(
            "manifest case_count sum {manifest_case_count} != collected ids {}",
            case_ids.len()
        ));
    }

    Ok(())
}

fn resolve_vector_root_for_test() -> Result<PathBuf, String> {
    match resolve_vector_root_from_env() {
        Ok(root) => Ok(root),
        Err(VectorRootError::EnvNotSet) => resolve_vector_root_from_path(normative_vector_root())
            .map_err(|error| format!("normative vector root resolution failed: {error}")),
        Err(error) => Err(format!("explicit vector root resolution failed: {error}")),
    }
}

#[test]
fn vector_root_env_contract_documented() {
    assert_eq!(VECTOR_ROOT_ENV, "GATEWAY_SHARED_KERNEL_VECTOR_ROOT");
}
