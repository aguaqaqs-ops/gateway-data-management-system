# WP5 R5 — Phase 1 Exit Evidence

状态：**PASSED / ACCEPTED**（clean exact-commit three-gate closure）

日期：2026-07-27

Gate：`PR-CORRECTNESS` + `PR-NATIVE` + `PHASE-EXIT-CONTAINER`

本文件保留 R5 从 pre-commit/network-blocked candidate 到最终 exact-commit
通过的结论。最终 Phase 1 裁决见
[`phase-1-closure-signoff.md`](phase-1-closure-signoff.md)。

## 1. Scope / non-goals

| 项 | 声明 |
| --- | --- |
| 本轮范围 | correctness/native 聚合；required matrix 回归；pinned/offline container exit gate；wheel/image/Compose identity；ledger 与 blocking register 收口 |
| 非目标 | 镜像 push/registry 发布；第二个正式 scenario；process-crash 正式业务 scenario；numeric 性能声明；Phase 2 Repository/Dolt；自动 bless |

## 2. Authority

- `implementation-stages.md` §4 Phase 1 exit / gate classes
- `phase-1-implementation-design-and-delivery-plan.md`
- `fixture-oracle-and-conformance.md`
- `canonical-row-hash-compute-boundary.md`
- `shared-canonical-encoding.md`
- `rust-safety-and-performance-policy.md`
- `wp3-wp5-checkout-plan.md`
- WP3 R5、WP4 R4、WP5 R1–R4 accepted evidence

## 3. Exact source identity

| 项 | 值 |
| --- | --- |
| R4 accepted commit | `b747590ac6ffdfe0e00b320363ce429e663e358e` |
| R5 / Phase 1 exit source commit | `7702d2127712193a8a88e66ba614dc073922ac15` |
| Branch | `main` |
| R4 ancestor check | **PASS** |
| Exit gate worktree | **clean** |
| Exit-source Patch SHA | `457eafb996cb8a6bcb5d0c10ea7668c1175d3716f96aa72a67b8d0aad88fd1b3` |

Phase 1 的 runtime/source identity 固定为 `7702d2127712193a8a88e66ba614dc073922ac15`。
其后的 ledger/evidence/sign-off 修改是 documentation-only administrative closure，
不重写已通过 gate 的 image revision。

## 4. Delivered closure

- `vnext/scripts/gate.sh` 提供唯一 `phase-exit-container` 子命令并绑定
  `EXPECTED_HEAD`。
- Container gate 对 clean revision、toolchain、六份 locks、base digest、
  release wheel、native extension、image label/ID、health、native smoke、
  Compose 与 cleanup fail closed。
- Dockerfile 消费 host `PR-NATIVE` 同源 release wheel；依赖由 frozen lock
  wheelhouse 离线安装，runtime 不使用 editable/source-tree extension。
- `compose.phase-exit.yaml` 运行预构建 exact image；默认 Compose 为
  image-only，legacy build 明确隔离。
- Identity 仅在 body 与 cleanup 均成功后原子、content-addressed 落盘。
- Formal scenario、golden、canonical vectors/bytes 与 required profile 语义未被
  R5 越界改变。

## 5. Toolchain / locks / pins

| 组件 | 版本 |
| --- | --- |
| uv | 0.11.28 |
| pip | 25.3 |
| Python | 3.14.6 |
| Rust | 1.97.0 |

| Lock | SHA-256 |
| --- | --- |
| `vnext/rust/Cargo.lock` | `95cffeb249cec9bbdb96f6978bf8b4755819992a3f0f5953af7a7a82b8e3a544` |
| `vnext/backend/uv.lock` | `681a3f4e4b0ff0b4890761736f8dd35e8a84afaebc8cf2310ccf3221adde680c` |
| `vnext/backend/uv.container.lock` | `bcba4053815b214bba6696944e09bfb073f9d9928818c78008143315e3305995` |
| `vnext/shared_kernel/uv.lock` | `fe79bf4df1231bf308ad19614a0b5690ef1e5489a0b99d8194e8f363e36e4f74` |
| `vnext/conformance/uv.lock` | `36091eadcfd8fde94983d4d843f095494f493ce75da02049415b574c468575d4` |
| `vnext/repository_service/uv.lock` | `e52d6b8c9720ed2eecebd0ba3ef3bdeca4435a525422b874f299abeba30f17f1` |

Base images are tag-and-digest pinned in
`vnext/deploy/phase-1-image-pins.env`:

- Rust:
  `sha256:8fa55b2f3ddf97471ab6a767bfa3f37e6bad0986ba823e75fea57e2a2a5c3073`
- Python:
  `sha256:4ff4b92a68355dbdb52584ab3391dff8d371a61d4e063468bfd0130e3189c6d9`

Gate 前后上述 locks 均未变化。

## 6. Exact-commit gate results

| Gate | Exit | 结果 |
| --- | ---: | --- |
| `bash vnext/scripts/gate.sh correctness` | 0 | **PASS** — shared kernel 139；repository 5；conformance 654 passed / 5 skipped；backend 256 passed / 3 skipped；Rust/fmt/clippy/release wheel smoke/mypy/ruff 全通过 |
| `bash vnext/scripts/gate.sh native` | 0 | **PASS** — authoritative Rust probes 8；facade 18；artifact full-chain 57；R4 conformance matrix 3；wheel identity unchanged |
| `bash vnext/scripts/gate.sh phase-exit-container` | 0 | **PASS** — offline build；direct native smoke；Compose health/native smoke；identity persist；cleanup |

