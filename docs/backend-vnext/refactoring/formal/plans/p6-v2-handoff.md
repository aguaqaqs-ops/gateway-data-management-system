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

Owning 正文目标：`contracts/business-lifecycle-and-state.md`（6.0.0）、`plans/p5-5d-archive-design.md`（规则、digest v2、audit、Start/关闭与统一处置）、`plans/p5-5c-review-design.md`（closedness/Review摘要）、`plans/p5-5e-history-compare-design.md`（统一处置与两读取入口/DTO）；Snapshot Materialization、Canonical Storage、Preview、Submit Contract 本节无新格式/算法改动（none），V1既定事实/schema/checkpoint版本保留。路径均相对本页的上级 formal 目录。

## 6. 当前固定交付

本节最终产品/容器候选为 **`f8fb796f020ab47725359c176fc0e53bfb68aae6`**，`vnext` tree=`3860ed86194e4eafea9cfd408e7e7b5096b24bbb`，backend `src` tree=`3ce20974cca67dd5a9d0aa1fe40763b78b752af5`，Rust tree仍=`e6ac6e3b05cbd923affc5773106e51ab9cc9c2ec`。`3cce25c72a..f8fb796f02`只修测试fixture、导出OpenAPI及正文，没有改变产品src；随后协调/审核/handoff仅docs，不以docs提交冒充新的产品运行。清单实际落点均已完成；最后GO由同一独审的[p6-v2-review](p6-v2-review.md)签署，不在此自行办理联合退出。

实际新增纯规则在`application/archive/business_validation.py`，确认/异常/Start仍原owner；最小成功记录校验集中`application/archive/integrity.py`，手工关闭为`application/archive/manual_close.py`。来源固定点/未知分量、时间质量/last非max/倒退及baseline不可比较全部从V1持久facts派生，合法跨ruleset边保持；来源接受后仍UNEXPLAINED。新异常由服务端完整分组重算和冻结，kind/code/代表target不允许caller删减members。audit.subject公开对象即JCS preimage：issue-specific closed details union保留原字段/null形状，不补会改变digest的无关null；HTTP owner实际重算公开subject摘要。

唯一`submission_disposition_records`直接替换原归档专用表，`SubmissionDisposition`仍归domain/archive owner，不增反向Domain依赖。CLOSE只读取授权目标/current Head，不调用候选图、active Attempt列表或Repository；旧baseline、201候选、非目标坏facts仍可关闭，精确释放/version+1且OPEN/generation、APPROVE和历史保留。same key跨当前授权actor回放首actor/time/reason；原关闭事实/请求绑定先于普通冲突校验。Start原成功返回Plan冻结commit，校原sequence确认/处置subject、不可变候选及Plan/Result/Node/统一处置closure，不重判当前Head/新候选/occupancy/latest。safe整数及递增上界、1/1601 refs、262144-byte body均已接HTTP/application/fingerprint/replay。

四份owning正文已同步，Business Lifecycle为6.0.0；新增golden仅`vnext/fixtures/golden/archive/v2/identities.json`（candidate、close-request、business-anomaly v2），原V1 facts及既有canonical/comparison/bundle等golden不改。没有依赖/lock/Rust改动，没有旧字段别名、旧表双读、migration或Python SQL重提取路径。

`benchmarks/real_dump_journey.py::_archive`已按全部新kind逐项消费最新sequence/status及限定action；显式`GATEWAY_REAL_DUMP_ARCHIVE_REASONS_JSON`为`{subject_digest或issue_code:非空reason}`，缺对应reason即失败，不自动无理由放行。新增consumer小向量验证缺理由拒绝及latest引用。当前main工具的FULL上传模式入口与完整tar仍待D联合收口；`--scope full`并非FULL输入模式，不能以本节工具测试声称已覆盖。冻结V_ref脚本/镜像/输入/卷未改。

## 7. 06验证与保留失败

