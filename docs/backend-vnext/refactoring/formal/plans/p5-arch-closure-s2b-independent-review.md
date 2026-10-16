# P5 架构收口 S2b（切换到规范域、commit 规范元数据与 DC9）独立审核

- 结论：**需修订**（1 项阻塞：S2b-F1）
- 日期：2026-10-16
- 审核对象：`p5-s2b` @ `0c45593afd8d2856cf8e50c419c3361cdffc394b`（H）；门禁提交 V = `adc5d87fea073545fde6416d123c3d7845e715ff`；
  实现 HEAD = `b0175cf583ba7e89b0db830607c0f9bf15dc4bf4`（V 之后只有执行计划 §8.9 允许的 benchmark 与 `tests/test_real_dump_*.py` 提交）。
  区间 `p5-s2a-exit..H`；区间内审核方文档提交 `0ce71cac27`、`a80ca8c402`、`cae9a0f82b` 不计入实现差异，实现差异按 `cae9a0f82b..H` 核对
  （208 个文件，+12,324 / −5,629）。不在分支中的 main 审核方文档提交 `62cc7c3e0f`（DC29）、`1925dcedc2`（DC30）、`5a1a391ea8`、
  `92db9df18e`（DC31）、`a889acc242` 只用于确定授权范围。
- 依据：执行计划 §2 S2b（内容 1–12 与验收）、§3 S2b 与 S1 延期路径、§8.1、§8.2、§8.5、§8.9；详细设计 §4–§5、§9–§10、§12–§13；
  Canonical Storage `3.2.0`；Repository Service Contract；R5 重试、接管与副作用恢复设计；owner 决议 DC29（§12）、DC30（§13）、DC31（§14）；
  S2a 独立审核报告；S1-F3；AGENTS.md「镜像身份等价」；handoff `plans/p5-arch-closure-s2b-handoff.md`。
- 审核在只读 detached worktree `/home/dev/gdds-review-s2b`（H）中进行。carried 复核在实施 worktree `/home/dev/gdds-p5-s2b`（H）中只做一次
  backend/worker 重建，期间没有运行测试，HEAD 与 `git status`（clean）前后不变。我没有读取真实 dump。

## 1. 结论摘要

S2b 的主体目标达成，证据扎实：

- 规范域切换、commit 规范元数据、`NO_CANONICAL_CHANGE`、DC9 删除和 S2b.0 延期项均已完成；
- DC29 的无主键兜底与 DC31 的 Catalog 上限均已落地；
- V 上权威 runner exit 0；
- 同一份代码的 t1–t4 真实数据完整走通：0 degraded / 0 failed；重传时全表 UNCHANGED 且 Submit 返回 `NO_CANONICAL_CHANGE`；有序 pseudo 行数与 census 一致；
- 我在同一 worktree 复现了 carried。

阻塞项只有一个。DC31 第二部分第 2 条要求“进程因外部原因退出时，重启后的 worker 在租约时长加退避之内接管过期租约”，但修复只覆盖 `PURE_RECOMPUTE` 步骤。Submit 的 `EXTERNAL_EFFECT` 步骤和 `NON_RETRYABLE` 步骤仍会落入停止 handoff 记录的那条路径：worker 在租约有效期内重启，变为 idle-ready，之后再也不检查租约是否过期，operation 永久停在 `RUNNING`（S2b-F1）。

修正量很小，需要形成新的 V 并重跑一次完整 runner。另有三项非阻塞问题（S2b-F2 至 S2b-F4）。真实数据是否需要在新 V 上重跑，按 §6 由 owner 确认。

## 2. Findings

### S2b-F1：worker 重启时，只有 `PURE_RECOMPUTE` 步骤会等待旧租约过期；其余步骤仍可能永久停在 `RUNNING`

- 类型：已证实缺陷（DC31 第二部分第 2 条只实施了一部分；属于 DC30 的 A 层）；是否阻塞：**是**
- 位置：`vnext/backend/src/gateway_backend/operations/recovery.py` `StartupRecovery.recover_pair`：
  - 首次判定租约未过期时，只有 `PURE_RECOMPUTE` 返回 `RETRYABLE_BLOCK`，其余能力返回 `READY`；
  - 事务内复查若发现租约未过期，一律返回 `READY`。
  测试 `tests/test_operation_takeover.py::test_live_external_effect_lease_keeps_existing_startup_behavior` 把 `EXTERNAL_EFFECT` 返回 `READY` 固定为预期。
