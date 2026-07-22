"""Read-only vector-set closure validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema.exceptions import ValidationError

from gateway_shared_kernel import DigestKind, raw_blob_digest, semantic_digest
from gateway_shared_kernel.errors import CanonicalEncodingError
from gateway_shared_kernel.jcs import canonicalize_json_value
from gateway_shared_kernel.testing.dispatch import DispatchMismatch, dispatch_case
from gateway_shared_kernel.testing.fs_safety import (
    assert_no_symlink_ancestors,
    assert_regular_directory,
    assert_regular_file,
)
from gateway_shared_kernel.testing.paths import CASE_SCHEMA_BY_PATH, JSONL_FILES
from gateway_shared_kernel.testing.schemas import (
    validate_case_envelope,
    validate_vector_set_manifest,
)
from gateway_shared_kernel.testing.strict_json import (
    DuplicateMemberError,
    NonJsonConstantError,
    loads_object_rejecting_duplicates,
)


class ClosureValidationError(ValueError):
    """Vector-set / JSONL closure failed validation."""


def _load_cases_for_manifest(
    requested: Path,
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    files = manifest["files"]
    if [entry["path"] for entry in files] != list(JSONL_FILES):
        raise ClosureValidationError("files[] path order must match fixed JSONL order")

    all_cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for entry in files:
        path_name = entry["path"]
        case_schema_id = entry["case_schema_id"]
        if CASE_SCHEMA_BY_PATH[path_name] != case_schema_id:
            raise ClosureValidationError(
                f"case_schema_id mismatch for {path_name}: {case_schema_id}"
            )
        file_path = requested / path_name
        try:
            assert_regular_file(file_path, label=path_name)
        except ValueError as exc:
            raise ClosureValidationError(str(exc)) from exc
        raw = file_path.read_bytes()
        if len(raw) != entry["size_bytes"]:
            raise ClosureValidationError(f"size_bytes mismatch for {path_name}")
        if raw_blob_digest(raw).value != entry["raw_sha256"]:
            raise ClosureValidationError(f"raw_sha256 mismatch for {path_name}")

        cases = _parse_and_schema_validate_jsonl(raw, path_name, case_schema_id)
        if len(cases) != entry["case_count"]:
            raise ClosureValidationError(f"case_count mismatch for {path_name}")
        _assert_sorted_unique_case_ids(cases, path_name, seen_ids)
        all_cases.extend(cases)

    return all_cases


def load_validated_vector_set(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load a fully validated vector-set snapshot as ``(manifest, cases)``.

    Performs filesystem safety, manifest/schema validation, per-file hash/count
    checks, case ordering/uniqueness, and ``vector_set_content_digest`` closure in
    a single read pass. Callers that need both manifest and cases must use this
    entrypoint so executed cases always belong to the validated closure.
    """
    requested = Path(root).expanduser()
    try:
        assert_no_symlink_ancestors(requested, label="vector root")
        assert_regular_directory(requested, label="vector root")
    except ValueError as exc:
        raise ClosureValidationError(str(exc)) from exc

    if not requested.exists():
        raise ClosureValidationError(f"vector root does not exist: {requested}")
    resolved = requested.resolve(strict=True)
    manifest_path = resolved / "vector-set.json"
    try:
        assert_regular_file(manifest_path, label="vector-set.json")
    except ValueError as exc:
        raise ClosureValidationError(str(exc)) from exc

    try:
        manifest = loads_object_rejecting_duplicates(
            manifest_path.read_text(encoding="utf-8")
        )
    except (DuplicateMemberError, NonJsonConstantError, ValueError) as exc:
        raise ClosureValidationError(f"vector-set.json: {exc}") from exc

    try:
        validate_vector_set_manifest(manifest)
    except ValidationError as exc:
        raise ClosureValidationError(
            f"vector-set.json schema validation failed: {exc.message}"
        ) from exc

    all_cases = _load_cases_for_manifest(resolved, manifest)
    _assert_content_digest(manifest)
    return manifest, all_cases


def validate_vector_set(
    root: Path,
    *,
    execute_cases: bool = True,
) -> dict[str, Any]:
    """Validate manifest, JSONL integrity, schemas, ordering, and optionally execute cases.

    Per-file case order: parse line → schema validate → then ordering/uniqueness.
    """
    manifest, all_cases = load_validated_vector_set(root)

    if execute_cases:
        for case in all_cases:
            try:
                dispatch_case(case)
            except (DispatchMismatch, Exception) as exc:
                raise ClosureValidationError(
                    f"case execution failed for {case.get('case_id')!r}: {exc}"
                ) from exc

    return manifest


def _parse_and_schema_validate_jsonl(
    raw: bytes,
    path_name: str,
    case_schema_id: str,
) -> list[dict[str, Any]]:
    if raw == b"":
        return []
    if not raw.endswith(b"\n"):
        raise ClosureValidationError(f"{path_name} must end with LF")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ClosureValidationError(f"{path_name} is not valid UTF-8") from exc
    if "\r" in text:
        raise ClosureValidationError(f"{path_name} must use LF line endings only")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    cases: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        if line == "":
            raise ClosureValidationError(f"{path_name} contains empty line at {index}")
        try:
            obj = loads_object_rejecting_duplicates(line)
        except (DuplicateMemberError, NonJsonConstantError, ValueError) as exc:
            raise ClosureValidationError(
                f"{path_name} line {index} is not a strict JSON object: {exc}"
            ) from exc
        try:
            validate_case_envelope(case_schema_id, obj)
        except ValidationError as exc:
            raise ClosureValidationError(
                f"{path_name} line {index} schema validation failed: {exc.message}"
            ) from exc
        try:
            canonical = canonicalize_json_value(obj)
        except CanonicalEncodingError as exc:
            raise ClosureValidationError(
                f"{path_name} line {index} is not JCS-canonical: {exc}"
            ) from exc
        if canonical != line.encode("utf-8"):
            raise ClosureValidationError(
                f"{path_name} line {index} is not JCS-canonical"
            )
        cases.append(obj)
    return cases


def _assert_sorted_unique_case_ids(
    cases: list[dict[str, Any]],
    path_name: str,
    seen_ids: set[str],
) -> None:
    ids = [case["case_id"] for case in cases]
    if ids != sorted(ids, key=lambda item: item.encode("ascii")):
        raise ClosureValidationError(f"{path_name} case_id order is not ASCII-sorted")
    for case_id in ids:
        if case_id in seen_ids:
            raise ClosureValidationError(f"duplicate case_id {case_id!r}")
        seen_ids.add(case_id)


def _assert_content_digest(manifest: dict[str, Any]) -> None:
    declared = manifest["vector_set_content_digest"]
    projected = {
        key: value for key, value in manifest.items() if key != "vector_set_content_digest"
    }
    try:
        projected_bytes = canonicalize_json_value(projected)
    except CanonicalEncodingError as exc:
        raise ClosureValidationError(
            f"vector-set.json projected body is not JCS-canonical: {exc}"
        ) from exc
    digest = semantic_digest(DigestKind.VECTOR_SET, projected_bytes)
    if digest.digest_ref.value != declared:
        raise ClosureValidationError("vector_set_content_digest mismatch")
