# Phase 1 Environment Execution Ledger

状态：Partially verified

执行日期：2026-07-15

## Baseline

| Component | Required | Actual | Status |
| --- | --- | --- | --- |
| Platform | Linux x86_64 glibc | Linux x86_64 (WSL2) | verified |
| uv | 0.11.28 | 0.11.28 | verified |
| Python | 3.14.6 | 3.14.6 | verified |
| Rust | 1.97.0 | 1.97.0 | verified |
| Docker / Compose | 29.6.1 / 5.3.1 | 29.6.1 / 5.3.1 | verified |
| Dolt | 2.1.11 | 2.1.11 | verified |

## Commands and evidence

- Legacy source was moved with `git mv backend_vnext legacy/backend_vnext`.
- Legacy execution now requires `PYTHONPATH=$PWD/legacy` and a separately frozen legacy environment.
- The selected legacy test command and golden/digest evidence were not available in this repository checkout; this is recorded as a Phase 0 follow-up, not repaired by changing legacy behavior.
- New projects are independent uv projects. Their committed lockfiles are generated from the exact dependency inputs in their `pyproject.toml` files.
- Rust workspace `Cargo.lock` resolves PyO3 0.29.0, pyo3-arrow 0.19.0, and Arrow 59.1.0.
- Backend release wheel built and imported on CPython 3.14.6. The native wheel is also a fixed local build dependency of the backend, so `uv sync --frozen` retains it. The Arrow round-trip preserves `NULL` and produces a SHA-256 artifact reference.
- Passed locally: backend `uv sync --frozen`, `ruff check`, `ruff format --check`, `mypy src tests`, `pytest -q`; Rust `fmt --check`, strict clippy, and `cargo test --locked`; Repository Service `uv sync --frozen`, ruff, mypy, and pytest.
- `docker compose config -q` passes. The Docker daemon is running, but two attempts to pull the pinned official Rust and Python images failed because `registry-1.docker.io:443` refused TCP connections. Consequently image build, container smoke, and manifest-digest verification remain network-blocked rather than untested by omission.

## Pending host-level gates

- Install Rust 1.97.0 with rustfmt and clippy, then run the Rust and native-wheel gates.
- Restore Docker Hub registry connectivity, then run image, Compose, and Repository Service gates.
- Record immutable manifest digests after registry access is restored. No floating image tags are used in repository files.
