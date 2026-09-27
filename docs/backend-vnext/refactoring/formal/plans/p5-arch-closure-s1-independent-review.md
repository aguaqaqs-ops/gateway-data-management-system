# P5 架构收口 S1 独立审核

- 结论：**定向修订**
- 日期：2026-09-27
- 审核对象：p5-closure/s1 @ `fa9dd6392c6023c48a12440a31cfe67d62baff89`（实现 HEAD `1caf2ffc26f690188f8311904bce24693fb61d43`），base main @ `218c211240b33e01eee1eb8965fdcca0ec4b8099`
- 依据：执行计划 §2 S1 kickoff 与 S1、§3 S1、§7、§8.1–§8.4、§8.8；设计 §9（S1 项）、§12、§14；ADR 0018–0021；AGENTS.md；
  `plans/p5-arch-closure-s1-handoff.md`

## 1. 结论摘要

S1 的主体方向成立。`import_rules` 输出 3/0/10，DC26 只放行 `capability:canonical_row_hash → ext:compute` 一条；死代码与两个
占位 capability 已删除，backend 用例减少 31 个，恰好等于删除的死代码用例数；comparison 行编码拆分与 pair 流水线抽取都是
等价移动；五包 ruff/mypy 通过。

阻塞项共 6 个：

1. A1 改变了 FAILED 终态 Repository 证据的字节，并放宽了它的解码校验。
2. history HTTP DTO 丢了 4 处约束。
3. 设计 §9 的三个 S1 项没有实施：Preview/History 受理用例下沉、UoW 枢纽按 owner 拆分、step plumbing 共享。handoff 却写
   “已闭合，无 §3 定向偏差”。
4. 不可达基线停在 10，靠的是生产代码里的 reachability shim；A7 的 facade 规则被换成放行上游私有模块的白名单。
5. 基线条目改名没有给出理由，Phase 6 延期与 `external_target_sync` 延期都没有登记。
6. kickoff 普查没有产出 §2 要求的事实，却给出了 DC12/DC15“未触发”的决议。

这些都能在现有结构上局部修正，不需要重建核心方案，所以结论是定向修订。修订并复审通过之前，不合入 `main`，也不进入 S2a。

## 2. Findings

### S1-F1：A1 改变 FAILED 终态 Repository 证据字节，并放宽持久证据的解码校验

- 类型：已证实缺陷；是否阻塞：是
- 位置：`application/submit_jobs.py:1672-1683`（`_serialize_terminal_repository_evidence` 改用 `asdict`）；
  `application/submission/contracts.py:422`（`RepositoryImportOperationError` 只有 `code`、`message`）与 `:435`
  （`repository_import_operation_from_evidence_payload`）；`submit_jobs.py:1740`。
- 依据：设计 §9 A1 要求“保持请求证据字节、实际发送与恢复语义一致”；§2 S1 要求 checkpoint 载荷不变。wire 端的
  `SimpleError` 带有 `details` 与 `request_id` 两个字段。base 用 `operation.error.model_dump(mode="json")` 写证据，
  用 `VersionedOperation.model_validate` 读证据；后者校验 UUID、稳定终态错误码、`request_id` 为空、result/error 不变量，
  并拒绝多余字段。
- 触发场景与影响：Repository 导入以 FAILED 结束（例如 `IMPORT_REJECTED`）时，await 步骤写入终态证据。审核者在临时目录
  用同一 `VersionedOperation` 对比两个版本的输出：
  - base：`"error":{"code":"IMPORT_REJECTED","details":{"table":"t1"},"message":"rejected","request_id":null}`
  - HEAD：`"error":{"code":"IMPORT_REJECTED","message":"rejected"}`

  证据 artifact 的字节与摘要因此改变，Repository 给出的 `details` 也丢失了。解码侧同样放宽：非终态错误码
  （`SOMETHING_ELSE`）与非 UUID 的 `operation_id`，base 拒绝（ValidationError），HEAD 接受；error 缺少 `message` 时，
  HEAD 抛出的是 KeyError 而不是校验错误。SUCCEEDED 证据的字节不变，请求证据字节也不变（逐项核对了媒体类型常量与
  sha256 前缀处理）。现有测试没有覆盖 FAILED 证据的格式，所以全量仍是绿色。
