# P5 Prepare 确定性失败与 Occupancy 调查报告

> **性质**：阶段性调查决策报告；**最小修复已实施**（`0d9d0d9dc5` 及本报告收尾修订）。  
> **修复 HEAD**：`0d9d0d9dc5`  
> **5E 门禁候选（gate）**：`217236980350d523101936af5464fbbd9ad66f88`（S4 slice exit 基线；本修复不重开 5E exit）。

**当前状态（评审用语）**：checkpoint attempt 绑定失败 **已证子类** 已修复；prepare focused 与五包 ruff/mypy **已通过**（`0d9d0d9dc5` 复跑：prepare 7 passed ~1.8s）。**容器验证处置待补齐**（见 §九）。其他 decode/异常路径仍为未评估项，不扩大本轮范围。

**5E slice exit**：无需因本调查或最小修复重开。

## 一、基线、源码锚点与验证命令

### 1.1 权威实现锚点

| 主题 | 位置 |
| --- | --- |
| Prepare handler 窄出口 | `submit_jobs.py` — `build_prepare_import_handler` |
| Binding 失败 → abort | `PrepareCheckpointPayloadBindingError` → `_publish_prepare_binding_failure` |
| Publication 失败 → abort | `_publish_prepare_projection_failure` → `abort_prepared_submit_in_control_transaction` |
| Worker 未捕获异常 | `worker_runtime.py` — `_validate_executor_outcome` re-raise（binding 失败在 handler 内 terminal，不经 fatal） |
| Prepare recovery | `prepare_import` → `PURE_RECOMPUTE`；`build_submit_recovery_port` **不含** prepare |
| Contract §9 | `external-effect-and-recovery.md` — **允许**释放 occupancy 的条件，非「凡未捕获即须 abort」 |

### 1.2 阶段一命令（handler-direct 对照，历史）

阶段一使用临时 `test_prepare_occupancy_investigation.py`（已删除）；对照用例保留在 `test_submit_job_prepare.py`。

### 1.3 正式验证命令（修复后）

```bash
cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_submit_job_prepare.py -k 'prepare'
```

**正式测试 nodeid（替代调查模块）**：

| 用例 | nodeid |
| --- | --- |
| Handler：binding mismatch → abort | `tests/test_submit_job_prepare.py::test_prepare_checkpoint_payload_binding_mismatch_aborts_prepared_attempt` |
| Worker：binding mismatch → abort；occupancy 释放后 **在恢复 preview protection 前提下** 再 accept | `tests/test_submit_job_prepare.py::test_prepare_checkpoint_payload_binding_mismatch_worker_aborts_and_allows_reaccept` |
| 反例：其它 decode → 保留 occupancy | `tests/test_submit_job_prepare.py::test_prepare_checkpoint_schema_mismatch_retains_occupancy` |
| Publication 失败对照 | `tests/test_submit_job_prepare.py::test_prepare_handler_publication_failure_marks_operation_failed` |

Compose B′（引用，未重跑）：`assert_submit_occupancy_cleared_in_compose` + `p5-5e-s3-handoff.md` §156–158。

---

## 二、静态路径（代码路径确认）

Handler **仅**窄 catch：

- `SubmitImportPublicationError` → abort（既有）
- `PrepareCheckpointPayloadBindingError` → abort（最小修复）

其余 `CheckpointDecodeError`、`SubmitImportBuilderError` 等 **不**经 abort catch。Contract §9 描述的是 matching finalize 或 stable failure abort **之后**可释放；不得将 lease/CAS、`CheckpointPublicationError`、effect 不确定等默认等同于应 abort。

---

## 三、动态复现

| ID | 路径 | 触发条件（生产含义） | 修复前实测 | 修复后（正式测试） | 证据层级 |
| --- | --- | --- | --- | --- | --- |
| **0** | 既有单测 + handler 镜像 | `SubmitImportPublicationError` | FAILED / ABORTED / occupancy **释放** | 不变 | **测试复现确认** + S3 compose 引用 |
| **1** | **handler_direct** | 合成 `RuntimeError` | occupancy **保留** | 不变 | **handler 层仅** |
| **1b** | **handler_direct** | 内存 patch `attempt.state` | occupancy **保留** | 调查模块已删；结论保留 | 合成对照 |
| **2** | **handler_direct + synthetic** | mock decode | occupancy **保留** | 不变 | **无效**用于 worker 结论 |
| **3** | **worker_runtime** | 持久化 checkpoint 篡改 `job_state.attempt_id` 与 payload 不一致 | worker-fatal；occupancy **保留**；再 accept → **`SubmitOccupancyConflict`** | **FAILED / ABORTED / occupancy 释放**；在测试中 **手动恢复 `current-preview` protection**（与首次 accept 同型）后，新 idempotency key **`accept_submit_transaction` 成功**（**非**「失败后零准备即可重试」） | **测试复现确认（worker）** |

**阶段二触发说明（ID 3）**：「持久化 checkpoint 与 control payload 的 attempt 绑定不一致」（存储或元数据损坏的可解释类），**无 Repository effect**。

**收敛形态（ID 3）**：lease 到期后 step 进入 `RETRY_WAIT` 并再次 claim 后发生 **同类确定性失败**；若再次重试仍会失败为 **代码路径推断**（修复前未自动 abort）。修复后 handler 在 binding 失败时 terminal abort，不再依赖 worker 未捕获异常。

