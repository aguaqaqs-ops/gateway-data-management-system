"""Unit tests for S5-C launcher/runtime provenance hard cutover."""

from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
from pathlib import Path

import pytest

import gateway_repository_service.matrix as matrix_module
from gateway_repository_service.settings import RepositoryServiceSettings

LAUNCHER = Path(__file__).resolve().parents[2] / "deploy/p2r1-cache/p2r1-target-launcher.sh"
HELPER = Path(__file__).resolve().parent / "support" / "build_context_digest.py"
LOCK_SHA256 = hashlib.sha256((Path(__file__).resolve().parents[1] / "uv.lock").read_bytes()).hexdigest()
_CANDIDATE = "a" * 40
_BUILD_INPUT = "b" * 40
_TREE = "sha256:" + "c" * 64
_IMAGE = "sha256:" + "d" * 64


def _valid_manifest(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "manifest_version": "p2-r1-provenance-v3",
        "candidate_sha": _CANDIDATE,
        "build_input_revision": _BUILD_INPUT,
        "source_tree_sha256": _TREE,
        "image_digest": _IMAGE,
        "lock_sha256": LOCK_SHA256,
        "dolt_version": "2.1.11",
        "uv_version": "0.11.28",
        "mysql_connector_version": "9.7.0",
        "pyarrow_version": "25.0.0",
        "cache_condition": "retained-dependency-cache",
        "project_name": "gateway-p2r1-test",
    }
    payload.update(overrides)
    return payload