- 最小修正方向：业务侧的错误值保留 `details` 与 `request_id`，或者把证据的序列化与解码留在 infrastructure codec 里，
  经 port 暴露，使证据字节与 base 一致；解码恢复与 `VersionedOperation` 等价的校验。`wire_codec` 中没有使用者的 helper
  （`repository_artifact_ref_to_wire`、`import_operation_from_evidence_payload`、`terminal_evidence_payload_from_operation`、
  `wire_terminal_status_value`）要么接入，要么删除。
- 关闭标准：在 submit job 的现有 owner 测试中，用一条 golden 固定 FAILED 证据的字节（含 `details` 与 `request_id`），
  并用模块级参数表覆盖解码的拒绝情形（非终态码、非 UUID、缺字段、多余字段、`request_id` 非空）。

### S1-F2：history HTTP DTO 丢失约束（OpenAPI 与 base 不一致）

- 类型：已证实缺陷；是否阻塞：是
- 位置：`http/schemas/history.py:46,56,149,151`。`commit_id`、`before_commit`、`current_commit` 的类型从 `CommitIdString`
  改成了 `str`。
- 依据：§2 S1 要求 HTTP DTO 不变；N-http-bypass 只要求 HTTP 不导入 wire 类型，并不允许放宽约束。
- 触发场景与影响：审核者分别从 base 与 HEAD 的源码生成 `/openapi.json` 做 diff，唯一差异就是这 4 个字段丢了
  `minLength: 1` / `maxLength: 1024`。响应模型也不再拒绝空的 `commit_id`。
- 最小修正方向：在 `http/schemas/constraints.py` 定义等价的有界字符串别名（min 1、max 1024），替换这 4 处。
- 关闭标准：HEAD 与 base 生成的 OpenAPI JSON 字节一致；最好补一条 OpenAPI 快照或约束断言。

### S1-F3：设计 §9 的三个 S1 项未实施，handoff 却报告“已闭合”

- 类型：已证实缺陷；是否阻塞：是
- 位置与事实：
  - **Preview/History 受理用例**：`http/orchestration/preview_acceptance.py:116`（`accept_preview_operation`）与
    `http/orchestration/history_compare.py:103`（`accept_compare_operation`）仍在 HTTP 层打开控制事务、写入 acceptance、
    插入 operation。`application/workspace/preview.py` 与 `application/history/compare.py` 在本 diff 中没有改动。
  - **UoW 枢纽**：`application/archive/ports.py:10`、`application/history/ports.py:19` 仍然只是 submission 的
    `WorkspaceControlTransaction` / `WorkspaceControlUnitOfWorkFactory` 的别名；Preview 受理使用
    `SubmitControlUnitOfWorkFactory`。新增的 `application/control_transactions.py` 只被 `http/dependencies.py` 的只读 store 使用；
    `application/workspace/ports.py` 只是重导出 domain port。
  - **step plumbing**：`application/job_steps.py:36` 的 `pinned_checkpoint_builder` 没有调用方；三份私有的
    `_pinned_checkpoint_builder`（`preview_jobs.py:1413`、`history/compare_jobs.py:1516`、`submit_jobs.py:2219`）都还在。
    实际共享的只有 `unique_artifact_refs` 与 Preview/History 的 `_run_comparison_risk_surface`（后者经核对为等价移动）。
- 依据：§2 S1 的目标是“关闭设计 §9 标为 S1 的项”；§3 S1 把这三项列为必改；handoff §3 与 §7 写“已闭合”“无 §3 定向偏差”。
- 影响：S2b 要在 Preview/Submit/History 的受理与 job 中接入规范域。受理逻辑留在 HTTP、事务 port 共用 submission 枢纽，
  会让 S2b 的改动面比设计预期更大；S1“后续语义变更只改一处”的前提也不成立。
