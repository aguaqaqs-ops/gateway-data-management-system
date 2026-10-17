# P5 架构收口 S3 STOP handoff

- 状态：**STOP，等待 owner 决定公开逐表 Preview 事实的接口范围；不是 S3 完成候选，不交独立审核，不进入 S4。**
- 日期：2026-10-17
- 分支 / worktree：`p5-s3` / `/home/dev/gdds-p5-s3`
- `range_start`：tag `p5-g11b-exit`，`944982eb910dab9cbfc117a976dea6721cdd6ca2`
- kickoff base：`be5fd5a9708ebb8a4d3ffb619f58ab75819c3576`
- `range_start..kickoff base` 仅有审核方提交：合并提交 `e8b5322b3c3af8d832080fbbc98255ee52daf80c`，文档提交 `be5fd5a9708ebb8a4d3ffb619f58ab75819c3576`。
- 当前实现 HEAD：`e988763393d119e27313ba7dba67143dd82631c3`
- 最终门禁 `V`：**无**。曾在候选 `6a1e0020335cf8a1b51845026d01a9d826e7915d` 上启动权威 runner，但有测试失败并因主机并发而中断；详见 §7。
- `H`：**无**。本文提交只记录 STOP handoff，不是门禁后 handoff-only 候选。
- main 仍为 kickoff base；没有合并、rebase、打 tag 或推送。

## 1. 停止原因与 owner 决定

S3 真实数据验收要求通过公开 HTTP 接口取得 Preview 的逐表状态，以证明除 `composite_signal_point` 外，各表状态与 S2b 对照一致。当前公开接口不能提供这项事实：

- `GET /v1/workspaces/{workspace_id}/preview-results/{preview_result_id}` 的 `PreviewResultResponse` 只返回标识、baseline、`derived_stale`、`bundle_digest` 和创建时间，没有逐表状态。
- 同资源的 `/bundle` 路由返回 `application/octet-stream`。当前 bundle manifest 中的 surface 只有 artifact 引用；manifest 不含 surface 内容，`ArtifactRef` 也没有公开下载 URL。
- Backend HTTP 路由中没有按 artifact id 读取 surface 的公开端点。现有 Compose 支撑函数 `read_preview_surface_table_states` 是通过 `docker compose exec backend` 读取容器内 `LocalArtifactStore`，不能用于规定的主机侧公开 HTTP 真实数据证明。

因此，按现有接口无法按要求生成 A/B/C 之外的逐表对照证据，也不能开始 t1。补齐证据需要新增或扩展 Backend Preview HTTP API / DTO；该接口不在 S3 §3 路径预算中，也会建立新的公开契约。S3 授权没有明确覆盖这项扩展。我没有加入该接口，也没有把容器内读取伪装成公开接口证据。此处需要 owner 决定：批准一个有 owning Contract 和路径预算的 Backend 公开逐表读取接口，或调整本阶段逐表证据要求并指定现有公开事实来源。

这不是 Repository Service API 变更：本分支未修改 Repository Service Contract、wire、HTTP DTO、Dockerfile、Compose 文件或依赖。现有证据也没有触发设计 §14 列出的类型、项目身份、兼容、初始库或新协议停止项。停止点是 S3 真实数据验收在当前公开接口上的可观测性缺口；owner 决定前不运行真实数据、最终 runner、carried 或 S3 exit 审核。

## 2. 子步与提交

