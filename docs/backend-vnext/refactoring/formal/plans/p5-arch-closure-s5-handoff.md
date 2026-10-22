# P5 架构收口 S5 handoff

pass_recommended: yes

建议 S5 验收通过：S5.1–S5.4、全量权威 runner、五包静态检查、fresh 镜像、t1–t4 真实旅程与最终 H 的 carried 判定均已完成。本文列出的证据没有触发执行计划 §14 停止条件。此建议等待独立审核；在 S5 审核通过前不做 P5 exit。P5 exit 清理依 G10 另行安排。

## 1. 区间、提交与环境

| 项 | 值 |
| --- | --- |
| `range_start` | `p5-s4-exit`，`5634dc6f9b` |
| kickoff base | `ebf46098a3` |
| 实现 HEAD | `b79844ddc2304a23a3e6fe386f40aed671c5047b` |
| 门禁提交 V | `b79844ddc2304a23a3e6fe386f40aed671c5047b` |
| 候选 H | 含本文的 handoff-only commit；精确 SHA 由分支 `p5-s5` 的 `git rev-parse HEAD` 与本次最终 CT108 取证日志记录。commit 不能包含自己的 SHA。 |
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
状态转换/恢复用例。累计分支五个目标符号在生产代码和测试中的 `rg` 结果为 0，命令和完整结果见 §6。

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

登记位于 `p5-arch-closure-design.md` §9；基线注释在 `vnext/backend/tests/architecture_baseline.py`。最终 `import_rules` 日志为 `s5-import-rules-b79844ddc2.log`。

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

## 5. 路径预算与依赖

相对 §3 S5 和 owner 授权，所有额外路径均属于相应子步或已记录治理决定；没有修改 Dockerfile、Compose、Contract、RS 公开接口或其他依赖。

| 文件/路径 | 超出最窄子步清单的原因 |
| --- | --- |
| `vnext/backend/src/gateway_backend/application/submission/contracts.py` | S5.1 删除无用途的 checkpoint 时间状态；S5.3 删除 build input 中不应由运行期 ruleset 提供的字段。两项都是 owning application contract 的实际载荷修正，不是外部 Contract。 |
| `vnext/backend/src/gateway_backend/operations/recovery.py` | 为 R5 增加显式 `ReconcileBudgetMode`，让 Submit 的受限 poll session 和其他 caller 的累计时间预算有名字、可分别验证；其他 caller 默认值不变。 |
| `vnext/backend/src/gateway_backend/application/recovery.py` | S5.1 明确要求删除没有生产调用方的累计预算 helper、常量与 checkpoint key。 |
| `vnext/backend/src/gateway_backend/infrastructure/repository_write/import_publication.py` | S5.3 owner 决议要求冻结规范 artifact/manifest 独立构建 schema 与 DML；组装逻辑必须消费冻结输入。公开 storage_projection/snapshot_materialization API 未改。 |
| `vnext/backend/tests/test_operation_effect_reconcile.py`、`test_operation_job_recovery.py`、`test_operation_recovery_policy.py`、`test_submit_job_effect.py`、`test_submit_job_payload.py` | S5.1 的 session 边界、泛型 R5 caller 不变、移除 Submit checkpoint 时间字段及终态回归。 |
| `vnext/backend/tests/support/synthetic_jobs.py` | 与 generic recovery fixtures 同步，保留其他 operation 使用的 session/timestamp 场景，删除 Submit 不再使用的时间状态。 |
| `vnext/backend/tests/test_architecture.py`、`architecture_baseline.py` | S5.2/5.3 的 import rule、延期基线注释和 owning 登记引用。 |
| `vnext/backend/tests/test_submit_import_builder.py`、`test_submit_job_prepare.py`、`test_submit_prepare_removed_tables.py` | 冻结 ruleset A/B 行为、包字节 golden、removed-table 与冻结 descriptor/row 绑定验证。 |
| `vnext/backend/benchmarks/s5_dc32_capability_measurement.py`、`tests/test_real_dump_dc32_measurement.py` | DC32 授权的独立测量模块和其业务行为测试；不进入生产包。 |
| `vnext/backend/benchmarks/real_dump_journey.py`、`tests/test_real_dump_journey.py` | 探针和两时钟/调试开关实现及行为测试；执行计划 §3 的测量脚本与 DC32 harness 范围。V 最后的改动只更新测试期望。 |
| `vnext/backend/tests/test_submit_recovery.py` | owner 授权修复测试 seam：替换公开 `build_and_publish`，不 patch 私有方法；仅测试路径。 |
| `docs/backend-vnext/refactoring/formal/plans/p5-arch-closure-design.md` | S5.2 要求 owning 设计登记 canonical row hash 与 external_target_sync 的 owner、理由、重开条件。 |
| `docs/backend-vnext/refactoring/formal/plans/p4-r5-retry-takeover-effect-recovery-design.md`、`p5-5b-submit-finalize-design.md` | S4-F2 明确授权修订 R5 设计 §6 和 5B Submit poll 上限关系。 |
| `docs/backend-vnext/refactoring/formal/plans/p5-arch-closure-execution-plan.md`、`p5-arch-closure-post-s1-governance-plan.md`、`p5-arch-closure-s0-owner-decisions.md` | 记录 owner 已批准的 S4 停止后 DC33/G12 范围修订及其治理依据；不改变 Contract 或实现范围。 |
| `vnext/backend/pyproject.toml`、`vnext/backend/uv.lock` | 唯一新增依赖为授权的 dev-only `blake3==1.0.10`，canonical PyPI identity。该版本于 2026-09-29 发布；到 V（2026-10-22）已超过两周，uv.lock 有 CPython 3.14 manylinux x86_64 wheel。无其他依赖/锁变更。 |

