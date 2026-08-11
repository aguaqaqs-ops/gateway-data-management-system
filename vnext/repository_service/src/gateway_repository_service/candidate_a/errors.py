"""Shared Candidate A primitive errors for probe and production paths."""


class CandidateAError(RuntimeError):
    """Base error for Candidate A SQL and CLI primitive failures."""


class DoltCliStreamCancelledError(CandidateAError):
    """Raised when a Dolt row stream is cancelled before completion."""
