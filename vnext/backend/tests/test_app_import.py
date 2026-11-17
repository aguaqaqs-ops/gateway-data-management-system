"""The backend must import successfully in a fresh interpreter."""

import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "module",
    (
        "gateway_backend.app",
        "gateway_backend.application.preview_jobs.definitions",
        "gateway_backend.application.submit_jobs.definitions",
        "gateway_backend.application.history.compare_jobs.definitions",
        "gateway_backend.application.pair_pipeline",
    ),
)
def test_application_imports_without_circular_dependencies(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