## 6. 失败、修正与符号搜索

| 停顿/失败 | 原因、处置、提交 |
| --- | --- |
| 首次 runner V `a2cfe03c21` exit 1 | `test_submit_recovery.py` patch 了已删除的公开 `build_and_publish_from_inputs`；`9f1df26914` 已将 seam 改为私有名。Owner 决议后在 `241ee66d94` 改为 patch 公开 `build_and_publish(self, *, build_input, store)` 并直接返回 `build_dolt_compatible_prepare_publication(...)`；不 patch 私有方法。 |
| 探针从 operation row 取 Repository operation ID 失败 | 成功 Submit 的 ID 写在 `submit_attempt_records.repository_operation_id`，先由 business_refs 的 `submit_attempt` ID 找到 attempt。`a92f455afb` 修正读取函数，保持 control DB 只读、备份优先。 |
| 探针从公开 RS response 取时间戳失败 | `GetOperationResponse` 只有 operation_id/status/result/error；时间在 RS control DB。`d76cff8018` 在容器内对 RS control DB 先 backup 到临时文件，再按 ID 精确查询并清理；公开 API 仅用于核对 SUCCEEDED 状态。未改产品代码或 RS DTO。 |
| Runner V `abb7968bbe` exit 1 | CLI 参数测试整字典比较缺少默认参数 `debug_t1_submit_probe=False`。`b79844ddc2` 仅更新测试期望并核对同模块其他整字典比较。 |
| fresh RS identity shell 校验曾因引号出错 | 修正了 worktree 外 `/home/dev/gdds-p5-closure-s1-gate-logs/s5/s5-build-and-verify-rs-v.sh`；脚本未入 Git。V 上重新执行的构建和独立身份校验均 PASS。 |

按 owner `398204b4c0` 决议的调试路径，在 `abb7968bbe` 上做过 t1 调试探针（不作证据）：`s5-debug-probe-t1-abb7968bbe.log`；v1/v2 Submit 均取得 Repository operation ID、RS `SUCCEEDED`、queue 0 秒、24/25 秒 RS import 与 1/3 个 reconcile session。最终 V 真实数据证据时关闭该调试开关。

沿用授权与实际执行分开记录：owner 最后允许的范围由 main `f84b930d4a` → `398204b4c0` → `0b8c2bac41` 收敛为 t1–t3 沿用 `a92f455afb`、t4 在新 V 全量运行。V `b79844ddc2` 实际运行了 t1–t4 全量；原因是 `real_dump_journey.py --dc32-output` 不接受 `--tier`，不是 owner 另行选择全量重跑。`--dc32-output` 对 `--tier` 的拒绝由 harness 校验，见 `real_dump_journey.py` 的完整旅程约束和 `test_real_dump_journey.py` 对 CLI 参数的覆盖。

符号搜索在 `vnext/backend/tests`（无 `vnext/backend/tools` 目录）执行。S5 区间 diff 提取 17 个被删/改名的 function/test 名，再逐名在 tests/tools/support 搜索；product helper 的测试引用为 0。搜索命令：

```bash
rg -n 'build_and_publish_from_inputs|_resolve_ruleset|_open_projection_inputs|migrated_table_ruleset_snapshot' vnext/backend/tests
git diff --unified=0 5634dc6f9b..b79844ddc2 -- vnext/backend > /tmp/p5-s5-symbol-diff.patch
rg -n '(_assert_projection_identity|_capability_storage_projection_version|_capture_control_operation_rows|_empty_projection_from_frozen_manifest|_open_frozen_manifest|_reopen_projection_inputs|_resolve_ruleset|build_and_publish_from_inputs|parse_reconcile_started_at|reconcile_elapsed_seconds|reconcile_session_budget_exhausted|test_await_terminal_checkpoint_rejects_unknown_job_state_fields|test_capability_storage_projection_version_maps_contract_v1|test_parse_reconcile_started_at_reads_iso_utc|test_parse_reconcile_started_at_rejects_missing_or_invalid_values|test_reconcile_session_budget_exhausted)' vnext/backend/tests
```

