"""Required profile matrix execution cells."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gateway_conformance.errors import ConformanceValidationError
from gateway_conformance.harness.canonical_row_hashes.constants import (
    FORMAL_PROVIDER_MATRIX_PROVIDER_IDS,
)
from gateway_conformance.owner.canonical_row_hash import FORMAL_REQUIRED_PROFILES

_PROFILES_REQUIRING_NULL_PROVIDER = frozenset({"reference", "integration"})
_PROFILES_REQUIRING_PROVIDER = frozenset({"provider-matrix"})


@dataclass(frozen=True, slots=True, order=True)
class ExecutionCell:
    profile: str
    provider_id: str | None

    def execution_key_tuple(self) -> tuple[str, str | None]:
        return (self.profile, self.provider_id)


def expand_required_cells(manifest: dict[str, Any]) -> tuple[ExecutionCell, ...]:
    """Expand manifest required_profiles into the fixed formal matrix cells."""

    profiles = [str(item) for item in manifest.get("required_profiles", [])]
    if profiles != FORMAL_REQUIRED_PROFILES:
        raise ConformanceValidationError(
            "canonical-row-hash formal scenario required_profiles must be "
            "integration, provider-matrix, reference in that order"
        )
    cells: list[ExecutionCell] = []
    for profile in profiles:
        if profile in _PROFILES_REQUIRING_NULL_PROVIDER:
            cells.append(ExecutionCell(profile=profile, provider_id=None))
        elif profile in _PROFILES_REQUIRING_PROVIDER:
            for provider_id in FORMAL_PROVIDER_MATRIX_PROVIDER_IDS:
                cells.append(ExecutionCell(profile=profile, provider_id=provider_id))
        else:
            raise ConformanceValidationError(f"unsupported required profile: {profile}")
    return tuple(cells)
