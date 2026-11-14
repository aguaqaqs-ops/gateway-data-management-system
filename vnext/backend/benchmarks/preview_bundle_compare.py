"""Conservative comparison of two verified Preview bundle transports.

This fails closed on scope-derived digest differences that cannot be mapped:
absence of a difference is evidence of equality, while a difference requires
inspection and is not automatically a product finding. No business field,
digest, pair ID, table ID, timestamp, or risk/navigation value is discarded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from pathlib import Path
from typing import Any

from pydantic import JsonValue, TypeAdapter

from benchmarks.bundle_tar import verify_bundle_tar
from gateway_backend.capabilities.bundle_assembly.contracts import BundleArtifactKind, BundleClosureEntry
from gateway_backend.capabilities.bundle_assembly.transport import read_bundle_transport_metadata

JSON = TypeAdapter(JsonValue)


def _role(entry: BundleClosureEntry) -> str:
    if entry.kind is BundleArtifactKind.SNAPSHOT_TABLE:
        bindings = [[item.pair_id, item.table_name, item.side.value] for item in entry.table_bindings]
        key: list[Any] = [entry.kind.value, entry.shared, bindings]
    else:
        key = [entry.kind.value, entry.pair_id, entry.table_name, entry.shared, entry.logical_path]
    return json.dumps(key, ensure_ascii=False, separators=(",", ":"))


def _map_value(value: Any, *, refs: dict[str, str], paths: dict[str, str]) -> Any:
    if isinstance(value, list):
        return [_map_value(item, refs=refs, paths=paths) for item in value]
    if isinstance(value, dict):
        mapped = {key: _map_value(item, refs=refs, paths=paths) for key, item in value.items()}
        # Only a complete minimal ref can be scope-mapped; its remaining integrity
        # fields are still compared. Missing/unknown references remain unchanged.
        if set(value) == {"artifact_id", "media_type", "size_bytes", "raw_sha256"}:
            artifact_id = value["artifact_id"]
            if isinstance(artifact_id, str) and artifact_id in refs:
                mapped["artifact_id"] = {"bundle_role": refs[artifact_id]}
        logical = value.get("logical_path")
        if isinstance(logical, str) and logical in paths:
            mapped["logical_path"] = {"bundle_role": paths[logical]}
        return mapped
    return value


def _archive(path: Path) -> tuple[dict[str, Any], dict[str, BundleClosureEntry],
                                  dict[str, str], dict[str, str]]:
    with path.open("rb") as stream:
        manifest, _ = verify_bundle_tar(stream, total_bytes=path.stat().st_size)
    with tarfile.open(path, "r:") as archive:
        manifest_stream = archive.extractfile("manifest.json")
        if manifest_stream is None:
            raise ValueError("manifest is unavailable")
        metadata = read_bundle_transport_metadata(manifest_stream.read())
        entries: dict[str, BundleClosureEntry] = {}
        grouped_refs: dict[str, list[str]] = {}
        paths: dict[str, str] = {}
        for entry in metadata.entries:
            role = _role(entry)
            if role in entries:
                raise ValueError("ambiguous bundle role")
            entries[role] = entry
            grouped_refs.setdefault(entry.artifact_ref.artifact_id, []).append(role)
            if entry.kind is BundleArtifactKind.SNAPSHOT_TABLE and entry.shared:
                paths[entry.logical_path] = role
        refs = {key: json.dumps(sorted(roles), ensure_ascii=False, separators=(",", ":"))
                for key, roles in grouped_refs.items()}
        return manifest, entries, refs, paths


def compare(left: Path, right: Path) -> dict[str, Any]:
    lmanifest, lentries, lrefs, lpaths = _archive(left)
    rmanifest, rentries, rrefs, rpaths = _archive(right)
    differences: list[dict[str, str]] = []
    if _map_value(lmanifest, refs=lrefs, paths=lpaths) != _map_value(rmanifest, refs=rrefs, paths=rpaths):
        differences.append({"role": "manifest", "reason": "document differs after explicit reference mapping"})
    roles = sorted(set(lentries) | set(rentries))
    kinds: dict[str, int] = {}
    with tarfile.open(left, "r:") as left_tar, tarfile.open(right, "r:") as right_tar:
        return _compare_roles(roles, lentries, rentries, lrefs, rrefs, lpaths, rpaths, differences, kinds,
                              left_tar, right_tar, left, right)


def _compare_roles(roles: list[str], lentries: dict[str, BundleClosureEntry],
                   rentries: dict[str, BundleClosureEntry], lrefs: dict[str, str], rrefs: dict[str, str],
                   lpaths: dict[str, str], rpaths: dict[str, str], differences: list[dict[str, str]],
                   kinds: dict[str, int], left_tar: tarfile.TarFile, right_tar: tarfile.TarFile,
                   left: Path, right: Path) -> dict[str, Any]:
    for role in roles:
        if role not in lentries or role not in rentries:
            differences.append({"role": role, "reason": "missing or changed pair/table/side binding"})
            continue
        le = lentries[role]
        re = rentries[role]
        kinds[le.kind.value] = kinds.get(le.kind.value, 0) + 1
        if le.artifact_ref.media_type != re.artifact_ref.media_type:
            differences.append({"role": role, "reason": "media type differs"})
            continue
        if le.raw_sha256 == re.raw_sha256 and le.size_bytes == re.size_bytes:
            continue
        if ("json" in le.artifact_ref.media_type.casefold()
                and le.size_bytes <= 16 * 1024**2 and re.size_bytes <= 16 * 1024**2):
            try:
                ls = left_tar.extractfile(le.logical_path)
                rs = right_tar.extractfile(re.logical_path)
                if ls is None or rs is None:
                    raise ValueError("member is unavailable")
                lv = JSON.validate_json(ls.read(), strict=True)
                rv = JSON.validate_json(rs.read(), strict=True)
            except ValueError:
                differences.append({"role": role, "reason": "JSON decoding failed"})
                continue
            if _map_value(lv, refs=lrefs, paths=lpaths) == _map_value(rv, refs=rrefs, paths=rpaths):
                continue
        differences.append({"role": role, "reason": "member content differs"})
    return {"equal": not differences, "verified_tar_sha256": [
        _file_hash(left), _file_hash(right)],
        "compared_roles": len(roles), "compared_kinds": kinds, "differences": differences,
        "scope_mapping": "only complete closure artifact refs and shared snapshot logical paths map to exact roles",
        "retained": "all digest, business, risk, navigation, table, side, pair and time fields",
        "limitation": "scope-derived digest or binary differences remain unequal pending investigation"}


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left", type=Path)
    parser.add_argument("right", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.left, args.right)
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(report, target, ensure_ascii=False, sort_keys=True, indent=2)
        target.write("\n")
    return 0 if report["equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
