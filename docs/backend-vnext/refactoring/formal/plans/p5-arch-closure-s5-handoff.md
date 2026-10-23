# P5 架构收口 S5 handoff

pass_recommended: yes

建议 S5 验收通过：S5.1–S5.4、V 全量权威 runner、五包静态检查、fresh RS 镜像、t1–t4 真实旅程、V 上 DC32 capability 全量重测与 V→H carried 均有证据。H 的 carried 复算与 final log 在 §7；本文证据没有触发执行计划 §14 停止条件。此建议等待独立复审；在 S5 审核通过前不做 P5 exit。P5 exit 清理依 G10 另行安排。

## 1. 区间、提交与环境

| 项 | 值 |
| --- | --- |
| `range_start` | `p5-s4-exit`，`5634dc6f9b` |
| kickoff base | `ebf46098a3` |
| 实现 HEAD | `55a8b810249649b403339d406cd2b5744feb7863` |
| 门禁提交 V | `55a8b810249649b403339d406cd2b5744feb7863` |
| 候选 H | 含本文的最终 handoff-only commit；完整 SHA 由复审方填写并与最终 CT108 取证日志核对。commit 不能包含自己的 SHA。 |
| 分支 | `p5-s5` |

开发主机 worktree 为 `/home/dev/gdds-p5-s5`，`legacy` 符号链接指向 `/home/dev/gateway-data-management-system/legacy`。测试、权威 runner、镜像门禁、真实数据、测量和 carried 都在 `ct108-gw-dms:/home/dev/gdds-p5-s5` 完成；开始前 `ssh -o BatchMode=yes ct108-gw-dms 'echo OK'` 返回 `OK`。worktree 通过 git bundle、`scp` 到 CT108 日志目录，再由 CT108 `git fetch` 同步；未经过 GitHub。没有合并或 rebase main，没有推送或打 tag。

所有 CT108 测试、runner、测量与 carried 使用 `/home/dev/gdds-p5-closure-s1-gate-logs/s5/s5-env.sh` 启动，变量如下：

| 变量 | 值 |
| --- | --- |
| `PATH` | `/home/dev/.cargo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin` |
| `HOME` | `/root` |
| `LC_ALL` | `C.UTF-8` |
| `TMPDIR` | `/home/dev/gdds-p5-closure-s1-gate-logs/g12-default-tmp` |
| `CARGO_LCHAIN` | 未设置 |
| `UV_CACHE_DIR` | 未设置 |
| `GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT` | `1` |
| `GATEWAY_TEST_PACKAGES` | 未设置；全量 runner 执行全部五包 |
| `GATEWAY_TEST_WORKERS` | 全量 runner 为 `48` |
| t1 调试探针开关 | 调试时开启；V 真实数据证据时关闭（默认 `false`） |

V 的包提交按 S5 子步推进：

| 子步 | 主要提交 | 结果 |
| --- | --- | --- |
| S5.1 S4-F2 | `9a1ae70a4f`, `3b1ee64bfa`, `66e631ce7a` | Submit poll/session 上限显式化，去除 Submit checkpoint 无用计时状态和无生产调用方的累计预算 helper；F1 再将 R5 通用上限统一为三个恢复会话。 |
| S5.2 不可达基线 | `f37460dd4b` | 将两组不可达模块登记到 owning 设计；基线注释引用登记。 |
| S5.3 project identity 拓扑 | `ba4ee7a5e6` | 从 Snapshot Materialization facade 导入 `SqlSetValue`，移除 project_identity 的 `table_access` allowlist。 |
| S5.3 冻结 Submit prepare | `9f1df26914`, `227255a562`, `61d9387f05`, `882638e961` | Prepare 只使用 T1 冻结产物；保留冻结绑定及 A/B ruleset 回归。 |
| DC32 依赖与 capability 测量 | `0c967542bb`, `f1ef573a6f`, `004bea5cdf`, `a21d933ce7`, `d7466b0064`, `75d98a2c49`, `a2cfe03c21` | 增加唯一获准的 dev-only BLAKE3、测量模块与用例；完成 DC32 capability 数据。 |
| 恢复最终门禁与真实数据探针 | `241ee66d94`, `a92f455afb`, `d76cff8018`, `abb7968bbe`, `b79844ddc2` | 修测试 seam、Repository operation ID 与 import 时间读取，增加 t1 调试探针，再修 CLI 测试期望；最后一项只改测试。 |

## 2. S5.1：S4-F2 修复与 S5-F1 定向修订

生产调用方是 `operations/recovery.py::finalize_handler_recovery` 和
`application/submit_jobs.py::await_import_result` 的 poll timeout。S5.1 之前，通用 operation recovery
路径在 S5 之前就传入 `reconcile_elapsed_seconds=0.0`；因此累计 60 秒分支一直没有生产调用方。Submit timeout
使用单次 poll 上限并按恢复会话数决定重试，本次前的实现显式传入 `None` 与
`RECOVERY_SESSIONS_ONLY`。

本次按 owner 在 main `b5d2961d33` 的授权移除 `reconcile_budget_exhausted`、`ReconcileBudgetMode`、
累计耗时分支，以及 `transition_for_outcome` 的 `reconcile_elapsed_seconds` / `reconcile_budget_mode`
参数；同时删除两个生产调用点的对应实参、`__all__` 导出和只证明累计分支的测试/合成 fixture。
通用状态转换仍按最多三个恢复会话决定重试或人工恢复；Submit 每个 Repository poll 继续以
`SUBMIT_IMPORT_POLL_DEADLINE_SECONDS = RECONCILE_SESSION_BUDGET_SECONDS`（60 秒）为单次会话上限。
不修改 Contract。

回归保留 `tests/test_submit_job_effect.py::test_await_import_result_timeout_uses_bounded_submit_poll_sessions`
（会话 1/2 → `RETRY_WAIT`，会话 3 → `MANUAL_RECOVERY_REQUIRED`）、
`test_await_import_result_timeout_retries_until_repository_operation_is_terminal`，以及 operation 通用
状态转换/恢复用例。累计分支五个目标符号在生产代码和测试中的递归搜索结果为 0；CT108 未安装 `rg`，实际等价搜索命令和结果见 §6。

按 owner 授权同步修订 R5 设计 §6 和 5B §13.1 的预算规则，文件为：

- `docs/backend-vnext/refactoring/formal/plans/p4-r5-retry-takeover-effect-recovery-design.md`
- `docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-design.md`

没有修改 Contract 文本或其他 Contract 条款。

## 3. S5.2：不可达基线

`import_rules` 在 S4 结束为 `0 / 0 / 6`，S5 V 仍为 `0 / 0 / 6`（依次为 import violation、runtime cycle、unreachable module）；没有增加基线条目，也没有未预期的不可达模块。

仅保留两组经 owning 设计登记的延期项，代码注释指向 `p5-arch-closure-design.md` §9：

| 组 | 模块数 | Owner、理由、重开条件 |
| --- | ---: | --- |
| canonical row hash（A6 / DC26） | 3 | Backend vNext Architecture。模块已在目标 capability 目录，但当前无生产 journey consumer，保留作 Phase 6 Rust 覆盖和性能输入；Phase 6 选为实际 workload 或出现新的生产 consumer 时重开。 |
| `external_target_sync`（A9） | 3 | Mutation Planning。当前没有生产 external-target journey，不在 P5 引入未确认 consumer 与流程；owner 接受 external-target Contract 且有明确生产 journey consumer 时重开。 |

登记位于 `p5-arch-closure-design.md` §9；基线注释在 `vnext/backend/tests/architecture_baseline.py`。V 的 `import_rules` 为 `0 / 0 / 6`；独立计数日志为 `s5-import-rules-55a8b81024.log`。

## 4. S5.3：文档与实现逐项核对

依设计 §11 的语义 owner/需修订文档逐行核对 S0 接受并入的 Contract、设计文本与最终实现。表中“对齐”包括实现已按 owner 决议修正；没有剩余偏差，也没有改写 Contract 文本。

