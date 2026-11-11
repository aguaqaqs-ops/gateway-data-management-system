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


def members(payload: bytes) -> dict[str, tuple[int, str | None]]:
    counter = ExpansionCounter(compressed_bytes=len(payload), expanded_bytes=0, entry_count=0)
    result: dict[str, tuple[int, str | None]] = {}
    for member in iter_members(PackageKind.TAR_GZ, payload, None, RESOURCE_BUDGETS, counter):
        digest = hashlib.sha256(member.content).hexdigest() if member.content is not None else None
        result[member.normalized_path.lstrip("/")] = (member.size_bytes, digest)
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
            expected = {entry["path"]: (entry["size"], entry["sha256"]) for entry in item["members"]}
            if sorted(actual) != sorted(expected):
                print(f"PACKAGE {item['name']} FAIL paths differ: expected={sorted(expected)} actual={sorted(actual)}")
                failures += 1
                continue
            mismatch = [path for path, (size, digest) in actual.items()
                        if size != expected[path][0] or (digest is not None and digest != expected[path][1])]
            if mismatch:
                print(f"PACKAGE {item['name']} FAIL member digests differ: {sorted(mismatch)}")
                failures += 1
                continue
            print(f"PACKAGE {item['name']} OK members={len(actual)}")
        else:
            print(f"PACKAGE {item['name']} OK rejected={code}")
    print(f"RESULT packages={len(manifest['packages'])} failures={failures}")
    # N27: the evidence wrapper reads the entry's own end fields from stdout, so
    # the validator must print its exit code itself (the process exit alone is not
    # part of the entry output section).
    print(f"exit_code={1 if failures else 0}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
