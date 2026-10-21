# P5 架构收口 S4 独立审核

- 结论：**通过**（终审 2026-10-21）。初审结论为定向修订（S4-F1）；终审确认 S4-F1 并在 handoff 中关闭，另提出 S4-F2，owner 决议按方案一处理并转为 S5 携带项，见 §7。
- 日期：初审 2026-10-21；终审 2026-10-21
- 终审对象：`p5-s4` @ `130a91103e070031f923716ad1c90625543bc5d7`（H，V 未变）；tag `p5-s4-exit` 指向本报告的终审提交
- 审核对象：`p5-s4` @ `d0b20ede10bdf26d36d68ed543b13084d50bd097`（门禁提交 V `ed70ca1be262653bb49267940e73e7edd09a2267`，实现 HEAD `ed70ca1be262653bb49267940e73e7edd09a2267`），区间 `13d97dc2db5cef4bd82583ab7ac339ed09b5aec3..d0b20ede10bdf26d36d68ed543b13084d50bd097`
- 依据：执行计划 §2/§3 S4、§8；设计 §7.1–§7.7/§12/§14；ADR 0020；Business Lifecycle 3.1.0 身份条款；[S4 handoff](p5-arch-closure-s4-handoff.md)

## 1. 结论摘要

实现与 V 上的功能、runner、容器和真实数据证据总体符合 S4 目标；身份判定、Submit/Archive 行为、三条 Compose 流程、停滞根因更正、RS 共享连接测试修复，以及 V→H 的 carried 证据均可由源码和 ct108 原始日志互相印证。`reconcile_elapsed_seconds=0.0` 与 handoff 所述“三个至多 60 秒的会话”一致；本次 t4 v1 Submit 使用 2/3 个会话，余量支持在 S5 执行完整 t4，但 S4 的 t4 证据仍只覆盖 v1 Submit 与 v2 Preview。

有一项阻塞 finding：handoff §3 的路径预算偏差表没有交代数个实际变更的生产与测试路径。路径偏差说明是本阶段验收材料的一部分，因此本次不判 S4 通过、不打阶段 tag，也不启动 S5；实现者补齐路径映射后按 finding 复审。

## 2. Findings

### S4-F1：handoff 未完整记录超出 §3 S4 路径预算的变更路径

- 类型：已证实缺陷（交付记录缺口）；是否阻塞：是
- 位置：[S4 handoff §3](p5-arch-closure-s4-handoff.md)；审核区间内的文件清单
- 依据：执行计划 §3 规定必改/条件路径，并要求新增文件名或路径调整在 handoff 中说明；§8.2 要求 handoff 记录路径预算偏差、条件路径与文件改名。handoff §3 的偏差表列出 G12-F1、诊断/t4、Submit 重试和 RS 测试竞争四组，但区间中还有未映射到这些组、也未逐项解释的改动，例如 `application/history/contracts.py`、`application/submission/finalize.py`、`capabilities/comparison/standard.py`、新增的 `domain/submission/reasons.py`、`http/mappers.py`、`infrastructure/control_db/history_reader.py`、`infrastructure/control_db/sqlite_history.py`，以及 `tests/support/compose_gate_harness.py`、`tests/support/http_workspace_harness.py`、`tests/support/workspace_fixtures.py` 和若干 S4 §3 未列测试模块。
- 触发场景与影响：按要求独立核对 `13d97dc..d0b20ede` 的实际文件集时，无法从 handoff 区分这些路径是必需的 owning-contract 实现、预算内路径名调整，还是另行启用的范围；因此当前交付记录不能完整证明路径预算验收已完成。此 finding 不表示这些改动本身已证实违反设计。
- 最小修正方向：在 handoff 增补完整映射：逐项列出不在原 §3 S4 必改/条件清单中的代码、测试与新增文件，说明对应验收/Contract、为何需要该路径，并标明命名调整或已有 owner 授权；若属于新增范围，先补相应预算/授权记录。
- 关闭标准：新的候选 handoff 可将区间内每一条超预算路径映射到验收项和理由；复审确认没有未解释路径。该修订只涉及文档时，仍按 DC34 在同一门禁 worktree 重新核对 H manifests 与镜像 label carried。

## 3. 验收核对