---

## 四、根因归类

| 根因 | 判断 |
| --- | --- |
| Publication 失败走 abort | **成立**（对照 0） |
| Binding mismatch 未走 abort（修复前） | **成立**（ID 3） |
| Handler 未 catch 其它非 publication 异常 | **成立**（反例 schema mismatch） |
| Worker-fatal ≠ step FAILED+abort（修复前 ID 3） | **成立**；修复后 ID 3 在 handler 内 terminal |
| 批量认定所有异常类均应 abort | **证据不足** |
| S3 主路径（projection → `SubmitImportPublicationError`） | **未复现缺陷** |

---

## 五、影响与分类

| 项 | 分类 |
| --- | --- |
| 生产 projection/DDL → `SubmitImportPublicationError` | **未复现缺陷** |
| Checkpoint reuse 下 **已证** 子类：payload 与 checkpoint `attempt_id` 绑定失败 | **已修复**（窄异常 + abort） |
| 其它 `CheckpointDecodeError`（如 schema） | **未修复**（仍保留 occupancy，见反例测试） |
| `SubmitImportBuilderError`、package SHA mismatch on reuse | **本轮未单独证 worker** |
| `CheckpointPublicationError`、lease 类 | **未纳入**本轮修复 |

---

## 六、是否建议 P5 首批修复

**已实施**：范围与 §七一致，仅为 ID 3 同型 binding 失败。

---

## 七、最小修复（已实施）

1. **`PrepareCheckpointPayloadBindingError`**（`CHECKPOINT_PAYLOAD_BINDING_MISMATCH`）：仅在 `_prepare_checkpoint_from_job_state` 中 `job_state.attempt_id != expected_attempt_id`（来自 payload）时抛出。
2. Handler **`except PrepareCheckpointPayloadBindingError`** → `_publish_prepare_binding_failure`，diagnostic **`CHECKPOINT_ATTEMPT_BINDING_MISMATCH`**；`submit_attempt_id` 来自 operation business ref / payload，**不使用** checkpoint 内 `attempt_id`。
3. 复用 `_publish_prepare_terminal_abort` / `abort_prepared_submit_in_control_transaction`（与 publication 失败同型）。
4. 正式测试见 §1.3；调查模块 `test_prepare_occupancy_investigation.py` **已删除**。

---

## 八、调查结束 → 最小修复

| 项 | 值 |
| --- | --- |
| 窄异常 | `PrepareCheckpointPayloadBindingError` |
| Operation diagnostic | `CHECKPOINT_ATTEMPT_BINDING_MISMATCH` |
| Attempt abort_code | `CHECKPOINT_ATTEMPT_BINDING_MISMATCH` |
| Worker 正式测试 | `test_prepare_checkpoint_payload_binding_mismatch_worker_aborts_and_allows_reaccept`（可控时钟，无 `sleep(31)`） |
| 再 accept 证据边界 | 证明 **occupancy 已释放** 且 **满足 accept 的 preview 前置条件**（`current-preview` protection 与 preflight 一致）后可重新 accept；abort 会清除首次 accept 建立的 protection，生产路径须由 preview/accept 流程重新建立 |
| 5E slice exit | **不重开** |

**剩余不确定项**：

- Publication 成功后 `publish_checkpoint` / pin 失败与 occupancy 的端到端组合。
- `SubmitImportBuilderError`（如 package SHA）在 **worker** 路径是否与修复前 ID 3 同结论。

---

## 九、容器验证处置（`testing-conventions.md` 评审记录）

本修复除 handler/abort 逻辑外，还修改了生产 **`bootstrap/operation_worker.py`** 中 `build_worker_runtime` 的 **`read_uow_factory` / `now_factory` 可选注入**（默认路径与改前等价，但属 worker runtime 组合接线变更）。**不得**将祖先镜像的 Compose 结果表述为 `0d9d0d9dc5` 已通过容器门禁。

```text
Current HEAD: 0d9d0d9dc5（本报告收尾修订以同线 HEAD 为准）
Container rebuild required: yes
Reason: 生产 bootstrap `operation_worker.py` worker runtime factory 接线变更（可选 read/now 注入触及组合边界）；非「仅 harness」改动
Last verified image revision: 217236980350d523101936af5464fbbd9ad66f88（5E S4 gate 基线；非本修复 HEAD）
Last verified source-tree/image id: none（本修复 HEAD 未 fresh 构建）
Container gate for current HEAD: deferred
Deferred gates/nodeids: 受影响 backend/worker 镜像 fresh build + 权威 Compose/production gate（具体 nodeid 按阶段最终候选与 `p5-5e-history-compare-execution-plan.md` / handoff 登记）；本修复未重跑 compose
Required execution point: 阶段最终候选或宣称「当前 HEAD 已通过容器门禁」之前
```

**已完成的非容器验证**（`0d9d0d9dc5`）：

```bash
cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest -q -m unit \
  tests/test_submit_job_prepare.py -k 'prepare'
# 7 passed, ~1.8s

cd vnext/<package> && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy
# 五包全部通过
```

---

## 附录：证据层级

| 标记 | 含义 |
| --- | --- |
| **handler_direct** | `LeaseSession` + handler，非 `WorkerRuntime._run_claim` |
| **worker_runtime** | `claim_one` + `_run_claim` |
| **synthetic** | mock / 内存 step / 不可达注入 |
