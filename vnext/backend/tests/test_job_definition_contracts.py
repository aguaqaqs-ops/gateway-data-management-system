"""JobDefinition descriptor and public export boundary tests."""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
from typing import Any

import pytest

import gateway_backend.application as application
import gateway_backend.operations as operations
from gateway_backend.application import (
    JobDefinition,
    JobDefinitionLookupError,
    NormalPublicationCapability,
    RecoveryCapability,
)
from gateway_backend.operations.contracts import JobStepKey

pytestmark = pytest.mark.unit

BACKEND_SRC = Path(__file__).parents[1] / "src"
APPLICATION_ROOT = BACKEND_SRC / "gateway_backend" / "application"
OPERATIONS_ROOT = BACKEND_SRC / "gateway_backend" / "operations"

EXPECTED_PUBLIC_EXPORTS = frozenset(
    {
        "JobDefinition",
        "JobDefinitionLookupError",
        "JobDefinitionRegistry",
        "NormalPublicationCapability",
        "RecoveryCapability",
        "RecoveryDecision",
        "RecoveryDecisionDisposition",
        "RecoveryOutcome",
        "RecoveryOutcomeDisposition",
        "RecoveryPort",
        "build_worker_registry",
    }
)

EXPECTED_PUBLICATION_CAPABILITIES = frozenset(
    {
        "SINGLE_SUCCESSOR",
        "TERMINAL",
    }
)

EXPECTED_RECOVERY_CAPABILITIES = frozenset(
    {
        "PURE_RECOMPUTE",
        "EXTERNAL_EFFECT",
        "NON_RETRYABLE",
    }
)

SAMPLE_KEY = JobStepKey(job_kind="import.package", step_name="validate")
SAMPLE_VERSION = "backend-vnext/synthetic/pure-compute/v1"
SAMPLE_DECODER = "backend-vnext/synthetic/pure-compute/decoder/v1"
SAMPLE_HANDLER = "backend-vnext/synthetic/pure-compute/handler/v1"


def _sample_definition(
    *,
    key: JobStepKey = SAMPLE_KEY,
    supported_payload_versions: frozenset[str] = frozenset({SAMPLE_VERSION}),
    decoder_identity: str = SAMPLE_DECODER,
    handler_identity: str = SAMPLE_HANDLER,
    publication_capability: NormalPublicationCapability = NormalPublicationCapability.TERMINAL,
    recovery_capability: RecoveryCapability = RecoveryCapability.PURE_RECOMPUTE,
) -> JobDefinition:
    return JobDefinition(
        key=key,
        supported_payload_versions=supported_payload_versions,
        decoder_identity=decoder_identity,
        handler_identity=handler_identity,
        publication_capability=publication_capability,
        recovery_capability=recovery_capability,
    )


