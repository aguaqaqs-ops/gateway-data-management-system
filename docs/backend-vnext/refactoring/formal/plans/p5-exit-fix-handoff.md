# P5 exit 修复 handoff

## 范围、提交与决议

- 审核基线：`85ebfb9a95`（`p5-exit-review`）；本次只处理 EXIT-F1、EXIT-F2 与 EXIT-F4 的 R2-O3。EXIT-F3 和 EXIT-F4 的另外两项未处理，审核报告未修改。
- Owner 决议：main `458b40fbea` 的治理计划 §3 第 13 项末尾；本次没有新增决议。
- 门禁提交 V：`88ba238a88af23eea00ee0d15dae504d6731dd95`。最终 handoff H 为本文所在的 handoff-only 提交；以该提交上的 `git rev-parse HEAD` 为准。
- 代码提交顺序：`4330a24961`（F1 实现）、`abba8c3114`（文件型 control DB 明细往返）、`75946afda3`（Preview 断言、F2 接线与公开导出修正）、`88ba238a88`（三项 backend mypy 修正）。均为新提交，没有 amend、merge、rebase、push 或 tag。
- 测试、镜像构建、权威 runner 和 carried 均在 `ct108-gw-dms` 的 `/home/dev/gdds-p5-exit-fix` 执行，通过 git bundle + scp + fetch 同步；`legacy` 链接指向 `/home/dev/gateway-data-management-system/legacy`。没有读取真实数据或运行 DC32 测量。

## EXIT-F1：Operation diagnostic 明细

`OperationDiagnostic` 增加可选 `details` 和 `omitted_count`，明细项为 `code`、`side`、`table_name`、`column_name`。`side` 取 `INITIAL` / `MODIFIED`；没有对应表的投影诊断允许 `table_name=null`，`column_name` 也允许为 null。代码和名称均有界；明细最多 100 项，稳定排序键为 `(side, table_name, column_name, code)`，空字段排在有值字段前。`omitted_count` 是非负 I-JSON safe integer；未省略时为 0，只有已列明细达到 100 项时才可大于 0。没有明细时序列化形态仍是 `{"code","message"}`，省略 `details` 与 `omitted_count`。

Operation Runtime Contract 从 `backend-vnext/operation-runtime/v1` 升为 `backend-vnext/operation-runtime/v2`。Control DB 继续用原有 diagnostic JSON blob，不改 schema；读写 JSON blob 和文件重开读取均保留明细。没有旧版双读或兼容路径。

失败数据流：

1. Preview 物化调用 `_materialize_uploaded_side(..., side=...)`。Storage projection 原有的全部 `ProjectionDiagnostic` 被映射为 Operation detail；本次没有改 projection 的收集逻辑。
2. `_materialize_all_sides` 对 FULL 的 INITIAL 与 MODIFIED 上传侧分别尝试物化，收集全部投影失败后统一抛出 `PreviewJobError`；MODIFIED_ONLY 只尝试 MODIFIED 上传侧。`PreviewJobError` 对明细稳定排序并限制为 100 项、累计 `omitted_count`。
3. `_publish_preview_materialization_failure` 将概要 `code` 与最多 255 字符的 `message`、明细和 omitted count 写入失败的 Step 与 terminal Operation diagnostic；摘要包括失败项数和首项信息。Operation 持久化不丢字段。
4. `/operations` 的 HTTP mapper 与 history compare orchestration 都将明细映射到 HTTP schema。Operation 与 history diagnostic response 共用对应字段形态；OpenAPI golden 和 schema 断言已更新。

Preview 入口唯一测试 owner 选为 `vnext/backend/tests/test_preview_job_materialize.py`：这里通过生产物化 handler、Control DB、Operation response mapper 一次覆盖投影到公开 Operation 的端到端失败路径。共享参数表覆盖多表失败、同表多列失败、FULL 两侧同时失败、101 项失败（保留有序的前 100 项并报告 omitted=1）。断言还确认整体 FAILED、没有 materialize checkpoint、assemble step 不存在、没有 ready closure / current preview / repository operation effect。

相关测试 nodeid：

