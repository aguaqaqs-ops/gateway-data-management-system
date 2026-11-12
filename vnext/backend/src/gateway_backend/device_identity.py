"""Exact business identities and independent processing-group routing keys.

This module is stdlib-only so the host configuration tool uses the same boundary.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid

DEVICE_KEY_HEADER = "X-Gateway-Device-Key"
MAX_REGISTRATION_BODY_BYTES = 8192
_DEPLOYMENT_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")
_ROUTE_KEY = re.compile(r"[0-9a-f]{64}\Z")


def validate_scope_identity(value: object) -> str:
    if type(value) is not str or not 1 <= len(value) <= 255:
        raise ValueError("scope identity must contain 1..255 Unicode scalar values")
    if any(ord(char) == 0 or 0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError("scope identity contains NUL or surrogate")
    if len(value.encode("utf-8")) > 1020:
        raise ValueError("scope identity exceeds 1020 UTF-8 bytes")
    return value


def validate_deployment_identity(value: object) -> str:
    if type(value) is not str or _DEPLOYMENT_ID.fullmatch(value) is None:
        raise ValueError("deployment identity is invalid")
    return value


def validate_device_route_key(value: object) -> str:
    if type(value) is not str or _ROUTE_KEY.fullmatch(value) is None:
        raise ValueError("device route key must be 64 lowercase hex digits")
    return value


def device_route_key(device: str) -> str:
    return hashlib.sha256(validate_scope_identity(device).encode("utf-8")).hexdigest()


def _registration_name(environment: str, group: str, device: str, *, initial: bool) -> str:
    values = [validate_deployment_identity(environment), validate_deployment_identity(group),
        validate_scope_identity(device)]
    if initial:
        values.insert(0, "gateway-device-initial-v1")
    # A string-only array: these separators and unescaped Unicode are its JCS bytes.
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def device_create_key(environment: str, group: str, device: str) -> str:
    name = _registration_name(environment, group, device, initial=False)
    return "p7-device-create-v1:" + hashlib.sha256(name.encode("utf-8")).hexdigest()


def device_initial_node_id(environment: str, group: str, device: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL,
        _registration_name(environment, group, device, initial=True)))
