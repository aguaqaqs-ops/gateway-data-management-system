"""Governance and golden security policy tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.golden.security import assert_golden_payload_safe
from gateway_conformance.scenario.validate import validate_scenario
from support import base_manifest, write_scenario_tree


def test_unknown_sanitization_policy_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "sanitized"
    manifest, golden = base_manifest(scenario_suffix="sanitized")
    manifest["provenance"] = {
        "kind": "SANITIZED_REGRESSION",
        "source_reference": "opaque-ref",
        "sanitization_policy": {"policy_id": "unknown-policy", "version": 1},
        "approval": {"authority": "test-review-authority", "reference": "approval-ref"},
    }
    write_scenario_tree(root, manifest, golden_bytes=golden)
    with pytest.raises(ConformanceValidationError, match="unknown sanitization policy"):
        validate_scenario(root)


def test_unknown_approval_authority_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "bad-approval"
    manifest, golden = base_manifest(scenario_suffix="bad-approval")
    manifest["provenance"] = {
        "kind": "SANITIZED_REGRESSION",
        "source_reference": "opaque-ref",
        "sanitization_policy": {"policy_id": "test-sanitization-policy", "version": 1},
        "approval": {"authority": "unknown-authority", "reference": "approval-ref"},
    }
    write_scenario_tree(root, manifest, golden_bytes=golden)
    with pytest.raises(ConformanceValidationError, match="unknown approval authority"):
        validate_scenario(root)


def test_unknown_fault_boundary_rejected(tmp_path: Path) -> None:
    root = tmp_path / "recovery" / "test-capability" / "bad-fault"
    manifest, golden = base_manifest(
        track="recovery",
        scenario_suffix="bad-fault",
        kind="recovery",
        include_fault=True,
    )
    manifest["fault"]["boundary"] = "unknown-boundary"
    write_scenario_tree(root, manifest, golden_bytes=golden)
    with pytest.raises(ConformanceValidationError, match="unknown fault boundary"):
        validate_scenario(root)


def test_golden_payload_with_host_path_rejected() -> None:
    with pytest.raises(ConformanceValidationError, match="host path"):
        assert_golden_payload_safe({"note": "/etc/passwd"})


@pytest.mark.parametrize(
    "payload",
    [
        r"C:\Users\secret",
        r"D:\a\b",
        r"\\server\share\x",
        "C:/Users/secret",
        {"nested": [r"C:\Users\secret"]},
        {"note": r"\\server\share\x"},
        "file:///tmp/secret",
        "file:///home/alice/.ssh/id_rsa",
        {"uri": "file:///tmp/secret"},
        r"path=C:\Users\secret\a.yaml",
        r"[C:\Users\secret]",
        r"{C:\Users\secret}",
        r"->C:\Users\secret",
        "file:%2F%2F%2Fetc%2Fpasswd",
        "file:%2F%2Ftmp%2Fx",
        "FILE:%2F%2F%2Ftmp%2Fa",
        {"note": "file:%2F%2F%2Ftmp%2Fx"},
        "／etc／passwd",
        "∕home∕alice",
        "C:＼Users＼secret",
        "file:／／／etc／passwd",
        "~alice/.ssh/id_rsa",
        "~root/x",
        "~/secret",
        "%7Ealice%2F.ssh",
    ],
)
def test_golden_payload_rejects_windows_and_unc_paths(payload: object) -> None:
    with pytest.raises(ConformanceValidationError, match="absolute paths|host path"):
        assert_golden_payload_safe(payload)


@pytest.mark.parametrize(
    "payload",
    [
        "ok-business-token",
        "sha256:" + "0" * 64,
        "expected/result.golden.json",
        {"path": "expected/result.golden.json"},
    ],
)
def test_golden_payload_accepts_safe_strings(payload: object) -> None:
    assert_golden_payload_safe(payload)


def test_source_reference_host_path_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "host-src"
    manifest, golden = base_manifest(scenario_suffix="host-src")
    manifest["provenance"] = {
        "kind": "SANITIZED_REGRESSION",
        "source_reference": "/root/private/raw.sql",
        "sanitization_policy": {"policy_id": "test-sanitization-policy", "version": 1},
        "approval": {"authority": "test-review-authority", "reference": "approval-ref"},
    }
    write_scenario_tree(root, manifest, golden_bytes=golden)
    with pytest.raises(ConformanceValidationError, match="source_reference"):
        validate_scenario(root)


def test_approval_reference_host_path_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "host-approval"
    manifest, golden = base_manifest(scenario_suffix="host-approval")
    manifest["provenance"] = {
        "kind": "SANITIZED_REGRESSION",
        "source_reference": "opaque-ref",
        "sanitization_policy": {"policy_id": "test-sanitization-policy", "version": 1},
        "approval": {"authority": "test-review-authority", "reference": "/etc/passwd"},
    }
    write_scenario_tree(root, manifest, golden_bytes=golden)
    with pytest.raises(ConformanceValidationError, match="approval.reference"):
        validate_scenario(root)


def test_unknown_fault_target_rejected(tmp_path: Path) -> None:
    root = tmp_path / "recovery" / "test-capability" / "bad-target"
    manifest, golden = base_manifest(
        track="recovery",
        scenario_suffix="bad-target",
        kind="recovery",
        include_fault=True,
    )
    manifest["fault"]["target"] = "unknown-target"
    write_scenario_tree(root, manifest, golden_bytes=golden)
    with pytest.raises(ConformanceValidationError, match="unknown fault target"):
        validate_scenario(root)


@pytest.mark.parametrize(
    "reference",
    [
        "https://example.com/raw.sql",
        "http://example.com/raw.sql",
        "file:/etc/passwd",
        "file:///etc/passwd",
        r"C:\Users\secret\raw.sql",
        "C:/Users/secret/raw.sql",
        r"\\server\share\x",
        r"..\secret",
        r"foo\..\bar",
        "../secret",
        "/root/private/raw.sql",
        "http:example.com",
        "https:evil",
        "file:etc",
        "c:windows",
        "javascript:alert",
        "HTTP:HOST",
        "data:text",
        "ftp:host",
        "blob:id",
        "mailto:user",
        "about:blank",
        "vbscript:x",
        "ws:x",
        "wss:host",
        "ssh:host",
        "jar:x",
        "chrome:x",
        "view-source:x",
        "MAILTO:x",
        "approval:http:x",
        "approval:mailto:x",
        "review-ticket:mailto:x",
        "approval:file:etc",
        "approval:c:windows",
        "review-ticket:c:x",
        "approval:HTTP:x",
    ],
)
def test_opaque_reference_rejects_locators(tmp_path: Path, reference: str) -> None:
    root = tmp_path / "data" / "test-capability" / "opaque-bad"
    manifest, golden = base_manifest(scenario_suffix="opaque-bad")
    manifest["provenance"] = {
        "kind": "SANITIZED_REGRESSION",
        "source_reference": reference,
        "sanitization_policy": {"policy_id": "test-sanitization-policy", "version": 1},
        "approval": {"authority": "test-review-authority", "reference": "approval-ref"},
    }
    write_scenario_tree(root, manifest, golden_bytes=golden)
    with pytest.raises(ConformanceValidationError, match="source_reference"):
        validate_scenario(root)


@pytest.mark.parametrize(
    "reference",
    [
        "opaque-ref",
        "approval:ticket-42",
        "approval:ok",
        "review-ticket:42",
        "ok-ref.1",
        "550e8400-e29b-41d4-a716-446655440000",
    ],
)
def test_opaque_reference_accepts_allowlisted(tmp_path: Path, reference: str) -> None:
    root = tmp_path / "data" / "test-capability" / "opaque-ok"
    manifest, golden = base_manifest(scenario_suffix="opaque-ok")
    manifest["provenance"] = {
        "kind": "SANITIZED_REGRESSION",
        "source_reference": reference,
        "sanitization_policy": {"policy_id": "test-sanitization-policy", "version": 1},
        "approval": {"authority": "test-review-authority", "reference": "approval:ticket-1"},
    }
    write_scenario_tree(root, manifest, golden_bytes=golden)
    validate_scenario(root)


def test_recovery_unknown_owner_rejected(tmp_path: Path) -> None:
    root = tmp_path / "recovery" / "test-capability" / "bad-recovery-owner"
    manifest, golden = base_manifest(
        track="recovery",
        scenario_suffix="bad-recovery-owner",
        kind="recovery",
        include_fault=True,
    )
    manifest["contract_bindings"].append(
        {
            "binding_id": "z-recovery",
            "owner": "unknown-owner",
            "contract_id": "gateway-vnext.test-contract",
            "semantic_version": "1.0.0",
        }
    )
    manifest["contract_bindings"] = sorted(
        manifest["contract_bindings"],
        key=lambda item: str(item["binding_id"]).encode("utf-8"),
    )
    manifest["recovery_trigger"]["contract_binding_id"] = "z-recovery"
    write_scenario_tree(root, manifest, golden_bytes=golden)
    with pytest.raises(ConformanceValidationError, match="unknown recovery owner"):
        validate_scenario(root)


def test_recovery_unknown_contract_version_rejected(tmp_path: Path) -> None:
    root = tmp_path / "recovery" / "test-capability" / "bad-recovery-contract"
    manifest, golden = base_manifest(
        track="recovery",
        scenario_suffix="bad-recovery-contract",
        kind="recovery",
        include_fault=True,
    )
    manifest["contract_bindings"].append(
        {
            "binding_id": "z-recovery",
            "owner": "test-capability",
            "contract_id": "gateway-vnext.unknown-contract",
            "semantic_version": "9.9.9",
        }
    )
    manifest["contract_bindings"] = sorted(
        manifest["contract_bindings"],
        key=lambda item: str(item["binding_id"]).encode("utf-8"),
    )
    manifest["recovery_trigger"]["contract_binding_id"] = "z-recovery"
    write_scenario_tree(root, manifest, golden_bytes=golden)
    with pytest.raises(ConformanceValidationError, match="unknown recovery contract"):
        validate_scenario(root)


def test_recovery_kind_not_in_recovery_registry_rejected(tmp_path: Path) -> None:
    root = tmp_path / "recovery" / "test-capability" / "bad-recovery-kind"
    manifest, golden = base_manifest(
        track="recovery",
        scenario_suffix="bad-recovery-kind",
        kind="recovery",
        include_fault=True,
    )
    manifest["recovery_trigger"]["kind"] = "migrate"
    write_scenario_tree(root, manifest, golden_bytes=golden)
    with pytest.raises(ConformanceValidationError, match="unknown recovery_trigger kind"):
        validate_scenario(root)


def test_recovery_illegal_profile_rejected(tmp_path: Path) -> None:
    root = tmp_path / "recovery" / "test-capability" / "bad-recovery-profile"
    manifest, golden = base_manifest(
        track="recovery",
        scenario_suffix="bad-recovery-profile",
        kind="recovery",
        include_fault=True,
    )
    manifest["required_profiles"] = ["provider-matrix"]
    write_scenario_tree(root, manifest, golden_bytes=golden)
    with pytest.raises(ConformanceValidationError, match="recovery illegal for required profile"):
        validate_scenario(root)


def test_fault_parameters_schema_mismatch_rejected(tmp_path: Path) -> None:
    root = tmp_path / "recovery" / "test-capability" / "bad-fault-params"
    manifest, golden = base_manifest(
        track="recovery",
        scenario_suffix="bad-fault-params",
        kind="recovery",
        include_fault=True,
    )
    manifest["fault"]["parameters"] = {"unexpected": True}
    write_scenario_tree(root, manifest, golden_bytes=golden)
    with pytest.raises(ConformanceValidationError, match="fault parameters"):
        validate_scenario(root)


def test_recovery_parameters_schema_mismatch_rejected(tmp_path: Path) -> None:
    root = tmp_path / "recovery" / "test-capability" / "bad-recovery-params"
    manifest, golden = base_manifest(
        track="recovery",
        scenario_suffix="bad-recovery-params",
        kind="recovery",
        include_fault=True,
    )
    manifest["recovery_trigger"]["parameters"] = {"unexpected": True}
    write_scenario_tree(root, manifest, golden_bytes=golden)
    with pytest.raises(ConformanceValidationError, match="recovery_trigger parameters"):
        validate_scenario(root)


def test_fault_and_recovery_distinct_legal_bindings_accepted(tmp_path: Path) -> None:
    root = tmp_path / "recovery" / "test-capability" / "distinct-bindings"
    manifest, golden = base_manifest(
        track="recovery",
        scenario_suffix="distinct-bindings",
        kind="recovery",
        include_fault=True,
    )
    manifest["contract_bindings"].append(
        {
            "binding_id": "z-recovery",
            "owner": "test-capability",
            "contract_id": "gateway-vnext.test-recovery-contract",
            "semantic_version": "1.0.0",
        }
    )
    manifest["contract_bindings"] = sorted(
        manifest["contract_bindings"],
        key=lambda item: str(item["binding_id"]).encode("utf-8"),
    )
    manifest["recovery_trigger"]["contract_binding_id"] = "z-recovery"
    write_scenario_tree(root, manifest, golden_bytes=golden)
    validate_scenario(root)
