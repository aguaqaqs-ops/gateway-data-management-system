# WP3 R4 — Kernel Component GIL / Failure / Determinism Evidence

状态：R4 sign-off evidence（seventh external-review remediation, worktree — **未提交**）

日期：2026-07-22

Authority：

- [WP3 R1 Arrow/PyO3 设计](wp3-r1-arrow-pyo3-design.md)（rev.3.1）§6、§8、§9、§10
- [Canonical Row Hash Compute Boundary](../../formal/contracts/canonical-row-hash-compute-boundary.md) §5–§7
- [Rust Safety and Performance Policy](../../formal/policies/rust-safety-and-performance-policy.md)

Gate：**`PR-CORRECTNESS` + native-kernel component**；**非** `PR-NATIVE` / `gate.sh native`

## 1. Summary

第七轮 remediation 闭合复审 Minor m1–m2：

- **m1 共享 EXIT trap**：抽出 `wheel_smoke_on_exit`；production `wheel_smoke` 与 `wheel-trap-regression` 安装同一 trap；body=0/restore=99→99，body=42/restore=99→42；断言 tmp 删除与 `CARGO_TARGET_DIR` 恢复
- **m2 历史 3.2MiB wheel tmp**：内容确认后删除 13 个目录；本轮准确路径 `/tmp/tmp.UVzt3YQdkt` 已清理；历史 wheel 查询（`/tmp/tmp.*` 下本项目 whl）为空

继承第六轮：启动同步、42/40 双计数、7×352MiB 清理、deferred。

## 2. Identity / worktree

| 项 | 值 |
| --- | --- |
| 基线（R3 sign-off） | `6b97ce8bcc08deb39c7bcbb6560cf79663feba5d` |
| merge-base | `6b97ce8bcc08deb39c7bcbb6560cf79663feba5d` |
| 已提交 R4 commits | `4b9c1cf`、`5dfeecd` |
| remediation worktree | 基于 `5dfeecd` 的第七轮回修（未提交） |
| **tracked patch SHA-256**（排除本 evidence） | `416a7d8b19920bbf1a2c356740c67d79c81e70b200d2174e491bf228279fb1b6` |

**不记录** evidence 自引用 full-diff SHA。

```bash
git diff 6b97ce8 -- . \
  ':(exclude)docs/backend-vnext/refactoring/temporary/phase-1/wp3-r4-kernel-component-evidence.md' \
  | sha256sum
# 416a7d8b19920bbf1a2c356740c67d79c81e70b200d2174e491bf228279fb1b6
```

### Untracked source manifest

| 路径 | sha256 |
| --- | --- |
| `kernel_component_tests.rs` | `251832f3d6b863b22f9b7fa9a8dfb47e0bc6f6461396aa9c173439ae52f30255` |
| `gil_00_python_thread.rs` | `9e9d702340391f826cca305f6dcfa439e0407abdf5c2692f54987764213810a3` |
| `gil_controller.rs` | `aa168dadfea1662cbb62a44387c7b1a7f588c8e91430f121a651aaa9c5108b98` |
| `gil_probe.rs` | `f2564cee5a2fd1814b6a487995f5c1fef7dbaef4bc40c29d274314af75215798` |
| `panic_matrix.rs` | `a8f7dabcd06c8baedd1a2c4aeb08ae629c84128ab4ec2ec34b6e1e3b7b7d768a` |
| `support.rs` | `3cde4ae0d8b83a0e45f3b5485b5858235af2dc5a6ca25d17a2dcf740a66e1db8` |
| `failure_goldens.rs` | `8c2001ca5152da092d0a78e3b46a3f61de1cb8865aed6fc6ec1c2a7d8a82b036` |

## 3. R3 inherited baseline

| 指标 | R3 sign-off | 本轮 |
| --- | ---: | --- |
| Rust workspace | **224** | **239** |
| R3 Python selected | 22 | gate backend **22** |

## 4. 变更清单（baseline..worktree）

### 新增（含 untracked）

| 路径 | 说明 |
| --- | --- |
| `kernel_component_tests/*` | GIL / panic / Python 线程探针 |
| `failure_goldens.rs` / `test_component_*.py` | golden + component suites |
| `native_kernel_component.sh` | wheel-smoke / component-pytest / **wheel-trap-regression** |

### 删除

| 路径 | 说明 |
| --- | --- |
| `test_probes.rs`、旧 `gil_probe.rs`、`adapter_panic_matrix.rs` | 迁出 production / 并入 tests |

### 修改

| 路径 | 说明 |
| --- | --- |
| `adapter.rs` / Cargo.toml / architecture-check | hooks、inventory、dev-deps |
| `gate.sh` | `target/gate`、component Ruff、trap regression、wheel-smoke |
| `native_kernel_component.sh` | finalize_exit、may_run 无关；restore 钩子；打印本轮 `tmp=` |
| `gil_00_python_thread.rs` | `py.detach` 启动同步 + barrier 回归 |
| `wp3-r3-pyo3-adapter-evidence.md` | R3 计数统一为 224 |