| 验收项（执行计划 §2 S4） | 结果 | 证据 |
| --- | --- | --- |
| S4 目标、变更范围与路径预算 | 定向修订 | 身份/替换功能满足目标；但 handoff §3 的路径偏差清单不完整，见 S4-F1。 |
| `version_manager` 身份规则与投影/Repository 侧一致性 | 通过 | `project_identity._rule.assess_project_identity()` 是共用判定；`test_project_identity.py` 的规则参数表覆盖相同行集合、排除 `no`、缺表/空表/无身份列/列集合不符和标量差异；SQL 与 Repository materialization parity 参数表覆盖 SAME、DIFFERENT、UNVERIFIABLE。初始空基线由 Application 标记 `NOT_APPLICABLE`。 |
| 替换比较事实、风险、surface 与双侧 bundle | 通过 | `comparison/replacement.py`、risk/surface/bundle 接线与相关测试；Preview 保存身份评估与两侧快照。跨项目 Compose 分支断言 `DIFFERENT_PROJECT`、`DATASET_REPLACEMENT`。 |
| Submit 身份确认、授权/scope 顺序与 same-key 重放 | 通过 | `accept.py` 先权限和 scope resolution，再在重放查询前校验 exact workspace scope 与 Repository 映射；写事务内重新检查 fresh mapping/exact scope 后才返回重放。`test_t1_replay_rechecks_current_permission_and_exact_scope`、mapping-disabled 并发赢家测试及 head-only drift 重放测试覆盖授权、精确 scope 与可漂移前置。确认摘要、必需/多余动作和请求指纹有事务测试。 |
| 确认理由校验和 Review 行为 | 通过 | Submission 共享理由校验只对身份确认允许 CR/LF/TAB；Review 仍 `allow_multiline=False`，并保留原有空白/规范化行为。共享参数表和 Review domain/HTTP 测试覆盖。 |
| Review/History 展示、Archive 身份异常处置与 StartArchive | 通过 | Review/History 只读映射确认记录及异常标记；Compose 用例在处置前阻止 Archive，分别确认 sibling exclusion 与 identity exception，再通过 `StartArchive`，检查 audit 与重启后读取。 |
| schema、HTTP DTO、checkpoint、golden/OpenAPI 目标形态 | 通过 | control DB 单一基线直接加入确认字段并泛化 anomaly target 字段；DTO 使用 `target_submission_id`/`target_candidate_digest` 和 identity 字段，没有旧字段别名。Preview assemble-state 升到 v2、materialize-side 升到 v4，并严格核验 identity pair 字段；Submit/Archive DTO 使用 `extra="forbid"`。OpenAPI 断言同步；区间无独立 golden 文件，相关 fixture/契约断言更新。无 migration、双读写或旧字段兼容。 |
| 三条 Compose 身份旅程 | 通过 | `test_archive_compose_e2e.py` 在一个既有三容器栈依次覆盖跨项目 replacement、UNVERIFIABLE 和 FULL mixed baseline→initial replacement/initial→modified SAME_PROJECT；各分支断言 Preview、确认、Review、Archive 行为。V 的 backend Compose 批次包含该测试。 |
| 10 月 20 日人工恢复原因更正与诊断证据 | 通过 | 两份诊断均显示 parent/await step 为 `MANUAL_RECOVERY_REQUIRED`、`attempt_count=1` 且无 lease，Repository API 为 HTTP 200/SUCCEEDED，worker 线程空闲等待；S3 对照相同。46/100 个线程的 `/proc` 等待点为 futex；第一份 Python-only py-spy 显示 worker idle。native py-spy 的 `UNW_EBADREG` 错误留存。支持“60 秒会话过期→人工恢复→worker 空闲→harness 等到 timeout”的更正，不支持“worker 卡死”作为根因。 |
| 停滞检测、先诊断后拆栈与分类测试 | 通过 | `real_dump_journey.py` 以 heartbeat event 与阈值区分 `worker_stalled`/timeout，诊断先于 teardown；五项确定性测试覆盖心跳、阈值、采集顺序、嵌套 RS 状态和 timeout 区分。诊断目录与调试日志在 ct108。 |
| `bafd64bf53` 重试修复、负向测试及 R5 耗时边界 | 通过 | `test_await_import_result_timeout_retries_until_repository_operation_is_terminal` 在 60 秒 poll 超时后断言 checkpointed RETRY_WAIT、attempt 增加、原 operation 终态成功；撤掉修复的负向日志显示该用例失败，恢复后 focused 通过。R5 定义每 Step 最多 3 个 session、每个 active reconcile session 60 秒；Repository client 每次 wait 的默认 poll deadline 为 60 秒，step attempt_count 达 3 后现有 policy 进入人工恢复。这里 `0.0` 表示下一 session 尚未消耗 elapsed，不是累计 60 秒预算；未发现超出“三次、每次至多 60 秒”的路径。 |
| t4 79 秒 RS import、2/3 session 与 S5 完整 t4 余量 | 足以支持 S5 执行；S5 仍须完整实测 | 新 V t4 v1 Submit operation 576.497 秒、step 578.201 秒；RS import 79 秒且成功；`await_import_result` 2/3 session，余一个最多 60 秒 session。按单次观测，v1 import 落在 3×60 秒上限内并有余量，支持安排 S5 完整 t4；不构成性能保证。S4 范围未包括 t4 v2 Submit、v2 Catalog 或 History，不能沿用为 S5 的完整 t4 证据。 |
| `22c1a7e530` 失败用例与共享连接读写排查 | 通过 | 失败为 `test_ready_file_without_db_is_not_visible` 在共享 `mutation_store._connection` 上未持锁 DELETE/COMMIT，与 app 后台事务竞争。修复限 tests：在 `transaction_lock` 下显式事务删除；16 次并发重复均通过，shared-connection focused 12 passed、worker-lock focused 3 passed、RS unit 1,534 passed/1 skipped。handoff 记录了 `_connection`/`execute`/`commit` 全量搜索及命中分类；22c runner exit 1 未作为任何包来源。 |
| runner 计数、按包沿用来源与真实数据范围 | 通过 | V 在 ct108 clean worktree 运行 backend 与 Repository Service：backend 2,901 并行 +36 serial；RS 1,724 并行、1 skipped +205 serial。shared_kernel 242、repository_contracts 152、repository_client 154 按 manifest 沿用 clean、整次 runner exit 0 的 938d V。t2/t3 也按 owner 条件沿用 938d：`938d..V` 仅改真实数据 harness、Submit timeout/retry 与 RS tests，无投影、比较、身份、composite、canonical storage 或 census 业务实现。新 V t1/t4 identity scope 与跨项目旅程 PASS；与 S3 的 t1/t4 已运行摘要一致，未把未运行的 t4 v2 Submit/History 当作新 V 证据。 |
| H 的五包 manifest 与 Repository Service labels carried | 通过 | ct108 同一 `/home/dev/gdds-p5-s4` worktree 上，H 的五个 compare 均 `changed_components=[]`，source/current 摘要依次相同：shared_kernel `c17741f99a8f62d6564fac4cc7abef43b922bd8b345ea7bfbcd602c846c7e44e`、repository_contracts `aca07576becbe8cee5a24b4d74c5577a0874263054bd7b37bd773796b2ba7657`、repository_client `4b7fd4989420e4457f9e6a8dea018810647c2c582e8465892b575e145a0c2f1b`、backend `a7f4ccc910ecf7502740fd080aafbc520ca0c8ded8e70415f46fc950cba62473`、repository_service `33cc2fe2919184c7951fad1eb742845c47e6429d8652dd1d48759d4ac024b941`。前三包来源 938d，backend/RS 来源 V。`s4-h-carried-identity-final.log` 记录 H=d0、build-input revision=V、source-tree `sha256:a3e56c4d90e67ba80b632599ead9dca8fc65d13d2193ad0f42472d9a9f68be3a`、clean=yes、label compare PASS，与 V Repository Service image labels 匹配。 |

