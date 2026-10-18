# P5 架构收口 S3 完成 handoff

- 状态：**V 门禁与真实数据验收完成；handoff 已提交。H0 与最终 H 的 carried 记录见 §7；等待独立审核。审核通过前不开始 S4。镜像记录中披露一项 runner 构建副作用，交 reviewer 判断其对退出的影响。**
- 日期：2026-10-18
- 分支 / worktree：p5-s3 / /home/dev/gdds-p5-s3
- range_start：p5-g11b-exit，944982eb910dab9cbfc117a976dea6721cdd6ca2
- kickoff base：be5fd5a9708ebb8a4d3ffb619f58ab75819c3576
- range_start..kickoff base 中仅有审核方合并提交 e8b5322b3c3af8d832080fbbc98255ee52daf80c 和文档提交 be5fd5a9708ebb8a4d3ffb619f58ab75819c3576。
- 实现 HEAD / V：dc9c08a410829f303aae1e0f826c674b335cb94b；clean V 的权威 runner、t4 完整真实数据与 t1 冒烟均通过。
- H：本 handoff 文档提交。V..H 仅有本 handoff 文档提交。
- 两项 owner 决议：main 上的 `7c77b5e8c8` 与 `c09c95fd81`。本实现分支没有合并或 rebase main、打 tag 或推送。

## 1. 停止与恢复

本节保留两次 STOP 及恢复决定。

### 第一次 STOP：72bdb6a9ee

当时提示词要求用新增的逐表 Preview 公共接口对照 S2b，超出执行计划 §2 S3 验收。PreviewResultResponse 没有逐表状态；bundle 路由只返回 artifact 引用，没有公开 surface 下载接口。按停止条件暂停，未新增接口。owner 在 main 的 `7c77b5e8c8` 决议：

1. 不新增 Backend 公开接口；撤销逐表 Preview 状态对照要求。
2. 真实数据证据改为 Preview 汇总、公开 RS Catalog 汇总、History record_count 和离线 composite 比较。
3. 恢复 `test_comparison_canonical_domain.py` 的原测试名和原不变量：同内容上传与 Repository 基线全表 UNCHANGED、无记录。Repository 夹具走生产业务物化与规范投影，包含零行 `composite_signal_point`，不改生产代码。

### 第二次 STOP：ac9146da7f，V=f73deee604

t4 v1 Submit 的公开 operation-status 查询返回 HTTP 500 `INTERNAL_ERROR`，worker 仍在心跳，operation 没有终态证据。按停止规则结束该轮真实数据运行。owner 在 main 的 `c09c95fd81` 决议在 S3 内修复，不另立治理项；保留硬件 preflight，t4 重新完整运行，t1 冒烟重跑，t2/t3 仅在核心投影、比较、composite、规范存储路径未变时沿用 `f73deee604` 证据。

### 调试和恢复结论

- 真实调试没有复现 500，也没有复现 `StaleWrite`：t4 v1 Preview 和 Submit 分别在 2,644.797 s、806.912 s 成功；没有 worker 重启。写事务插桩没有发现超过 1 s 的 control DB 写事务，持锁超过 5 s 的写入方没有找到。插桩补丁 `/home/dev/gdds-p5-closure-s1-gate-logs/s3-debug-control-db-instrumentation.patch`，调试运行与容器日志为 `s3-debug-t4-v1-run-20261017-retry.log`、`s3-debug-t4-v1-compose-logs-20261017.txt`；这些只作调试记录，不作门禁证据。
- 移除修复时的确定性测试确实失败：写连接持锁超过 5 s 时 GET operation 未返回 200；`StoreBusy` 路由测试得到 500 而非 503；已终态提交后到期心跳触发 `StaleWrite`。日志 `/home/dev/gdds-p5-closure-s1-gate-logs/s3-debug-deterministic-repro-20261017.log`。修复后的 focused 组 71 passed，日志 `s3-debug-focused-final-20261017.log`。
- GET 查询现在显式使用 read-only UOW。其事务使用延迟的 `BEGIN`，不发出 `BEGIN IMMEDIATE`；在 WAL 下不被另一个 writer 的保留锁挡住。因此，原来的“GET 开写事务 → busy timeout 5 s → 未映射异常落到通用 500”这条具体路径被消除。这个机制性结论不等于找到或证明了原写锁持有者。
- `StoreBusy` 由 `register_exception_handlers(app)` 注册为 app-wide 503 `SERVICE_NOT_READY`。Contract 已允许控制数据库依赖不可用返回 503，未改 Contract。应用到写路由时也同样生效；见 §11.2。
- 心跳遇到租约异常时，若 session 已能确认 durable terminal acknowledgment，就等待 executor 线程完成，不再把该预期竞态升级成 worker fatal error；租约在终态提交前真正丢失仍沿用原异常路径。

## 2. 子步与提交

| S3 子步 | 提交 | 结果 |
| --- | --- | --- |
| DC20：source_table 改 VARCHAR(64) 并校验长度 | f5aa52a39d | 超长沿用 COMPOSITE_LOGIC_FAILED；未改 composite contract。 |
| Preview 业务物化与 XML / EMPTY 来源摘要；DC8 诊断 | 280bb1034d、6afdbc5de6 | 缺失 XML 用稳定 EMPTY；无效 XML 或 composite 不变量失败沿用 P3-R3 diagnostic。 |
| composite 投影、身份与规则事实测试 | 4744b5c5e0 | 未重复实施 S2a 的 registry 规则。 |
| composite canonical golden | 59f204f7f5 | 规范类型、键、列见 §6。 |
| 已有 serial History Compose 扩展 | 9f7af5fd13 至 a61419dc31 | 同一栈完成 XML-only 公式变化、Preview、Submit、Repository、History；不加 parallel_safe、不新增独立栈。 |
| 删除 S3 的 8 个不可达基线项 | d93c76e8f4、48e8f190b5、6a1e002033 | import_rules 预期不可达由 14 降至 6。 |
| 恢复 canonical compare 与生产基线夹具 | 3e01baff21、e988763393 为中间尝试；34baca070c 为最终修正 | 断言恢复为同内容全表 UNCHANGED、零记录；fixture 通过生产路径生成 composite 零行表。 |
| 真实数据 composite 离线比较与计数 | 62cca24b99 | 复用 census 的物化、投影与生产比较能力，只输出计数。 |
| 修正空 composite 的 Catalog exact-set expectation | f73deee604 | 此后最终 V full runner 通过。 |
| 只读查询事务、StoreBusy HTTP 映射、终态 heartbeat race | ee0a4c43a7 | GET operation/submission stores 使用 `read_only=True`；StoreBusy 映射到 503；已提交终态后的竞态不再触发 worker fatal exit。 |
| 失败时先保存 Compose 日志 | 2179e89138 | journey 失败路径在 stack teardown 前保存所有服务日志；在新 V 前完成。 |
| Compose 起栈失败时保存日志 | dc9c08a410 | startup failure 也走日志捕获；在新 V 前完成。 |
| 早期 STOP 记录 | 72bdb6a9ee | 历史停止原因与 owner 决议见 §1。 |
| 第二次 STOP 记录 | ac9146da7f | 记录 owner 决议前的 t4 v1 Submit 500。 |

V = `dc9c08a410829f303aae1e0f826c674b335cb94b`。`f73deee604..V` 中的 `2179e89138`、`dc9c08a410` 只改真实数据 benchmark / tests；完整 runner 与 t4、t1 真实数据均在这个新 V 上完成。V..H 仅提交本 handoff 文件；H0=`576755e99714ec9449fc730ea188fddb3b41fdbf` 为初次汇总，最终 H 在其后只更新本文件中的 carried 结果。

## 3. 路径预算与偏差

