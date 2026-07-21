#![forbid(unsafe_code)]

//! R1 contract tests for vector-root discovery (test-support only).

mod support;

use std::fs;
use std::path::PathBuf;

use support::vector_root::{
    VECTOR_ROOT_ENV, VectorRootError, resolve_vector_root_from_env,
    resolve_vector_root_from_os_var, resolve_vector_root_from_path,
};

#[test]
fn vector_root_env_name_is_stable() {
    assert_eq!(VECTOR_ROOT_ENV, "GATEWAY_SHARED_KERNEL_VECTOR_ROOT");
}

#[test]
fn resolve_from_path_accepts_existing_directory() -> Result<(), String> {
    let dir = tempfile_dir()?;
    let resolved = resolve_vector_root_from_path(&dir)
        .map_err(|error| format!("expected directory to resolve: {error}"))?;
    let canonical = fs::canonicalize(&dir).map_err(|error| error.to_string())?;
    assert_eq!(resolved, canonical);
    let _ = fs::remove_dir_all(&dir);
    Ok(())
}

#[test]
fn resolve_from_path_rejects_empty_and_missing() -> Result<(), String> {
    match resolve_vector_root_from_path("") {
        Err(VectorRootError::EmptyPath) => {}
        other => {
            return Err(format!("empty path must yield EmptyPath, got: {other:?}"));
        }
    }

    match resolve_vector_root_from_path("/definitely/missing/gateway-shared-kernel-vector-root") {
        Err(VectorRootError::NotFound(_)) => Ok(()),
        other => Err(format!("missing path must yield NotFound, got: {other:?}")),
    }
}

#[test]
fn resolve_from_os_var_contract() -> Result<(), String> {
    match resolve_vector_root_from_os_var(None) {
        Err(VectorRootError::EnvNotSet) => {}
        other => {
            return Err(format!("None must yield EnvNotSet, got: {other:?}"));
        }
    }

    match resolve_vector_root_from_os_var(Some(std::ffi::OsStr::new(""))) {
        Err(VectorRootError::EnvEmpty) => {}
        other => {
            return Err(format!(
                "empty os value must yield EnvEmpty, got: {other:?}"
            ));
        }
    }

    let dir = tempfile_dir()?;
    let resolved = resolve_vector_root_from_os_var(Some(dir.as_os_str()))
        .map_err(|error| format!("os var path must resolve: {error}"))?;
    let canonical = fs::canonicalize(&dir).map_err(|error| error.to_string())?;
    assert_eq!(resolved, canonical);
    let _ = fs::remove_dir_all(&dir);
    Ok(())
}

#[test]
fn resolve_from_env_wrapper_returns_typed_result() -> Result<(), String> {
    // Process-env wrapper is part of the R1 contract surface.
    match resolve_vector_root_from_env() {
        Ok(path) => {
            assert!(path.is_absolute());
            Ok(())
        }
        Err(
            VectorRootError::EnvNotSet
            | VectorRootError::EnvEmpty
            | VectorRootError::Symlink(_)
            | VectorRootError::NotFound(_)
            | VectorRootError::NotDirectory(_)
            | VectorRootError::Io { .. },
        ) => Ok(()),
        Err(VectorRootError::EmptyPath) => {
            Err("env wrapper must not synthesize EmptyPath".to_string())
        }
    }
}

fn tempfile_dir() -> Result<PathBuf, String> {
    let base = std::env::temp_dir();
    let path = base.join(format!(
        "gateway-shared-kernel-vector-root-{}-{}",
        std::process::id(),
        unique_suffix()
    ));
    fs::create_dir_all(&path).map_err(|error| error.to_string())?;
    Ok(path)
}

fn unique_suffix() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    match SystemTime::now().duration_since(UNIX_EPOCH) {
        Ok(duration) => duration.as_nanos() as u64,
        Err(_) => 0,
    }
}
