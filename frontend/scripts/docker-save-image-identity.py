#!/usr/bin/env python3
"""Export and validate config digest plus RootFS DiffIDs from docker save."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
from pathlib import Path
from typing import Any


CONFIG_PATH = re.compile(r"^blobs/sha256/([0-9a-f]{64})$")
DIFF_ID = re.compile(r"^sha256:[0-9a-f]{64}$")


def export_identity(archive_path: Path) -> dict[str, Any]:
    with tarfile.open(archive_path, mode="r:*") as archive:
        manifest_stream = archive.extractfile("manifest.json")
        if manifest_stream is None:
            raise SystemExit("error: docker save archive has no manifest.json")
        manifest = json.load(manifest_stream)
        if not isinstance(manifest, list) or len(manifest) != 1:
            raise SystemExit("error: expected exactly one image in docker save archive")

        image = manifest[0]
        if not isinstance(image, dict):
            raise SystemExit("error: docker save manifest entry is not an object")
        config_path = image.get("Config")
        layers = image.get("Layers")
        if not isinstance(config_path, str) or not isinstance(layers, list):
            raise SystemExit("error: docker save manifest must include Config and Layers")
        if not all(isinstance(layer, str) for layer in layers):
            raise SystemExit("error: docker save Layers must contain paths")

        config_stream = archive.extractfile(config_path)
        if config_stream is None:
            raise SystemExit(f"error: config member is missing: {config_path}")
        config_blob = config_stream.read()
        config = json.loads(config_blob)

    if not isinstance(config, dict):
        raise SystemExit("error: image config is not an object")
    config_digest = hashlib.sha256(config_blob).hexdigest()
    path_match = CONFIG_PATH.fullmatch(config_path)
    if path_match is None or config_digest != path_match.group(1):
        raise SystemExit("error: config content SHA256 does not match its Config path")

    rootfs = config.get("rootfs")
    diff_ids = rootfs.get("diff_ids") if isinstance(rootfs, dict) else None
    if (
        not isinstance(diff_ids, list)
        or not all(isinstance(item, str) and DIFF_ID.fullmatch(item) for item in diff_ids)
    ):
        raise SystemExit("error: config has no valid RootFS DiffID list")
    if len(diff_ids) != len(layers):
        raise SystemExit("error: RootFS DiffID count does not equal Layers count")

    return {
        "config_digest": f"sha256:{config_digest}",
        "config_path": config_path,
        "diff_ids": diff_ids,
        "layers_count": len(layers),
        "manifest_image_count": len(manifest),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path, help="path to a docker save archive")
    arguments = parser.parse_args()
    print(json.dumps(export_identity(arguments.archive), sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
