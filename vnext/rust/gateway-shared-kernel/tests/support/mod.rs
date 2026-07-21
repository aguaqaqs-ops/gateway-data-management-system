#![forbid(unsafe_code)]

//! Integration-test support for Shared Kernel conformance.
//!
//! This module tree is compiled only into integration tests. Production
//! library modules must never import filesystem-aware vector discovery.

mod vector_root;

pub use vector_root::{
    VECTOR_ROOT_ENV, VectorRootError, resolve_vector_root_from_env,
    resolve_vector_root_from_os_var, resolve_vector_root_from_path,
};