| 设计 §11 语义 / 文档条款 | 实现位置与核对证据 | 结论 |
| --- | --- | --- |
| 规范快照、schema/状态摘要、Repository 单遍物化、标量解码；P3-R3 hidden summary 由 ADR 0019 取代 | `capabilities/snapshot_materialization/`；`test_canonical_snapshot_identity.py`、`test_canonical_state_identity.py`、`test_repository_ref_materialization_protocol.py`。摘要权威、单遍读取与失败语义符合 owning Contract。 | 对齐 |
| 规范投影、manifest、import schema 打包、存储词表/约束；Canonical Storage §2/§4、Contract Taxonomy §4.4/§4.6/§5/§13 | `capabilities/storage_projection/`；`test_storage_projection_core.py`、`test_storage_projection_publication.py`、`test_repository_import_artifact_package.py`。schema、manifest 与包 golden 通过。 | 对齐 |
| import DML；无额外文档修订 | `capabilities/mutation_planning/`；`test_mutation_planning_import_replay.py`、`test_submit_import_builder.py`。DML 由冻结规范表与 manifest 事实生成。 | 对齐 |
| Submit import 包组装/发布；P5 §2A.4 包根 adapter 处置 | `application/submission/` port 与 `infrastructure/repository_write/import_publication.py`；`test_submit_import_builder.py`、`test_submit_recovery.py`。冻结输入与包输出绑定一致。 | 对齐 |
| `ComparisonRuleView` 与列处置；P3-R4 §4.2 的 ADR 0018 标注，ADR 0018、Canonical Storage §2 | `capabilities/table_rules/` 与 `capabilities/comparison/`；`test_table_rules_comparison_view.py`、`test_comparison_rule_roles.py`、`test_comparison_planning.py`。按运行期规则比较规范域状态。 | 对齐 |
| Comparison 输入、替换模式、Canonical Storage §7；P3-R5 与 P5 §2A.2 | `capabilities/comparison/`、`application/pair_pipeline.py`、Preview/History job；`test_comparison_canonical_domain.py`、`test_comparison_replacement.py`、Compose 与真实数据链路。 | 对齐 |
| 规则激活；Ruleset Activation §1/§5 与 P5 §4.8/§4.9 | Preview/History 在恢复时按冻结 digest 校验；Submit T1 后只依赖冻结 manifest 与表 artifact。Prepare 不读取 runtime ruleset，不调用 storage projection 重新投影；包 schema SQL、DML、digest 与原 golden 逐字节一致。详见本表后的 owner 决议记录。 | owner 决议后已修复 |
| 项目身份；Contract Taxonomy §4.4/§4.6/§5/§13 | `capabilities/project_identity/_rule.py` 从 `snapshot_materialization` facade 导入 `SqlSetValue`；`test_architecture.py` project_identity allowlist 只保留 `snapshot_materialization`。S4 引入了错误的 `table_access` 拓扑，提交 `3d3ab764ba`；按 owner 决议在 `ba4ee7a5e6` 修正。 | owner 决议后已修复；S4 引入 |
| Preview/Submit/Archive 身份确认与持久事实；Business Lifecycle 3.1.0 | 对应 Application 的 Preview、Submit、Review、Archive 事务与 DTO；`test_submit_transactions.py`、`test_review_domain.py`、`test_archive_transactions.py`，并由全量 Compose 与真实数据验证。 | 对齐 |
| History integrity/read inconsistency；5E §6.6、ADR 0016、Operation Lifecycle §4 | `application/history/` 与 repository read adapters；History 按 owner 区分稳定读取失败和 authority mismatch；`test_history_compare_jobs.py`、`test_repository_ref_materialization_protocol.py`。 | 对齐 |
| 目标 DAG；Architecture §7.1/§7.2/§9.1/§10/§13 | `tests/support/import_rules.py`、`test_architecture.py` 与 `architecture_baseline.py`。无新增 import violation/cycle；6 个 unreachable 均有 owning 登记。 | 对齐 |

**偏差 1（S4 引入的拓扑偏差）。** Owner 决议记录于 main `e0054eceec`，没有合并 main。按决议将 `SqlSetValue` 改从 Snapshot Materialization 公开 facade 导入并移除 `table_access` allowlist；没有 Contract 文本修改。focused architecture、project_identity 测试与 `import_rules` 均通过，计数仍为 `0 / 0 / 6`。

**偏差 2（Submit frozen ruleset）。** Owner 决议记录于 main `d876aea9fb`，采用已接受 Contract 与 DC11 修实现，不改 Ruleset Activation §1/§5 和 P5 §4.8/§4.9。偏差由 `90e7f90759` 引入（`git log --all --follow -S 'def _resolve_ruleset' -- vnext/backend/src/gateway_backend/infrastructure/repository_write/import_publication.py`）；`9f1df26914` 实施修复：T1 以后 prepare 不读取 runtime ruleset，也不再次投影；build input 中的运行期 ruleset id/version/digest 与 storage projection version 移除，由冻结 manifest 提供事实。schema（列、类型、可空性、有序键）与 DML 只从冻结规范 artifact descriptor/row 及 manifest 逐表事实生成；删除 `_resolve_ruleset` 与 runtime ruleset mismatch 拒绝分支。闭包与 manifest ref/digest、table artifact raw_sha256/snapshot_digest、source_artifact_digest、expected parent CAS 绑定仍会校验，不一致仍稳定失败。`test_submit_prepare_recovers_from_frozen_t1_artifacts_after_ruleset_activation` 与 `test_submit_prepare_reuses_t1_frozen_products_after_ruleset_activation_changes` 证明 A 在 T1 冻结、prepare 前切换至 digest 不同的 B 后仍可恢复；同输入产出的 schema SQL、DML 与包 digest 与旧 golden 逐字节一致。没有修改 storage_projection 或 snapshot_materialization 的公开 API。Prepare 少做两次投影；DC32 测量以最终 V 路径为准，没有伪造旧路径前后差值。

## 5. V 文件范围与路径预算

按最终门禁条件，比较真实数据来源 V `b79844ddc2304a23a3e6fe386f40aed671c5047b` 与新 V `55a8b810249649b403339d406cd2b5744feb7863`：`git diff --name-only b79844ddc2..55a8b81024` 恰为下表 13 个文件。生产代码只涉及 `operations/recovery.py` 与 `application/submit_jobs.py` 中删除累计预算分支及对应参数；其余都是 tests、benchmarks 与文档。没有修改 Contract、RS 公开接口或其他生产模块。

| 文件 | 类别 | 该文件在 `b79844ddc2..V` 中的内容 |
| --- | --- | --- |
| `vnext/backend/src/gateway_backend/operations/recovery.py` | 生产 | 删除累计 elapsed-time 分支、helper/枚举及转换参数，统一到恢复会话预算。 |
| `vnext/backend/src/gateway_backend/application/submit_jobs.py` | 生产 | 删除 await poll timeout 的累计预算相关实参。 |
| `vnext/backend/tests/support/synthetic_jobs.py` | 测试支持 | 删除只服务于累计预算断言的合成时间状态。 |
| `vnext/backend/tests/test_operation_effect_reconcile.py` | 测试 | 删除累计分支证明；最后的 V 修复也移除随该分支不再使用的 checkpoint envelope 读取及导入。 |
| `vnext/backend/tests/test_operation_job_recovery.py` | 测试 | 更新通用恢复会话状态转换回归。 |
| `vnext/backend/tests/test_operation_recovery_policy.py` | 测试 | 删除累计预算策略用例并保持通用恢复策略覆盖。 |
| `vnext/backend/tests/test_operation_state.py` | 测试 | 更新通用状态转换表，不再传累计预算参数。 |
| `vnext/backend/tests/test_real_dump_dc32_measurement.py` | 测试 | 覆盖 DC32 阶段父子关系、测量状态和外层 CPU 记录。 |
| `vnext/backend/benchmarks/s5_dc32_capability_measurement.py` | benchmark | 修正阶段命名/父子关系、补外层 CPU 与已执行阶段的测量，并区分逐表与 package 成本。 |
| `docs/backend-vnext/refactoring/formal/plans/p4-r5-retry-takeover-effect-recovery-design.md` | 文档 | 按 owner 授权修订 R5 §6。 |
| `docs/backend-vnext/refactoring/formal/plans/p5-5b-submit-finalize-design.md` | 文档 | 同步修订 5B §13.1。 |
| `docs/backend-vnext/refactoring/formal/plans/p5-arch-closure-s5-independent-review.md` | 初审报告 | 这是 `ac679c3961` 初审报告提交新增的原报告；F1–F3 修订提交没有修改它。 |
| `docs/backend-vnext/refactoring/formal/plans/p5-arch-closure-s5-handoff.md` | handoff | 更新 S5 证据、修正后的 DC32/真实链路数字、文件范围与定向修订记录。 |

