# V2 归档核验与关闭出口交接

2026-11-07。实施起点为 clean main `d0add6bd16`（相对 V1 最终 `5dc01deeb543d4bdc07da02b0e0c6ba1f1472533` 仅协调启动文档）；V1 产品 `c229582a9e72a591cf00a70de526b1b0792c1c18`，vnext tree `954caffe70c00c9268cd026477298a73f8e47976`。本页先于产品写入固定实际字段、DDL、摘要与唯一测试 owner。仅 V2；不推送、不改写被引用提交、不启动 S3，不改 frontend、前端文档、AGENTS、testing-conventions 或冻结基准资源。

## 1. 类型、字段和权威边界

V1 `domain/configuration_facts.py` 的 `ConfigurationFacts` / `ConfigurationSideFacts` / `CanonicalContentIdentity` / `ConfigurationGeneratedTime` 为唯一事实输入；版本与提取规则不改。完整内容身份的四字段全部参与来源节点相等；合法 A→B ruleset 边可达，FULL 同 digest/不同 ruleset 不合并。baseline 从当前 BaselineNode.source_submission_id 对应 durable Submission.modified 读取并校 scope/node/commit/facts，INITIAL 明确无来源；不读 SQL/Preview TTL，不调 Repository。

新增 `application/archive/business_validation.py`，纯函数 owner：`ArchiveBusinessCandidate{submission_id,candidate_digest,configuration_facts}`、`ArchiveBusinessIssue{subject_kind,issue_code,affected_submission_ids,side,relations,details}`、`ArchiveBusinessValidation{rule_id,baseline_facts_digest,source_diagnostics,time_comparisons,issues}`。规则固定 `gateway-vnext/archive-business-validation/v1`。来源固定点＋未知弱连通分量，稳定排序完整 identities/edges/affected members；时间只用 canonical UTC 精确 instant，质量缺失/INVALID 互斥、LAST_NOT_MAX 单列，modified 两个倒退 relations 合一、initial 另项，全局 BASELINE_TIME_UNAVAILABLE 单项；空 baseline NOT_APPLICABLE，MO initial BASELINE_REUSED 不重复上传侧质量。

`ArchiveCandidateSnapshot` 增加完整 business validation 输入/派生结果，candidate digest 增必需 `configuration_facts_digest`。`ArchivePreviewAnomaly` 增 `affected_submission_ids,side,relations,details,detected_status,resolution_status,latest_sequence,accepted_by,accepted_at,reason`；原 sibling/identity 同 DTO。subject 新枚举 `CONFIGURATION_SOURCE`、`CONFIGURATION_TIME_QUALITY`、`CONFIGURATION_TIME_ORDER`；接受 action 对应 `ACKNOWLEDGE_SOURCE_EXCEPTION`、`ACKNOWLEDGE_TIME_QUALITY`、`ACKNOWLEDGE_TIME_ORDER`，仍有 REVOKE，原两种 action 保留。issue code 限已审类别，不接受 caller 自由 issue；未知来源保持 UNEXPLAINED，接受只改变 resolution。preview 增 `business_validation` 结构化诊断。

`ArchiveAnomalyResolutionEvent` 增必需 `subject_payload_json`，存服务端同事务派生完整 anomaly subject，包含完整组/边/事实与规则，caller 不提供 affected 列表。原 target_submission_id/candidate_digest 保留为稳定代表项；group 使用 UTF-8 顺序首个 member，完整成员只能由服务端重算。audit append fingerprint 仍 actor-bound。Plan 的 `frozen_input_json` 版本为 `backend-vnext/archive-frozen-input/v2`，增加 business validation、candidate facts digests、完整 anomaly subjects及 exact 接受引用；Result 读取公开这些已冻结诊断，不重判历史为 PASS。

直接将 `domain/archive/models.py::ArchiveDispositionKind/ArchiveDisposition` 推广为 `SubmissionDispositionKind/SubmissionDisposition`，仍由既有 domain/archive owner 持有，不建立反向 Domain import 或第二闭包权威。新增 `SubmissionDispositionSourceKind=ARCHIVE|MANUAL_CLOSE`、`ManualSubmissionClosure`。统一 record 含 submission_id、disposition、source_kind、result_id（manual null）；manual closure 冻结 repository/device/project、actor/time/reason/key/fingerprint、expected_review_version、expected 当前 baseline node/head version、workspace ID/generation/upload/preview/关闭前 optimistic_version、configuration_facts_digest。ARCHIVE 来源 actor/time继续沿真实 Result/Plan，不另保存可漂移副本。

## 2. 唯一基线 DDL 与读取端口

只改 `infrastructure/control_db/schema.py::CONTROL_DB_SCHEMA_STATEMENTS`；旧 DB schema 不符拒启动，无 migration/default/backfill/双读。

