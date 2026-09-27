"""Comparison execution errors."""

from __future__ import annotations


class StandardComparisonError(ValueError):
    """A table-local comparison failure that must not be treated as an empty table."""