四个指定字符串的历史总命中是 68：`build_and_publish_from_inputs` 0；`_resolve_ruleset` 0；`_open_projection_inputs` 6（`test_submit_import_builder.py` 对仍存在于 publication adapter 的 artifact reader 测试）；`migrated_table_ruleset_snapshot` 62、分布在 19 个测试/支持文件（规则 capability、其他 Preview/History 构造、Submit build-input fixture，以及断言 Submit prepare 不再读取 runtime ruleset 的 A/B 测试）。diff 派生 17 个候选名：8 个生产 helper/method、1 个通用 `json` helper、5 个测试函数名、3 个累计预算 helper；除过于通用的 `json` 外，其余 16 个均逐名搜索。没有已删除生产 helper 的陈旧调用。命中归类为 fixture/assertion、仍存在的 private artifact reader、迁移后的同名测试定义、通用 R5 测试。

S5-F1 关闭后的残留搜索命令与结果：

```text
rg -n 'reconcile_budget_exhausted|ReconcileBudgetMode|CUMULATIVE_ELAPSED_TIME|RECOVERY_SESSIONS_ONLY|reconcile_elapsed_seconds' vnext/backend/src vnext/backend/tests
exit 1; no matches (0)
```

## 7. 五包检查与权威 runner

### Focused 与静态检查

在 V 的 clean CT108 worktree 运行完整 `tests/test_real_dump_journey.py`、backend `pytest -m unit` 和五包 ruff/mypy；全部 exit 0。日志均在 `/home/dev/gdds-p5-closure-s1-gate-logs/s5/`：focused 日志为 `s5-b79844ddc2-real-dump-journey-tests.log`、`s5-b79844ddc2-backend-unit.log`；静态检查分别为 `s5-b79844ddc2-{shared_kernel,repository_contracts,repository_client,backend,repository_service}-{ruff,mypy}.log`。

### Preflight、镜像与 runner

V runner 前 preflight 和 runner 后 postflight 都通过：无 Dolt 进程、无 Compose 栈/容器、8000 空闲、worktree clean。日志：`s5-preflight-b79844ddc2-final.log`、`s5-b79844ddc2-postflight.log`。

在 V 上执行 `./vnext/scripts/build-repository-service-image.sh` fresh 重建 `gateway-repository-service:local`。重建前 image ID 为 `sha256:d4da542a1816e6b1a905323510f941064bbd1e11517be4bf34d1cc6318549dc7`，重建后为 `sha256:5092011e2761964071228179d698d215d441c2ef684c90e3a66666f5c8193495`。identity：candidate `b79844ddc2304a23a3e6fe386f40aed671c5047b`；RS `build_input_revision=ed70ca1be262653bb49267940e73e7edd09a2267`；`source_tree_sha256=sha256:a3e56c4d90e67ba80b632599ead9dca8fc65d13d2193ad0f42472d9a9f68be3a`。两个 RS identity label 与 V 重算值相同，独立 verifier PASS。日志 `s5-b79844ddc2-fresh-rs-build-verify.log`。

权威命令为 `GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`，未设置 `GATEWAY_TEST_PACKAGES`。runner 在 clean V 上 exit 0；五包均由本次运行，未把失败的 `a2cfe03c21` 当作任何包的沿用来源。backend/worker Compose context 为 V；RS 镜像按上文在 V fresh 构建；client e2e 镜像由 runner 按候选 label 自动重建。未手工 `docker rmi`、`docker tag` 或删除 client `:local` / `-base:local`。postflight provenance 记录在 `s5-b79844ddc2-postflight.log`。

| 包 | S4 V `ed70ca1be2` | S5 V `b79844ddc2` | 变化 |
| --- | --- | --- | --- |
| `shared_kernel` | 242 passed | 242 passed | 无 |
| `repository_contracts` | 152 passed | 152 passed | 无 |
| `repository_client` | 154 passed | 154 passed | 无 |
| `backend` | parallel 2901；serial 36 | parallel 2907；serial 39 | parallel +6、serial +3，来自 S5 新增/参数化回归与 measurement tests |
| `repository_service` | parallel 1724 passed + 1 skipped；serial 205 passed | parallel 1724 passed + 1 skipped；serial 205 passed | 无 |

唯一 skip 是 `tests/test_p2_r1_target_cgroup_smoke.py`，原因是“runs only inside the delegated target container”；该用例只在 delegated target container 运行，不是 Compose 旅程。RS 从 `241ee66d94` 起未改变，引用此前 `pytest -m unit -rs` 日志 `s5-v241ee66-repository-service-unit-rs.log`；S4 与 V 计数相同。全部 Compose 旅程 0 skipped。

V runner 日志：`s5-b79844ddc2-full-runner.log`；起止 HEAD 均为 V，runner 自身 exit code 0。五包起始 manifest：`s5-b79844ddc2-manifest-<package>-start.json`。

