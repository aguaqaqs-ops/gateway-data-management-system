"""Baseline domain errors."""

from __future__ import annotations


class BaselineHeadVersionConflict(Exception):
    """Expected baseline head version does not match persisted authority."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
