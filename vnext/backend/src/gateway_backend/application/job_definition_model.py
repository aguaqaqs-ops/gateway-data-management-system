"""Leaf JobDefinition descriptor types (no registry or payload decode edges)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from gateway_backend.application.recovery import RecoveryCapability
from gateway_backend.operations.contracts import JobStepKey

_CONTRACT_VERSION_RE = re.compile(r"^[\x20-\x7e]{1,128}$")


class NormalPublicationCapability(StrEnum):
    """Static normal completion path for one JobDefinition step."""

    SINGLE_SUCCESSOR = "SINGLE_SUCCESSOR"
    TERMINAL = "TERMINAL"


def validate_contract_version_string(value: object, label: str) -> None:
    if type(value) is not str:
        raise ValueError(f"{label} must be a string")
    if not _CONTRACT_VERSION_RE.fullmatch(value):
        raise ValueError(f"{label} must be bounded ASCII printable")


@dataclass(frozen=True, slots=True)
class JobDefinition:
    """Immutable JobDefinition descriptor without business entities or callables."""

    key: JobStepKey
    supported_payload_versions: frozenset[str]
    decoder_identity: str
    handler_identity: str
    publication_capability: NormalPublicationCapability
    recovery_capability: RecoveryCapability

    def __post_init__(self) -> None:
        if type(self.key) is not JobStepKey:
            raise ValueError("key must be JobStepKey")
        if type(self.supported_payload_versions) is not frozenset:
            raise ValueError("supported_payload_versions must be frozenset")
        if not self.supported_payload_versions:
            raise ValueError("supported_payload_versions must not be empty")
        for version in self.supported_payload_versions:
            validate_contract_version_string(version, "supported_payload_versions")
        validate_contract_version_string(self.decoder_identity, "decoder_identity")
        validate_contract_version_string(self.handler_identity, "handler_identity")
        if type(self.publication_capability) is not NormalPublicationCapability:
            raise ValueError("publication_capability must be NormalPublicationCapability")
        if type(self.recovery_capability) is not RecoveryCapability:
            raise ValueError("recovery_capability must be RecoveryCapability")


__all__ = [
    "JobDefinition",
    "NormalPublicationCapability",
    "validate_contract_version_string",
]