- `tests/test_preview_job_materialize.py::test_projection_failures_publish_complete_bounded_operation_details[multiple tables]`
- `tests/test_preview_job_materialize.py::test_projection_failures_publish_complete_bounded_operation_details[multiple columns in one table]`
- `tests/test_preview_job_materialize.py::test_projection_failures_publish_complete_bounded_operation_details[both full input sides]`
- `tests/test_preview_job_materialize.py::test_projection_failures_publish_complete_bounded_operation_details[details over operation limit]`
- `tests/test_operation_contracts.py::test_operation_diagnostic_details_round_trip_in_stable_order`
- `tests/test_operation_contracts.py::test_operation_record_rejects_invalid_diagnostic_details[...]`（共享参数表逐项覆盖明细与 omitted 配对、side、非满额 omitted、bool、字段长度和超过 100 项）
- `tests/test_sqlite_operation_store.py::test_operation_mapping_round_trips_diagnostic_details_json_blob`
- `tests/test_sqlite_operation_store_integration.py::test_operation_store_commits_and_reads_back_after_reopen`
- `tests/test_http_openapi.py::test_openapi_operation_diagnostic_details_match_the_bounded_contract`

## EXIT-F2：ADDITIVE 后读取旧基线

`test_additive_ruleset_previews_nonempty_baseline_from_older_manifest` 复用 Preview harness、fake Repository 与 metadata port。测试从非空 baseline catalog 构造 A 的 manifest；B 保留 A 的全部规则，只追加此前不存在的 exact `new_preview_table` 规则（`BROWSE_ONLY`、`PROJECT`、`DDL_PRIMARY_KEY_OR_KEYLESS`、`OrderedPolicy.NONE`）。因此 B 相对 A 是 ADDITIVE，A 的既有 storage projection 未变。

测试将 baseline commit metadata 固定为 A，并把新受理 Preview 的运行期 ruleset 固定为 B。MODIFIED_ONLY 上传包创建 `new_preview_table` 并插入一行；生产物化步骤成功，baseline 仍从 pinned `commit-base` 读取且 manifest provenance 为 A，上传侧 manifest / 运行期 ruleset 为不同的 B。生产 assembly handler 随后成功完成；捕获的实际 pair pipeline surface 显示 B 新增规则的效果：`new_preview_table` 为 `ADDED_TABLE`、`content_changed=true`，`records_ref=null`（browse-only 语义）。既有陈旧 Preview 拒绝及激活后恢复失败用例未改动，并在 V runner 中通过。

nodeid：`tests/test_preview_job_materialize.py::test_additive_ruleset_previews_nonempty_baseline_from_older_manifest`。

## EXIT-F4 / R2-O3

`tests/test_http_admission_shutdown_process.py` 的模块 marker 设为 `[pytest.mark.integration, pytest.mark.serial]`，保留 serial 并将 3 个子进程 / 信号用例归入 integration。V 上执行 `pytest --collect-only -m unit tests/test_http_admission_shutdown_process.py`，输出 `collected 3 items / 3 deselected / 0 selected`；pytest 对空选择返回 5，这是预期的 collect-only 结果，不是门禁失败。

## 验证与记录

所有 V 验证使用 `umask 022`、`HOME=/root`、`LC_ALL=C.UTF-8`、指定 PATH、`TMPDIR=/home/dev/gdds-test-tmp`、`GATEWAY_UV_CONSUME_SKIP_LOCK_ASSERT=1`。未设置 `UV_CACHE_DIR`、`GATEWAY_TEST_PACKAGES`、`HYPOTHESIS_STORAGE_DIRECTORY` 或 `GATEWAY_TEST_BASETEMP`；全量 runner 设置 `GATEWAY_TEST_WORKERS=48`。日志目录为 `/home/dev/gdds-p5-closure-s1-gate-logs/p5-exit-fix/`（0700），日志和保存的 manifests 显式 chmod 0600，manifest 目录为 0700。