- 依据（读代码）：
  - 进入正常领取循环后，`claim_one` 只领取 `PENDING` / `RETRY_WAIT` 候选（`operations/persistence.py`、`store.list_claim_candidates`）。过期租约的接管只发生在启动恢复里，此外没有任何周期性检查。这正是 handoff §8.3 写明的停止原因。
  - `build_recovery_routed_executor` 对非 `PURE_RECOMPUTE` 步骤会原样重新抛出 handler 异常，worker 进程随之退出。
  - Compose 的 `restart: unless-stopped` 会在数秒内拉起新进程，而租约时长是 30 秒，新进程启动时旧租约仍然有效。
- 触发场景：Submit 的 `EXTERNAL_EFFECT` 步骤（例如向 Repository 发布）出现未分类异常，或 worker 被 OOM kill。
  1. 容器在 30 秒内重启，启动恢复看到有效租约，返回 `READY`；
  2. 租约随后过期，但不会再被检查；
  3. 公开 operation 一直是 `RUNNING`、没有 diagnostic，直到下一次有人重启 worker。
  这与停止 handoff 中 t4 重传 Preview 的现象相同，只是步骤不同。
- 最小修正方向：
  - 启动时遇到任何能力的有效 `RUNNING` 租约都返回 `RETRYABLE_BLOCK`，事务内复查同样返回 `RETRYABLE_BLOCK`。启动循环已经带有有界退避，等待时间不超过租约时长；
  - 租约过期后，仍按 R5 现有的处置表进入重试、对账或人工恢复。
  - **审核方澄清**：这只是让启动等待旧租约过期，不改变 `EXTERNAL_EFFECT` 步骤的语义，也不改变 R5 处置表，因此不触发 DC31 第二部分第 4 条的停止条件。
  - 删除把 `READY` 固定为预期的测试，改为按三种能力列出的参数表：有效租约 → `RETRYABLE_BLOCK`；过期后 → 现有处置。
- 关闭标准：
  - 参数表覆盖 `PURE_RECOMPUTE`、`EXTERNAL_EFFECT`、`NON_RETRYABLE` 三种能力在有效租约和过期租约下的启动处置，事务内复查的竞态单独有一行；
  - 新 V 上权威 runner exit 0。

### S2b-F2：Preview 和 History 在组装阶段被取消时，结果是 `FAILED`，不是 `CANCELLED`

- 类型：已证实缺陷（旧代码中原本存在的路径，在本阶段改变了表现）；是否阻塞：否（建议在 S2b-F1 的同一轮修正）
- 位置：
  - `application/preview_jobs.py`：组装循环检查到 `control.cancel_requested` 时抛出 `PreviewJobError("preview assembly cancelled")`；
  - `application/pair_pipeline.py`：同样以抛 `PairPipelineError(cancel_message)` 的方式处理取消，Preview 侧把它转成 `PreviewJobError`；
  - `application/history/compare_jobs.py`：`HistoryCompareJobError("history compare assembly cancelled")` 与 `PairPipelineError` 的处理方式相同。
- 依据：
  - 这几处在 kickoff 前就是“抛异常”的写法，异常会冒出 handler，worker 随之退出。
  - S2b 给 `PURE_RECOMPUTE` 加了兜底捕获，现在它们变成 `PERMANENT_FAILURE`，diagnostic 为 `OPERATION.PURE_RECOMPUTE_FAILED`。
  - 同一文件中其他取消检查点都是发布 `_make_cancelled_terminal_builder()`，终态为 `CANCELLED`。
  - 没有测试覆盖组装阶段的取消。
- 触发场景：用户在 Preview 或 History 比较的组装阶段取消，界面显示失败而不是已取消。
- 最小修正方向：这几处改为发布取消终态，与其他检查点一致；补一行参数表或一个用例。
- 关闭标准：用例证明组装阶段取消后 operation 为 `CANCELLED`。

### S2b-F3：handoff 与 Contract 的若干记录和实际不符

