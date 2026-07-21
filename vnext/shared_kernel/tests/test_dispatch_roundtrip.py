"""Sample dispatch round-trips for catalog seeds."""

from __future__ import annotations

from gateway_shared_kernel.testing.cases.catalog import all_case_seeds
from gateway_shared_kernel.testing.cases.digest import FIXED_EMPTY_ROW_FRAME
from gateway_shared_kernel.testing.codec import encode_base64url
from gateway_shared_kernel.testing.dispatch import compute_expected, dispatch_case


def test_catalog_unique_and_sorted() -> None:
    seeds = all_case_seeds()
    ids = [seed.case_id for seed in seeds]
    assert ids == sorted(ids, key=lambda item: item.encode("ascii"))
    assert len(ids) == len(set(ids))


def test_dispatch_sample_valid_and_invalid() -> None:
    seeds = {seed.case_id: seed for seed in all_case_seeds()}
    empty_row = seeds["digest.row.empty"]
    expected = compute_expected(empty_row.operation, empty_row.input)
    assert expected["row_frame_base64url"] == encode_base64url(FIXED_EMPTY_ROW_FRAME)
    dispatch_case(empty_row.to_envelope(expected))

    semantic = seeds["digest.semantic.row-empty-frame"]
    assert semantic.input["canonical_payload_base64url"] == encode_base64url(
        FIXED_EMPTY_ROW_FRAME
    )
    dispatch_case(semantic.to_envelope(compute_expected(semantic.operation, semantic.input)))

    invalid = seeds["invalid.digest.identifier.collision"]
    dispatch_case(invalid.to_envelope())
