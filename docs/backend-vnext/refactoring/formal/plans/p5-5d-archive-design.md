# P5-5D Archive Detailed Design

状态：**ACCEPTED — 2026-09-20 独立 docs review 通过；implementation 未授权**

审核依据：[S0 Independent Docs Acceptance](p5-5d-s0-independent-docs-acceptance.md)。

日期：2026-09-20

Owner：Archive Application / Archive Domain / Baseline Domain（按下文分责）。

入口：[S0 Entry Brief](p5-5d-s0-entry-brief.md)；实施预算：[Execution Plan](p5-5d-archive-execution-plan.md)。
上游：[P5 §2A / §6.4](p5-business-vertical-slices-design.md)、
[Business Lifecycle §5](../contracts/business-lifecycle-and-state.md)、
[Canonical Storage](../contracts/canonical-storage-and-repository-boundary.md)、
[External Effect](../contracts/external-effect-and-recovery.md)、
[Proportional Assurance](../policies/proportional-assurance-and-risk-based-verification-policy.md)。

## 1. Decision and non-goals

Archive 是同步业务命令：唯一选择一个合格 Submission，把它的既有 immutable commit 设为下一业务
Baseline；用一个 SQLite commit 冻结全部接受输入、记录结果、分类 sibling 并释放 Workspace。
Repository main 可以比被选 commit 更新，也可以处于另一 Submission 的技术后继位置；Archive
不比较 main 与被选 commit 的先后，不调用 Repository，不移动 ref、不合并、不重新 materialize、
不重复 import/commit。成功的本地事务就是归档成立点。

PreviewArchivePlan 为纯读，可重复调用，不保留 preview ID，不冻结、不预占。Confirmation 与
AnomalyResolution 可在 Start 之前独立 append 审计事实，但这些事实不预留候选、不阻止 Review
或 Submit，也不等于成功 ArchivePlan。没有 Operation、ArchiveExecution、持久 candidate/status、
outbox、notification dispatcher 或 full-row archive 副本。

本文新增接口、表、权限、测试已作为设计接受，尚未实现；当前代码事实仅在 §2 明示。
Business Lifecycle `3.0.0` 补充已同步接受，文档审核通过不构成 implementation authority。

## 2. Current code and required seams

只读核查基线 `16f4112ee1`；与 accepted 5C `04317788c2` 的 `vnext/**` 无差异。下表路径相对
`vnext/backend/src/gateway_backend/`，可以用入口文档的基线在 Git 中复核。

| 真实路径 / 接口 | 当前实现 | 5D 接入决策 |
| --- | --- | --- |
| `infrastructure/control_db/database.py` / `ControlDbUnitOfWork` | `BEGIN` 读事务、`BEGIN IMMEDIATE` 写事务；WAL、foreign_keys、synchronous FULL；participant 共 connection | 添加 Baseline/Archive participant；应用只消费 typed UoW port，不接触 `.connection` |
| `infrastructure/control_db/migrations.py` | operations component v1；workspace component v4，已有 v1→v4 迁移 | 下一 workspace v5 一次完成相关业务表升级；不新增独立迁移框架 |
| `domain/workspace/models.py` / `BaselineHead` | 三字段 value DTO：node、commit、version，无持久 Node | 新 Baseline owner 模型/port；保留旧 DTO 为 5A/5B adapter 输出，不把 Archive 放入 Workspace Domain |
| `infrastructure/control_db/sqlite_mapping.py` | `ProvisionedScopeResolution`、`ProvisionedBaselineHeadRead` 读 mapping 中 Head；`seed_provisioned_mappings` 每次覆盖 Head | mapping 只拥有 scope/Repository/enabled；Head 唯一 authority 迁出；HTTP/worker 所有 reader 和 seed 同时接入 |
| `application/submission/accept_transaction.py` / `accept_submit_transaction` | preflight 在事务外读 canonical/main；T1 重读 scope、Head、occupancy，并插入 repository occupancy | 保留外部读在事务外；T1 通过同一 Head adapter 看 Archive 推进；无需 Archive lock row |
| `application/submission/accept.py` / `validate_accept_submit_with_frozen` | 重放先验证当前授权，再用既有 Attempt；新动作校验 current Head 与 preflight/Preview binding | 保留既有 replay 语义；新增回归验证旧 preflight 不穿过 Archive |
| `domain/submission/models.py` / `Submission` | 已保存 `based_on_baseline_node_id`、业务 base commit、`repository_commit_id`、canonical digest、manifest ref/digest、source refs、verification facts | Candidate 只读这些冻结事实；不把 manifest digest、commit hash 当 canonical business digest |
| `domain/submission/ports.py` / `SubmissionReadPort` | 只有按 Submission/Attempt ID get；没有候选集合接口 | 增加按 scope/Repository/base 的 bounded facts 查询 port，由 SQLite adapter 批量 join；不从 Archive 调 Review 用例 |
| `application/submission/review_transaction.py` | 同 UoW append/CAS/replay/release；未查 ArchiveResult | Review 新 mutation 增加 closure read；不能仅依赖 Workspace occupancy 错误表达已归档 |
| `application/submission/review.py` | fresh-scope helper 把 Head 变化也视为 scope mismatch；release 清 current input/preview、删除 occupancy，Workspace 保持 OPEN | 最小区分 Repository 授权变化与正常业务 Head advance；授权不绑定某个 Head；Review replay 仍先于 closure/new-action guard |
| `http/runtime.py`、`http/dependencies.py`、`http/wiring.py` | production factory、Workspace dependencies、固定 OpenAPI path 集合 | composition 明确构造 Archive dependencies，新增 route/schema/orchestration，不往通用 context bag 堆字段 |
| `bootstrap/operation_worker.py` | startup 也 seed mapping，Preview 使用 `ProvisionedBaselineHeadRead` | 必须纳入 seed 不回退验证；不注册 Archive job |
| `capabilities/business_projection/contracts.py`、`comparison_projection/contracts.py` | docstring 占位，无执行接口 | 本 slice 无其执行 consumer，不实现也不依赖；CandidateProjection 归 Archive Application |

当前部署示例 `vnext/deploy/config/provisioned-mapping.json` 的 `local-dev-commit` 是占位值，不能用它
宣称已存在真实 initial commit。容器 journey 必须用正式 provisioning 产生的真实 initial commit；
Archive 不承担 Repository provisioning，migration 也不推测 main 或执行 Dolt。
另已核查现有 `test_submit_compose_e2e.py` 的 seed helper 在创建 Repository 后先 import 一个
零行 `t` 表，再将该 commit 登记为 version=0 测试 base；它不是 P5 §4 所说的 Repository
initial empty commit 证据。保留其作为既有 schema-seeded fixture 回归；5D 必须新增真实
initial-empty 接入场景，不能把该 helper 的结果冒称初始 commit。

