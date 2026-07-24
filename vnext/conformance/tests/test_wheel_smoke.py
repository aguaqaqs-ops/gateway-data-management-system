"""Wheel runtime dependency smoke test."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


def test_built_wheel_imports_jsonschema_without_extras() -> None:
    project_root = Path(__file__).resolve().parents[1]
    shared_kernel = project_root.parent / "shared_kernel"
    with tempfile.TemporaryDirectory() as td:
        dist = Path(td) / "dist"
        dist.mkdir()
        subprocess.run(
            ["uv", "build", "--out-dir", str(dist)],
            cwd=shared_kernel,
            check=True,
        )
        subprocess.run(
            ["uv", "build", "--out-dir", str(dist)],
            cwd=project_root,
            check=True,
        )
        wheels = sorted(dist.glob("*.whl"))
        assert len(wheels) == 2
        venv = Path(td) / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        python = venv / "bin" / "python"
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), *[str(w) for w in wheels]],
            check=True,
        )
        subprocess.run(
            [
                str(python),
                "-c",
                "import jsonschema; from gateway_conformance.schemas import validate_scenario_manifest",
            ],
            check=True,
        )
