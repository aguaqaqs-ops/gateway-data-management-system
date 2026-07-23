#![forbid(unsafe_code)]

use std::fs;
use std::io::{BufRead, BufReader, Cursor};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use gateway_architecture_check::{CheckConfig, run_checks};

#[test]
fn rejects_member_without_workspace_lint_inheritance() -> Result<(), String> {
    let root = tempfile::tempdir().map_err(|error| error.to_string())?;
    let rust_root = root.path().join("rust");
    write_minimal_workspace(&rust_root, "bad-member", false, "pub fn ok() {}\n")?;

    let config = CheckConfig {
        rust_workspace_root: rust_root,
        vnext_root: root.path().to_path_buf(),
    };

    match run_checks(&config) {
        Err(violations)
            if violations
                .iter()
                .any(|violation| violation.contains("workspace = true")) =>
        {
            Ok(())
        }
        Ok(()) => Err("expected workspace lint inheritance violation".to_string()),
        Err(violations) => Err(format!("unexpected violations: {violations:?}")),
    }
}

#[test]
fn rejects_crate_root_missing_forbid_unsafe() -> Result<(), String> {
    let root = tempfile::tempdir().map_err(|error| error.to_string())?;
    let rust_root = root.path().join("rust");
    write_minimal_workspace(&rust_root, "bad-member", true, "pub fn ok() {}\n")?;

    let config = CheckConfig {
        rust_workspace_root: rust_root,
        vnext_root: root.path().to_path_buf(),
    };

    match run_checks(&config) {
        Err(violations)
            if violations
                .iter()
                .any(|violation| violation.contains("forbid(unsafe_code)")) =>
        {
            Ok(())
        }
        Ok(()) => Err("expected crate root forbid(unsafe_code) violation".to_string()),
        Err(violations) => Err(format!("unexpected violations: {violations:?}")),
    }
}

#[test]
fn rejects_first_party_unsafe_in_member() -> Result<(), String> {
    let root = tempfile::tempdir().map_err(|error| error.to_string())?;
    let rust_root = root.path().join("rust");
    write_minimal_workspace(
        &rust_root,
        "bad-member",
        true,
        "#![forbid(unsafe_code)]\npub fn bad() { unsafe { () } }\n",
    )?;

    run_cargo_clippy_should_fail_with_code(&rust_root, "unsafe_code")
}

#[test]
fn rejects_compute_python_impl_to_pylist_pattern() -> Result<(), String> {
    let root = tempfile::tempdir().map_err(|error| error.to_string())?;
    let impl_src = root
        .path()
        .join("rust/gateway-compute-python-impl/src/lib.rs");
    if let Some(parent) = impl_src.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::write(&impl_src, "fn demo() { let _ = values.to_pylist(); }\n")
        .map_err(|error| error.to_string())?;

    let config = CheckConfig {
        rust_workspace_root: root.path().join("rust"),
        vnext_root: root.path().to_path_buf(),
    };

    match run_checks(&config) {
        Err(violations)
            if violations
                .iter()
                .any(|violation| violation.contains("to_pylist")) =>
        {
            Ok(())
        }
        Ok(()) => Err("expected compute-python-impl to_pylist violation".to_string()),
        Err(violations) => Err(format!("unexpected violations: {violations:?}")),
    }
}

#[test]
fn rejects_forbidden_hook_extension_workspace_member() -> Result<(), String> {
    let root = tempfile::tempdir().map_err(|error| error.to_string())?;
    let rust_root = root.path().join("rust");
    write_minimal_workspace(
        &rust_root,
        "gateway-compute-python-hooks",
        true,
        "#![forbid(unsafe_code)]\n",
    )?;

    bootstrap_fixture_workspace(&rust_root)?;

    let violations =
        gateway_architecture_check::check_forbidden_release_workspace_members(&rust_root);
    if violations
        .iter()
        .any(|violation| violation.contains("gateway-compute-python-hooks"))
    {
        Ok(())
    } else {
        Err(format!(
            "expected forbidden workspace member violation, got {violations:?}"
        ))
    }
}

#[test]
fn rejects_compute_python_to_pylist_pattern() -> Result<(), String> {
    let root = tempfile::tempdir().map_err(|error| error.to_string())?;
    let compute_src = root.path().join("rust/gateway-compute-python/src/lib.rs");
    if let Some(parent) = compute_src.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    fs::write(&compute_src, "fn demo() { let _ = values.to_pylist(); }\n")
        .map_err(|error| error.to_string())?;

    let config = CheckConfig {
        rust_workspace_root: root.path().join("rust"),
        vnext_root: root.path().to_path_buf(),
    };

    match run_checks(&config) {
        Err(violations)
            if violations
                .iter()
                .any(|violation| violation.contains("to_pylist")) =>
        {
            Ok(())
        }
        Ok(()) => Err("expected compute-python to_pylist violation".to_string()),
        Err(violations) => Err(format!("unexpected violations: {violations:?}")),
    }
}

