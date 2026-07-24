"""Scenario closure and path safety tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gateway_shared_kernel import raw_blob_digest

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.scenario.validate import validate_scenario
from support import (
    base_manifest,
    build_valid_data_scenario,
    build_valid_structured_input_scenario,
    structured_input_asset,
    write_scenario_tree,
)


def test_absolute_path_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    text = (
        (root / "scenario.yaml")
        .read_text(encoding="utf-8")
        .replace(
            "path: expected/result.golden.json",
            "path: /etc/passwd",
        )
    )
    (root / "scenario.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(ConformanceValidationError):
        validate_scenario(root)


def test_parent_segment_path_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    text = (
        (root / "scenario.yaml")
        .read_text(encoding="utf-8")
        .replace(
            "path: expected/result.golden.json",
            "path: expected/../escape.golden.json",
        )
    )
    (root / "scenario.yaml").write_text(text, encoding="utf-8")
    with pytest.raises(ConformanceValidationError):
        validate_scenario(root)


def test_missing_declared_file_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    (root / "expected" / "result.golden.json").unlink()
    with pytest.raises(ConformanceValidationError):
        validate_scenario(root)


def test_undeclared_file_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    (root / "expected" / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ConformanceValidationError, match="undeclared"):
        validate_scenario(root)


def test_raw_hash_mismatch_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    golden_path = root / "expected" / "result.golden.json"
    raw = bytearray(golden_path.read_bytes())
    raw[-1] ^= 0x01
    golden_path.write_bytes(bytes(raw))
    with pytest.raises(ConformanceValidationError, match="raw_sha256"):
        validate_scenario(root)


def test_shared_ref_invalid_format_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "shared-ref"
    manifest, golden = base_manifest()
    manifest["input_assets"] = [
        {
            "logical_name": "table",
            "ref": "not-a-valid-ref",
            "media_type": "application/json",
            "size_bytes": 2,
            "raw_sha256": raw_blob_digest(b"{}").value,
        }
    ]
    with pytest.raises(ConformanceValidationError):
        write_scenario_tree(root, manifest, golden_bytes=golden)


def test_shared_ref_valid_under_shared_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared_root = tmp_path / "fixtures" / "shared"
    payload = b"{}"
    digest_hex = raw_blob_digest(payload).value.removeprefix("sha256:")
    asset_dir = shared_root / "sha256" / digest_hex
    asset_dir.mkdir(parents=True)
    (asset_dir / "table-json").write_bytes(payload)

    import gateway_conformance.scenario.closure as closure_paths

    monkeypatch.setattr(closure_paths, "SHARED_ROOT", shared_root)

    root = tmp_path / "data" / "test-capability" / "shared-ref"
    manifest, golden = base_manifest(scenario_suffix="shared-ref")
    manifest["input_assets"] = [
        {
            "logical_name": "table",
            "ref": f"sha256/{digest_hex}/table-json",
            "media_type": "application/json",
            "size_bytes": len(payload),
            "raw_sha256": raw_blob_digest(payload).value,
        }
    ]
    write_scenario_tree(root, manifest, golden_bytes=golden)
    validate_scenario(root)


def test_structured_input_asset_valid_passes(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "structured-input"
    build_valid_structured_input_scenario(root)
    validate_scenario(root)


def test_structured_input_asset_content_digest_mismatch_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "structured-input"
    manifest, golden = base_manifest(scenario_suffix="structured-input")
    payload, asset = structured_input_asset()
    asset["content_digest"] = "sha256:" + "f" * 64
    manifest["input_assets"] = [asset]
    root.mkdir(parents=True)
    (root / "input").mkdir()
    (root / asset["path"]).write_bytes(payload)
    with pytest.raises(ConformanceValidationError, match="content_digest mismatch"):
        write_scenario_tree(root, manifest, golden_bytes=golden)


def test_symlink_in_closure_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    golden_path = root / "expected" / "result.golden.json"
    content = golden_path.read_bytes()
    golden_path.unlink()
    outside = tmp_path / "outside.golden.json"
    outside.write_bytes(content)
    golden_path.symlink_to(outside)
    with pytest.raises(ConformanceValidationError):
        validate_scenario(root)


def test_expected_directory_symlink_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    expected_dir = root / "expected"
    content = (expected_dir / "result.golden.json").read_bytes()
    outside_dir = tmp_path / "outside-expected"
    outside_dir.mkdir()
    (outside_dir / "result.golden.json").write_bytes(content)
    import shutil

    shutil.rmtree(expected_dir)
    expected_dir.symlink_to(outside_dir, target_is_directory=True)
    with pytest.raises(ConformanceValidationError):
        validate_scenario(root)


def test_input_directory_symlink_rejected(tmp_path: Path) -> None:
    root = tmp_path / "data" / "test-capability" / "structured-input"
    build_valid_structured_input_scenario(root)
    input_dir = root / "input"
    outside_dir = tmp_path / "outside-input"
    outside_dir.mkdir()
    (outside_dir / "table.json").write_bytes((input_dir / "table.json").read_bytes())
    import shutil

    shutil.rmtree(input_dir)
    input_dir.symlink_to(outside_dir, target_is_directory=True)
    with pytest.raises(ConformanceValidationError):
        validate_scenario(root)


def test_shared_ref_digest_mismatch_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared_root = tmp_path / "fixtures" / "shared"
    payload = b"{}"
    digest_hex = raw_blob_digest(payload).value.removeprefix("sha256:")
    asset_dir = shared_root / "sha256" / digest_hex
    asset_dir.mkdir(parents=True)
    (asset_dir / "table-json").write_bytes(payload)

    import gateway_conformance.scenario.closure as closure_paths

    monkeypatch.setattr(closure_paths, "SHARED_ROOT", shared_root)

    root = tmp_path / "data" / "test-capability" / "shared-ref"
    manifest, golden = base_manifest(scenario_suffix="shared-ref")
    manifest["input_assets"] = [
        {
            "logical_name": "table",
            "ref": f"sha256/{'b' * 64}/table-json",
            "media_type": "application/json",
            "size_bytes": len(payload),
            "raw_sha256": raw_blob_digest(payload).value,
        }
    ]
    with pytest.raises(ConformanceValidationError, match="ref digest must match"):
        write_scenario_tree(root, manifest, golden_bytes=golden)


def test_toctou_replace_after_open_reads_original_fd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After openat, path replacement must not change bytes read from the fd."""
    import gateway_conformance.secure_io as secure_io

    root = tmp_path / "data" / "test-capability" / "structured-input"
    build_valid_structured_input_scenario(root)
    input_path = root / "input" / "table.json"
    original_bytes = input_path.read_bytes()
    evil_path = tmp_path / "evil-payload.json"
    evil_path.write_bytes(b'{"rows":[{"id":9999}]}')

    def hooked_read_regular_file(
        self: secure_io.SecureRoot,
        relative: str,
        *,
        label: str,
        max_bytes: int,
    ) -> bytes:
        fd = secure_io._openat_relative(self._fd, relative, label=label, want_dir=False)
        try:
            if relative == "input/table.json":
                input_path.unlink()
                input_path.symlink_to(evil_path)
                assert input_path.read_bytes() == evil_path.read_bytes()
                data = secure_io._read_fd(fd, max_bytes=max_bytes)
                assert data == original_bytes
                input_path.unlink()
                input_path.write_bytes(original_bytes)
                return data
            return secure_io._read_fd(fd, max_bytes=max_bytes)
        finally:
            os.close(fd)

    monkeypatch.setattr(secure_io.SecureRoot, "read_regular_file", hooked_read_regular_file)
    validate_scenario(root)


