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
    {}
)

RUNTIME_CYCLE_BASELINE: tuple[frozenset[str], ...] = ()

UNREACHABLE_MODULE_BASELINE: frozenset[str] = frozenset(
    {
        # A6 / DC26 Phase 6 defer; owner, rationale, and reopen condition: design §9 deferral register.
        "gateway_backend.capabilities.canonical_row_hash.canonical_row_hash_ipc",
        "gateway_backend.capabilities.canonical_row_hash.compute",
        "gateway_backend.capabilities.canonical_row_hash.contracts",
        # A9 external-target defer; owner, rationale, and reopen condition: design §9 deferral register.
        "gateway_backend.capabilities.external_target_sync._ledger_digest",
        "gateway_backend.capabilities.external_target_sync._reference_executor",
        "gateway_backend.capabilities.external_target_sync.contracts",
    }
)