#[test]
fn rejects_production_unwrap_shortcut() -> Result<(), String> {
    let root = tempfile::tempdir().map_err(|error| error.to_string())?;
    let rust_root = root.path().join("rust");
    write_minimal_workspace(
        &rust_root,
        "bad-member",
        true,
        "#![forbid(unsafe_code)]\npub fn bad(opt: Option<i32>) -> i32 { opt.unwrap() }\n",
    )?;

    run_cargo_clippy_should_fail_with_code(&rust_root, "clippy::unwrap_used")
}

#[test]
fn rejects_production_panic_shortcut() -> Result<(), String> {
    let root = tempfile::tempdir().map_err(|error| error.to_string())?;
    let rust_root = root.path().join("rust");
    write_minimal_workspace(
        &rust_root,
        "bad-member",
        true,
        "#![forbid(unsafe_code)]\npub fn bad() { panic!(\"production shortcut\") }\n",
    )?;

    run_cargo_clippy_should_fail_with_code(&rust_root, "clippy::panic")
}

#[test]
fn rejects_renamed_hook_workspace_member() -> Result<(), String> {
    let root = tempfile::tempdir().map_err(|error| error.to_string())?;
    let rust_root = root.path().join("rust");
    write_minimal_workspace(
        &rust_root,
        "gateway-compute-fault-inject",
        true,
        "#![forbid(unsafe_code)]\n",
    )?;

    let violations = gateway_architecture_check::check_production_release_inventory(&rust_root);
    if violations.iter().any(|violation| {
        violation.contains("gateway-compute-fault-inject")
            && (violation.contains("unexpected workspace member")
                || violation.contains("suspicious hook package"))
    }) {
        Ok(())
    } else {
        Err(format!(
            "expected renamed hook workspace member violation, got {violations:?}"
        ))
    }
}

#[test]
fn rejects_compute_adapter_dep_on_renamed_hook_crate() -> Result<(), String> {
    let root = tempfile::tempdir().map_err(|error| error.to_string())?;
    let rust_root = root.path().join("rust");
    write_hooked_compute_workspace(&rust_root)?;

    let violations = gateway_architecture_check::check_production_release_inventory(&rust_root);
    if violations.iter().any(|violation| {
        violation.contains("gateway-compute-python-impl")
            && violation.contains("gateway-compute-fault-inject")
    }) {
        Ok(())
    } else {
        Err(format!(
            "expected adapter dependency on renamed hook crate violation, got {violations:?}"
        ))
    }
}

#[test]
fn rejects_extra_hook_cdylib_target_in_compute_python_manifest() -> Result<(), String> {
    let root = tempfile::tempdir().map_err(|error| error.to_string())?;
    let rust_root = root.path().join("rust");
    write_compute_python_with_extra_hook_cdylib(&rust_root)?;

    let violations = gateway_architecture_check::check_production_release_inventory(&rust_root);
    if violations.iter().any(|violation| {
        violation.contains("gateway-compute-python")
            && (violation.contains("gateway_compute_hooks")
                || violation.contains("test cdylib target"))
    }) {
        Ok(())
    } else {
        Err(format!(
            "expected extra hook cdylib target violation, got {violations:?}"
        ))
    }
}

fn write_hooked_compute_workspace(rust_root: &Path) -> Result<(), String> {
    fs::create_dir_all(rust_root.join("gateway-compute-fault-inject/src"))
        .map_err(|error| error.to_string())?;
    fs::create_dir_all(rust_root.join("gateway-compute-python-impl/src"))
        .map_err(|error| error.to_string())?;
    fs::create_dir_all(rust_root.join("gateway-compute-core/src"))
        .map_err(|error| error.to_string())?;

    fs::write(
        rust_root.join("Cargo.toml"),
        r#"[workspace]
members = [
    "gateway-compute-core",
    "gateway-compute-python-impl",
    "gateway-compute-fault-inject",
]
resolver = "3"

[workspace.lints.rust]
unsafe_code = "forbid"
unstable_features = "forbid"

[workspace.lints.clippy]
unwrap_used = "deny"
expect_used = "deny"
panic = "deny"
todo = "deny"
unimplemented = "deny"
dbg_macro = "deny"
"#,
    )
    .map_err(|error| error.to_string())?;

    fs::write(
        rust_root.join("rust-toolchain.toml"),
        "[toolchain]\nchannel = \"1.97.0\"\n",
    )
    .map_err(|error| error.to_string())?;

    for (name, deps) in [
        ("gateway-compute-core", ""),
        ("gateway-compute-fault-inject", ""),
        (
            "gateway-compute-python-impl",
            "gateway-compute-core = { path = \"../gateway-compute-core\" }\ngateway-compute-fault-inject = { path = \"../gateway-compute-fault-inject\" }\n",
        ),
    ] {
        fs::write(
            rust_root.join(name).join("Cargo.toml"),
            format!(
                r#"[package]
name = "{name}"
version = "0.1.0"
edition = "2024"

[lints]
workspace = true

[dependencies]
{deps}"#
            ),
        )
        .map_err(|error| error.to_string())?;
        fs::write(
            rust_root.join(name).join("src/lib.rs"),
            "#![forbid(unsafe_code)]\n",
        )
        .map_err(|error| error.to_string())?;
    }

    bootstrap_fixture_workspace(rust_root)
}