| 包 | V runner 起始 manifest total_digest | 判定 |
| --- | --- | --- |
| `shared_kernel` | `c50ed6636ebed5dc3c67c2c788a556e60bae3981d4213d5f96bf620f6f2b8ff9` | V 实际运行通过 |
| `repository_contracts` | `cf02462ed6d4e953501e9a97e2b7f9f7c0fa8275f8a1d8b16abe540cd26b4517` | V 实际运行通过 |
| `repository_client` | `a9a541548bb64db8e0cf1067c72c18a08600eab0ca4cd5046f5b1227cde46d92` | V 实际运行通过 |
| `backend` | `ab337285f850b0e6318eb54785833795bb8ffeda9be65fbc86dfa7968e4095f0` | V 实际运行通过 |
| `repository_service` | `acbe7c9b712fef2aef1b2386e40f48bc6f77073021b02106eaf0cb2141c62509` | V 实际运行通过 |

### V→H carried（DC34）

第一份 handoff-only 提交 H1 `cc15dabec9bf837ef7a277f2883e536026d27c60` 已在运行 V runner 的同一 CT108 worktree 中，以本节列出的完整 V runner 环境完成 carried 检查。日志 `s5-carried-cc15dabec9.log` 起止 HEAD 均为 H1、exit 0。RS `build_context_digest.py identity` 的 `build_input_revision=ed70ca1be262653bb49267940e73e7edd09a2267`、`source_tree_sha256=sha256:a3e56c4d90e67ba80b632599ead9dca8fc65d13d2193ad0f42472d9a9f68be3a` 均与 `gateway-repository-service:local` 两个 provenance label 一致。五包 manifest compare 均为“可沿用”，`changed_components=[]`，current digest 与 V runner 起始 digest 逐包相同，数值见上表。最终 H 也是 handoff-only；最终提交后的同 worktree 复核日志 `/home/dev/gdds-p5-closure-s1-gate-logs/s5/s5-carried-final-H.log` 起止 HEAD 均为最终 H、exit 0。RS 两项 label 均匹配，五包 manifest 均为“可沿用”、`changed_components=[]`，且各自 digest 与 V runner 起始 digest 相同。

## 8. DC32 capability 测量

owner 最后允许沿用的范围为 main `f84b930d4a` → `398204b4c0` → `0b8c2bac41`：t1–t3 使用 `a92f455afb` 的通过证据，t4 在新 V 全量运行。实际 V `b79844ddc2` 的 harness 以 `--dc32-output` 运行 t1–t4 全量，因为该选项不接受 `--tier`；这是实际命令约束，不是 owner 的范围选择。该完整真实旅程日志为 `s5-b79844ddc2-realdata-dc32-full.log`，真实数据明细为 `/home/dev/gateway-real-dumps/runs/s5-dc32-realdata-b79844ddc2.json`。

S5-F2 完成后在新 V 上从头运行全部 DC32 capability 场景，使用新日志与 JSON 文件名；不拼接 `a2cfe03c21` 的旧数据。新日志、JSON 路径与权限、场景数、逐表记录数和运行结果列于本节下文。测量只记录 capability 调用，不修改生产代码，也不读取 dump 行内容。

下方尚未重写的旧 capability 数字仅作历史记录，不作为 S5-F2 结论或新运行的输入。新 V 测量完成后，最终 H 将整体替换本节汇总、§10 逐表统计和 §11 B 层观察。

允许沿用的范围经核对：

```text
git diff --name-only a2cfe03c21..b79844ddc2
vnext/backend/benchmarks/real_dump_journey.py
vnext/backend/tests/test_real_dump_journey.py
vnext/backend/tests/test_submit_recovery.py
```

DC32 capability runner 位于 `vnext/backend/benchmarks/s5_dc32_capability_measurement.py`；其 `main → run → materialize/project, pair, submit, history` 调用 production capability facade，不导入或调用 `real_dump_journey.py`。后者仅负责真实数据 operation journey/harness。上述三处变化不影响 capability 调用路径，因此沿用 `a2cfe03c21` 的 DC32 capability 数据；`a2cfe03c21` 的 runner exit 1 不作为 package test 来源。

### 阶段墙钟 / thread CPU

下表各项为 `wall / thread CPU` 秒。简写：解析/物化依次是 source package staging、SQL parse、business materialization、canonical projection + table digest、canonical artifact write；Preview/History 顺序为 comparison planning、comparison、risk evaluation、surface assembly、artifact write。XML parse 与小型 staging 记录在完整 JSON 中。Submit 的 mutation planning/replay 有四段独立计时；Package build/readback 当前只记录 wall time。