全部测试、编译依赖同步和静态检查仅在 **06 / `gw-dms-06`**，clean detached WT **`/home/dev/gdds-test-tmp/wt/p6-v2`**。09:59:49Z现场核空闲后原子取标志；目录birth实核为 **10:00:14.111Z**（owner文件会话开始标识写10:00:00Z，不把它或V1旧释放时间当取得证据）。来源经开发机`heavy-dev-01`→06 LAN Git bundle/fetch；legacy链接到节点主参考目录。开发机只编辑/读文件和生成静态JSON golden，没有运行产品测试/编译/lint。

证据根 **`/home/dev/gdds-test-tmp/artifacts/p6-v2/`**，完整本地副本 **`/home/dev/gdds-v2-evidence/`**。`evidence-index.json`列37份runs原日志的hostname、起止UTC/HEAD、argv、exit及SHA，并列13个sidecar/script/bundle；SHA256 **`cc505fe5a1a1776191a8ab599b7433784460a47f004fab2398e3459b9c611efb`**。同一独审已逐项独立重算全部摘要并读取实际脚本/日志，不以索引替代原结果。

| 实际运行 | 结果 / UTC | 日志SHA256 |
| --- | --- | --- |
| 7878主体，原12 owner文件（含200 FULL/399真实application接受和Start） | **419 passed**；10:13:33–10:16:49Z，exit0 | `focused-second-7878e41ad3.log`：`417b1c34a86c82f288e4ba84a682b613bd617108eaf53b10692d10ab24aa1ed3` |
| 3c主体，13文件加入benchmark consumer及F5/F6等增量 | **497 passed / 2 failed**；10:23:41–10:26:55Z，exit1，原因与补验见下 | `focused-third-3cce25c72a.log`：`c53881907f0a3086aff8c46ae62efe2769331b99bd1502e13cc5c4d8d1a53dbe` |
| 996仅两个受影响owner增量主体 | **71 passed**；10:28:18–10:28:23Z，exit0 | `focused-final-996f0935d5.log`：`9b4aa071bee9b2c64c697e895a84c1c6b27f9976d3bb41fc07083cdcac6a6c72` |
| f8同13文件剩余serial独立批次 | **2 passed / 499 deselected**；10:30:29–10:30:31Z，exit0；非空批 | `focused-serial-f8fb796f02.log`：`39cfbcac84b30f7e914d00242b84dc7188ea236b1dd79e695e28164a58816e3a` |
| f8 backend ruff/mypy | 均exit0，mypy **509 source files**；10:30:29Z | ruff：`ca47992d64c1fb547b0fa6001d79a6a1992da94438b3bbadfad059fce79c1feb`；mypy：`207f0d9b931efe6506cde21e639c8e748f957e7b50653c3794501103a7d562af` |
| f8最小生产Compose | **1 passed**；10:34:57–10:35:37Z，exit0 | `compose-business-f8fb796f02.log`：`4a6c36dfa2d710e126b849f2284eba60b578034a810d3e3f05537544d7b2bc0b` |
| f8安装扩展输入核验 | expected=installed=e6ac…，10:37:58Z，exit0 | `extension-build-input-f8fb796f02.log`：`77c07547df3fe624f6a4c5dc3beb21816e3479ea373aa77ffedd76dcb76f2114` |
| f8现场清理/释放 | 10:39:24Z，exit0 | `node-release-f8fb796f02.log`：`a93667718f9f49c727fc7dde4186a3d5af65398989786f6fb9f4b812243eccbb` |

主体统一`-m '(not serial) or parallel_safe' -n4`，serial统一`-m 'serial and not parallel_safe' -n0`。五包ruff/mypy均实际通过：四个未改源码包在7878的`{ruff,mypy}-{shared_kernel,repository_contracts,repository_client,repository_service}-7878e41ad3.log`全部exit0；后续仅backend/fixture/golden/文档改动，backend在3c、996及f8重新通过。日志完整摘要在索引，不把这种focused源码连续性称为权威包carried。3c失败整跑不称通过；497个实际通过node、996原owner两处修正补验及f8同选serial共同关闭已选范围的失败，不重复已通过的200/399向量。