以上文件逐项闭合最终 diff 边界；相对 `b79844ddc2` 没有其他改动。初审报告在整个定向修订中保持原样。

## 6. 定向修订、失败、修正与符号搜索

### S5-F1：R5 累计耗时预算删除

生产调用面只有 `operations/recovery.py::finalize_handler_recovery` 与 `application/submit_jobs.py::await_import_result` 的 poll timeout。S5 前通用 operation recovery 路径已传 `reconcile_elapsed_seconds=0.0`，累计时间分支没有生产调用方。按 main `b5d2961d33` 治理修订计划 §3 第 12 项授权，本次删除 `reconcile_budget_exhausted`、`ReconcileBudgetMode`、累计耗时分支、`transition_for_outcome` 的累计 elapsed/mode 参数、两个生产调用方的相应实参和 `__all__` 导出，并删除累计分支专用测试与合成 fixture。Submit 的单次 session poll 上限仍由 `SUBMIT_IMPORT_POLL_DEADLINE_SECONDS = RECONCILE_SESSION_BUDGET_SECONDS` 提供，3 个恢复会话用尽后进入 `MANUAL_RECOVERY_REQUIRED`；通用 operation 语义不变，不修改 Contract。

回归：Submit session 1、2 timeout → `RETRY_WAIT`，session 3 timeout → `MANUAL_RECOVERY_REQUIRED`；Repository operation 已终态时按其结果完成；通用恢复状态转换保留。最终 V 的五包静态与 focused/backend unit 日志见 §7。

### S5-F2：DC32 capability 测量修正

V `55a8b81024` 上从头运行完整 t1–t4 v1/v2 capability 场景，不使用 `a2cfe03c21` 的旧计时值。首个重跑命令将 `--real-dump-root` 指向仅含 runs 输出的目录，读取 `datasets.json` 时以 exit 1 结束；日志为 `s5-dc32-capability-55a8b81024.log`。没有启动场景、写测量 JSON 或创建 scratch。`s5-dc32-preflight-55a8b81024-r2.log` 记录失败文件/目录均不存在、preflight 通过，并将新命令与成功的 `s5-dc32-capability-v1.log` 的 `command=` 逐项对照；成功重跑命令除输出文件名外保持同一参数结构；将 real-dump root 改为其数据集索引所在的根，省略 `--dataset`，并使用 S5 scratch parent。正确运行的日志为 `s5-dc32-capability-55a8b81024-r2.log`，exit 0；检查记录为 `s5-dc32-verify-55a8b81024-r2.log`。结果 18 个场景、17,435 个逐表 stage 记录；v1 也是 18 场景，新计数增加 2,496 是因为 Submit 的 624 张表各增加 4 条明确 stage 记录，不是场景遗漏或拼接旧数据。JSON mode 600、runs 目录 700，scratch 已清理。§8/§10/§11 全部基于这个新 JSON。

Submit 内部 `render_import_mutation_dml`、`plan_storage_mutation`、`render_change_set_replay` 使用三个不同阶段名并标明父子关系；table-level 无法实测的 planning/render 标记为 package 共享成本。父段包含两个 child，汇总不把父段与 child 相加。adapter 外层 build/publish/readback 单独计 wall 与 thread CPU，不能与内部阶段相加。Submit schema SQL 与 artifact write 按 package 记录；pair artifact write 与 business materialization 有实际计时；逐表记录显式使用“实测 / 共享成本（按包计） / 不适用”，未测值为 null 而不是 0。没有为测量修改生产代码。

### S5-F3：owner 决议与真实数据范围

§4 偏差 1 的决议来源为 main `e0054eceec`，偏差 2 的决议来源为 main `d876aea9fb`；偏差 2 原引入提交为 `90e7f90759`（`git log -S "def _resolve_ruleset"`）。最后一次 owner 允许的真实数据沿用范围为 `f84b930d4a` → `398204b4c0` → `0b8c2bac41`，其中 t1–t3 沿用 `a92f455afb`。实际在 V `b79844ddc2` 上重跑 t1–t4 全量，是因为 `--dc32-output` 不接受 `--tier`，不是 owner 选择了全量重跑。V 真实数据证据见 §9；它与本次新 V 的 capability 全场景测量是不同工作。

### 7ff34be684 ruff 停止后的修复

`7ff34be684` 的五包静态检查停在 backend ruff：`test_operation_effect_reconcile.py` 中 `envelope` 赋值及 `load_checkpoint_envelope` 导入只为已删除的累计预算断言服务。新提交 `55a8b810249649b403339d406cd2b5744feb7863` 只改该测试文件，删除赋值与导入；未 amend 或改写 `7ff34be684`。在新 V 上从头通过五包 ruff/mypy、全部指定 focused 文件、`test_submit_recovery.py -n 0` 和 backend `pytest -m unit`；结果与日志见 §7。

### 全量 runner umask 失败、清理与重跑

第一次 V 全量 runner 的实际 runner 命令为 `GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`，没有设置 `GATEWAY_TEST_PACKAGES`。`s5-full-runner-55a8b81024.log` 的 `command=` 记录了该命令，但没有记录 umask；只读排查确认启动 shell umask 为 `0077`。测试的 `write_text` 生成 root 属主、mode 600 的 bearer-token；RS entrypoint 降权到非 root 后无法读取，Repository Service 日志为 `PermissionError`。因而两个 Compose 用例失败并被停止，runner exit 143；该次不作为任何沿用来源。`umask 077` 没写在 runner 的 `command=` 文本内；日志目录的 carried helper 采用该 umask 习惯，失败进程的 token 权限与排查结果确认其启动时实际 umask 为 0077。

`s5-cleanup-55a8b81024.log` 记录只按两个指定 Compose project labels 清理：指定的 3 个容器、2 个网络、4 个卷在清理后均无匹配项；没有触碰镜像。之后 preflight 重新确认无 Dolt、Compose 容器/栈、8000 listener，worktree clean，RS label 与 V identity 相同。重跑先设置 `umask 022`，并用 `s5-env.sh` 的环境变量启动 `GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`，没有 package filter。runner log 开头记录 `umask=0022`；全量五包 exit 0。只有 `s5-full-runner-55a8b81024-r2.log` 是 V runner 通过证据。

### 累计预算符号搜索

CT108 没有安装 `rg`；对同一生产与测试目录执行等价递归搜索，结果 0 命中：

```text
grep -R -n -E 'reconcile_budget_exhausted|ReconcileBudgetMode|CUMULATIVE_ELAPSED_TIME|RECOVERY_SESSIONS_ONLY|reconcile_elapsed_seconds' vnext/backend/src vnext/backend/tests
NO_MATCHES
runner_exit_code=0
```

命令与结果在 `s5-r5-symbol-search-55a8b81024.log`。

## 7. 五包检查、V 权威 runner 与 carried

### Focused 与静态检查

在 V 的 clean CT108 worktree 中，`s5-static-55a8b81024.log` 记录五包 ruff 与 mypy 全部 exit 0；`s5-import-rules-55a8b81024.log` 为 0 import violation / 0 runtime cycle / 6 unreachable。`s5-focused-55a8b81024.log` 完整运行 `test_operation_effect_reconcile.py`、`test_operation_job_recovery.py`、`test_operation_recovery_policy.py`、`test_operation_state.py`、`test_submit_job_effect.py`、`test_submit_job_payload.py`、`test_submit_recovery.py -n 0`、`test_real_dump_dc32_measurement.py`、`test_real_dump_journey.py`：430 passed。其后 backend `pytest -m unit`：2,757 passed、178 deselected。上述日志均记录 V 起始 HEAD 与 clean worktree。`7ff34be684` 的 ruff 失败日志没有作为通过结果；V 全套从头执行。

### Preflight、fresh RS 镜像与 runner