预算内生产路径为 application/preview_jobs.py、capabilities/snapshot_materialization/compose.py；S3 所有者测试、既有 History Compose、architecture_baseline.py；真实数据 benchmark 与 tests/test_real_dump 文件。

| 额外路径 | 原因 |
| --- | --- |
| vnext/backend/tests/support/preview_job_harness.py | owner 明确要求 Repository fixture 使用生产业务物化与规范投影。 |
| vnext/backend/tests/test_architecture.py | 删除不可达项后同步 synthetic facade probe；没有 import 规则豁免。 |
| vnext/backend/tests/support/upload_http_packages.py、compose_gate_harness.py | 让现有上传与 Compose harness 携带 logics.xml，复用同一 serial stack。 |
| vnext/backend/tests/test_submit_compose_e2e.py | 更新 Catalog 精确表集合期望以包含业务派生 composite_signal_point。 |
| vnext/backend/benchmarks/real_dump_census.py、real_dump_journey.py，tests/test_real_dump_census.py、test_real_dump_journey.py | 按 owner 恢复后的聚合核对增加只读计数与验证；属于 §8.9 允许路径。 |
| 本 handoff | 记录停止与恢复。 |

第二次 STOP 的修复路径也在本轮预算内：

| 路径 | 原因 |
| --- | --- |
| `vnext/backend/src/gateway_backend/http/dependencies.py`、`bootstrap/composition.py` | 只读 HTTP store 必须创建 `read_only=True` UOW，避免只读 GET 执行 `BEGIN IMMEDIATE`。 |
| `vnext/backend/src/gateway_backend/http/errors.py` | 为 StoreBusy 注册 HTTP 503 handler；不改 Contract。 |
| `vnext/backend/src/gateway_backend/operations/worker_runtime.py` | 已有终态 acknowledgment 时，heartbeat race 不应将提交后的 stale lease 升级为 worker fatal exit。 |
| `vnext/backend/tests/test_operation_http.py`、`test_operation_worker_scheduler.py` | 分别拥有只读查询 / StoreBusy 映射和终态 heartbeat 行为。 |
| `vnext/backend/tests/test_real_dump_journey.py`、`benchmarks/real_dump_journey.py` | 503 在 operation 超时内退避重试；失败时拆栈前保存全部服务日志。 |

未启用 capabilities/composite_signal/contracts.py；snapshot_materialization 是派生表 schema owner，未发现需要改 composite 契约的条件。未改 Repository Service Contract、wire、HTTP DTO、Dockerfile、Compose 文件、依赖或 uv.lock。

## 4. import_rules

命令：cd vnext/backend && ../scripts/uv-consume.sh -C . run python -m tests.support.import_rules

| 时点 | 违例 | 运行时环 | 不可达 |
| --- | ---: | ---: | ---: |
| kickoff base be5fd5a970 | 0 | 0 | 14 |
| V dc9c08a410 | 0 | 0 | 6 |

删除项为 composite_signal._ast、_bind、_digest、materialize；snapshot_materialization._catalog、compose；table_access._xml_parser、xml。余下 6 项属其他阶段。

## 5. 验收 owner、focused / 静态验证与 V runner

| Owner / 命令 | 结果 |
| --- | --- |
| DC20：test_snapshot_materialization_business.py | 13 passed；键类型、长度校验与 EMPTY 来源。 |
| Preview / DC8：test_preview_job_materialize.py | 9 passed；坏 XML → FAILED 与公开 diagnostic；缺失 XML → EMPTY。 |
| Projection / registry：相关 storage projection 与 table rules unit | 70 passed。 |
| Identity integration：test_canonical_snapshot_identity.py | 1 passed；真实 Repository Service 导入并经 HTTP Arrow 读回 VARCHAR(64) 键列。 |
| canonical compare：test_comparison_canonical_domain.py | 1 passed；两侧同内容，全表 UNCHANGED、零记录。 |
| 只读 GET 遇写锁与 StoreBusy HTTP 映射：test_operation_http.py | 新增确定性覆盖；移除修复时写锁用例未返回 200，StoreBusy 用例返回 500；修复后通过。 |
| 终态提交与 heartbeat race：test_operation_worker_scheduler.py | 移除修复时 terminal acknowledgment 后 heartbeat 抛 StaleWrite；修复后通过。 |
| journey 503 重试 / 失败日志顺序：test_real_dump_journey.py | 503 退避重试、500 仍失败；失败时日志先于 teardown 保存；focused 通过。 |
| 修复 focused 组 | 71 passed；日志 `/home/dev/gdds-p5-closure-s1-gate-logs/s3-debug-focused-final-20261017.log`。 |
| 五包 Ruff + mypy | shared_kernel、repository_contracts、repository_client、repository_service、backend 全部通过。 |
| 权威 runner V | `GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`；V clean，start/end HEAD 均为 `dc9c08a410829f303aae1e0f826c674b335cb94b`，runner exit 0。日志 `/home/dev/gdds-p5-closure-s1-gate-logs/s3-final-v-dc9c08a4-authoritative-20261018.log`。 |

静态检查对每个包执行：cd vnext/<package> && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy。mypy 覆盖 shared_kernel 34、repository_contracts 15、repository_client 26、repository_service 198、backend 476 source files；均无 issue。

G11b 对照：shared_kernel 242、repository_contracts 152、repository_client 154 不变；Repository Service parallel 1,684 + 1 skipped、serial 205 不变。backend 当前 parallel 2,839、serial 36；G11b 为 2,816 + 34。parallel 集合相对 G11b 新增 25、删除 2，净增 23；serial 新增 2、无删除。按文件：`test_architecture.py` +2/-2、`test_operation_http.py` +1 parallel/+1 serial、`test_operation_worker_scheduler.py` +1 parallel/+1 serial、`test_preview_job_materialize.py` +3、`test_real_dump_census.py` +2、`test_real_dump_journey.py` +13、`test_snapshot_materialization_business.py` +1、`test_storage_projection_core.py` +1、`test_table_rules_contracts.py` +1。相对第二次 STOP 的 `f73deee604` runner（2,833 + 34），当前新增 parallel 6、serial 2、无删除：`test_operation_http.py` +1 parallel/+1 serial、`test_operation_worker_scheduler.py` +1 parallel/+1 serial、`test_real_dump_journey.py` +4 parallel。collection-only 对照日志在 `/home/dev/gdds-p5-closure-s1-gate-logs/s3-g11b-collect-parallel.txt`、`s3-g11b-collect-serial.txt`、`s3-f73-collect-parallel.txt`、`s3-f73-collect-serial.txt`、`s3-final-v-collect-current-parallel.txt`、`s3-final-v-collect-current-serial.txt`。最终 runner 摘要见上述 V 日志。62cca24b99 的 runner 因旧 Catalog exact-set 期望失败，f73deee604 修正后通过；`6a1e002033` 的 exit 141 是作废运行。

## 6. Golden、digest 与 checkpoint 载荷