- 最小修正方向：实施这三项；如果 owner 决定延期，就在 handoff 中逐项写明偏差、理由与目标阶段，并同步执行计划，
  不能以“已闭合”报告。没有使用者的 `pinned_checkpoint_builder` 要么被三个 job 共用，要么删除。
- 关闭标准：受理用例位于 Application，HTTP 只做 DTO 映射与准入；workspace/archive/history 各自声明所需的事务 port，
  组合在 bootstrap/infrastructure 完成；三个 job 共用一个 step helper。或者 owner 书面接受的延期记录。

### S1-F4：不可达基线靠生产 shim 维持；A7 的 facade 规则被换成私有模块白名单

- 类型：已证实缺陷；是否阻塞：是
- 位置：`capabilities/snapshot_materialization/materialize.py:98-109`（`_ensure_composite_signal_production_anchor`，每次
  `materialize_sql_snapshot` 都会调用）；`capabilities/snapshot_materialization/compose.py:17`；`tests/test_architecture.py:776-785`。
- 依据：设计 §9 A7 规定“公共面改为 facade + contracts，contracts 为叶子；DAG 测试放行上游 facade”；执行计划 §7 规定
  不得以兼容代码或新增基线条目绕过；§8.1 要求基线条目的变化在同一提交中说明。
- 事实：
  - A7 把 lazy wrapper 从 `contracts.py` 移到了 facade `__init__.py`，而 `import_rules.unreachable_modules` 不计入来自
    `__init__.py` 的边。审核者在临时副本中删去 shim 函数后重算，不可达集合从 10 变成 14，多出
    `composite_signal._ast`、`_bind`、`_digest`、`materialize`。
  - shim 的唯一作用是让静态指标命中 §2 列出的 10 项，同时给生产热路径加了一条运行时导入。
  - handoff 没有说明这个 shim，只在提交标题 `d97428ed22` 中提到。
  - DAG 测试也没有放行上游 facade（`remainder == ""` 仍然判为违规），而是逐对放行上游私有实现模块：
    `snapshot_materialization.sql_declared_types`、`composite_signal.materialize`、`table_rules.resolver`。
    这比 base 的“只能导入 contracts”更宽，与 A7 的方向相反，handoff 同样没有说明。
- 最小修正方向：
  1. 删除 shim。
  2. 二选一：一是让 `import_rules` 把 facade 中定义的 wrapper 函数的函数内导入计入该符号，并在 `IMPORT_RULE_SHAPES`
     中加一条用例；二是如实登记这 4 个 composite 模块为不可达（S3 关闭），并在 handoff 中说明与 §2 列表的偏差，交 owner 确认。
  3. DAG 测试改为放行上游 facade，消费者经 facade 或 contracts 导入，删除私有模块例外；确需保留的例外逐条说明理由。
- 关闭标准：没有只为可达性存在的生产代码；`import_rules` 输出与基线一致，每个条目都有理由；DAG 测试中不再有未说明的
  私有模块例外。

### S1-F5：基线改名理由、Phase 6 延期与 `external_target_sync` 延期均未登记；基线治理说明被删除

- 类型：已证实缺陷（验收项缺失）；是否阻塞：是
- 位置：`vnext/backend/tests/architecture_baseline.py`（整体重写）；handoff §4。
- 依据：§2 S1 要求 canonical row hash 改名导致的条目替换在同一 diff 中给出理由并登记 Phase 6 延期；`external_target_sync`
  三个模块要在 owning 设计中登记延期；设计 §9 A6 与 A9 也有相同要求。
- 事实：
  - 全 diff 与所有提交信息中都找不到 Phase 6 延期、改名理由或 `external_target_sync` 延期的文字，handoff 也没有提及。
  - base 文件头的治理规则（新增条目必须在同一 diff 中给出经评审的理由；陈旧条目必须删除；A<n>/N-* 分组标签）被整段删除，
    剩余条目也不再标注关闭阶段。