## 5. GIL 探针机制（R4-A1）

权威证据为真实 Python 线程计数（非 `AttemptPending` smoke）：

| Stage | 协议 |
| --- | --- |
| Import / Export attached | 启动：`may_run` + `py.detach(wait_until_started)`；hold `observed==0`；release 后 `>=16` |
| Parse / Compute detached | hold 期间 `>=16` |
| 负向 | Parse + attached 协议必须失败 |
| 启动同步回归 | `may_run` 在 `start()` 后仍 clear → detach 内 `set` → wait 仍成功 |

## 6. Fault / wheel isolation

| 检查 | 状态 |
| --- | --- |
| restore 成功+失败 → 非零（99） | ✅ 共享 `wheel_smoke_on_exit` + `wheel-trap-regression` |
| body 失败+restore 失败 → 保留 body 码 | ✅ 同一 production trap |
| 本轮 wheel tmp 打印并清理 | ✅ `wheel-smoke tmp=/tmp/tmp.UVzt3YQdkt`（gate 后不存在） |
| 历史 352MiB ×7 + 3.2MiB ×13 wheel tmp | ✅ 已删除（见 §14） |
| `/tmp/tmp.*` 下本项目 whl 查询 | ✅ **0** |

## 7. Failure matrix（R4-A3）

| Code | Golden | Python component | Rust |
| --- | --- | --- | --- |
| `COMPUTE_REQUEST_SCHEMA_INVALID` | ✅ | ✅ | ✅ |
| `COMPUTE_CONTRACT_VERSION_UNSUPPORTED` | ✅ | ✅ | ✅ |
| `COMPUTE_CANONICAL_VERSION_UNSUPPORTED` | ✅ | ✅ | ✅ |
| `COMPUTE_ARROW_MAPPING_VERSION_UNSUPPORTED` | ✅ | ✅ | ✅ |
| `ARROW_SCHEMA_MISMATCH` | ✅ | ✅ | ✅ |
| `ARROW_TYPE_UNSUPPORTED` | ✅ | ✅ precedence | ✅ |
| `CANONICAL_VALUE_INVALID` | ✅ | facade | ✅ |
| `ARROW_STREAM_IMPORT_FAILED` | ✅ | — | ✅ |
| `ROW_HASH_COMPUTE_FAILED` | ✅ | — | ✅ |
| `RESOURCE_LIMIT_EXCEEDED` | ✅ | — | ✅ |
| `ARROW_STREAM_EXPORT_FAILED` | ✅ | — | ✅ |
| `NATIVE_PANIC` | ✅ | — | ✅ Import/Compute/Export |

## 8. Determinism matrix（R4-A4）

| 测试 | 断言 |
| --- | --- |
| `test_duplicate_row_hashes_are_retained` | 同 hash ×2 |
| `test_multi_batch_partition_matches_single_batch_row_hashes` | bytes 一致 |
| `test_multi_batch_serial_execution_is_byte_identical` | 串行一致 |
| `test_serial_execution_result_jcs_is_exact_bytes` | JCS 精确 |
| `test_input_row_permutation_preserves_digests` | 置换不变 |
| `test_field_order_permutation_is_invariant` | 字段序不变 |
| `test_output_row_hashes_are_sorted_unsigned_lexicographic` | 排序 |
| `test_zero_batches_with_declared_schema_succeeds` | row_count=0 |
| `test_serial_execution_preserves_digest_fields` | digest 字段 |

## 9. Wheel identity

| 项 | 值 |
| --- | --- |
| Wheel | `gateway_compute_python-0.1.0-cp314-cp314-manylinux_2_34_x86_64.whl` |
| 本轮准确 tmp | `/tmp/tmp.UVzt3YQdkt`（gate 后已删除） |
| `CARGO_TARGET_DIR` | `$tmp/cargo-target` |
| maturin | `1.14.1` |

## 10. Lock identity

Rust `1.97.0`；pyo3 `0.29.0`；pyo3-arrow `0.19.0`；arrow `59.1.0`；pyarrow `25.0.0`；maturin `1.14.1`。

## 11. Dependency delta

无新增 production 第三方 crate。dev-dependencies：`gateway-compute-python-impl` / `gateway-compute-python` 的 arrow/pyo3-arrow/core（tests）；`Cargo.lock` membership 更新。

## 12. 验证命令

```bash
cd vnext && bash scripts/gate.sh correctness
# includes:
#   native_kernel_component.sh wheel-trap-regression
#   native_kernel_component.sh wheel-smoke   # prints wheel-smoke tmp=...
cargo test -p gateway-compute-python-impl kernel_component_tests -- --test-threads=1

# Full audit Python (42):
cd vnext/backend && uv run --offline --no-sync pytest -q \
  ../rust/gateway-compute-python/tests tests
```

## 13. 验证结果（第七轮 gate）

