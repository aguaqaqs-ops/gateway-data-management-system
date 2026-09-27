"""Frozen architecture violations owned by ``tests/test_architecture.py``.

P5 S1 exit baseline (``p5-arch-closure-execution-plan.md`` §2 S1). Regenerate with
``python -m tests.support.import_rules`` from ``vnext/backend`` when intentionally
changing the allowed deviation set.
"""

from __future__ import annotations

IMPORT_RULE_BASELINE: frozenset[tuple[str, str, str]] = frozenset(
    {
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
        ("unowned-root-module", "gateway_backend.repository_import_artifact", ""),
    }
)

RUNTIME_CYCLE_BASELINE: tuple[frozenset[str], ...] = ()

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