| 场景 | 各阶段 wall / thread CPU 秒 |
| --- | --- |
| t1 v1 materialize | staging `.007/.007`；SQL `2.406/2.406`；business `3.601/3.601`；projection/digest `3.623/3.622`；canonical artifact `3.139/3.049`；ArtifactStore `.006/.005` |
| t1 v2 Preview | planning `.042/.042`；compare `.088/.088`；risk `.004/.004`；surface `.099/.099`；artifact `<.001/<.001` |
| t2 v1 materialize | staging `.077/.077`；SQL `31.057/31.053`；business `48.816/48.810`；projection `58.002/57.994`；canonical artifact `42.470/42.309`；ArtifactStore `.018/.017` |
| t2 v2 Preview | `.092/.092`; `34.851/34.848`; `1.310/1.310`; `.193/.193`; `.005/.005` |
| t3 v1 materialize | staging `.253/.253`; SQL `92.101/92.090`; business `143.573/143.560`; projection `127.129/127.118`; canonical artifact `93.758/93.610`; ArtifactStore `.037/.037` |
| t3 v2 Preview | `.076/.076`; `73.218/73.203`; `.109/.109`; `.164/.164`; `.003/.003` |
| t4 v1 materialize | staging `.391/.391`; SQL `143.120/143.104`; business `213.067/213.044`; projection `220.586/220.557`; canonical artifact `155.378/155.121`; ArtifactStore `.061/.061` |
| t4 v1 Preview | `.134/.134`; `149.935/149.913`; `26.863/26.860`; `.328/.328`; `.060/.059` |
| t4 重传 v1 materialize | staging `.403/.403`; SQL `141.118/141.106`; business `210.565/210.550`; projection `214.833/214.815`; canonical artifact `154.728/154.482`; ArtifactStore `.061/.061` |
| t4 重传 v1 Preview | `.140/.140`; `40.007/40.003`; `.005/.005`; `.257/.257`; `<.001/<.001` |
| t4 v2 materialize | staging `.400/.400`; SQL `141.101/141.089`; business `210.546/210.531`; projection `216.198/216.182`; canonical artifact `152.823/152.567`; ArtifactStore `.061/.060` |
| t4 v2 Preview | `.139/.139`; `38.358/38.355`; `.024/.024`; `.261/.261`; `.002/.001` |
| t4 v1 Submit prepare | mutation/replay spans `69.052/69.009 + 228.623/228.490 + 7.117/7.116 + 235.776/235.641` (total `540.569/540.257`); schema SQL `.002/.002`; artifact write `.001/.001`; package build/readback wall `371.923` |
| t4 v2 Submit prepare | mutation/replay spans `64.654/64.617 + 227.583/227.489 + 6.973/6.972 + 234.591/234.495` (total `533.800/533.573`); schema SQL `.002/.002`; artifact write `.001/.001`; package build/readback wall `367.528` |
| t4 History | planning `.138/.138`; compare `38.439/38.437`; risk `.025/.025`; surface `.262/.262`; artifact `.002/.002` |

RS baseline读取与 conversion 在真实数据 measurement 中分开记录。RS逐表汇总见第 9 节；四个 t4 stages 的 package build/readback 没有 thread CPU field，因此只报告实际采到的 wall，未推算 CPU。Repository import/commit 的基本操作用同一规范重放 SQL 在临时 Dolt repository 中单独测量，并记录 child CPU。

### 基本操作吞吐

| 操作 | workload 与结果 |
| --- | --- |
| 包解压 | t4 v1 compressed `5,597,503 B` → expanded `80,337,841 B`；`421.233 MiB/s`，wall `.181885s`，CPU `.181881s`。 |
| 现有 SQL 解析 | `79,446,967 B`；`0.529 MiB/s`，wall `143.120s`，CPU `143.104s`。 |
| Arrow → Python | `246,794` rows、2 个 int64 列；`36.663 MiB/s`，wall `.102729s`，CPU `.102709s`。 |
| Arrow IPC | 写入 `3,949,322 B`，`2596.929 MiB/s`、`.001450s`；mmap read/scan `1361.311 MiB/s`、`.002767s`。 |
| 压缩包 hash | existing/SHA-256 `1717.988/1723.073 MiB/s`；BLAKE2b `983.880`；BLAKE3 `5606.835`。 |
| 解压 SQL hash | existing/SHA-256 `1732.955/1733.453 MiB/s`；BLAKE2b `990.980`；BLAKE3 `5210.150`。 |
| 直接 Dolt import/commit | 临时离线仓库、规范 replay SQL `50,566,047 B`；import `24.226s` wall / `23.888s` child CPU；commit `.134s` / `.192s`。 |

## 9. 真实数据与 operation 时间

V 上完整真实旅程日志为 `s5-b79844ddc2-realdata-dc32-full.log`（mode `0600`），开始 `2026-10-22T08:44:28Z`、结束 `2026-10-22T12:57:26Z`，起止 HEAD 都是 V，exit 0。此日志覆盖 t1–t4，因此 `s5-a92f455afb-realdata-dc32-full.log` 仅作先前执行记录，不作为 V 的 t1–t3 沿用来源。`/home/dev/gateway-real-dumps/runs/s5-dc32-realdata-b79844ddc2.json` mode `0600`，runs 目录 mode `0700`；它和日志保存 summary facts、operation timing 与 measurement，不含 dump 行数据。未读取 dump 内容。所有必需 operation 均 `SUCCEEDED`；没有 `worker_stalled`、超时、HTTP 500、人工恢复状态或 assertion mismatch。

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