全量 runner r2 前 preflight 和 postflight 均通过：无 Dolt 进程、Compose 栈或容器，8000 端口空闲，worktree clean，HEAD 为 V。日志为 `s5-preflight-55a8b81024-r2.log` 与 `s5-postflight-55a8b81024-r2.log`。在 V 上以 `build-repository-service-image.sh` fresh 重建 RS 镜像，构建与独立 identity 校验见 `s5-build-rs-55a8b81024.log`；postflight RS image ID 为 `sha256:a1d2e14c8574ea10557c3d16a6643d17ae4c6dd440499379442edfab052f3fec`。V identity 的 `build_input_revision=ed70ca1be262653bb49267940e73e7edd09a2267`、`source_tree_sha256=sha256:a3e56c4d90e67ba80b632599ead9dca8fc65d13d2193ad0f42472d9a9f68be3a` 与镜像相应 labels 一致。client e2e 镜像由 runner 按 candidate label 自动重建；没有手工 `docker rmi`、`docker tag` 或删除 `gateway-repository-client-e2e:local` / `-base:local`。

实际通过命令为 `GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`，没有设置 `GATEWAY_TEST_PACKAGES`。runner 在 clean V 上 exit 0，起止 HEAD 均为 V；通过日志只有 `s5-full-runner-55a8b81024-r2.log`。r1 exit 143 仅记录失败和环境原因，未沿用。

| 包 | S4 V `ed70ca1be2` | S5 V `55a8b81024` | 变化 |
| --- | --- | --- | --- |
| `shared_kernel` | 242 passed | 242 passed | 无 |
| `repository_contracts` | 152 passed | 152 passed | 无 |
| `repository_client` | 154 passed | 154 passed | 无 |
| `backend` | parallel 2901；serial 36 | parallel 2896；serial 39 | parallel -5、serial +3；F1 删除累计分支专用证明，其他 R5/session 回归通过 |
| `repository_service` | parallel 1724 passed + 1 skipped；serial 205 passed | parallel 1724 passed + 1 skipped；serial 205 passed | 无 |

唯一 skip 是 `tests/test_p2_r1_target_cgroup_smoke.py`，原因是仅在 delegated target container 运行；Compose journeys 0 skipped。V runner 的五包起始 manifest 从 `s5-full-runner-55a8b81024-r2.log` 提取：

| 包 | V runner 起始 manifest `total_digest` | V 状态 |
| --- | --- | --- |
| `shared_kernel` | `c50ed6636ebed5dc3c67c2c788a556e60bae3981d4213d5f96bf620f6f2b8ff9` | V 实际运行通过 |
| `repository_contracts` | `cf02462ed6d4e953501e9a97e2b7f9f7c0fa8275f8a1d8b16abe540cd26b4517` | V 实际运行通过 |
| `repository_client` | `a9a541548bb64db8e0cf1067c72c18a08600eab0ca4cd5046f5b1227cde46d92` | V 实际运行通过 |
| `backend` | `b1669d672d22612469ebb395695c83f8eefbaee64d65055f6e3352521bd05f6b` | V 实际运行通过 |
| `repository_service` | `d498559964fdb430d3b09000f33a544057c28dd69ed6ca7615426b57a4a4cf6e` | V 实际运行通过 |

### V→H carried

H 的 handoff-only diff 不触及五包闭包。最终在 V runner 的同一 CT108 worktree、umask 022、V runner 环境中重算 RS identity，与 RS image 的 build-input/source-tree labels 比较；从 r2 runner 日志提取 V 五包起始 manifests，逐包与 H manifests 执行 `test_input_closure.py compare`。结果、完整 H SHA、RS labels 和日志名将在最终 H 提交后记录；最终门禁要求五包均为“可沿用”，`changed_components=[]`。

## 8. DC32 capability 测量

owner 最后允许沿用的真实数据范围为 main `f84b930d4a` → `398204b4c0` → `0b8c2bac41`：t1–t3 使用 `a92f455afb` 证据，t4 在新 V 全量运行。实际在 V `b79844ddc2` 上重跑 t1–t4 全量，是因为 `real_dump_journey.py --dc32-output` 不接受 `--tier`；这不是 owner 的选择。真实数据运行见 §9。

与真实 journey 分开的 DC32 capability 测量在最终 V `55a8b810249649b403339d406cd2b5744feb7863` 上完整运行 18 个场景：9 个 materialize/project（t1–t4 的 v1/v2，加 t4 v1 repeat）、6 个 Preview pair（t1/t2/t3 v2、t4 v1、t4 v1 repeat、t4 v2）、2 个 t4 Submit prepare、1 个 t4 History。JSON 状态 `PASS`，head 为 V；日志 `s5-dc32-capability-55a8b81024-r2.log`、结果 `s5-dc32-capability-55a8b81024.json`，验证 `s5-dc32-verify-55a8b81024-r2.log`。输出 JSON mode 600、runs 目录 700、scratch 清理完成。成功 v1 也有 18 个场景；新逐表记录 17,435，比 v1 的 14,939 多 2,496，恰为 624 张 Submit 表各新增 4 个拆分/覆盖 stage 记录。v1 的 stage 时间没有拼接或用作本节数据。

下表每项为 `wall / thread CPU` 秒；每个 stage 都有独立名字。物化中 projected snapshot write 与 canonicalization manifest write 分开；Materialization ArtifactStore、Pair ArtifactStore 均记录实际写入时间。所有场景 stage 均以 package scope 记录：

| 场景 | stage wall / thread CPU 秒 |
| --- | --- |
| t1 v1 materialize | staging 0.008071/0.008075；SQL parse 2.394374/2.394107；XML parse 0.000094/0.000094；business materialization 3.563133/3.562557；projection/digest 3.589435/3.588758；projected snapshot write 3.096617/3.011072；manifest write 0.037356/0.037360；materialization ArtifactStore.put 0.005570/0.005457 |
| t1 v2 materialize | staging 0.007421/0.007423；SQL parse 2.394441/2.394042；XML parse 0.000078/0.000079；business materialization 3.556001/3.555529；projection/digest 3.594111/3.593544；projected snapshot write 3.072629/3.000257；manifest write 0.037371/0.037373；materialization ArtifactStore.put 0.005529/0.005441 |
| t2 v1 materialize | staging 0.076423/0.076391；SQL parse 31.142213/31.137435；XML parse 0.007713/0.007715；business materialization 48.563841/48.553376；projection/digest 57.549059/57.542086；projected snapshot write 41.705238/41.550465；manifest write 0.063135/0.063140；materialization ArtifactStore.put 0.017577/0.017382 |
| t2 v2 materialize | staging 0.072598/0.072602；SQL parse 30.285206/30.281270；XML parse 0.007627/0.007630；business materialization 47.644531/47.640177；projection/digest 55.493921/55.488237；projected snapshot write 40.021386/39.879514；manifest write 0.063231/0.063235；materialization ArtifactStore.put 0.017324/0.017115 |
| t3 v1 materialize | staging 0.254529/0.254511；SQL parse 92.675630/92.663145；XML parse 0.023317/0.023324；business materialization 144.467211/144.447574；projection/digest 126.885862/126.879195；projected snapshot write 92.137520/91.997775；manifest write 0.056151/0.056156；materialization ArtifactStore.put 0.037215/0.037009 |
| t3 v2 materialize | staging 0.262591/0.262592；SQL parse 93.440782/93.431425；XML parse 0.023908/0.023914；business materialization 145.645157/145.633652；projection/digest 129.146874/129.133695；projected snapshot write 94.414378/94.272309；manifest write 0.058038/0.058020；materialization ArtifactStore.put 0.037571/0.037357 |
| t4 v1 materialize | staging 0.391022/0.390992；SQL parse 140.497920/140.484810；XML parse 0.059615/0.059621；business materialization 211.540377/211.516414；projection/digest 218.976624/218.946315；projected snapshot write 153.333749/153.072172；manifest write 0.094926/0.094913；materialization ArtifactStore.put 0.061082/0.060727 |
| t4 v2 materialize | staging 0.403923/0.403822；SQL parse 140.951957/140.936321；XML parse 0.064723/0.064729；business materialization 212.939197/212.916260；projection/digest 220.055170/220.027995；projected snapshot write 155.168885/154.902928；manifest write 0.097938/0.097942；materialization ArtifactStore.put 0.060992/0.060618 |
| t1 v2 Preview | planning 0.042226/0.042233；comparison 0.087810/0.087812；risk 0.004239/0.004239；surface 0.098425/0.098432；pair ArtifactStore.put 0.000146/0.000142 |
| t2 v2 Preview | planning 0.091882/0.091890；comparison 34.998849/34.996224；risk 1.338913/1.338664；surface 0.197025/0.197030；pair ArtifactStore.put 0.005398/0.005285 |
| t3 v2 Preview | planning 0.075526/0.075533；comparison 72.536638/72.526344；risk 0.109778/0.109782；surface 0.162986/0.162991；pair ArtifactStore.put 0.002597/0.002552 |
| t4 v1 Preview | planning 0.133633/0.133641；comparison 148.361557/148.341328；risk 27.369189/27.366569；surface 0.330262/0.330225；pair ArtifactStore.put 0.060149/0.059485 |
| t4 v1 repeat materialize | staging 0.405965/0.405896；SQL parse 141.386808/141.372180；XML parse 0.061672/0.061677；business materialization 211.695735/211.674981；projection/digest 217.328916/217.309229；projected snapshot write 154.340563/154.081547；manifest write 0.093906/0.093911；materialization ArtifactStore.put 0.061193/0.060758 |
| t4 v1 repeat Preview | planning 0.140085/0.140092；comparison 40.550846/40.547723；risk 0.004829/0.004830；surface 0.256395/0.256398；pair ArtifactStore.put 0.000041/0.000037 |
| t4 v2 Preview | planning 0.139386/0.139393；comparison 39.164349/39.159499；risk 0.025881/0.025885；surface 0.266510/0.266513；pair ArtifactStore.put 0.001563/0.001530 |
| t4 v1 Submit prepare | snapshot build 69.060765/69.022034；schema SQL 0.002052/0.002054；plan (child) 230.808288/230.776276；replay (child) 7.140672/7.139179；DML parent (inclusive) 237.983897/237.950377；adapter outer 373.979684/373.753891；ArtifactStore.put (inside outer) 0.001438/0.001435 |
| t4 v2 Submit prepare | snapshot build 65.166574/65.102553；schema SQL 0.002075/0.002076；plan (child) 228.957770/228.936570；replay (child) 6.922427/6.921293；DML parent (inclusive) 235.915228/235.892878；adapter outer 369.455820/369.208861；ArtifactStore.put (inside outer) 0.001460/0.001458 |
| t4 History | planning 0.138984/0.138988；comparison 38.562149/38.559346；risk 0.024812/0.024813；surface 0.261837/0.261841；pair ArtifactStore.put 0.001672/0.001643 |