- 新 golden：vnext/fixtures/golden/storage-projection/composite-signal/canonical.json。source_table 为 VARCHAR(64)；键为 source_table、point_gid；保留 source_table、point_gid、point_name、formula_digest、formula_ast_json；ignored 为 dev_addr、device_gid、point_payload_json；compare-excluded 为 formula_ast_json、point_name。schema digest sha256:45ab9549945be08b1386620fbc3d2f88f28a6818852dd3dab1628fd34582104c；content digest sha256:369e048b093be7a8ec62de2f1d31648bec77b3b595d660cc1d5ac4d2f1eb73b1；golden SHA-256 1e247286337087123e288a8d7397b896948f7c59933b08ff348426c75e2e8ee1。
- registry 规则由 S2a 396cfa2d28 落地；S3 只通过 test_table_rules_contracts.py 核对。
- snapshot_digest 在 XML 存在时包含 XML 内容摘要，缺失时包含稳定 EMPTY 摘要。规范状态摘要仅覆盖派生表内容；composite_signal_point 规范投影进入存储、比较与风险。
- 公式变化使 formula_digest 改变、该行 MODIFIED；point_name 与 formula_ast_json 为 compare-excluded，不单独改变表状态。Compose serial journey 断言行 MODIFIED 和 History record_count=1。
- checkpoint 未新增字段、envelope 或 materialize-side contract version。已有 composite_logic_source_digest 值包含 XML / EMPTY 来源；materialize_inputs 引用的 snapshot 规范表闭包可包含 composite_signal_point。值及闭包变化是目标形态，DC6 不保留旧兼容路径。
- 真实运行中的规范状态摘要、bundle digest 和 surface digest 因增加 composite 表而变化；具体新值及 S2b 对照见 §8、§9。它们仅记录，不作除 composite 以外变化的判据。golden、snapshot_digest 和 checkpoint 的结构 / 值变化见以上各项；没有加入兼容层。

## 7. V 镜像及 carried

provenance：`/home/dev/gdds-p5-closure-s1-gate-logs/s3-v-dc9c08a4-provenance.json`。V=`dc9c08a410829f303aae1e0f826c674b335cb94b` 的完整 runner 实际镜像：

| 镜像 | image ID | 记录 |
| --- | --- | --- |
| backend | `sha256:88f617468ba1315884f377a325955c9e21ebe4139dcf7f663bfb97727e4f7d0e` | V runner provenance；Compose project `ordered-bisect-b-2871524-baseline`。 |
| worker | `sha256:eb8e6d236ecd0e00f2de9b3c2d657f0f148dc81d2801e336e49888a479e21d17` | V runner provenance；同上 project。 |
| repository-service | `sha256:84e2213d8a42d4a98d266efb72c21307a35ab31bdd9def4243c0855992e47194` | V runner provenance。 |

在 V 上执行 `python3 vnext/repository_service/tests/support/build_context_digest.py identity`，结果 candidate SHA=`dc9c08a410829f303aae1e0f826c674b335cb94b`、build-input revision `adc5d87fea073545fde6416d123c3d7845e715ff`、source-tree `sha256:5b34d0c51e8d4798beb06d7524e9610785a2ad95763fbfd0ddcb942cb2eb8fd4`。后两个值分别等于 provenance repository-service image 的 `gateway.p2r1.build-input-revision` 和 `gateway.p2r1.source-tree-sha256` label。记录在 `/home/dev/gdds-p5-closure-s1-gate-logs/s3-v-dc9c08a4-image-record.log`。

carried 在 V runner 同一 worktree `/home/dev/gdds-p5-s3` 完成。H0=`576755e99714ec9449fc730ea188fddb3b41fdbf` 上重算 RS identity：candidate SHA 为 H0，build-input revision=`adc5d87fea073545fde6416d123c3d7845e715ff`、source-tree=`sha256:5b34d0c51e8d4798beb06d7524e9610785a2ad95763fbfd0ddcb942cb2eb8fd4`；后两项与 V provenance label 一致。随后使用 provenance project `ordered-bisect-b-2871524-baseline` 连续两次执行 `docker compose -f compose.yaml build backend worker`，两次之间没有运行测试；两次 backend ID 均为 `sha256:88f617468ba1315884f377a325955c9e21ebe4139dcf7f663bfb97727e4f7d0e`，worker ID 均为 `sha256:eb8e6d236ecd0e00f2de9b3c2d657f0f148dc81d2801e336e49888a479e21d17`，都等于 V provenance。日志 `/home/dev/gdds-p5-closure-s1-gate-logs/s3-h0-carried-20261018.log`，耗时约 10 s。H0 与最终 H 之间只有本文件变化；最终 H 在同一 worktree 重算 identity 并重复两次构建，日志 `/home/dev/gdds-p5-closure-s1-gate-logs/s3-final-h-carried-20261018.log`，identity 的 build-input/source-tree 及两镜像 ID 与上述相同，构建间未运行测试。

受保护 client 镜像记录：`gateway-repository-client-e2e-base:local` 当前 ID 为 `sha256:dafde407833e087cc619da34b3e352e7fa85e63d6138ed8d516cdccfa3e46764`，与先前记录一致。`gateway-repository-client-e2e:local` 当前 ID 为 `sha256:55c506d6ef4895a6c8bf8d734c3e9fc21772554186a1cad66f386dba83aacb90`，创建时间为 2026-10-18 15:51:29 +01:00，revision label 为 V。repository_client Compose 用例的 `ensure_client_image()` 因 candidate label 不匹配，通过 `docker build -t gateway-repository-client-e2e:local` 更新了这个 tag。未运行 `docker rmi` 或 `docker tag` 命令，但该构建确实改变了受保护 tag 指向的 image ID；未尝试恢复（恢复需要再次改 tag）。上一份 handoff 记录的 client image ID 为 `sha256:7883e067020adbdb84f8d7e305218e492f161058b85fa7b74f774acc27811368`，但没有本次 runner 紧邻开始前的 image 快照。此 runner side effect 与原始“不重新 tag”要求的边界请 reviewer 明确评价，不宣称 client image 未变。

镜像标签变更的事实以本节前两段的 V runner provenance 和 image ID 记录为准；没有可证明的 V runner 开始前快照，故不声称 `gateway-repository-client-e2e:local` 在整个阶段未变。H0 carried 开始与结束时，client tag 均为 `sha256:55c506d6ef4895a6c8bf8d734c3e9fc21772554186a1cad66f386dba83aacb90`，base tag 均为 `sha256:dafde407833e087cc619da34b3e352e7fa85e63d6138ed8d516cdccfa3e46764`；final H carried 也记录在上述日志中。carried 未执行受保护镜像的删除或改 tag 操作。

## 8. 真实数据身份与规模

脚本由主机侧 real_dump_journey.py 启动，原始数据只读；使用生产 census、business materialization、规范投影和生产 comparator，通过公开 HTTP 驱动 Preview / Submit / History。下表仅列 dataset ID、package SHA-256、大小与结构统计，不含项目别名、原始路径或行数据。

实际命令为 GATEWAY_REAL_DUMP_ROOT=<host-only configured value> ../scripts/uv-consume.sh -C . run python benchmarks/real_dump_journey.py；变量值仅留在主机日志，不写入 handoff。

| Dataset ID | package SHA-256 | bytes | 源 DDL 表 | census 派生表 | census 行数 | logics.xml |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| rd-t1-a-v1 | 42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2 | 107,115 | 132 | 133 | 6,097 | complete / depth 1 |
| rd-t1-a-v2 | 4019737fc8fe35e90792dcef722537bf09338110ace8cc09f35e004cc7095bd0 | 107,066 | 132 | 133 | 6,095 | complete / depth 1 |
| rd-t2-b-v1 | acd1b5e6f92083c3a6d53e9996be0bf46f520ae7fdea94d8449069748a3817c0 | 1,247,459 | 216 | 217 | 97,140 | complete / depth 56 |
| rd-t2-b-v2 | c66e3921c7774a38bfeb2f407c24a39209225e962f593ec88d17db0d85fcba98 | 1,197,404 | 216 | 217 | 93,154 | complete / depth 56 |
| rd-t3-c-v1 | c34e266c458d9b2cfb630fec56fa7c893113e11b56f768710aecebb0715eec7e | 3,356,815 | 199 | 200 | 268,661 | complete / depth 66 |
| rd-t3-c-v2 | 658422efd2583963cc04bdff6e88e2b733d33396bdd92ff5b3635dc00cffc28d | 3,370,171 | 200 | 201 | 268,667 | complete / depth 66 |
| rd-t4-d-v1 | 95408cc3cfd5bee4f7e53ab1b556e58c3335535b16e8791059029e59d5da1675 | 5,597,503 | 319 | 320 | 437,149 | complete / depth 97 |
| rd-t4-d-v2 | 5a7cd54d9b996be55c34b7bb766eb01ad5c1b7c4fa9bd1e72f5c4741baee3611 | 5,596,595 | 319 | 320 | 437,229 | complete / depth 97 |