- 删除 `archive_disposition_records`，创建唯一 `submission_disposition_records`：`submission_id TEXT PK`（FK Submission）、`result_id TEXT NULL`（FK ArchiveResult）、`disposition TEXT`、`source_kind TEXT`；`repository_id,gateway_device_external_key,business_project_id TEXT NOT NULL`；manual 列为 `closed_by TEXT,closed_at_us INTEGER,reason TEXT,idempotency_key TEXT,request_fingerprint TEXT,expected_review_version INTEGER,expected_baseline_node_id TEXT,expected_baseline_head_version INTEGER,workspace_id TEXT,workspace_generation INTEGER,upload_revision_id TEXT,preview_result_id TEXT,workspace_version INTEGER,configuration_facts_digest TEXT`，ARCHIVE 全部 manual 列 null；MANUAL_CLOSE 全部非 null、result null且只能 CLOSED_NOT_ARCHIVED。CHECK 固定来源二选一，文本 UTF-8 字节限额沿现有 ID/reason；sequence/version 0..9007199254740991。filtered unique 每 Result 一个 ARCHIVED_BASELINE；filtered unique exact scope＋manual idempotency key；result_id 普通索引。
- `archive_anomaly_resolution_events` 新 `subject_payload_json TEXT NOT NULL`，扩上述 subject/action CHECK，sequence增加 I-JSON 上界；confirmation sequence、Plan old head version同步上界。无新增诊断表或关闭 receipt 表。
- `sqlite_archive.py` 统一装配、get/list/is_closed、按 exact scope 查 manual key并 insert manual；Result children只装配 ARCHIVE 行。`sqlite_submission.py` candidate JOIN与Review closure、`sqlite_history.py`分页及完整snapshot、history_reader全部读新表。
- `ArchiveSubmissionPort` 补与 V1一致的 `get_submission_access_binding`及 scoped `get_submission(workspace_id,repository_id)`；CLOSE先 permission、最小三标量 binding/current exact Workspace scope再 full facts，已授权 decoder 的已知 shape/binding错误仅在 Archive owning seam 转 `ArchiveIntegrityFailure`（503），无全局 catch。

## 3. 摘要与命令版本/preimage

Archive `D(kind,payload)` 统一升 `v2`：`D = 'sha256:' + hex_lower(SHA256(UTF8('gateway-vnext:archive:' + kind + ':v2') + NUL + JCS(payload)))`（只计算一次 SHA256）。原 candidate preimage加 configuration_facts_digest；candidate-set加核验规则及 baseline facts identity（INITIAL null），再含原 exact scope/完整 Head/全候选；selection经 candidate-set绑定完整输入。旧 sibling/identity subject同步绑定 selection；新增 business subject `D('business-anomaly',{selection_subject_digest,rule_id,issue_code,subject_kind,affected candidates/facts,side,relations,details})`，details冻结完整组节点/边与匹配来源/原时间。非诊断 UI 当前接受状态不进 subject，不形成递归。

confirmation/resolution/start-request preimage仍原完整请求字段及 exact scope，refs排序；resolution仍含 actor、kind/code/代表target，服务端重算 subject 完整绑定。CLOSE为 `D('close-request',{command_kind:'CLOSE',repository_id,gateway_device_external_key,business_project_id,submission_id,expected_review_version,expected_baseline_node_id,expected_baseline_head_version,reason})`；key是 exact scope+CLOSE命名空间，actor/time/current mutable状态均不进fingerprint。成功 replay校 durable record与冻结请求身份，保留首actor/time/reason。追加审计与CLOSE命名空间分离。

删除 `ARCHIVE_MAX_AUDIT_REFS`，改 `ARCHIVE_MAX_CONFIRMATION_REFS=1`、`ARCHIVE_MAX_ANOMALY_REFS=8*200+1=1601`；body仍262144 bytes。HTTP/application/fingerprint/replay均验safe整数、拒bool/字符串/float，append increment超界拒。399反例与1601形状预算用小固定向量，不造大数据。

## 4. HTTP、Review、History 与consumer

复用 archive routes；新增 `POST /v1/submissions/{submission_id}/closure`（Idempotency-Key header；固定CLOSE_NOT_ARCHIVED，不提供自由action）。body `expected_review_version,expected_baseline_node_id,expected_baseline_head_version,reason`。仅 archive_submission；当前权限不足403；缺失/跨exact scope目标404且不解其facts；fresh review非APPROVED或已处置409；stale Head409；占用绑定错误409；facts/持久关闭事实损坏503。201 fresh/200 replay，响应 `submission_id,disposition,source_kind,closed_by,closed_at,reason,released_workspace_id,workspace_version`。同短 BEGIN IMMEDIATE 内唯一处置与精确释放；OPEN/generation不变、version+1，不查图/其他Attempt，旧baseline合法占用可关闭。