Submit 的逐表记录无法在不改生产代码的前提下拆出 planning/render 的逐表耗时，因此这些行标为 package 共享成本；实测 wall/CPU 在上表按包列出。`render_import_mutation_dml` 内部调用 `plan_storage_mutation` 和 `render_change_set_replay`；后两者是它的 child，父段是 inclusive，不能把父段和两个 child 相加。外层 adapter build/publish/readback 单独记录，包含内部 stages，不能与内部各段相加。ArtifactStore.put 单独列出但位于 outer 内，也不再加进 outer。各段关系和两种不重叠汇总如下：

| Submit | snapshot build | schema SQL | plan child | replay child | DML parent inclusive | parent exclusive | non-overlap mutation + frozen row read | adapter outer | ArtifactStore.put（outer 内） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| t4 v1 Submit prepare | 69.060765/69.022034 | 0.002052/0.002054 | 230.808288/230.776276 | 7.140672/7.139179 | 237.983897/237.950377 | 0.034937/0.034922 | 337.281378/337.172761 | 373.979684/373.753891 | 0.001438/0.001435 |
| t4 v2 Submit prepare | 65.166574/65.102553 | 0.002075/0.002076 | 228.957770/228.936570 | 6.922427/6.921293 | 235.915228/235.892878 | 0.035031/0.035015 | 334.757963/334.626365 | 369.455820/369.208861 | 0.001460/0.001458 |

`non-overlap mutation + frozen row read` 是 snapshot build + plan + replay + parent exclusive + per-table frozen artifact row read 的汇总；未把 parent inclusive 和 child 重复加入。schema SQL 与 artifact write 为共享成本（按包计），不并入这个 subtotal。submit frozen artifact row read 本身的逐表汇总见 §10。

### 基本操作吞吐

| 操作 | 新 V 实测 |
| --- | --- |
| 包解压 | 5,597,503 B → 80,337,841 B；415.458 MiB/s，wall 0.184414s / CPU 0.184419s。 |
| 现有 SQL parse | 79,446,967 B；0.539 MiB/s，wall 140.497920s / CPU 140.484810s。 |
| Arrow → Python | 246,794 rows、2 int64 列；36.546 MiB/s，wall 0.103058s / CPU 0.103033s。 |
| Arrow IPC | 写 3,949,322 B：2625.35 MiB/s，0.001435s；mmap read/scan 1339.667 MiB/s，0.002811s。 |
| hash throughput | compressed package SHA-256 1729.18 MiB/s、BLAKE3 5617.042 MiB/s；uncompressed SQL SHA-256 1732.8 MiB/s、BLAKE3 5166.846 MiB/s。BLAKE2b 与 existing digest 的全部结果保留在 JSON。 |
| Direct Dolt import/commit | 临时离线 repo，replay SQL 50,566,047 B；import 24.280177s wall / 24.162280s child CPU；commit 0.128057s / 0.174224s。 |

## 9. 真实数据与 operation 时间

真实数据证据沿用来源 V `b79844ddc2304a23a3e6fe386f40aed671c5047b`：完整旅程日志 `s5-b79844ddc2-realdata-dc32-full.log`（mode `0600`）开始 `2026-10-22T08:44:28Z`、结束 `2026-10-22T12:57:26Z`，起止 HEAD 均为来源 V，exit 0。此日志覆盖 t1–t4，因此 `s5-a92f455afb-realdata-dc32-full.log` 仅作更早的执行记录，不作为本次 t1–t3 沿用来源。`s5-dc32-realdata-b79844ddc2.json` mode `0600`，runs 目录 mode `0700`；它和日志保存 summary facts、operation timing 与 measurement，不含 dump 行数据。未读取 dump 内容。所有必需 operation 均 `SUCCEEDED`；没有 `worker_stalled`、超时、HTTP 500、人工恢复状态或 assertion mismatch。

文件 SHA 为上传包 SHA-256；行数为物化后的规范快照。项目名不记录，跨版本 identity 为 `SAME_PROJECT`。Preview facts 的变化数分别是 v1 初始：125/209/192/312，v1 重传：0，v2：4/57/54/26；History 与 composite 计数与 S3/S4 handoff 的事实一致。

| 档/版本 | Dataset ID | package bytes / SHA-256 | source SQL 表/行 | canonical 表/行 | Preview changed 表数 |
| --- | --- | --- | --- | --- | --- |
| t1 v1 | `rd-t1-a-v1` | `107115` / `42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2` | 133 / 6097 | 125 / 3733 | 125 |
| t1 v2 | `rd-t1-a-v2` | `107066` / `4019737fc8fe35e90792dcef722537bf09338110ace8cc09f35e004cc7095bd0` | 133 / 6095 | 125 / 3731 | 4 |
| t2 v1 | `rd-t2-b-v1` | `1247459` / `acd1b5e6f92083c3a6d53e9996be0bf46f520ae7fdea94d8449069748a3817c0` | 217 / 97140 | 209 / 73693 | 209 |
| t2 v2 | `rd-t2-b-v2` | `1197404` / `c66e3921c7774a38bfeb2f407c24a39209225e962f593ec88d17db0d85fcba98` | 217 / 93154 | 209 / 68909 | 57 |
| t3 v1 | `rd-t3-c-v1` | `3356815` / `c34e266c458d9b2cfb630fec56fa7c893113e11b56f768710aecebb0715eec7e` | 200 / 268661 | 192 / 122452 | 192 |
| t3 v2 | `rd-t3-c-v2` | `3370171` / `658422efd2583963cc04bdff6e88e2b733d33396bdd92ff5b3635dc00cffc28d` | 201 / 268667 | 193 / 122458 | 54 |
| t4 v1 | `rd-t4-d-v1` | `5597503` / `95408cc3cfd5bee4f7e53ab1b556e58c3335535b16e8791059029e59d5da1675` | 320 / 437149 | 312 / 246794 | 312 |
| t4 v2 | `rd-t4-d-v2` | `5596595` / `5a7cd54d9b996be55c34b7bb766eb01ad5c1b7c4fa9bd1e72f5c4741baee3611` | 320 / 437229 | 312 / 246874 | 26 |

