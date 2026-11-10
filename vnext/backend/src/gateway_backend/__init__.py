"""Backend application entrypoint, imported lazily by host deployment tooling."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gateway_backend.app import create_app as create_app

__all__ = ["create_app"]


def __getattr__(name: str) -> object:
    if name == "create_app":
        from gateway_backend.app import create_app
        return create_app
    raise AttributeError(name)
