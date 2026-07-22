#![forbid(unsafe_code)]

use std::collections::BTreeSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

const REQUIRED_TOOLCHAIN: &str = "1.97.0";
const REQUIRED_FORBID_UNSAFE_LINE: &str = "#![forbid(unsafe_code)]";

#[derive(Debug, Clone)]
pub struct CheckConfig {
    pub rust_workspace_root: PathBuf,
    pub vnext_root: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub struct WorkspaceMember {
    pub name: String,
    pub manifest_path: PathBuf,
}

pub fn run_checks(config: &CheckConfig) -> Result<(), Vec<String>> {
    let mut violations = Vec::new();

    violations.extend(check_toolchain(&config.rust_workspace_root));
    violations.extend(check_workspace_members(&config.rust_workspace_root));
    violations.extend(check_no_unstable_features(&config.rust_workspace_root));
    violations.extend(check_vnext_import_boundaries(&config.vnext_root));
    violations.extend(check_crate_dependency_boundaries(
        &config.rust_workspace_root,
    ));

    if violations.is_empty() {
        Ok(())
    } else {
        Err(violations)
    }
}

pub fn crate_root_has_forbid_unsafe(contents: &str) -> bool {
    let without_bom = contents.strip_prefix('\u{FEFF}').unwrap_or(contents);
    match without_bom.lines().next() {
        Some(first_line) => first_line == REQUIRED_FORBID_UNSAFE_LINE,
        None => false,
    }
}

fn check_toolchain(rust_workspace_root: &Path) -> Vec<String> {
    let toolchain_path = rust_workspace_root.join("rust-toolchain.toml");
    let contents = match fs::read_to_string(&toolchain_path) {
        Ok(contents) => contents,
        Err(error) => {
            return vec![format!(
                "failed to read {}: {error}",
                toolchain_path.display()
            )];
        }
    };

    let channel = contents
        .lines()
        .find_map(parse_toolchain_channel)
        .unwrap_or_default();

    if channel == REQUIRED_TOOLCHAIN {
        Vec::new()
    } else {
        vec![format!(
            "rust-toolchain.toml must pin stable {REQUIRED_TOOLCHAIN}, found '{channel}'"
        )]
    }
}

fn parse_toolchain_channel(line: &str) -> Option<&str> {
    let trimmed = line.trim();
    let rest = trimmed.strip_prefix("channel")?;
    let rest = rest.trim_start();
    let rest = rest.strip_prefix('=')?;
    Some(rest.trim().trim_matches('"'))
}

fn check_workspace_members(rust_workspace_root: &Path) -> Vec<String> {
    let metadata = match fetch_cargo_metadata(rust_workspace_root) {
        Ok(metadata) => metadata,
        Err(error) => return vec![error],
    };

    let workspace_root = match metadata["workspace_root"].as_str() {
        Some(root) => root,
        None => return vec!["cargo metadata missing workspace_root".to_string()],
    };

    let packages = match metadata["packages"].as_array() {
        Some(packages) => packages,
        None => return vec!["cargo metadata missing packages".to_string()],
    };

    let mut violations = Vec::new();
    let mut checked_target_roots = BTreeSet::new();

    for package in packages {
        let manifest_path = match package["manifest_path"].as_str() {
            Some(path) => PathBuf::from(path),
            None => {
                violations.push("cargo metadata package missing manifest_path".to_string());
                continue;
            }
        };

        if !manifest_path.starts_with(workspace_root) {
            continue;
        }

        let name = match package["name"].as_str() {
            Some(name) => name,
            None => {
                violations.push("cargo metadata package missing name".to_string());
                continue;
            }
        };

        if let Err(error) = member_manifest_inherits_workspace_lints(&manifest_path) {
            violations.push(format!("{name}: {error}"));
        }

        let targets = match package["targets"].as_array() {
            Some(targets) => targets,
            None => {
                violations.push(format!("{name}: cargo metadata package missing targets"));
                continue;
            }
        };

        for target in targets {
            let src_path = match target["src_path"].as_str() {
                Some(path) => PathBuf::from(path),
                None => continue,
            };

            if !should_check_target_forbid(target["kind"].as_array()) {
                continue;
            }

            if !checked_target_roots.insert(src_path.clone()) {
                continue;
            }

            if let Err(error) = check_target_root_forbids_unsafe(&src_path) {
                let target_name = target["name"].as_str().unwrap_or("<unknown>");
                violations.push(format!("{name} target `{target_name}`: {error}"));
            }
        }
    }

    if checked_target_roots.is_empty() {
        violations.push("no first-party Cargo targets found in workspace metadata".to_string());
    }

    violations
}

fn should_check_target_forbid(kind: Option<&Vec<serde_json::Value>>) -> bool {
    let Some(kind) = kind else {
        return false;
    };

    kind.iter().filter_map(|value| value.as_str()).any(|kind| {
        matches!(
            kind,
            "lib"
                | "bin"
                | "example"
                | "test"
                | "bench"
                | "custom-build"
                | "cdylib"
                | "dylib"
                | "staticlib"
                | "proc-macro"
                | "rlib"
        )
    })
}

fn check_target_root_forbids_unsafe(path: &Path) -> Result<(), String> {
    let contents = fs::read_to_string(path)
        .map_err(|error| format!("failed to read {}: {error}", path.display()))?;

    if crate_root_has_forbid_unsafe(&contents) {
        Ok(())
    } else {
        Err(format!(
            "target root {} must have first line `{REQUIRED_FORBID_UNSAFE_LINE}`",
            path.display()
        ))
    }
}

pub fn discover_workspace_members(
    rust_workspace_root: &Path,
) -> Result<Vec<WorkspaceMember>, String> {
    let metadata = fetch_cargo_metadata(rust_workspace_root)?;
    let workspace_root = metadata["workspace_root"]
        .as_str()
        .ok_or_else(|| "cargo metadata missing workspace_root".to_string())?;

    let packages = metadata["packages"]
        .as_array()
        .ok_or_else(|| "cargo metadata missing packages".to_string())?;

    let mut members = BTreeSet::new();
    for package in packages {
        let manifest_path = package["manifest_path"]
            .as_str()
            .ok_or_else(|| "cargo metadata package missing manifest_path".to_string())?;
        let manifest = PathBuf::from(manifest_path);
        if !manifest.starts_with(workspace_root) {
            continue;
        }

        let name = package["name"]
            .as_str()
            .ok_or_else(|| "cargo metadata package missing name".to_string())?
            .to_string();

        members.insert(WorkspaceMember {
            name,
            manifest_path: manifest,
        });
    }

    Ok(members.into_iter().collect())
}

fn fetch_cargo_metadata(rust_workspace_root: &Path) -> Result<serde_json::Value, String> {
    let output = Command::new("cargo")
        .arg("metadata")
        .arg("--format-version")
        .arg("1")
        .arg("--no-deps")
        .arg("--locked")
        .arg("--offline")
        .current_dir(rust_workspace_root)
        .output()
        .map_err(|error| format!("failed to run cargo metadata: {error}"))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("cargo metadata failed: {stderr}"));
    }

    serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("failed to parse cargo metadata JSON: {error}"))
}

