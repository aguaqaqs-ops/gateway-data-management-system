"""Conservative comparison of two verified Preview bundle transports.

This fails closed on scope-derived digest differences that cannot be mapped:
absence of a difference is evidence of equality, while a difference requires
inspection and is not automatically a product finding. No business field,
digest, pair ID, table ID, timestamp, or risk/navigation value is discarded.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import tarfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import JsonValue, TypeAdapter
import pyarrow as pa
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from benchmarks.bundle_tar import verify_bundle_tar
from gateway_backend.capabilities.bundle_assembly.contracts import BundleArtifactKind, BundleClosureEntry
from gateway_backend.capabilities.bundle_assembly.transport import read_bundle_transport_metadata

JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


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
            paths[entry.logical_path] = role
        refs = {key: json.dumps(sorted(roles), ensure_ascii=False, separators=(",", ":"))
                for key, roles in grouped_refs.items()}
        return manifest, entries, refs, paths


def compare(left: Path, right: Path, *, left_repository: str, right_repository: str) -> dict[str, Any]:
    lmanifest, lentries, lrefs, lpaths = _archive(left)
    rmanifest, rentries, rrefs, rpaths = _archive(right)
    differences: list[dict[str, str]] = []
    roles = sorted(set(lentries) | set(rentries))
    kinds: dict[str, int] = {}
    with tarfile.open(left, "r:") as left_tar, tarfile.open(right, "r:") as right_tar:
        return _compare_roles(roles, lentries, rentries, lrefs, rrefs, lpaths, rpaths, differences, kinds,
                              left_tar, right_tar, left, right, left_repository, right_repository, lmanifest, rmanifest)


def _compare_roles(roles: list[str], lentries: dict[str, BundleClosureEntry],
                   rentries: dict[str, BundleClosureEntry], lrefs: dict[str, str], rrefs: dict[str, str],
                   lpaths: dict[str, str], rpaths: dict[str, str], differences: list[dict[str, str]],
                   kinds: dict[str, int], left_tar: tarfile.TarFile, right_tar: tarfile.TarFile,
                   left: Path, right: Path, left_repository: str, right_repository: str,
                   lmanifest: dict[str, Any], rmanifest: dict[str, Any]) -> dict[str, Any]:
    equivalent: set[str] = set()
    pending_json: dict[str, tuple[Any, Any]] = {}
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
        if le.kind is BundleArtifactKind.SNAPSHOT_TABLE and le.artifact_ref.media_type == "application/vnd.apache.parquet":
            ls = left_tar.extractfile(le.logical_path)
            rs = right_tar.extractfile(re.logical_path)
            if ls is not None and rs is not None and _parquet_equal(ls, rs, left_repository, right_repository):
                equivalent.add(role)
            else:
                differences.append({"role": role, "reason": "snapshot content, metadata, or repository scope differs"})
            continue
        if le.raw_sha256 == re.raw_sha256 and le.size_bytes == re.size_bytes:
            equivalent.add(role)
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
            pending_json[role] = (lv, rv)
            continue
        differences.append({"role": role, "reason": "member content differs"})
    # Propagate only from content already proven equivalent. Unresolved cycles or
    # fields not covered by a complete exact ref stay unequal, not masked.
    while pending_json:
        newly_equivalent = {
            role for role, (lv, rv) in pending_json.items()
            if _map_proven_refs(lv, lentries, equivalent) == _map_proven_refs(rv, rentries, equivalent)
        }
        if not newly_equivalent:
            break
        equivalent.update(newly_equivalent)
        for role in newly_equivalent:
            del pending_json[role]
    differences.extend({"role": role, "reason": "JSON content or unresolved child reference differs"}
                       for role in sorted(pending_json))
    if (_manifest_roles(lmanifest, lentries, lrefs, lpaths, equivalent)
            != _manifest_roles(rmanifest, rentries, rrefs, rpaths, equivalent)):
        differences.append({"role": "manifest", "reason": "verified manifest differs after proven scope mapping"})
    return {"equal": not differences, "verified_tar_sha256": [
        _file_hash(left), _file_hash(right)],
        "compared_roles": len(roles), "compared_kinds": kinds, "differences": differences,
        "scope_mapping": "only verified closure identities and integrity values of proven-equivalent members map to exact roles; snapshot footer repository mapped to supplied identities",
        "retained": "all business, risk, navigation, table, side, pair and time fields; non-closure digests compared strictly",
        "limitation": "scope-derived digest or binary differences remain unequal pending investigation"}


def _map_proven_refs(value: Any, entries: dict[str, BundleClosureEntry], equivalent: set[str]) -> Any:
    if isinstance(value, list):
        return [_map_proven_refs(item, entries, equivalent) for item in value]
    if isinstance(value, dict):
        if set(value) == {"artifact_id", "media_type", "size_bytes", "raw_sha256"}:
            matches = [role for role, entry in entries.items()
                if value == {"artifact_id": entry.artifact_ref.artifact_id,
                             "media_type": entry.artifact_ref.media_type,
                             "size_bytes": entry.artifact_ref.size_bytes,
                             "raw_sha256": entry.artifact_ref.raw_sha256.value}]
            if matches and all(role in equivalent for role in matches):
                return {"verified_equivalent_roles": sorted(matches), "media_type": value["media_type"]}
        return {key: _map_proven_refs(item, entries, equivalent) for key, item in value.items()}
    return value


def _manifest_roles(manifest: dict[str, Any], entries: dict[str, BundleClosureEntry], refs: dict[str, str],
                    paths: dict[str, str], equivalent: set[str]) -> Any:
    """Normalize only validated closure integrity of members compared equal.

    verify_bundle_tar has already verified each input manifest, closure and raw
    SHA. Substitution ties each differing integrity value to the same role whose
    full bytes or typed Parquet contents were independently compared above.
    """
    doc = copy.deepcopy(manifest)
    doc["bundle_digest"] = "<verified-manifest-digest>"
    doc["closure_manifest_digest"] = "<verified-closure-digest>"
    lists = [doc["closure_entries"], doc["closure"]["entries"]]
    for group in lists:
        for item in group:
            path = item["logical_path"]
            role = paths.get(path)
            if role is None or role not in equivalent:
                continue
            entry = entries[role]
            token = {"compared_role": role}
            if "artifact_ref" in item:
                item["artifact_ref"] = {"compared_role": role, "media_type": entry.artifact_ref.media_type}
            if "raw_sha256" in item:
                item["raw_sha256"] = token
            if "size_bytes" in item:
                item["size_bytes"] = token
            if "integrity" in item:
                item["integrity"]["raw_sha256"] = token
                item["integrity"]["size_bytes"] = token
    return _map_value(_map_proven_refs(doc, entries, equivalent), refs=refs, paths=paths)


def _parquet_equal(left: Any, right: Any, left_repository: str, right_repository: str) -> bool:
    """Compare schema and ordered rows, mapping only the verified repository footer."""
    lp, rp = pq.ParquetFile(left), pq.ParquetFile(right)
    lm, rm = dict(lp.schema_arrow.metadata or {}), dict(rp.schema_arrow.metadata or {})
    key = b"gdds.client.repository_id"
    if key in lm or key in rm:
        if lm.get(key) != left_repository.encode() or rm.get(key) != right_repository.encode():
            return False
        lm[key] = rm[key] = b"<repository-scope>"
    if lm != rm or not lp.schema_arrow.remove_metadata().equals(rp.schema_arrow.remove_metadata(), check_metadata=True):
        return False
    return _batches_equal(lp.iter_batches(batch_size=4096, use_threads=False),
                          rp.iter_batches(batch_size=4096, use_threads=False))


def _batches_equal(left: Iterator[pa.RecordBatch], right: Iterator[pa.RecordBatch]) -> bool:
    left_batch, right_batch = next(left, None), next(right, None)
    li = ri = 0
    while left_batch is not None and right_batch is not None:
        count = min(left_batch.num_rows - li, right_batch.num_rows - ri)
        if not left_batch.slice(li, count).equals(right_batch.slice(ri, count), check_metadata=False):
            return False
        li += count
        ri += count
        if li == left_batch.num_rows:
            left_batch, li = next(left, None), 0
        if ri == right_batch.num_rows:
            right_batch, ri = next(right, None), 0
    return left_batch is None and right_batch is None


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
    parser.add_argument("--left-repository", required=True)
    parser.add_argument("--right-repository", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.left, args.right, left_repository=args.left_repository, right_repository=args.right_repository)
    with args.output.open("x", encoding="utf-8") as target:
        json.dump(report, target, ensure_ascii=False, sort_keys=True, indent=2)
        target.write("\n")
    return 0 if report["equal"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