def _write_manifest(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _install_versions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(matrix_module, "_actual_dolt_version", lambda _binary: "2.1.11")
    monkeypatch.setattr(
        matrix_module,
        "_distribution_version",
        lambda name: {
            "mysql-connector-python": "9.7.0",
            "pyarrow": "25.0.0",
        }.get(name),
    )


def _install_verified_env(
    monkeypatch: pytest.MonkeyPatch,
    manifest_path: Path,
    *,
    extra: dict[str, str] | None = None,
) -> None:
    values = {
        "GATEWAY_P2R1_PROVENANCE_VERIFIED": "1",
        "GATEWAY_P2R1_PROVENANCE_MANIFEST": str(manifest_path),
        "GATEWAY_P2R1_IMAGE_DIGEST": _IMAGE,
        "GATEWAY_P2R1_CANDIDATE_SHA": _CANDIDATE,
        "GATEWAY_P2R1_BUILD_INPUT_REVISION": _BUILD_INPUT,
        "GATEWAY_P2R1_BUILD_REVISION": _CANDIDATE,
        "GATEWAY_P2R1_SOURCE_TREE_SHA256": _TREE,
        "GATEWAY_P2R1_LOCK_SHA256": LOCK_SHA256,
        "GATEWAY_P2R1_CACHE_CONDITION": "retained-dependency-cache",
    }
    if extra:
        values.update(extra)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def _metadata(
    *,
    image_digest: str | None = None,
    build_revision: str | None = None,
    cache_condition: str | None = None,
) -> dict[str, object]:
    return matrix_module._measurement_metadata(
        RepositoryServiceSettings(),
        image_digest=image_digest,
        build_revision=build_revision,
        cache_condition=cache_condition,
    )


SCHEMA_FAULTS: tuple[tuple[str, dict[str, object]], ...] = (
    (
        "v2-manifest",
        {
            "manifest_version": "p2-r1-provenance-v2",
            "build_revision": _CANDIDATE,
            "source_tree_sha256": _TREE,
            "image_digest": _IMAGE,
            "lock_sha256": LOCK_SHA256,
            "dolt_version": "2.1.11",
            "mysql_connector_version": "9.7.0",
            "pyarrow_version": "25.0.0",
            "cache_condition": "retained-dependency-cache",
        },
    ),
    ("missing-candidate", {key: value for key, value in _valid_manifest().items() if key != "candidate_sha"}),
    ("missing-build-input", {key: value for key, value in _valid_manifest().items() if key != "build_input_revision"}),
    ("missing-source-tree", {key: value for key, value in _valid_manifest().items() if key != "source_tree_sha256"}),
    ("malformed-candidate", {**_valid_manifest(), "candidate_sha": "short"}),
    ("malformed-build-input", {**_valid_manifest(), "build_input_revision": "not-a-sha"}),
    ("malformed-source-tree", {**_valid_manifest(), "source_tree_sha256": "sha256:abcd"}),
    ("legacy-only-build-revision", {**_valid_manifest(), "build_revision": _CANDIDATE}),
    (
        "overloaded-build-revision-without-split-fields",
        {
            "manifest_version": "p2-r1-provenance-v3",
            "build_revision": _CANDIDATE,
            "source_tree_sha256": _TREE,
            "image_digest": _IMAGE,
            "lock_sha256": LOCK_SHA256,
            "dolt_version": "2.1.11",
            "mysql_connector_version": "9.7.0",
            "pyarrow_version": "25.0.0",
            "cache_condition": "retained-dependency-cache",
        },
    ),
)

STALE_FAULTS: tuple[tuple[str, dict[str, object]], ...] = (
    ("stale-candidate", {**_valid_manifest(), "candidate_sha": "0" * 40}),
    ("stale-build-input", {**_valid_manifest(), "build_input_revision": "0" * 40}),
    ("stale-source-tree", {**_valid_manifest(), "source_tree_sha256": "sha256:" + "0" * 64}),
    (
        "contradictory-candidate-build-input",
        {**_valid_manifest(), "candidate_sha": _BUILD_INPUT, "build_input_revision": _CANDIDATE},
    ),
)


@pytest.mark.unit
def test_launcher_calls_helper_before_run_dir_and_systemd() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")
    helper_idx = source.index('python3 "$DIGEST_HELPER" identity')
    mkdir_idx = source.index('mkdir -p "$RUN_DIR"')
    systemctl_idx = source.index('systemctl start --wait')
    compose_idx = source.index(
        'docker compose -p "$PROJECT_NAME" -f "$COMPOSE_FILE" --profile p2-r1 up'
    )
    assert helper_idx < mkdir_idx < systemctl_idx
    assert helper_idx < compose_idx
    assert str(HELPER.relative_to(Path(__file__).resolve().parents[3])) in source
    assert "archive HEAD" not in source
    assert "p2-r1-provenance-v2" not in source
    assert '"manifest_version": "p2-r1-provenance-v3"' in source
    assert "gateway.p2r1.build-input-revision" in source
    assert "org.opencontainers.image.revision" in source
    assert "gateway.p2r1.source-tree-sha256" in source
    assert '"build_revision"' not in source
    assert "GATEWAY_P2R1_CANDIDATE_SHA=$CANDIDATE_SHA" in source
    assert "GATEWAY_P2R1_BUILD_INPUT_REVISION=$BUILD_INPUT_REVISION" in source
    assert "GATEWAY_P2R1_BUILD_REVISION=$CANDIDATE_SHA" in source


@pytest.mark.unit
def test_launcher_write_manifest_emits_v3_three_fields(tmp_path: Path) -> None:
    source = LAUNCHER.read_text(encoding="utf-8")
    start = source.index("write_manifest() {")
    end = source.index("write_storage_layout() {")
    snippet = source[start:end]
    target = tmp_path / "provenance.json"
    script = tmp_path / "write.sh"
    quoted_target = shlex.quote(str(target))
    script.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "set -eu",
                "fail() { echo \"$*\" >&2; exit 2; }",
                snippet,
                f"write_manifest {quoted_target} {_IMAGE} {_CANDIDATE} {_BUILD_INPUT} {_TREE} "
                f"{LOCK_SHA256} 2.1.11 0.11.28 9.7.0 25.0.0 retained-dependency-cache gateway-p2r1-test",
                "",
            ]
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(["sh", str(script)], check=False, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["manifest_version"] == "p2-r1-provenance-v3"
    assert payload["candidate_sha"] == _CANDIDATE
    assert payload["build_input_revision"] == _BUILD_INPUT
    assert payload["source_tree_sha256"] == _TREE
    assert payload["image_digest"] == _IMAGE
    assert "build_revision" not in payload
    assert oct(target.stat().st_mode & 0o777) == "0o444"


@pytest.mark.unit
def test_verified_v3_manifest_maps_build_revision_to_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_versions(monkeypatch)
    manifest_path = tmp_path / "provenance.json"
    _write_manifest(manifest_path, _valid_manifest())
    _install_verified_env(monkeypatch, manifest_path)
    metadata = _metadata()
    assert metadata["provenance_manifest_valid"] is True
    assert metadata["metadata_complete"] is True
    assert metadata["build_revision"] == _CANDIDATE
    assert metadata["image_digest"] == _IMAGE
    manifest = metadata["provenance_manifest"]
    assert isinstance(manifest, dict)
    assert manifest["candidate_sha"] == _CANDIDATE
    assert manifest["build_input_revision"] == _BUILD_INPUT


@pytest.mark.unit
def test_equal_candidate_and_build_input_remain_independent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_versions(monkeypatch)
    same = "c" * 40
    manifest_path = tmp_path / "provenance.json"
    _write_manifest(
        manifest_path,
        _valid_manifest(candidate_sha=same, build_input_revision=same),
    )
    _install_verified_env(
        monkeypatch,
        manifest_path,
        extra={
            "GATEWAY_P2R1_CANDIDATE_SHA": same,
            "GATEWAY_P2R1_BUILD_INPUT_REVISION": same,
            "GATEWAY_P2R1_BUILD_REVISION": same,
        },
    )
    metadata = _metadata()
    assert metadata["metadata_complete"] is True
    manifest = metadata["provenance_manifest"]
    assert isinstance(manifest, dict)
    assert manifest["candidate_sha"] == same
    assert manifest["build_input_revision"] == same
    assert metadata["build_revision"] == same


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [payload for _name, payload in SCHEMA_FAULTS],
    ids=[name for name, _payload in SCHEMA_FAULTS],
)
def test_verified_schema_faults_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    _install_versions(monkeypatch)
    manifest_path = tmp_path / "provenance.json"
    _write_manifest(manifest_path, payload)
    _install_verified_env(monkeypatch, manifest_path)
    metadata = _metadata()
    assert metadata["provenance_manifest_valid"] is False
    assert metadata["metadata_complete"] is False
    assert metadata["build_revision"] == "unknown"


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload",
    [payload for _name, payload in STALE_FAULTS],
    ids=[name for name, _payload in STALE_FAULTS],
)
def test_verified_stale_or_contradictory_fields_are_incomplete(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    payload: dict[str, object],
) -> None:
    _install_versions(monkeypatch)
    manifest_path = tmp_path / "provenance.json"
    _write_manifest(manifest_path, payload)
    _install_verified_env(monkeypatch, manifest_path)
    metadata = _metadata()
    assert metadata["metadata_complete"] is False
    assert metadata["build_revision"] != "unknown"


