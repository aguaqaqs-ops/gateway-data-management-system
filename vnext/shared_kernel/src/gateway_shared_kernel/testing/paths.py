"""Filesystem roots for schemas and the forbidden normative vector path."""

from __future__ import annotations

from pathlib import Path

from gateway_shared_kernel.testing.fs_safety import assert_no_symlink_ancestors

# testing/paths.py -> testing -> gateway_shared_kernel -> src -> shared_kernel -> vnext
_VNEXT_ROOT = Path(__file__).resolve().parents[4]

SCHEMA_ROOT = (
    _VNEXT_ROOT / "fixtures" / "schemas" / "shared-kernel" / "canonical-encoding" / "v1"
)

NORMATIVE_VECTOR_ROOT = (
    _VNEXT_ROOT / "fixtures" / "vectors" / "shared-kernel" / "canonical-encoding" / "v1"
)

SCHEMA_FILES = (
    "definitions.schema.json",
    "vector-set.schema.json",
    "jcs-case.schema.json",
    "scalar-case.schema.json",
    "digest-case.schema.json",
    "invalid-case.schema.json",
)

JSONL_FILES = (
    "digest.jsonl",
    "invalid.jsonl",
    "jcs.jsonl",
    "scalar.jsonl",
)

CASE_SCHEMA_BY_PATH = {
    "digest.jsonl": "gateway-vnext.canonical-encoding.digest-case.v1",
    "invalid.jsonl": "gateway-vnext.canonical-encoding.invalid-case.v1",
    "jcs.jsonl": "gateway-vnext.canonical-encoding.jcs-case.v1",
    "scalar.jsonl": "gateway-vnext.canonical-encoding.scalar-case.v1",
}

CASE_SCHEMA_FILE_BY_ID = {
    "gateway-vnext.canonical-encoding.digest-case.v1": "digest-case.schema.json",
    "gateway-vnext.canonical-encoding.invalid-case.v1": "invalid-case.schema.json",
    "gateway-vnext.canonical-encoding.jcs-case.v1": "jcs-case.schema.json",
    "gateway-vnext.canonical-encoding.scalar-case.v1": "scalar-case.schema.json",
}

CANDIDATE_MARKER_NAME = "CANDIDATE_PENDING_WP2_CONFIRMATION"

CANDIDATE_MARKER_TEXT = (
    "This directory is a WP1 candidate vector set pending independent "
    "Rust confirmation (WP2). It is not a published normative vector root.\n"
)


def vnext_root() -> Path:
    return _VNEXT_ROOT


def resolve_candidate_output_dir(path: Path) -> Path:
    """Resolve a generate output path; refuse the fixed normative vector root tree."""
    requested = path.expanduser()
    assert_no_symlink_ancestors(requested, label="candidate output")
    resolved = requested.resolve(strict=False)
    normative = NORMATIVE_VECTOR_ROOT.resolve(strict=False)
    try:
        resolved.relative_to(normative)
    except ValueError:
        return resolved
    raise ValueError(
        "refusing to write under the fixed normative vector root as a candidate"
    )


def resolve_vector_root(path: Path) -> Path:
    """Resolve a read-only vector-set directory (candidate or normative)."""
    requested = path.expanduser()
    assert_no_symlink_ancestors(requested, label="vector root")
    resolved = requested.resolve(strict=True)
    return resolved


# Back-compat alias used by older call sites within this package.
def resolve_output_dir(path: Path) -> Path:
    return resolve_candidate_output_dir(path)
