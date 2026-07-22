"""Candidate generator safety and offline generate→validate loop."""

from __future__ import annotations

from pathlib import Path

import pytest

from gateway_shared_kernel.testing import generate_candidate, validate_vector_set
from gateway_shared_kernel.testing.closure import ClosureValidationError, load_validated_vector_set
from gateway_shared_kernel.testing.paths import (
    CANDIDATE_MARKER_NAME,
    NORMATIVE_VECTOR_ROOT,
)


def test_generate_and_validate_in_tmp(tmp_path: Path) -> None:
    out = tmp_path / "candidate"
    generate_candidate(out)
    assert (out / CANDIDATE_MARKER_NAME).is_file()
    assert (out / "vector-set.json").is_file()
    for name in ("digest.jsonl", "invalid.jsonl", "jcs.jsonl", "scalar.jsonl"):
        assert (out / name).is_file()
    validate_vector_set(out)


def test_rejects_non_empty_directory(tmp_path: Path) -> None:
    out = tmp_path / "candidate"
    out.mkdir()
    (out / "stale.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="not empty"):
        generate_candidate(out)


def test_rejects_normative_vector_root() -> None:
    with pytest.raises(ValueError, match="normative"):
        generate_candidate(NORMATIVE_VECTOR_ROOT)


def test_rejects_normative_vector_subdirectory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="normative"):
        generate_candidate(NORMATIVE_VECTOR_ROOT / "nested-candidate")