- 最小修正方向：恢复文件头的治理规则；为 10 个不可达条目和 3 个违例标注分组与关闭阶段（S2b / S3 / Phase 6 / 外部目标延期）；
  在 owning 设计中登记 `external_target_sync` 与 canonical row hash 的延期，并在 handoff 中引用。
- 关闭标准：每个基线条目都有归属与关闭节点；两处延期在 owning 文档中可查。

### S1-F6：kickoff 普查未产出要求的事实，DC12/DC15“未触发”属于过度表述

- 类型：已证实缺陷；是否阻塞：是（S1 阶段验收与 S2a 开工的前置）
- 位置：handoff §1。
- 依据：执行计划 §2 kickoff 第 4 项列出了 handoff 必须记录的内容：dataset ID、SHA-256、规模、表数、总行数；非 SKIP
  存储表的列类型分布；词表外类型、无键表、重复键、可空键列、JSON 列清单；`version_manager.saved_time` 的实际类型；
  `logics.xml` 的解析结果。第 5 项要求按普查结果落定 DC12/DC15。§8.3 要求 `pair_of` 由 owner 确认。
- 事实：
  - handoff §1 没有逐个数据集的记录。它自己写明 SQL 多为 `UNSUPPORTED_STATEMENT`，业务物化多数 FAILED，结构统计多为空，
    “不得当作 S2a 强证据”；但同一节又把 DC12 写成“未触发 → S2a 仍 fail-closed JSON”，DC15 写成“未触发词表扩充”。
  - 在解析基本失败的情况下，JSON 列与词表外类型清单为空，只说明没能观测到，不说明数据中没有，不能据此落定决议。
  - `pair_of` 写成了事实，但没有 owner 确认的记录。
- 最小修正方向：先查明 SQL 被判为 `UNSUPPORTED_STATEMENT` 的原因（普查脚本的解析入口，或 dump 中超出 parser 范围的语句），
  修正后重跑普查，并按 §2 第 4 项补齐 handoff 记录。若确实超出 parser 范围，按设计 §14 与计划 §7 交 owner 处理。
  重跑之前，DC12/DC15 标为“未判定”。补上 owner 对 `pair_of` 的确认。
- 关闭标准：handoff 中有 8 份数据集的结构统计；DC12/DC15 的决议基于实际观测，或者由 owner 显式处置。

### S1-F7：常量复制代替组合根注入

- 类型：已证实缺陷（设计偏差，当前值一致）；是否阻塞：否（S2a 修改规则集版本之前必须处理）
- 位置：`application/workspace/contracts.py:24`（`PREVIEW_FROZEN_RULESET_VERSION = "v2"`，复制了 table_rules 的
  `RULESET_VERSION`）；`application/workspace/contracts.py:129-131` 与 `settings.py:10,14`（`FIXED_UPLOAD_*` 两处定义）。
- 依据：设计 §9 N-http-bypass 规定“设置常量由组合根注入”。
- 影响：Preview payload 冻结的 `ruleset_version` 与 table_rules 的版本之间没有任何等值约束。S2a/S4 调整规则集版本时，
  两者可能静默分叉，导致 Preview/Submit 的陈旧判定依据不一致。
- 最小修正方向：由 bootstrap 注入，或者至少在 owner 测试中断言两处常量相等。
- 关闭标准：常量只有一个来源，或者有等值断言。

### S1-F8：handoff 与流程记录不准确

