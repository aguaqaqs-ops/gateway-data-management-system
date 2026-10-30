"""Unit tests for backend dependency-base input identity and reuse checks."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
import pytest

VNEXT_ROOT = Path(__file__).resolve().parents[2]
BUILD_SCRIPT = VNEXT_ROOT / "scripts" / "build-backend-dependency-base.sh"
BASE_IMAGE_ID = "sha256:" + "a" * 64
BUILT_IMAGE_ID = "sha256:" + "b" * 64


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _fake_docker(path: Path) -> str:
    state = path / "backend-dependency-base-label"
    argv = path / "docker-build.argv"
    return f"""#!/usr/bin/env bash
set -euo pipefail
STATE={str(state)!r}
ARGV={str(argv)!r}
if [[ "$1" == "image" && "$2" == "inspect" ]]; then
  reference="${{@:$#}}"
  format=""
  while [[ $# -gt 0 ]]; do
    if [[ "$1" == "--format" ]]; then
      format="$2"
      shift 2
    else
      shift
    fi
  done
  if [[ "$reference" == rust:* ]]; then
    [[ "$format" == *".Id"* ]] && echo "{BASE_IMAGE_ID}" || exit 0
    exit 0
  fi
  if [[ "$reference" == gateway-backend-deps:lock-* ]]; then
    if [[ ! -f "$STATE" ]]; then
      if [[ "${{FAKE_EXISTING_TAG:-0}}" == "1" ]]; then
        if [[ "$format" == *"dependency-input-sha256"* ]]; then
          echo "${{FAKE_LABEL:-}}"
        elif [[ "$format" == *".Id"* ]]; then
          echo "{BUILT_IMAGE_ID}"
        fi
        exit 0
      fi
      exit 1
    fi
    if [[ "$format" == *"dependency-input-sha256"* ]]; then
      cat "$STATE"
    elif [[ "$format" == *".Id"* ]]; then
      echo "{BUILT_IMAGE_ID}"
    fi
    exit 0
  fi
fi
if [[ "$1" == "build" ]]; then
  printf '%s\\n' "$@" > "$ARGV"
  for arg in "$@"; do
    case "$arg" in
      DEPENDENCY_INPUT_SHA256=*) printf '%s' "${{arg#*=}}" > "$STATE" ;;
    esac
  done
  exit 0
fi
if [[ "$1" == "save" ]]; then
  output=""
  while [[ $# -gt 0 ]]; do
    if [[ "$1" == "--output" ]]; then output="$2"; shift 2; else shift; fi
  done
  printf 'fake backend dependency base archive\\n' > "$output"
  exit 0
fi
echo "unexpected docker invocation: $*" >&2
exit 1
"""


def _run_script(
    tmp_path: Path,
    *arguments: str,
    extra_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    docker = bin_dir / "docker"
    _write_executable(docker, _fake_docker(tmp_path))
    env = os.environ.copy()
    env.pop("GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE", None)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env.update(extra_env or {})
    completed = subprocess.run(
        [str(BUILD_SCRIPT), *arguments],
        cwd=VNEXT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return completed, tmp_path / "docker-build.argv", tmp_path / "backend-dependency-base-label"


@pytest.mark.unit
def test_dependency_base_input_summary_hashes_locked_inputs_and_base_identity(
    tmp_path: Path,
) -> None:
    completed, _, _ = _run_script(tmp_path, "--print-input")

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    inputs = summary["inputs"]
    expected_digest = hashlib.sha256(
        json.dumps(inputs, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert summary["input_sha256"] == expected_digest
    assert summary["image"] == f"gateway-backend-deps:lock-{expected_digest[:12]}"
    assert inputs["files"].keys() == {
        "backend/pyproject.toml",
        "backend/uv.lock",
        "backend/.python-version",
        "rust/Cargo.lock",
        "rust/rust-toolchain.toml",
    }
    assert inputs["base_image"] == "rust:1.97.0-bookworm"
    assert inputs["base_image_id"] == BASE_IMAGE_ID
    assert inputs["python_version"] == "3.14.6"
    assert inputs["uv_version"] == "0.11.28"


@pytest.mark.unit
def test_dependency_base_build_verifies_label_and_exports_archive_sha256(
    tmp_path: Path,
) -> None:
    save_path = tmp_path / "backend-dependency-base.tar"
    completed, argv_path, label_path = _run_script(tmp_path, "--save", str(save_path))

    assert completed.returncode == 0, completed.stderr
    assert label_path.is_file()
    digest = label_path.read_text(encoding="ascii")
    assert f"image=gateway-backend-deps:lock-{digest[:12]}" in completed.stdout
    assert f"input_sha256={digest}" in completed.stdout
    assert f"image_id={BUILT_IMAGE_ID}" in completed.stdout
    assert save_path.read_bytes() == b"fake backend dependency base archive\n"
    save_sha256 = hashlib.sha256(save_path.read_bytes()).hexdigest()
    assert f"save_sha256={save_sha256}" in completed.stdout
    argv = argv_path.read_text(encoding="utf-8")
    assert "--pull=false" in argv
    assert "--file" in argv and "Dockerfile.dependency-base" in argv
    assert f"DEPENDENCY_INPUT_SHA256={digest}" in argv


@pytest.mark.unit
def test_dependency_base_tag_with_mismatched_label_is_not_reused(tmp_path: Path) -> None:
    # A wrong label is returned for any extant derived tag. The script must
    # stop before issuing a build that would silently replace the tag.
    completed, argv_path, _ = _run_script(
        tmp_path,
        extra_env={"FAKE_EXISTING_TAG": "1", "FAKE_LABEL": "0" * 64},
    )
    assert completed.returncode != 0
    assert "refusing to reuse" in completed.stderr
    assert not argv_path.exists()


@pytest.mark.unit
def test_dependency_base_builder_rejects_a_tag_that_does_not_match_inputs(
    tmp_path: Path,
) -> None:
    completed, argv_path, _ = _run_script(
        tmp_path,
        extra_env={
            "GATEWAY_BACKEND_DEPENDENCY_BASE_IMAGE": "gateway-backend-deps:lock-wrong",
        },
    )

    assert completed.returncode != 0
    assert "does not match the current dependency input tag" in completed.stderr
    assert not argv_path.exists()
