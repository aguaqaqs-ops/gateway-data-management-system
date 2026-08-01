# Gateway Shared Kernel

Python reference implementation for Shared Canonical Encoding (Phase 1 WP1).

Canonical cases are ordinary read-only test material at
`vnext/fixtures/vectors/shared-kernel/canonical-encoding/v1/`.
The Python owner tests load the four JSONL files directly; no manifest or
candidate publication step is required.

```bash
uv run pytest
```