### 2.1 Initial-empty is a prerequisite gap

已确认 `application/preview_jobs.py::_bound_from_side_document` 使用
`if type(tables_raw) is not list or not tables_raw` 拒绝空集合；因此即使零表 baseline 完成
materialization，下一步从 checkpoint 解码也会失败。**当前 initial-empty journey 未支持完整，
不能仅新增 fixture 宣称具备验收条件。** S1 增加由 Preview/Comparison/Submit 原 owner 负责的
前置修复与验证 gate，详见 Execution Plan §3–4，通过后才能进入 Archive journey。

| 链路 / 已核查路径（相对 Backend source root） | 现状与 S1 必须证明的行为 |
| --- | --- |
| `infrastructure/repository_read/http_arrow.py::_hidden_summary_from_streaming_tables` → `capabilities/snapshot_materialization/repository_ref.py` | 按 catalog tables 构建描述符和 digest；代码允许迭代零表，但尚无本轮运行证据。验证 exact initial commit 的零表 summary/table set，不能伪造一张零行表 |
| `application/preview_jobs.py` materialize checkpoint 编解码 | 明确阻塞；允许经 snapshot/summary/repository identity 和空集合 digest 校验的 `tables=[]`，仍拒绝字段缺失/null/错误类型、非空 summary 丢 refs、digest 不匹配；不能简单移除 non-empty guard 后把缺损 checkpoint 当空输入 |
| `capabilities/comparison/contracts.py` / `pair_planning.py` / `standard.py` | BoundSnapshotInput 的空 tuple 不等于 absent；`BASELINE_RECONSTRUCTION_EMPTY` 当前判断的是 baseline 对象为 None，不是零表。验证 FULL 的 baseline→INITIAL、MODIFIED_ONLY 的空 baseline 复用、零表→有表的新增，以及零表→零表的完整 facts/records closure |
| `application/preview_jobs.py::_run_pair_pipeline` → risk/surface/bundle 公共入口 | 两种输入模式均须得到正常 READY closure，重启/从 checkpoint 续跑与连续运行结果一致；零表不是计算失败、降级或 missing input |
| `application/preview_jobs.py::compute_baseline_canonical_bundle_digest` → `http/runtime.py::HttpBaselineCanonicalDigestPort` → Submit T1 | 当前走同一完整 pair/risk/surface/bundle 拓扑，不能返回硬编码 empty digest。验证两种模式的空 base canonical digest 与同拓扑结果一致、有真实改动可通过 T1、无 canonical 改动仍在 Attempt/Operation 前拒绝 |

这里不要求 Upload 接受原本不合法的空 source package；零表→零表是 baseline digest 的内部计算
输入。必要修复只在原 owner 内保持既有公共 Contract，不让 Archive 调 Preview 私有函数、不新增
Archive 专用 comparison mode。若发现 capability 本身有额外空集合阻塞，按计划中列明的 owner
路径最小修复并跑其原测试；超出预算或改变 canonical/identity 语义必须停止并重评，不能跳过此 gate。

## 3. Candidate identity, query and bounded preview

### 3.1 Eligibility and closure

