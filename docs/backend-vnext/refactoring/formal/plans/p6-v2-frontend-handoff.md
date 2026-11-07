# V2 归档界面接口交接（Owner手动转发）

2026-11-07。协调者维护，前端 owner 实施其代码。**当前为固定接口候选 `7878e41ad3`→完整候选 `3cce25c72a` 的提前交接，V2 尚未独审 GO**；后者将subject正文细化为按issue闭合的DTO、保留精确preimage，本页公开流程/字段要点相同。后续修复、最终 OpenAPI 制品/摘要及证据确认后更新本页。A1/V1 已本节 GO；BE-d 完整 tar 与前端 PAX 同制品互通仍另待，不把本页视作 FE3 完成。当前没有等待前端判断的阻塞问题。

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

## 4. 最终转发补件（待）

待固定V2最终候选：实际生成OpenAPI文件及SHA、权限/错误矩阵、06必要生产旅程及同角色独审报告链接。提前接口来源为 `http/schemas/archive.py`、`archive_business.py`、`history.py`、`review.py` 及 archive routes；此页没有运行或宣称公开接口已通过验收。后续若需前端判断影响后端方案，协调者另给具体问题，等Owner手动转发回复；当前实现不以沉默作确认。
