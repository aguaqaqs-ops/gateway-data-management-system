"""Frozen architecture violations owned by ``tests/test_architecture.py``.

P5 S1 exit baseline (``p5-arch-closure-execution-plan.md`` §2 S1; design §9 W6). Rules:

- New violations fail. Fix them instead of adding entries; an entry may be added only with an
  explicit, reviewed justification in the same diff.
- Entries that no longer occur fail as stale. Delete them when the underlying issue is fixed, so
  this file only shrinks.
- ``python -m tests.support.import_rules`` (from ``vnext/backend``) prints the current state.

Group tags: ``A<n>`` = design §9 W6 row; unreachable comments name the closing stage.
"""

from __future__ import annotations

IMPORT_RULE_BASELINE: frozenset[tuple[str, str, str]] = frozenset(
    {
        # A2 (close S2b): Arrow read adapter still reaches private digest + scalar_encoding.
        (
            "capability-surface",
            "gateway_backend.infrastructure.repository_read.http_arrow",
            "gateway_backend.capabilities.snapshot_materialization.scalar_encoding",
        ),
        (
            "private",
            "gateway_backend.infrastructure.repository_read.http_arrow",
            "gateway_backend.capabilities.snapshot_materialization._digest",
        ),
        # A6 (close S2b): package-root import artifact adapter pending infrastructure migration.
        ("unowned-root-module", "gateway_backend.repository_import_artifact", ""),
        # F7: workspace contracts re-export upload limits from settings (single source).
        ("layer", "gateway_backend.application.workspace.contracts", "gateway_backend.settings"),
    }
)

RUNTIME_CYCLE_BASELINE: tuple[frozenset[str], ...] = (
    # F9: strict payload decode (`type(...) is JobDefinition`) with lazy job_definitions import.
    frozenset(
        {"gateway_backend.application.job_definitions", "gateway_backend.application.payloads"}
    ),
    # F9: default internal bearer uses auth.FailClosedInternalBearerPort via lazy factory.
    frozenset({"gateway_backend.http.auth", "gateway_backend.http.dependencies"}),
    # F9: baseline head read uses read_only ControlDbUnitOfWork (busy mapping aligned with UoW).
    frozenset(
        {
            "gateway_backend.infrastructure.control_db.database",
            "gateway_backend.infrastructure.control_db.sqlite_baseline",
            "gateway_backend.infrastructure.control_db.sqlite_provisioned_scope",
        }
    ),
)

UNREACHABLE_MODULE_BASELINE: frozenset[str] = frozenset(
    {
        # A6 / Phase 6 (DC26 defer): capability shell migrated; production consumer deferred.
        "gateway_backend.capabilities.canonical_row_hash.canonical_row_hash_ipc",
        "gateway_backend.capabilities.canonical_row_hash.compute",
        "gateway_backend.capabilities.canonical_row_hash.contracts",
        # A9 (external target defer, design §9): no production external-target journey yet.
        "gateway_backend.capabilities.external_target_sync._ledger_digest",
        "gateway_backend.capabilities.external_target_sync._reference_executor",
        "gateway_backend.capabilities.external_target_sync.contracts",
        # S3: business snapshot compose + composite catalog; XML parser until logics.xml path.
        "gateway_backend.capabilities.snapshot_materialization._catalog",
        "gateway_backend.capabilities.snapshot_materialization.compose",
        "gateway_backend.capabilities.table_access._xml_parser",
        "gateway_backend.capabilities.table_access.xml",
    }
)
