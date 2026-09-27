"""Frozen architecture violations owned by ``tests/test_architecture.py``.

Seeded 2026-09-25 from HEAD ``499468f362`` (P5-5E-S3). These are the known deviations scheduled for
the centralized P5 repair round (after 5E-S3, before P5 exit; see P5 §2A.4, §2A.4.1, §2A.5). Rules:

- New violations fail. Fix them instead of adding entries; an entry may be added only with an
  explicit, reviewed justification in the same diff.
- Entries that no longer occur fail as stale. Delete them when the underlying issue is fixed, so
  this file only shrinks.
- ``python -m tests.support.import_rules`` (from ``vnext/backend``) prints the current state.

Group tags: ``A<n>`` = P5 §2A.4 known-issue row n; ``N-*`` = found in the 2026-09-25 assessment.
"""

from __future__ import annotations

IMPORT_RULE_BASELINE: frozenset[tuple[str, str, str]] = frozenset(
    {
        # A1: business ports / job handlers depend on Repository wire DTOs.
        ("layer", "gateway_backend.application.submission.ports", "gateway_repository_contracts"),
        ("layer", "gateway_backend.application.submit_jobs", "gateway_repository_contracts"),
        # A2: consumers import capability private modules.
        (
            "layer",
            "gateway_backend.http.orchestration.source_package_admission",
            "gateway_backend.capabilities.source_package_staging._archive",
        ),
        (
            "private",
            "gateway_backend.infrastructure.repository_read.http_arrow",
            "gateway_backend.capabilities.snapshot_materialization._digest",
        ),
        (
            "capability-surface",
            "gateway_backend.infrastructure.repository_read.http_arrow",
            "gateway_backend.capabilities.snapshot_materialization.scalar_encoding",
        ),
        # A5: foundation layer depends on Domain (nominal refs defined in the wrong owner).
        (
            "layer",
            "gateway_backend.artifacts.nominal_refs",
            "gateway_backend.domain.submission.models",
        ),
        # A6: unowned package-root modules and their consumers.
        ("unowned-root-module", "gateway_backend.repository_import_artifact", ""),
        # A7: contracts.py trampolines into its own execution modules.
        (
            "contracts-leaf",
            "gateway_backend.capabilities.composite_signal.contracts",
            "gateway_backend.capabilities.composite_signal.materialize",
        ),
        (
            "contracts-leaf",
            "gateway_backend.capabilities.snapshot_materialization.contracts",
            "gateway_backend.capabilities.snapshot_materialization.sql_declared_types",
        ),
        (
            "contracts-leaf",
            "gateway_backend.capabilities.table_rules.contracts",
            "gateway_backend.capabilities.table_rules.resolver",
        ),
        # A8: Application bypasses capability facades (package root / contracts).
        (
            "capability-surface",
            "gateway_backend.application.history.compare_jobs",
            "gateway_backend.capabilities.snapshot_materialization.artifact",
        ),
        (
            "capability-surface",
            "gateway_backend.application.history.compare_jobs",
            "gateway_backend.capabilities.snapshot_materialization.repository_ref",
        ),
        (
            "capability-surface",
            "gateway_backend.application.history.compare_jobs",
            "gateway_backend.capabilities.table_rules.registry",
        ),
        (
            "capability-surface",
            "gateway_backend.application.history.compare_jobs",
            "gateway_backend.capabilities.table_rules.resolver",
        ),
        (
            "capability-surface",
            "gateway_backend.application.preview_jobs",
            "gateway_backend.capabilities.snapshot_materialization.artifact",
        ),
        (
            "capability-surface",
            "gateway_backend.application.preview_jobs",
            "gateway_backend.capabilities.snapshot_materialization.materialize",
        ),
        (
            "capability-surface",
            "gateway_backend.application.preview_jobs",
            "gateway_backend.capabilities.snapshot_materialization.repository_ref",
        ),
        (
            "capability-surface",
            "gateway_backend.application.preview_jobs",
            "gateway_backend.capabilities.table_access.sql",
        ),
        (
            "capability-surface",
            "gateway_backend.application.submit_jobs",
            "gateway_backend.capabilities.snapshot_materialization.artifact",
        ),
        (
            "capability-surface",
            "gateway_backend.application.submit_jobs",
            "gateway_backend.capabilities.table_rules.registry",
        ),
        # N-http-composition: http.runtime acts as a second composition root.
        (
            "layer",
            "gateway_backend.bootstrap.composition",
            "gateway_backend.capabilities.snapshot_materialization.contracts",
        ),
        (
            "layer",
            "gateway_backend.bootstrap.composition",
            "gateway_backend.capabilities.table_rules.contracts",
        ),
        ("layer", "gateway_backend.bootstrap.composition", "gateway_backend.infrastructure.artifact_store"),
        ("layer", "gateway_backend.bootstrap.composition", "gateway_backend.infrastructure.control_db"),
        (
            "layer",
            "gateway_backend.bootstrap.composition",
            "gateway_backend.infrastructure.control_db.sqlite_mapping",
        ),
        ("layer", "gateway_backend.bootstrap.composition", "gateway_backend.infrastructure.repository_read"),
        (
            "layer",
            "gateway_backend.bootstrap.composition",
            "gateway_backend.infrastructure.repository_write",
        ),
        ("layer", "gateway_backend.bootstrap.composition", "gateway_backend.repository_import_artifact"),
        ("layer", "gateway_backend.bootstrap.composition", "gateway_backend.settings"),
        ("layer", "gateway_backend.bootstrap.composition", "gateway_repository_client"),
        ("layer", "gateway_backend.bootstrap.composition", "gateway_repository_client.errors"),
        ("layer", "gateway_backend.bootstrap.composition", "httpx"),
        (
            "private",
            "gateway_backend.bootstrap.composition",
            "gateway_backend.application.submit_jobs:read_write_factory",
        ),
        # N-http-bypass: HTTP reaches infrastructure, settings, capabilities or wire DTOs directly.
        (
            "layer",
            "gateway_backend.http.dependencies",
            "gateway_backend.infrastructure.control_db.database",
        ),
        (
            "layer",
            "gateway_backend.infrastructure.control_db.history_reader",
            "gateway_backend.infrastructure.control_db.database",
        ),
        (
            "layer",
            "gateway_backend.infrastructure.control_db.history_reader",
            "gateway_backend.infrastructure.control_db.sqlite_history",
        ),
        (
            "layer",
            "gateway_backend.http.orchestration.multipart_stream",
            "gateway_backend.settings",
        ),
        (
            "layer",
            "gateway_backend.http.orchestration.multipart_upload",
            "gateway_backend.settings",
        ),
        (
            "layer",
            "gateway_backend.http.orchestration.preview_acceptance",
            "gateway_backend.capabilities.table_rules.contracts",
        ),
        (
            "layer",
            "gateway_backend.http.orchestration.source_package_admission",
            "gateway_backend.capabilities.source_package_staging.contracts",
        ),
        ("layer", "gateway_backend.http.schemas.history", "gateway_repository_contracts.types"),
        # N-infra-usecase: adapters depend on Application use-case modules instead of ports.
        (
            "layer",
            "gateway_backend.infrastructure.control_db.sqlite_history_compare",
            "gateway_backend.application.history.compare_bindings",
        ),
        (
            "layer",
            "gateway_backend.infrastructure.repository_write.abort_evidence",
            "gateway_backend.application.submission.abort",
        ),
        # N-operations-private: Operation contract validators are consumed as private symbols.
        (
            "private",
            "gateway_backend.application.checkpoints",
            "gateway_backend.operations.contracts:_validate_json_structure",
        ),
        (
            "private",
            "gateway_backend.application.payloads",
            "gateway_backend.operations.contracts:_validate_canonical_job_payload_bytes,"
            "_validate_json_structure",
        ),
        (
            "private",
            "gateway_backend.bootstrap.operation_worker",
            "gateway_backend.operations.contracts:_validate_opaque_id",
        ),
        (
            "private",
            "gateway_backend.http.schemas.constraints",
            "gateway_backend.operations.contracts:_IJSON_MAX_SAFE_INTEGER,"
            "_MAX_DIAGNOSTIC_MESSAGE_BYTES,_MAX_OPAQUE_ID_BYTES",
        ),
    }
)