35c首次backend sync通过受控wrapper显式offline并`--reinstall-package gateway-compute-python`，79s exit0；`sync-backend-35c4a20456.log` SHA=`7769fce6203d865b54bcc5a4b11920e22ff2b39de8cc7d20996aa95a495e3be9`。3c/f8均实际核扩展e6ac；本节Rust tree未变，不重跑Rust全集/性能。`toolchain-identity-f8fb796f02.log`实际核rustc/cargo/rustfmt/clippy-driver同1.97工具链，PATH以/home/dev/.cargo/bin开头，RUSTUP_TOOLCHAIN/RUSTUP_HOME/CARGO_HOME不设；TMPDIR=/home/dev/gdds-test-tmp，Cargo target在WT外，jobs4与pytest workers4独立于产品kernel设置。UV_OFFLINE=1、CARGO_NET_OFFLINE=true，proxy清除，无测试CT公网或转发代理。

失败不隐藏：35c首轮374pass/8fail与ruff3/mypy3为validator文字、旧合成baseline/INITIAL facts、schema inventory和新增typing；5af新增Literal alias漏定义被ruff拒绝，补齐后通过。7878静态1个unused import/13个mypy错误均为本节新helper/测试变量及注解，3c起全部修正。3c两失败分别为benchmark Mock成功响应漏既有必需baseline_node_id，以及pending/Start竞争APPROVE先胜时旧fixture把实际INITIAL node的facts标为非INITIAL，产品正确报完整性失败；996补真实响应字段及race前合法fixture事实，**没有放宽生产校验、异常集合或marker**。原日志及SHA全部保留。

一次自身checkout使用linked WT不可见FETCH_HEAD，在产品运行/WT写入前exit128；保留`checkout-operation-error.log` SHA=`7deea0d7410bae6a589b529b51954b1e10994a134da8c3f9f058dc63232e0cb5`，按DC68改明确5af SHA仅一次成功。所有后续checkout均用显式commit；没有缓存缺失、身份不符或不明重试。

## 8. 当前容器、OpenAPI、缓存与释放

本节改HTTP接线/持久事实/实际harness，触发当前候选最小容器重建。f8保留Compose build，由06本机offline构建backend/worker，`GATEWAY_BACKEND_USE_PRELOADED_DEPENDENCIES=1`、dependency-base=`gateway-backend-deps:lock-d054366c02fa`、`GATEWAY_DOCKER_BUILD_NETWORK=none`；prebuilt未设。RS/客户端沿既有预置依赖模式，RS新tag=`gateway-repository-service:v2-f8fb796f02`；`dependency-input-f8fb796f02.log`实际重算完整输入仍d054366c…，`repository-build-f8fb796f02.log` exit0。最小nodeid：`tests/test_archive_compose_e2e.py::test_compose_business_rejection_manual_close_and_fresh_upload_archive`，证明真实Rust Preview→Submit/APPROVE→异常拒绝→CLOSE保留历史/不动Head与Repository/释放→新上传补齐saved_time→新Submission/APPROVE→Archive/Result读取。没有把fake reader、自然t1或旧镜像冒充该证据。

`archive-business-provenance-f8fb796f02.json` SHA=`4c7e6a26c3d7edcc990de96341699cd43fb4ca017f3abb3f375c70aeb1d0808c`；`image-identities-f8fb796f02.json` SHA=`d848e614bad84661db11695cd85cb523ee5847c4e09b66ca12c641d01ff5e7bf`。后者从docker save真实config bytes计算config digest，并与inspect逐项核全部RootFS DiffID，完整列表在JSON；不以本机manifest/inspect ID充当跨节点config identity。运行中三个镜像本机ID与fresh build及provenance已核一致。