| S3 内容 | 提交 | 结果 |
| --- | --- | --- |
| DC20：派生表 `source_table VARCHAR(64)` 和超长诊断 | `f5aa52a39d` | 已实施；使用现有 `COMPOSITE_LOGIC_FAILED` diagnostic，不改 composite contract。 |
| Preview 上传侧改为业务物化，加入 XML 或稳定 EMPTY 来源 | `280bb1034d` | 已实施；`snapshot_digest` 来源现在绑定 XML 摘要或 EMPTY 摘要。 |
| DC8：无效 `logics.xml` 与 composite 业务失败导致 Preview FAILED | `6afdbc5de6` | 已实施；沿用 P3-R3 diagnostic。 |
| 规则、投影、真实 Repository Service/HTTP Arrow 同一性测试 | `4744b5c5e0` | 已补测试；生产 composite registry 规则没有重复实施。 |
| composite 规范投影 golden | `59f204f7f5` | 已增加 golden，细节见 §5。 |
| 单改 `logics.xml` 的 Preview → Submit → History Compose 旅程 | `9f7af5fd13`, `84fda99947`, `8497f7c886`, `906618665f`, `6999abd2e3`, `a61419dc31` | 在既有 serial History Compose 测试和同一栈中扩展；修正 oracle、review scope、workspace 隔离与 unbound 行期望。没有增加独立测试函数或独立栈。 |
| 移除 S3 不可达基线 8 项、更新架构测试 | `d93c76e8f4`, `48e8f190b5`, `6a1e002033` | 已移除 8 项；更新 `test_architecture.py` 的合成 facade 探针。 |
| 更新 canonical compare 对 EMPTY composite 表的实际状态断言 | `3e01baff21`, `e988763393` | authoritative runner 首次发现比较基线没有 composite 表时，EMPTY 来源会产生零行 `composite_signal_point`，其表状态是 `ADDED_TABLE`，而 `t` 为 `UNCHANGED`。测试现按该实际状态表达；修正后的 focused unit 通过。 |

