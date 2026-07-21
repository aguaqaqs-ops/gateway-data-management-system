"""Aggregate and sort all candidate case seeds."""

from __future__ import annotations

from gateway_shared_kernel.testing.cases import CaseSeed
from gateway_shared_kernel.testing.cases.digest import digest_seeds
from gateway_shared_kernel.testing.cases.jcs import jcs_seeds
from gateway_shared_kernel.testing.cases.scalar import scalar_seeds


def all_case_seeds() -> list[CaseSeed]:
    seeds = [*jcs_seeds(), *scalar_seeds(), *digest_seeds()]
    ids = [seed.case_id for seed in seeds]
    if len(ids) != len(set(ids)):
        dupes = sorted({item for item in ids if ids.count(item) > 1})
        raise ValueError(f"duplicate case_id in catalog: {dupes}")
    return sorted(seeds, key=lambda seed: seed.case_id.encode("ascii"))