- 类型：文档准确性；是否阻塞：否（在修订轮的 handoff 中更正；Contract 与决议文本由审核方在合入时更正）
- 内容：
  1. **storage projection version 实际已从 `1` 升到 `2`**，不是“不变”。改动来自 `26560b2595`（S2a-F1 浮点负零归一），连带 `RULESET_VERSION` 由 `v2` 升到 `v3`。
     - 负零归一会改变含 `-0.0` 的表的规范字节，所以升版本本身是对的。
     - 但 handoff §4、§8.7、DC29 决议 §12，以及 Canonical Storage `3.2.0` 段落都写着“storage projection version 不变”。
     - 4 个 storage-projection golden 中，版本字段的变化来自这个提交，不是 DC29。
  2. **路径预算外的生产改动没有登记。** handoff §1 写的是“路径预算外仅增加真实数据 runner 与 fixture 修复”，实际还有下列改动：
     - `capabilities/risk_evaluation/_engine.py`（`74db10e1fe`，行全部被抑制时的风险计数）；
     - `capabilities/bundle_assembly/_assembly.py`（`91ad5affcc`）；
     - `artifacts/store.py`、`infrastructure/artifact_store/{bounded_store,local_store}.py`（`9d2537c329`）；
     - `capabilities/snapshot_materialization/{materialize,artifact}.py`（`a8fb1ba902`、`e37323e220`）；
     - `capabilities/mutation_planning/{_planner,_repository_replay_renderer,contracts}.py`（`0c48314dbe`、`ce58301a4f`）；
     - `capabilities/storage_projection/_ordered.py`（`041640eb7b`）；
     - `capabilities/comparison/{ordered,row_encoding,contracts}.py`；
     - `capabilities/surface_assembly/*`。
     我逐个看过，规模都小，并且各自对应一个内容项或一次真实数据缺陷，可以接受，但需要在 handoff 中逐项登记理由。
  3. **V 的改动描述不准。** handoff §8.3 说 V（`adc5d87fea`）是把 barrier 改为“受控更长预算”。实际改动是把测试的拦截点从 `commit_exists` 移到 `catalog_at`。原因是 `09c3e8c217` 加了 Catalog 缓存后，读取路径不再调用 `commit_exists`，原拦截点永远等不到。改动本身合理，描述需要更正。
  4. **测试所在批次写错。** handoff 写 `test_submit_prepare_removed_tables.py` 和 `test_canonical_snapshot_identity.py` 在 repository_service 批次，实际都在 `vnext/backend/tests`（带 integration 标记），在 backend 批次中运行。
  5. **内容重复。** handoff §5 之后有一个重复的“8.1”小节，与 §8.1 内容相同，应删去。

### S2b-F4：故障注入参数表的“确定性错误”一行没有走生产路径

- 类型：测试真实性；是否阻塞：否
- 位置：`tests/test_operation_recovery_policy.py::test_pure_recompute_repository_read_failure_uses_bounded_terminal_diagnostics`。
- 依据：
  - 这一行直接注入 `HandlerExecutionFailure(retryable=False, diagnostic_code="repository.service_not_ready")`，但生产代码从不抛出不可重试的 `HandlerExecutionFailure`。
  - 不可重试的 `RepositoryProviderError` 在生产中的去向是：
    - `snapshot_materialization/repository_ref.py` 把它转为物化失败，diagnostic 为 `REPOSITORY_CATALOG_LOAD_FAILED`，消息里带有 wire code；
    - 少数情况下会冒到兜底捕获，diagnostic 为 `OPERATION.PURE_RECOMPUTE_FAILED`。
  - 因此 `preview_jobs.py`、`compare_jobs.py` 里 `if not exc.retryable: raise` 这一分支基本不可达。
  - 错误码映射已有测试：`test_production_wiring.py` 证明 500 `RESPONSE_LIMIT_EXCEEDED` 被判为不可重试。但没有一个用例证明完整链路：Catalog 超限 → Preview 进入 `FAILED`，且 diagnostic 带出原因。
- 最小修正方向：把这一行改成经 provider 与物化路径的用例，断言公开 diagnostic 的 code 和消息里带出 `RESPONSE_LIMIT_EXCEEDED`；不可达的分支删除或改为断言。
- 关闭标准：参数表的确定性错误一行走生产路径。

