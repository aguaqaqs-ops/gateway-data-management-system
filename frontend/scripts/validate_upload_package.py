"""Validate frontend-produced Source Package fixtures with the backend contract."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from gateway_backend.application.workspace.upload_admission import (
    UploadClosureInvalidError,
    validate_source_package_archive,
)
from gateway_backend.capabilities.source_package_staging import (
    ExpansionCounter,
    PackageKind,
    iter_members,
)
from gateway_backend.capabilities.source_package_staging import RESOURCE_BUDGETS


def members(payload: bytes) -> dict[str, str]:
    counter = ExpansionCounter(compressed_bytes=len(payload), expanded_bytes=0, entry_count=0)
    result: dict[str, str] = {}
    for member in iter_members(PackageKind.TAR_GZ, payload, None, RESOURCE_BUDGETS, counter):
        if member.content is None:
            continue
        result[member.normalized_path] = hashlib.sha256(member.content).hexdigest()
    return result


def main() -> int:
    root = Path(sys.argv[1])
    manifest = json.loads((root / "manifest.json").read_text())
    failures = 0
    for item in manifest["packages"]:
        payload = (root / f"{item['name']}.tar.gz").read_bytes()
        try:
            validate_source_package_archive(payload)
            code = "accepted"
        except UploadClosureInvalidError:
            code = "UPLOAD_CLOSURE_INVALID"
        if code != item["expect"]:
            print(f"PACKAGE {item['name']} FAIL expected={item['expect']} actual={code}")
            failures += 1
            continue
        if code == "accepted":
            actual = members(payload)
            expected = {entry["path"]: entry["sha256"] for entry in item["members"]}
            if actual != expected:
                print(f"PACKAGE {item['name']} FAIL members differ: expected={sorted(expected)} actual={sorted(actual)}")
                failures += 1
                continue
            print(f"PACKAGE {item['name']} OK members={len(actual)}")
        else:
            print(f"PACKAGE {item['name']} OK rejected={code}")
    print(f"RESULT packages={len(manifest['packages'])} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
