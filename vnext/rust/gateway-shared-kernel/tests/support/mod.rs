#![forbid(unsafe_code)]
#![allow(
    dead_code,
    clippy::collapsible_if,
    reason = "shared integration-test support: submodules are used by different test binaries"
)]

//! Integration-test support for Shared Kernel conformance.
//!
//! This module tree is compiled only into integration tests. Production
//! library modules must never import filesystem-aware vector discovery.

pub mod candidate;
pub mod closure;
pub mod codec;
pub mod dispatch;
pub mod fs_safety;
pub mod paths;
pub mod schemas;
pub mod strict_json;
pub mod temp_dir;
pub mod validate_frame;
pub mod vector_root;
