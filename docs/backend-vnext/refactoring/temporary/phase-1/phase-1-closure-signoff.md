# Backend vNext Phase 1 Closure Sign-off

状态：**COMPLETED / ACCEPTED**

签署日期：2026-07-27

本文件是 Phase 1 的最终收口记录。实现和运行身份以已经完成三门禁的
exact source commit 为准；本文件及同批 ledger/evidence 状态修订属于其后的
administrative closure commit，不改变或冒充已验证的 source/image identity。

## 1. Final identity

| 项 | 值 |
| --- | --- |
| Phase 1 exit source commit | `7702d2127712193a8a88e66ba614dc073922ac15` |
| R4 base | `b747590ac6ffdfe0e00b320363ce429e663e358e` |
| Exit-source R5 Patch SHA | `457eafb996cb8a6bcb5d0c10ea7668c1175d3716f96aa72a67b8d0aad88fd1b3` |
| Branch | `main` |
| Exit-source worktree | clean |
| Toolchains | uv 0.11.28；pip 25.3；Python 3.14.6；Rust 1.97.0 |

`7702d2127712193a8a88e66ba614dc073922ac15` 是唯一的 Phase 1
runtime/source exit identity。后续仅文档收口的 commit 不要求重建容器，也不把
新的文档 commit SHA 写入既有镜像 label。

## 2. Exact-commit gates

| Gate | 结果 | 关键证据 |
| --- | --- | --- |
| `PR-CORRECTNESS` | **PASS** | shared kernel 139；repository 5；conformance 654 passed / 5 skipped；backend 256 passed / 3 skipped；Rust/fmt/clippy/release wheel smoke/mypy/ruff 全通过 |
| `PR-NATIVE` | **PASS** | authoritative Rust probes 8；facade 18；artifact full-chain 57；WP5 R4 conformance matrix 3；wheel identity 前后不变 |
| `PHASE-EXIT-CONTAINER` | **PASS** | pinned/offline image build；direct native smoke；Compose healthy；Compose native smoke；cleanup 完成 |

上表三项均针对同一 source commit、toolchain 与六份 lock identity 执行。门禁
没有使用 dirty override、success injection、skip、xfail、`UNSUPPORTED` 或
网络故障豁免。

## 3. Immutable container evidence

权威 content-addressed artifact（按策略 gitignored）：

`docs/backend-vnext/refactoring/temporary/phase-1/artifacts/phase-exit-container-identity-95b3d7633caa7b536960552ba72e29b18bbe0fb6434d97b51b9cb40b9dde5f58.json`

| 字段 | 值 |
| --- | --- |
| `gate_status` | `passed` |
| `source_revision` / `expected_head` | `7702d2127712193a8a88e66ba614dc073922ac15` |
| image/config ID | `sha256:9f58f4ed48e2b6d8522201977d2df4f365bc13b674ddf7fdd42c6a95445b9df2` |
| release wheel SHA-256 | `18551041541e1d8fcf0d49a19c1cbd975298e9b2e10f2d6e67ec32592a55235c` |
| native extension SHA-256 | `5600abc550118a364aeb95f36126cd0880d9f955a10a8e812231aff24c751071` |
| network deadline | 3600 seconds |

Artifact 中的 Python base digest、uv/pip/Python/Rust versions 与六份 lock
SHA-256 已独立复核，均与 exit source 一致。

## 4. Required matrix and contract closure

- 正式 scenario root 仍恰好一条：
  `data.canonical-row-hashes.mixed-scalars`。
- 四个 required cells 均唯一执行并 `PASSED`：
  `reference/null`、`integration/null`、
  `provider-matrix/python-reference`、
  `provider-matrix/rust-native`。
- Required lanes 无 missing、skip、xfail、`UNSUPPORTED` 或 retry 覆盖。
- Python/Rust 独立 vector implementations 与 Repository consumer 继续消费同一
  normative root，coverage set 一致。
- Integration 路径实际经过 facade → PyO3/Rust → IPC ArtifactRef → fresh
  reopen，并重验 raw/semantic identity。
- Harness 不读取 golden，runner 仍唯一负责 comparison/result；Repository
  仍是 vector consumer，不是 row-hash provider。
- 原 doubling/`to_pylist()` bootstrap demo 不属于 public/formal path。

## 5. Phase 1 exit conditions

| # | Formal exit condition | Final |
| ---: | --- | --- |
| 1 | Correctness/native at exit commit | **SATISFIED** |
| 2 | Container at same commit/toolchain/locks + immutable evidence | **SATISFIED** |
| 3 | Required matrix all passed | **SATISFIED** |
| 4 | Python/Rust vectors + Repository same root | **SATISFIED** |
| 5 | Artifact fresh reopen + raw/semantic verification | **SATISFIED** |
| 6 | `to_pylist()` demo not formal/public | **SATISFIED** |
| 7 | Blocking register empty | **SATISFIED** |
| 8 | Formal ownership complete；temporary discussions Resolved | **SATISFIED** |
| 9 | Rust/wheel/container cross-stage policy | **SATISFIED** |

## 6. Final blocking register

**EMPTY.**

此前的 `CONTAINER-REGISTRY`、`R5-PRECOMMIT`、
`WP5-R3-EVIDENCE-HOLD` 与 `WP5-R4-EVIDENCE-HOLD` 均已关闭。历史网络
阻塞仍保留在 ledger/R5 evidence 的过程记录中，不再是当前阻塞项。

Phase 1 明确 non-goals（例如 process-crash 正式 scenario、Phase 2
Repository transport/Dolt、numeric benchmark）不是 deferred blockers，不随
Phase 1 closure 自动授权实现。

## 7. Cleanup and transition

- Docker 容器、Phase 1 images、volumes、networks、build staging 与临时目录均已
  清理；未发现 source-tree `.so` 残留。
- Ordinary CI 仍无 auto-bless；未 push image、未发布 registry artifact、未部署。
- Phase 1 至此可以结束。后续工作可以进入 **Phase 2 完整设计**，但 Phase 2
  scope、owner、Dolt/Repository transport contract 与验收矩阵须独立评审，
  不得回写或扩展本 sign-off 的 Phase 1 identity。
