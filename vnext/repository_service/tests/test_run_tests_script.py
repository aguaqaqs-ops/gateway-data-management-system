"""Unit tests for run-tests.sh exit-code propagation."""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

VNEXT_ROOT = Path(__file__).resolve().parents[2]
RUN_TESTS_SCRIPT = VNEXT_ROOT / "scripts" / "run-tests.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _fake_uv_consume_for_serial_batches(path: Path) -> None:
    _write_executable(
        path,
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            if [[ "$1" == "-C" ]]; then
              shift 2
            fi
            if [[ "$1" != "run" ]]; then
              echo "unexpected uv-consume invocation: $*" >&2
              exit 99
            fi
            shift
            for arg in "$@"; do
              if [[ "${arg}" == --ignore=* ]]; then
                exit 42
              fi
            done
            exit 0
            """
        ),
    )


@pytest.mark.unit
def test_run_tests_serial_batches_keep_first_batch_failure(tmp_path: Path) -> None:
    fake_uv_consume = tmp_path / "uv-consume.sh"
    _fake_uv_consume_for_serial_batches(fake_uv_consume)
    env = os.environ.copy()
    env["GATEWAY_UV_CONSUME"] = str(fake_uv_consume)
    env["GATEWAY_TEST_BASETEMP"] = str(tmp_path / "pytest-tmp")
    env["GATEWAY_TEST_WORKERS"] = "1"
    completed = subprocess.run(
        ["bash", str(RUN_TESTS_SCRIPT)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=VNEXT_ROOT,
    )
    assert completed.returncode == 1, completed.stderr
