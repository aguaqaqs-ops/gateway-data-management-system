//! Generate Python candidate vector sets for Rust integration tests (test-only).

use std::path::{Path, PathBuf};
use std::process::Command;

use super::paths::CANDIDATE_MARKER_NAME;

#[derive(Debug)]
pub struct CandidateGenerationError {
    message: String,
}

impl std::fmt::Display for CandidateGenerationError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}

impl std::error::Error for CandidateGenerationError {}

/// Resolve `vnext/shared_kernel` relative to this crate's manifest dir.
pub fn shared_kernel_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .join("shared_kernel")
}

/// Generate a fresh candidate vector set into `output_dir` via Python reference tooling.
pub fn generate_python_candidate(output_dir: &Path) -> Result<PathBuf, CandidateGenerationError> {
    let shared_kernel = shared_kernel_root();
    if !shared_kernel.is_dir() {
        return Err(CandidateGenerationError {
            message: format!(
                "shared_kernel directory not found at {}",
                shared_kernel.display()
            ),
        });
    }

    let status = Command::new("uv")
        .current_dir(&shared_kernel)
        .args([
            "run",
            "--offline",
            "python",
            "-m",
            "gateway_shared_kernel.testing",
            "generate",
        ])
        .arg(output_dir)
        .status()
        .map_err(|source| CandidateGenerationError {
            message: format!("failed to spawn uv for candidate generation: {source}"),
        })?;

    if !status.success() {
        return Err(CandidateGenerationError {
            message: format!("python candidate generator exited with status {status}"),
        });
    }

    let marker = output_dir.join(CANDIDATE_MARKER_NAME);
    if !marker.is_file() {
        return Err(CandidateGenerationError {
            message: format!(
                "candidate marker missing after generation: {}",
                marker.display()
            ),
        });
    }

    Ok(output_dir.to_path_buf())
}