fn member_manifest_inherits_workspace_lints(manifest_path: &Path) -> Result<(), String> {
    let contents = fs::read_to_string(manifest_path)
        .map_err(|error| format!("failed to read {}: {error}", manifest_path.display()))?;

    let mut in_lints = false;
    for line in contents.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with('[') && trimmed.ends_with(']') {
            in_lints = trimmed == "[lints]";
            continue;
        }

        if in_lints && trimmed == "workspace = true" {
            return Ok(());
        }
    }

    Err(format!(
        "manifest {} must declare [lints] workspace = true",
        manifest_path.display()
    ))
}

fn check_no_unstable_features(rust_workspace_root: &Path) -> Vec<String> {
    let mut violations = Vec::new();
    if let Err(error) = walk_rust_sources(rust_workspace_root, &mut |path| {
        let contents = match fs::read_to_string(path) {
            Ok(contents) => contents,
            Err(error) => {
                violations.push(format!("failed to read {}: {error}", path.display()));
                return;
            }
        };

        for line in contents.lines() {
            if line.trim().starts_with("#![feature") {
                violations.push(format!("unstable feature gate found in {}", path.display()));
                break;
            }
        }
    }) {
        violations.push(error);
    }

    violations
}

fn check_crate_dependency_boundaries(rust_workspace_root: &Path) -> Vec<String> {
    let members = match discover_workspace_members(rust_workspace_root) {
        Ok(members) => members,
        Err(error) => return vec![error],
    };

    let metadata = match fetch_cargo_metadata_with_deps(rust_workspace_root) {
        Ok(metadata) => metadata,
        Err(error) => return vec![error],
    };

    let package_dependencies = match package_dependency_map(&metadata) {
        Ok(map) => map,
        Err(error) => return vec![error],
    };

    let mut violations = Vec::new();
    for member in members {
        let dependencies = package_dependencies
            .get(&member.name)
            .cloned()
            .unwrap_or_default();

        match member.name.as_str() {
            "gateway-compute-core" | "gateway-compute-python" | "gateway-shared-kernel" => {
                for dependency in &dependencies {
                    if let Some(violation) =
                        forbidden_dependency_violation(&member.name, dependency)
                    {
                        violations.push(violation);
                    }
                }
            }
            _ => {}
        }
    }
    violations
}

