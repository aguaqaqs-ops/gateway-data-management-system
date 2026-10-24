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

handoff 首次提交 `42706ba7cf` 后，在 V runner 的同一 ct108 worktree、相同环境下执行了 carried。RS 当前 identity 的 build-input revision 与 source-tree digest 均匹配 V 镜像 labels；uv lock label 也匹配。镜像 ID 只记录，不作为等价条件。

五包均使用 V runner 相同的 `HYPOTHESIS_STORAGE_DIRECTORY=/home/dev/gdds-test-tmp/gateway-runner-hypothesis/<package>`，目录在 manifest 前后均不存在；与 V runner 起始 manifest 的 compare 全部为“可沿用”，`changed_components=[]`，source/current total digest 相等：

| Package | V/current total digest | Result |
| --- | --- | --- |
| `shared_kernel` | `630927157f24e0aaddab1a98199d19cd8f979246181f958f1075f5c76cedbb5f` | 可沿用 |
| `repository_contracts` | `a7025c2aeee34e562739bbff0af3e1cd4d7cc3b524baa56e5b95ec05b50d5425` | 可沿用 |
| `repository_client` | `ac29d6e19391d9deca18bfe43994766627183312c211314550363e9945270885` | 可沿用 |
| `backend` | `e738203b9d7dbca9ca579151919564cd58d1ee287f30b668b8106456542cc816` | 可沿用 |
| `repository_service` | `b80d22fd57ee5af0f6f8843c2541034b1ab00ccb9474ff61c4b5759ff32e59b3` | 可沿用 |

H1 carried 日志为 `h1-carried-42706ba7cf-20261023.log`；current manifests 与 compare JSON 分别在 `h1-current-manifests-42706ba7cf/`、`h1-compares-42706ba7cf/`。本 handoff 的最终记录提交只增加上述 carried 证据；提交后会在同一 worktree 重做同样检查，最终 H 的 carried 日志预定为 `h2-carried-final-20261023.log`，current manifests / compares 位于对应的 `h2-*-final/` 目录。最终 H 的 post-commit compare 以该日志为准。

## EXIT-R1-F1 第二轮：投影诊断省略计数

### 原因与修复

复审 `p5-exit-rereview` 提交 `e9f80f8acc` 的 §9.3 指出，Storage Projection 的 `MAX_DIAGNOSTICS = 1024` 只限制保留列表，超出部分在投影聚合及 canonical 合并处被丢弃而没有计数。Preview 因此只能对收到的条目计算 Operation 的 100 项明细上限：例如 MODIFIED_ONLY 的三张表各有 400 个失败列时，真实失败数是 1,200，旧结果却把 1,024 当作总数。

`ProjectionResult` 与 `CanonicalProjectionResult` 现在都要求调用方提供非负整数 `omitted_diagnostic_count`，没有默认兼容值。COMPLETE 结果必须是 0；值大于 0 时，`diagnostics` 必须正好保留 1,024 项。所有构造点均已传递真实值或显式传 0，包括 `infrastructure/repository_write/import_publication.py` 的冻结导入结果。

当前各处计数如下：

1. `_project_storage` 在 runtime / snapshot / `_selected_inputs` 失败返回前，按异常诊断总数减去保留数计算省略量。
2. `_project_storage` 的逐表投影循环每次只把尚有容量的诊断加入有界列表，并将 `len(exc.diagnostics) - 实际追加数` 累加到省略量；后续表继续处理并计数。
3. `project_canonical_table_set` 收集投影前的 reader / binding 错误时同样保持最多 1,024 项；与 `project_storage` 合并时，累加其上游省略量和本次合并容量不足而省略的数量。
4. canonical snapshot table 组装失败时继续有界收集；对应 FAILED 构造保留此前累计的省略量。两个 canonical FAILED 返回点都不再静默切片。

取消和超时仍立即返回单条 `PROJECTION_CANCELLED` / `PROJECTION_TIMEOUT` 诊断，`omitted_diagnostic_count=0`。未增加无界诊断列表、artifact、证据状态或状态机。