fn write_compute_python_with_extra_hook_cdylib(rust_root: &Path) -> Result<(), String> {
    fs::create_dir_all(rust_root.join("gateway-compute-python/src"))
        .map_err(|error| error.to_string())?;
    fs::create_dir_all(rust_root.join("gateway-compute-python-impl/src"))
        .map_err(|error| error.to_string())?;
    fs::create_dir_all(rust_root.join("gateway-compute-core/src"))
        .map_err(|error| error.to_string())?;

    fs::write(
        rust_root.join("Cargo.toml"),
        r#"[workspace]
members = [
    "gateway-compute-core",
    "gateway-compute-python-impl",
    "gateway-compute-python",
]
resolver = "3"

[workspace.lints.rust]
unsafe_code = "forbid"
unstable_features = "forbid"

[workspace.lints.clippy]
unwrap_used = "deny"
expect_used = "deny"
panic = "deny"
todo = "deny"
unimplemented = "deny"
dbg_macro = "deny"
"#,
    )
    .map_err(|error| error.to_string())?;

    fs::write(
        rust_root.join("rust-toolchain.toml"),
        "[toolchain]\nchannel = \"1.97.0\"\n",
    )
    .map_err(|error| error.to_string())?;

    for (name, manifest) in [
        (
            "gateway-compute-core",
            r#"[package]
name = "gateway-compute-core"
version = "0.1.0"
edition = "2024"

[lints]
workspace = true
"#,
        ),
        (
            "gateway-compute-python-impl",
            r#"[package]
name = "gateway-compute-python-impl"
version = "0.1.0"
edition = "2024"

[lints]
workspace = true

[dependencies]
gateway-compute-core = { path = "../gateway-compute-core" }
"#,
        ),
        (
            "gateway-compute-python",
            r#"[package]
name = "gateway-compute-python"
version = "0.1.0"
edition = "2024"

[lints]
workspace = true

[lib]
name = "gateway_compute"
crate-type = ["cdylib", "rlib"]

[[test]]
name = "gateway_compute_hooks"
path = "tests/hooks.rs"
crate-type = ["cdylib"]

[dependencies]
gateway-compute-python-impl = { path = "../gateway-compute-python-impl" }
"#,
        ),
    ] {
        fs::write(rust_root.join(name).join("Cargo.toml"), manifest)
            .map_err(|error| error.to_string())?;
        fs::write(
            rust_root.join(name).join("src/lib.rs"),
            "#![forbid(unsafe_code)]\n",
        )
        .map_err(|error| error.to_string())?;
    }

    bootstrap_fixture_workspace(rust_root)
}

fn write_minimal_workspace(
    rust_root: &Path,
    member_name: &str,
    inherit_lints: bool,
    lib_rs: &str,
) -> Result<(), String> {
    fs::create_dir_all(rust_root.join(member_name).join("src"))
        .map_err(|error| error.to_string())?;

    fs::write(
        rust_root.join("Cargo.toml"),
        r#"[workspace]
members = ["MEMBER"]
resolver = "3"

[workspace.lints.rust]
unsafe_code = "forbid"
unstable_features = "forbid"

[workspace.lints.clippy]
unwrap_used = "deny"
expect_used = "deny"
panic = "deny"
todo = "deny"
unimplemented = "deny"
dbg_macro = "deny"
"#
        .replace("MEMBER", member_name),
    )
    .map_err(|error| error.to_string())?;

    fs::write(
        rust_root.join("rust-toolchain.toml"),
        "[toolchain]\nchannel = \"1.97.0\"\n",
    )
    .map_err(|error| error.to_string())?;

    let manifest = if inherit_lints {
        format!(
            r#"[package]
name = "{member_name}"
version = "0.1.0"
edition = "2024"

[lints]
workspace = true
"#
        )
    } else {
        format!(
            r#"[package]
name = "{member_name}"
version = "0.1.0"
edition = "2024"
"#
        )
    };

    fs::write(rust_root.join(member_name).join("Cargo.toml"), manifest)
        .map_err(|error| error.to_string())?;
    fs::write(rust_root.join(member_name).join("src/lib.rs"), lib_rs)
        .map_err(|error| error.to_string())?;

    bootstrap_fixture_workspace(rust_root)?;

    Ok(())
}