| 档 | v1 重传 Preview changed 表 | History `record_count` | composite 行（v1/v2） | v1→v2 project identity |
| --- | ---: | ---: | ---: | --- |
| t1 | 0 | 12 | 4 / 4 | `SAME_PROJECT` |
| t2 | 0 | 11511 | 45 / 45 | `SAME_PROJECT` |
| t3 | 0 | 744 | 201 / 201 | `SAME_PROJECT` |
| t4 | 0 | 168 | 435 / 435 | `SAME_PROJECT` |

下表时间来自现有 `s5-dc32-realdata-b79844ddc2.json`，没有重跑真实数据。每格依次为“用户可见 / operation terminal / 结果读取与核对完成”墙钟秒；operation 完成统一采用原始 JSON 中已采到的 `operation_terminal_seconds`。journey harness 在 operation 进入终态后才读取 result/bundle 并核对，所以 `completion_seconds` 是后续“核对完成”，不能代替 operation 完成时间。重复 Submit 没有新 operation terminal，记为 `—`。Submit 的 approve/archive 在各档均完成，之后 History 结果与上表一致。

真实数据沿用条件是 `b79844ddc2..V` 的生产 diff 仅包含 `operations/recovery.py` 与 `application/submit_jobs.py` 中删除累计预算分支及对应实参；其余是 tests、benchmarks、文档，完整逐文件清单见 §5。S5 前通用生产 recovery caller 已传 `reconcile_elapsed_seconds=0.0`，实际走 session-only 路径，累计分支不可达；删除它不改变这条真实链路的行为。operation 时间边界的校正来自上述现有原始 JSON，不是重跑或替换数据。真实 dump 行内容、真实项目名与其主机路径不放入 Git。

| 档 | v1 Preview | v1 Submit | 重传 Preview | 重传 Submit | v2 Preview | v2 Submit | History |
| --- | --- | --- | --- | --- | --- | --- | --- |
| t1 | `52.282 / 52.282 / 52.300` | `40.280 / 40.280 / 40.291` | `62.336 / 62.336 / 62.350` | `.008 / — / .008` | `66.376 / 66.376 / 66.390` | `44.309 / 44.309 / 44.319` | `62.184 / 62.184 / 62.191` |
| t2 | `492.596 / 492.596 / 492.617` | `195.316 / 195.316 / 195.327` | `412.162 / 412.162 / 412.176` | `.008 / — / .008` | `458.414 / 458.414 / 458.429` | `187.255 / 187.255 / 187.265` | `342.987 / 342.987 / 342.996` |
| t3 | `842.390 / 842.390 / 842.410` | `348.320 / 348.320 / 348.331` | `902.787 / 902.787 / 902.801` | `.007 / — / .007` | `1017.408 / 1017.408 / 1017.423` | `358.375 / 358.375 / 358.384` | `625.762 / 625.762 / 625.771` |
| t4 | `1684.782 / 1684.782 / 1684.805` | `565.761 / 565.761 / 565.773` | `1463.686 / 1463.686 / 1463.700` | `.008 / — / .008` | `1477.774 / 1477.774 / 1477.789` | `573.831 / 573.831 / 573.841` | `892.522 / 892.522 / 892.530` |

真实 journey 每步还用 host cgroup `cpu.stat` 记录 backend、worker、repository-service 的 CPU 秒；这是整个容器 CPU delta，不等同于上节 direct capability 的 thread CPU。

| 档 | 步骤 | Backend CPU | Worker CPU | Repository Service CPU |
| --- | --- | ---: | ---: | ---: |
| t1 | v1 Preview | 1.388 | 27.525 | 1.106 |
| t1 | v1 Submit | 1.491 | 9.337 | 50.363 |
| t1 | 重传 v1 Preview | 1.537 | 31.266 | 24.802 |
| t1 | 重传 v1 Submit | .007 | .000 | .100 |
| t1 | v2 Preview | 1.656 | 31.305 | 25.060 |
| t1 | v2 Submit | 1.538 | 9.511 | 62.039 |
| t1 | History | 1.405 | 22.668 | 49.879 |
| t2 | v1 Preview | 12.135 | 458.513 | 10.463 |
| t2 | v1 Submit | 5.803 | 133.474 | 104.817 |
| t2 | 重传 v1 Preview | 10.174 | 362.723 | 61.221 |
| t2 | 重传 v1 Submit | .007 | .000 | .001 |
| t2 | v2 Preview | 11.212 | 408.601 | 62.366 |
| t2 | v2 Submit | 5.531 | 128.350 | 120.299 |
| t2 | History | 7.722 | 268.485 | 117.452 |
| t3 | v1 Preview | 20.675 | 809.876 | 17.854 |
| t3 | v1 Submit | 9.583 | 288.480 | 108.034 |
| t3 | 重传 v1 Preview | 22.146 | 852.051 | 75.176 |
| t3 | 重传 v1 Submit | .007 | .000 | .001 |
| t3 | v2 Preview | 24.947 | 959.156 | 78.117 |
| t3 | v2 Submit | 9.943 | 297.434 | 121.956 |
| t3 | History | 13.981 | 544.860 | 130.265 |
| t4 | v1 Preview | 41.272 | 1646.300 | 35.926 |
| t4 | v1 Submit | 15.571 | 479.216 | 178.769 |
| t4 | 重传 v1 Preview | 35.942 | 1388.700 | 126.804 |
| t4 | 重传 v1 Submit | .007 | .000 | .042 |
| t4 | v2 Preview | 36.532 | 1400.605 | 128.011 |
| t4 | v2 Submit | 15.683 | 477.801 | 212.552 |
| t4 | History | 20.124 | 768.297 | 218.595 |

### t4 S4-F2 submit 对账

| Submit | Repository import 状态 | RS import elapsed | RS queue | `await_import_result` session | 上限 / 余量 |
| --- | --- | ---: | ---: | ---: | --- |
| v1 | `SUCCEEDED` | 79s | 0s | 2 | 3 / 1 |
| v2 | `SUCCEEDED` | 83s | 0s | 2 | 3 / 1 |

两次余量均为 1，没有达到停止条件。精确 Repository operation ID 留在 mode `0600` 的外部 measurement JSON 和 CT108 日志中，不复制进 Git。

### RS 逐表 Arrow 读取

| 规模/基线 | 表数 | Arrow bytes | RS read wall / thread CPU | stream decode wall / CPU | Arrow→Python wall / CPU | 最慢表 |
| --- | ---: | ---: | --- | --- | --- | --- |
| t1 v1 baseline | 125 | 864392 | `12.701 / .121s` | `.013 / .013s` | `.033 / .033s` | `device_st`，1302 rows，`.294s` |
| t2 v1 baseline | 209 | 10708352 | `27.007 / .218s` | `.025 / .025s` | `.418 / .418s` | `device_st`，14633 rows，`2.266s` |
| t3 v1 baseline | 192 | 24734672 | `32.479 / .214s` | `.022 / .022s` | `.910 / .910s` | `device_st`，43110 rows，`6.525s` |
| t4 Preview empty baseline | 0 | 0 | 0 | 0 | 0 | 无表 |
| t4 v1 committed baseline | 312 | 46766064 | `51.847 / .355s` | `.036 / .036s` | `1.492 / 1.492s` | `device_st`，54150 rows，`8.167s` |

Catalog 读取也单独记录：t1 `122517 B / .008464s / .001037s CPU`；t2 `199317 B / .012213s / .001048s`；t3 `174706 B / .011230s / .001037s`；t4 empty baseline `72 B / .001600s / .000603s`，t4 committed baseline `286137 B / .016705s / .001097s`。


## 10. DC32 逐表分布与耗时最高表

新 V 的 `per_table_stage_costs` 有 17,435 条记录，均标为 per-table scope。状态分布是：实测 11,907，共享成本（按包计）5,519，不适用 9。shared 与 not-applicable 的 wall/CPU 字段为 null；下表不把它们填作 0。共享成本的按包 wall/CPU 在 §8 场景表中，无法按生产实现合理拆分的 planning/render 保持 package 级。

