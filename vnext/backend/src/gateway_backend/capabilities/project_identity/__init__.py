"""Canonical project identity rule capability."""

from gateway_backend.capabilities.project_identity._rule import assess_project_identity
from gateway_backend.capabilities.project_identity.contracts import (
    PROJECT_IDENTITY_RULE_VERSION,
    PROJECT_IDENTITY_SCHEMA_VERSION,
    ProjectIdentityAssessment,
    ProjectIdentityInput,
    ProjectIdentityStatus,
)

__all__ = [
    "PROJECT_IDENTITY_RULE_VERSION",
    "PROJECT_IDENTITY_SCHEMA_VERSION",
    "ProjectIdentityAssessment",
    "ProjectIdentityInput",
    "ProjectIdentityStatus",
    "assess_project_identity",
]