## 4. 实际执行的检查

| 检查 | 命令/来源 | 结果 |
| --- | --- | --- |
| 目标 worktree 与区间 | detached worktree `/tmp/gdds-p5-s4-review-d0`；核对 `13d97dc..d0b20ede` 变更和 handoff | HEAD 为 d0；只读源码/文档复核。 |
| V 权威 preflight | ct108：`s4-v-preflight-ed70ca1be2.log` | HEAD=V、branch `p5-s4`、clean、legacy link 存在、TMPDIR 存在、无 Dolt/Compose/容器、8000 空闲；PASS。 |
| V 权威 runner | `GATEWAY_TEST_PACKAGES=backend,repository_service GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh`；`s4-v-runner-ed70ca1be2.log` | 开始 00:33:08Z，起始/结束 HEAD 均 V，起止状态 clean；backend 2,901+36 passed，RS 1,724 passed/1 skipped +205 serial；exit 0，结束 01:11:26Z。 |
| 三包来源 runner 与失败来源排除 | `s4-v-runner-938d41d171.log`；`s4-v-runner-22c1a7e530.log`；V compare 日志 | 938d 包实际通过且整次 exit 0；22c 五包 runner exit 1，排除为沿用源；compare 只将三个未变包沿用 938d。 |
| G12-F1 client rebuild/manifest | ct108：`s4-g12f1-client-compose-98fd6c912b.log`、`s4-g12f1-client-compose-post-98fd6c912b.log`、`s4-g12f1-rs-manifest-before-7e00092d14.json`、`s4-g12f1-rs-manifest-after-98fd6c912b.json` | Compose client 用例通过并重建 client image（ID `sha256:3133afd8…`→`sha256:befb5bba…`）；Repository Service manifest source/current 均 `01b82d2a25536f4ea3a2e8b54bda71bd6c2b70e32a83d84da8b6db45137a4664`，无 changed components、可沿用。 |
| S4 focused/静态/import rules | ct108：`s4-static-five-packages-ed70ca1be2.log`、`s4-import-rules-ed70ca1be2.log`、`s4-debug-stall-reconcile-negative-4a02bea8.log`、RS focused/repeated logs | 五包 ruff/mypy 通过；import rules 0/0/6；修复撤除时负向测试失败；RS 重复与 focused 结果见 §3。 |
| 真实数据、诊断与 container provenance | ct108：`s4-realdata-t1-full-ed70ca1be2.log`、`s4-realdata-t4-identity-ed70ca1be2.log`、`s4-realdata-cross-project-ed70ca1be2.log`、诊断目录 `s4-stall-20261020T132915988408Z/` 与 `s4-stall-20261020T151720059085Z/`、V runner Compose journey；`s4-h-manifest-compare-final.log`、`s4-h-carried-identity-final.log` | 按 handoff 核对；V→H carried 条件满足。真实数据只有 S4 批准范围，没有把部分 t4 写成完整 t4。 |

