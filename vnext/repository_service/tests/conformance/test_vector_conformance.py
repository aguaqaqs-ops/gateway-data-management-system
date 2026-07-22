"""Repository Service dev-side vector conformance consumer (WP2 R7)."""

from __future__ import annotations

import pytest

from gateway_shared_kernel.testing import dispatch_case, load_validated_vector_set
from gateway_shared_kernel.testing.dispatch import DispatchMismatch, dispatch_case as sk_dispatch_case
from gateway_shared_kernel.testing.paths import CANDIDATE_MARKER_NAME

from .paths import NORMATIVE_VECTOR_ROOT, resolve_normative_vector_root

EXPECTED_CASE_COUNT = 125


def test_repository_uses_shared_kernel_dispatch_entrypoint() -> None:
    """Repository consumer must call the shared-kernel dispatch entrypoint, not a stub."""
    assert dispatch_case is sk_dispatch_case


def test_repository_dispatch_compares_valid_case_bytes() -> None:
    """Prove the explicit dispatch path performs expected-bytes comparison."""
    root = resolve_normative_vector_root()
    _manifest, cases = load_validated_vector_set(root)
    tampered = dict(cases[0])
    tampered["expected"] = {"canonical_bytes_base64url": "AAAA"}
    with pytest.raises(DispatchMismatch):
        dispatch_case(tampered)


def test_repository_vector_conformance_matches_normative_root() -> None:
    root = resolve_normative_vector_root()
    assert (root / "vector-set.json").is_file()
    assert not (root / CANDIDATE_MARKER_NAME).exists()

    manifest, cases = load_validated_vector_set(root)
    closure_ids = [str(case["case_id"]) for case in cases]

    assert len(closure_ids) == EXPECTED_CASE_COUNT
    assert len(set(closure_ids)) == EXPECTED_CASE_COUNT
    assert closure_ids == sorted(closure_ids, key=lambda item: item.encode("ascii"))

    executed_ids: list[str] = []
    for case in cases:
        dispatch_case(case)
        executed_ids.append(str(case["case_id"]))

    assert executed_ids == closure_ids

    manifest_total = sum(int(entry["case_count"]) for entry in manifest["files"])
    assert manifest_total == EXPECTED_CASE_COUNT
    assert manifest_total == len(closure_ids)
    assert manifest_total == len(executed_ids)


def test_repository_fixed_normative_root_matches_shared_layout() -> None:
    """Repository-computed fixed root must match the monorepo normative layout."""
    root = resolve_normative_vector_root()
    expected = NORMATIVE_VECTOR_ROOT.resolve(strict=True)
    assert root == expected