下表时间来自现有 `/home/dev/gateway-real-dumps/runs/s5-dc32-realdata-b79844ddc2.json`，没有重跑真实数据。每格依次为“用户可见 / operation terminal / 核对完成”墙钟秒；完成时间统一使用 `operation_terminal_seconds`，`completion_seconds` 只作为 terminal result 读取与核对结束时间单独列示。重复 Submit 没有新的 operation terminal，记为 `—`。Submit 的 approve/archive 在各档均完成，之后 History 结果与上表一致。

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

`per_table_stage_costs` 完整逐表数据共 14,939 条，路径和权限见 §8。每个条目保留 table、stage、row/column count、comparison role、ordered、record/output count、changed、wall 与 thread CPU。下表按该明细对 invocation（`invocations`）及 output record 汇总；`changed` 为表级比较事实计数，物化阶段为不适用。

| 比较角色 | 输入行数区间 | 调用数 | wall / thread CPU 秒 | 输出记录数 | changed true / false 观察数 |
| --- | --- | ---: | --- | ---: | ---: |
| BROWSE_ONLY | 0 | 27 | `.023 / .021` | 0 | 0 / 12 |
| BROWSE_ONLY | 1–10 | 109 | `.382 / .362` | 311 | 44 / 28 |
| BROWSE_ONLY | 11–100 | 172 | `.668 / .658` | 3524 | 64 / 36 |
| BROWSE_ONLY | 101–1k | 246 | `7.750 / 7.735` | 47404 | 140 / 40 |
| BROWSE_ONLY | 1k–10k | 96 | `26.780 / 26.770` | 170665 | 66 / 12 |
| ORDERED | 0 | 3238 | `1.839 / 1.714` | 0 | 0 / 2308 |
| ORDERED | 1–10 | 73 | `.096 / .091` | 45 | 0 / 28 |
| ORDERED | 11–100 | 521 | `9.028 / 9.002` | 29955 | 0 / 364 |
| ORDERED | 101–1k | 949 | `124.241 / 124.176` | 352453 | 0 / 692 |
| ORDERED | 1k–10k | 457 | `680.081 / 679.949` | 2786273 | 0 / 316 |
| SNAPSHOT_ONLY | 1–10 | 9 | `.007 / .006` | 6 | 0 / 4 |
| SNAPSHOT_ONLY | 11–100 | 73 | `.415 / .411` | 3077 | 22 / 34 |
| SNAPSHOT_ONLY | 101–1k | 96 | `3.192 / 3.186` | 25704 | 25 / 53 |
| SNAPSHOT_ONLY | 1k–10k | 41 | `23.038 / 23.014` | 187200 | 26 / 4 |
| STANDARD | 0 | 3151 | `2.017 / 1.865` | 28 | 0 / 2166 |
| STANDARD | 1–10 | 913 | `1.194 / 1.150` | 3427 | 0 / 620 |
| STANDARD | 11–100 | 1287 | `5.160 / 5.101` | 28863 | 0 / 938 |
| STANDARD | 101–1k | 964 | `42.354 / 42.283` | 198427 | 0 / 784 |
| STANDARD | 1k–10k | 132 | `223.503 / 223.458` | 324890 | 0 / 94 |
| STANDARD | >10k | 64 | `886.702 / 886.544` | 1243586 | 0 / 52 |

跨阶段累计最贵的是 `device_st`（STANDARD，最高 54,150 rows）：50 次 invocation 合计 `763.517s` wall / `763.369s` thread CPU。其次 `device_mx` `213.500s`、`device_co` `74.958s`。单个 table-stage 最高为 t4 重传 v1 的 `artifact_write / device_st`：`48.551s / 48.542s`；接着是 t4 `device_st` business materialization `44.140s`。详细列/record/change 信息保存在外部 JSON，不在 handoff 展开每一行。

## 11. C/B 层、容量估算与 Phase 6 候选

### S2b 起各阶段 C 层记录

下表统一使用 t4 的 operation wall 秒。S2b handoff §9 只记录 journey step wall，没有 operation wall；因此留空，不用 step wall 代替。S3 取其 §9 operation 记录，S4 只填实际执行的三项 operation，S5 使用现有真实数据 JSON 的 `operation_terminal_seconds`。

| 阶段 | v1 Preview | 重传 v1 Preview | v2 Preview | v1 Submit | v2 Submit | History | 各行来源 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| S2b | — | — | — | — | — | — | `p5-arch-closure-s2b-handoff.md` §9 仅有 step wall，故不换口径补值 |
| S3 | 2656.491 | 2335.359 | 2339.012 | 800.757 | 810.836 | 1375.067 | `p5-arch-closure-s3-handoff.md` §9 operation wall |
| S4 | 1677.773 | — | 1463.100 | 576.497 | — | — | `p5-arch-closure-s4-handoff.md` §9 operation wall；其余未运行 |
| S5 | 1684.782 | 1463.686 | 1477.774 | 565.761 | 573.831 | 892.522 | `s5-dc32-realdata-b79844ddc2.json` 的 `operation_terminal_seconds` |

### B 层观察（登记到 Phase 6，不在 P5 修）