History `archive_disposition`直接改名 `submission_disposition`（无旧别名），增加 `disposition_source_kind,closure` 摘要；分页/完整snapshot/projection/DTO同步。ReviewFacts增加 `submission_disposition`摘要（source/disposition/result/关闭actor/time/reason），原review projection/events不改；self-only仅自身既定范围。ArchiveResult dispositions同统一类型输出source_kind/result_id，并公开frozen business validation，不能把manual关闭伪装成ArchiveResult。

实际接线文件：`http/schemas/archive.py`、`http/orchestration/archive.py`、`http/routes/archives.py`（closure route可同router归owner）、`http/wiring.py`固定path，Review/History schema/mapper；`test_http_openapi.py`固定结构/paths同步。公开错误沿现有Archive/Review handlers，不建新全局框架。无独立OpenAPI静态文件，运行时app schema为owner。

`benchmarks/real_dump_journey.py::_archive`同步遍历新增issue按kind给逐项明确业务reason，先读取实际sequence/状态，不force/无理由放行。FULL上传模式入口与完整tar在D联合收口，未实现前明确待D；不修改冻结V_ref。前端经Owner手动接收实际DTO/权限/错误、接受/撤销/关闭重提流程；本角色不改其源码/文档。

## 5. Golden、唯一测试owner与验证安排

| 不变量 | 唯一owner |
| --- | --- |
| 完整身份固定点、六组来源图/排列/跨ruleset、弱连通组/关闭桥移除、时间分组/三关系/相等/空baseline/MO与8N+1 | 新 `tests/test_archive_business_validation.py`（纯小型facts，无Dolt） |
| candidate/subject/preimage版本与facts/rules/Head/集合变化 | 既有 `tests/test_archive_queries.py`；新增最小 `vnext/fixtures/golden/archive/v2/identities.json`（由其测试验证，不改原business golden） |
| 接受/撤销/序列/exact组/actor-bound replay/完整subject冻结 | 既有 `tests/test_archive_audit.py` |
| Start全部效果/exact最新引用/399正常反例/rollback/原成功replay；CLOSE唯一事实、精确释放、Head不变、坏记录拒、恢复 | 既有 `tests/test_archive_transactions.py` |
| Start/close、双close语义commit次序 | 既有 `tests/test_archive_concurrency.py`（真实SQLite两连接，不调度平台） |
| 公开permission/404先授权、CLOSE跨actor replay/撤权/不同payload、DTO、安全整数/1601/1602/256KiB | 既有 `tests/test_archive_http.py`；OpenAPI结构只归 `test_http_openapi.py` |
| DDL来源二选一/FK/unique与旧schema拒启动 | 既有 `tests/test_control_db_schema.py` |
| 两来源History分页/完整snapshot及Review独立状态、自读不扩权 | `tests/test_history_projection.py` / `tests/test_history_http.py`（分别projection/HTTP）与 `tests/test_review_http.py`（Review摘要smoke，不复制权限矩阵） |
| 生产wiring异常拒绝→关闭→新上传重提→归档 | 既有 `tests/test_archive_compose_e2e.py`仅一个小型真实旅程；当前候选offline fresh build绑定 |

所有测试/编译/lint仅06，运行前SSH、现场空闲/原子marker、独立clean已提交WT/LAN bundle/legacy、UV_OFFLINE=1/CARGO_NET_OFFLINE=true/TMPDIR和jobs/workers4。pytest显式主体 `-m '(not serial) or parallel_safe' -n4`＋其余serial `-m 'serial and not parallel_safe' -n0`；空批exit5记N/A。五包ruff/mypy必跑；本节不改Rust/依赖，核已安装build input，首次新环境仍强制扩展sync。日志WT外记host/起止UTC和HEAD/exit/SHA，保留本节失败及前节WT/镜像/证据。代码固定先交同一独审并行静审；04权威、05 fresh t1和D/前端留联合候选。

当前 HEAD d0add6bd16；本提交仅清单文档，container rebuild required=no、本提交container gate=not-applicable；最后产品镜像证据为V1 c229（本节不冒充已验证）。V2收敛候选必须06 fresh最小Compose，04联合门禁延期到D后最终候选；无carried声明。

Own​​ing 正文目标：`contracts/business-lifecycle-and-state.md`（6.0.0）、`plans/p5-5d-archive-design.md`（规则、digest v2、audit、Start/关闭与统一处置）、`plans/p5-5c-review-design.md`（closedness/Review摘要）、`plans/p5-5e-history-design.md`（统一处置与两读取入口/DTO）；Snapshot Materialization、Canonical Storage、Preview、Submit Contract 本节无新格式/算法改动（none），V1既定事实/schema/checkpoint版本保留。路径均相对本页的上级 formal 目录。
