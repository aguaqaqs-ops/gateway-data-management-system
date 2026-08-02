"""Target-container gate used by the root launcher before cgroup authorization."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def main(run_dir: Path | None = None) -> None:
    run_dir = Path("/run/gateway-p2r1") if run_dir is None else run_dir
    release = run_dir / "release"
    argv_path = run_dir / "argv.json"
    deadline = time.monotonic() + float(os.environ.get("GATEWAY_P2R1_GATE_TIMEOUT", "120"))
    while not release.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("target authorization gate timed out")
        time.sleep(0.02)
    layout_path = Path(
        os.environ.get(
            "GATEWAY_REPOSITORY_CGROUP_LAYOUT",
            str(run_dir / "cgroup-layout.json"),
        )
    )
    if not layout_path.is_file():
        raise FileNotFoundError("launcher cgroup layout manifest is missing")
    from gateway_repository_service.process import load_cgroup_topology

    layout = load_cgroup_topology(layout_path)
    if layout is None or layout.layout_version != "p2-r1-cgroup-layout-v1":
        raise ValueError("launcher cgroup layout manifest is invalid")
    supervisor_control_group = layout.supervisor_control_group
    delegated_control_group = layout.delegated_control_group
    if os.environ.get("GATEWAY_P2R1_TARGET_CONTAINER") == "1":
        from gateway_repository_service.process import current_cgroup_membership

        if current_cgroup_membership() != supervisor_control_group:
            raise RuntimeError("target gate is not in the declared supervisor cgroup")
        os.environ["GATEWAY_REPOSITORY_CGROUP_SUPERVISOR_CONTROL_GROUP"] = supervisor_control_group
        os.environ["GATEWAY_REPOSITORY_CGROUP_DELEGATED_CONTROL_GROUP"] = delegated_control_group
        os.environ["GATEWAY_REPOSITORY_CGROUP_LAYOUT_VERIFIED"] = "1"
    argv = json.loads(argv_path.read_text(encoding="utf-8"))
    if not isinstance(argv, list) or not all(isinstance(item, str) for item in argv):
        raise ValueError("target matrix argv is invalid")
    os.execv(sys.executable, [sys.executable, "-m", "gateway_repository_service.matrix", *argv])


if __name__ == "__main__":
    main()