V 重跑得到的规范状态摘要：

| Dataset ID | canonical state digest |
| --- | --- |
| rd-t1-a-v1 | `sha256:a700e0c085b5406eb85e10ddec6e9f6319378dd6b72cbb3b8069f869027c499b` |
| rd-t1-a-v2 | `sha256:0e4c1ceb07ab33925f7372250a6b213476c93cec7d9190fc5f65c250aec250f3` |
| rd-t4-d-v1 | `sha256:c1481b65dbc6e228a175ee175551df8ad5c57a859d6033c96635bff686afbf7a` |
| rd-t4-d-v2 | `sha256:346f08e7cef4df018bb1d0e5a8d7758f2c090ec446155cca44794029c59fa3f8` |

`f73deee604` 的 t2/t3 通过运行未在其逐步日志中输出 canonical state digest 或 bundle/surface digest；按 owner 决议沿用该 journey，没有重跑 t2/t3。故不补造这四个历史 digest；它们不是本次 S3 对照判定值。所有可用的 digest 只记录新值、不作为复合表以外变化的判据。

八份 logics.xml 均 COMPLETE；t1/t2/t3/t4 的 v1/v2 深度依次为 1、1、56、56、66、66、97、97。离线 composite 比较复用 real_dump_census.py 的生产物化、规范投影与比较能力，只输出计数：

| Tier | composite rows v1 → v2 | 状态 | ADDED / REMOVED / MODIFIED | History records |
| --- | ---: | --- | --- | ---: |
| t1 | 4 → 4 | UNCHANGED | 0 / 0 / 0 | 0 |
| t2 | 45 → 45 | UNCHANGED | 0 / 0 / 0 | 0 |
| t3 | 201 → 201 | UNCHANGED | 0 / 0 / 0 | 0 |
| t4 | 435 → 435 | UNCHANGED | 0 / 0 / 0 | 0 |

## 9. 聚合对照、A/B/C 与结论

权威 runner V、t1 和 t4 均在 clean 的 `dc9c08a410` 上运行。最终 runner preflight 为 2026-10-18T14:20:59Z：nproc=96、loadavg=2.92/2.96/3.08、无 Dolt、无 Compose project、8000 端口空闲，docker ps -a 只有两个常驻 BuildKit 容器。runner 于 14:21:10Z 开始、14:56:46Z 结束，起止 HEAD 相同、状态 clean、exit 0。运行中 14:41:10Z 观察到外部 pytest 约 0.875 CPU 核、loadavg 6.97/5.06/4.08；按用户后续明确的“外部负载未越限不作废”要求继续，1-minute load 远低于当前 nproc=96 的运行阈值，没有作废 runner。观察写入 `/home/dev/gdds-p5-closure-s1-gate-logs/s3-final-v-host-load-20261018.log`。t1/t4 的最终 journey 日志各自记录时间戳和容器 cpu.stat；t4 运行期间无 500、StaleWrite、worker restart 或 503 retry，所有 operation 均在 timeout 内终态。最终 runner preflight 为 `/home/dev/gdds-p5-closure-s1-gate-logs/s3-final-v-preflight-20261018-corrected.log`；先前一次 preflight 的 `pgrep` 搜索误匹配了自身 shell，未启动 runner，修正后重新检查通过。最终容器 runner 日志为 `/home/dev/gdds-p5-closure-s1-gate-logs/s3-final-v-dc9c08a4-authoritative-20261018.log`。

| Tier/version | Preview table_count / changed / degraded / failed | composite rows | Catalog / History | 结果 |
| --- | --- | ---: | --- | --- |
| t1 v1 | 125 / 125 / 0 / 0，S2b + 1 | 4 | Catalog 3733 rows；减 composite 后 3729，与 S2b 相同 | 通过 |
| t1 repeat v1 | 125 / 0 / 0 / 0 | 4 | 全表 UNCHANGED；Submit NO_CANONICAL_CHANGE | 通过 |
| t1 v2 | 125 / 4 / 0 / 0 | 4 | Catalog 3731 rows；减 composite 后 3727；History 12（S2b=12） | 通过 |
| t2 v1 | 209 / 209 / 0 / 0，S2b + 1 | 45 | Catalog 断言：73,648 + 45 = 73,693 | 通过，见 owner 决议 |
| t2 repeat v1 | 209 / 0 / 0 / 0 | 45 | 全表 UNCHANGED；Submit NO_CANONICAL_CHANGE | 通过 |
| t2 v2 | 220 / 57 / 0 / 0 | 45 | Catalog 断言：68,864 + 45 = 68,909；History 11,511（S2b=11,511） | 通过，见 owner 决议 |
| t3 v1 | 192 / 192 / 0 / 0，S2b + 1 | 201 | Catalog 断言：122,251 + 201 = 122,452 | 通过，见 owner 决议 |
| t3 repeat v1 | 192 / 0 / 0 / 0 | 201 | 全表 UNCHANGED；Submit NO_CANONICAL_CHANGE | 通过 |
| t3 v2 | 193 / 54 / 0 / 0 | 201 | Catalog 断言：122,257 + 201 = 122,458；History 744（S2b=744） | 通过，见 owner 决议 |
| t4 v1 | 312 / 312 / 0 / 0，S2b + 1 | 435 | Catalog 246,794 rows；减 composite 后 246,359 | V 重跑通过 |
| t4 repeat v1 | 312 / 0 / 0 / 0 | 435 | 全表 UNCHANGED；Submit NO_CANONICAL_CHANGE | V 重跑通过 |
| t4 v2 | 312 / 26 / 0 / 0 | 435 | Catalog 246,874 rows；减 composite 后 246,439；History 168（S2b=168） | V 重跑通过 |

### t4 / t1 公开汇总事实

V 上 t4 完整执行 v1 Preview、Submit、Repository 读取、approve、archive、v1 重传 Preview / Submit、v2 Preview / Submit、Repository 读取、approve 与 History；t1 完整执行同样的核心旅程作为冒烟。t1–t4 INITIAL 都是空提交，Catalog 为 0 table / 0 row。所有 Preview degraded / failed 均为 0；所有 operation 在 protection timeout 内终态。t1 深度 1 的 logics.xml 得到 4 行 composite 表，不是 EMPTY 来源。t1 与 t4 v1 重传时全表 UNCHANGED、Submit 为 `NO_CANONICAL_CHANGE`，包含 composite_signal_point。

与 S2b 对照，Catalog 表数均为 `S2b + 1`：t1=125、t2=209、t3 v1/v2=192/193、t4=312。Catalog 总行数扣除 composite 后，t1 为 3,729 / 3,727，t2 为 73,648 / 68,864，t3 为 122,251 / 122,257，t4 为 246,359 / 246,439，与 S2b v1/v2 相同；t1/t4 为本次公开 Catalog 实测，t2/t3 的生产汇总断言由 f73 成功 journey 执行，精确总数未持久化在逐步日志。composite 行数分别为 t1 4/4、t2 45/45、t3 201/201、t4 435/435，和离线 census 相同。History record_count 差值四档均为 0，等于离线 composite 生产比较所得的 History records。可用的 bundle / surface digest 仅记录新值且不作判定依据：t1 bundle `sha256:b80366a3dbda78c5bb229a125caca629240cf8f3f76aba6f21944c68787556b9`、surface `sha256:cf759ad0baad380ee3187f92cef8f7acf214ab15842d0e30a75d188c753e617e`；t4 bundle `sha256:d5da700194c7772218d8000cee33abb5efff14c8da94c4035c9d1d11ccbf7a4f`、surface `sha256:09a23e1f6c0514f2bc202b8c65ae9ba6f855c37aea2a63eb082a8e48b4b08727`。f73 t2/t3 成功 journey 的逐步日志未保存 History bundle/surface digest 或规范状态摘要，沿用结果不重新跑；不补造这四个 digest。Catalog JSON bytes t1=122,517（S2b 122,107）、t4=286,137（S2b 285,725）；变化与新增 composite Catalog 行相符。