fn fetch_cargo_metadata_with_deps(rust_workspace_root: &Path) -> Result<serde_json::Value, String> {
    let output = Command::new("cargo")
        .arg("metadata")
        .arg("--format-version")
        .arg("1")
        .arg("--locked")
        .arg("--offline")
        .current_dir(rust_workspace_root)
        .output()
        .map_err(|error| format!("failed to run cargo metadata: {error}"))?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("cargo metadata failed: {stderr}"));
    }

    serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("failed to parse cargo metadata JSON: {error}"))
}

fn package_dependency_map(
    metadata: &serde_json::Value,
) -> Result<std::collections::BTreeMap<String, Vec<String>>, String> {
    let packages = metadata["packages"]
        .as_array()
        .ok_or_else(|| "cargo metadata missing packages".to_string())?;

    let mut map = std::collections::BTreeMap::new();
    for package in packages {
        let name = package["name"]
            .as_str()
            .ok_or_else(|| "cargo metadata package missing name".to_string())?
            .to_string();
        let mut dependencies = BTreeSet::new();
        if let Some(deps) = package["dependencies"].as_array() {
            for dep in deps {
                if let Some(dep_name) = dependency_crate_name(dep) {
                    dependencies.insert(dep_name);
                }
            }
        }
        map.insert(name, dependencies.into_iter().collect());
    }
    Ok(map)
}

fn dependency_crate_name(dep: &serde_json::Value) -> Option<String> {
    dep["name"].as_str().map(str::to_string)
}

fn forbidden_dependency_violation(crate_name: &str, dependency: &str) -> Option<String> {
    match crate_name {
        "gateway-compute-core" => {
            if matches!(
                dependency,
                "pyo3" | "pyo3-arrow" | "gateway-compute-python" | "gateway-artifact-store"
            ) {
                return Some(format!("{crate_name} must not depend on {dependency}"));
            }
            if dependency == "reqwest" || dependency == "tokio" || dependency == "hyper" {
                return Some(format!(
                    "{crate_name} must not depend on network crate `{dependency}`"
                ));
            }
        }
        "gateway-compute-python" => {
            if dependency == "gateway-shared-kernel" {
                return Some(
                    "gateway-compute-python must not directly depend on gateway-shared-kernel"
                        .to_string(),
                );
            }
        }
        "gateway-shared-kernel"
            if dependency.starts_with("arrow-")
                || dependency.starts_with("pyo3")
                || dependency == "gateway-compute-core"
                || dependency == "gateway-compute-python" =>
        {
            return Some(format!(
                "gateway-shared-kernel must not depend on {dependency}"
            ));
        }
        _ => {}
    }
    None
}

fn check_vnext_import_boundaries(vnext_root: &Path) -> Vec<String> {
    let mut violations = Vec::new();
    if let Err(error) = walk_source_files(vnext_root, &mut |path| {
        let contents = match fs::read_to_string(path) {
            Ok(contents) => contents,
            Err(error) => {
                violations.push(format!("failed to read {}: {error}", path.display()));
                return;
            }
        };

        for line in contents.lines() {
            if line_violates_legacy_import_boundary(path, line) {
                violations.push(format!(
                    "legacy import boundary violation in {}: `{line}`",
                    path.display()
                ));
            }
        }
    }) {
        violations.push(error);
    }

    violations
}