fn bootstrap_fixture_workspace(rust_root: &Path) -> Result<(), String> {
    let output = Command::new("cargo")
        .arg("generate-lockfile")
        .arg("--offline")
        .current_dir(rust_root)
        .output()
        .map_err(|error| error.to_string())?;

    if output.status.success() {
        Ok(())
    } else {
        Err(format!(
            "failed to bootstrap negative fixture workspace: {}",
            String::from_utf8_lossy(&output.stderr)
        ))
    }
}

fn run_cargo_clippy_should_fail_with_code(
    rust_root: &PathBuf,
    expected_code: &str,
) -> Result<(), String> {
    let output = Command::new("cargo")
        .arg("clippy")
        .arg("--all-targets")
        .arg("--message-format=json")
        .arg("--offline")
        .arg("--")
        .arg("-D")
        .arg("warnings")
        .current_dir(rust_root)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .map_err(|error| error.to_string())?;

    if output.status.success() {
        return Err("expected clippy to fail for negative fixture".to_string());
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    let combined = format!("{stdout}\n{stderr}");

    let codes = collect_diagnostic_codes(&combined);
    if codes.iter().any(|code| code == expected_code) {
        return Ok(());
    }

    if codes.is_empty() && is_infrastructure_failure(&combined) {
        return Err(format!(
            "negative fixture hit infrastructure failure instead of expected lint: {combined}"
        ));
    }

    Err(format!(
        "expected diagnostic code `{expected_code}`, found {codes:?}; output:\n{combined}"
    ))
}

fn is_infrastructure_failure(output: &str) -> bool {
    const MARKERS: &[&str] = &[
        "failed to fetch",
        "could not find `Cargo.toml`",
        "failed to download",
        "failed to resolve",
        "network unreachable",
        "failed to run `rustc`",
        "can't find crate",
    ];

    let lowered = output.to_ascii_lowercase();
    MARKERS.iter().any(|marker| lowered.contains(marker))
}

fn collect_diagnostic_codes(output: &str) -> Vec<String> {
    let mut codes = Vec::new();

    for line in output.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }

        let value: serde_json::Value = match serde_json::from_str(line) {
            Ok(value) => value,
            Err(_) => continue,
        };

        if value.get("reason").and_then(|reason| reason.as_str()) != Some("compiler-message") {
            continue;
        }

        let message = match value.get("message") {
            Some(message) => message,
            None => continue,
        };

        if let Some(code) = message
            .get("code")
            .and_then(|code| code.get("code"))
            .and_then(|code| code.as_str())
        {
            codes.push(code.to_string());
        }
    }

    codes
}

#[test]
fn diagnostic_parser_finds_expected_code() -> Result<(), String> {
    let sample =
        r#"{"reason":"compiler-message","message":{"code":{"code":"clippy::unwrap_used"}}}"#;
    let codes = collect_diagnostic_codes(sample);
    if codes.iter().any(|code| code == "clippy::unwrap_used") {
        Ok(())
    } else {
        Err(format!("unexpected parsed codes: {codes:?}"))
    }
}

#[test]
fn diagnostic_parser_ignores_non_json_lines() -> Result<(), String> {
    let sample = "warning: unrelated\n{\"reason\":\"compiler-message\",\"message\":{\"code\":{\"code\":\"unsafe_code\"}}}\n";
    let reader = BufReader::new(Cursor::new(sample));
    let mut combined = String::new();
    for line in reader.lines() {
        combined.push_str(&line.map_err(|error| error.to_string())?);
        combined.push('\n');
    }
    let codes = collect_diagnostic_codes(&combined);
    if codes == vec!["unsafe_code".to_string()] {
        Ok(())
    } else {
        Err(format!("unexpected parsed codes: {codes:?}"))
    }
}

#[test]
fn rejects_renamed_compute_hook_feature() -> Result<(), String> {
    let root = tempfile::tempdir().map_err(|error| error.to_string())?;
    let rust_root = root.path().join("rust");
    let manifest = rust_root.join("gateway-compute-python-impl/Cargo.toml");
    fs::create_dir_all(manifest.parent().ok_or("missing parent")?)
        .map_err(|error| error.to_string())?;
    fs::write(
        &manifest,
        r#"[package]
name = "gateway-compute-python-impl"
version = "0.1.0"
edition = "2021"

[features]
fault-injection = []
default = []
"#,
    )
    .map_err(|error| error.to_string())?;

    let violations =
        gateway_architecture_check::check_forbidden_compute_test_hook_features(&rust_root);
    if violations
        .iter()
        .any(|violation| violation.contains("fault-injection"))
    {
        Ok(())
    } else {
        Err(format!(
            "expected renamed hook feature violation, got {violations:?}"
        ))
    }
}