- 类型：已证实缺陷（记录）；是否阻塞：否（随本轮修订更正）
- 事实：
  - §8.1 要求每个子步至少一个提交。实际上 S1.3–S1.4 合在 `a5a62e58d3`（标题带“WIP”），S1.5–S1.6 合在 `d42a740e7d`。
  - §3 要求把“只改导入路径的测试”清单写入 handoff，handoff 中没有。此外有 4 个测试桩为新的 port 方法
    `canonical_import_request_bytes` 做了适配，断言未变，但也应列出。
  - handoff §3 的预算表只列了新建文件，没有逐项覆盖 §3 的必改路径。
  - §6.3 记录的 backend/worker 镜像是 `deploy-backend:latest 6610f2c6b7f0` 与 `deploy-worker:latest 9e1672eca5e4`。但 compose
    旅程实际使用的是 `gateway-p5-closure-s1-gate` 项目自建的镜像 `58105c10…` 与 `2298cf4f…`（见
    `tests/support/.last_compose_gate_provenance.json`）。两类镜像的最后一层都创建于 2026-09-27T09:35:07Z，即 `7de23ed349`
    之后；`7de23ed349` 与实现 HEAD 在 `vnext/` 下没有差异，因此内容等价，但记录与实际使用的镜像不一致，并且 backend 镜像
    没有 revision/source-tree 标签。
  - handoff 引用的 `/tmp/s1-backend-compose.log` 在 handoff 提交之后（21:38）被另一次运行覆盖，现在的内容是
    “6 failed, 3 passed”，失败全部是端口 8000 冲突。它已不能作为 9/9 的证据。
- 最小修正方向：更正子步与提交的对照；补齐测试清单与预算逐项表；记录 compose 实际使用的镜像 ID 与 provenance；
  日志放到不会被覆盖的路径。
- 关闭标准：handoff 与仓库、镜像事实一致。

### S1-F9：本轮新增的重复与放宽（非阻塞清理）

- 类型：非阻塞建议；是否阻塞：否
- 事实：
  - `build_payload_decoder_registry` 在 `application/payloads.py:118` 与 `application/job_definitions.py:170` 各有一份。
    payloads 中那份，以及 `decode_job_payload` 的类型检查，从 `type(...) is JobDefinition` 放宽成了鸭子类型
    （`hasattr(definition, 'key')`）。
  - `http/dependencies.py:43` 的 `_FailClosedInternalBearerPort` 复制了 `http/auth.py` 的 `FailClosedInternalBearerPort`
    （行为一致，已核对）。
  - `application/submission/artifact_release.py` 复制了 `submit_jobs._successor_step_id`；这是 checkpoint 保护的 owner id
    推导，两份一旦分叉，会导致保护释放不到位。
  - `SQLiteBaselineHeadRead.get_current_head`（`infrastructure/control_db/sqlite_baseline.py:186`）绕开了 UoW，BEGIN 阶段的
    busy 错误不再映射为 `StoreBusy`。
- 最小修正方向：每项只保留一个定义；恢复严格的类型检查；busy 映射与 UoW 保持一致。

## 3. 验收核对

