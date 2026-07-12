from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
import time


class SignedTokenError(ValueError):
    """Raised when a formal session token cannot be trusted."""


@dataclass(frozen=True)
class SsoTicketPayload:
    owner_actor_id: str
    gateway_device_external_key: str
    expires_at: int


@dataclass(frozen=True)
class GatewayWorkspaceSessionPayload:
    actor_id: str
    gateway_device_external_key: str
    expires_at: int


def sign_sso_ticket(payload: SsoTicketPayload, *, secret: str) -> str:
    return _sign_token(
        {
            "token_type": "sso_ticket",
            "owner_actor_id": payload.owner_actor_id,
            "gateway_device_external_key": payload.gateway_device_external_key,
            "expires_at": payload.expires_at,
        },
        secret=secret,
    )


def sign_gateway_workspace_session(payload: GatewayWorkspaceSessionPayload, *, secret: str) -> str:
    return _sign_token(
        {
            "token_type": "gateway_workspace_session",
            "actor_id": payload.actor_id,
            "gateway_device_external_key": payload.gateway_device_external_key,
            "expires_at": payload.expires_at,
        },
        secret=secret,
    )


def verify_gateway_workspace_session(
    token: str,
    *,
    secret: str,
    now: int | None = None,
) -> GatewayWorkspaceSessionPayload:
    payload = _verify_token(token, secret=secret, now=now)
    if payload.get("token_type") != "gateway_workspace_session":
        raise SignedTokenError("Invalid gateway workspace session token type.")
    return GatewayWorkspaceSessionPayload(
        actor_id=str(payload["actor_id"]),
        gateway_device_external_key=str(payload["gateway_device_external_key"]),
        expires_at=int(payload["expires_at"]),
    )


def verify_sso_ticket(token: str, *, secret: str, now: int | None = None) -> SsoTicketPayload:
    payload = _verify_token(token, secret=secret, now=now)
    if payload.get("token_type") != "sso_ticket":
        raise SignedTokenError("Invalid SSO ticket token type.")
    return SsoTicketPayload(
        owner_actor_id=str(payload["owner_actor_id"]),
        gateway_device_external_key=str(payload["gateway_device_external_key"]),
        expires_at=int(payload["expires_at"]),
    )


def _sign_token(payload: dict[str, object], *, secret: str) -> str:
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    payload_segment = _encode_segment(payload_json)
    signature = hmac.new(secret.encode("utf-8"), payload_segment.encode("utf-8"), hashlib.sha256).digest()
    return f"{payload_segment}.{_encode_segment(signature)}"


def _verify_token(token: str, *, secret: str, now: int | None = None) -> dict[str, object]:
    try:
        payload_segment, signature_segment = token.split(".", maxsplit=1)
    except ValueError as exc:
        raise SignedTokenError("Malformed token.") from exc

    expected_signature = hmac.new(
        secret.encode("utf-8"),
        payload_segment.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    actual_signature = _decode_segment(signature_segment)
    if not hmac.compare_digest(expected_signature, actual_signature):
        raise SignedTokenError("Invalid token signature.")

    try:
        payload_data = json.loads(_decode_segment(payload_segment).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SignedTokenError("Invalid token payload.") from exc
    if not isinstance(payload_data, dict):
        raise SignedTokenError("Invalid token payload.")

    try:
        expires_at = int(payload_data["expires_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SignedTokenError("Invalid token expiry.") from exc
    now_ts = int(time.time()) if now is None else now
    if expires_at <= now_ts:
        raise SignedTokenError("Token expired.")
    return payload_data


def _encode_segment(raw_bytes: bytes) -> str:
    return base64.urlsafe_b64encode(raw_bytes).decode("utf-8").rstrip("=")


def _decode_segment(raw_value: str) -> bytes:
    padding = "=" * (-len(raw_value) % 4)
    return base64.urlsafe_b64decode(f"{raw_value}{padding}".encode("utf-8"))