fn line_violates_legacy_import_boundary(path: &Path, line: &str) -> bool {
    let trimmed = line.trim();
    match path.extension().and_then(|ext| ext.to_str()) {
        Some("py") => {
            trimmed.starts_with("import legacy")
                || trimmed.starts_with("from legacy")
                || trimmed.starts_with("import backend_vnext")
                || trimmed.starts_with("from backend_vnext")
        }
        Some("rs") => trimmed.starts_with("use legacy::") || trimmed.starts_with("mod legacy"),
        _ => false,
    }
}

fn should_skip_vnext_path(path: &Path) -> bool {
    path.components().any(|component| {
        matches!(
            component.as_os_str().to_str(),
            Some("target") | Some(".venv") | Some("__pycache__")
        )
    })
}

fn walk_rust_sources(root: &Path, visit: &mut dyn FnMut(&Path)) -> Result<(), String> {
    walk_source_files_with_extension(root, "rs", visit)
}

fn walk_source_files(root: &Path, visit: &mut dyn FnMut(&Path)) -> Result<(), String> {
    let entries = fs::read_dir(root)
        .map_err(|error| format!("failed to read directory {}: {error}", root.display()))?;

    for entry in entries {
        let entry = entry.map_err(|error| {
            format!(
                "failed to read directory entry under {}: {error}",
                root.display()
            )
        })?;
        let path = entry.path();
        if path.is_dir() {
            if should_skip_vnext_path(&path) {
                continue;
            }
            walk_source_files(&path, visit)?;
            continue;
        }

        if path
            .extension()
            .is_some_and(|ext| ext == "py" || ext == "rs")
        {
            visit(&path);
        }
    }

    Ok(())
}

