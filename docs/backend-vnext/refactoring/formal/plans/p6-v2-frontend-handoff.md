# V2 归档界面接口交接（Owner手动转发）

2026-11-07。协调者维护，前端 owner 实施其代码。**V2已本节GO，最终独审`9ec62e82ad`，产品/当前Compose`f8fb796f02`，handoff`3cd4400f9f`**。提前候选7878→完整3c→f8已收敛，subject按issue闭合并保留精确preimage。A1/V1亦已本节GO；04/05联合最终、BE-d完整tar与前端PAX同制品互通仍另待，不把本页视作FE3完成。当前没有等待前端判断的阻塞问题。

## 1. 预览与逐项接受

`POST /v1/archive-plan-preview` 保留 selected、candidate_set_digest、selection_subject_digest、blockers/can_start，新增 `business_validation`（rule_id、baseline_facts_digest、source_diagnostics、time_comparisons、issues）。各 anomaly 增加 affected_submission_ids、side、relations、details、detected_status、resolution_status、latest_sequence、accepted_by/accepted_at/reason。应分别展示原始诊断与处理状态；接受后来源仍可能 UNEXPLAINED，时间仍可能 NOT_COMPARABLE，不改为自然通过。

3c 完整候选的 `ArchiveIssueDetailsResponse` 是按 issue 区分的闭合 union：`ArchiveSourceIssueDetailsResponse`、`ArchiveTimeQualityDetailsResponse`、`ArchiveBaselineTimeDetailsResponse`、`ArchiveTimeRegressionDetailsResponse`、`ArchiveEmptyIssueDetailsResponse`。按 subject_kind / issue_code 渲染相应内容，最终类型从实际 OpenAPI 刷新；`audit.subject` 保留 exact preimage，不补无关null或自行补齐另一种issue的字段。此为7878提前包之后的具体结构细化，权限/业务流程不变。

新增异常分类与接受 action：

| subject_kind | 接受 action |
| --- | --- |
| CONFIGURATION_SOURCE | ACKNOWLEDGE_SOURCE_EXCEPTION |
| CONFIGURATION_TIME_QUALITY | ACKNOWLEDGE_TIME_QUALITY |
| CONFIGURATION_TIME_ORDER | ACKNOWLEDGE_TIME_ORDER |

沿 `POST /v1/archive-anomaly-resolutions`，每项填写明确 reason，保留 `REVOKE`。使用服务端返回的 subject_digest、issue_code、代表 target_submission_id/target_candidate_digest、当前 expected_sequence，以及同次预览的 Head、selected、candidate_set_digest；不要自行构造 affected 成员集合或将一组异常拆成多份接受。完整组/边由后端派生并冻结，candidate/facts/Head/selection/来源组改变后刷新预览及相应审计引用。

原 sibling 排除、project identity 例外与选择确认保留。`POST /v1/archives` 的 `confirmation_refs` 上限为 **1**，`anomaly_resolution_refs` 为 **1601**（候选仍上限200）；引用须无重复、精确匹配最新肯定 sequence。请求 body 上限仍262144 bytes。版本/sequence 使用0..9007199254740991的整数；不要将1601重新限制为旧共用200。

## 2. 有理由关闭、不归档

新增 `POST /v1/submissions/{submission_id}/closure`，使用 `Idempotency-Key` header。body 为 `expected_review_version`、`expected_baseline_node_id`、`expected_baseline_head_version`、非空 `reason`；只有当前 `archive_submission` 权限可操作，reviewer/self-only不自动取得关闭权限。

首次201，合法同键同请求重放200。响应含 submission_id、`disposition=CLOSED_NOT_ARCHIVED`、`source_kind=MANUAL_CLOSE`、closed_by/closed_at/reason、released_workspace_id、workspace_version。另一有权限操作者重放同一命令仍返回首次操作者/时间/理由；不同请求复用该key冲突。403权限、404目标范围、409版本/状态/占用/幂等冲突、422无效请求、413体积、429准入、503完整性/依赖，最终细分以实际OpenAPI/错误矩阵为准。

成功后保留 APPROVED 历史，工作区释放并清当前输入/Preview，需要重新上传和预览再提交；不会推进 baseline，也不会产生伪 ArchiveResult。此出口不要求先接受异常或候选图自然通过。关闭桥接提交后，其余来源可重新UNKNOWN，应刷新预览处理，不自动接受或级联关闭。当前 baseline 下 PENDING/active Attempt 的归档硬阻塞仍按 A1规则。

## 3. Review / History 统一处置

Review 的审核 status 继续显示历史状态，新增 required-nullable `submission_disposition` 对象，包含 submission_id、disposition、source_kind、result_id、closure（closed_by/closed_at/reason）。闭合处置与审核状态分别展示；手工关闭不是 WITHDRAW，也不是新的审核状态。

History 节点的 `archive_disposition` **直接替换为 `submission_disposition`**，无旧字段别名；增加 disposition_source_kind、disposition_result_id、closure。source_kind 区分 ARCHIVE / MANUAL_CLOSE；手工关闭的 result_id 为null，但已关闭，不能据null误判仍可归档。分页和完整树均采用新事实。Archive响应的 dispositions 也使用统一对象，只有真实ARCHIVE来源关联ArchiveResult。

## 4. 最终转发制品与证据

实际生产 `GET /openapi.json`（同一f8 Compose）副本：[openapi-f8fb796f02.json](/home/dev/gdds-v2-evidence/openapi-f8fb796f02.json)，SHA256=`e937a38e8073abebb406138e9be2ca2bd61eb25ac8fda9d9adabee56fd2abda1`。首次/重放、权限与错误边界按本页§2及实际schema；确认1/异常1601、History改名、Review required-nullable处置和closed union均已核实际制品。前端刷新自己OpenAPI快照/类型，本轮后端没有修改前端源码。

06真实异常拒绝→关闭→新上传补saved_time→新提交/审核→归档旅程1/0，生产镜像/provenance与资源释放由同角色独审核收；全部37运行/13附件索引：[evidence-index.json](/home/dev/gdds-v2-evidence/evidence-index.json)，SHA256=`cc505fe5a1a1776191a8ab599b7433784460a47f004fab2398e3459b9c611efb`。详细结果/失败保留和范围见[V2 handoff §6–9](p6-v2-handoff.md)、[最终独审 §11](p6-v2-review.md)。06于10:39:24Z释放，角色已结束；没有权威包carried或04/05完整旅程声明。

后续若需前端判断影响后端方案，协调者另给具体问题，等Owner手动转发回复；现无这类阻塞。D会另交真实生产encoder同字节tar及摘要，前端修PAX和同制品OPFS证据仍须其owner提供，后端GO不代替FE3。