MALFORMED_DEFINITION_FIELDS: tuple[tuple[dict[str, Any], str], ...] = (
    (
        {
            "key": ("import.package", "validate"),
            "supported_payload_versions": frozenset({SAMPLE_VERSION}),
            "decoder_identity": SAMPLE_DECODER,
            "handler_identity": SAMPLE_HANDLER,
            "publication_capability": NormalPublicationCapability.TERMINAL,
            "recovery_capability": RecoveryCapability.PURE_RECOMPUTE,
        },
        "key must be JobStepKey",
    ),
    (
        {
            "key": SAMPLE_KEY,
            "supported_payload_versions": {SAMPLE_VERSION},
            "decoder_identity": SAMPLE_DECODER,
            "handler_identity": SAMPLE_HANDLER,
            "publication_capability": NormalPublicationCapability.TERMINAL,
            "recovery_capability": RecoveryCapability.PURE_RECOMPUTE,
        },
        "supported_payload_versions must be frozenset",
    ),
    (
        {
            "key": SAMPLE_KEY,
            "supported_payload_versions": frozenset(),
            "decoder_identity": SAMPLE_DECODER,
            "handler_identity": SAMPLE_HANDLER,
            "publication_capability": NormalPublicationCapability.TERMINAL,
            "recovery_capability": RecoveryCapability.PURE_RECOMPUTE,
        },
        "supported_payload_versions must not be empty",
    ),
    (
        {
            "key": SAMPLE_KEY,
            "supported_payload_versions": frozenset({""}),
            "decoder_identity": SAMPLE_DECODER,
            "handler_identity": SAMPLE_HANDLER,
            "publication_capability": NormalPublicationCapability.TERMINAL,
            "recovery_capability": RecoveryCapability.PURE_RECOMPUTE,
        },
        "supported_payload_versions must be bounded ASCII printable",
    ),
    (
        {
            "key": SAMPLE_KEY,
            "supported_payload_versions": frozenset({SAMPLE_VERSION}),
            "decoder_identity": "bad\nidentity",
            "handler_identity": SAMPLE_HANDLER,
            "publication_capability": NormalPublicationCapability.TERMINAL,
            "recovery_capability": RecoveryCapability.PURE_RECOMPUTE,
        },
        "decoder_identity must be bounded ASCII printable",
    ),
    (
        {
            "key": SAMPLE_KEY,
            "supported_payload_versions": frozenset({SAMPLE_VERSION}),
            "decoder_identity": SAMPLE_DECODER,
            "handler_identity": "bad\nidentity",
            "publication_capability": NormalPublicationCapability.TERMINAL,
            "recovery_capability": RecoveryCapability.PURE_RECOMPUTE,
        },
        "handler_identity must be bounded ASCII printable",
    ),
    (
        {
            "key": SAMPLE_KEY,
            "supported_payload_versions": frozenset({SAMPLE_VERSION}),
            "decoder_identity": SAMPLE_DECODER,
            "handler_identity": SAMPLE_HANDLER,
            "publication_capability": "TERMINAL",
            "recovery_capability": RecoveryCapability.PURE_RECOMPUTE,
        },
        "publication_capability must be NormalPublicationCapability",
    ),
    (
        {
            "key": SAMPLE_KEY,
            "supported_payload_versions": frozenset({SAMPLE_VERSION}),
            "decoder_identity": SAMPLE_DECODER,
            "handler_identity": SAMPLE_HANDLER,
            "publication_capability": NormalPublicationCapability.TERMINAL,
            "recovery_capability": "PURE_RECOMPUTE",
        },
        "recovery_capability must be RecoveryCapability",
    ),
)


def test_application_public_exports_match_contract_surface() -> None:
    assert frozenset(application.__all__) == EXPECTED_PUBLIC_EXPORTS
    for symbol in EXPECTED_PUBLIC_EXPORTS:
        assert hasattr(application, symbol)


def test_normal_publication_capability_values_exact() -> None:
    assert {item.value for item in NormalPublicationCapability} == EXPECTED_PUBLICATION_CAPABILITIES


def test_recovery_capability_values_exact() -> None:
    assert {item.value for item in RecoveryCapability} == EXPECTED_RECOVERY_CAPABILITIES


def test_job_definition_is_frozen_bounded_descriptor() -> None:
    definition = _sample_definition()
    assert dataclasses.is_dataclass(definition)
    assert definition.__slots__ == (
        "key",
        "supported_payload_versions",
        "decoder_identity",
        "handler_identity",
        "publication_capability",
        "recovery_capability",
    )
    assert definition.key == SAMPLE_KEY
    assert definition.supported_payload_versions == frozenset({SAMPLE_VERSION})
    assert definition.decoder_identity == SAMPLE_DECODER
    assert definition.handler_identity == SAMPLE_HANDLER
    assert definition.publication_capability is NormalPublicationCapability.TERMINAL
    assert definition.recovery_capability is RecoveryCapability.PURE_RECOMPUTE


def test_job_definition_lookup_error_carries_bounded_context() -> None:
    error = JobDefinitionLookupError(
        "registry has no JobDefinition for the JobStepKey",
        key=SAMPLE_KEY,
        job_contract_version=SAMPLE_VERSION,
    )
    assert isinstance(error, ValueError)
    assert error.key == SAMPLE_KEY
    assert error.job_contract_version == SAMPLE_VERSION


def test_job_definition_registry_exposes_decoder_identities() -> None:
    from gateway_backend.application.job_definitions import JobDefinitionRegistry

    definition = _sample_definition()
    registry = JobDefinitionRegistry.build((definition,))
    assert registry.decoder_identities() == frozenset({SAMPLE_DECODER})


@pytest.mark.parametrize(("fields", "message"), MALFORMED_DEFINITION_FIELDS)
def test_job_definition_rejects_malformed_fields(fields: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        JobDefinition(**fields)


def test_operations_package_does_not_import_application() -> None:
    for source in sorted(OPERATIONS_ROOT.rglob("*.py")):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("gateway_backend.application"), source
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                assert not node.module.startswith("gateway_backend.application"), source


def test_operations_root_exports_remain_unchanged() -> None:
    assert "JobDefinition" not in operations.__all__
    assert "application" not in dir(operations)