Preview 上传侧将 capability 的省略量传给 `PreviewJobError.diagnostic_omitted_count`，概要消息的数量使用“收到的诊断 + 上游省略数”。FULL 会先尝试 INITIAL 和 MODIFIED 两侧，随后合并两侧诊断与省略量，再按 Operation 的 100 项上限累计本层截断；MODIFIED_ONLY 只处理 MODIFIED。最终公开不变量为 `len(details) + omitted_count == 完整失败数`，message 仍不超过 255 字符。Operation 持久化、control DB JSON diagnostic blob 和 HTTP mapper 沿用上一节已验证的数据通路。

明细选择规则：capability 按投影处理顺序保留前 1,024 条；Operation 从这个保留集中按 `(side, table_name, column_name, code)` 稳定排序，再取前 100 条。故列出的条目有序且结果确定，但不承诺是全部失败中的全局排序最小 100 条。该规则没有改变成功路径语义。

### 测试

F1 唯一行为 owner 仍为 `vnext/backend/tests/test_preview_job_materialize.py`：通过生产 Preview materialization、Control DB 重读和 `operation_to_response` 一次验证 capability 到公开 Operation 的完整失败路径。

`PROJECTION_FAILURE_CASES` 新增两项：

- `modified projection counts failures beyond capability limit`：MODIFIED_ONLY，3 张表各 400 个 DECIMAL 失败列，并含合法 INT 主键；每张表共 401 列，低于 parser 512 列上限，期望总数 1,200。
- `full projection counts failures beyond capability limit on both sides`：FULL，INITIAL 和 MODIFIED 各 3 张表、每表 400 个失败列，期望总数 2,400。Operation 列出的 100 项全部来自 INITIAL，且按稳定排序键有序。

两项复用既有参数化测试，断言 Operation 为 FAILED、没有 READY closure / assemble step / Repository effect、details 不超过 100、明细与 omitted 总数精确、概要消息包含完整总数，且 Control DB 读回与 HTTP mapper 结果一致。既有 101 项边界用例和 F2 ADDITIVE 用例均保留。`test_storage_projection_contracts.py` 的参数表对两种 result contract 覆盖负数、COMPLETE 非零、未达上限却有正 omitted 三类拒绝；capability 截断总数只由 Preview 端到端用例证明。

新增参数用例 nodeid：

- `tests/test_preview_job_materialize.py::test_projection_failures_publish_complete_bounded_operation_details[modified projection counts failures beyond capability limit]`
- `tests/test_preview_job_materialize.py::test_projection_failures_publish_complete_bounded_operation_details[full projection counts failures beyond capability limit on both sides]`
- `tests/test_storage_projection_contracts.py::test_projection_results_validate_omitted_diagnostic_count[negative]`
- `tests/test_storage_projection_contracts.py::test_projection_results_validate_omitted_diagnostic_count[complete with omissions]`
- `tests/test_storage_projection_contracts.py::test_projection_results_validate_omitted_diagnostic_count[omissions below cap]`

### V 与验证记录

本轮 V 为 `6badf722c9e8e243e7802bb37ae1afe8893d4872`，基于 H `ddd1b2a1cf50eb046243b66bea0c69022b25330c`。其前一候选 `573b2c0d12` 的 backend mypy 因测试把 `int` 与 `int | None` 相加而按停止规则终止；`6badf722c9` 只在该求和断言前加入 `assert persisted.diagnostic.omitted_count is not None`，没有改类型、语义或其他文件。此修正提交重新从五包静态检查开始验收。

`573b2c0d12` 上此前 508 项 focused 调试通过，但该结果不作为 V 证据。正式候选 `6badf722c9` 的五包静态检查 / `import_rules` → focused → R2-O3 unit collect → preflight → fresh RS → 全量 runner → postflight 按序从头执行；Focused 全文件 631 passed，随后单独复跑 MODIFIED_ONLY 3×400 nodeid，1 passed。

