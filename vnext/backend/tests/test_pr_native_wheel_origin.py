"""WP4 R4 PR-NATIVE release wheel module origin verification."""

from __future__ import annotations

import importlib.metadata
import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.pr_native


def test_installed_gateway_compute_origin_is_not_editable_source() -> None:
    """When GATE_PR_NATIVE=1, prove the active extension comes from an installed wheel."""

    if os.environ.get("GATE_PR_NATIVE") != "1":
        pytest.skip("wheel origin probe runs under gate.sh native only")

    import gateway_compute
    import gateway_compute.gateway_compute as native  # type: ignore[import-untyped]

    module_file = Path(native.__file__).resolve()
    repo_root = Path(__file__).resolve().parents[3]
    source_tree = repo_root / "rust" / "gateway-compute-python" / "python"
    assert not str(module_file).startswith(str(source_tree)), module_file
    assert "site-packages" in module_file.parts or ".venv" in module_file.parts, module_file

    version = importlib.metadata.version("gateway-compute-python")
    assert version
    assert gateway_compute.__version__

    dist = importlib.metadata.distribution("gateway-compute-python")
    direct_url = None
    for path in dist.files or []:
        if path.name == "direct_url.json":
            direct_url = json.loads(dist.locate_file(path).read_text(encoding="utf-8"))
            break
    assert direct_url is not None, "direct_url.json missing"
    url = direct_url.get("url", "")
    assert url.endswith(".whl"), url
    assert str(source_tree) not in url, url

    expected_wheel_sha256 = os.environ.get("NATIVE_PR_WHEEL_SHA256")
    assert expected_wheel_sha256, "gate must export NATIVE_PR_WHEEL_SHA256"