- t4 Preview 主要消耗在 SQL parse、业务物化、规范 projection/digest、artifact 写入与 comparison；CPU 时间接近 wall 时间，呈 CPU-bound 特征。
- 相同 v1 重传与低变化 v2 Preview 仍完整执行上传侧解析/物化和 table work；分别观察到 1463.686s 与 1477.774s operation wall。重复 v1 Preview changed=0，v2 changed=26/312。Phase 6 可评估复用与局部处理，但须保持冻结 Contract 与相同规范事实。
- RS baseline 是逐表 Arrow read；t4 为 312 次，合计 read wall 51.847s，但本机 thread CPU `.355s`；Arrow→Python 转换 `1.492s`。没有按行发起 Repository 请求，也没有观察到 operation 空等或 worker stall。
- Submit prepare 的 mutation planning/replay 约 534–541s；Repository 实际导入用时 79s/83s。可在 Phase 6 分别分析 replay 生成和 Dolt import 的成本。
- 以上是性能候选，不构成 P5 失败；DC31 要求记录、P5 不修，除非影响 A 层。t1–t4 全部达到 operation 终态且断言通过。

### 目标外推与字节余量

Owner 的业务容量目标为约 2×t4（约 640 tables、约 493,588 canonical rows、约 11.2 MB 上传包），Preview 在 10 分钟内。以 t4 v1 Preview 的 `1684.782s` 线性外推，2×规模约 `3369.564s`（56.16 分钟），比 600 秒目标多 `2769.564s`，是目标时间的 5.62 倍。未实际跑 2×数据；单个 t4 点、数据变化比例、缓存、并发和 CPU/I/O 都会使线性外推失真。此目标属于 Phase 6 退出目标，不是 S5 门槛。

| 字节上限 | t4 实测 | 2×外推 | 上限 | 余量 |
| --- | ---: | ---: | ---: | ---: |
| replay SQL（200 MiB） | v1 `50,566,047 B`；v2 `50,572,564 B` | v1 `101,132,094 B`；v2 `101,145,128 B` | `209,715,200 B` | v1 `108,583,106 B`；v2 `108,570,072 B` |
| Catalog（2 MiB） | `286,137 B` | `572,274 B` | `2,097,152 B` | `1,524,878 B` |

### Phase 6 候选

1. 先按 DC32 下界重新制定可重复基准，再确定 2×t4 Preview 的目标值。
2. 评估 SQL parser、业务 materialization、canonical projection/table digest、canonical artifact row handling 的 native/Arrow 化。
3. 评估重复 v1 / 低变化 v2 的全量 scan 与 table 粒度缓存/增量计算；以现有 canonical summaries、Preview counts、History records 和 composites 作正确性对照。
4. 评估 ordered 比较与 STANDARD 大表处理的 CPU 成本，以及合理的逐表并发边界。
5. 分离 Submit mutation planning/replay 与 Repository import/commit 成本；保持 expected parent CAS 与冻结 artifact 语义。
6. 本次唯一新增的 BLAKE3 dev dependency 已满足测量授权；不把 benchmark harness 扩展为生产依赖或平台。

### 旧实现 t4 Preview 对照

没有获得可在本次 CT108、同一数据与同一两时钟口径下运行的旧实现。旧路径需可执行旧应用/依赖闭包及已解包数据目录；此 worktree 只提供 `legacy/` 参考代码，真实数据按约定以归档包供应，没有旧镜像/锁定环境/独立可执行入口。没有读取或解包 dump。Phase 6 讨论稿记录过旧流程约 60 秒前端等待，但它不是本次 operation 终态/完成时口径，不做数值对比。执行计划明确旧实现对照“条件允许时”且不阻塞 S5。

## 12. P5 §2A.5 逐项对照与证据包索引

| §2A.5 项 | 结果 | 证据索引 |
| --- | --- | --- |
| 1. wire 泄漏、私有导入、事务/编排环、基础层倒挂、包根归属已修；architecture gate 有边界；canonical/manifest golden 与 digest 语义仍可核对 | 本轮 `import_rules=0/0/6`，全量 architecture tests 通过。Submit frozen products 用同输入 golden 核对 schema SQL、DML、package digest 字节一致；无新的架构例外。 | `s5-import-rules-b79844ddc2.log`；`s5-b79844ddc2-full-runner.log`；§4 S5.3 表 |
| 2. Contract 执行边界、编排集中度、projection 占位风险已由实际消费者和 owning 文档核对 | §4 的 11 行均对齐或按 owner 决议修复。Project identity 的 facade 拓扑和 Submit prepare 冻结 ruleset 两项决议均未修改 Contract。 | §4 核对表；提交 `ba4ee7a5e6`, `9f1df26914`；focused/full runner 日志 |
| 3. 依赖合规、既有问题位置、真实链路与 Phase 6 候选 | 仅加 dev-only `blake3==1.0.10`；真实数据和阶段测量见 §8–§11；B 层和候选均列于 §11。 | `pyproject.toml`、`uv.lock`；外部 metrics JSON |
| 4. 语义回归、五包静态、权威 runner/容器门禁 | 五包 ruff/mypy、全量 runner、fresh RS image、全部 Compose journeys 0 skipped，t1–t4 完整真实链路通过。 | §7；CT108 `s5-b79844ddc2-*` logs |
| 5. 不可达基线清理；余项须有 owner/reason/next phase；§2A.4.1 已修或 owning 登记 | 没有不必要条目可删；只剩两组已在 §9 逐项登记的延期，共 6 个模块。 | `p5-arch-closure-design.md` §9；`architecture_baseline.py`；§3 |