| 顺序 | 结果 | ct108 记录 |
| --- | --- | --- |
| 五包 Ruff / mypy | 五包通过；mypy 文件数：shared_kernel 34、repository_contracts 15、repository_client 26、backend 486、repository_service 200。 | `static-import-rules-88ba238a-20261023.log` |
| `import_rules` | 0 import violations / 0 runtime cycles / 6 已登记 unreachable modules；exit 0。 | 同上 |
| focused 全文件 | 原 focused 集合（Preview、R2-O3、Operation/control DB、OpenAPI）加 `tests/test_real_dump_dc32_measurement.py`；845 passed、1 条既有 Starlette deprecation warning、exit 0。该 DC32 文件是 synthetic/pure test；没有运行测量或读取真实 dump。 | `focused-88ba238a-20261023.log` |
| R2-O3 unit collect | 3 deselected / 0 selected；pytest command exit 5（零项选中的预期状态）。 | `r2-o3-unit-collect-88ba238a-20261023.log` |
| preflight | clean V；无 `dolt` 进程、无容器、Compose projects 为 `[]`、8000 无 listener；legacy 与 TMPDIR 存在。Docker daemon identity 已记录。 | `preflight-88ba238a-20261023.log` |
| fresh repository-service image | `build-repository-service-image.sh` 在 V 上成功。image ID `sha256:22cd13dfa799bec4c8f20547dae051c211d1d050c02ddf3aac4f51781429c979`；revision label 为 V；build-input revision `b93748c04e63be4eeece66cb5abaadf13fd7b6d3` 与 source-tree `sha256:b24fa92dbbb59d00617eec838a22ca947fa98fe42fab996770aa9b9e20f7f15c` 与 identity helper 匹配；uv-lock label 与 lock SHA 匹配。 | `fresh-rs-build-88ba238a-20261023.log` |
| 权威全量 runner | V clean worktree，起止 HEAD 均为 V；workers=48、未筛包；242 + 152 + 154 + backend 2,912 parallel / 39 serial + repository_service 1,730 parallel / 205 serial；合计 5,434 passed、1 个 delegated target-container cgroup smoke skip，runner exit 0。 | `full-runner-88ba238a-20261023.log` |
| postflight | clean V；无 Dolt、容器、Compose project 或 8000 listener；五个 runner Hypothesis package 目录均不存在，storage root 为空；RS identity 与 labels 仍匹配。 | `postflight-88ba238a-20261023.log` |

权威 runner 起始逐包 manifest 直接从 V runner 日志提取并校验 HEAD / clean 状态，存于 `v-manifests-88ba238a/`；提取记录为 `manifest-extraction-88ba238a-20261023.log`。它们是 H carried 的 V 来源，不是 focused 运行的 manifest。

## 停止与顺序偏差记录

候选 `75946afda3` 的第一次全量 focused 发生在静态检查之前，838 passed 的结果**不作为 V 证据**。随后 backend mypy 报了三项并按停止规则暂停；原始日志 `static-import-rules-20261023.log` 保留。新提交 `88ba238a88` 只改三处机械问题：DC32 benchmark 调用传 `side=OperationDiagnosticSide.MODIFIED`（仅诊断侧标识，不改测量口径）；OpenAPI 测试先将 `items` 收窄为 dict 再取 `$ref`（断言不变）；删除 F2 测试中多余的 `type: ignore[attr-defined]`。没有改 `_materialize_uploaded_side` 签名或 F1/F2 方案。

恢复后严格按五包静态检查 / import_rules → focused → marker collect → preflight → fresh RS → 全量 runner → postflight 顺序执行；所有 V 证据均来自 `88ba238a88`。此前 `abba8c3114` 的 7 项 debug focused 接线失败已在 `75946afda3` 修正；其结果也不作为验收证据。没有遇到 auto mode 拒绝，没有读取真实数据，没有重跑 DC32 测量。`85ebfb9a95..V` 共 16 个文件、1,082 insertions / 44 deletions；生产行为变化限于 projection failure diagnostics，Preview 成功路径语义未改。F2 是验证 ADDITIVE 场景的测试，不引入运行时语义改动。

## H carried

本文首次提交后，在 V runner 的同一 ct108 worktree、同一环境下执行 carried：先复核 RS identity 与 labels，再以 V runner 完全相同的 `HYPOTHESIS_STORAGE_DIRECTORY=/home/dev/gdds-test-tmp/gateway-runner-hypothesis/<package>` 为每个包生成 current manifest，确认目录无残留，并与 `v-manifests-88ba238a/<package>.json` 逐包 compare。Compare 结果及日志路径将在携带该结果的最终 handoff-only 提交中记录；本段不能作为 carried 通过证据。
