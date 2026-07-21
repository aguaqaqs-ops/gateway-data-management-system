"""Out-of-tree candidate vector-set generator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gateway_shared_kernel import DigestKind, raw_blob_digest, semantic_digest
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_shared_kernel.testing.cases import CaseSeed
from gateway_shared_kernel.testing.cases.catalog import all_case_seeds
from gateway_shared_kernel.testing.dispatch import compute_expected
from gateway_shared_kernel.testing.fs_safety import (
    assert_no_symlink_ancestors,
    assert_regular_directory,
    is_symlink,
)
from gateway_shared_kernel.testing.paths import (
    CANDIDATE_MARKER_NAME,
    CANDIDATE_MARKER_TEXT,
    CASE_SCHEMA_BY_PATH,
    JSONL_FILES,
    resolve_candidate_output_dir,
)


def generate_candidate(output_dir: Path) -> Path:
    """Generate a candidate vector set into a new empty directory.

    Write order: marker → four JSONL (verified from disk) → vector-set.json last.
    """
    requested = Path(output_dir).expanduser()
    assert_no_symlink_ancestors(requested, label="candidate output")
    target = resolve_candidate_output_dir(requested)
    _prepare_empty_directory(requested, target)
    assert_no_symlink_ancestors(requested, label="candidate output after create")
    assert_regular_directory(requested, label="candidate output")

    seeds = all_case_seeds()
    _assert_unique_case_ids(seeds)

    buckets: dict[str, list[dict[str, Any]]] = {
        "digest.jsonl": [],
        "invalid.jsonl": [],
        "jcs.jsonl": [],
        "scalar.jsonl": [],
    }
    for seed in seeds:
        path_name = _bucket_to_path(seed.bucket)
        if seed.expected_error is not None:
            envelope = seed.to_envelope()
        else:
            expected = compute_expected(seed.operation, seed.input)
            envelope = seed.to_envelope(expected)
        buckets[path_name].append(envelope)

    # 1) marker first so interrupted runs are still clearly candidates
    marker_path = requested / CANDIDATE_MARKER_NAME
    if is_symlink(marker_path):
        raise ValueError(f"refusing to write through symlink child {marker_path}")
    marker_path.write_text(CANDIDATE_MARKER_TEXT, encoding="utf-8")

    # 2) JSONL files, then re-read bytes for authoritative metadata
    file_entries: list[dict[str, Any]] = []
    for path_name in JSONL_FILES:
        cases = buckets[path_name]
        cases.sort(key=lambda item: item["case_id"].encode("ascii"))
        raw = _encode_jsonl(cases)
        file_path = requested / path_name
        if is_symlink(file_path):
            raise ValueError(f"refusing to write through symlink child {file_path}")
        file_path.write_bytes(raw)
        on_disk = file_path.read_bytes()
        if on_disk != raw:
            raise ValueError(f"on-disk bytes differ from written payload for {path_name}")
        file_entries.append(
            {
                "path": path_name,
                "media_type": "application/x-ndjson",
                "case_schema_id": CASE_SCHEMA_BY_PATH[path_name],
                "case_count": len(cases),
                "size_bytes": len(on_disk),
                "raw_sha256": raw_blob_digest(on_disk).value,
            }
        )

    # 3) manifest last
    manifest_body: dict[str, Any] = {
        "vector_set_schema_version": 1,
        "vector_set_id": "gateway-vnext.shared-kernel.canonical-encoding.v1",
        "owner": "shared-kernel",
        "contract_binding": {
            "contract_id": "gateway-vnext.shared-canonical-encoding",
            "semantic_version": "1.0.0",
        },
        "canonical_encoding_version": 1,
        "files": file_entries,
    }
    content_digest = semantic_digest(
        DigestKind.VECTOR_SET,
        canonicalize_json_value(manifest_body),
    )
    manifest = {
        **manifest_body,
        "vector_set_content_digest": content_digest.digest_ref.value,
    }
    manifest_path = requested / "vector-set.json"
    if is_symlink(manifest_path):
        raise ValueError(f"refusing to write through symlink child {manifest_path}")
    manifest_path.write_bytes(canonicalize_json_value(manifest) + b"\n")
    return requested.resolve(strict=True)


def _assert_unique_case_ids(seeds: list[CaseSeed]) -> None:
    seen: set[str] = set()
    for seed in seeds:
        case_id = seed.case_id
        if case_id in seen:
            raise ValueError(f"duplicate case_id in catalog: {case_id!r}")
        seen.add(case_id)


def _bucket_to_path(bucket: str) -> str:
    mapping = {
        "jcs": "jcs.jsonl",
        "scalar": "scalar.jsonl",
        "digest": "digest.jsonl",
        "invalid": "invalid.jsonl",
    }
    return mapping[bucket]


def _encode_jsonl(cases: list[dict[str, Any]]) -> bytes:
    if not cases:
        return b""
    lines = [canonicalize_json_value(case) for case in cases]
    return b"\n".join(lines) + b"\n"


def _prepare_empty_directory(requested: Path, target: Path) -> None:
    if requested.exists():
        assert_regular_directory(requested, label="candidate output")
        if any(requested.iterdir()):
            raise ValueError(f"output directory is not empty: {requested}")
        if requested.resolve(strict=True) != target:
            raise ValueError("output path resolved differently than expected")
        return
    assert_no_symlink_ancestors(requested.parent, label="candidate output parent")
    requested.mkdir(parents=False, exist_ok=False)
    assert_no_symlink_ancestors(requested, label="candidate output after create")
    assert_regular_directory(requested, label="candidate output")
    if requested.resolve(strict=True) != target:
        raise ValueError("output path resolved differently after creation")
