from __future__ import annotations

from collections.abc import Mapping

from ...core.digests import DigestRef


def build_surface_digest(surface: object) -> DigestRef:
    payload_for_digest = getattr(surface, "payload_for_digest", None)
    if not callable(payload_for_digest):
        raise TypeError("surface must provide payload_for_digest()")
    payload = payload_for_digest()
    if not isinstance(payload, Mapping):
        raise TypeError("surface payload_for_digest() must return a mapping")
    return DigestRef.from_payload(payload)