def test_rejects_broken_symlink_ancestor(tmp_path: Path) -> None:
    broken = tmp_path / "broken-parent"
    broken.symlink_to(tmp_path / "does-not-exist", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        generate_candidate(broken / "candidate")


def test_write_order_marker_before_manifest(tmp_path: Path) -> None:
    out = tmp_path / "candidate"
    generate_candidate(out)
    # Marker must exist alongside final manifest; write order is marker→JSONL→manifest.
    assert (out / CANDIDATE_MARKER_NAME).is_file()
    assert (out / "vector-set.json").is_file()


def test_rejects_manifest_non_json_constant(tmp_path: Path) -> None:
    out = tmp_path / "candidate"
    generate_candidate(out)
    (out / "vector-set.json").write_text('{"x":NaN}\n', encoding="utf-8")
    with pytest.raises(ClosureValidationError, match="non-JSON constant|NaN"):
        validate_vector_set(out, execute_cases=False)


def test_rejects_jsonl_non_json_constant(tmp_path: Path) -> None:
    out = tmp_path / "candidate"
    generate_candidate(out)
    (out / "jcs.jsonl").write_text('{"x":Infinity}\n', encoding="utf-8")
    # size/hash will also mismatch; force metadata to match poisoned bytes first.
    poisoned = (out / "jcs.jsonl").read_bytes()
    from gateway_shared_kernel import raw_blob_digest
    import json

    manifest = json.loads((out / "vector-set.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        if entry["path"] == "jcs.jsonl":
            entry["size_bytes"] = len(poisoned)
            entry["raw_sha256"] = raw_blob_digest(poisoned).value
            entry["case_count"] = 1
    # Manifest itself must be rewritten without going through JCS (contains only ASCII).
    # Use duplicate-free JSON that still fails content digest later; we only need JSONL reject.
    from gateway_shared_kernel.jcs import canonicalize_json_value

    # Drop content digest check by making a valid projected digest after file metadata update.
    body = {k: v for k, v in manifest.items() if k != "vector_set_content_digest"}
    from gateway_shared_kernel import DigestKind, semantic_digest

    digest = semantic_digest(DigestKind.VECTOR_SET, canonicalize_json_value(body))
    body["vector_set_content_digest"] = digest.digest_ref.value
    (out / "vector-set.json").write_bytes(canonicalize_json_value(body) + b"\n")
    with pytest.raises(ClosureValidationError, match="non-JSON constant|Infinity|strict JSON"):
        validate_vector_set(out, execute_cases=False)


def test_generate_does_not_create_normative_root(tmp_path: Path) -> None:
    before = NORMATIVE_VECTOR_ROOT.exists()
    generate_candidate(tmp_path / "candidate")
    assert NORMATIVE_VECTOR_ROOT.exists() is before


def test_rejects_symlink_directory(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        generate_candidate(link)


def test_rejects_ancestor_symlink_for_generate(tmp_path: Path) -> None:
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    link_parent = tmp_path / "link-parent"
    link_parent.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        generate_candidate(link_parent / "candidate")


def test_rejects_child_jsonl_symlink_on_validate(tmp_path: Path) -> None:
    out = tmp_path / "candidate"
    generate_candidate(out)
    outside = tmp_path / "outside-jcs.jsonl"
    outside.write_bytes((out / "jcs.jsonl").read_bytes())
    (out / "jcs.jsonl").unlink()
    (out / "jcs.jsonl").symlink_to(outside)
    with pytest.raises(ClosureValidationError, match="symlink"):
        validate_vector_set(out)


def test_rejects_manifest_duplicate_member(tmp_path: Path) -> None:
    out = tmp_path / "candidate"
    generate_candidate(out)
    manifest = out / "vector-set.json"
    text = manifest.read_text(encoding="utf-8").rstrip("\n")
    # Inject a duplicate "owner" member before the closing brace.
    assert text.endswith("}")
    poisoned = text[:-1] + ',"owner":"shared-kernel"}'
    manifest.write_text(poisoned + "\n", encoding="utf-8")
    with pytest.raises(ClosureValidationError, match="duplicate"):
        validate_vector_set(out, execute_cases=False)


def test_rejects_jsonl_escaped_lone_surrogate_as_closure_error(tmp_path: Path) -> None:
    """Schema-valid JSONL with \\uD800 must not leak CanonicalEncodingError."""
    import json

    from gateway_shared_kernel import DigestKind, raw_blob_digest, semantic_digest
    from gateway_shared_kernel.errors import CanonicalEncodingError
    from gateway_shared_kernel.jcs import canonicalize_json_value

    out = tmp_path / "candidate"
    generate_candidate(out)
    # identifier is an unconstrained string in digest-case schema; escaped lone
    # surrogate passes schema but fails JCS canonicalize.
    line = (
        '{"case_schema_version":1,"case_id":"digest.identifier.surrogate",'
        '"expected":{"canonical_utf8_base64url":""},'
        '"input":{"identifier":"\\uD800"},'
        '"operation":"canonicalize-identifier"}\n'
    )
    (out / "digest.jsonl").write_text(line, encoding="utf-8")
    poisoned = (out / "digest.jsonl").read_bytes()
    manifest = json.loads((out / "vector-set.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        if entry["path"] == "digest.jsonl":
            entry["size_bytes"] = len(poisoned)
            entry["raw_sha256"] = raw_blob_digest(poisoned).value
            entry["case_count"] = 1
    body = {k: v for k, v in manifest.items() if k != "vector_set_content_digest"}
    digest = semantic_digest(DigestKind.VECTOR_SET, canonicalize_json_value(body))
    body["vector_set_content_digest"] = digest.digest_ref.value
    (out / "vector-set.json").write_bytes(canonicalize_json_value(body) + b"\n")

    with pytest.raises(ClosureValidationError, match="JCS-canonical") as exc_info:
        validate_vector_set(out, execute_cases=False)
    assert not isinstance(exc_info.value, CanonicalEncodingError)
    assert isinstance(exc_info.value.__cause__, CanonicalEncodingError)


def test_load_validated_vector_set_rejects_invalid_content_digest(tmp_path: Path) -> None:
    import json

    out = tmp_path / "candidate"
    generate_candidate(out)
    validate_vector_set(out, execute_cases=False)

    manifest_path = out / "vector-set.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["vector_set_content_digest"] = "sha256:" + ("00" * 32)
    manifest_path.write_text(json.dumps(manifest, separators=(",", ":")) + "\n", encoding="utf-8")

    with pytest.raises(ClosureValidationError, match="vector_set_content_digest mismatch"):
        load_validated_vector_set(out)
