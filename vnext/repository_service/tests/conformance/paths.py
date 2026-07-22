"""Repository-owned normative vector root discovery."""

from __future__ import annotations

import os
from pathlib import Path

from gateway_shared_kernel.testing.paths import resolve_vector_root

VECTOR_ROOT_ENV = "GATEWAY_SHARED_KERNEL_VECTOR_ROOT"

# tests/conformance -> tests -> repository_service -> vnext
_VNEXT_ROOT = Path(__file__).resolve().parents[3]

NORMATIVE_VECTOR_ROOT = (
    _VNEXT_ROOT / "fixtures" / "vectors" / "shared-kernel" / "canonical-encoding" / "v1"
)


def resolve_normative_vector_root() -> Path:
    """Resolve the fixed normative vector root for Repository conformance tests."""
    env_value = os.environ.get(VECTOR_ROOT_ENV)
    if env_value:
        return Path(resolve_vector_root(Path(env_value)))
    return Path(resolve_vector_root(NORMATIVE_VECTOR_ROOT))
