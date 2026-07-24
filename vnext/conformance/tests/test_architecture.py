"""Architecture boundary tests for conformance ownership."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_conformance.paths import FORMAL_SCENARIO_ROOT, SCHEMA_ROOT
from gateway_conformance.sanitize import sanitize_message


def test_conformance_package_lives_under_vnext_conformance() -> None:
    package_root = Path(__file__).resolve().parents[1] / "src" / "gateway_conformance"
    assert package_root.is_dir()
    assert "gateway_backend" not in str(package_root)


def test_schema_files_have_no_remote_http_refs() -> None:
    allowed = {"https://json-schema.org/draft/2020-12/schema"}
    for path in SCHEMA_ROOT.rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "https://" in line and not any(token in line for token in allowed):
                raise AssertionError(f"unexpected remote https ref in {path}: {line}")
        assert "http://" not in text


def test_no_unsafe_yaml_loader_in_conformance_sources() -> None:
    package_root = Path(__file__).resolve().parents[1] / "src" / "gateway_conformance"
    forbidden = (
        "yaml.safe_load",
        "FullLoader",
        "UnsafeLoader",
        "CLoader",
        'YAML(typ="unsafe")',
        "YAML(typ='unsafe')",
    )
    for source in package_root.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        assert not any(marker in text for marker in forbidden), source


def test_no_bless_or_writeback_helpers() -> None:
    package_root = Path(__file__).resolve().parents[1] / "src" / "gateway_conformance"
    for source in package_root.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        if source.name == "validate.py":
            continue
        assert "bless" not in text, source
        assert "write_back" not in text, source


def test_runner_package_lives_under_conformance_harness() -> None:
    runner_root = Path(__file__).resolve().parents[1] / "src" / "gateway_conformance" / "runner"
    assert runner_root.is_dir()
    assert "gateway_backend" not in str(runner_root)


def test_fake_harness_not_in_formal_scenario_root() -> None:
    fake_path = (
        Path(__file__).resolve().parents[1] / "src" / "gateway_conformance" / "runner" / "fake"
    )
    formal = Path(__file__).resolve().parents[2] / "fixtures" / "scenarios"
    assert fake_path.is_dir()
    assert not str(fake_path).startswith(str(formal))


def test_harness_sources_do_not_return_correctness_status_literals() -> None:
    fake_root = (
        Path(__file__).resolve().parents[1] / "src" / "gateway_conformance" / "runner" / "fake"
    )
    forbidden_returns = ('"PASSED"', '"ASSERTION_FAILED"', '"MATCH"', '"MISMATCH"')
    for source in fake_root.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        for marker in forbidden_returns:
            assert marker not in text, (source, marker)


def test_runner_package_has_no_subprocess_or_dynamic_import() -> None:
    runner_root = Path(__file__).resolve().parents[1] / "src" / "gateway_conformance" / "runner"
    forbidden = ("importlib", "__import__", "subprocess")
    for source in runner_root.rglob("*.py"):
        text = source.read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in text, (source, marker)


def test_formal_scenario_root_not_polluted() -> None:
    if FORMAL_SCENARIO_ROOT.exists():
        assert list(FORMAL_SCENARIO_ROOT.rglob("scenario.yaml")) == []


def test_sanitize_strips_absolute_paths() -> None:
    message = sanitize_message("failed at /root/secret/path/file.yaml")
    assert "/root/" not in message


@pytest.mark.parametrize(
    "message",
    [
        r"failed at C:\Users\secret\file.yaml",
        r"failed at \\server\share\x",
        "failed at C:/Users/secret/file.yaml",
        "failed at file:///tmp/secret",
        r"path=C:\Users\secret\a.yaml",
        r"[C:\Users\secret]",
        r"{C:\Users\secret}",
        r"->C:\Users\secret",
        "failed at file:%2F%2F%2Fetc%2Fpasswd",
        "failed at file:%2F%2Ftmp%2Fx",
        "failed at FILE:%2F%2F%2Ftmp%2Fa",
        "failed at %2Fetc%2Fpasswd",
        "failed at file:%252F%252F%252Fetc%252Fpasswd",
        "failed at file%3A%2F%2F%2Fetc%2Fpasswd",
        r"failed at C:%5CUsers%5Csecret",
        r"failed at %5C%5Cserver%5Cshare",
        "failed at /home/alice/My Secrets/id_rsa",
        r"failed at C:\Users\alice\My Documents\secret.yaml",
        r"failed at \\server\My Share\secret",
        "failed at file:///tmp/my secret/key",
        "failed at ／etc／passwd",
        "failed at ∕home∕alice",
        r"failed at C:＼Users＼secret",
        "failed at ~alice/.ssh/id_rsa",
        "failed at ~/secret",
        "failed at %7Ealice%2F.ssh",
    ],
)
def test_sanitize_strips_windows_and_unc_paths(message: str) -> None:
    sanitized = sanitize_message(message)
    assert "Users" not in sanitized
    assert "server" not in sanitized
    assert "/tmp" not in sanitized
    assert "file:%2f" not in sanitized.lower()
    assert "%2Fetc" not in sanitized
    assert "passwd" not in sanitized
    assert "Secrets" not in sanitized
    assert "Documents" not in sanitized
    assert "id_rsa" not in sanitized
    assert "Share" not in sanitized
    assert "alice" not in sanitized
    assert "<path>" in sanitized


@pytest.mark.parametrize(
    "message",
    [
        "failed at expected/foo.json",
        "digest sha256:" + "0" * 64,
    ],
)
def test_sanitize_preserves_safe_relative_and_digest(message: str) -> None:
    assert sanitize_message(message) == message


def test_runner_result_public_api_requires_semantic_validator() -> None:
    """Wire sufficient condition is schema AND semantic; package must not export bare schema."""
    import gateway_conformance as pkg
    from gateway_conformance.protocol import validate as protocol_validate

    assert "validate_runner_result" not in getattr(pkg, "__all__", ())
    assert not hasattr(pkg, "validate_runner_result")
    source = Path(protocol_validate.__file__).read_text(encoding="utf-8")
    assert "def validate_runner_result_semantics" in source
    assert "validate_runner_result(result)" in source
