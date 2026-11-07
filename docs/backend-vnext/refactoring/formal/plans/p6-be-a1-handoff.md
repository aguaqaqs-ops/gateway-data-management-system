# A1 BE-a 实施交接

日期：2026-11-07。实施角色 `/root/be_a1_impl`，GPT-6.1-Sol/xhigh；协调者 `/root`，独审 `/root/be_a1_review`。起点 `8fbdcb7d54`，允许其后的协调文档提交。按 [A1 工作单](p6-be-a1-work-order.md) 与 [BE-a 设计](p6-be-a-design.md)实施，不办理联合 exit。

当前为首个代码候选，06 focused、五包静态/RS unit与受影响 Compose 取证待运行；不声明已通过。最后实际镜像来源仍为 S2b `a6876d5600`，RS source-tree `sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2`；本节修改实际 Compose 测试及 session 接线，触发06最终候选的受影响小型容器门禁，不做 carried。

实现与 consumer：

- Review domain、review application/transaction、HTTP review/history literals、control DB baseline CHECK 删除退回动作/状态/事件；同步 domain/transaction/HTTP/DB tests，删除已替代的旧并发与历史 proof。
- `review.py` 共用当前permission/持久created_by规则，粗粒度检查先于对象读取；事务内再验。仅本人身份在完整Review closure前校验。原project-wide actor-independent key/fingerprint完整性及原actor replay保留，成功 replay早于fresh baseline/state/occupancy门禁。
- Workspace service以整个transaction为输入，create/get结果带occupancy；route在单个写事务返回Workspace/version/occupancy。mapper/required-nullable DTO、全部直接服务caller及OpenAPI同步，不新增持久副本。
- Archive SQL有界读取helper分别取APPROVED与PENDING；missing projection/event或latest event分叉均进入closure验证。snapshot校验scope/Workspace/Attempt；candidates/preview增加pending IDs/count与`ARCHIVE_PENDING_REVIEW`，Start在自身写事务重查。active Attempt、唯一选中及完整sibling审计保持。
- fresh APPROVE在同写事务检查冻结node/commit，409 `BASELINE_VERSION_CONFLICT`；REJECT/WITHDRAW仍能处置旧PENDING。精确occupancy、Workspace CAS和失败回滚沿用。
- session示例区分self-only与reviewer；真实review Compose补self-only上传→撤回→再次上传，archive双actor旅程补两人PENDING预览/直接Start阻塞后审核并归档。

Owning正文同步：Business Lifecycle `4.0.0`、P5-5A Workspace HTTP、P5-5C授权/replay/状态机、P5-5D候选/受理与错误。历史DC及审核报告不改写。没有编辑frontend、前端文档、AGENTS、testing-conventions、benchmarks或冻结资源。

对外增量：Workspace两个指针必需但可null且互斥；`POST /v1/workspaces`新建201/已有200、`POST /v1/history-compares`首次202/回放200均声明实际response schema。GET review/WITHDRAW允许reviewer或self-only；self-only只读本人所有状态、只撤回本人PENDING；APPROVE/REJECT只reviewer。缺permission403，目标不存在/非本人/跨scope404，closure损坏503；新APPROVE过期409，archive pending409。本人权限不授予History/Archive列表。

唯一验证owner按工作单：HTTP权限/披露/replay与过期APPROVE；transaction完整性/CAS/释放；Workspace指针生命周期/一致快照；archive query/transaction/concurrency；OpenAPI创建schema；Compose仅真实接线smoke。具体命令、节点、候选HEAD/UTC/exit与日志SHA在运行后补入本页。

后续V1/V2/D仍待交付：时间/内容事实、来源规则/逐项接受、完整tar和有理由关闭。APPROVED不可本人撤回，本节没有恢复旧return出口。04联合权威runner与05 fresh t1留联合最终候选，本节不冒称完成。