离线 composite 生产比较：四档 v1→v2 均 UNCHANGED，行数 t1 4、t2 45、t3 201、t4 435；ADDED / REMOVED / MODIFIED 均为 0 / 0 / 0，History records 均为 0。t1/t4 与公开 Catalog 行数和 History 差额相符。t2/t3 完整 journey 沿用 `f73deee604` 通过结果；`f73deee604..V` 改动文件已列在 §10，未触及投影、比较、composite、规范存储或 census 业务路径。

IEC104 ordered pseudo 行数：t1 4/4、t2 3,056/2,674、t3 9,858/9,858、t4 12,676/12,688；有序表未降级，重传无变化，History 移动 / 空白区间 / 字段显示四项仍由 owning tests 与 Compose 验证，不从真实行数据推算。DC29 keyless fallback 表：t1 23、t2 27、t3 27/28、t4 33；重复 v1 时包含在全表 UNCHANGED 中，不产生 `KEY_MISSING` / `KEY_DEGRADED`。t4 ordered pseudo 总行 12,676 / 12,688，t4 keyless 表 33，均与 S2b 相同。

### A/B/C 明细

下表按 S2b handoff §8.6 记录每步 wall 与三容器 CPU；括号内为本次减 S2b 的秒数。A 对 operation 表示保护超时内终态，C 表示时间戳和 CPU 采样已写入。t4 v2 Preview 的 S2b worker counter 重置，保留本次绝对 CPU 秒、不计算该项差值。

### t1

| Step | Wall s (Δ S2b) | Backend CPU s (Δ) | RS CPU s (Δ) | Worker CPU s (Δ) | A / C |
| --- | ---: | ---: | ---: | ---: | --- |
| v1-workspace | 0.676 (-0.023) | 0.020 (-0.007) | 0.001 (+0.000) | 0.000 (+0.000) | A n.a.; C logged |
| v1-upload | 0.667 (-0.035) | 0.017 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A n.a.; C logged |
| v1-preview | 52.980 (-0.009) | 1.486 (-0.009) | 1.309 (+0.000) | 42.144 (+1.159) | A terminal SUCCEEDED; C logged |
| v1-submit | 41.612 (-0.013) | 1.841 (+0.042) | 62.171 (-0.087) | 13.580 (-0.444) | A terminal SUCCEEDED; C logged |
| v1-repository-read | 10.668 (-0.058) | 0.240 (-0.018) | 57.512 (+0.588) | 0.013 (+0.000) | A n.a.; C logged |
| v1-approve | 0.669 (-0.024) | 0.013 (+0.000) | 0.001 (+0.000) | 0.003 (+0.003) | A n.a.; C logged |
| v1-archive | 0.691 (-0.057) | 0.045 (-0.004) | 0.123 (+0.017) | 0.003 (+0.000) | A n.a.; C logged |
| repeat-v1-workspace | 0.664 (-0.018) | 0.126 (+0.056) | 0.001 (+0.000) | 0.000 (+0.000) | A n.a.; C logged |
| repeat-v1-upload | 0.682 (-0.033) | 0.022 (+0.003) | 0.001 (+0.000) | 0.000 (+0.000) | A n.a.; C logged |
| repeat-v1-preview | 73.030 (-0.056) | 2.072 (+0.009) | 31.572 (+0.477) | 47.497 (+0.407) | A terminal SUCCEEDED; C logged |
| repeat-v1-submit | 0.656 (-0.044) | 0.011 (+0.001) | 0.001 (+0.000) | 0.000 (+0.000) | A n.a.; C logged |
| v2-workspace | 0.634 (-0.063) | 0.006 (-0.001) | 0.001 (+0.000) | 0.000 (+0.000) | A n.a.; C logged |
| v2-upload | 0.673 (-0.053) | 0.021 (+0.001) | 0.001 (+0.000) | 0.000 (+0.000) | A n.a.; C logged |
| v2-preview | 77.111 (-0.002) | 2.250 (+0.030) | 31.984 (+0.539) | 47.396 (-0.235) | A terminal SUCCEEDED; C logged |
| v2-submit | 43.521 (-0.040) | 1.870 (-0.013) | 68.117 (-0.321) | 13.595 (-0.354) | A terminal SUCCEEDED; C logged |
| v2-repository-read | 10.830 (-0.169) | 0.251 (+0.005) | 60.200 (+0.698) | 0.016 (+0.000) | A n.a.; C logged |
| v2-approve | 0.660 (-0.034) | 0.009 (+0.000) | 0.001 (+0.000) | 0.000 (-0.003) | A n.a.; C logged |
| history | 60.948 (-2.023) | 1.708 (-0.023) | 61.185 (+1.477) | 34.205 (-0.761) | A terminal SUCCEEDED; C logged |

journey wall: 377.587 s.

### t2

| Step | Wall s (actual; Δ vs S2b) | Backend CPU s (actual; Δ) | RS CPU s (actual; Δ) | Worker CPU s (actual; Δ) | A / C |
| --- | ---: | ---: | ---: | ---: | --- |
| v1-workspace | 0.683 (-0.017) | 0.071 (+0.030) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v1-upload | 0.732 (-0.017) | 0.066 (+0.004) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v1-preview | 742.395 (+20.074) | 20.668 (+0.549) | 18.815 (+0.708) | 733.296 (+19.246) | A 终态成功；C 已记录 |
| v1-submit | 237.294 (-1.891) | 7.863 (-0.012) | 116.036 (+0.705) | 202.648 (-1.372) | A 终态成功；C 已记录 |
| v1-repository-read | 27.048 (-0.240) | 0.629 (-0.114) | 117.466 (-0.512) | 0.065 (-0.002) | A 不适用；C 已记录 |
| v1-approve | 0.678 (-0.036) | 0.013 (+0.000) | 0.001 (+0.000) | 0.000 (-0.003) | A 不适用；C 已记录 |
| v1-archive | 0.703 (-0.023) | 0.042 (+0.001) | 0.001 (+0.000) | 0.003 (+0.003) | A 不适用；C 已记录 |
| repeat-v1-workspace | 0.654 (-0.052) | 0.007 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| repeat-v1-upload | 0.726 (-0.023) | 0.061 (+0.000) | 0.001 (+0.000) | 0.000 (-0.003) | A 不适用；C 已记录 |
| repeat-v1-preview | 623.827 (+19.939) | 17.705 (+0.711) | 75.356 (+0.182) | 593.528 (+21.892) | A 终态成功；C 已记录 |
| repeat-v1-submit | 0.695 (+0.003) | 0.010 (-0.056) | 0.068 (-0.053) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v2-workspace | 0.679 (-0.005) | 0.007 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v2-upload | 0.745 (+0.000) | 0.094 (+0.030) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v2-preview | 708.216 (+20.173) | 20.037 (+0.837) | 77.443 (+1.157) | 665.864 (+20.497) | A 终态成功；C 已记录 |
| v2-submit | 239.090 (+0.019) | 7.897 (-0.011) | 126.527 (+0.941) | 198.243 (+0.611) | A 终态成功；C 已记录 |
| v2-repository-read | 28.369 (+0.282) | 0.767 (+0.129) | 121.030 (+0.848) | 0.076 (+0.001) | A 不适用；C 已记录 |
| v2-approve | 0.691 (-0.001) | 0.008 (+0.000) | 0.001 (+0.000) | 0.003 (+0.003) | A 不适用；C 已记录 |
| history | 502.750 (+0.008) | 13.758 (+0.034) | 137.438 (+0.201) | 434.309 (-0.728) | A 终态成功；C 已记录 |