| 命令 | Exit | 结果 |
| --- | ---: | --- |
| Rust workspace | 0 | **239** passed |
| wheel-trap-regression | 0 | 共享 trap：99 / 42 + tmp/`CARGO_TARGET_DIR` 断言 |
| wheel-smoke | 0 | tmp=`/tmp/tmp.UVzt3YQdkt` → 已清理 |
| component-pytest | 0 | **18** |
| backend selected | 0 | **22** |
| **gate Python 精选合计** | 0 | **40**（18+22） |
| **完整 Python** `tests` + `gateway-compute-python/tests` | 0 | **42** passed |
| Ruff（含 component） | 0 | 通过 |
| `gate.sh correctness` | 0 | 全绿 |

## 14. Gate 前后状态

| 检查 | 结果 |
| --- | --- |
| `vnext/.cache/cargo-target-gate` | 不存在 |
| `vnext/rust/target/gate/release/libgateway_compute.so` | gate artifact |
| 本轮 wheel tmp `/tmp/tmp.UVzt3YQdkt` | **已删除** |
| trap regression tmp（`VZgrw8HXaE`、`e6pf1sczNs`） | **已删除** |
| 历史 352MiB wheel tmp（`GyEzw9hCDI`、`KC2tF0FMCc`、`OqsebP9tru`、`PyJWWcmyc4`、`WsIEmBgFLd`、`aKR5CTRKDr`、`gYK4nYH5tN`） | **已删除**（约 2.4 GiB） |
| 历史 3.2MiB wheel tmp ×13（`5anUT2n4wu`、`I1gijYGdjy`、`IRVotay3Zd`、`JkeXDrL7sb`、`KnLZP9gRxl`、`LorftoNoWT`、`N4ZGT67pvU`、`T071H5Bk56`、`UEuH0x7r5b`、`V6tTB0G94t`、`ZTxglcHHWr`、`di0EtiGJvx`、`qiuFzRSqXu`） | **已删除**（内容确认含同名 whl） |
| `/tmp/tmp.*` 下 `gateway_compute_python-0.1.0-*.whl` | **0** |
| 声明 | **不**声称“任意 `/tmp/tmp.*` 均不存在”；仅验证本轮准确路径与已识别历史 wheel 目录；未泛化删除其他 `/tmp/tmp.*` |
| source `.so` / hooks | 0 / `[]` |

## 15. R4-A1～R4-A8 checklist

| # | 项 | 状态 |
| --- | --- | --- |
| R4-A1 | GIL | ✅（detach 启动同步 + barrier 回归） |
| R4-A2 | Panic | ✅ |
| R4-A3 | Failure | ✅ |
| R4-A4 | Determinism | ✅ |
| R4-A5 | C Stream | ✅ |
| R4-A6 | Wheel + 共享 EXIT trap 回归 | ✅ |
| R4-A7 | Safety/lifecycle | ✅ |
| R4-A8 | Gate/Ruff/naming | ✅ |

## 16. Deferred

| 项 | 归属 | 说明 |
| --- | --- | --- |
| Kernel-native sign-off / dependency inventory 扩展 | **WP3 R5** | 超出 R4 component 边界 |
| ArtifactRef / IPC / corrupt IPC | **WP4** | 未实现 |
| 细粒度 C Stream chunk / `gate.sh native` | **WP4 R4** | native 现 exit 2 占位 |
| Scenario / harness / container / Phase 1 exit | **WP5** | Phase 1 范围外 |
| Python 级 GIL 权威证据 | — | 已由 Rust probes 承担 |

## 17. Remediation mapping

### 第七轮

| Finding | 修复 |
| --- | --- |
| **m1** trap 回归未覆盖 production EXIT | 抽出 `wheel_smoke_on_exit`；regression 安装同一 trap |
| **m2** 13×3.2MiB 历史 wheel tmp | 内容确认后删除；evidence + 历史 whl 查询为空 |

### 第六轮（继承）

| Finding | 修复 |
| --- | --- |
| **M1** 启动同步持 GIL 自旋 | `py.detach(wait_until_started)` + `may_run` barrier 回归 |
| **M2** evidence 40/42、tmp、deferred | 双计数；删 7×352MiB；本轮精确 tmp；补全 WP3 R5/WP4/WP5 |
| **m1** restore 无持久回归 | `wheel-trap-regression` 入 gate |

### 第五轮（继承）

Import/Export Python 线程权威；probe_stage lifecycle；restore 非零；Ruff；evidence manifest 初版。

## 18. Sign-off boundary

- **归属**：`PR-CORRECTNESS` + native-kernel component
- **不是**：`PR-NATIVE` / WP3 R5 / WP4 / WP5
- **工作区**：第七轮 remediation **未提交**（DO NOT COMMIT）
- **权威 GIL**：`gil_00_python_thread.rs`（含启动同步）+ `gil_controller`/`gil_probe`
- **权威 release**：`vnext/rust/target/gate/release/libgateway_compute.so` + §9 wheel
- **权威 wheel cleanup**：`wheel_smoke_on_exit`（production + regression 共用）