## 3. 验收核对

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| 设计 §12 的 S2b owner 测试与 control DB schema | 通过 | V 的权威 runner 全部收集并通过；我在审核 worktree 跑了 21 个 focused 文件，569 passed（§4） |
| `NO_CANONICAL_CHANGE` 唯一 owner | 通过 | 不变量只由 `test_submit_transactions.py` 断言（`NoCanonicalChange`）；`test_archive_compose_e2e.py` 只断言 HTTP 码，属于 Compose 旅程要求 |
| DC9 删除清单、OpenAPI、ADR 0016 | 通过 | `history_integrity.py`、`test_history_compare_integrity.py`、hidden summary 测试、`repository_import_artifact.py` 均已删除；src 与 tests 中无 `integrity-ack`、`integrity_incident`、`read_hidden_summary`、`HiddenFinalSummary`、`expected_digest_ref` 或两个 baseline digest port 的残留 |
| S2b.0 按 S1-F3 关闭 | 通过 | `http/orchestration/preview_acceptance.py` 只剩 45 行（构造命令）；History 受理在 `application/history/compare.py`，HTTP 层只做映射与结果读取；`application/job_steps.py` 为共享 helper |
| 导入基线 | 通过 | `import_rules` 为 0 / 0 / 14（S2a 退出时 3 / 0 / 14） |
| S2a-F1/F2 携带 | 通过（版本记录见 S2b-F3 第 1 点） | `test_canonical_snapshot_identity.py`、`test_canonical_state_identity.py` 在审核 worktree 用真实 Dolt 运行，12 passed |
| DC29 规则、存储与比较 | 通过 | 三类规则使用 `DDL_PRIMARY_KEY_OR_KEYLESS`，`device_cfg` 独立规则不变；`pair_planning` 只对 STANDARD 角色的兜底表使用 `FULL_ROW_DIGEST_SET_DIFF`，并允许主键出现或消失；重复行往返用例（`keyless_duplicates_dc29`）通过；manifest 写 `3.2.0`，读取不限制旧版本 |
| DC29 真实数据 | 通过 | keyless 兜底表 t1 23、t2 27、t3 27/28、t4 33 张，名单与决议的 35 个名字一致；无 `KEY_MISSING`；重传时全表 UNCHANGED |
| DC31 Catalog | 通过 | 离线估算 t3 174,294 bytes、t4 285,725 bytes，分处 262,144 两侧，原因确认；上限 2 MiB；取证实测 t4 285,725 bytes，3 倍为 857,175，未超；超限返回 500 `RESPONSE_LIMIT_EXCEEDED`，`GetOperation` 数值不变、错误码一致；Contract 已更新 |
| DC31 读取失败终态 | **未通过**（S2b-F1；另见 S2b-F2、S2b-F4） | 读取错误的分类、worker 不因 `PURE_RECOMPUTE` 异常退出、Preview 中途 SIGKILL 后恢复成立；非 `PURE_RECOMPUTE` 步骤的重启接管未覆盖 |
| 真实数据（DC22、G8 有序表四项） | 通过 | `s2b-realdata-b0175cf583-retry1.log`：起止 HEAD 均为 `b0175cf583`，clean，exit 0，PASS；pseudo 行数 4/4、3,056/2,674、9,858/9,858、12,676/12,688，与 census 一致；逐类 History 记录数没有公开接口，以 public record_count 加 bundle/surface digest 替代（§5） |
| 性能（DC30，经 DC31 修订） | 通过 | A 层：所有 operation 在 5 倍实测（最低 300 秒）的保护超时内进入终态；B 层：只记录；C 层：72 步表齐全，t4 v2 Preview 的 worker CPU 因计数器重置缺一格，已标明 |
| 对照基准（DC31 第三部分第 6 条） | 通过 | handoff §8.5 按档、按版本记录了规范状态摘要、Preview 计数、Catalog 字节数与行数、History record_count 和 digest |
| V 的门禁与 carried | 通过 | §4 |
| golden 变化逐项说明 | 部分（S2b-F3 第 1 点） | mutation renderer 的变化是批量 INSERT；manifest 与 ruleset golden 的变化是版本号和 `DDL_PRIMARY_KEY_OR_KEYLESS` |

## 4. 实际执行的检查