### t3

| Step | Wall s (actual; Δ vs S2b) | Backend CPU s (actual; Δ) | RS CPU s (actual; Δ) | Worker CPU s (actual; Δ) | A / C |
| --- | ---: | ---: | ---: | ---: | --- |
| v1-workspace | 0.693 (+0.013) | 0.038 (-0.028) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v1-upload | 0.846 (+0.018) | 0.173 (+0.007) | 0.002 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v1-preview | 1315.151 (+70.303) | 36.980 (+2.131) | 33.233 (+1.827) | 1301.051 (+62.592) | A 终态成功；C 已记录 |
| v1-submit | 484.799 (+5.523) | 15.301 (+0.288) | 121.535 (-0.409) | 443.398 (+4.239) | A 终态成功；C 已记录 |
| v1-repository-read | 24.947 (+0.204) | 0.633 (+0.014) | 102.990 (+1.127) | 0.048 (-0.002) | A 不适用；C 已记录 |
| v1-approve | 0.678 (-0.006) | 0.014 (+0.001) | 0.001 (+0.000) | 0.000 (-0.003) | A 不适用；C 已记录 |
| v1-archive | 0.716 (-0.001) | 0.044 (+0.002) | 0.001 (+0.000) | 0.003 (+0.003) | A 不适用；C 已记录 |
| repeat-v1-workspace | 0.669 (-0.018) | 0.007 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| repeat-v1-upload | 0.854 (+0.017) | 0.173 (+0.003) | 0.001 (-0.001) | 0.000 (-0.003) | A 不适用；C 已记录 |
| repeat-v1-preview | 1423.743 (+60.275) | 40.527 (+1.732) | 103.271 (+1.170) | 1373.383 (+52.728) | A 终态成功；C 已记录 |
| repeat-v1-submit | 0.659 (-0.037) | 0.011 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v2-workspace | 0.659 (-0.021) | 0.007 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v2-upload | 0.844 (+0.000) | 0.181 (+0.004) | 0.001 (-0.001) | 0.000 (+0.000) | A 不适用；C 已记录 |
| v2-preview | 1588.882 (+60.553) | 45.254 (+2.018) | 108.060 (+2.036) | 1541.536 (+56.531) | A 终态成功；C 已记录 |
| v2-submit | 492.827 (-10.103) | 15.402 (-0.217) | 133.537 (-6.197) | 447.135 (-3.859) | A 终态成功；C 已记录 |
| v2-repository-read | 25.615 (-0.178) | 0.639 (-0.001) | 112.203 (-0.132) | 0.054 (-0.004) | A 不适用；C 已记录 |
| v2-approve | 0.686 (+0.002) | 0.009 (+0.001) | 0.001 (+0.000) | 0.000 (+0.000) | A 不适用；C 已记录 |
| history | 963.270 (-9.333) | 26.347 (-0.011) | 169.525 (+2.522) | 881.267 (-8.660) | A 终态成功；C 已记录 |

### t4

| Step | Wall s (Δ S2b) | Backend CPU s (Δ) | RS CPU s (Δ) | Worker CPU s (Δ) | A / C |
| --- | ---: | ---: | ---: | ---: | --- |
| v1-workspace | 0.692 (+0.016) | 0.016 (-0.044) | 0.001 (+0.000) | 0.000 (+0.000) | A n.a.; C logged |
| v1-upload | 0.929 (-0.005) | 0.254 (-0.009) | 0.001 (-0.001) | 0.000 (+0.000) | A n.a.; C logged |
| v1-preview | 2657.230 (+89.789) | 74.528 (+1.978) | 67.621 (+2.815) | 2646.402 (+90.801) | A terminal SUCCEEDED; C logged |
| v1-submit | 802.912 (-2.302) | 24.886 (-0.352) | 207.056 (+1.712) | 738.439 (-4.225) | A terminal SUCCEEDED; C logged |
| v1-repository-read | 51.662 (-1.103) | 1.260 (-0.027) | 193.070 (-5.035) | 0.121 (-0.014) | A n.a.; C logged |
| v1-approve | 0.694 (+0.004) | 0.013 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A n.a.; C logged |
| v1-archive | 0.722 (-0.005) | 0.154 (+0.112) | 0.001 (+0.000) | 0.003 (+0.003) | A n.a.; C logged |
| repeat-v1-workspace | 0.681 (+0.009) | 0.007 (+0.000) | 0.001 (+0.000) | 0.000 (-0.003) | A n.a.; C logged |
| repeat-v1-upload | 0.943 (-0.013) | 0.266 (-0.127) | 0.001 (-0.054) | 0.000 (-0.003) | A n.a.; C logged |
| repeat-v1-preview | 2336.092 (+91.933) | 65.869 (+1.444) | 175.460 (+2.585) | 2271.524 (+97.321) | A terminal SUCCEEDED; C logged |
| repeat-v1-submit | 0.677 (+0.009) | 0.010 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A n.a.; C logged |
| v2-workspace | 0.684 (-0.007) | 0.006 (+0.000) | 0.001 (+0.000) | 0.000 (+0.000) | A n.a.; C logged |
| v2-upload | 0.942 (-0.012) | 0.395 (+0.123) | 0.130 (+0.128) | 0.000 (+0.000) | A n.a.; C logged |
| v2-preview | 2339.742 (+95.700) | 65.774 (+3.032) | 177.231 (+5.324) | 2266.078 (S2b worker counter reset) | A terminal SUCCEEDED; C logged |
| v2-submit | 812.804 (-2.104) | 25.129 (+0.258) | 226.316 (+0.099) | 746.676 (-1.681) | A terminal SUCCEEDED; C logged |
| v2-repository-read | 50.844 (+0.315) | 1.213 (-0.049) | 211.317 (+3.926) | 0.128 (+0.026) | A n.a.; C logged |
| v2-approve | 0.689 (-0.010) | 0.009 (+0.000) | 0.001 (+0.000) | 0.000 (-0.003) | A n.a.; C logged |
| history | 1375.789 (+23.708) | 37.454 (+1.042) | 278.869 (+4.283) | 1247.915 (+14.202) | A terminal SUCCEEDED; C logged |

journey wall: 10434.965 s.

t1 journey wall 为 377.587 s（S2b 380.335 s，−2.748 s）；t4 journey wall 为 10,434.965 s（S2b 10,139.016 s，+295.949 s）。t4 三次 Preview wall 增量分别为 v1 +89.789 s、repeat-v1 +91.933 s、v2 +95.700 s；worker CPU 同步增加，Backend / Repository Service 也有小幅增量，没有 wall 显著大于 CPU 的额外空等迹象，按验收要求归因于 composite 物化 / 投影工作，不把它升级为已确认的结构性原因。t2/t3 复用值相对 S2b 的 Preview wall 增量约 +20 s / +60 s，同方向归因于 composite。