V1 accepted 设计规定一个 Repository 的整个业务历史只属于一个固定
`(gateway_device_external_key, business_project_id)`，不允许不同 scope 共享或先后接管同一
Repository；同 scope 的多个 actor 仍合法。当前 schema 仅有 one-active-device 约束，**没有**
这个反向基数保障。规则已写入
[Business Lifecycle §1A](../contracts/business-lifecycle-and-state.md#repository-scope-ownership-amendment)，
补充已独立复审接受为 `3.0.0`；不是 `2.0.0` 已有约束。S1 的这项 Contract 前置已满足，
实现仍须后续明确授权。

在一个 read-only UoW snapshot 内先验证该 Repository 的固定 scope，再按当前 session 解析
current BaselineHead。因此本 scope 的候选全集等于该 Repository 的业务候选全集。若发现另一
scope 的 mapping 或历史 Workspace/Submission，返回完整性失败，不静默过滤、不归档任一子集。
候选资格严格为：

1. 成功的 immutable Submission，repository 及其 Workspace 冻结 device/project 与当前授权相符；
   project Archive 权限允许覆盖其他 actor 的 Workspace。
2. Review current projection 为 `APPROVED`，其 event/projection closure 有效。
3. `based_on_baseline_node_id` **及** `business_baseline_commit_id` 匹配 current Head node/commit。
4. 未出现在任何已提交 ArchiveResult 的 disposition 中（selected 和 sibling 都算关闭）。

Workspace occupancy/bindings 和 finalized Attempt closure 是 Start 的不可豁免完整性 gate。
缺失或矛盾时不能悄悄从 candidate set 丢掉一项以缩小 sibling 集合；返回 typed integrity blocker，
Start fail closed。Review=`PENDING/REJECTED/RETURNED_FOR_REVISION/WITHDRAWN` 不在候选内。
旧 base approved Submission 留在历史事实中，不属于普通 candidate。旧 base 的 PENDING 后来
APPROVED 也不自动回归资格：可由 Review return，再基于新 base Preview/Submit；不自动迁移内容。

稳定引用是 `{submission_id, expected_candidate_digest}`，不是可变 candidate ID。digest 相同
不合并两个 Submission；选择始终按唯一 Submission ID，两个内容相同的 Submission 也分别审计。

### 3.2 Canonical digest contracts

Archive Application `contracts.py` 拥有纯 codec/validator/digest 规范，复用现有
`gateway_shared_kernel.jcs.canonicalize_jcs`。不复制 Storage Projection 摘要算法，不依赖私有
snapshot digest，也不引入 provider/class/运行时间作为身份。

统一 `D(kind, payload) = 'sha256:' + hex_lower(SHA256(UTF8('gateway-vnext:archive:' + kind + ':v1')
+ byte(0) + JCS(payload)))`。payload 仅 strict JSON、I-JSON 安全整数；object unknown keys 拒绝，
数组按下述规则排序，重复 ID 拒绝；可选字段用显式 null，不能把空值和 omitted 当两个身份。
此 v1 是 Archive 消费者所需规范版本，不新增通用 policy/version registry。

| kind | 完整语义 preimage（字段名为拟定公共 contract） |
| --- | --- |
| `candidate` | `repository_id, gateway_device_external_key, business_project_id, workspace_id, workspace_generation, submission_id, submit_attempt_id, upload_revision_id, preview_result_id, based_on_baseline_node_id, business_baseline_commit_id, repository_commit_id, canonical_business_digest, canonicalization_manifest_ref, canonicalization_manifest_digest, source_artifact_refs`（按 UTF-8 ID 排序）、`requested_verification_policy, completed_verification_policy, review_status, review_sequence` |
| `candidate-set` | `repository_id, gateway_device_external_key, business_project_id, baseline_node_id, baseline_commit_id, baseline_head_version, candidates`；candidates 为按 UTF-8 submission_id 排序的 `{submission_id, candidate_digest}` 全集 |
| `selection` | `candidate_set_digest, selected_submission_id, expected_candidate_digest`；selection 所指必须在全集中 |
| `anomaly` | `selection_subject_digest, issue_code, sibling_submission_id, sibling_candidate_digest` |
| `confirmation-request` / `resolution-request` | exact resolved scope、command kind、`selected={submission_id,expected_candidate_digest}`、`candidate_set_digest`、`subject_digest`、expected Head node/version、expected subject sequence、action、reason、actor_id；resolution 另含 `issue_code,sibling_submission_id,sibling_candidate_digest`；覆盖 §8.1 全部语义 body 字段 |
| `start-request` | exact resolved scope、expected Head node/version、candidate_set_digest、唯一 selected ref、按 subject digest 排序的 exact confirmation/resolution `{subject_digest, sequence}` references；不含 server ID/time、幂等键或当前可变事实 |

`candidate` 不含当前 Workspace version、active Attempt、confirmation sequence 或整个 candidate set；
这些各自验收，不制造 digest 递归。Review sequence 改变会改变 candidate digest，即使未来状态回到
APPROVED 也不能复用旧确认。candidate-set 绑定 Head version 防止 ABA；新增 approve/return 会使
集合变化。审计事件的追加不改变 candidate-set；subject digest 也不包含其自身 sequence。

### 3.3 Queries and PreviewArchivePlan

拟定 `GetArchiveCandidates(context)` 返回 scope、Head、完整候选 refs/facts、candidate-set digest、
active Attempt blocker。`PreviewArchivePlan(context, selected_ref)` 在同一读 snapshot 派生 selection
subject、需确认事项、异常及审计有效性、选中 commit、全部 sibling dispositions 和预计 Workspace
release。没有 selection 时只用候选查询，不暗选第一条；未知/失效 selected ref 返回冲突。

预览不创建 Plan、result、idempotency row、审计 event、artifact 或 Operation；不更新 last-viewed
字段、不落 cache。返回 `can_start` 仅代表此 snapshot，不承诺之后 Start 成功。

首版提案限制：候选最多 200 项（查询 limit 201 识别超限）、请求 JSON 最大 256 KiB；文本均以
strict UTF-8 **字节数**为唯一长度预算：ID/key 1–255 bytes，非 null reason 1–4096 bytes。
不另设 2000 字符上限；Unicode 字符数仅作解释，不作第二套验收。拒绝非 string、非法 surrogate
及不可编码值，不自动截断、trim 或 Unicode normalize 后再计算 fingerprint。可选 reason 的
omitted 统一为 null；需要 reason 的动作仍不允许 null/空串。digest 为 `sha256:` + 64 lowercase
hex，sequence/version 为非负 I-JSON integer 且拒绝 bool。

HTTP 可以复用公开 `BoundedOpaqueId`、`BoundedDiagnosticReason`、`NonNegativeIJsonInt` 的
现有语义；不改变它们或其余用例。Archive Application `contracts.py` 明确定义相同的 byte
规则与纯 validator，HTTP Archive DTO/command mapper 调用同一 owner validator（可以在复用
公开 Annotated 类型之上委托校验）；Application 不 import HTTP 或 Operations 私有常量。
Archive 专用约束仅为固定格式 digest、各动作 reason 必填性和集合大小，不需要另创不同文本上限。
SQLite 对新增 Archive 文本使用 `length(CAST(value AS BLOB))` 检查 UTF-8 bytes，不能用
`length(TEXT)` 替代；迁移不重写已有历史文本，处理命令引用超预算旧 ID 时明确拒绝而非截断。

audit references 最多 200 项；全部数组禁止重复。分页不会用于
Start 的候选全集，超过上限返回 `ARCHIVE_SCOPE_LIMIT_EXCEEDED`，不可只归档第一页。通过既有
Review 处置减少集合或重新评估容量预算，不新增后台分批归档。审计历史读取采用每页最多 100 的
单 subject sequence cursor，不把全历史载入 Start；批量读每个 subject 最新事件与被引用事件。

## 4. Confirmation and AnomalyResolution

### 4.1 Owner and actual consumer

Archive Domain 拥有 append-only Confirmation/AnomalyResolution 的形状和 sequence 不变量；
Archive Application 拥有 subject 推导、授权、当前有效性与 Start 验收。真正 consumer 为
PreviewArchivePlan 展示、Start gate 及 ArchiveResult 审计读取。能力层不 import Archive。

已接受的最小业务策略：

- 每个 selection 必须有一个 `CONFIRM_SELECTION` subject：确认 selected commit、base、完整
  candidate set 和所有 sibling disposition；subject digest 即 `D(selection, ...)`。
- 每个未选 approved sibling 产生 `APPROVED_SIBLING_EXCLUDED` anomaly，subject 用上述 anomaly
  digest；必须以 `ACKNOWLEDGE_EXCLUSION` + 非空 reason 解决。语义是知悉该成功内容未成为新
  baseline，后续采用须重新 Preview/Submit；不是合并冲突修复，也不声称比较了两份内容。
- 单候选没有 sibling anomaly，resolution refs 必须为空。多候选即使 canonical digest 相等，
  不省略 sibling 事实或自动确认；选择与 sibling 审计身份不同。
- 不借 Archive 补签 Submit 的 destructive/identity confirmation，不把 P3 assessment/bundle
  当作已经持久化的 Archive anomaly。没有已冻结的其他 Archive issue producer，V1 不做通用
  caller-supplied anomaly、风险豁免、任意“已处理”标签或 dynamic policy 插件。

Review、scope、Head、active Attempt、candidate closure、missing manifest identity 和 SQLite
integrity 属于不可豁免 gate；AnomalyResolution 不能消除这些 blocker。

### 4.2 Append, sequence and validity

拟定 `AppendArchiveConfirmation` 接受 `CONFIRM | REVOKE`；`AppendArchiveAnomalyResolution`
接受 `ACKNOWLEDGE_EXCLUSION | REVOKE`。一个 subject 流按 `(RepositoryId, subject_kind,
subject_digest)` 唯一排序，sequence 从 1 递增，空流 expected_sequence=0；REVOKE 要求已有流
并有非空 reason（§3.3 的 UTF-8 byte 规则）。不 update/delete 旧 event，不持久化 active flag、expiry 状态或 latest projection。

每条事件冻结 event ID、exact device/project/Repository、subject kind/digest、sequence、action、
reason、actor_id、UTC occurred_at、idempotency key、规范化完整 request payload 与 request fingerprint。
request payload 保存 selected、集合 digest 等全部接受绑定，便于在不读当前候选时核对 replay；
不保存原始 HTTP bytes/headers。subject payload 按
canonical 规范保存以解释审计事件；它是一次人类动作的审计对象，不能被查询为持久候选实体或
preview plan。reference 为 `{subject_digest, sequence}`，可由 scope/subject 定位 event。

append 也是短 `BEGIN IMMEDIATE`：strict shape/byte 校验 → 当前授权与 scope → 由全部请求绑定
计算 fingerprint 并查已成功 key → 同 key 比较 durable 完整 request/fingerprint → expected Head/
重新推导 subject → expected latest sequence CAS → append。无需无 active Attempt；记录当时
知悉事实可以在 Submit 活跃期间发生，但 Start 仍拒绝。subject 已过期时新 append 拒绝；原 key
replay 仍返回原事件，但只有完整请求 fingerprint 相同才算 replay；即使 subject_digest 未改，
修改 selected ID/candidate digest 或 candidate_set_digest 也必须返回 `IDEMPOTENCY_CONFLICT`。
比较 replay 时不重算 current subject、不查当前 Head/审计最新 sequence；新动作才执行这些检查。
整个流的最新 sequence 控制并发，不按 actor 各自维护流。

Start 时有效当且仅当：subject 仍从本次 Head/集合/选择导出、引用的是当前最新 sequence、最新
动作是 affirmative、事件 scope 正确。后续 REVOKE 使旧 affirmative 无效；同 subject 再确认必须
新 sequence，并提交新 reference。V1 不加墙钟 TTL、不要求双人复核，任一持有 `archive_submission`
权限的项目审核人可确认/撤销，Start actor 可不同；事件发生时授权冻结为审计事实，Start actor
必须当前授权。权限撤回不追溯抹除既有审计事实，如需撤销使用新的授权 REVOKE。

成功 Start 后这些 event 被 Plan 引用；后续 Head 改变不会改写历史 Plan，有效性只在新动作中派生。
不允许通过针对已关闭 subject 的新 revoke 撤销已成功 ArchiveResult。以上 actor/撤销策略已由独立
docs review 接受，未暗示上游已规定双人制、TTL 或跨系统签名。

## 5. Start transaction, replay and concurrency

### 5.1 Ordered acceptance

命令 `StartArchive(context, idempotency_key, expected_baseline_node_id,
expected_baseline_head_version, candidate_set_digest, selected_ref, confirmation_refs,
anomaly_resolution_refs)`。`selected_ref` 为单个对象；不接受 list selection 或 caller commit。

严格顺序：

1. HTTP strict shape/size；当前 session、`archive_submission` 权限、new-work admission。
2. 开启同 control DB `BEGIN IMMEDIATE`；解析 transaction-fresh enabled mapping，冻结本次 exact
   device/project/Repository。不可将事务外 Head snapshot 当授权依据。
3. 以 `(repository_id, device, project, command_kind=START, idempotency_key)` 查成功结果；先核对
   durable record/Plan/Result closure，再按本次请求的固定字段计算 fingerprint。same key/same
   fingerprint 返回原 Plan/Result，**早于** current Head/candidate/confirmation/occupancy 检查。
   same key/different fingerprint 返回 `IDEMPOTENCY_CONFLICT`。当前 scope/权限永不被 replay 绕过。
4. 新动作才校验 expected Head node/version；检查 repository occupancy，并查该 Repository 的
   `PREPARED/EFFECT_PENDING` Attempts。任一 active（含 UNKNOWN、MANUAL_RECOVERY_REQUIRED
   对应的未终局 Attempt）阻塞；两者不一致返回 integrity failure，不清理或推断释放。
5. 同 snapshot 批量读全集，重算 candidate-set/selected digests、Review closure、所有 involved
   Workspace generation/input/preview/active_submission binding；校验 confirmation/anomaly exact
   subject set、sequence 和 affirmative 状态。缺少、多余、跨 scope、重复或 stale 引用都拒绝。
6. 生成 server Plan/Result/Node IDs 和一个 UTC transaction time；构造 immutable Plan：scope、
   accepted_by/time、request fingerprint/key、原 Head node/commit/version、全集 candidate refs、
   selected ref/commit、审计 exact refs、所有受影响 Workspace 的 version 与 Submission binding。
7. 在同一 transaction 插入 Plan、新 BaselineNode（parent 为旧业务 node；commit 为 selected
   Submission commit）、Result 和 dispositions；CAS Head 从 exact node/version 到新 node/version+1；
   对选中及全集未选 sibling 逐一 CAS Workspace version，清 current input/preview、删除 exact
   active_submission occupancy。Workspace 保持 OPEN、generation 不回退，version 增 1。
8. 提交成功才响应 `201`；replay `200`。任何失败 rollback 全事务，包括失败的 Head/Workspace
   CAS、约束或 commit。校验失败不记录 Plan/Result/key；已独立 append 的审计事实继续存在。

release 复用 Workspace owner 的写 port 和 Submission occupancy port；不从 Archive 调用
Review 私有 release helper。保留 immutable UploadRevision/PreviewResult/Submission/Review facts、
SourcePackageArtifact durable retention、manifest 和 Repository history；Archive 不增加 artifact
pin/transfer/cleanup，不把 Workspace CLOSED 作为 archive disposition。

### 5.2 Idempotency details and errors after commit

START fingerprint 不包含 actor_id：同 exact scope、同 key/payload 的另一位当前授权 actor 可以
取回既有结果，Plan 的原 accepted_by 不变。审计 append fingerprint **包含 actor_id**，防止不同
actor 对同 key 被误表示为同一签署动作。command_kind 隔离 confirmation/resolution/Start key。

fingerprint 包含 caller 的 expected versions 和 exact refs，集合顺序规范化但语义不同必冲突。
不能在重放时用 current Head、当前审计序列重建旧请求；使用 Plan 冻结输入/已存事件校验 durable
fingerprint。Head 已前进、Workspace 已 release、subject 已失效均不使合法成功 replay 失败。

commit 前进程退出由 SQLite rollback；commit 后响应丢失由原 key 重试查成功 Plan/Result。
遇到连接/commit 响应不明，客户端不得换 key 推断失败，重试原 payload/key；服务重开连接查
本地事实，不创建 ArchiveExecution 或 effect journal。普通 busy 使用已有 5s bounded timeout
与 503，不能把未知数据库错误当业务 conflict，也不自动改写损坏事实。

### 5.3 Semantic barriers

SQLite 锁是当前单机数据库 writer serialization；语义 scope 仍是 Repository/Head，不新增锁表。

| 竞争 | 谁先 commit | 另一路可观察的结果 |
| --- | --- | --- |
| AcceptSubmit T1 / Start | T1 先 | Archive 看到 active Attempt，返回 `ACTIVE_SUBMIT_ATTEMPT`；Operation terminal 不替代 Attempt terminal |
| AcceptSubmit preflight / Start | Archive 先 | T1 重读新 Head，旧 base/preflight 拒绝；不得创建新 Attempt/Operation；以后新 Preview/Submit 合法 |
| Finalize/Abort / Start | 终局事务先 | Finalize 的 Submission/Review seed/occupancy 或 Abort release 完整可见；PENDING 不进候选；Archive 不读取中间前缀 |
| Review return/reject/withdraw / Start | Review 先 | candidate digest/set 改变，旧 Start 冲突；Review release 已完成 |
| Start / 新 Review mutation | Archive 先 | Review 在授权、成功 replay 后查 closure，返回 `ARCHIVE_CLOSED`；selected 和 closed sibling 均不可再 return/withdraw |
| 两个不同 key Archive | 一个先 | 另一个 Head CAS/precondition 冲突，无第二结果、无 sibling 重释放 |
| 同 key Archive | 一个先 | 相同 fingerprint 返回原结果；不同 fingerprint 冲突 |
| 审计 revoke / Start | revoke 先 | 引用 sequence 过期，Start 拒绝；Start 先则归档已成立，revoke 不撤销结果 |
| 新 approve / Start | approve 先 | candidate set 增大导致旧请求冲突；Start 先则旧 base 的新 approve 仍保留历史，非新候选 |

Review closure read port 定义在 Submission Application（consumer-owned
`ArchiveClosureReadPort`，只返回 closed bool），SQLite adapter 查询 ArchiveResult disposition；
不能让 Review import Archive Application 的 transaction/service，也不能让 Archive Domain import
Submission Domain。Review 原成功 approve/return replay 允许在后续归档后返回原事件，但不执行
新状态变化；fresh-scope 比較必须区分 Repository 授权与合法 Head advance。

## 6. Persistence, migration and initial Baseline

### 6.1 Proposed records and ownership

所有表在既有 control DB。下面是字段预算，不是本轮 DDL；具体 SQL mapping 归 infrastructure，
domain record 不含 SQLite connection、HTTP body、capability/provider 或 Repository wire DTO。

| 表 / 唯一 owner | 最小权威字段与约束 |
| --- | --- |
| `baseline_node_records` / Baseline Domain | node_id PK；Repository、frozen device/project；commit_id；kind=`INITIAL/ARCHIVED_SUBMISSION`；parent_node_id nullable；source_submission_id nullable；created_at；INITIAL 无 parent/source，ARCHIVED 必有；composite repository/node FK 防跨 root |
| `baseline_head_records` / Baseline Domain | repository_id PK、node_id、optimistic_version >=0；同 Repository node FK；commit 从 Node join 派生，不再复制进 Head |
| `archive_plan_records` / Archive Application | plan_id PK；scope；key/fingerprint；accepted_by/time；old Head identity；canonical frozen input（§5.1）；UNIQUE exact scope+START key；immutable；没有 draft/status |
| `archive_result_records` / Archive Domain | result_id PK、plan_id UNIQUE FK、baseline_node_id UNIQUE FK；成功时间；只存在成功结果，没有执行四态 |
| `archive_disposition_records` / Archive Domain（Result children） | submission_id PK、result_id FK、disposition=`ARCHIVED_BASELINE/CLOSED_NOT_ARCHIVED`；每 result 恰好一个 selected，通过 filtered unique + transaction closure 保证；这是 Result 的规范化子记录，不是 Submission 上另一套 archive status |
| `archive_confirmation_events` / Archive Domain | §4.2 字段；UNIQUE scope+subject_digest+sequence；UNIQUE scope+CONFIRMATION key；append-only |
| `archive_anomaly_resolution_events` / Archive Domain | 同上，含 anomaly issue/sibling identity；UNIQUE scope+subject_digest+sequence；UNIQUE scope+RESOLUTION key；append-only |

不另建 Start idempotency table：成功 Plan 的唯一 key/fingerprint 就是 replay authority。失败 Start
不占 key。事件也直接持有其成功 key，不增加通用 command receipt。Plan/Result 双向存在性、
selected count、candidate/disposition 等集合、Head/Node/Submission commit 一致性由同事务
closure 校验与测试证明；FK/unique/CHECK 负责可直接表达的约束，不用新持久 evidence 状态机。

索引限定真实 query：candidate read 的 `submission(repository_id, based_on_baseline_node_id,
submission_id)` 与 Review join、active Attempt 的 `(repository_id,state)`、audit subject latest
sequence、Result children result_id。所有 scope、IDs 使用绑定 SQL 参数。

### 6.2 Upgrade from workspace schema v4

保持 operations v1；下一 workspace v5（名称虽为 workspace，现状已经承载 Submit/Review）用现有
migration ledger 和一个 migration transaction 建表、验证、转移 Head authority、重建 mapping 表。
若实施前版本已被其他工作占用，重新确认相邻版本，不覆盖历史 migration。

1. 验证 integrity/FK；按 Repository 聚合所有 mapping（包括 disabled），必须只有一个 distinct
   device/project scope，**即使多个 scope 的 node/commit/version 完全相同也拒绝**。所有历史
   Workspace/Submission 的冻结 scope 必须与之相同；disabled、旧历史不得作为共享例外。
   不能沿用 `LIMIT 1` 任选 Head。historical Workspace/Preview/Attempt/
   Submission 的 Repository/base 引用必须能解释；缺少 mapping 或出现不可重建的历史 base 停止。
2. 本 slice 自动迁移仅接入已 provision 的 explicit initial Baseline（version=0），保留 exact node ID
   和 commit ID，建 INITIAL Node 与 Head=0；已存在 v4 Submit/Review 全部保留。不得要求没有
   Submission，也不得把最新 Submission/main 猜成 base。
3. 非零 seed version、一个 Repository 多组冲突 Head、同 node ID 跨 scope/Repository、无法证明
   initial 的历史数据不能伪造 ArchiveResult 或 SYSTEM_MIGRATION；migration fail closed，由
   provisioning/cutover owner 给出独立数据迁移方案。本设计不授权 legacy cutover。
4. 重建 `provisioned_scope_mappings` 只保存 device/project/Repository/enabled，保留原有约束并新增全表 `UNIQUE(repository_id)`（不限 enabled），移除
   三个可变 Head 字段；旧消费者通过 adapter join 新 Head/Node 返回既有三字段 DTO。
5. 全部校验通过才提交 version=5。失败恢复为完整 v4；fresh DB 从既有 migration 顺序升级，
   没有 mapping 时先建空表，再由 seed 初始化。禁止自动 downgrade；旧 binary 遇 newer schema
   按现有 UnsupportedSchemaVersion fail closed。

initial commit 的真实性由外部 provisioning 拥有，迁移只保留已登记事实，不声称校验 Repository
内容。真实 container 验收另证明从真实 initial empty commit 到新 Baseline 的 journey。非零/矛盾
数据是迁移停止条件，不把人工编辑 DB 作为正常恢复 API。

### 6.3 Seed and restart invariant

保持现有 server-owned mapping JSON 的字段输入，三个 baseline 字段从“每次写 current Head”
收窄为“Repository 初始 seed identity”。首次 Repository seed 仅接受 initial version=0；创建
INITIAL Node/Head 与 mapping 原子完成。已存在 Repository 时核对文件 initial identity 与存储
INITIAL node 一致，**从不更新 Head**；归档后旧 seed 重读无影响，错误的 initial identity 明确
启动失败。enabled 及 control-plane mapping 更新仍由原 owner 处理，不能重写历史对象 scope；
mapping 指向新 Repository 时，该 Repository 必须有匹配自身初始事实，旧 Repository 数据保留。

首次 seed、批量 mapping 文件和 mapping update 使用同一个 transaction-scoped 验证入口：先校验
整个输入批次与既有 mapping 的反向唯一性，再检查该 Repository 的 INITIAL Node 冻结 scope。
INITIAL Node 作为已存在的 durable 所属依据，不另建 owner registry；每 Repository 仅一个
INITIAL Node（filtered unique），其中 scope 永不更新。即使原 mapping 已移走或 disabled，
也不能把旧 Repository 重新分配给别的 scope；同 scope 重启、禁用/启用可重放，业务 scope 换新
Repository 仍受其固定归属限制。任一冲突使整批 seed/update rollback，不能先更新部分 mapping。
每次 scope resolution/Archive 验收还核对 INITIAL scope，防止遗留不一致穿过查询过滤。

若业务确需 Repository 跨 scope 共享/转交，当前设计不支持：先由 owning Contract 定义授权全集、
候选集合、历史访问与 sibling release，再修改迁移/查询/验收；不得简单撤掉 unique index。

同时改 `ProvisionedBaselineHeadRead`、`ProvisionedScopeResolution`、transaction-fresh reader，
覆盖 HTTP runtime 与 worker startup。不得只修 HTTP seed；worker 重启同样可能覆写。不增加
新配置服务/同步 daemon。新 Head 每次读来自 DB，不在进程 startup cache 固定。

部署升级先关 admission、drain/停止共享 DB 的旧 HTTP/worker，按既有维护流程保存一致 SQLite
backup，再迁移并启新进程。不能混跑 v4/v5 writer。迁移前可恢复一致备份；一旦接受新归档，
恢复旧备份会丢失权威事实，不能当普通 rollback，须停写由 owner 决策。本文只是实施设计，不
执行维护、备份、权限变更或部署。

## 7. Modules, ports and dependency budget

拟新增小模块（准确路径预算见 Execution Plan §3）：

- `domain/baseline/{models,ports}.py`：Node/Head authority；`domain/archive/{models,ports}.py`：
  Result/disposition/audit invariants。Domain 只依赖 Shared Kernel；跨 domain 只用 opaque IDs。
- `application/archive/contracts.py`：Input/Result/Facts、canonical bytes、shape validators；
  `ports.py`：最小读 port / 同事务 UoW protocol；`queries.py`：bounded read orchestration；
  `audit.py`、`start.py`：短事务与业务策略。不新增 `archive_jobs.py`。
- `infrastructure/control_db/sqlite_baseline.py`、`sqlite_archive.py` 实现 row mapping；
  `sqlite_submission.py` 增加真实候选事实查询，Review closure adapter 在 `sqlite_archive.py`
  实现 consumer-owned port，由 composition/UoW 绑定。
- `http/routes/archives.py`、`schemas/archive.py`、`orchestration/archive.py`：HTTP contract mapping；
  `http/runtime.py` 装配具体 UoW/adapter。依赖对象可定义在 `http/dependencies.py` 为独立窄
  `ArchiveHttpDependencies`，不能扩成 common context。不新增 Repository client 或 provider。

Archive read model 可用本用例 `ArchiveCandidateFacts` 承载批量 SQL join 的中性业务事实；不能把
SQL row、wire VersionedOperation 或 capability intermediate object 当公共结果。不因 Archive
是第三个 consumer 就 import Review/Submit 私有 helper；如公共 sequence/scope 逻辑确需共享，
在其原 owner 暴露窄 port/入口，禁止反向 import transaction/job。

`business_projection` / `comparison_projection` 占位继续延期到真实跨 Slice consumer 复核；
Archive 无计算 consumer，不能为了模块清单实现空 pipeline。现存 P5 §2A 已知 wire/private/helper
问题仍由原 owner 在 P5 exit 前收口，本轮不整体重构。必要 cross-slice 改动包括 Head authority
adapter、Review closure/fresh-scope 区分及 S1 initial-empty Preview/Comparison/Submit 前置支持；
均由原 owner 在精确路径预算内完成，不扩大 Archive 的能力依赖。

## 8. HTTP contract and production wiring

### 8.1 Routes and DTOs (proposed v1)

权限字符串 `archive_submission`，对 device/project 的独立权限；不由 upload/submit 或
`review_submission` 隐含授予。每次读、append、新 Start、replay 都重新检查当前 session、enabled
mapping 和 exact scope。原作者不自动拥有项目 Archive 权限；有权限的其他 actor 可处置同项目
Workspace。内部 Repository bearer 和 admin recovery bearer 都不是此业务 authority。

路径 scope 从 session 解析，caller 不提交 RepositoryId、actor、device/project 或 commit/server path：

| HTTP | Request | Result |
| --- | --- | --- |
| `GET /v1/archive-candidates` | 无业务 body | `ArchiveCandidatesResponse{head,candidates,candidate_set_digest,blockers}` |
| `POST /v1/archive-plan-preview` | `{selected:{submission_id,expected_candidate_digest}}`；纯读，不要求 key/expected version | `PreviewArchivePlanResponse{head,candidate_set_digest,selected,selection_subject_digest,confirmation_requirements,anomalies,audit_validity,dispositions,workspace_releases,can_start,blockers}`；200 |
| `POST /v1/archive-confirmations` | Idempotency-Key；`{expected_baseline_node_id,expected_baseline_head_version,selected,candidate_set_digest,subject_digest,expected_sequence,action,reason}` | immutable confirmation event；201/200 replay |
| `POST /v1/archive-anomaly-resolutions` | 同上，另有 `issue_code,sibling_submission_id,sibling_candidate_digest`；action 为 resolution action | immutable resolution event；201/200 replay |
| `GET /v1/archive-audit-events` | `subject_kind,subject_digest,after_sequence=0,limit=100` | scope 内按 sequence 的 events、next cursor；无任意全项目导出 |
| `POST /v1/archives` | Idempotency-Key；§5.1 Start DTO | `ArchiveStartedResponse{archive_plan_id,archive_result_id,baseline_node_id,baseline_commit_id,baseline_head_version,selected_submission_id,dispositions,released_workspace_ids,archived_by,archived_at}`；201/200 replay |
| `GET /v1/archives/{archive_result_id}` | 当前授权 | immutable frozen Plan summary、Result、引用审计事实与其接受时 sequence；200 |

所有 DTO `extra=forbid`，ID/digest/version/reason 使用 §3.3 限额，reuse 既有 HTTP constraints 的
公共类型；request body duplicate JSON keys 不得悄悄覆盖。Start 不允许 `force`、policy override、
fault injection、Repository fields、arbitrary confirm flags；references 必须由本服务审计事实解释。
`PreviewArchivePlanResponse` 不包含 durable `plan_id`；Start response 不包含 `operation_id`。
GET history 和 legacy wire 兼容不在本 slice，Result 读取是当前真实审计 consumer。

### 8.2 Stable error mapping

采用 owner-owned `{code,message,details?}`，不建立 Shared Kernel error registry。

| HTTP | Code / 行为 |
| --- | --- |
| 401 | 沿用 `AUTHENTICATION_REQUIRED`：session 缺失、过期、无效 |
| 403 | `SCOPE_FORBIDDEN`：权限不足、disabled/missing mapping、跨 scope ref；不得泄漏他项目对象 |
| 404 | `RESOURCE_NOT_FOUND`：已授权 scope 内无所查 ArchiveResult；未知跨 scope refs 统一不披露 |
| 409 | `IDEMPOTENCY_CONFLICT`, `BASELINE_VERSION_CONFLICT`, `CANDIDATE_SET_CONFLICT`, `CANDIDATE_BINDING_CONFLICT`, `ACTIVE_SUBMIT_ATTEMPT`, `ARCHIVE_AUDIT_VERSION_CONFLICT`, `ARCHIVE_CONFIRMATION_REQUIRED`, `ARCHIVE_ANOMALY_UNRESOLVED`, `ARCHIVE_CLOSED`, `WORKSPACE_OCCUPANCY_CONFLICT` |
| 422 / 413 | `REQUEST_VALIDATION_FAILED`（shape/enum/digest/重复引用等）/ `REQUEST_TOO_LARGE`（body bytes） |
| 409 | `ARCHIVE_SCOPE_LIMIT_EXCEEDED`：完整集合超预算，提示减少候选或 owner 评估容量，不返回可 Start 的部分集合 |
| 429 | 既有 `ADMISSION_LIMIT_REACHED` |
| 503 | 既有 `SERVICE_NOT_READY` / `DEPENDENCY_UNAVAILABLE`（busy/I/O）；`ARCHIVE_INTEGRITY_FAILURE`（本地事实不一致，停止该动作并记录 bounded 诊断，不自动修复） |

重读后 caller 可修复的 stale/binding 为 409；磁盘/数据库不可用为 503。Review 新闭包错误
`ARCHIVE_CLOSED` 由 Review HTTP mapping 明确公开，测试只补增量。日志不输出 raw request、secret、
SQL payload 或内部 pathname。

### 8.3 Wiring and deployment permission

production `create_app → http/runtime.py` 初始化/验证 control DB、seed、绑定 Archive dependencies、
注册 routes/errors/OpenAPI paths；仍使用 live session provider、readiness 与 admission-first shutdown。
Preview POST 为纯读无需 mutation key，但受既有读取资源限制；append/Start 进入 new-work admission。
同步 Start 不依赖 worker job registry 新条目，也不因为 worker 暂停创建 Archive recovery task。

后续授权实现时，在 `vnext/deploy/config/session.json` 的受控示例明确配置 `archive_submission`，
真实 session 文件由部署方授予目标 actor；不能给全部 session 自动追加权限。更新部署文档说明
permission、seed input 的 initial-only 语义及维护升级步骤。沿用 backend/worker control DB volume、
non-root 与 Repository 内网隔离；不加 Repository mount、Dolt binary、socket、UID/helper 或网络
访问。配置/wiring/启动语义及容器 harness 改动触发当前 HEAD 重建，实际 deployment 仍需另行授权。

## 9. Verification ownership

测试名字描述业务行为，不按 finding/轮次。下表为唯一权威 owner；其他层仅 smoke，不复制负面
矩阵。除 Compose 用真实提交外，Archive 本地测试使用有效冻结 Submission facts 与 SQLite，不
为纯 digest/validation 建 Dolt。Backend 单进程，时序/进程测试标 serial；不引入 xdist。

| 行为不变量 | 唯一测试 owner（相对 `vnext/backend/tests/`，除既有者均拟新增） |
| --- | --- |
| zero-table Repository materialization 的真实事实形状 | 既有 `test_repository_ref_materialization_hidden_summary.py` |
| empty checkpoint 合法恢复/缺损拒绝、两种模式 READY 与 baseline digest 同拓扑（Preview/Submit digest producer owner） | 既有 `test_preview_job_assemble.py` |
| empty pair 绑定、table addition / empty facts 的 Comparison 语义 | 既有 `test_comparison_planning.py` / `test_comparison_standard.py` 各管 binding / facts，不复制流程恢复 |
| 空 base canonical 无变更仍在 T1 前拒绝、有变更可接受 | 既有 `test_submit_transactions.py`；production digest adapter 接线由 `test_production_wiring.py` smoke |
| candidate 资格、canonical digest、selection/anomaly 推导；Preview 无写 | `test_archive_queries.py` |
| append/revoke sequence、exact subject validity、审计 replay/actor 策略；同 key 改 selected/集合 digest 的共享参数表，及 subject 过期后的合法 replay | `test_archive_audit.py` |
| Start 全事务 closure、Head/Workspace CAS、同 key replay、commit 前 rollback/commit 后丢响应 | `test_archive_transactions.py`（真实 SQLite；代表性故障点，不逐 SQL 注入） |
| AcceptSubmit/Review/Archive/audit 竞争的两种 commit 顺序 | `test_archive_concurrency.py`（同 DB 两条连接；覆盖语义屏障，不自建 schedule 平台） |
| v4→v5、fresh DB、失败 rollback、seed 重启不回退、旧 binary拒绝；迁移/seed/update 的跨 scope 共享和旧 Repository 再分配拒绝 | `test_archive_control_db_migrations.py` |
| HTTP scope/permission/body 限额、DTO/error、cross-actor replay 与读取；HTTP 与 Application 同表验证 ASCII/中文/四字节字符的 UTF-8 边界 | `test_archive_http.py` |
| 新 path OpenAPI schema | 既有 `test_http_openapi.py` |
| 真实 production factory 依赖、seed adapter、无 Archive job | 既有 `test_production_wiring.py` |
| 新依赖的公共面、反向调用/私有依赖禁止 | 既有 `test_architecture.py` |
| 正式 API 从真实 Submit/Review 到 Archive，再次 Preview 使用新 base；实际 Repository main/commit 集合无 Archive effect；重启后 Head 保留 | `test_archive_compose_e2e.py` |

既有 `test_review_transactions.py`/`test_submit_transactions.py` 等用于回归其 owner 的已有行为，
不重复托管 Archive 竞争矩阵。Compose 只做成功/重启/无 Repository 写的跨进程 smoke；精确事务
失败、scope permutation 在上述 owner 验证。关键 crash 用真实文件系统；tmpfs 不替代持久语义。

## 10. Acceptance and image evidence

docs review → 单独 implementation authorization → Execution Plan 分阶段实施/独立评审 → 最终
fresh-image conjunction → separate independent slice acceptance。作者不得自行写
`p5_5d_slice_exit: pass`。5D exit 不等于 5E、P5 整体退出或 production deployment 授权。

最终测试必须把 Archive journey 与现有 Review、Submit restart/journey、Backend CMD、readiness/
clean-stop 在同一套本轮 fresh images 下结合，所有必要场景 pass 且 0 skipped。需保存**运行中**
repository/backend/worker 的 `.Image` IDs，与构建后的不可变 image ID、revision/source-tree、
Compose config/五锁摘要关联；仅有 tag 或预构建 inspect 不能证明实际被运行。详见 Execution
Plan §6 的命令和证据预算。

## 11. Open decisions, conflicts and stop conditions

单 SQLite/零 Repository effect 的核心方向不变。四项文档 finding 已全部关闭；
Business Lifecycle §1A/§9A 已接受为 `3.0.0`，S1 Contract 前置已满足。
以下决策已作为设计接受，源码修复和实施验收仍由后续阶段完成：

| 事项 | 本文 accepted 决策 / 边界 |
| --- | --- |
| Repository 反向归属 | V1 不允许不同 device/project 共享或先后接管 Repository；migration、seed、update、history scope 检查一致。Business Lifecycle §1A/§9A 已接受为 3.0.0；S1 Contract 前置已满足，原 2.0.0 作为历史版本 |
| initial-empty 支持缺口 | S1 原 Preview/Comparison/Submit owner 完成 checkpoint 修复、完整 pipeline/digest focused gate 后才能跑 Archive journey；零行表 fixture 继续保留作回归 |
| Audit subject 与 actor policy | selection confirmation + 每 sibling exclusion resolution；无 TTL/双人制；任一授权 actor 可撤销尚未归档 subject。若业务要求改变，先改本设计与验收，再接受 |
| Anomaly producer | 当前真实业务损失是未选 approved 内容不进入 Baseline；只覆盖此 exclusion，不承诺整合未落地的通用 risk/validation issue。要求其他 producer 时明确 facts owner/稳定 digest/真实 consumer 后重评预算 |
| 初始 Baseline | 自动升级仅支持已登记 version=0 initial；无法证明的历史/非零 base 不猜测。部署示例不是实际 commit；现有 Compose fixture 的零行表 import 也不是 Repository 初始 commit 证明。真实环境 inventory 必须在 migration gate 确认；若实际 provisioning 使用非初始 commit，则与 P5 §4 冲突，先由 provisioning/contract owner 决策，不能靠 migration 把它标 INITIAL |
| Workspace release | 沿用现有 Review 可复用 OPEN Workspace 语义，清指针、保留 generation 和历史；不会隐式变 CLOSED。若要求归档后新 Workspace 生命周期，须 reopen Workspace contract |
| 资源限额 | 200 candidates / 256 KiB body / 100 audit page、ID/key 255 UTF-8 bytes / reason 4096 UTF-8 bytes 为 V1 具体预算；实施容量样本发现不够须修订预算，不可分页冻结部分 sibling |
| 现有 Head/mapping 耦合 | source 与目标 contract 的实现缺口，需同阶段修 migration、全部 reader 和两个进程 seed；不能宣称单独加 CAS 即可 |

出现 Archive 必须合并/新 commit/ref 写、持久 candidate/执行状态、跨 DB participant、外部 event
consumer、multi-host writer 或业务 Head 等同技术 main 等要求时，停止对应工作，列出与
Business Lifecycle/P5/External Effect 的冲突，由 owning Contract/ADR 决策后再继续。不能以
普通 finding 扩大同 euid 威胁模型或引入 broker/sidecar；没有真实 consumer 不增加 outbox。
