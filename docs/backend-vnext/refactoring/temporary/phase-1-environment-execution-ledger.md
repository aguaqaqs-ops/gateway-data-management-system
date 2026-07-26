# Phase 1 Environment Execution Ledger

状态：**Verified / Resolved**（Phase 1 closed 2026-07-27）

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

## Historical pending host-level gates（已于 2026-07-27 关闭）

- Rust 1.97.0、rustfmt、clippy 与 native-wheel gates：**RESOLVED / PASSED**。
- Docker daemon proxy 与 Docker Hub connectivity：**RESOLVED**；image 与 Compose
  gate 已在 exit source exact commit 通过。
- Immutable container identity：**RECORDED**；见本文件末尾最终收口记录。

## Historical WP5 R5 update (2026-07-25)

- Added `vnext/deploy/phase-1-image-pins.env` with `rust:1.97.0-bookworm` and `python:3.14.6-slim-bookworm` **index digests** (tags not used in builds).
- `bash vnext/scripts/gate.sh correctness` — **PASS** on pre-commit dirty snapshot (`/tmp/wp5-r5-correctness.log`).
- `bash vnext/scripts/gate.sh native` — **PASS** on same snapshot (`/tmp/wp5-r5-native.log`).
- `bash vnext/scripts/gate.sh phase-exit-container` — **fail-closed** on dirty worktree (exit 1); with `PHASE_EXIT_CONTAINER_ALLOW_DIRTY=1`, registry pull → **BLOCKED** (exit 3, `BLOCKED:` in stderr; `/tmp/wp5-r5-container-allow-dirty.log`). **Not recorded as PASS.**
- Formal `PHASE-EXIT-CONTAINER` health/native/compose runtime smoke and immutable image identity capture remain **BLOCKED** until registry connectivity and a clean exact-commit rerun.
- Evidence: `docs/backend-vnext/refactoring/temporary/phase-1/wp5-r5-phase1-exit-evidence.md` (**pre-commit candidate**).

## Historical WP5 R5 audit remediation (2026-07-25)

- Host wheel 为唯一 release 来源：`backend/.phase-exit-build/` → Dockerfile `sha256sum -c`；`compose.phase-exit.yaml` 使用预构建 image（`--no-build`）。
- `CONTAINER-WHEEL-IDENTITY` / `CONTAINER-COMPOSE-IDENTITY` 模型 **FIXED**；registry 实证仍 **BLOCKED**。
- `pytest test_phase_exit_container_gate.py`：**20 passed**；`test_container_native_smoke.py`：**3 passed**（**历史快照 2026-07-25**；现行计数见 `wp5-r5-phase1-exit-evidence.md` §6，约 gate 42 / smoke 10）。

## Historical WP5 R5 consolidated review fix (2026-07-26)

- 外部审核合并项：native smoke oracle、cleanup/唯一 tag、toolchain 断言、identity 落盘、pull/curl 超时、`compose.yaml` 默认 image-only。
- Identity artifact（gitignore）：`docs/backend-vnext/refactoring/temporary/phase-1/artifacts/phase-exit-container-identity-<sha256>.json`（content-addressed；可选 `phase-exit-container-identity-latest.json` 非权威指针）
- Patch SHA：见 `wp5-r5-phase1-exit-evidence.md` §10。
- 当时 `CONTAINER-REGISTRY` 仍 **BLOCKED**；这是 2026-07-26 的历史快照，
  已由下述最终 exact-commit 执行关闭。

## Phase 1 final exact-commit closure (2026-07-27)

| 项 | 最终值 |
| --- | --- |
| Exit source commit | `7702d2127712193a8a88e66ba614dc073922ac15` |
| R4 base | `b747590ac6ffdfe0e00b320363ce429e663e358e` |
| Source patch SHA | `457eafb996cb8a6bcb5d0c10ea7668c1175d3716f96aa72a67b8d0aad88fd1b3` |
| `PR-CORRECTNESS` | **PASS** — shared kernel 139；repository 5；conformance 654 passed / 5 skipped；backend 256 passed / 3 skipped；Rust/fmt/clippy/release wheel smoke/mypy/ruff 全通过 |
| `PR-NATIVE` | **PASS** — authoritative Rust probes 8；facade 18；artifact full-chain 57；R4 conformance matrix 3 |
| `PHASE-EXIT-CONTAINER` | **PASS** — offline image build、direct native smoke、Compose health/native smoke |
| Blocking register | **EMPTY** |

Immutable identity：
`phase-exit-container-identity-95b3d7633caa7b536960552ba72e29b18bbe0fb6434d97b51b9cb40b9dde5f58.json`
（content-addressed、gitignored）。权威字段包括：

- image/config ID：
  `sha256:9f58f4ed48e2b6d8522201977d2df4f365bc13b674ddf7fdd42c6a95445b9df2`
- release wheel SHA-256：
  `18551041541e1d8fcf0d49a19c1cbd975298e9b2e10f2d6e67ec32592a55235c`
- native extension SHA-256：
  `5600abc550118a364aeb95f36126cd0880d9f955a10a8e812231aff24c751071`
- uv 0.11.28 / pip 25.3 / Python 3.14.6 / Rust 1.97.0；六份 lock
  SHA 与 exit source evidence 一致。

Docker/Compose 资源、Phase 1 临时 build staging、容器、网络和卷均已清理。
Phase 1 的最终裁决见
[`phase-1/phase-1-closure-signoff.md`](phase-1/phase-1-closure-signoff.md)。