与 f73 的 t4 比较：f73 v1 Preview operation wall 为 2,649.150 s，本次为 2,656.491 s（+7.341 s）；step wall 为 2,649.893 s → 2,657.230 s（+7.337 s），Backend CPU +0.321 s、RS CPU +0.674 s。f73 worker counter 在旧 worker 重启后读取，0.945 s 无效；不比较 worker CPU。f73 v1 Submit 在 594.828 s 因 GET status HTTP 500 中断、没有 operation 终态；本次 800.757 s 成功，与该失败 partial elapsed 不作性能差值。f73 未运行后续 repeat-v1、v2、History，因此这些步骤只与 S2b 比较。

## 10. STOP 条件、复用依据与运行记录

- 最终 V 为 dc9c08a410829f303aae1e0f826c674b335cb94b。权威 runner 于 2026-10-18T14:21:10Z 开始、14:56:46Z 结束，起止 HEAD 相同、状态 clean、exit 0；日志见 /home/dev/gdds-p5-closure-s1-gate-logs/s3-final-v-dc9c08a4-authoritative-20261018.log。五包 ruff / mypy 和 import_rules 对照见 §4–§5。
- t1 冒烟在同一 clean V 上完整通过，journey wall 377.587 s，结论 PASS；日志 /home/dev/gdds-p5-closure-s1-gate-logs/s3-post-fix-t1-20261018.log。t4 在同一 clean V 上完成 v1 Preview / Submit / Repository 读取 / approve / archive、v1 重传 Preview / Submit、v2 Preview / Submit / Repository 读取 / approve 与 History，journey wall 10,434.965 s，结论 PASS；日志 /home/dev/gdds-p5-closure-s1-gate-logs/s3-post-fix-t4-final-run6-20261018.log。真实数据运行发生在最终 full runner 之前，但两者都绑定同一已提交 clean HEAD，期间没有工作区写入。
- A 层：t1、t4 的所有 operation 均在保护 timeout 内达到 SUCCEEDED。t1 的 Preview / Submit / repeat Preview / v2 Preview / v2 Submit / History 分别为 52.272/300、40.254/300、72.341/316、76.400/386、42.257/300、60.236/315 秒。t4 对应 operation wall / timeout 分别为 2,656.491/12,887、800.757/4,047、2,335.359/11,271、2,339.012/11,300、810.836/4,055、1,375.067/6,821 秒。所有状态查询均成功；未观察到 503，因此 503 retry 次数为 0。没有 500、StaleWrite 或 worker restart。
- t2/t3 沿用 f73deee604 上的完整成功 journey，日志 /home/dev/gdds-p5-closure-s1-gate-logs/s3-realdata-v-f73deee6-journey.log，exit 0。f73deee604..V 的文件清单为：本 handoff、vnext/backend/benchmarks/real_dump_journey.py、vnext/backend/src/gateway_backend/http/dependencies.py、vnext/backend/src/gateway_backend/http/errors.py、vnext/backend/src/gateway_backend/operations/worker_runtime.py、vnext/backend/tests/test_operation_http.py、vnext/backend/tests/test_operation_worker_scheduler.py、vnext/backend/tests/test_real_dump_journey.py。没有改投影、比较、composite materialization、规范存储或 real_dump_census.py 业务路径；因此符合 owner c09c95fd81 给出的 t2/t3 复用条件。t1 与 t4 已在最终 V 重跑。
- 最终数据核对未触发 S3 设计停止条件：8 份 XML 均 COMPLETE，来源表名均在 64 字符上限内；Preview degraded/failed 为 0；Catalog / History 的 composite 汇总与离线生产比较相符，未发现 composite 以外的变化；S3 的 8 个模块均从不可达基线移除。没有改 Repository Service Contract、wire、HTTP DTO、control DB schema、固定预算、Dockerfile、Compose 文件或依赖；没有新加 baseline、放宽或跳过用例。
- A/B/C 中 t4 三次 Preview 相比 S2b 分别多约 90–96 秒，伴随 worker / service CPU 增加；与 composite 物化、投影的新增工作相符，没有观察到额外空等。t2/t3 沿用的 Preview wall 增量约 20 / 60 秒，同方向归因于 composite。具体逐步数值和 f73 t4 部分运行比较见 §9。
- 真实调试明确为“未复现”：调试 t4 v1 Preview / Submit 成功，无 HTTP 500、StaleWrite 或 worker restart；控制库插桩未发现超过 1 秒的写事务，持锁超过 5 秒的 owner 未找到。移除修复时只读锁测试、StoreBusy 映射测试与 heartbeat 竞态测试均按预期失败。插桩补丁及日志在 §1 列出，不作为门禁证据。
- 失败 / 作废运行如实记录：62cca24b99 的 full runner 因 Catalog exact-set 旧期望失败，f73deee604 修正后通过；6a1e002033 runner exit 141 作废。2026-10-18 多次 t4 尝试在离线 census 阶段因外部 pytest 按较早的严格单飞口径而中断（exit 130），有一次调用因 PATH 无 python 退出 127；这些尝试未启动本 journey 的 Compose 栈，不是产品失败或门禁证据。另有一次运行到 History 后收到 SIGINT，exit 130，操作未终态，作废而非通过；拆栈前保存了 backend、worker、Repository Service 全部日志，记录于 /home/dev/gdds-p5-closure-s1-gate-logs/s3-post-fix-void-runs-20261018.txt 及 s3-post-fix-t4-compose-errors-run5-20261018/。在用户明确允许外部负载低于限额后，最终 run6 在 load 远低于 nproc=96 的条件下完成，未作废。第一次 V preflight 的 pgrep 模式误匹配其自身 shell，没有启动 runner；修正为精确进程名检查后通过，日志在 s3-final-v-preflight-20261018-corrected.log。此前 --validate-inputs 缺主机 pyarrow / root 环境变量和缺 --keep-stack project-name 的检查没有启动真实数据栈。所有重试细节、时间和退出码在外部 void-runs 日志中。
- 镜像副作用另见 §7：final runner 的 client Compose 用例经 docker build -t 改变了 gateway-repository-client-e2e:local 的指向。未手动运行 docker rmi 或 docker tag；base tag 未变。该 side effect 不隐去，交 reviewer 判断与原始约束的关系。
- H0 和最终 H 的 carried 均按 §7 记录并与 V provenance 对齐；未合并或 rebase main、未打 tag、未推送；S4 尚未开始，仍等待 S3 独立审核结论。

## 11. 请 reviewer 重点核查

### 11.1 复现结论

确认真实调试没有复现 HTTP 500 或 `StaleWrite`，持锁超过 5 s 的写入方没有找到；同时查看移除修复时的确定性测试确实失败。read-only UOW 以 `BEGIN` 而非 `BEGIN IMMEDIATE` 消除了只读 operation GET 进入 5 s 写锁等待再落入通用 500 的机制路径。不要把“未复现”写成已找到原写锁 owner。

### 11.2 StoreBusy 503 的全局范围与 Contract 依据

`register_exception_handlers(app)` 在 `http/errors.py` app 层注册 `@app.exception_handler(StoreBusy)`，返回 503 `SERVICE_NOT_READY`，按 HTTP method 无差别生效。Owning Contract `docs/backend-vnext/refactoring/formal/plans/p5-5a-upload-preview-design.md` §3.3 的 503 行允许 `SERVICE_NOT_READY` / `DEPENDENCY_UNAVAILABLE` 表示 registry、ArtifactStore、control DB 或 Repository read 依赖不可用；没有修改 Contract。

因此，任何 endpoint 只要 `StoreBusy` 未在内部处理而逃逸，都会从旧通用 500 变为 503。此全局行为也覆盖可能访问 control DB / operation stores 的 POST：`/v1/workspaces`、`/v1/workspaces/{workspace_id}/upload-revisions`、`/v1/workspaces/{workspace_id}/preview-operations`、`/v1/workspaces/{workspace_id}/submit-attempts`、`/v1/history-compares`、`/v1/submissions/{submission_id}/review-events`、`/internal/v1/operations/{operation_id}/steps/{step_id}/recovery`、`/v1/archive-plan-preview`、`/v1/archive-confirmations`、`/v1/archive-anomaly-resolutions`、`/v1/archives`。该列表描述异常 handler 的覆盖范围，不表示这些 routes 在正常请求中会返回 503。