非 required suite 中的 skip 均为既有条件化测试；required matrix 本身 zero
skip/xfail/`UNSUPPORTED`。正式 gate 未启用 dirty allowance、success injection、
regression mode 或 platform bypass。

## 7. Immutable container identity

权威 artifact：

`docs/backend-vnext/refactoring/temporary/phase-1/artifacts/phase-exit-container-identity-95b3d7633caa7b536960552ba72e29b18bbe0fb6434d97b51b9cb40b9dde5f58.json`

| 字段 | 值 |
| --- | --- |
| `gate_status` | `passed` |
| `expected_head` / `source_revision` | `7702d2127712193a8a88e66ba614dc073922ac15` |
| image/config ID | `sha256:9f58f4ed48e2b6d8522201977d2df4f365bc13b674ddf7fdd42c6a95445b9df2` |
| release wheel SHA-256 | `18551041541e1d8fcf0d49a19c1cbd975298e9b2e10f2d6e67ec32592a55235c` |
| native extension SHA-256 | `5600abc550118a364aeb95f36126cd0880d9f955a10a8e812231aff24c751071` |
| network deadline | 3600 seconds |

Artifact 的 source/toolchain/lock/base/wheel/extension/image 字段已独立复算。
Content-addressed artifact 按既定策略 gitignored；这不影响其 immutable
evidence 身份。

## 8. Required matrix / artifact / structural evidence

- `data.canonical-row-hashes.mixed-scalars` 仍是唯一 formal scenario。
- `reference/null`、`integration/null`、
  `provider-matrix/python-reference`、
  `provider-matrix/rust-native` 四个 required cells 全部 `PASSED`。
- Python/Rust vectors 与 Repository consumer 继续全量消费同一 root。
- Integration cell 经过 facade → PyO3/Rust → IPC ArtifactRef → fresh reopen，
  并复验 size/raw hash/schema/sorted row hashes/semantic digest。
- PyArrow 25.0.0；Rust 1.97.0；GIL probe 4096 rows / 16×256 batches。
- Python row/list/dict materialization count：0。
- Memory evidence upper bounds：input 16384 B；hash-sort 131072 B；
  production IPC 131352 B。
- 不声明 numeric throughput/latency 收益。

## 9. Final blocking register

**EMPTY.**

| Historical item | Final |
| --- | --- |
| `CONTAINER-REGISTRY` | **CLOSED**；daemon proxy 恢复拉取，正式 gate 已通过 |
| `R5-PRECOMMIT` | **CLOSED**；R5 source commit 已创建并在 clean HEAD 重跑 |
| `WP5-R3-EVIDENCE-HOLD` | **CLOSED / ACCEPTED** |
| `WP5-R4-EVIDENCE-HOLD` | **CLOSED / ACCEPTED** |
| Container wheel/Compose/native-smoke/cleanup/toolchain/network findings | **CLOSED**；由 exact runtime evidence 复验 |

Docker Hub 慢速及早期 registry failure 保留在 environment ledger 作为历史事实，
没有被改写为 PASS，也没有作为 waiver 使用。

## 10. Patch SHA

Exit source 的冻结 R5 Patch SHA：

在 detached、clean 的
`7702d2127712193a8a88e66ba614dc073922ac15` worktree 中复算：

```bash
BASE=b747590ac6ffdfe0e00b320363ce429e663e358e \
  EXPECTED_SHA=457eafb996cb8a6bcb5d0c10ea7668c1175d3716f96aa72a67b8d0aad88fd1b3 \
  bash vnext/scripts/verify-wp5-r5-patch-sha.sh
```

值：`457eafb996cb8a6bcb5d0c10ea7668c1175d3716f96aa72a67b8d0aad88fd1b3`。

下列 `EXPECTED_SHA` 是 R4 base 到当前 closure worktree/HEAD 的累计审计 SHA；
它供现有防 staged/unstaged/untracked 漏计的 verifier 与 regression test 使用。

```bash
BASE=b747590ac6ffdfe0e00b320363ce429e663e358e \
  EXPECTED_SHA=750075cb4348c3c714148fb74362c19efb71a612df2fc4ea857ab09cdf3a48fb \
  bash vnext/scripts/verify-wp5-r5-patch-sha.sh
```

EXPECTED_SHA=750075cb4348c3c714148fb74362c19efb71a612df2fc4ea857ab09cdf3a48fb

## 11. Phase 1 exit conditions

| # | 条件 | 最终结论 |
| ---: | --- | --- |
| 1 | Correctness + native at exit commit | **SATISFIED** |
| 2 | Container at same identity + immutable evidence | **SATISFIED** |
| 3 | Required matrix all passed | **SATISFIED** |
| 4 | Python/Rust vectors + Repository consumer | **SATISFIED** |
| 5 | Artifact fresh reopen/raw/semantic verification | **SATISFIED** |
| 6 | `to_pylist()` demo not formal/public | **SATISFIED** |
| 7 | Blocking register empty | **SATISFIED** |
| 8 | Formal ownership complete；temporary discussion Resolved | **SATISFIED** |
| 9 | Rust/wheel/container policy evidence | **SATISFIED** |

## 12. Cleanup / limitations / rollback

- Gate 后无 Phase 1 containers、images、volumes、networks、staging、temporary
  directory 或 source-tree `.so` 残留。
- 未 push commit、未 push image、未发布 registry artifact、未部署、未自动
  bless golden/vector。
- Phase 1 明确 non-goals 不构成 blocking register 项。
- Source rollback point：`b747590ac6ffdfe0e00b320363ce429e663e358e`；
  rollback 只作为身份记录，不在本次收口中执行。