RUNTIME_CYCLE_BASELINE: tuple[frozenset[str], ...] = (
    # A3: transactions call back into the submit job module (function-local imports).
    frozenset(
        {
            "gateway_backend.application.submission.abort_transaction",
            "gateway_backend.application.submission.finalize_transaction",
            "gateway_backend.application.submit_jobs",
        }
    ),
    # A7: contracts.py lazily delegates to its own implementation.
    frozenset(
        {
            "gateway_backend.capabilities.composite_signal._ast",
            "gateway_backend.capabilities.composite_signal._bind",
            "gateway_backend.capabilities.composite_signal._digest",
            "gateway_backend.capabilities.composite_signal.contracts",
            "gateway_backend.capabilities.composite_signal.materialize",
        }
    ),
    frozenset(
        {
            "gateway_backend.capabilities.table_rules.contracts",
            "gateway_backend.capabilities.table_rules.registry",
            "gateway_backend.capabilities.table_rules.resolver",
        }
    ),
    # N-cycles: intra-owner cycles.
    frozenset(
        {"gateway_backend.application.job_definitions", "gateway_backend.application.payloads"}
    ),
    frozenset(
        {
            "gateway_backend.capabilities.comparison.ordered",
            "gateway_backend.capabilities.comparison.standard",
        }
    ),
    frozenset(
        {"gateway_backend.domain.submission.models", "gateway_backend.domain.submission.policies"}
    ),
    frozenset({"gateway_backend.http.auth", "gateway_backend.http.dependencies"}),
    frozenset(
        {
            "gateway_backend.infrastructure.control_db.database",
            "gateway_backend.infrastructure.control_db.sqlite_baseline",
            "gateway_backend.infrastructure.control_db.sqlite_mapping",
        }
    ),
)

# A9 / N-dead: modules that no production entrypoint reaches. Either wire them to a real consumer,
# record an explicit deferral in the owning design, or delete them.
UNREACHABLE_MODULE_BASELINE: frozenset[str] = frozenset(
    {
        "gateway_backend.capabilities.canonical_row_hash.canonical_row_hash_ipc",
        "gateway_backend.capabilities.canonical_row_hash.compute",
        "gateway_backend.capabilities.canonical_row_hash.contracts",
        "gateway_backend.capabilities.external_target_sync._ledger_digest",
        "gateway_backend.capabilities.external_target_sync._reference_executor",
        "gateway_backend.capabilities.external_target_sync.contracts",
        "gateway_backend.capabilities.snapshot_materialization._catalog",
        "gateway_backend.capabilities.snapshot_materialization.compose",
        "gateway_backend.capabilities.table_access._xml_parser",
        "gateway_backend.capabilities.table_access.xml",
    }
)