### 11.3 其他只读 GET 路径

请逐项核实 `ReadOnlyOperationStore`、`ReadOnlySubmissionStore` 及其他只读查询没有用默认写 UOW：

| GET 路由 | control DB / storage 读取方式 |
| --- | --- |
| `/v1/operations/{operation_id}` | `ReadOnlyOperationStore` 用 `read_only=True`；history compare scope authorization 的 UOW 也只读。 |
| `/v1/workspaces/{workspace_id}/submit-attempts/{submit_attempt_id}` | `ReadOnlySubmissionStore.get_submit_attempt()` 用 `read_only=True`；workspace scope repository 的 `_read_uow()` 只读。 |
| `/v1/workspaces/{workspace_id}/submissions/{submission_id}` | `ReadOnlySubmissionStore.get_submission()` 用 `read_only=True`；scope 查询走只读 repository。 |
| `/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}` 和 `/bundle` | `TransactionWorkspaceRepository._read_uow()`、baseline head read 为只读；bundle 内容从 artifact reader 读取。 |
| `/v1/history` | `application/history/queries.py` 显式 `unit_of_work_factory(read_only=True)`。 |
| `/v1/history-compares/{operation_id}` 和 `/bundle` | operation/submission reader、授权、compare result 与 checkpoint UOW 均只读；bundle artifact 为文件读取。 |
| `/v1/submissions/{submission_id}/review` | `get_review_facts()` 显式使用 `read_only=True`。 |
| `/v1/archive-candidates`、`/v1/archive-audit-events`、`/v1/archives/{archive_result_id}` | `application/archive/queries.py` 查询 UOW 显式只读。 |
| `/healthz`、`/readyz` | 静态状态 / app readiness flag；route 不开启 control DB UOW。 |

`GET /v1/workspaces` 不存在；collection 创建 route 是 POST。工作区读取经 workspace repository 的只读 UOW。

### 11.4 终态之后的无界等待与 drain

核对 `operations/worker_runtime.py` 的 `completed.wait()`：在 durable terminal acknowledgment 已确认、heartbeat 随后遇到 `StaleWrite` / `LeaseExpired` 时，supervisor 会无限等 executor thread 的 `finally` 设置 event。如果 executor 线程在 durable terminal commit 后卡住不返回，supervisor 不会离开 wait 去执行 `thread.join()` 之后的 lifecycle timeout 检查，也不会回到 claim loop。SIGTERM handler 只执行 `stop_requested.set()`；该 event 不会唤醒 `completed.wait()`，所以 drain intent 即使到达也不能在 wait 期间被 runtime 处理。若 drain deadline 已开始，墙钟会继续走过 deadline，但代码无法在该 wait 中调用 `check_timeout()` 或发出 drain-timeout event。

Compose worker 配置 `stop_grace_period: 180s`；容器停止超时后 Docker 会发 SIGKILL。durable terminal 状态已经提交，不会因进程被杀而变回 RUNNING，也不会重新领取该 operation；但 graceful drain 和进程停止可以延迟至 executor return 或 180 s 强制终止。没有证据证明 executor 在终态提交后绝不可能卡住；这不是本修复已验证的不变量，需 reviewer 明确评价其对 S3 exit 的影响。

## 12. 审核提示词

任务：独立审核 P5 架构收口 S3。你没有参与 S3 的实现；按 `docs/backend-vnext/refactoring/formal/guides/slice-design-execution-and-review-guide.md` §5–§6 审核，不预设结论。

审核对象：分支 `p5-s3` 的 H（本 handoff 最后提交），门禁提交 V=`dc9c08a410829f303aae1e0f826c674b335cb94b`，实现 HEAD=`dc9c08a410829f303aae1e0f826c674b335cb94b`，区间 `p5-g11b-exit` (`944982eb910dab9cbfc117a976dea6721cdd6ca2`) .. H。只审该区间的实现和 handoff。review worktree 用只读 detached checkout，并创建 `legacy` 符号链接；不要在实现 worktree 写文件或跑测试。

权威依据：执行计划 §2 S3、§3 S3、§4、§6、§7、§8.1、§8.2、§8.7、§8.9；设计 §8、§4.4、§4.6、§12、§14；决议 DC4、DC8、DC20、DC22、DC30、DC31；owner 决议 `7c77b5e8c8` 与 `c09c95fd81`（在 main 上）；Contract logics.xml 条款和 `p5-5a-upload-preview-design.md` §3.3 的 HTTP 503 条款；S2b handoff §8.5、§8.6、§8.9；本 handoff。

必须核查：

- S3 composite schema、Preview 业务物化、DC8 公开 diagnostic、规则和 projection、canonical golden、checkpoint 内容、路径预算及 `test_comparison_canonical_domain.py` 全表 UNCHANGED / 零记录不变量与生产路径零行 composite fixture。
- 8 个 S3 unreachable modules 删除与 `import_rules` kickoff 0/0/14 → V 0/0/6；五包 Ruff / mypy 和 runner 用例计数（对照 G11b 与 f73 runner）。
- V clean 权威 runner 的 HEAD / status / exit，RS 两个 provenance label 与 identity，V image IDs，final H carried 重算与两次 backend/worker build；核查受保护 client 镜像记录，尤其 `gateway-repository-client-e2e:local` 在 V runner 中由 Compose 测试的 `ensure_client_image()` 触发 `docker build -t` 后变更了 ID、base tag 未变，且没有手动执行 `docker rmi` / `docker tag` 或尝试恢复。
- 第一次和第二次 STOP、owner 决议及每个 void run；真实 debug 的 500 / StaleWrite “未复现”，无修复确定性测试失败、写锁 owner 未找到，以及只读事务如何消除 500 机制路径。
- `StoreBusy` app-wide 503：确认 §3.3 Contract 条款覆盖 control DB 依赖，列出受影响 POST routes，并判断 503 影响范围是否合理且无需 Contract 修改。
- 对所有 GET route 逐项确认 read-only transaction 模式，特别是 workspace、submission、preview、history、archive 与 health/readiness。
- 按 §11.4 判断 terminal-ack 后 `completed.wait()` 无超时的 liveness / drain / SIGTERM 后果；代码没有证明 executor 不会卡住。指出该已披露限制是否阻止批准 S3 exit。
- V 上 t4 完整 journey 与 t1 冒烟；t2/t3 沿用 `f73deee604` 的精确 path audit；Preview、Catalog 扣除 composite 行数、离线生产比较、History、INITIAL、重复 v1、IEC104 四项和 DC29 keyless 不变量；A/B/C 及复用 digest 的明确限制。
- STOP 条件和设计 §14 条件是否都未触发；S4 未启动。

验证：在只读 detached worktree 中运行五包 Ruff / mypy 与 `import_rules`；审阅门禁日志与 real-data 证据，不要求重跑完整 runner 或真实 journey。若需重跑，按 AGENTS.md clean commit、worktree 不写入、整机单飞和日志规则执行。

交付：按执行计划 §8.8 写 `p5-arch-closure-s3-independent-review.md`，仅作为单独文档提交。若审核通过，审核方按本任务流程把报告提交快进到 `p5-s3`，在报告提交打附注 tag `p5-s3-exit`，再以 `--no-ff` 合入 `main`；不推送。未通过则按报告结论处理。S4 仍须等待 S3 审核通过。

允许结论：通过 / 定向修订 / 整体返工。