本审核未另行启动测试、Compose 或真实数据旅程；结论基于只读代码审查和上述 ct108 权威/调试原始日志。所有被引用的测试与容器证据均在 ct108；没有采用其他 worktree 的 carried 判断。

## 5. 验证限制与剩余前置

- S4-F1 关闭并复审通过之前，不打 `p5-s4-exit`，不进入 S5。
- 关闭 finding 后，S5 最终候选仍须按执行计划完整运行五包权威 runner、fresh 容器门禁及完整 t1–t4 真实数据链路；S4 的 `t4-identity` 不能代替 S5 full t4。
- 本审核没有声称 S5 容量目标已满足，也没有将单次 79 秒 RS import 外推为稳定上限。

## 6. 复审记录

S4-F1 的修订由审核方按 owner 授权直接完成（`130a91103e`，只改 handoff §3），复审并入 §7 终审，不另行复审。

## 7. 终审（2026-10-21）

### 7.1 核查

- **路径预算（S4-F1）。** 用执行计划 §3 S4 的清单逐项对照 `p5-g12-exit..d0b20ede10` 的实际文件。除 handoff 已说明的四组路径和 RS 测试外，另有 8 个生产文件、17 个测试或测试支持文件没有说明。逐个阅读改动后确认：它们是设计 §7 验收在清单路径之外的接线（finalize 冻结身份确认、`standard.py` 接入替换比较、History 只读展示身份异常、Preview DTO mapper）、DC28 共享理由抽取的落点（新增 `domain/submission/reasons.py`），以及 DTO/字段目标形态带来的测试更新。`test_history_compose_e2e.py` 删除的内联处置代码改由共享 helper 逐项处置并断言 201，另加 anomaly 数断言，没有削弱。区间中的 AGENTS.md、testing-conventions 等文档改动来自截至 kickoff base 的 main 上 G12 收尾提交。S4-F1 成立，不涉及代码。
- **R5 耗时预算（S4-F2，终审新提出）。** 在 `operations/recovery.py` 的 `transition_for_outcome()` 中，`RECONCILE_PENDING` 先检查会话数，再以 `reconcile_budget_exhausted(reconcile_elapsed_seconds)` 判定是否转人工恢复。修复处的会话刚好跑满 60 s，传入实际耗时会转人工恢复；传 `0.0` 等于跳过耗时检查。R5 设计 §6 规定对账预算用尽即转 `MANUAL_RECOVERY_REQUIRED`；Submit checkpoint 持久保存 `reconcile_started_at`，重试时保留不变，按设计预算应从对账开始累计计时。累计预算函数 `reconcile_session_budget_exhausted`、`parse_reconcile_started_at` 目前没有生产调用方。初审所述“0.0 表示下一会话尚未消耗耗时”与持久保存的起点不符。修复后的实际上限为 3 个 60 s 会话，行为合理且有上限；问题在于它以字面量隐性改变了 R5 的规则。
- **余量。** 同意初审：t4 v1 Submit 的 RS import 79 s，使用 2/3 个会话，余 1 个；足以安排 S5 的完整 t4，但不是性能保证，S5 须实测。
- **新 H 的 carried（DC34）。** 新 H `130a91103e` 只比 `d0b20ede10` 多 handoff 文档。经 bundle `s4-sync-final-review-130a91103e.bundle` 同步到 ct108，在运行 V runner 的同一 worktree `/home/dev/gdds-p5-s4` detached 检出，clean。五个包 compare 均为“可沿用”，总摘要与来源一致（前三包来源 `938d41d171`，backend/RS 来源 V）；`build_context_digest.py identity` 得到 `build_input_revision=ed70ca1be2…`、`source_tree_sha256=sha256:a3e56c4d…`，与本机 `gateway-repository-service:local` 的两个 label 相同。日志 `/home/dev/gdds-p5-closure-s1-gate-logs/s4-final-review-carried-130a91103e.log`，脚本 `s4-final-review-carried.sh`，manifest 在 `s4-final-review-manifest-current/`。
- **其余验收。** 抽查身份规则共用、受理顺序、Compose 旅程与真实数据日志，与初审一致；未另跑测试。

