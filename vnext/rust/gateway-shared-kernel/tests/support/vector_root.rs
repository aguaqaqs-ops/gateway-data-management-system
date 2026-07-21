//! Vector-root discovery contract (R1).
//!
//! # Boundary
//!
//! ```text
//! gate/script
//!   -> supplies an explicit filesystem path (candidate or fixed normative root)
//!   -> Rust integration test resolves that path via this support module
//!   -> loader/dispatcher (R5) reads JSONL under the resolved root
//! ```
//!
//! Hard rules:
//! - Path enters Rust **only** through integration-test support.
//! - Production `gateway_shared_kernel` must not read env, filesystem, or this module.
//! - Full JSONL loader / case dispatcher is deferred to R5; R1 only fixes discovery.

use std::env;
use std::ffi::OsStr;
use std::fmt;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

/// Environment variable used by the harness to pass a vector root into Rust tests.
///
/// Prefer explicit path arguments when available; this env name is the fixed
/// fallback contract for `cargo test` orchestration.
pub const VECTOR_ROOT_ENV: &str = "GATEWAY_SHARED_KERNEL_VECTOR_ROOT";

/// Discovery failures for the test-support layer (not Shared Kernel stable codes).
#[derive(Debug)]
pub enum VectorRootError {
    EmptyPath,
    EnvNotSet,
    EnvEmpty,
    NotFound(PathBuf),
    NotDirectory(PathBuf),
    Io { path: PathBuf, source: io::Error },
}

impl fmt::Display for VectorRootError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::EmptyPath => f.write_str("vector root path is empty"),
            Self::EnvNotSet => write!(f, "environment variable {VECTOR_ROOT_ENV} is not set"),
            Self::EnvEmpty => write!(f, "environment variable {VECTOR_ROOT_ENV} is empty"),
            Self::NotFound(path) => write!(f, "vector root does not exist: {}", path.display()),
            Self::NotDirectory(path) => {
                write!(f, "vector root is not a directory: {}", path.display())
            }
            Self::Io { path, source } => {
                write!(
                    f,
                    "failed to resolve vector root {}: {source}",
                    path.display()
                )
            }
        }
    }
}

impl std::error::Error for VectorRootError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io { source, .. } => Some(source),
            _ => None,
        }
    }
}

/// Resolve a vector root from an explicit path argument.
///
/// Symlink policy and closure validation are owned by the R5 loader; this
/// function only requires an existing directory.
pub fn resolve_vector_root_from_path(path: impl AsRef<Path>) -> Result<PathBuf, VectorRootError> {
    let requested = path.as_ref();
    if requested.as_os_str().is_empty() {
        return Err(VectorRootError::EmptyPath);
    }

    let metadata = match fs::metadata(requested) {
        Ok(metadata) => metadata,
        Err(source) if source.kind() == io::ErrorKind::NotFound => {
            return Err(VectorRootError::NotFound(requested.to_path_buf()));
        }
        Err(source) => {
            return Err(VectorRootError::Io {
                path: requested.to_path_buf(),
                source,
            });
        }
    };

    if !metadata.is_dir() {
        return Err(VectorRootError::NotDirectory(requested.to_path_buf()));
    }

    match fs::canonicalize(requested) {
        Ok(resolved) => Ok(resolved),
        Err(source) => Err(VectorRootError::Io {
            path: requested.to_path_buf(),
            source,
        }),
    }
}

/// Resolve from an injected env value (testable without mutating process env).
pub fn resolve_vector_root_from_os_var(value: Option<&OsStr>) -> Result<PathBuf, VectorRootError> {
    match value {
        None => Err(VectorRootError::EnvNotSet),
        Some(value) if value.is_empty() => Err(VectorRootError::EnvEmpty),
        Some(value) => resolve_vector_root_from_path(PathBuf::from(value)),
    }
}

/// Resolve a vector root from [`VECTOR_ROOT_ENV`].
pub fn resolve_vector_root_from_env() -> Result<PathBuf, VectorRootError> {
    resolve_vector_root_from_os_var(env::var_os(VECTOR_ROOT_ENV).as_deref())
}
