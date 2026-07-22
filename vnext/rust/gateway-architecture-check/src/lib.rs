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
    violations.extend(check_compute_adapter_source_patterns(&config.vnext_root));
    violations.extend(check_crate_dependency_boundaries(
        &config.rust_workspace_root,
    ));
    violations.extend(check_forbidden_release_workspace_members(
        &config.rust_workspace_root,
    ));
    violations.extend(check_forbidden_compute_test_hook_features(
        &config.rust_workspace_root,
    ));
    violations.extend(check_production_release_inventory(
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

    let package_dependencies = match package_resolved_dependency_names(&metadata) {
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
            "gateway-compute-core"
            | "gateway-compute-python"
            | "gateway-compute-python-impl"
            | "gateway-shared-kernel" => {
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

const FORBIDDEN_RELEASE_WORKSPACE_MEMBERS: &[&str] = &["gateway-compute-python-hooks"];

const FORBIDDEN_COMPUTE_HOOK_FEATURE_TOKENS: &[&str] = &[
    "test-probe",
    "test-hook",
    "testhook",
    "fault-inject",
    "fault-injection",
    "inject-fault",
];

pub fn is_suspicious_compute_hook_feature(feature_name: &str) -> bool {
    let lowered = feature_name.replace('_', "-").to_ascii_lowercase();
    FORBIDDEN_COMPUTE_HOOK_FEATURE_TOKENS
        .iter()
        .any(|token| lowered.contains(token))
        || (lowered.contains("hook") && (lowered.contains("test") || lowered.contains("fault")))
        || (lowered.contains("probe") && lowered.contains("test"))
        || (lowered.contains("inject") && (lowered.contains("test") || lowered.contains("fault")))
}

pub fn is_suspicious_hook_package(name: &str) -> bool {
    if FORBIDDEN_RELEASE_WORKSPACE_MEMBERS.contains(&name) {
        return true;
    }

    let lowered = name.replace('_', "-").to_ascii_lowercase();
    let has_hook = lowered.contains("hook");
    let has_probe = lowered.contains("probe");
    let has_fault = lowered.contains("fault");
    let has_inject = lowered.contains("inject");

    (has_hook && (has_probe || has_fault || has_inject))
        || (has_probe && has_fault)
        || (has_inject && (has_fault || has_hook))
        || lowered.contains("fault-inject")
        || lowered.contains("test-hook")
        || lowered.contains("test-probe")
}

const ALLOWED_PRODUCTION_WORKSPACE_MEMBERS: &[&str] = &[
    "gateway-architecture-check",
    "gateway-compute-core",
    "gateway-compute-python",
    "gateway-compute-python-impl",
    "gateway-shared-kernel",
];

const EXPECTED_COMPUTE_PYTHON_CDYLIB_TARGET: &str = "gateway_compute";

fn collect_manifest_feature_names(contents: &str) -> Vec<String> {
    let mut in_features = false;
    let mut names = Vec::new();
    for line in contents.lines() {
        let trimmed = line.trim();
        if trimmed == "[features]" {
            in_features = true;
            continue;
        }
        if in_features && trimmed.starts_with('[') {
            break;
        }
        if !in_features {
            continue;
        }
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let Some((name, _)) = trimmed.split_once('=') else {
            continue;
        };
        let name = name.trim();
        if !name.is_empty() {
            names.push(name.to_string());
        }
    }
    names
}

pub fn check_forbidden_compute_test_hook_features(rust_workspace_root: &Path) -> Vec<String> {
    let mut violations = Vec::new();
    let manifests = [
        rust_workspace_root.join("gateway-compute-python-impl/Cargo.toml"),
        rust_workspace_root.join("gateway-compute-python/Cargo.toml"),
    ];

    for manifest in manifests {
        let contents = match fs::read_to_string(&manifest) {
            Ok(contents) => contents,
            Err(error) => {
                violations.push(format!("failed to read {}: {error}", manifest.display()));
                continue;
            }
        };
        for feature in collect_manifest_feature_names(&contents) {
            if is_suspicious_compute_hook_feature(&feature) {
                violations.push(format!(
                    "forbidden production test-hook feature `{feature}` in {}",
                    manifest.display()
                ));
            }
        }
    }

    violations
}

pub fn check_forbidden_release_workspace_members(rust_workspace_root: &Path) -> Vec<String> {
    let members = match discover_workspace_members(rust_workspace_root) {
        Ok(members) => members,
        Err(error) => return vec![error],
    };

    FORBIDDEN_RELEASE_WORKSPACE_MEMBERS
        .iter()
        .filter_map(|forbidden| {
            if members.iter().any(|member| member.name == *forbidden) {
                Some(format!(
                    "forbidden release workspace member `{forbidden}` must not be listed in workspace members"
                ))
            } else {
                None
            }
        })
        .collect()
}

pub fn check_production_release_inventory(rust_workspace_root: &Path) -> Vec<String> {
    let metadata = match fetch_cargo_metadata_with_deps(rust_workspace_root) {
        Ok(metadata) => metadata,
        Err(error) => return vec![error],
    };
    check_production_release_inventory_from_metadata(&metadata)
}

pub fn check_production_release_inventory_from_metadata(
    metadata: &serde_json::Value,
) -> Vec<String> {
    let workspace_root = match metadata["workspace_root"].as_str() {
        Some(root) => root,
        None => return vec!["cargo metadata missing workspace_root".to_string()],
    };

    let packages = match metadata["packages"].as_array() {
        Some(packages) => packages,
        None => return vec!["cargo metadata missing packages".to_string()],
    };

    let package_dependencies = match package_resolved_dependency_names(metadata) {
        Ok(map) => map,
        Err(error) => return vec![error],
    };

    let mut violations = Vec::new();
    let mut first_party_names = BTreeSet::new();

    for package in packages {
        let manifest_path = match package["manifest_path"].as_str() {
            Some(path) => PathBuf::from(path),
            None => continue,
        };
        if !manifest_path.starts_with(workspace_root) {
            continue;
        }

        let name = match package["name"].as_str() {
            Some(name) => name,
            None => continue,
        };
        first_party_names.insert(name.to_string());

        if !ALLOWED_PRODUCTION_WORKSPACE_MEMBERS.contains(&name) {
            violations.push(format!(
                "production release inventory contains unexpected workspace member `{name}`"
            ));
        }

        if is_suspicious_hook_package(name) {
            violations.push(format!(
                "production release inventory contains suspicious hook package `{name}`"
            ));
        }

        if name == "gateway-compute-python" {
            violations.extend(check_compute_python_cdylib_targets(package, &manifest_path));
        }
    }

    if let Some(dependencies) = package_dependencies.get("gateway-compute-python-impl") {
        for dependency in dependencies {
            if is_suspicious_hook_package(dependency) {
                violations.push(format!(
                    "gateway-compute-python-impl must not depend on suspicious hook package `{dependency}`"
                ));
            }
        }
    }

    if first_party_names.is_empty() {
        violations.push(
            "production release inventory found no first-party workspace packages".to_string(),
        );
    }

    violations
}

fn check_compute_python_cdylib_targets(
    package: &serde_json::Value,
    manifest_path: &Path,
) -> Vec<String> {
    let mut violations = Vec::new();
    let mut cdylib_targets = BTreeSet::new();

    if let Some(targets) = package["targets"].as_array() {
        for target in targets {
            let is_cdylib = target["kind"].as_array().is_some_and(|kinds| {
                kinds
                    .iter()
                    .filter_map(|kind| kind.as_str())
                    .any(|kind| kind == "cdylib")
            });
            if !is_cdylib {
                continue;
            }

            let target_name = target["name"].as_str().unwrap_or("<unknown>").to_string();
            if is_suspicious_hook_package(&target_name) {
                violations.push(format!(
                    "gateway-compute-python must not define suspicious cdylib target `{target_name}`"
                ));
            }
            cdylib_targets.insert(target_name);
        }
    }

    if cdylib_targets.len() > 1 {
        violations.push(format!(
            "gateway-compute-python must define exactly one cdylib target, found {:?}",
            cdylib_targets
        ));
    } else if cdylib_targets.len() == 1
        && !cdylib_targets.contains(EXPECTED_COMPUTE_PYTHON_CDYLIB_TARGET)
    {
        violations.push(format!(
            "gateway-compute-python cdylib target must be `{EXPECTED_COMPUTE_PYTHON_CDYLIB_TARGET}`"
        ));
    }

    let manifest_contents = match fs::read_to_string(manifest_path) {
        Ok(contents) => contents,
        Err(error) => {
            violations.push(format!(
                "failed to read {} for cdylib inventory check: {error}",
                manifest_path.display()
            ));
            return violations;
        }
    };

    for test_target in collect_manifest_test_cdylib_targets(&manifest_contents) {
        violations.push(format!(
            "gateway-compute-python manifest must not declare test cdylib target `{test_target}`"
        ));
    }

    violations
}

fn collect_manifest_test_cdylib_targets(contents: &str) -> Vec<String> {
    let mut names = Vec::new();
    let mut in_test = false;
    let mut current_name: Option<String> = None;
    let mut current_is_cdylib = false;

    for line in contents.lines() {
        let trimmed = line.trim();
        if trimmed == "[[test]]" {
            if in_test
                && current_is_cdylib
                && let Some(name) = current_name.take()
            {
                names.push(name);
            }
            in_test = true;
            current_name = None;
            current_is_cdylib = false;
            continue;
        }
        if in_test && trimmed.starts_with("[[") {
            if current_is_cdylib && let Some(name) = current_name.take() {
                names.push(name);
            }
            in_test = false;
            current_name = None;
            current_is_cdylib = false;
            continue;
        }
        if !in_test {
            continue;
        }
        if let Some((key, value)) = trimmed.split_once('=') {
            let key = key.trim();
            let value = value.trim().trim_matches('"');
            if key == "name" {
                current_name = Some(value.to_string());
            }
            if key == "crate-type" && value.contains("cdylib") {
                current_is_cdylib = true;
            }
        }
    }

    if in_test
        && current_is_cdylib
        && let Some(name) = current_name
    {
        names.push(name);
    }

    names
}

fn package_resolved_dependency_names(
    metadata: &serde_json::Value,
) -> Result<std::collections::BTreeMap<String, BTreeSet<String>>, String> {
    let packages = metadata["packages"]
        .as_array()
        .ok_or_else(|| "cargo metadata missing packages".to_string())?;

    let mut id_to_name = std::collections::BTreeMap::new();
    for package in packages {
        let id = package["id"]
            .as_str()
            .ok_or_else(|| "cargo metadata package missing id".to_string())?;
        let name = package["name"]
            .as_str()
            .ok_or_else(|| "cargo metadata package missing name".to_string())?;
        id_to_name.insert(id.to_string(), name.to_string());
    }

    let nodes = metadata["resolve"]["nodes"]
        .as_array()
        .ok_or_else(|| "cargo metadata missing resolve.nodes".to_string())?;

    let mut map = std::collections::BTreeMap::new();
    for node in nodes {
        let id = node["id"]
            .as_str()
            .ok_or_else(|| "resolve node missing id".to_string())?;
        let Some(name) = id_to_name.get(id) else {
            continue;
        };

        let mut dependencies = BTreeSet::new();
        if let Some(deps) = node["deps"].as_array() {
            for dep in deps {
                let dep_id = dep["pkg"].as_str().unwrap_or_default();
                if let Some(dep_name) = id_to_name.get(dep_id) {
                    dependencies.insert(dep_name.clone());
                }
            }
        }
        map.insert(name.clone(), dependencies);
    }

    Ok(map)
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

fn forbidden_dependency_violation(crate_name: &str, dependency: &str) -> Option<String> {
    match crate_name {
        "gateway-compute-core" => {
            if matches!(
                dependency,
                "pyo3"
                    | "pyo3-arrow"
                    | "gateway-compute-python"
                    | "gateway-compute-python-impl"
                    | "gateway-artifact-store"
            ) {
                return Some(format!("{crate_name} must not depend on {dependency}"));
            }
            if dependency == "reqwest" || dependency == "tokio" || dependency == "hyper" {
                return Some(format!(
                    "{crate_name} must not depend on network crate `{dependency}`"
                ));
            }
        }
        "gateway-compute-python" | "gateway-compute-python-impl" => {
            if dependency == "gateway-shared-kernel" {
                return Some(format!(
                    "{crate_name} must not directly depend on gateway-shared-kernel"
                ));
            }
        }
        "gateway-shared-kernel"
            if dependency.starts_with("arrow-")
                || dependency.starts_with("pyo3")
                || dependency == "gateway-compute-core"
                || dependency == "gateway-compute-python"
                || dependency == "gateway-compute-python-impl" =>
        {
            return Some(format!(
                "gateway-shared-kernel must not depend on {dependency}"
            ));
        }
        _ => {}
    }
    None
}

fn check_compute_adapter_source_patterns(vnext_root: &Path) -> Vec<String> {
    let mut violations = Vec::new();
    let roots = [
        vnext_root.join("rust/gateway-compute-python-impl/src"),
        vnext_root.join("rust/gateway-compute-python/src"),
        vnext_root.join("rust/gateway-compute-python/python"),
    ];

    for root in roots {
        if !root.is_dir() {
            continue;
        }
        if let Err(error) = walk_source_files(&root, &mut |path| {
            let contents = match fs::read_to_string(path) {
                Ok(contents) => contents,
                Err(error) => {
                    violations.push(format!("failed to read {}: {error}", path.display()));
                    return;
                }
            };

            for (line_number, line) in contents.lines().enumerate() {
                if let Some(reason) = compute_python_line_violation(line) {
                    violations.push(format!(
                        "gateway-compute adapter source policy violation in {}:{}: {reason} (`{line}`)",
                        path.display(),
                        line_number + 1
                    ));
                }
            }
        }) {
            violations.push(error);
        }
    }

    violations
}

fn compute_python_line_violation(line: &str) -> Option<&'static str> {
    let trimmed = line.trim();
    if trimmed == "#![forbid(unsafe_code)]" {
        return None;
    }
    if trimmed.contains("feature = \"test-probes\"") || trimmed.contains("feature = \"test-hooks\"")
    {
        return Some("forbidden production test-hook feature gate");
    }
    if trimmed.contains("to_pylist") {
        return Some("forbidden materialization API `to_pylist`");
    }
    if trimmed.contains("to_pydict") {
        return Some("forbidden materialization API `to_pydict`");
    }
    if trimmed.contains("combine_chunks") {
        return Some("forbidden table materialization `combine_chunks`");
    }
    if trimmed.contains("gateway_shared_kernel") {
        return Some("forbidden direct shared-kernel import");
    }
    if trimmed.contains("unsafe ") || trimmed.contains(" unsafe") || trimmed == "unsafe" {
        return Some("forbidden `unsafe` usage");
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
    fn renamed_pyo3_alias_does_not_bypass_forbidden_package_name() -> Result<(), String> {
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
    fn compute_python_impl_shared_kernel_dependency_is_forbidden() -> Result<(), String> {
        assert!(
            super::forbidden_dependency_violation(
                "gateway-compute-python-impl",
                "gateway-shared-kernel"
            )
            .is_some()
        );
        Ok(())
    }

    #[test]
    fn compute_core_must_not_depend_on_compute_python_impl() -> Result<(), String> {
        assert!(
            super::forbidden_dependency_violation(
                "gateway-compute-core",
                "gateway-compute-python-impl"
            )
            .is_some()
        );
        Ok(())
    }

    #[test]
    fn shared_kernel_must_not_depend_on_compute_python_impl() -> Result<(), String> {
        assert!(
            super::forbidden_dependency_violation(
                "gateway-shared-kernel",
                "gateway-compute-python-impl"
            )
            .is_some()
        );
        Ok(())
    }

    #[test]
    fn package_resolved_dependency_names_follows_resolve_graph() -> Result<(), String> {
        let metadata = serde_json::json!({
            "packages": [
                {"id": "path+0", "name": "gateway-compute-python-impl"},
                {"id": "path+1", "name": "gateway-shared-kernel"}
            ],
            "resolve": {
                "nodes": [
                    {"id": "path+0", "deps": [{"pkg": "path+1"}]},
                    {"id": "path+1", "deps": []}
                ]
            }
        });
        let map = super::package_resolved_dependency_names(&metadata)?;
        assert!(map["gateway-compute-python-impl"].contains("gateway-shared-kernel"));
        Ok(())
    }

    #[test]
    fn compute_python_line_violation_detects_banned_patterns() {
        assert!(super::compute_python_line_violation("values.to_pylist()").is_some());
        assert!(super::compute_python_line_violation("data.combine_chunks()").is_some());
        assert!(super::compute_python_line_violation("import gateway_shared_kernel").is_some());
        assert!(super::compute_python_line_violation("#![forbid(unsafe_code)]").is_none());
    }

    #[test]
    fn suspicious_compute_hook_feature_detects_renamed_tokens() {
        assert!(super::is_suspicious_compute_hook_feature("test-probes"));
        assert!(super::is_suspicious_compute_hook_feature("fault-injection"));
        assert!(super::is_suspicious_compute_hook_feature(
            "custom_test_hook"
        ));
        assert!(!super::is_suspicious_compute_hook_feature("default"));
    }

    #[test]
    fn suspicious_hook_package_detects_renamed_members() {
        assert!(super::is_suspicious_hook_package(
            "gateway-compute-python-hooks"
        ));
        assert!(super::is_suspicious_hook_package(
            "gateway-compute-fault-inject"
        ));
        assert!(!super::is_suspicious_hook_package("gateway-compute-python"));
    }

    #[test]
    fn production_release_inventory_is_clean() -> Result<(), String> {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..");
        let violations = super::check_production_release_inventory(&root);
        if violations.is_empty() {
            Ok(())
        } else {
            Err(violations.join("\n"))
        }
    }
}
