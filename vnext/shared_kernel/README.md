# Gateway Shared Kernel

Python reference implementation for Shared Canonical Encoding (Phase 1 WP1).

Normative vectors are published at
`vnext/fixtures/vectors/shared-kernel/canonical-encoding/v1/` (WP2 R6).
Candidate generation remains out-of-tree and must not write the fixed
normative root.

## Test-only candidate tooling

Not part of the production import surface (`gateway_shared_kernel` root).

```bash
# Write a candidate vector set into a new empty directory
uv run python -m gateway_shared_kernel.testing generate /tmp/canonical-candidate

# Re-validate (schema, closure digests, and Python reference dispatch)
uv run python -m gateway_shared_kernel.testing validate /tmp/canonical-candidate
```

Safety: refuses the fixed normative vector root, symlinks, and non-empty
targets. Output includes `CANDIDATE_PENDING_WP2_CONFIRMATION`.
