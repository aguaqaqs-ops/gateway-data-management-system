# P7 后端专项整顿执行计划

日期：2026-11-12。阶段名：`p7-backend-remediation`；退出附注 tag：`p7-backend-remediation-exit`。
状态：**已按 2026-11-13 计划复审补齐，复审结论为改完即通过、无需再评；未实施、未测试**。Owner 已确认方向，本次只准备正式文档和实施提示词。
来源：Owner 的 `remediation-input-backend.md`（下称“输入”）及 `project-review-2026-11.md`（下称“复盘”）；原件存于 `/home/dev/gdds-stage-exchange/p7-backend-remediation/design/`。正式决议见 [S0 §19](p7-s0-owner-decisions.md#19-后端专项整顿与后续阶段收窄2026-11-12)。

## 1. 入口、冻结与规模

输入的统计基线是 `4276b22c69`；本设计按 main `8739d4094e357f32b7c326204d6aa0aa33e868de` 只读核对路径和符号。该提交已包含本地附注 `p7-s2b-exit` 指向的 `64b89505f411fda1623858a95b1ca408b9ebe50d`；这只是入口事实，不重评 S2b 证据或改其范围、角色、方案。本次修订另核 main 的现行规则（含 `8dafcf92b8`、`df0356baa4`）；合入 main 时重新核现行 AGENTS 的角色、校验与身份、测试 artifact ID 和总结条文。实施前重新核 tag、main 祖先关系、活动工作区与实际源码，不能用本文行数作删除依据。

整顿在 S2b 本地 exit 且合入 main 后开始，四批完成才进入 S3。输入 §7 的第二轮 L5 **没有本轮计划、分包、排期或实施授权**；只把试点报告交 Owner 决定。

- 除输入 §2 已批准的删除，不改变接口、错误码/HTTP 状态、文档字节、digest、golden。Owner 于 2026-11-13 另批准 P1 删除只写不读 digest（先交字段清单、公开 DTO 字段逐项决定、最终 V 前落地）及 G2 公开 OpenAPI 移除内部路径和仅由其引用的 schema 组件两项例外，范围见 §7；其余冻结不变。
- 不改 `frontend/`、`AGENTS.md`、`testing-conventions.md`；前端与规则会话都经 Owner 转交，后端不直接联络。S2b 已改前端请求层，前端应从其退出后的 main 起步。
- 不增加框架、服务、依赖、兼容层或转发模块，不改锁文件以配合整顿。调用方和测试直接更新导入。
- 预计删除源码约 9,500 行（C1 5,800、C2 2,800、C3 800、J2 250），测试约 5,000 行；移动约 11,000 行。它们是量级，不是验收配额，不叠加统计移动删除和真实净减。
- 预计 4 个批末门禁点；5 个重点独审对象（C2、C3、J3、K1、L2），再一次整轮独审。实际修复由原审复审，不因小节/角色更换增设全量门禁。

### 1.1 开工核收（2026-11-13）

已核 main `74a0f326bfdaf402c8cb372246d761ab6461d6c0`：S2b 附注 tag 指向 `64b89505f411fda1623858a95b1ca408b9ebe50d` 且为 main 祖先；FE4 退出记录 `ae4884c12e`、后端复审修复 `57b9a99073`（合入 `0ca9281d3c`）和前端定稿 `8459d1b628`（合入 `98abf25c19`）均已进入 main。计划层面的开工前提已满足，无需再做总体计划复审。实施者以实际启动时最新 clean main 为 B，记录完整 SHA、frontend/vnext tree 与本次核收点的差异；本次补充不启动产品实现或测试。

Owner 本次确认：后端继续现有角色分工与模型选择原则（§3），前端由单 agent 实施，不套用后端团队；两端配合仅由 Owner 转发。第 4 批真实数据配置和 P1 字段清单是后续局部检查点，不阻塞前三批开工，不把文档准备当作对尚未知字段/运行条件的批准。

## 2. 工作包与源码接点

下表路径以 `vnext/backend/src/gateway_backend/`（BE）、`vnext/repository_service/src/gateway_repository_service/`（RS）为根；测试相对各包 `tests/`。风险依[比例化政策 §4](../policies/proportional-assurance-and-risk-based-verification-policy.md#4-risk-classes-and-default-assurance)：A 权威/安全边界，B 持久可恢复状态，C 可重建产物，D 内部机械改动。工作包编号与风险字母无关。

### 第 1 批：删除与格式化

J6 必须先落单独格式化提交，再开展其他修改。C1 与 C2 可分别实施，C3 **依赖 C2**；worktree 盘点独立进行。输入“互相独立”不覆盖其 §2.4 的明确依赖。

| 包 | 源码与目标 | 风险及验证方式 | 独立审核 |
| --- | --- | --- | --- |
| J6 | BE 源码和测试，以已锁定 Ruff 全量 format；仅 `vnext/backend`。随后另一个提交将 `ruff format --check src tests` 接入 `vnext/scripts/run-tests.sh` 的 backend 环境同步后、pytest 前的失败即停止路径 | D；格式化提交不夹带逻辑/规则改动，核 docstring/字符串值、golden 与锁文件未变；Ruff/mypy、批末 backend 回归。检查命令非零必须传播到 runner/stage gate，不能只打印 | 实施者＋门禁 |
| C1 | 删 RS `matrix.py`、`workflow.py`、`workflow_worker.py`、`fixtures.py`、`filesystem.py`、`storage.py`、`target_gate.py`；沿引用删 `providers.py` 的 `SqlServerProvider`、`discard_table_to_devnull` 和 `process.py` 的 `ServerSupervisor`、`preflight_cgroup` 等专属尾部；删专属两测试、Compose `repository-probe` 及专属 launcher/systemd | D，触及容器接线为 C；先反向查生产/脚本/测试消费者，保留产品 `CandidateADoltCli`、Dolt 版本核验及仍使用的进程能力。`fixtures.generate_fixture` 移至 `tests/support/`；修 `test_import_verification.py`、`test_p2_r2_compose_integration.py`、BE `test_backend_dockerfile_contract.py`。批末 RS 集成/容器门禁与 backend Compose | 实施者＋门禁 |
| C2 | RS `artifact_cleaner.py` 只留 `_process_candidate`→`artifact_cleanup.py` 最小协议；删 sidecar/unlink-stage/receipt/residual 分支，连同 `upload_artifact/admission_pin.py` 名字解析、`mutation_store.py` 无写入读取/清除方法 | C，protected retention/root 越界最高 A；保留 admission pin、eligibility 重读、server-owned exact path、root/symlink、成功先持久化再清理、I/O 重试。未知旧名字只诊断；`test_artifact_cleaner.py` 删除旧形态证明，保留 `test_artifact_cleanup_integration.py` 等成功前/成功后/清理失败三个屏障 | 一次，核删除集合与保留边界 |
| C3 | RS `control_db.py` 将 V2–V16 合为单一基线；C2 后删除无写入列和 `artifact_residual`，同步 store/row 解码及 `test_auth_lifecycle.py` 迁移用例 | A/B；新建、重启、精确 schema 不符拒启（不只判断 newer version）、事务回滚和业务恢复；保留 mutation/idempotency/result 等在用约束。只清本人确认可重建的 RS SQLite 及 `-wal/-shm`，不删除 Dolt/别人的卷，不自动降级或回填 | 一次，独立于 C2 |
| WT | 用 `git worktree list --porcelain` 重新列数量/祖先关系/dirty/锁定/用途；排除活动会话、未知用途、被引用证据与 carried 来源 | D；先展示候选数量和排除理由给 Owner，按现行回收授权处理 clean、已合入、用途结束的树；不用 force，不删 dirty/未知树，不把“已合入”当唯一条件；核回收后目录/登记一致 | 实施者记录，无代码测试 |

C1 保留 `vnext/deploy/p2r1-cache/Dockerfile.dependency-base`、在用构建/缓存端点、`gateway.p2r1.*` labels 和 `gateway-p2r1-repository` image 名。MySQL 驱动留到下次**已授权依赖变更**再顺带删，不单独重建依赖基镜像。RS/deploy README 已在文档准备中撤下 probe 操作入口；实施后补真实删除提交，不把本文当已删除代码的证据。CLI 真实读取/并发遇硬限制才从 Git 历史重开选型工具。

### 第 2 批：结构移动

严格按 J2→J1→J3→K1→G1→G2 串行。每一步先做调用与类型依赖清单，迁移后删除旧实现，提交可单独审阅，不将去重、语义改写混在一次文件移动里。

| 包 | 源码与目标 | 风险及验证方式 | 独立审核 |
| --- | --- | --- | --- |
| J2 | `application/preview_jobs.py`、`submit_jobs.py`、`history/compare_jobs.py` 的八个共用函数移至已有 `application/job_steps.py`：checkpoint generation、load step、cancelled builder、successor builder、stopped cancellation、non-empty string、terminal step、resource-failure wrapper | B；逐个对比三个实现，只有有意差异才以显式参数保留，不能把 0.9 相似当等价。跨目录使用的共用函数改为公开名称，避免 J4 又拦住新布局；恢复/取消/terminal focused | 实施者＋门禁；J3 独审覆盖共享步骤调用 |
| J1 | 快照 descriptor 编解码移至 `capabilities/snapshot_materialization/documents.py`，storage facts 编解码移至 `capabilities/comparison/documents.py`，公开原语；History/Preview 直接导入能力 owner | A/B（摘要与恢复）；保持键、null/缺省、列表顺序、整数/布尔域、错误映射、canonical 字节和 digest。包内 checkpoint 字段仍归 application；此步不引入声明式改写 | 实施者＋门禁；J3 核对持久载荷 |
| J3 | 三个作业模块拆包，具体布局见下表；调用方、bootstrap、harness 与测试直接更新导入，无旧路径重导出 | A/B；`test_job_payload_decoding.py`、`test_operation_checkpoint_contracts.py`、`test_operation_job_recovery.py`、Preview/Submit/History job 测试、presentation golden 与实际 digest 比对；原 effect、CAS、保护释放次序不变 | 一次，覆盖三个包和 J1/J2 接线 |
| K1 | `http/orchestration/operation_scope.py`→`application/operation_reads.py`；History 结果读取→`application/history/results.py`；Submit preflight/accept→已有 `application/submission/accept.py`/`accept_transaction.py`；运维恢复执行→`application/submission/operator_recovery.py` | A/B；用例入口接身份上下文并首先授权；application/domain 抛其自身错误，由 `http/errors.py` 映射。`http` 的 DTO/依赖 Protocol 不搬作 application 依赖，必要窄 port 放用例所属 `ports.py`。HTTP 正/负路径逐项核错误码、状态、拒绝顺序、隐藏对象语义；恢复未知 effect 不重放 | 一次 |
| G1 | `capabilities/bundle_assembly/contracts.py:BundleInput` 与 Preview bundle 构造点；[bundle Contract](../../../contracts/comparison-bundle.md) 明确 Preview 三角色与 History ref 语义 | C，冻结摘要；只在 Preview 构造边界约束 `baseline/initial/modified`，通用 `role: str` 不改成全局三值枚举；History 继续 node `ref_id`。现有三角色/History 向量，字节/digest/golden 不变 | 实施者＋门禁 |
| G2 | `http/wiring.py` 的 router 注册与 `/internal/v1` 所属 routes（维护、注册及统计，逐个核注册点）；`test_http_openapi.py` | C；设置 `/internal/v1` 路由 `include_in_schema=False`，保持路由存在、内部认证/调用与公开 `/v1` 不变；冻结测试区分 public schema 与 runtime route。按 2026-11-13 R2 决定同时移除仅被内部路径引用的 schema 组件；`PRODUCTION_OPENAPI_PATHS` 拆为公开 schema 路径集合与运行时路由集合，两者分别保留冻结测试 | 实施者＋门禁；阶段末检查授权边界 |

J3 目标布局（不是新的执行框架）：

| 旧模块→包 | 文件及职责 |
| --- | --- |
| `application/preview_jobs.py`→`application/preview_jobs/` | `definitions.py` 注册/组合；`payload.py` 载荷/依赖类型；`materialize.py` 三侧物化；`assemble.py` pair/surface/bundle；`publish.py` 原子业务发布；`checkpoint.py` job_state/闭包读写；`failures.py` 失败/取消发布 |
| `application/submit_jobs.py`→`application/submit_jobs/` | `definitions.py`；`payload.py`；`prepare.py` 冻结导入输入；`submit.py` 发送 effect；`await_result.py` 查询/等待；`checkpoint.py` 原状态文档；`recovery.py` 普通及 operator 恢复；`failures.py` 有限失败发布 |
| `application/history/compare_jobs.py`→`application/history/compare_jobs/` | `definitions.py`；`payload.py`；`materialize.py` 去重 commit 物化；`assemble.py`；`publish.py`；`checkpoint.py`；`failures.py` |

`__init__.py` 只标识包，不保旧 API 转发；注册/组合从 `definitions.py` 引入各步，步骤只依赖 payload/checkpoint/能力 owner，共享 steps 不反向依赖具体作业。同目录私有 helper 可保留，跨目录必须公开。若切分发现必须改变字段/事务/字节或额外公共协调层，停该项报 Owner。

相关工作包的现有回归入口（路径相对各包 `tests/`，移动后跟随新路径；不是新增一轮全量测试）：

| 工作包 | 现有测试与核对依据 |
| --- | --- |
| C3（第 1 批） | RS `test_auth_lifecycle.py`、`test_synchronous_mutation_recovery.py`、`test_create_repository_online_recovery.py`、`test_import_recovery.py`；覆盖 schema 拒启、事务与重启恢复，迁移旧形态用例改为单一基线语义 |
| J2 | BE `test_operation_checkpoint_contracts.py`、`test_operation_job_recovery.py`、`test_submit_recovery.py`、`test_history_compare_jobs.py`；核 generation、取消、terminal、恢复与资源失败映射 |
| J1 | BE `test_preview_job_payload.py`、`test_history_compare_jobs.py`、`test_operation_checkpoint_contracts.py`、`test_job_payload_decoding.py`；逐项比对 descriptor/storage facts 往返与坏文档、canonical 字节和 digest |
| K1 | BE `test_operation_http.py`、`test_preview_read_http.py`、`test_submit_read_http.py`、`test_history_http.py`、`test_bundle_download_http.py`、`test_submit_http.py`、`test_operator_recovery_http.py`、`test_operator_recovery_mapping.py`、`test_http_auth_matrix.py`；逐项核状态/错误、授权拒绝顺序、隐藏对象及恢复 effect |
| G1 | BE `test_bundle_contracts.py`、`test_bundle_assembly.py` 及 `vnext/fixtures/golden/bundle/s1b/snapshot-table-bindings.json`、`test_history_compare_jobs.py`；Preview 三角色及 History ref 向量保持字节/digest 不变 |

K1 实施前从现有 HTTP 测试及各路由 `responses` 声明整理“路由（method/path）、错误码、HTTP 状态码”对照表，在阶段区 `reference/k1-http-errors.md` 保存来源测试/声明与拒绝顺序；两种来源不一致处先核实际行为，不靠声明推定。移动后逐行核对，新增缺失的必要回归；对照表及结果交 K1 独审者作为审核依据。

K1 后仍留 `http`：`multipart_stream.py`、`multipart_upload.py`、`bundle_stream.py` 的流式边界、命令构造、DTO 映射、幂等头解析。授权不能只留在路由调用之前，也不新建通用授权层。

### 第 3 批：门禁与规则

移动完成后集中落地，四条门禁复用 Ruff、既有 `tests/test_architecture.py` / `tests/support/import_rules.py` 及 runner，不加依赖。格式检查已由 J6 接线，本批核收，不重复全量格式化。

| 包 | 接点、规则 | 风险与验证 | 独立审核 |
| --- | --- | --- | --- |
| J4 | 扩展既有 AST import 检查：下划线名字只能在**定义文件所在包目录**内导入；相对/绝对、别名及 `TYPE_CHECKING` 解析到实际定义，不用 re-export 绕过 | D；检查范围仅 BE `src/`，测试不受生产私有导入禁令约束，但 J3 必须更新 12 个测试文件的 28 个私有名字导入路径，不留兼容转发；空基线；最小正例“同目录允许”、反例“跨目录拒绝”验证 checker，扫描失败打印路径/名字/规则 | 实施者＋门禁 |
| K2 | `http/routes/statistics.py` 仓库归属检查移到 新建 `application/statistics_queries.py` 的身份上下文入口，复用现有 `statistics/queries.py` 查询 port；取消调用其他 route 复用授权；同表内组级 `/v1/statistics` 权限检查也由接收身份上下文的用例入口完成，不遗漏 `http/auth.py` helper 的间接授权。`http/routes/history.py` 的 `get_history_compare_route`、`get_history_compare_bundle_route` 直接授权也移入 `application/history/results.py` 接收身份上下文的入口；保留错误码、状态码和拒绝顺序。AST 禁止 `http` 导入 `domain.*.policies`；人工核每个 `/v1` 用例授权入口 | A（既有授权不变）；空基线；`test_statistics_queries.py`、`test_history_http.py`、`test_http_auth_matrix.py`、HTTP statistics、跨 scope/不存在对象/权限失败回归，最小 import checker 正负例。门禁不冒称静态证明每条路由都授权 | 实施者＋门禁，整轮独审点名核 statistics 与 History 两路由的授权实际调用链及拒绝顺序 |
| J5 | `pyproject.toml` 追加 Ruff `C901`（保留现有选中规则），并将 `ruff check src tests` 接入 runner 的 backend 预检查、非零失败；`lint.mccabe.max-complexity=30`；按移动后的代码由 Ruff 重算，逐函数 `# noqa: C901` 加原因，现有约 41 项仅作线索 | D；新函数不得豁免；在现有架构基线中登记具体函数身份，不按易变行号；清单与注释一一匹配，删/消除即从清单移除，新增失败；不得整个文件忽略 C901，不为过门集中重写旧逻辑。用已锁 Ruff 的实际算法，不复用复盘估算法 | 实施者＋门禁 |
| RULE | 准备四条门禁的名称/命令/失败/豁免说明，写阶段总结，由 Owner 转规则会话；不直接改两份规则文件 | D；对照实际输出和 runner 接线，未生效不写成已启用 | 实施者核对 |

J4 跨目录私有导入逐项清零（评审基线共 7 个名字，不按 import 语句计数）：

| 导入方 → 定义 owner | 名字与目标 | 落地步骤 |
| --- | --- | --- |
| `application/history/compare_jobs.py` → `application/preview_jobs.py` | `_snapshot_descriptor_to_document`、`_snapshot_descriptor_from_document` → `capabilities/snapshot_materialization/documents.py` 的无下划线公开原语 | J1 |
| 同上 | `_storage_facts_to_documents`、`_storage_facts_from_documents` → `capabilities/comparison/documents.py` 的无下划线公开原语 | J1 |
| 同上 | `_document_string` → 顶层 `document_fields.py` 的公开 `document_string`，由 codec/作业直接导入，不依赖 application；只搬原字段读取原语，保留错误/类型语义，与 J2 non-empty string helper 不强行合并 | J2 |
| `application/history/compare_jobs.py` → `application/pair_pipeline.py` | `_same_complete_table_identity` → 原 owner 的公开 `same_complete_table_identity`；直接更新消费者 | J4 接线前 |
| `bootstrap/deployment_identity.py` → `deployment_config.py` | `_document` → 原 owner 的公开 `decode_deployment_document`；直接更新消费者 | J4 接线前 |

输入 §4.1 的“J1 至 J3 后全部清零”在此更正：J1 处理四个名字，其余按上表处理；J4 对最终 `src/` 全量扫描为空，不只检查这七项。生产及测试的导入路径随移动更新。

计划中的规则会话交接表（实施后填实际 SHA/测试函数名）：

| 门禁 | 节点内执行命令 | 失败表现 / 豁免 |
| --- | --- | --- |
| 格式 | `vnext/scripts/uv-consume.sh -C vnext/backend run ruff format --check src tests` | 非零、列出待格式化文件；无存量豁免 |
| 私有名字 | `vnext/scripts/uv-consume.sh -C vnext/backend run pytest tests/test_architecture.py -n 0` | 跨目录名字/路径失败；基线空、同目录允许 |
| HTTP policies | 同上 | `http`→`domain.*.policies` 失败；基线空；用例接线仍须审核 |
| 复杂度 | `vnext/scripts/uv-consume.sh -C vnext/backend run ruff check src tests`，加上述架构基线核对 | C901 >30 或新增豁免失败；只允许登记的存量函数，清单只减不增 |

L1/P3/B9 与总结格式直接遵守合入时现行 [AGENTS.md](../../../../../AGENTS.md) 的“新代码的校验与身份”“写测试 / artifact ID”“流程与角色 / 阶段总结写给人看”条文；这些规则已落入 main，不再当作待规则会话制定，也不在此复制。规则会话只接收本轮四门禁的实际生效说明。

### 第 4 批：试点与核对

P1 的删除提交排在 L2 试点候选及其比较、独审之后，单独提交；L2 的字节、digest 和 t1 比较不包含 P1 的改动。

| 包 | 接点、产出 | 风险与验证 | 独立审核 |
| --- | --- | --- | --- |
| L2 | J1 两处 `documents.py` 合作一个文档试点；`capabilities/composite_signal/contracts.py` 及 JSON、Rust/Arrow/SQL 到该类型的实际适配入口作进程内试点 | A/B；用已锁 Pydantic strict/extra forbid 定义文档模型，输出仍走原 canonical encoder，不直接换 JSON 序列化器；保留 list/tuple、null/缺省、枚举/错误映射。内部只在查清未经检查的入口后删类型复检，跨字段校验保留、逐行不用 Pydantic。比较同输入 golden/digest、恢复和坏文档边界；真实 t1 前后分段观测见 §4 | 一次，覆盖两类试点 |
| P1 | 对当前 BE digest 字段重新扫描，逐项追踪 BE/RS/Rust/序列化、`frontend/src` 只读消费者；记录用途及引用，不能把“没有比较表达式”当无消费者 | D 盘点，实际删除可能 A；原 112/94/18 是线索。清单按缓存键、别的 digest 的输入、对外暴露、只写不读分类并附引用依据，标出待删字段；删除前交 Owner 看一次。公开 OpenAPI DTO 中即使前端不读也须单列，由 Owner 决定删否。按 2026-11-13 R1 删除只写不读字段并同步 Contract/golden，全部删除在最终 V 前落地，t4/N2/最终六包基于删除后的文档形态 | 盘点由实施者核对；涉及持久文档或摘要输入的删除由最终 V 前的整轮 Sol 独审逐字段覆盖 Contract、golden、恢复及摘要消费者；公开 DTO 删除另核 Owner 决定与 schema 差异 |
| P2 | 正式一页 digest 说明，建议 `docs/backend-vnext/refactoring/formal/guides/digest-map.md`；以六类组织约 55 种，每种四列：覆盖内容、计算者、核对者、防什么 | D；从 P1 实际引用归纳，未找到核对者明确写未知/待决定，不猜测。无别名统一或合并；完全同输入/整类无核对者才报重开 | 实施者核对 |
| D24 | 真实 t4 最终完整旅程保存 P7-D23 逐尝试摘要，成为整轮回归及未来 Dolt 升级参考；同一真实输入 N2/N1 正式结果/digest 核对 | B；产品 kernel N 与 W/pytest workers 分开，默认 N1 不变；输入/节点/预算依 DC33 一次确认，记录实际配置、结果、失败和差异；不再挂“最迟 S5” | 整轮独审核原件 |
| C4 | `vnext/deploy/README.md` 加 Dolt 升级 runbook，RS README 引用；不新增程序或本轮升级 Dolt | D；逐项查实际版本源、身份拒启和缓存入口；升级流程：RS Dockerfile、dependency-base Dockerfile、RS settings 三处同步→DC67 预填充→stage gate `--fresh` 六包→真实 t4 与 D24 比结果/digest及 RS 导入耗时/内存 | 实施者核对 |

L2 一页报告逐条给结论：①字节/digest 不变且无特例补丁；②**所涉样板**净减≥40%（两类分列、附合计，不能把移动/测试删除计入）；③真实 t1 分阶段耗时不变差；④单 capability 的实际工时/提交/审核修复量。任何一条无证据即未达标。试点失败则恢复其替换前实现（不保双路径），记录原因；存量只按改字段触发，是否 L5 等 Owner。不得降低判据以保住试点。

## 3. 提交与独立审核

计划已获 2026-11-13 独立评审及复审意见，复审要求已补齐；按复审结论改完即通过，无需再评一轮，本设计者自查不充独审。实施沿当前三角色惯例：持续协调 Terra/high；按内聚工作包使用新的 Terra/high 实施上下文；独审用 Sol/xhigh 新上下文（复杂判断可 max）、不自审、不递归扩队、无专职测试/监视角色。这里只安排下一协调会话，不在文档会话启动角色或产品工作；不改 S2b 分工。阶段验收时按现行 AGENTS“代码独审与验收核对”集中启用一次 Luna 验收核对，核交付清单与原始证据完整性，逐项区分通过/失败/未知；不改代码/标准、不自行重跑测试、不常驻。语义、安全、一致性及证据矛盾交独审者或设计负责人；协调者分别核收代码独审、门禁和验收核对，复用阶段区记录。

实施在 main；必要并行只开短期分支并及时合回。J6 格式化本身单独提交，门禁接线另提交；C2/C3 各有可独立审核的候选，J3/K1/L2 同理，其余相邻小修改可合并，不为每次日志更新提交。审核在只读 detached worktree，以“上一个已审边界..候选 SHA”界定，J3 补核 J1/J2；C2/C3 的相互调用也要在第二次审核核齐。阶段末新独审完整覆盖四批，普通修复由原审核增量。整轮独审另明确覆盖 K2 History/statistics 授权及 P1 持久文档/摘要输入删除。发现超出已批准例外范围的行为变化先交 Owner。

过程材料只入 `/home/dev/gdds-stage-exchange/p7-backend-remediation/`：`log.md`（协调者串行追加）、`reviews/`、`gate/`、`reference/`、`pilot-report.md`、`digest-audit.md`、`prompts/`。正式计划/设计/Contract/决议入库；退出只另入库一页 `p7-backend-remediation-summary.md`，不堆过程报告。

## 4. 验证执行点

本次文档任务**不运行下列命令或任何测试**。实施时按现行 AGENTS、[测试规程](../../../testing-conventions.md)、[stage gate 用法](../../../../../scripts/README.md)执行，先核专用节点 SSH、有效占用、离线缓存、clean 已提交 worktree；日志在树外。开发机只编排，不跑测试/ruff/mypy。04 门禁占用由脚本获取；其他节点按其实际用途/资源池选择，不复制旧阶段特殊授权。

| 时点 | 验证与闭包责任 |
| --- | --- |
| 各包 | 受影响 Ruff/mypy、上表 focused/Contract/恢复；不按小包跑完整 runner。删除测试必须证明只属于被删机制，其余不变量继续有 owner |
| 第 1 批末 | `python3 scripts/run-stage-gate.py <完整SHA> --packages backend,repository_service --purpose stage --session p7-backend-remediation-b1`；C1–C3 触发 RS 产品重建和 backend/RS 容器门禁；依赖基础镜像输入不变则复用 |
| 第 2 批末 | 同命令 `--packages backend`、session `...-b2`；核公开 OpenAPI 差异仅含已批准 G2；字节/digest/golden 无变化 |
| 第 3 批末 | 同命令 `--packages backend`、session `...-b3`；J5 改 backend `pyproject.toml` 会改变 dependency-base 输入，须按下段先重建/预填充；四门禁须实际进入 runner/pytest 检查链；公开 `/openapi.json` 与 G2 提交的同条件输出逐字节相同（含 K2 路由调整），保存输出与比较结果；若 checker/runner 涉其他包则扩大实际受影响包 |
| 第 4 批末/最终 V | 先完成 P1 清单交 Owner、获准删除及 Contract/golden 更新，再完成整轮独审与修复；最终 V 的公开 `/openapi.json` 与 G2 提交逐字节核对，只有 P1 获准公开字段删除可例外，差异逐项对应批准项并留原件；在唯一最终 V 上触发六包 `--purpose stage`（省略 packages），按实际闭包运行或沿用；有闭包/镜像变化实跑，无变化不重做。真实 t4、N2核对与最终 V 绑定，不用旧 S2b 特许替代 |
| 总结 H | 文档提交后再由 stage gate 绑定 H；满足同节点同固定树/源 manifest/镜像等价才 carried。未过门禁/独审或还有未决定的范围冲突不打 exit tag |

J5 即使只改 Ruff 配置，也触及 backend `pyproject.toml` 的完整依赖基镜像输入摘要；按现行规则在 CT201 clean 提交运行 `vnext/scripts/build-backend-dependency-base.sh --save <归档>`，在本批配置收敛后集中一次，通过 LAN 预填充实际 focused/04 节点并记录来源、完整输入摘要、tag/config digest/全部 DiffID、归档 SHA 与时间。不能以“锁未变”跳过；仍无新依赖，不因此重建未改变输入的 RS 基镜像。

stage gate 在有 `vnext/` 增量时可能保守重建容器，不绕过脚本裁剪；同次 runner 已过 Compose 不另重跑。只有未来 Dolt 升级、S5、发布/production 强制 `--fresh`/对应 purpose 六包；本轮每批不强制 fresh 六包。runner 非零先处理失败，停止依赖验收，不继续 carried。

L2 的 t1 比较在第 3 批合格提交和试点候选之间，同节点、同输入、相同 N/M/W/缓存模式，记录八阶段耗时和峰值；优先使用已有同条件证据。没有可比来源则准备一次基线和一次试点运行，不默许大矩阵。计时用途按独占规则，预先约定如何区分噪声与回归；不据单次波动宣称改善，无法判定如实写未证实。具体清单（含 t1、t4、N2 的输入/节点/预算与比较口径）在启动时按 DC33 一次给 Owner 确认。

最省运行的建议是最终 t4 的 N1 作为参考、再以相同 t4 跑 N2，一次对比同时关闭 D24；只有资源与输入范围被确认后执行，否则 Owner 可确定更小真实档作 N2 对照，但 t4 本轮责任不取消。正式结果/内容 digest 要逐项一致，运行 ID/耗时等本来可变的观测单列，不把非确定元数据掺入比较。原件包含 hostname、起止 HEAD/UTC、exit、输入/配置/摘要/结果 SHA、缓存来源与镜像身份；不记录凭据。

### 4.1 真实数据运行卡与停止边界

阶段区已准备 `reference/real-data-run-card.md`；协调者在启动准备中核实并补全该卡，在相关旅程前一次交 Owner 确认 DC33；本节给出固定建议，不能把未填写的来源身份写成已核实。该局部确认不阻塞前三批。

| 运行 | 建议输入/节点/次数 | 固定比较与配置 |
| --- | --- | --- |
| L2 基线/试点 | `rd-t1-a-v1/v2`，05；第 3 批合格提交一次、L2 候选一次；已有完全同条件来源可替代基线 | 同输入、同节点、同存储与缓存模式，单 worker/单 active，N1、E32/reserve8/M24 GiB；八阶段耗时、峰值、正式结果及字节/digest逐项比较。P1 删除不能混入 |
| D24 最终参考 | `rd-t4-d-v1/v2`，CT108；最终 V（P1 删除后）完整 N1 一次 | 同上述资源档，完整业务旅程与 D23 逐尝试摘要；不是旧 `t4-w1-w2` 专项范围 |
| D24 一致性 | 同一 t4、同节点、同 V，N2 一次，复用上一行 N1 参考 | 只将 kernel N 从 1 改为 2，W/active、E/reserve/M 不变；不把 N2 当双 worker，不增加内存预算，不据此更改生产默认值；逐项正式结果/digest一致，运行 ID/耗时等非确定观测另列 |

运行卡必须填：输入包实际路径、manifest 与逐文件摘要及来源；基线/候选 SHA；实际节点和配置；明确冷暖条件、独立运行目录、现有 driver 的完整命令；各阶段预算的既有来源；阶段/结果/digest 比较键、允许变化的元数据和输出路径。不得复制前端 `source-dirs` 目录当作后端打包输入。运行前核节点资源、离线缓存与真实输入，旧现场快照不充就绪证据。计时组独占，同一组不跨节点；不新增预热/重复矩阵，不能解释的差异记未知，L2 未证实不变差则按未达标处置，不临时放宽阈值。

**driver 接线先核实。** 当前 `benchmarks/real_dump_journey.py` 有 `--kernel-threads`、`--kernel-memory-budget-bytes`，但部分容器资源 guard 固定 N1，`t4-w1-w2` 明确拒绝 N2；CLI 能接受参数不证明容器实际采用 N2。D24 执行前由实施者追踪 `--scope full` 到部署配置、worker runtime/profile 和 cgroup，证明 N1/N2 的实际设置与记录一致。若现有入口不足，仅在既有 driver/harness 增加完成 D24 所需的显式参数传递与对应检查，不改生产默认、不删旧 scope 的 N1 守卫；该增量先交 Sol 独审并在专用节点 focused/相关容器验证后进入最终 V。涉及产品行为或预算变化则回 Owner，不能为了开跑去掉资源检查。未核实不启动长旅程、不输出猜测的可执行命令。

资源或耗时使 t4 N2 不可行时，只交 Owner 决定是否改用较小真实档作 N2/N1 对照；t4 N1 责任保留。输入身份、实际命令和资源档确认后才执行这些旅程，不借用 S2b 临时授权。

## 5. 后续阶段设计入口

[整顿后的设计输入](p7-post-remediation-design-inputs.md)是 S3、S4a、回灌演练、S4b、S5 的 kickoff 约束；不在本轮实现。总执行计划和总体设计同步链接，S2b 原计划/授权保持。

## 6. 退出与转交

四批完成、重点与整轮独审核收、四门禁实生效、L2/P1/P2/D24/C4 有真实产出，P1 清单已交 Owner 且删除已在最终 V 之前落地、阶段验收核对完成后才退出。删旧路径不残留 fallback/死 import；Contract 和操作说明与最终代码一致。规则会话未接收前不宣称全局规则文件已更新。

一页总结写人可读的完成/净删与移动量/偏差/未测限制/遗留/证据索引，并将以下两个 SHA 分开列为由 Owner 转交前端的事项（两者可能不是同一提交）：① `p7-backend-remediation-exit` 指向的提交在 `main` 上的 SHA，用于前端 journeys；② 本轮公开 schema 不再变化的提交 SHA（前端刷新 `frontend/openapi.json` 并重新生成类型）；若 G2 后有 P1 获准公开字段删除，给出后一个 SHA 及获准差异，不能仅转交 G2 SHA；四门禁交接表及生效提交（规则会话）；试点四判据报告和 L5 决定；P1 清单已交 Owner 且获准删除在最终 V 前落地的结论与引用。G2 合入 main 时立即经 Owner 通知前端并说明窗口：直到前端快照提交合入 main，真实 backend 入口因 `frontend/openapi.json` 与运行时 `/openapi.json` 不一致以 exit 2 停止，浏览器用例不会运行；后续获准 schema 变化也经 Owner 更新转交 SHA。此通知不等阶段退出。不与前端 agent 直接通信，不把前端格式化作为后端退出前置。收尾只释放本会话已完成用途的资源，保留仍引用的证据与 carried 树，不 force 回收。

Owner 2026-11-13 决定：前端 journeys 完整集至少有一次跑在包含上述后端整顿退出提交的后端上，由前端会话在 04 执行；后端不运行前端入口、不改 `frontend/`。前端的 04 退出证据已满足这一点则不另跑，否则在两端都合入 `main` 后补跑。这次旅程不阻塞打 `p7-backend-remediation-exit`，但 S3 实施开始之前必须有结果。失败时停止依赖推进，由 Owner 转来失败用例及观察到的错误码、状态码；属于后端整顿改动引起的，按“发现必须改行为即停”处理，修复后重新走相应独审和门禁。

### 跨端交接（Owner 2026-11-13 开工补充）

前后端由不能直接通信的不同 agent 执行。只写本端阶段区并向 Owner 给出可直接转发的文字；不调用消息工具联系另一端、不写另一端 log/prompts、不把共享文件出现或 Git 分支前进当作对方已收到通知。接收方在本端 log 记录 Owner 原文、来源提交及处理结果，再由 Owner 回传。没有收到依赖输入时只暂停相关步骤，其余工作继续。

| 交接 | 发出时点与必填内容 | 接收方动作与回执 |
| --- | --- | --- |
| BE-SCHEMA-NOTICE | 后端 G2 进入 main 时立即发：完整提交、main HEAD、vnext tree、允许的差异、公开 schema 尚可能变化与否、OpenAPI mismatch 窗口 | 前端记录；未取得最终 schema 前，继续固定 B 的独立整改和 mock，不盲目合入后端新树或绕过 OpenAPI 检查 |
| BE-SCHEMA-FINAL | 后端确认 schema 不再变化时发 Sb、main HEAD、vnext tree、schema 原件路径/摘要和逐项差异；若有 P1 公开 DTO 删除，附 Owner 逐字段决定和消费者核对结论 | 前端核 Sb 在 main，按 G2 同步快照与类型；差异必须全部匹配交接清单。若影响实际前端消费者或需改行为，停相关项交 Owner，不能借生成类型更新隐式修改行为 |
| BE-EXIT | 后端 exit 后发 Sx（tag 指向提交）、tag、main HEAD、vnext tree、总结/证据索引，明确 Sb 是否仍有效 | 前端核 Sx 祖先关系，安排 §9.1 的 04 完整 journeys；已有合格运行则回执引用，不重复运行 |
| FE-SCHEMA-ACK / FE-JOURNEYS | 前端发快照提交、合入 main 的提交、消费的 Sb/Sx、运行候选/节点/原件、结果与未完成项；新 npm 缓存来源提交/归档摘要/节点路径单列 | Owner 转后端登记。S3 实施前必须核收包含 Sx 的完整 journeys 通过结果；失败或未知不算满足 |
| FAILURE / REVISED | 任一端失败或改变已交接的 schema/候选，发旧/新 SHA、失效范围、失败用例、观察到的错误码/状态码和原件；不放凭据 | Owner 决定归属并转发；修复后原审核定向复审、重做受影响验证，再回执。旧回执保留但明确失效 |

Sb 与 Sx 是两个不同用途的提交，不能互相代替。FE 04 证据及 BE 04 stage gate 共享节点，按现场有效占用排队，不抢占；只有实际冲突才经 Owner 协调。前端保持独立 worktree/分支，后端在 main 推进；前端准备合入时经 Owner 转交候选、写入范围和 main 接入时点，不让两个会话同时修改同一 worktree。

## 7. 冲突记录与 Owner 决定（2026-11-13）

| 项 | 已核事实 / 冲突 | 决定与执行条件 |
| --- | --- | --- |
| R1：P1 删除 | 原冲突：输入 §5.2 要删只写不读 digest 并改 Contract/golden；§1 仅豁免 §2 删除，冻结表述过宽 | **Owner 2026-11-13 已批准**按复盘 §17.3 逐项核用途，删除只写不读字段并改 Contract/golden，撤销默认保留。清单先交 Owner，列分类/依据/待删项；公开 DTO 字段单列由 Owner 决定。删除在最终 V 前完成，t4/N2/最终六包在删除后形态运行；持久文档/摘要输入变更由整轮独审覆盖 |
| R2：G2 schema | 原冲突：输入 §3.5 要内部路由从公开 OpenAPI 消失，但总冻结含接口/文档字节；现有冻结集合混合公开和内部路径 | **Owner 2026-11-13 已批准**移除公开 OpenAPI 中 `/internal/v1` 路径及仅被这些路径引用的 schema 组件；保留仍被公开路径引用的组件。运行时内部路由、认证/调用方、`/v1` 路径/请求/响应 schema、业务文档/digest/golden 不变；公开 schema 和运行时路由分别冻结 |
| R3：声明“已删除” | 输入 §8 要总纲写“代码已删除”，当前 main 仍有 P2-R1 七模块与 `repository-probe`；本次仅文档，不允许代码实施 | 本次正式记“删除决定已生效，C1 待实施”；C1 删除提交后更新为已删除并写 SHA。这样保留方向又不伪造进度，无需另改删除范围 |

已采用的工程简化：G1 在 Preview 构造处限定三角色，避免破坏 History 的 `ref_id`；J2 跨目录函数公开化，避免与 J4 冲突；t4/N2 尽量共用一份 N1 参考。C3 单一基线与 ADR 兼容条款的冲突已经由 Owner 明确要求修订，非新增待决；不重新询问。试点未达标时如实撤回替换并报告，不因此规划 L5。