| 验收项（执行计划 §2 S1 / kickoff / §8.4） | 结果 | 证据 |
| --- | --- | --- |
| kickoff：普查记录与 DC12/DC15 决议 | 不满足 | S1-F6 |
| 违例基线只剩 http_arrow×2 与 `repository_import_artifact` | 满足 | 审核者运行 `import_rules`，输出与 handoff §4 一致 |
| 运行时环基线为空 | 满足 | 同上（`RUNTIME_CYCLE_BASELINE = ()`） |
| 不可达基线只剩列出的 10 项 | 形式满足，实质不满足 | 依赖生产 shim；去掉后为 14（S1-F4） |
| 改名条目给出理由并登记 Phase 6 延期；`external_target_sync` 登记延期 | 不满足 | S1-F5 |
| DC26 精确放行 `capability:canonical_row_hash → ext:compute`，只对该 owner 生效 | 满足 | `tests/support/import_rules.py:84,316-318`；`IMPORT_RULE_SHAPES` 新增一条；`canonical_row_hash/contracts.py` 不导入 compute。建议补一条其他 capability → `ext:compute` 仍违规的反例 |
| 行为不变：golden、业务 digest、checkpoint 载荷、HTTP DTO | 不满足 | FAILED 终态证据字节（S1-F1）；OpenAPI 4 处（S1-F2）。请求证据字节、SUCCEEDED 证据、pair 流水线、`nodes_json`、comparison 行编码经核对等价 |
| 受影响测试只改导入路径，不改断言；死代码测试随模块删除 | 满足 | backend 2705 → 2674，差值 31 = 删除的 28 个函数 + 3 个参数化展开；剩余测试改动只涉及导入、patch 路径与测试桩适配 |
| backend unit/integration/serial 全绿；五包 ruff/mypy | 满足（见 §4 的环境说明） | 五包 ruff/mypy 通过；backend 2671 passed，另 3 个 compose 用例因外部并发进程占用端口 8000 失败，隔离重跑 3 passed（168.7 s）；合计 backend 2674 个用例全部通过 |
| 阶段末重建 current HEAD 镜像并运行既有 compose 旅程，结果与 5E exit 一致 | 基本满足，记录有误 | RS 镜像 `f4957f1a…` 创建于实现 HEAD 之后，label 的 uv-lock SHA 与 handoff 一致；RS compose 8 个用例在审核者的串行批次中通过；backend 镜像内容与实现 HEAD 等价，但记录的镜像不是旅程实际使用的（S1-F8） |
| synthetic/external effect 桩移出生产包，worker 测试改为测试侧注入 | 满足 | `src/` 中已无引用；`build_worker_runtime(external_effect_recovery=...)`；生产只有 submit 是 EXTERNAL_EFFECT 且总是传入 `submit_recovery`，生产行为不变。测试注入对象由 `polling_stub` 改为包装它的 `recording_stub`，断言未变，handoff §5 已说明 |
| §8.4 S1.4：`build_worker_runtime` 保留 `read_uow_factory`、`now_factory` | 满足 | `bootstrap/operation_worker.py:259-260` |
| §3 S1 预算：A1、A2、A3、A5、A6、A9、N-http-composition、N-http-bypass、N-infra-usecase、N-operations-private、N-cycles | 基本满足 | A2 为逐行移动；A3 下沉到 `artifact_release`；A5 使 `artifacts` 不再导入 domain；HTTP 不再导入 capability、wire 类型或 infrastructure。例外见 S1-F1、F7、F9 |
| §3 S1 预算：A7、Preview/History 受理、UoW 枢纽、job step plumbing | 不满足 | S1-F3、S1-F4 |
| merge `218c211240` 只含 §8 文档，无实现冲突 | 满足 | `git diff 218c211240 1caf2ffc26 -- <execution-plan>` 为空；merge 只引入该文档 |
| 分支末端只比实现 HEAD 多 handoff | 满足 | `git diff 1caf2ffc26 fa9dd6392c` 只改 handoff；handoff 中的 `candidate_head` 是 `7b0db60b44`（文件无法记录包含自己的提交） |
| `uv.lock` 未改 | 满足 | diff 不含 lock；运行后 `git diff --exit-code HEAD -- 'vnext/*/uv.lock'` 干净 |
| 普查脚本不进入生产包 | 满足 | `vnext/backend/benchmarks/` 不在 Dockerfile 的 COPY 中 |
| 设计 §14 停止条件 | 未触发，但无法确认 | 第 2 项取决于普查结果；普查没有产出有效的类型事实（S1-F6） |