def _swap_scenario_root_to_outside(root: Path, outside: Path) -> None:
    """Rename scenario dir and replace path with symlink to outside (ancestor TOCTOU)."""
    import shutil

    parent = root.parent
    name = root.name
    real = parent / f".real-{name}"
    shutil.move(str(root), str(real))
    outside.mkdir(parents=True, exist_ok=True)
    # Copy a minimal decoy so Path-based open would succeed if it followed the symlink.
    if (real / "scenario.yaml").exists():
        shutil.copytree(real, outside, dirs_exist_ok=True)
        # Corrupt outside golden so escape would diverge if followed.
        golden = outside / "expected" / "result.golden.json"
        if golden.exists():
            golden.write_bytes(golden.read_bytes() + b"\n")
    root.symlink_to(outside, target_is_directory=True)


def test_ancestor_swap_after_manifest_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import gateway_conformance.secure_io as secure_io

    root = tmp_path / "data" / "test-capability" / "minimal"
    build_valid_data_scenario(root)
    outside = tmp_path / "outside-escape"
    original_assert = secure_io.SecureRoot.assert_path_unchanged
    calls = {"n": 0}

    def hooked_assert(self: secure_io.SecureRoot) -> None:
        calls["n"] += 1
        if calls["n"] == 1:
            _swap_scenario_root_to_outside(root, outside)
        original_assert(self)

    monkeypatch.setattr(secure_io.SecureRoot, "assert_path_unchanged", hooked_assert)
    with pytest.raises(ConformanceValidationError):
        validate_scenario(root)


def test_intermediate_fd_no_leak(tmp_path: Path) -> None:
    import gateway_conformance.secure_io as secure_io

    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    target = nested / "x"
    target.write_bytes(b"payload")
    before = len(os.listdir("/proc/self/fd"))
    with secure_io.SecureRoot.open_path(tmp_path, label="fd-leak-root") as secure:
        for _ in range(100):
            data = secure.read_regular_file("a/b/x", label="nested", max_bytes=1024)
            assert data == b"payload"
    after = len(os.listdir("/proc/self/fd"))
    assert after - before <= 2


def test_large_shared_asset_not_counted_in_local_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    shared_root = tmp_path / "fixtures" / "shared"
    payload = b"x" * (1_100_000)
    digest_hex = raw_blob_digest(payload).value.removeprefix("sha256:")
    asset_dir = shared_root / "sha256" / digest_hex
    asset_dir.mkdir(parents=True)
    (asset_dir / "table-json").write_bytes(payload)

    import gateway_conformance.scenario.closure as closure_mod

    monkeypatch.setattr(closure_mod, "SHARED_ROOT", shared_root)

    root = tmp_path / "data" / "test-capability" / "shared-large"
    manifest, golden = base_manifest(scenario_suffix="shared-large")
    manifest["input_assets"] = [
        {
            "logical_name": "table",
            "ref": f"sha256/{digest_hex}/table-json",
            "media_type": "application/json",
            "size_bytes": len(payload),
            "raw_sha256": raw_blob_digest(payload).value,
        }
    ]
    write_scenario_tree(root, manifest, golden_bytes=golden)
    validate_scenario(root)
