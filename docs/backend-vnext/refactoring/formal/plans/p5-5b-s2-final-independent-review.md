# P5-5B-S2 Final Independent Review and Closure

状态：**S2 closure pass — S1 countersign complete**

日期：2026-09-15

Owner：Independent reviewer（新开 context；非实现侧自查）

评审对象 code candidate：`2da4d71f3c8090cfac08390cfe5f3fb79fd305f4`
（`feat(guard): add uv-consume wrapper and D-1 projection freshness`）

输入：

- [p5-5b-s2-round2-remediation-brief.md](p5-5b-s2-round2-remediation-brief.md) §6–§7
- [p5-5b-s2-handoff.md](p5-5b-s2-handoff.md)
- [p5-5b-s2-d1-projection-freshness-handoff.md](p5-5b-s2-d1-projection-freshness-handoff.md)
- [uv-lockfile-canonical-guard-pending.md](../../../uv-lockfile-canonical-guard-pending.md) §5–§7

## Closure summary

```yaml
candidate_head: 2da4d71f3c8090cfac08390cfe5f3fb79fd305f4
code_track_s2_findings: pass
design_track_d1: pass
process_track_f18: pass
engineering_track_uv_guard: pass
s1_countersign: pass
s2_closure: pass
unresolved_contract_drift: none
d2_status: reported_not_gating
```

## 1. 代码轨（A）— S2-F14–F18 + round-2 follow-up

| 项 | 结论 | 依据 |
| --- | --- | --- |
| S2-F14 version fencing | pass | `test_submit_transactions.py` stale step/attempt/abort 矩阵 |
| S2-F15 NO_CANONICAL_CHANGE / I/O boundary | pass | `main_resolve.calls==0`、writer/uow 探针、§6.1 顺序回归 |
| S2-F16 PREPARED abort gate | pass | EFFECT_PENDING-only；PREPARED 拒绝 |
| S2-F17 workspace CAS | pass | 选项 B 记录在 round-2 handoff |
| S2-F18 process | pass | 见过程轨 |
| Round-2 P1/P2 follow-up | pass | baseline I/O 事务外、writer 事件历史、no-op 优先级 |
| D-1 projection freshness | pass | 同连接 `resolve_provisioned_scope`；并发 winner replay 用例 |

### Verification record（@ `2da4d71f`）

```bash
./vnext/scripts/uv-consume.sh -C vnext/backend run --offline pytest -q -m unit \
  tests/test_architecture.py tests/test_submit_domain.py tests/test_submit_application.py \
  tests/test_submit_idempotency.py tests/test_submit_control_db_migrations.py \
  tests/test_sqlite_submit_repository.py tests/test_submit_transactions.py \
  tests/test_sqlite_workspace_repository.py tests/test_workspace_control_db_migrations.py
# 165 passed

./vnext/scripts/uv-consume.sh -C vnext/backend run --offline pytest -q -m unit
# 1894 passed, 115 deselected, 0 failed (~70s)

git diff -- vnext/backend/uv.lock | wc -l
# 0
```

五包 ruff/mypy、`test_canonical_lock_identity.py`、repository_service wrapper 单测：已在
`2da4d71f` 验证（`verified_at: 2da4d71f, not re-run`）。

## 2. 设计轨（B）— D-1

| 项 | 结论 |
| --- | --- |
| `same_uow_projection_freshness` 裁定 | pass |
| owning design §6.1/§6.3/§13.1 勘误落盘 | pass（commit `2da4d71f`） |
| `unresolved_contract_drift: none` | pass |
| **D-2** QUEUED/prepare-PENDING 取消无释放口 | **reported**，不 gate S2 pass |

## 3. 过程轨（C）— F18 / S1 countersign

| 项 | 结论 |
| --- | --- |
| `candidate_head` 绑定 review tip 全 SHA | pass → `2da4d71f` |
| `changed_paths` 补全（含 D-1、uv-lock guard） | pass（见各 handoff） |
| S1 independent countersign | pass（本节签署；见 [p5-5b-s1-handoff.md](p5-5b-s1-handoff.md)） |
| round-2 补救卷对齐 | pass |

S1 focused 复跑证据（S2 remediation 期间）：102 passed（S1 四文件）；九文件 165 passed；
全包 unit 1894 passed（交叉引用 round-2 / final 记录）。

## 4. 工程轨 — uv-lock canonical guard（合并提交触及 build/native 入口）

| 命令 | 退出码 | 备注 |
| --- | --- | --- |
| `prepare-dev-dependencies.sh` | 0 | 五锁 unchanged |
| `native_kernel_component.sh wheel-smoke` | 0 | release wheel + no-sync + restore |
| `native_kernel_component.sh wheel-trap-regression` | 0 | body+restore 子场景 |
| `NATIVE_KERNEL_FORCE_RESTORE_FAIL=1 wheel-smoke` | 99 | 预期 restore 失败 |
| `build-repository-service-image.sh` | 0 | `gateway-repository-service:local` → `sha256:b44a67a7fe6260293ce80ad5e94ee3ba8d65a6c9d16494255c9585807a837a44`；`CANDIDATE_SHA=2da4d71f` |
| `docker compose -f vnext/deploy/compose.yaml build backend worker` | 0 | 当前 HEAD 重建 |
| `./vnext/scripts/run-tests.sh` | 0 | 权威全量；见下 |

`run-tests.sh`：首次 serial 批次因并行 unit 遗留 dolt 子进程导致 2 项 compose teardown 失败
（环境残留，非候选回归）。清理后**同 SHA 重跑**全绿：五包 unit + `repository_service` serial
205 passed。

五锁全程 canonical（`git diff -- vnext/*/uv.lock` 为空；无 `192.168` registry 污染）。

## 5. 明确不纳入 S2 pass 的范围

- S3–S6 真实 Submit HTTP/Repository container journey（后续阶段）
- D-2 实现（仅上报）

## 6. 签署

按 brief §7 三轨并行门禁：**代码轨 + 设计轨 + 过程轨** 均 pass；工程轨在当前候选上 pass。
出具 **S2 closure: pass**；**S1 independent countersign: pass**（绑定 `2da4d71f`）。

下一授权步骤：**P5-5B-S3** entry（不以本卷自证 S3 delivery）。
