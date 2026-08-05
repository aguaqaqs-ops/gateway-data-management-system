"""Immutable bearer auth state resolved once at service startup."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AuthState:
    """Startup-resolved bearer token; must not be re-read from disk per request."""

    bearer_token: str

    def __repr__(self) -> str:
        return "AuthState(<redacted>)"
