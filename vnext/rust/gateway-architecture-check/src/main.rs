#![forbid(unsafe_code)]

use std::env;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

use gateway_architecture_check::{CheckConfig, run_checks};

fn main() -> ExitCode {
    let config = match parse_config(env::args().skip(1).collect()) {
        Ok(config) => config,
        Err(message) => {
            eprintln!("gateway-architecture-check: {message}");
            return ExitCode::from(2);
        }
    };

    match run_checks(&config) {
        Ok(()) => ExitCode::SUCCESS,
        Err(violations) => {
            eprintln!("architecture/policy check failed:");
            for violation in violations {
                eprintln!("  - {violation}");
            }
            ExitCode::from(1)
        }
    }
}

fn parse_config(args: Vec<String>) -> Result<CheckConfig, String> {
    let mut rust_workspace_root = PathBuf::from(".");
    let mut vnext_root = None;
    let mut index = 0usize;

    while index < args.len() {
        match args[index].as_str() {
            "--rust-workspace-root" => {
                index += 1;
                rust_workspace_root = next_value(&args, index, "--rust-workspace-root")?;
                index += 1;
            }
            "--vnext-root" => {
                index += 1;
                vnext_root = Some(next_value(&args, index, "--vnext-root")?);
                index += 1;
            }
            flag => return Err(format!("unknown argument: {flag}")),
        }
    }

    let vnext_root = match vnext_root {
        Some(path) => path,
        None => default_vnext_root(&rust_workspace_root),
    };

    Ok(CheckConfig {
        rust_workspace_root,
        vnext_root,
    })
}

fn next_value(args: &[String], index: usize, flag: &str) -> Result<PathBuf, String> {
    match args.get(index) {
        Some(value) => Ok(PathBuf::from(value)),
        None => Err(format!("missing value for {flag}")),
    }
}

fn default_vnext_root(rust_workspace_root: &Path) -> PathBuf {
    match rust_workspace_root.parent() {
        Some(parent) => parent.to_path_buf(),
        None => rust_workspace_root.to_path_buf(),
    }
}
