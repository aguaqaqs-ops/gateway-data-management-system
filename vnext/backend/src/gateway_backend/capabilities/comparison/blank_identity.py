"""Ordered blank identity according to materialization provenance."""

from gateway_backend.capabilities.comparison.contracts import (
    GID_PSEUDO_MAX, GID_PSEUDO_MIN, GID_REAL_MAX, GID_REAL_MIN,
)
from gateway_backend.capabilities.snapshot_materialization.contracts import BlankRowProvenance


def ordered_blank_identity(gid: object, provenance: BlankRowProvenance) -> bool | None:
    """Return None when the canonical identity cannot be established."""
    if provenance is BlankRowProvenance.SOURCE_MISSING_STABLE_KEY and (gid is None or gid == 0):
        return True
    if type(gid) is not int:
        return None
    if GID_REAL_MIN <= gid <= GID_REAL_MAX:
        return False
    if provenance is BlankRowProvenance.CANONICAL_PSEUDO_GID and GID_PSEUDO_MIN <= gid <= GID_PSEUDO_MAX:
        return True
    return None
