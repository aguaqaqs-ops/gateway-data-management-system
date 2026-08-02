from __future__ import annotations

import os
from pathlib import Path

import pytest

from gateway_repository_service.process import load_cgroup_topology, preflight_cgroup


@pytest.mark.skipif(
    os.environ.get("GATEWAY_P2R1_TARGET_CONTAINER") != "1",
    reason="runs only inside the delegated target container",
)
def test_target_container_has_real_delegated_cgroup() -> None:
    layout = load_cgroup_topology(Path(os.environ["GATEWAY_REPOSITORY_CGROUP_LAYOUT"]))
    assert layout is not None
    preflight_cgroup(layout.samples, layout)
