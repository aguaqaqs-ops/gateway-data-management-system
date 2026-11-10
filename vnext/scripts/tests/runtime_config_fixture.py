#!/usr/bin/env python3
"""Explicit isolated bind fixture, shared by both Compose test harnesses."""
from __future__ import annotations

import argparse
import json
import os
import stat
import shutil
import runpy
import sys
from pathlib import Path

VNEXT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VNEXT / "scripts"))
from host_runtime_config import DeploymentConfig, initialize_host, mounts  # noqa: E402


OWNER_FILE = ".gateway-runtime-fixture-owner.json"


def _owner(directory: Path, owner: str) -> dict[str, object]:
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or directory.resolve() != directory.absolute():
        raise ValueError("runtime fixture directory is redirected")
    worktree = VNEXT.parent
    if directory == worktree or worktree in directory.parents or directory == Path("/"):
        raise ValueError("runtime fixture must be outside the worktree")
    return {"schema_version": 1, "owner": owner, "device": info.st_dev, "inode": info.st_ino,
            "directory": str(directory.absolute())}


def claim_owner(directory: Path, owner: str) -> None:
    document = _owner(directory, owner)
    record = directory / OWNER_FILE
    if record.exists() or record.is_symlink():
        descriptor = os.open(record, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode) or json.loads(os.read(descriptor, 4097)) != document:
                raise ValueError("runtime fixture has another owner")
        finally:
            os.close(descriptor)
    else:
        if next(directory.iterdir(), None) is not None:
            raise ValueError("new runtime fixture ownership requires an empty directory")
        with record.open("x", encoding="utf-8") as stream:
            json.dump(document, stream, sort_keys=True)


def cleanup(directory: Path, owner: str, *, retain: bool) -> None:
    # Recheck the exact owner and inode; never infer authority from a prefix.
    if not (directory / OWNER_FILE).is_file() or (directory / OWNER_FILE).is_symlink():
        raise ValueError("runtime fixture has no valid existing owner")
    claim_owner(directory, owner)
    if retain:
        print("runtime_fixture_retained=" + str(directory), flush=True)
    else:
        shutil.rmtree(directory)
        print("runtime_fixture_removed=" + str(directory), flush=True)


def prepare(directory: Path, rs_source: Path | None = None, split_root: Path | None = None, owner: str | None = None) -> Path:
    directory.mkdir(mode=0o755, parents=True, exist_ok=True)
    directory.chmod(0o755)
    if owner is not None:
        claim_owner(directory, owner)
    fixtures = VNEXT / "fixtures/runtime-config/v1"
    storage = json.loads((fixtures / "storage-layout.json").read_bytes())
    profile = json.loads((fixtures / "resource-profile.json").read_bytes())
    storage["filesystems"] = {}
    observed = mounts()
    existing_rs = rs_source is not None and next(rs_source.iterdir(), None) is not None
    for slot, root in storage["roots"].items():
        source = (split_root if split_root is not None and slot in {"be-export", "rs-scratch"} else
                  rs_source if slot.startswith("rs-") and rs_source is not None else directory / "roots") / slot
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
    parser.add_argument("--split-root", type=Path)
    parser.add_argument("--owner")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--retain", action="store_true")
    args = parser.parse_args()
    if args.cleanup:
        if args.owner is None:
            parser.error("cleanup requires the exact fixture owner")
        cleanup(args.directory, args.owner, retain=args.retain)
    else:
        print(prepare(args.directory, args.rs_source, args.split_root, args.owner))


if __name__ == "__main__":
    main()