## 4. 实际执行的检查

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 五包静态 | `cd vnext/<p> && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy`（5 包） | 全部通过（backend mypy 459 个文件，repository_service 198 个） |
| 导入边界 | `cd vnext/backend && ../scripts/uv-consume.sh -C . run python -m tests.support.import_rules` | 3 / 0 / 10，与 handoff 一致 |
| 权威全量 | `GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`（worktree 干净，`legacy` 为指向主工作区的 symlink） | shared_kernel 242、repository_contracts 152、repository_client 154 通过；backend 2671 passed、3 failed；RS 并行 1678 passed、1 skipped；RS 串行 205 passed（含 RS compose 8）；runner exit 1，原因只有这 3 个失败。见下方说明 |
| backend compose 隔离重跑 | `cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest -q tests/test_archive_compose_e2e.py::test_compose_dual_actor_archive_journey_restart_and_zero_repository_effect tests/test_backend_http_container_gate.py` | 3 passed（168.7 s），exit 0 |
| 锁文件漂移 | `git diff --exit-code HEAD -- 'vnext/*/uv.lock'`；`git status --porcelain` | 无漂移；工作区保持干净 |
| shim 反事实 | 在 scratch 副本中删除 `_ensure_composite_signal_production_anchor` 后运行 `import_rules` | 不可达 14 项（S1-F4） |
| OpenAPI 对比 | 分别用 base 与 HEAD 的 `src` 经 `create_workspace_http_environment` 生成 `/openapi.json` 并 diff | 仅 4 处 `minLength`/`maxLength` 缺失（S1-F2） |
| 终态证据对比 | scratch 脚本用 base 与 HEAD 的序列化与解码处理同一个 `VersionedOperation` | FAILED 证据字节不同；3 类非法证据的判定不同（S1-F1） |
| 等价移动核对 | 逐行比对 `standard.py` → `row_encoding.py`、`compare_jobs`/`preview_jobs` → `pair_pipeline.py`、`compare_bindings` → `history/contracts.py`、`upload_admission` | 等价 |
| 用例计数 | 统计删除的测试函数与参数化用例 | 31，与 2705 − 2674 一致 |
| 镜像 provenance | `docker image inspect`；`tests/support/.last_compose_gate_provenance.json` | 见 §3 与 S1-F8 |

**全量运行的环境说明**：审核者的全量运行期间，另有一个不是审核者启动的 backend compose gate 进程（`pytest -q -m 'integration and serial' …`，
compose 项目 `gateway-p5-closure-s1-gate`，来自 Cursor 会话，cwd 为本 worktree）在同一 worktree 中运行。backend 的 3 个失败
全部是 `port 8000 is already published by non-gate containers: gateway-p5-closure-s1-gate-backend-1`，与代码无关。所以在该进程
结束、确认没有残留容器之后，审核者单独重跑了这 3 个用例（上表）。那个外部进程也覆盖了 handoff 引用的 `/tmp/s1-backend-compose.log`。
审核者本人在测试期间没有写入 worktree；harness 自己会写入被 gitignore 的 provenance 文件。

## 5. 验证限制与剩余前置

- 真实数据：按执行环境的权限限制，审核者没有读取 `$GATEWAY_REAL_DUMP_ROOT` 下的普查产出，也没有读取普查脚本的内部实现，
  因此没有独立复核 S1-F6 所述解析失败的原因。S1-F6 的判断只依据 handoff 本身的记录与执行计划 §2 的要求。修订时由实现侧
  重跑普查并补齐记录，复审者核对 handoff。
- backend 的 9 个 compose 用例（handoff §6.4 的文件集，`--collect-only` 确认为 9 个）都在 backend 默认批次中：6 个在全量运行中通过，
  另 3 个在全量运行中因外部端口冲突失败、隔离重跑后通过。这些用例由 harness 以 current HEAD 构建的镜像运行；RS compose 8 个在
  串行批次中通过。审核者没有另外执行 `build-repository-service-image.sh` 与 `docker compose build`。backend 镜像与实现 HEAD 内容
  等价的判断，依据的是创建时间与 `vnext/` 无差异（S1-F8）。
- 5E exit 的 compose 结果只按“同一组旅程全部通过”对照，没有逐项比对业务 digest。S1 声称“结果与 5E exit 一致”的证据，同样是
  旅程通过加 golden 测试通过。
- 进入复审的前置：关闭 S1-F1 至 S1-F6，并随修订更正 S1-F8。S1-F7 可以随本轮处理，最迟在 S2a 修改规则集版本之前。
  修订若改动 bootstrap/composition 或受理路径，须按 §6 在新的实现 HEAD 上重建镜像并运行 compose 旅程，记录旅程实际使用的镜像 ID。
- 本报告只审 `218c211240..fa9dd6392c` 的差异，没有复审 base 已有的内容。
