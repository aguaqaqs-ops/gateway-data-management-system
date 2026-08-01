#![forbid(unsafe_code)]
#![allow(
    dead_code,
    clippy::collapsible_if,
    reason = "shared integration-test support: submodules are used by different test binaries"
)]

//! Integration-test support for Shared Kernel owner tests.
//!
//! This module tree is compiled only into integration tests. Production
//! library modules must never import filesystem-aware vector discovery.

pub mod codec;
pub mod dispatch;
pub mod validate_frame;
