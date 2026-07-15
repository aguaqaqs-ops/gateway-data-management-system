from __future__ import annotations

from .degraded import build_degraded_annotations
from .ordered import build_ordered_annotations
from .ordered_placeholder import build_ordered_placeholder_annotations
from .standard_basic import build_standard_annotations
from .structural import build_structural_annotations

__all__ = [
    "build_degraded_annotations",
    "build_ordered_annotations",
    "build_ordered_placeholder_annotations",
    "build_standard_annotations",
    "build_structural_annotations",
]