fn walk_source_files_with_extension(
    root: &Path,
    extension: &str,
    visit: &mut dyn FnMut(&Path),
) -> Result<(), String> {
    let entries = fs::read_dir(root)
        .map_err(|error| format!("failed to read directory {}: {error}", root.display()))?;

    for entry in entries {
        let entry = entry.map_err(|error| {
            format!(
                "failed to read directory entry under {}: {error}",
                root.display()
            )
        })?;
        let path = entry.path();
        if path.is_dir() {
            if should_skip_vnext_path(&path) {
                continue;
            }
            walk_source_files_with_extension(&path, extension, visit)?;
            continue;
        }

        if path.extension().is_some_and(|ext| ext == extension) {
            visit(&path);
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{
        check_target_root_forbids_unsafe, crate_root_has_forbid_unsafe,
        member_manifest_inherits_workspace_lints,
    };
    use std::fs;
    use std::path::PathBuf;

    #[test]
    fn accepts_workspace_lint_inheritance() -> Result<(), String> {
        let dir = tempfile::tempdir().map_err(|error| error.to_string())?;
        let manifest = dir.path().join("Cargo.toml");
        fs::write(&manifest, "[lints]\nworkspace = true\n").map_err(|error| error.to_string())?;

        member_manifest_inherits_workspace_lints(&manifest)?;
        Ok(())
    }

    #[test]
    fn rejects_missing_workspace_lint_inheritance() -> Result<(), String> {
        let dir = tempfile::tempdir().map_err(|error| error.to_string())?;
        let manifest = dir.path().join("Cargo.toml");
        fs::write(&manifest, "[package]\nname = \"demo\"\n").map_err(|error| error.to_string())?;

        let error = match member_manifest_inherits_workspace_lints(&manifest) {
            Ok(()) => return Err("missing workspace lint inheritance must fail".to_string()),
            Err(error) => error,
        };
        if error.contains("workspace = true") {
            Ok(())
        } else {
            Err(format!("unexpected error message: {error}"))
        }
    }

    #[test]
    fn accepts_real_forbid_unsafe_attribute() -> Result<(), String> {
        assert!(crate_root_has_forbid_unsafe(
            "#![forbid(unsafe_code)]\npub fn ok() {}\n"
        ));
        Ok(())
    }

    #[test]
    fn rejects_comment_only_forbid_unsafe() -> Result<(), String> {
        assert!(!crate_root_has_forbid_unsafe(
            "// #![forbid(unsafe_code)]\npub fn ok() {}\n"
        ));
        Ok(())
    }

    #[test]
    fn rejects_block_comment_forbid_unsafe() -> Result<(), String> {
        assert!(!crate_root_has_forbid_unsafe(
            "/*\n#![forbid(unsafe_code)]\n*/\npub fn ok() {}\n"
        ));
        Ok(())
    }

    #[test]
    fn rejects_forbid_unsafe_after_blank_line() -> Result<(), String> {
        assert!(!crate_root_has_forbid_unsafe(
            "\n#![forbid(unsafe_code)]\npub fn ok() {}\n"
        ));
        Ok(())
    }

    #[test]
    fn accepts_utf8_bom_prefix() -> Result<(), String> {
        assert!(crate_root_has_forbid_unsafe(
            "\u{FEFF}#![forbid(unsafe_code)]\npub fn ok() {}\n"
        ));
        Ok(())
    }

    #[test]
    fn accepts_crate_root_forbid_unsafe() -> Result<(), String> {
        let dir = tempfile::tempdir().map_err(|error| error.to_string())?;
        let src = dir.path().join("lib.rs");
        fs::write(&src, "#![forbid(unsafe_code)]\n").map_err(|error| error.to_string())?;

        check_target_root_forbids_unsafe(&src)?;
        Ok(())
    }

    #[test]
    fn rejects_missing_crate_root_forbid_unsafe() -> Result<(), String> {
        let dir = tempfile::tempdir().map_err(|error| error.to_string())?;
        let src = dir.path().join("lib.rs");
        fs::write(&src, "pub fn demo() {}\n").map_err(|error| error.to_string())?;

        let error = match check_target_root_forbids_unsafe(&src) {
            Ok(()) => return Err("missing crate root forbid must fail".to_string()),
            Err(error) => error,
        };
        if error.contains("forbid(unsafe_code)") {
            Ok(())
        } else {
            Err(format!("unexpected error message: {error}"))
        }
    }

    #[test]
    fn dependency_crate_name_uses_package_identity_not_rename() -> Result<(), String> {
        let dep = serde_json::json!({
            "name": "serde",
            "rename": "pyo3"
        });
        assert_eq!(
            super::dependency_crate_name(&dep),
            Some("serde".to_string())
        );
        Ok(())
    }

    #[test]
    fn renamed_pyo3_alias_does_not_bypass_forbidden_package_name() -> Result<(), String> {
        let dep = serde_json::json!({
            "name": "pyo3",
            "rename": "safe_alias"
        });
        assert_eq!(super::dependency_crate_name(&dep), Some("pyo3".to_string()));
        assert!(super::forbidden_dependency_violation("gateway-compute-core", "pyo3").is_some());
        Ok(())
    }

    #[test]
    fn serde_rename_to_pyo3_is_not_forbidden() -> Result<(), String> {
        assert!(super::forbidden_dependency_violation("gateway-compute-core", "serde").is_none());
        Ok(())
    }

    #[test]
    fn shared_kernel_reverse_dependency_is_forbidden() -> Result<(), String> {
        assert!(
            super::forbidden_dependency_violation("gateway-shared-kernel", "gateway-compute-core")
                .is_some()
        );
        Ok(())
    }

    #[test]
    fn package_dependency_map_collects_dependencies() -> Result<(), String> {
        let metadata = serde_json::json!({
            "packages": [{
                "name": "demo",
                "dependencies": [
                    {"name": "serde", "rename": null},
                    {"name": "pyo3", "rename": null, "target": "cfg(windows)"}
                ]
            }]
        });
        let map = super::package_dependency_map(&metadata)?;
        assert_eq!(map.get("demo").map(Vec::len), Some(2));
        assert!(map["demo"].contains(&"pyo3".to_string()));
        Ok(())
    }

    #[test]
    fn workspace_dependency_boundaries_are_clean() -> Result<(), String> {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
        let violations = super::check_crate_dependency_boundaries(&root);
        if violations.is_empty() {
            Ok(())
        } else {
            Err(violations.join("\n"))
        }
    }

    #[test]
    fn forbidden_dependency_fixture_is_detected() -> Result<(), String> {
        let metadata = serde_json::json!({
            "packages": [{
                "name": "gateway-compute-core",
                "dependencies": [{"name": "pyo3", "rename": null}]
            }]
        });
        let map = super::package_dependency_map(&metadata)?;
        let deps = map.get("gateway-compute-core").cloned().unwrap_or_default();
        assert!(deps.iter().any(|name| name == "pyo3"));
        Ok(())
    }
}