| 镜像 | config digest | 全部DiffID数量（完整列表见上述JSON） |
| --- | --- | --- |
| backend | `sha256:99188ad41cef18addc3e6760b45b7fd144a0e0f7fc6e51f0de137e7ac0bfc2b1` | 13 |
| worker | `sha256:7485e3f252d6cfd6ea4371a7f263913cdce2e392b8535e89369ed14dc312c028` | 13 |
| RS v2-f8 | `sha256:13292c3de726f47e85e8fa649a9ef65a1251a13aa8ba3755f6cb23cd9abadd5c` | 28 |
| backend dependency-base d054 | `sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a` | 19 |
| RS dependency-base 6dc | `sha256:98d0801b1140a903ff72988a2dba5e3f4819b86103bb8cb6e5dbdf7302ad9ec9` | 16 |
| client e2e base | `sha256:515069721c40303f942d050f0bb072aead44b63209823c890beeab494f8e2218` | 9 |

RS revision=f8，未变build-input revision=`a6876d560050285321fd9f62942d590a03f35d64`、source-tree=`sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2`。backend/worker无source label，以clean f8 fresh build、运行镜像等式与provenance绑定。缓存全部06既有local预填uv/Rust/Docker；无新依赖/锁/base制品传输。d054历史CT201来源提交132fc621d5711ae39ac8f1dc66f4349b2f6fe428、archive SHA3fd859201de06757c8ce5af6dd4ad6e26d99b7439bc2edabb59035b5dd0c9ce6及预填时点沿[06 readiness](p6-node-06-07-readiness.md)与[V1 handoff §5](p6-v1-handoff.md#5-容器缓存与清理)，本轮实核config/全DiffID，不伪造新预填时间。所需制品全部命中local，不依赖未核LAN端点。

实际生产OpenAPI来自同一Compose的`GET /openapi.json`，由上述pytest nodeid写出 **`/home/dev/gdds-test-tmp/artifacts/p6-v2/openapi-f8fb796f02.json`**，SHA256 **`e937a38e8073abebb406138e9be2ca2bd61eb25ac8fda9d9adabee56fd2abda1`**。可转发本地副本 **`/home/dev/gdds-v2-evidence/openapi-f8fb796f02.json`**，字节/SHA一致；不是另造mock OpenAPI。前端需按实际schema消费1/1601、安全整数、完整来源/时间诊断与接受/撤销、History字段改名、Review/结果的处置source及新closure路由；协调者通过Owner手动转交，本角色未改前端源码/设计，也未宣称FE3完成。

Compose project=`gateway-archive-5d-306130-test_compose_business_rejectio0`正常down -v/remove-orphans；10:39:24Z核本项目容器/卷/网络空、8000无监听、无Dolt/pytest/cargo/rustc/clippy、WT clean及legacy正确后，核本人owner再释放marker。同一独审另只读现场确认。全部本节WT/镜像/成功失败证据和V1/A1资源保留；无后台执行、无节点占用、无待推送动作。

```text
Reviewed product/container HEAD: f8fb796f020ab47725359c176fc0e53bfb68aae6
Container rebuild required: yes，已完成06当前候选fresh最小Compose
Current container result: passed（仅上述实际nodeid，不冒充04联合门禁）
Last verified revision: f8fb796f020ab47725359c176fc0e53bfb68aae6
RS source-tree: sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2
Carried from: none（没有权威runner/package/image carried声明）
Docs-only follow-up: vnext tree不变，不另作产品运行声明
```

## 9. 明确交接与角色收尾

V2产品、Contract、唯一owner增量及06最小生产接线已完成固定候选，F1–F6修复与原始证据交原同角色独审最终核收。04权威六包/其余Compose及05 fresh t1的FULL/MODIFIED_ONLY、完整tar与联合业务范围仍**未在本节执行**，留D后联合最终候选，退出前按DC33由Owner确认；不使用06本节结果冒充正式性能、真实数据全旅程或联合exit。D仍负责完整tar与FULL真实工具入口，FE3仍由前端owner设计/实施并接收Owner转发包。没有触及原基准冻结资源、S3、推送或被引用历史提交。最终handoff仅docs；本角色交同一独审固定提交后停止产品/测试/节点写入，普通收口问题仍按同角色闭环。
