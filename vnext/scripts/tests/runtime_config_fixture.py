#!/usr/bin/env python3
"""Explicit isolated bind fixture, shared by both Compose test harnesses."""
from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path

VNEXT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VNEXT / "scripts"))
from host_runtime_config import DeploymentConfig, initialize_host, mounts  # noqa: E402


def prepare(directory: Path, rs_source: Path | None = None) -> Path:
    directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    directory.chmod(0o755)
    fixtures = VNEXT / "fixtures/runtime-config/v1"
    storage = json.loads((fixtures / "storage-layout.json").read_bytes())
    profile = json.loads((fixtures / "resource-profile.json").read_bytes())
    storage["filesystems"] = {}
    observed = mounts()
    existing_rs = rs_source is not None and next(rs_source.iterdir(), None) is not None
    for slot, root in storage["roots"].items():
        source = (rs_source if slot.startswith("rs-") and rs_source is not None else directory / "roots") / slot
        if existing_rs and slot.startswith("rs-"):
            if not source.is_dir() or not (source / ".gateway-storage.json").is_file():
                raise ValueError("existing snapshot fixture must contain every initialized RS root")
        else:
            source.mkdir(mode=0o777, parents=True, exist_ok=True)
        # Parent traversal is owned by this isolated fixture. Never change a
        # pre-existing filesystem root or Docker's volume metadata directory.
        if source.parent == directory / "roots":
            source.parent.chmod(0o755)
        containing = max((entry for entry in observed if Path(entry.target) == source or Path(entry.target) in source.parents),
                         key=lambda entry: len(entry.target))
        fs_id = "fs-" + str(containing.mount_id)
        storage["filesystems"][fs_id] = {"mountpoint": containing.target, "expected_source": containing.source,
            "min_free_bytes": 1, "min_free_fraction": 0.000001}
        root["source"] = str(source)
        root["filesystem_id"] = fs_id
    # Resource amounts are still the explicit conservative N1/M24/E32 example;
    # this fixture changes only watermarks for its tiny correctness inputs.
    storage_path, resource_path = directory / "storage-layout.json", directory / "resource-profile.json"
    storage_path.write_text(json.dumps(storage))
    resource_path.write_text(json.dumps(profile))
    storage_path.chmod(0o444)
    resource_path.chmod(0o444)
    config = DeploymentConfig.load(storage_path, resource_path)
    initialize_host(config)
    render = runpy.run_path(str(VNEXT / "scripts/render-runtime-config.py"))["render"]
    override = directory / "compose-runtime.json"
    override.write_text(json.dumps(render(config, storage_path, resource_path)))
    return override


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--rs-source", type=Path)
    args = parser.parse_args()
    print(prepare(args.directory, args.rs_source))


if __name__ == "__main__":
    main()
