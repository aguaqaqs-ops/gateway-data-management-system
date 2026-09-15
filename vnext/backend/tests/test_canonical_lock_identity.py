"""Canonical uv.lock registry identity gate (sole owner for five-lock identity checks)."""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path
from urllib.parse import urlparse

import pytest

VNEXT_ROOT = Path(__file__).resolve().parents[2]
LOCK_PACKAGES = (
    "shared_kernel",
    "repository_contracts",
    "repository_client",
    "backend",
    "repository_service",
)

CANONICAL_REGISTRY = "https://pypi.org/simple"
APPROVED_ARTIFACT_HOST_SUFFIXES = (
    "files.pythonhosted.org",
    "pypi.org",
)
ALLOWED_NON_REGISTRY_SOURCE_KEYS = frozenset(
    {
        "editable",
        "directory",
        "virtual",
        "git",
        "url",
        "path",
    }
)


class CanonicalLockIdentityError(ValueError):
    """Raised when a uv.lock violates canonical PyPI identity rules."""


def _artifact_host_allowed(host: str) -> bool:
    normalized = host.lower().rstrip(".")
    return any(
        normalized == suffix or normalized.endswith(f".{suffix}")
        for suffix in APPROVED_ARTIFACT_HOST_SUFFIXES
    )


def _validate_artifact_urls(package_name: str, payload: object) -> None:
    if not isinstance(payload, dict):
        return
    for key in ("url",):
        raw_url = payload.get(key)
        if not isinstance(raw_url, str) or not raw_url.startswith(("http://", "https://")):
            continue
        host = urlparse(raw_url).hostname
        if host is None or not _artifact_host_allowed(host):
            raise CanonicalLockIdentityError(
                f"{package_name}: artifact URL host {host!r} is not an approved PyPI host",
            )


def _validate_package_source(package: dict[str, object]) -> None:
    name = str(package.get("name", "<unknown>"))
    source = package.get("source")
    if not isinstance(source, dict):
        raise CanonicalLockIdentityError(f"{name}: missing or invalid source table")

    if "registry" in source:
        registry = source.get("registry")
        if registry != CANONICAL_REGISTRY:
            raise CanonicalLockIdentityError(
                f"{name}: registry must be {CANONICAL_REGISTRY}, got {registry!r}",
            )
        for section in ("sdist",):
            _validate_artifact_urls(name, package.get(section))
        wheels = package.get("wheels")
        if isinstance(wheels, list):
            for wheel in wheels:
                _validate_artifact_urls(name, wheel)
        return

    if not ALLOWED_NON_REGISTRY_SOURCE_KEYS.intersection(source):
        raise CanonicalLockIdentityError(
            f"{name}: unsupported non-registry source keys {sorted(source)}",
        )


def assert_canonical_lock_identity(lock_path: Path) -> None:
    if not lock_path.is_file():
        raise CanonicalLockIdentityError(f"missing lockfile: {lock_path}")
    payload = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    packages = payload.get("package")
    if not isinstance(packages, list):
        raise CanonicalLockIdentityError(f"{lock_path}: missing package table")
    for package in packages:
        if isinstance(package, dict):
            _validate_package_source(package)


@pytest.mark.unit
def test_repository_lockfiles_have_canonical_registry_identity() -> None:
    for package in LOCK_PACKAGES:
        assert_canonical_lock_identity(VNEXT_ROOT / package / "uv.lock")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("lock_text", "message"),
    [
        (
            'version = 1\n[[package]]\nname = "demo"\nversion = "1.0.0"\n'
            'source = { registry = "http://192.168.1.1/simple" }\n',
            "registry must be",
        ),
        (
            'version = 1\n[[package]]\nname = "demo"\nversion = "1.0.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
            'wheels = [{ url = "http://mirror.internal/pkg.whl", hash = "sha256:ab", size = 1 }]\n',
            "artifact URL host",
        ),
    ],
)
def test_canonical_lock_identity_rejects_polluted_lock(
    tmp_path: Path,
    lock_text: str,
    message: str,
) -> None:
    lock_path = tmp_path / "uv.lock"
    lock_path.write_text(lock_text, encoding="utf-8")
    with pytest.raises(CanonicalLockIdentityError, match=message):
        assert_canonical_lock_identity(lock_path)


@pytest.mark.unit
def test_canonical_lock_identity_allows_local_workspace_sources(tmp_path: Path) -> None:
    backend_lock = VNEXT_ROOT / "backend" / "uv.lock"
    lock_path = tmp_path / "uv.lock"
    shutil.copy(backend_lock, lock_path)
    assert_canonical_lock_identity(lock_path)


@pytest.mark.unit
def test_canonical_lock_identity_rejects_missing_lock(tmp_path: Path) -> None:
    with pytest.raises(CanonicalLockIdentityError, match="missing lockfile"):
        assert_canonical_lock_identity(tmp_path / "uv.lock")
