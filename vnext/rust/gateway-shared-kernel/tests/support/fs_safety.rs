//! Symlink and regular-file checks for vector-set I/O (test-only).

use std::io;
use std::path::{Path, PathBuf};

#[derive(Debug)]
pub enum FsSafetyError {
    Symlink { path: PathBuf, label: String },
    NotRegularFile { path: PathBuf, label: String },
    NotRegularDirectory { path: PathBuf, label: String },
    Io { path: PathBuf, source: io::Error },
}

impl std::fmt::Display for FsSafetyError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Symlink { path, label } => {
                write!(
                    f,
                    "refusing {label} that involves symlink path {}",
                    path.display()
                )
            }
            Self::NotRegularFile { path, label } => {
                write!(f, "{label} is not a regular file: {}", path.display())
            }
            Self::NotRegularDirectory { path, label } => {
                write!(f, "{label} is not a directory: {}", path.display())
            }
            Self::Io { path, source } => {
                write!(f, "failed to inspect {}: {source}", path.display())
            }
        }
    }
}

impl std::error::Error for FsSafetyError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io { source, .. } => Some(source),
            _ => None,
        }
    }
}

pub fn is_symlink(path: &Path) -> Result<bool, FsSafetyError> {
    match path.symlink_metadata() {
        Ok(metadata) => Ok(metadata.file_type().is_symlink()),
        Err(source) if source.kind() == io::ErrorKind::NotFound => Ok(false),
        Err(source) => Err(FsSafetyError::Io {
            path: path.to_path_buf(),
            source,
        }),
    }
}

pub fn assert_no_symlink_ancestors(path: &Path, label: &str) -> Result<(), FsSafetyError> {
    let mut parts: Vec<PathBuf> = Vec::new();
    let mut cursor = path.to_path_buf();
    loop {
        parts.push(cursor.clone());
        let parent = cursor.parent();
        match parent {
            Some(parent) if parent != cursor.as_path() => cursor = parent.to_path_buf(),
            _ => break,
        }
    }
    for item in parts.iter().rev() {
        if is_symlink(item)? {
            return Err(FsSafetyError::Symlink {
                path: item.clone(),
                label: label.to_string(),
            });
        }
    }
    Ok(())
}

pub fn assert_regular_file(path: &Path, label: &str) -> Result<(), FsSafetyError> {
    if is_symlink(path)? {
        return Err(FsSafetyError::Symlink {
            path: path.to_path_buf(),
            label: label.to_string(),
        });
    }
    match path.metadata() {
        Ok(metadata) if metadata.is_file() => Ok(()),
        Ok(_) => Err(FsSafetyError::NotRegularFile {
            path: path.to_path_buf(),
            label: label.to_string(),
        }),
        Err(source) => Err(FsSafetyError::Io {
            path: path.to_path_buf(),
            source,
        }),
    }
}

pub fn assert_regular_directory(path: &Path, label: &str) -> Result<(), FsSafetyError> {
    if is_symlink(path)? {
        return Err(FsSafetyError::Symlink {
            path: path.to_path_buf(),
            label: label.to_string(),
        });
    }
    match path.metadata() {
        Ok(metadata) if metadata.is_dir() => Ok(()),
        Ok(_) => Err(FsSafetyError::NotRegularDirectory {
            path: path.to_path_buf(),
            label: label.to_string(),
        }),
        Err(source) => Err(FsSafetyError::Io {
            path: path.to_path_buf(),
            source,
        }),
    }
}