| stage | 逐表记录 | 实测 | 共享成本（按包计） | 不适用 | 实测 wall / thread CPU 秒累计 |
| --- | ---: | ---: | ---: | ---: | --- |
| `artifact_write` | 4,388 | 1,989 | 2,399 | 0 | 573.483 / 572.671 |
| `business_materialization` | 1,989 | 1,980 | 0 | 9 | 518.771 / 518.719 |
| `canonical_projection_and_table_digest` | 1,989 | 1,989 | 0 | 0 | 424.685 / 424.646 |
| `comparison` | 1,775 | 1,775 | 0 | 0 | 454.116 / 454.080 |
| `risk_evaluation` | 1,775 | 1,775 | 0 | 0 | 1.300 / 1.301 |
| `schema_sql_rendering` | 624 | 0 | 624 | 0 | —（非逐表计时） |
| `submit_build_import_mutation_snapshots` | 624 | 0 | 624 | 0 | —（非逐表计时） |
| `submit_frozen_artifact_row_read` | 624 | 624 | 0 | 0 | 63.913 / 63.831 |
| `submit_plan_storage_mutation` | 624 | 0 | 624 | 0 | —（非逐表计时） |
| `submit_render_change_set_replay` | 624 | 0 | 624 | 0 | —（非逐表计时） |
| `submit_render_import_mutation_dml` | 624 | 0 | 624 | 0 | —（非逐表计时） |
| `surface_assembly` | 1,775 | 1,775 | 0 | 0 | 0.132 / 0.133 |

按 comparison role 和输入行数区间汇总所有实测且互不重叠的 per-table stage；调用数为该组 `invocations` 之和，输出记录为各 stage 的输出计数之和，不代表跨阶段去重后的业务记录数。pair artifact write、Submit schema SQL/artifact write 与其他 package 共享成本不进入这些逐表 wall/CPU 累计。

| comparison role | 输入行数区间 | 调用数 | wall / thread CPU 秒 | 输出记录累计 |
| --- | --- | ---: | --- | ---: |
| BROWSE_ONLY | 0 | 27 | 0.023 / 0.021 | 0 |
| BROWSE_ONLY | 1–10 | 109 | 0.374 / 0.357 | 289 |
| BROWSE_ONLY | 11–100 | 172 | 0.662 / 0.653 | 3,436 |
| BROWSE_ONLY | 101–1k | 246 | 7.723 / 7.709 | 43,502 |
| BROWSE_ONLY | 1k–10k | 96 | 26.741 / 26.732 | 150,887 |
| ORDERED | 0 | 3,238 | 1.836 / 1.709 | 0 |
| ORDERED | 1–10 | 73 | 0.094 / 0.089 | 45 |
| ORDERED | 11–100 | 521 | 9.040 / 9.013 | 25,519 |
| ORDERED | 101–1k | 949 | 124.540 / 124.475 | 295,745 |
| ORDERED | 1k–10k | 457 | 681.000 / 680.796 | 2,336,649 |
| SNAPSHOT_ONLY | 1–10 | 9 | 0.006 / 0.006 | 6 |
| SNAPSHOT_ONLY | 11–100 | 73 | 0.416 / 0.412 | 2,767 |
| SNAPSHOT_ONLY | 101–1k | 96 | 3.199 / 3.193 | 22,992 |
| SNAPSHOT_ONLY | 1k–10k | 41 | 23.070 / 23.063 | 167,550 |
| STANDARD | 0 | 3,151 | 1.998 / 1.846 | 21 |
| STANDARD | 1–10 | 913 | 1.185 / 1.141 | 3,128 |
| STANDARD | 11–100 | 1,287 | 5.124 / 5.066 | 25,824 |
| STANDARD | 101–1k | 964 | 42.127 / 42.058 | 171,296 |
| STANDARD | 1k–10k | 132 | 221.978 / 221.931 | 301,958 |
| STANDARD | >10k | 64 | 885.264 / 885.112 | 1,105,704 |

按表跨所有实测、非重叠逐表 stage 聚合，最高为 `device_st` 761.967s / 761.828s CPU across 50 invocations (max input 54,150 rows); `device_mx` 212.721s / 212.683s CPU across 50 invocations (max input 14,790 rows); `device_co` 74.448s / 74.435s CPU across 50 invocations (max input 7,251 rows)。单个 table-stage 最大 wall 是 `artifact_write` / `device_st`：49.003788s wall、48.996703s thread CPU。`business_materialization` 有 9 个不适用记录；它们没有 wall/CPU 成本值，不被解释成零耗时。完整逐表细节只在外部 JSON；handoff 不展开行内容。

## 11. C/B 层、容量估算与 Phase 6 候选

### S2b 起各阶段 C 层记录

下表统一使用 t4 的 operation wall 秒。S2b handoff §9 只记录 journey step wall，因此留空，不用 step wall 代替。S3 取 §9 operation wall，S4 只填实际执行的 operation，S5 取现有 `s5-dc32-realdata-b79844ddc2.json` 的 `operation_terminal_seconds`。

| 阶段 | v1 Preview | 重传 v1 Preview | v2 Preview | v1 Submit | v2 Submit | History | 各行来源 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| S2b | — | — | — | — | — | — | `p5-arch-closure-s2b-handoff.md` §9 只有 step wall，故留空，不换口径补值 |
| S3 | 2656.491 | 2335.359 | 2339.012 | 800.757 | 810.836 | 1375.067 | `p5-arch-closure-s3-handoff.md` §9 operation wall；Submit 用 800.757/810.836，不用 step wall 802.912/812.991 |
| S4 | 1677.773 | — | 1463.100 | 576.497 | — | — | `p5-arch-closure-s4-handoff.md` §9 operation wall；v1 Submit 用 576.497，不用 step wall 578.201；其余未运行 |
| S5 | 1684.782 | 1463.686 | 1477.774 | 565.761 | 573.831 | 892.522 | `s5-dc32-realdata-b79844ddc2.json` 的 `operation_terminal_seconds`，没有重跑真实数据 |

### B 层观察（登记到 Phase 6，不在 P5 修）

- t4 Preview 的 operation terminal 为 1,684.782s；DC32 capability 独立 package 阶段的 SQL parse 为 140.498/140.485s、business materialization 211.540/211.516s、projection/digest 218.977/218.946s、projected snapshot write 153.334/153.072s（wall/thread CPU）。t4 v1 Preview pair comparison 为 148.362/148.341s，risk evaluation 为 27.369/27.367s。各值属于不同测量边界，不能相加替代 operation wall。
- 完整 v1 重传与低变化 v2 Preview 的 operation terminal 分别为 1,463.686s 与 1,477.774s；重传 v1 Preview changed=0，v2 changed=26/312。Phase 6 可评估重复/低变化 workload 的 table 粒度复用，但须维持冻结 Contract 与相同规范事实。
- RS baseline 是逐表 Arrow read；t4 有 312 次，合计 read wall 51.847s、RS thread CPU .355s，Arrow→Python 为 1.492s。未按行发送 Repository 请求，没有观察到 operation 空等或 worker stall。
- Submit 的新 capability 证据把边界分清：v1 snapshot build 69.061s；plan child 230.808s、replay child 7.141s，父 DML inclusive 237.984s（父 exclusive .035s）；将 frozen row read 与不重叠内部段汇总后为 337.281s wall / 337.173s CPU。v2 对应 non-overlap 为 334.758/334.626s。adapter outer 为 v1 373.980/373.754s、v2 369.456/369.209s，不能再与内层相加。真实 V 的 repository import 79s/83s、queue 0s/0s、await session 2/2 是完整生产 journey 的另一个测量边界，不与 capability outer 相加。
- 上述是性能候选，不构成 P5 失败；DC31 要求记录、P5 不修，除非影响 A 层。真实 t1–t4 全部达到 operation 终态且断言通过。真实 journey 的 operation 完成采用终态采样时间，result/bundle 读取与核对完成另列，不混用两者。

### 目标外推与字节余量

Owner 的业务容量目标为约 2×t4（约 640 source tables、约 493,588 canonical rows、约 11.2 MB 上传包），Preview 在 10 分钟内。以 t4 v1 Preview 的 operation terminal `1,684.782s` 线性外推，2×规模约 `3,369.564s`（56.16 分钟），比 600 秒目标多 `2,769.564s`，是目标时长的 5.62 倍。未实际跑 2×数据；单个 t4 点、数据变化比例、缓存、并发和 CPU/I/O 都会使线性外推失真。此目标属于 Phase 6 退出目标，不是 S5 门槛。