@pytest.mark.unit
def test_cli_cannot_override_verified_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_versions(monkeypatch)
    manifest_path = tmp_path / "provenance.json"
    _write_manifest(manifest_path, _valid_manifest())
    _install_verified_env(monkeypatch, manifest_path)
    other = "f" * 40
    metadata = _metadata(build_revision=other, image_digest=_IMAGE)
    assert metadata["build_revision"] == _CANDIDATE
    assert metadata["metadata_complete"] is False


@pytest.mark.unit
def test_env_cannot_override_verified_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_versions(monkeypatch)
    manifest_path = tmp_path / "provenance.json"
    _write_manifest(manifest_path, _valid_manifest())
    _install_verified_env(
        monkeypatch,
        manifest_path,
        extra={"GATEWAY_P2R1_BUILD_REVISION": "f" * 40},
    )
    metadata = _metadata()
    assert metadata["build_revision"] == _CANDIDATE
    assert metadata["metadata_complete"] is False


@pytest.mark.unit
def test_v2_manifest_does_not_supply_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install_versions(monkeypatch)
    manifest_path = tmp_path / "provenance.json"
    _write_manifest(
        manifest_path,
        {
            "manifest_version": "p2-r1-provenance-v2",
            "build_revision": _CANDIDATE,
            "source_tree_sha256": _TREE,
            "image_digest": _IMAGE,
            "lock_sha256": LOCK_SHA256,
            "dolt_version": "2.1.11",
            "mysql_connector_version": "9.7.0",
            "pyarrow_version": "25.0.0",
            "cache_condition": "retained-dependency-cache",
        },
    )
    _install_verified_env(monkeypatch, manifest_path)
    metadata = _metadata(build_revision=_CANDIDATE, image_digest=_IMAGE)
    assert metadata["provenance_manifest_valid"] is False
    assert metadata["metadata_complete"] is False
    assert metadata["build_revision"] == "unknown"


@pytest.mark.unit
def test_helper_identity_is_the_launcher_authority() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")
    assert "compute_image_identity" not in source
    assert "archive HEAD" not in source
    assert 'python3 "$DIGEST_HELPER" identity' in source
    assert source.count('python3 "$DIGEST_HELPER" identity') == 1
    assert HELPER.name in source