## 13. 停止条件与审核状态

执行计划 §14 的停止条件均未触发：真实 Dolt 类型/同一性正常；无 Contract 例外、兼容部署或新增协议族；所有 operation 正常终态；无 t4 Submit 会话耗尽；没有需要扩大 API、Docker/Compose、依赖或生产测量插桩的改动；无未预期不可达模块；完整 runner exit 0、Compose journeys 0 skipped、真实数据 assertions 通过。

S5 审核尚未执行，故本 handoff 只给 `pass_recommended: yes`，不等于审核通过或 P5 exit。审核通过前不做 P5 exit；P5 exit cleanup 按 G10 另行安排。

## 14. 审核提示词

```text
任务：独立审核 P5 架构收口 S5。你没有参与 S5 实现；按
docs/backend-vnext/refactoring/formal/guides/slice-design-execution-and-review-guide.md §5–§6 审核，不预设结论。

审核对象：p5-s5 分支 H @ <由 git rev-parse HEAD 填入>（门禁提交 V = b79844ddc2304a23a3e6fe386f40aed671c5047b，
实现 HEAD = b79844ddc2304a23a3e6fe386f40aed671c5047b），区间 p5-s4-exit `5634dc6f9b`..H。只审该区间差异。
在只读 detached worktree 审核；测试与取证按 DC34 在 ct108-gw-dms 上进行，不在开发主机或 main 上审核。
权威依据：p5-arch-closure-execution-plan.md（§2 S5、§3 S5、§6、§7、§8.1–§8.3、§8.7、§8.9）、
p5-arch-closure-design.md（§9、§11、§13、§14）、P5 §2A.5、DC30–DC34、G10、G12、
Performance Measurement Guidance、Phase 6 planning discussion §3/§9 V2、AGENTS.md、testing-conventions.md 与本 handoff。

必须核查：
1. §2 S5 所有验收与 §3 S5 路径预算、fresh 镜像和全量 runner；运行期间的 clean worktree、起止 HEAD、exit code、provenance；
2. S4-F2 是否显式命名为 Submit poll deadline / 3-session bound、是否移除无用 checkpoint 状态和无生产调用方 helper、其他 operation 的 R5 默认行为是否不变；
3. 两组且仅两组不可达延期条目的 owner、理由、重开条件是否登记，import_rules 是否为 0/0/6；
4. §11 文档核对 11 项及 owner 决议：S4 引入的 project_identity 拓扑修复、Submit prepare 冻结 A/B ruleset 修正、golden 字节等价和所有 artifact/manifest/CAS bindings；Contract 文本是否保持未改；
5. DC32 四部分是否覆盖 Preview/Submit/History 各阶段墙钟与 CPU、逐表分布、基本操作吞吐、用户可见/完成时间、t1–t4 范围；旧实现 t4 Preview 对照限制是否合理；是否未为测量改生产代码；
6. fresh RS image identity/build label、backend/worker 与 client e2e provenance；全部五包 runner 计数与 S4 V 对照，skip 是否仅 delegated target container 而非 Compose journey；
7. t1–t4 同一 V 真实数据证据、S2b–S4 对照、composite/History/Preview facts、t4 两次 Submit 的 RS import elapsed、session count 与余量；
8. P5 §2A.5 五项逐项对照及证据索引；容量外推限制、replay SQL/Catalog 字节余量和 Phase 6 候选；
9. DC34 carried：在运行 V runner 的同一 CT108 worktree 与一致完整环境中重算 H 的 RS identity 并比较镜像 label；计算五包 manifest，与 V runner 起始 manifest 逐包 compare，确认 backend/worker 可沿用；
10. S5 停止条件状态，并确认 S5 审核通过前未宣称 P5 exit，也未做 G10 cleanup。

验证：只在 CT108 审核 worktree 运行五包 ruff/mypy 与 import_rules；核对 V 权威 runner 与真实数据日志、镜像 provenance、V→H carried 记录。不要求重跑全量 runner；若需重跑，须在 CT108 clean 已提交 worktree 上整机单飞运行。审核期间不改实现、测试或 handoff。

交付：按执行计划 §8.8 写 plans/p5-arch-closure-s5-independent-review.md，作为独立纯文档报告提交到 `p5-s5` 分支；不推送、不打 tag。审核结论只可为通过 / 定向修订 / 整体返工。S5 审核通过后再由 owner 决定下一步；P5 exit 与 G10 cleanup 另行安排。
```