| 顺序 | 结果 | ct108 记录 |
| --- | --- | --- |
| 五包 Ruff / mypy | 五包均通过；mypy 文件数：34 / 15 / 26 / 486 / 200。 | `static-import-rules-6badf722c9-20261024.log` |
| `import_rules` | 0 import violations / 0 runtime cycles / 6 registered unreachable modules。 | 同上 |
| Focused 全文件 | 631 passed、1 条既有 Starlette deprecation warning；随后单独记录 MODIFIED_ONLY 3×400 用例 1 passed。 | `focused-6badf722c9-20261024.log` |
| R2-O3 unit collect | 3 deselected / 0 selected；pytest exit 5 是空选择的预期值，核对脚本 exit 0。 | `r2-o3-unit-collect-6badf722c9-20261024.log` |
| Preflight | clean V；无 Dolt 进程、容器、Compose 项目或 8000 listener；Docker daemon identity `f4933ba1-00e8-4655-9011-44c9c2d2b161`。 | `preflight-6badf722c9-20261024.log` |
| Fresh repository-service image | 正式构建脚本成功；image ID `sha256:ed8c0d7bbf9e0c49ece0783fcf108d03fbfcaffc8cd56e626917f65c1d49dc41`。revision label 为 V；build-input revision `b93748c04e63be4eeece66cb5abaadf13fd7b6d3`、source-tree `sha256:b24fa92dbbb59d00617eec838a22ca947fa98fe42fab996770aa9b9e20f7f15c`、uv-lock `6dc9659f0aeea1b4b1e9bb0e901796ccb0dda3f99f4a0fc04932ede29ce68b11` 均与 identity / lock 一致。 | `fresh-rs-build-6badf722c9-20261024.log` |
| 权威全量 runner | 五包通过；242 + 152 + 154 + backend 2,917 parallel / 39 serial + repository_service 1,730 parallel / 205 serial = **5,439 passed，1 skipped**；runner exit 0。 | `full-runner-6badf722c9-20261024.log` |
| Postflight | clean V；无 Dolt、容器、Compose 项目或 8000 listener；五个 runner Hypothesis 目录均不存在；RS labels 仍匹配。 | `postflight-6badf722c9-20261024.log` |

V runner 起始 manifests 已从实际全量 runner 日志提取并校验 clean HEAD，位于 `v-manifests-6badf722c9/`；提取记录为 `manifest-extraction-6badf722c9-20261024.log`。五包 total_digest：

| Package | V runner total_digest |
| --- | --- |
| `shared_kernel` | `630927157f24e0aaddab1a98199d19cd8f979246181f958f1075f5c76cedbb5f` |
| `repository_contracts` | `a7025c2aeee34e562739bbff0af3e1cd4d7cc3b524baa56e5b95ec05b50d5425` |
| `repository_client` | `ac29d6e19391d9deca18bfe43994766627183312c211314550363e9945270885` |
| `backend` | `145ce59abb434326c79994e5254f0beb41974610584d30544dd4113dbba34387` |
| `repository_service` | `8bf2f982abbadcafe27498a2f32e79b81e7800919ffe83de13fb2d6a21483c33` |

相对上一 H `ddd1b2a1cf`，V 的 `git diff --stat` 为 7 个文件、178 insertions / 27 deletions；改动限于投影诊断省略计数的 capability / Preview 失败路径及对应构造与行为测试。成功投影结果始终提供 0，成功路径语义不变；没有改 Operation Contract 文本、control DB schema、RS API 或 storage projection 的诊断产生逻辑。本轮依据 `458b40fbea` 的 DC33 决议不重跑真实数据，也不运行 DC32 测量。未遇到 auto mode 拒绝。

本节提交后在 V runner 的同一 ct108 worktree 执行 H carried；carried 比较与最终 handoff commit 的记录随后附于本节。来源必须直接使用上述 V runner manifests，不引用其他 carried 结果。