| 检查 | 命令或方法 | 结果 |
| --- | --- | --- |
| 区间与 post-V | `git log cae9a0f82b..H`；`git diff --name-only adc5d87fea H` | V 之后只改动 `benchmarks/real_dump_journey.py`、`tests/test_real_dump_journey.py` 和 handoff，符合 §8.9 |
| V 的门禁日志 | `s2b-gate-adc5d87fea.log` | 起止 HEAD 均为 V、clean，预检：无 Dolt、无 Compose、8000 端口空闲；六个批次 242 / 152 / 154 / 2,834 / 1,684 + 1 skipped / 205；runner_exit_code=0 |
| 真实数据日志 | `s2b-realdata-b0175cf583-retry1.log` | 起止 HEAD 均为 `b0175cf583`、clean，exit 0，PASS。该次运行由 `b0175cf583` 自行构建镜像（compose project 不同，image ID 不同）；V 到 `b0175cf583` 之间没有镜像输入变化 |
| carried | 在 `/home/dev/gdds-p5-s2b`（H）运行 `build_context_digest.py identity`；以 `COMPOSE_PROJECT_NAME=ordered-bisect-b-2918210-baseline docker compose -f vnext/deploy/compose.yaml build backend worker` 重建一次 | identity 为 revision `adc5d87fea…`、source-tree `sha256:5b34d0c5…`，与 RS 镜像 label 一致；backend `sha256:b90b70e0…`、worker `sha256:e14b5b89…` 与 provenance 相同。日志 `s2b-review-carried-0c45593afd.log`。carried 成立 |
| 五包静态检查 | 各包 `uv-consume.sh run ruff check .` / `run mypy` | 全部通过（34 / 15 / 26 / 198 / 475 个 source files） |
| `import_rules` | `python -m tests.support.import_rules` | 0 / 0 / 14 |
| backend focused | 21 个文件：canonical metadata、canonical domain、standard、history jobs、mutation planning、operation recovery policy、worker startup、preview materialize、production wiring、repository ref protocol、risk、storage projection core、submit 的四个 owner、surface、table rules、architecture | 569 passed |
| repository_service unit | `pytest -m unit -n 8` | 1,494 passed，1 skipped |
| 规范同一性（真实 Dolt） | `test_canonical_snapshot_identity.py`、`test_canonical_state_identity.py` | 12 passed |
| DC31 代码 | 读 `recovery.py`、`http_arrow.py`、`preview_jobs.py`、`compare_jobs.py`、`repository_ref.py`、`versioned_read/{wire,application}.py` 的区间差异 | 发现 S2b-F1、S2b-F2、S2b-F4；Catalog 缓存先做可见性检查再查缓存，按 `(repository_id, commit_id)` 缓存不可变 commit，有条目数和字节上限 |
| 预算外路径 | `git diff --numstat` 加 `git log` 逐文件定位提交 | S2b-F3 第 2 点 |
| golden | `git diff cae9a0f82b H -- vnext/fixtures/golden` | 见 §3 |

## 5. 验证限制与剩余前置

- 我没有重跑全量 runner 和真实数据；门禁结果取自实施方在 V 上的完整日志和真实数据日志，并复核了 carried。
- 我没有读取真实 dump。t2 v2 的 Preview `table_count` 为 219，而提交后 Catalog 为 208 张表。这与“v1、v2 之间各有 11 张表增删”一致，但没有表名无法核实。建议修订轮的 handoff 由脚本经公开 Preview 结果给出各档 ADDED / REMOVED 表数。
- 逐类 History 记录数没有公开读取接口；实施方以 public record_count 加 bundle/surface digest 替代，没有新增接口，我接受。digest 作为 Phase 6 的对照基准比逐类计数更强。审核方合入时把 DC31 第三部分第 6 条与执行计划的对照基准写法改为“record_count 与 bundle/surface digest”。
- py-spy 采样未做（DC31 第三部分第 3 条为可选）。
- 合入时审核方更正的文档：Canonical Storage `3.2.0` 段落、DC29 决议 §12 中“storage projection version 不变”的表述（S2b-F3 第 1 点）。

## 6. 修订轮要求

1. 修正 S2b-F1（阻塞）；建议同轮修正 S2b-F2，并处理 S2b-F4；在 handoff 中按 S2b-F3 更正。
2. 修正改动了 `backend/src`，因此形成新的 V，在新 V 上运行一次完整权威 runner；carried 在同一 worktree 判定。
3. 真实数据：S2b-F1 与 S2b-F2 只改 worker 启动恢复和取消终态的发布，真实数据旅程中没有重启或取消，这两条路径不会被执行。审核方建议沿用 `b0175cf583` 的真实数据取证，不在新 V 上重跑，**待 owner 确认**。若 owner 不同意，则按 §8.9 在新 V 上完整重跑一次。
4. 复审范围：`H..新 H` 的增量，加上 S2b-F1 至 S2b-F4 的关闭标准。
