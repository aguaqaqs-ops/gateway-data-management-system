"""Register production harness for formal canonical-row-hash subject."""

from __future__ import annotations

from gateway_conformance.harness.canonical_row_hashes.harness import (
    CanonicalRowHashesSubjectHarness,
)
from gateway_conformance.runner.registry import (
    FORMAL_PRODUCTION_SUBJECT_KEY,
    SubjectHarnessRegistry,
)


def register_production_canonical_row_hashes_harness(registry: SubjectHarnessRegistry) -> None:
    def factory() -> CanonicalRowHashesSubjectHarness:
        return CanonicalRowHashesSubjectHarness()

    registry.register(
        FORMAL_PRODUCTION_SUBJECT_KEY,
        factory,
        harness_provenance="production",
    )