| 字节上限 | t4 实测 | 2×外推 | 上限 | 余量 |
| --- | ---: | ---: | ---: | ---: |
| replay SQL（200 MiB） | v1 `50,566,047 B`；v2 `50,572,564 B` | v1 `101,132,094 B`；v2 `101,145,128 B` | `209,715,200 B` | v1 `108,583,106 B`；v2 `108,570,072 B` |
| Catalog（2 MiB） | `286,137 B` | `572,274 B` | `2,097,152 B` | `1,524,878 B` |

### Phase 6 候选

1. 先以本 handoff 的 V capability 与真实 operation terminal 口径建立可重复基准，再确定 2×t4 Preview 目标。
2. 评估 SQL parser、business materialization、canonical projection/table digest、canonical artifact row handling 的 native/Arrow 化。
3. 评估重复 v1 / 低变化 v2 的全量 scan 与 table 粒度缓存/增量计算；以 canonical summaries、Preview counts、History records 和 composites 作正确性对照。
4. 评估 ordered 比较与 STANDARD 大表处理的 CPU 成本，以及合理的逐表并发边界。
5. 基于分开的 Submit snapshot build、storage mutation planning、change-set replay、DML parent-exclusive、adapter outer 和实际 Repository import/commit 边界分别评估成本；不把 parent/child 或 outer/inner 相加推断占比，同时保持 expected parent CAS 与冻结 artifact 语义。
6. 本次唯一新增的 BLAKE3 dev dependency 已满足测量授权；不把 benchmark harness 扩展为生产依赖或平台。

### 旧实现 t4 Preview 对照

没有获得可在本次 CT108、同一数据与同一两时钟口径下运行的旧实现。旧路径需可执行旧应用/依赖闭包及已解包数据目录；此 worktree 只提供 `legacy/` 参考代码，真实数据按约定以归档包供应，没有旧镜像/锁定环境/独立可执行入口。没有读取或解包 dump。Phase 6 讨论稿记录过旧流程约 60 秒前端等待，但它不是本次 operation 终态或核对完成口径，不作数值对比。执行计划明确旧实现对照“条件允许时”且不阻塞 S5。

## 12. P5 §2A.5 逐项对照与证据包索引

| §2A.5 项 | 结果 | 证据索引 |
| --- | --- | --- |
| 1. wire 泄漏、私有导入、事务/编排环、基础层倒挂、包根归属已修；architecture gate 有边界；canonical/manifest golden 与 digest 语义仍可核对 | 本轮 `import_rules=0/0/6`，全量 architecture tests 通过。Submit frozen products 用同输入 golden 核对 schema SQL、DML、package digest 字节一致；无新的架构例外。 | `s5-import-rules-55a8b81024.log`；`s5-full-runner-55a8b81024-r2.log`；§4 S5.3 表 |
| 2. Contract 执行边界、编排集中度、projection 占位风险已由实际消费者和 owning 文档核对 | §4 的 11 行均对齐或按 owner 决议修复。Project identity 的 facade 拓扑和 Submit prepare 冻结 ruleset 两项决议均未修改 Contract。 | §4 核对表；提交 `ba4ee7a5e6`, `9f1df26914`；focused/full runner 日志 |
| 3. 依赖合规、既有问题位置、真实链路与 Phase 6 候选 | 仅加 dev-only `blake3==1.0.10`；真实数据和阶段测量见 §8–§11；B 层和候选均列于 §11。 | `pyproject.toml`、`uv.lock`；外部 metrics JSON |
| 4. 语义回归、五包静态、权威 runner/容器门禁 | 五包 ruff/mypy、全量 runner、fresh RS image、全部 Compose journeys 0 skipped，t1–t4 完整真实链路通过。 | §7；CT108 `s5-55a8b81024-*` logs |
| 5. 不可达基线清理；余项须有 owner/reason/next phase；§2A.4.1 已修或 owning 登记 | 没有不必要条目可删；只剩两组已在 §9 逐项登记的延期，共 6 个模块。 | `p5-arch-closure-design.md` §9；`architecture_baseline.py`；§3 |

## 13. 停止条件与审核状态

执行计划 §14 的停止条件均未触发：真实 Dolt 类型/同一性正常；无 Contract 例外、兼容部署或新增协议族；所有 operation 正常终态；无 t4 Submit 会话耗尽；没有需要扩大 API、Docker/Compose、依赖或生产测量插桩的改动；无未预期不可达模块；完整 runner exit 0、Compose journeys 0 skipped、真实数据 assertions 通过。

S5 审核尚未执行，故本 handoff 只给 `pass_recommended: yes`，不等于审核通过或 P5 exit。审核通过前不做 P5 exit；P5 exit cleanup 按 G10 另行安排。

## 14. 审核提示词

```text
任务：独立复审 P5 架构收口 S5 定向修订。你没有参与修订实现；按
slice-design-execution-and-review-guide.md §5–§6 与执行计划 §8.8 审核，不预设结论。

审核对象：p5-s5 的最终 H @ <由复审方填写完整 H SHA>（门禁 V = 55a8b810249649b403339d406cd2b5744feb7863），区间 p5-s4-exit `5634dc6f9b`..H。只审该区间差异；初审报告保持原样。
在只读 detached worktree 审核；测试与取证按 DC34 在 ct108-gw-dms 上进行，不在开发主机或 main 上审核。
权威依据：p5-arch-closure-execution-plan.md §2/§3/§6/§7/§8.1–§8.3/§8.7/§8.9，p5-arch-closure-design.md §9/§11/§13/§14，P5 §2A.5，DC30–DC34、G10、G12，Performance Measurement Guidance，AGENTS.md，testing-conventions.md 与本 handoff。

必须复审：
1. S5-F1 是否彻底删除 R5 累计耗时分支、helper、枚举与参数；两生产 caller、三个会话耗尽、Submit session 1/2 retry 与 session 3 manual recovery、已终态结果和通用恢复语义是否有对应证据；owner 授权是否准确记录。
2. S5-F2 新 V 是否从头运行全部 18 个 DC32 capability 场景；各 per-table 项是否区分实测、共享成本（按包计）、不适用且没有把未测记 0；planning/render 的逐表限制、Submit 父子边界、adapter outer、schema SQL/artifact write、pair artifact write 与 business materialization 计时是否有准确解释；§8/§10/§11 的数值是否能从新日志/JSON 复算且没有拼接旧 v1 数据。
3. 真实数据是否正确沿用 b79844ddc2 的 t1–t4 证据，沿用条件是否由 `b79844ddc2..V` 逐文件 diff 支持；operation completion 是否使用 `operation_terminal_seconds`，结果核对完成是否单独命名；真实行内容、真实项目名与主机路径是否未入 Git。
4. S5-F3 两项 owner decision SHA、偏差 2 引入提交、最后允许沿用范围与实际 t1–t4 全量重跑原因是否正确区分。
5. 全量 runner exit 143 的 umask/secret-permission 原因、清理范围、umask 022 r2 通过结果，fresh RS 镜像 provenance，runner 起始 manifests，以及 H 的 carried compare 是否真实、完整；V runner 和 DC32 成功重测分别核对其自身日志与 exit code。
6. P5 §2A.5 五项、文件路径预算、S5 停止条件、H handoff-only scope 与 Phase 6 候选是否基于修正后事实；审核通过前没有宣称 P5 exit 或执行 G10 cleanup。

复审验证：只在 CT108 审核 worktree 核对五包 ruff/mypy、import_rules、V 权威 runner/测量原始证据、RS identity/labels 与 V→H carried；不要求重跑全量 runner或真实数据。发现证据不符时按执行计划 §8.8 报告；不要修改 V、初审报告或 Contract。

交付：按执行计划 §8.8 更新 plans/p5-arch-closure-s5-independent-review.md，并以独立纯文档提交到 p5-s5；不推送、不打 tag。审核结论只能是通过 / 定向修订 / 整体返工。请复审方在审核报告中填写最终 H 完整 SHA；H 自身不包含自己的 SHA。S5 审核通过后由 owner 决定下一步；P5 exit 与 G10 cleanup 另行安排。
```