所有提交使用 `refactor(p5-closure-s3): ...` 并带 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` trailer。

## 3. 路径预算

S3 预算内改动：

- Production：`application/preview_jobs.py`、`capabilities/snapshot_materialization/compose.py`。
- Tests / support：`test_snapshot_materialization_business.py`、`test_preview_job_materialize.py`、`test_storage_projection_core.py`、`test_canonical_snapshot_identity.py`、`test_table_rules_contracts.py`、`tests/support/upload_http_packages.py`、`tests/support/compose_gate_harness.py`、`test_history_compose_e2e.py`。
- Golden：新增 `vnext/fixtures/golden/storage-projection/composite-signal/canonical.json`。
- 按 S3 内容要求删除不可达项：`tests/architecture_baseline.py`。

预算外改动逐项说明：

| 路径 | 原因 |
| --- | --- |
| `vnext/backend/tests/test_architecture.py` | S3 删除 8 个不可达模块后，架构测试仍把 facade consumer 计入 synthetic probe。更新探针边界和 expected reachability，避免把已接入 consumer 重新误报为不可达；没有改 import 规则豁免。 |
| `vnext/backend/tests/test_comparison_canonical_domain.py` | 当前 authoritative runner 发现 EMPTY 来源新增派生表后，原有全表 `UNCHANGED` 断言不成立。测试现在明确断言 composite 表为 `ADDED_TABLE`、普通表 `t` 为 `UNCHANGED` 且没有行记录。该行为应由 owner 在真实 t1 对照中确认。 |
| 本 handoff 文档 | S3 STOP 记录按执行计划 §8.2 交 owner。 |

未启用条件路径 `capabilities/composite_signal/contracts.py`，未改 `table_rules/registry.py`：S2a 的 composite 规则已按设计 §4.4 落地，S3 只核对并测试事实。未改任何 Repository Service / Backend HTTP DTO、Contract、wire、Dockerfile、Compose 文件或依赖；未改 `uv.lock`。

## 4. 导入规则

命令：`cd vnext/backend && ../scripts/uv-consume.sh -C . run python -m tests.support.import_rules`

| 时点 | 违例 | 运行时环 | 不可达 |
| --- | ---: | ---: | ---: |
| kickoff base `be5fd5a970` | 0 | 0 | 14 |
| 当前实现 HEAD `e988763393` | 0 | 0 | 6 |

被移除的 8 项为 `composite_signal._ast`、`_bind`、`_digest`、`materialize`，`snapshot_materialization._catalog`、`compose`，`table_access._xml_parser`、`xml`。剩余 6 项为 canonical row hash 与 external target sync 模块，属于其他阶段范围。

## 5. Golden、digest、checkpoint

- S2a `396cfa2d28` 已完成的 composite 规则在 S3 未重复修改：键为 `source_table, point_gid`；`dev_addr`、`device_gid`、`point_payload_json` 丢弃；`formula_ast_json`、`point_name` 保留但 compare-excluded。`test_table_rules_contracts.py` 核对这些规则事实。
- 新 golden `vnext/fixtures/golden/storage-projection/composite-signal/canonical.json` 描述规范形态：`source_table VARCHAR(64)`，键 `source_table, point_gid`，保留列 `source_table, point_gid, point_name, formula_digest, formula_ast_json`，忽略列按上述规则丢弃。golden 内 schema digest 为 `sha256:45ab9549945be08b1386620fbc3d2f88f28a6818852dd3dab1628fd34582104c`，内容 digest 为 `sha256:369e048b093be7a8ec62de2f1d31648bec77b3b595d660cc1d5ac4d2f1eb73b1`，golden 文件 SHA-256 为 `1e247286337087123e288a8d7397b896948f7c59933b08ff348426c75e2e8ee1`。其变化来自规则后的列投影和 `source_table` 类型，不承担旧形态兼容。
- Preview 上传侧现调用 `materialize_business_snapshot`。缺失 XML 使用稳定 EMPTY 来源；存在 XML 时用 XML 内容摘要。现有 `SnapshotSourceContext.composite_logic_source_digest` 进入 `snapshot_digest`：XML 内容变化会改变来源摘要，缺失 XML 则使用 EMPTY 摘要。EMPTY 与 XML 的来源身份不同；canonical state digest 只由规范派生表状态决定。
- `composite_signal_point` 现在作为规范投影后的表进入存储、比较和风险。公式变化使 `formula_digest` 和对应行比较变化；Compose focused 旅程观察到该行 `MODIFIED`、`row_modified_count=1`，History 比较 `record_count=1`。
- Checkpoint 没有新增字段名或升级 envelope / materialize-side contract version。`SnapshotSourceContext` 已有的 `composite_logic_source_digest` 字段现在在 materialize_inputs checkpoint 引用的 snapshot 中带 XML / EMPTY 值；规范表集合及 canonicalization manifest 的既有闭包现在可包含 `composite_signal_point`。这是载荷值与闭包内容的变化，不是 checkpoint shape/version 变更。DC6 下不保留旧 payload 兼容路径。
- 除 golden 和以上 snapshot/state/bundle/closure digest 的派生变化外，没有修改其他 golden 或 checkpoint fixture。由于未跑 S3 真实数据，不能报告真实各档摘要值。

## 6. Focused 与静态验证

以下均为开发期 focused 结果，不替代 V 上的权威 runner；调试日志均位于 worktree 外的 `/home/dev/gdds-p5-closure-s1-gate-logs/`。

| Owner / 命令 | 结果 |
| --- | --- |
| `test_snapshot_materialization_business.py`，unit | 13 passed；覆盖长度、VARCHAR 键类型和业务 EMPTY 来源。 |
| `test_preview_job_materialize.py`，unit | DC8 修正后 9 passed；覆盖无效 XML/业务规则失败诊断和缺失 XML 的 EMPTY 摘要。 |
| business + storage projection + table rules focused unit | 70 passed。 |
| `test_canonical_snapshot_identity.py`，integration | 1 passed，6.01s；真实 Repository Service 导入后经 HTTP Arrow 读回 composite `VARCHAR(64)` 键列。该次在 `a61419dc31`，不是最终 V。 |
| `test_history_compose_e2e.py::test_compose_history_compare_journey_zero_write_restart`，integration + serial | 1 passed，437.46s；同一既有 Compose 栈中完成 XML-only 变化、Preview、Submit、Repository 读回、History。日志报告通过，但之后发现同机有并发 pytest / Docker workload；按单飞规则不把它作为门禁证据。 |
| `test_architecture.py` focused | 77 passed；在 `6a1e002033`。 |
| `test_comparison_canonical_domain.py`，unit | 修正后 1 passed，0.91s；在 `e988763393`。 |
| 五包 Ruff + mypy | 当前实现 HEAD 通过。Ruff 全部 `All checks passed`；mypy：shared_kernel 34、repository_contracts 15、repository_client 26、repository_service 198、backend 476 source files，无 issue。 |
| `import_rules` | 当前实现 HEAD 为 0 / 0 / 6，见 §4。 |

已发生的失败或作废调试运行：

- `s3-debug-canonical-identity.log`：失败原因是新 worktree 的 `repository_service/.venv` 缺失，不是测试断言；运行 `prepare-dev-dependencies.sh` 后，`s3-debug-canonical-identity-rerun.log` 通过。
- `s3-debug-preview/existing-focused.log`：旧表集合断言只含 `t`；S3 增加 composite 派生表后更新为包含两表。
- `s3-debug-preview/dc8-focused.log`：测试把 EMPTY 来源误当作零行表；fixture 实际产生两个 unbound composite point，断言改为检查实际派生结果，随后 9 项通过。
- `s3-debug-compose-history.log`：History oracle 未声明派生 composite 表，bundle digest 不同；更新 oracle。
- `s3-debug-compose-history-oracle.log` 与 `s3-debug-compose-history-scope.log`：先后遇到 Submit occupancy 冲突；隔离版本 workspace 后继续。
- `s3-debug-compose-history-occupancy.log`：复用的 reviewer scope 遇到 `REVIEW_VERSION_CONFLICT`；改用已授权 scope 后继续。
- `s3-debug-compose-history-final.log`：oracle 预期一行，实际含一个额外 unbound point；更新为对真实两行状态的断言。随后 `s3-debug-compose-history-composite.log` 通过，但不具备 clean host 单飞证据。
- 当前 candidate runner 在 `6a1e002033` 首先失败于 `test_comparison_canonical_domain.py` 的 all-UNCHANGED 断言；在 `3e01baff21` / `e988763393` 修正为显式 `ADDED_TABLE` 语义并 focused 通过。该修正尚未由权威 runner 验证。

## 7. 权威 runner、主机并发与镜像

在当时 clean 的候选 `6a1e0020335cf8a1b51845026d01a9d826e7915d` 上启动了要求的命令：

```text
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh
```

日志：`/home/dev/gdds-p5-closure-s1-gate-logs/s3-v-authoritative.log`。日志记录 start/end HEAD 相同、start/end worktree status clean。结果如下：

| 批次 | 结果 |
| --- | --- |
| shared_kernel | 242 passed |
| repository_contracts | 152 passed |
| repository_client | 154 passed |
| backend parallel | 2,821 passed，1 failed；失败是上节说明的 canonical compare 断言 |
| backend serial | 4 passed，2,822 deselected；后续被中断 |
| repository_service parallel | 1,684 passed，1 skipped |
| repository_service serial | 已开始，尚无结果汇总 |
| runner | 因 SIGINT 退出，exit code 141；不是成功门禁 |

该轮期间发现主机上有另一项并发 pytest / Docker workload，初始 preflight 未检出。为遵守整机单飞，发送 SIGINT 中断的是本轮 runner；没有停止或修改其他任务。该运行同时存在 backend 测试失败，因此整体作废。修正后的 `e988763393` 没有重跑完整 runner。

未执行 S3 真实数据 t1–t4；没有 dataset 结果、A/B/C 测量、S2b 对照表或 operation 终态证据。未形成有效 V，没有最终镜像 provenance、RS labels identity 或 carried 判定。S3 新增 Compose 旅程要求重建当前 HEAD；尚未对任何最终候选完成这一步。

禁止触碰的两个本地测试镜像只读检查结果仍为初始 ID：

- `gateway-repository-client-e2e:local`: `sha256:7883e067020adbdb84f8d7e305218e492f161058b85fa7b74f774acc27811368`
- `gateway-repository-client-e2e-base:local`: `sha256:dafde407833e087cc619da34b3e352e7fa85e63d6138ed8d516cdccfa3e46764`

没有对这两个镜像执行 `docker rmi` 或重新 tag。

## 8. Owner 决定后恢复 S3

请先决定逐表 Preview 状态的公开证据路径及其契约归属。owner 决定前，当前分支仅是部分实现加 STOP handoff：不得把它标为 S3 pass，不交 `p5-s3-exit` 审核，不打 tag、不合并 main、不推送，也不开始 S4。若批准新增 Backend HTTP API，应先明确 owning Contract 与路径预算，再在 S3 范围内继续；若调整验收，则需指出可用的公开 HTTP 事实来源及如何逐表复核 S2b。