### 7.2 Findings 处置

| Finding | 处置 |
| --- | --- |
| S4-F1：handoff 未完整说明超出预算的路径 | 已关闭。审核方按 owner 授权在 handoff §3 补齐逐项映射（`130a91103e`）。 |
| S4-F2：`reconcile_elapsed_seconds=0.0` 隐性改变 R5 耗时预算 | owner 决议（main `fd2282c1e0`，治理修订计划 §3 第 11、12 项）：Submit 的 `await_import_result` 以 R5 的 3 个 60 s 会话为上限，S4 不改代码；S5 携带项负责改为显式、有名字的 import 轮询预算，在 Contract 层面写明与 R5 的关系，清理无调用方的累计预算函数，并在完整 t4 中记录 RS import 用时与会话数。 |

### 7.3 其他

- 初审报告最初提交在 main（`9187b58139`），没有在阶段分支上。本报告的终审版本提交在 `p5-s4`，合入时以分支版本为准。
- manifest 记录 HOME、LC_ALL、UV_CACHE_DIR 等环境变量的指纹。第一次核对沿用了 G12 脚本的环境（HOME=/home/dev、设置 UV_CACHE_DIR、不设 LC_ALL），backend/RS 判为“运行”，差异只在这些指纹；改用 V runner 的环境（HOME=/root、LC_ALL=C.UTF-8、不设 UV_CACHE_DIR）后五包均“可沿用”。该次尝试保留为 `s4-final-review-carried-130a91103e-env-mismatch.log`。handoff §10 只记录了 PATH 与 TMPDIR，S5 的 handoff 应记录 runner 与 carried 判定使用的完整环境。
- 结论：S4 通过。`p5-s4-exit` 打在本报告的终审提交上，`--no-ff` 合入 main；S5 按治理修订计划 §3 第 12 项 kickoff。
