# S3 补测、S4 顺序例外与 Q18 并行计划独立审核

2026-11-08。审核对象：固定治理候选 `3180f61d462e56d1e42c5b55eeca80b5c79ed8ae`（父提交 `a1ca3bad93a25cb47384a81fbc985075b1299c39`），仅八份文档；最终治理文档候选 `c1c77a3c380b29639de18f4101a0b3b7918278e0` 的单行增量另见末节。本人在 clean detached worktree `/home/dev/gdds-review-s3-s4-parallel-3180` 静态阅读，已按仓库规则链接 `legacy/`；未运行测试、编译、lint、容器或节点验证。本报告只评价决策记录和新对话提示词，不评价 S4 产品实现或 Q18 节点结果。

## 结论

**DOCS CLEAR；无阻塞 finding。** 候选可作为 Owner 本轮决策记录及下一对话的 S4 补充设计任务提示词。S3 原 V=`774acf33a3f12eeccfbb440d9446ffde9c1c6d43`、H=`685c97f4e275e5e52b42ea403a07a5e96b0695b2`、最终审核 `0bf64540389e13b80735b483e1b9616bf8dca1e0` 的 `BLOCKED_CAPACITY` 未被改写；本结论不签 S3/S4 exit、性能 PASS 或 FE3c Q18 前置解除。

## 核对范围

| 边界 | 固定候选中的处理与判断 |
| --- | --- |
| 节点与证据 | `AGENTS.md`、`testing-conventions.md`、FE kickoff §6 统一为五个 32 vCPU / 64 GiB 节点；要求逐节点工具链/离线缓存就绪，按包 carried 及镜像等价保持来源节点和同一 worktree。历史来源不重写。所有有执行的任务取得本节点原子标记；`run-real-backend-e2e.sh` 自带获取时外层不重复。04/06/07 同宿主，正式样本同组同节点/配置/存储条件，跨节点实际干扰协调，符合 DC91。|
| 历史文件清理 | 计划仅允许确认归属、无 live use/保留消费者的派生文件进入逐项白名单，并记录删除与空间；明确保护 04 carried 来源 worktree、环境和当前镜像、引用的成功/失败原件、真实输入、冻结基准及 CT108 W3 私有归档。没有年龄批删或全局 Docker prune 的授权；本候选没有执行删除。|
| S3 容量 | 原 W3 在基线 v1 Submit 的 M24 操作预约失败，首次拒绝的 stage/requested/live 未知，后续 W3/W4 未测；低 RSS 不被用来改估算。临时大预算须先定位、固定参数与脚本并独审，另条件结果与原 N1/32-8/M24、同 worker 场景分列，符合容量停止报告与 DC92。|
| S4 顺序 | 执行计划只增加设计及 kickoff 独审之后可提前实施的例外；本对话只作决策和新对话交接，不启动 S4 设计、实施或测试。S3 不因 S4 倒签通过，S5 仍需 S3/S4 exit。新对话提示词明确 S1a `replay.sql` 逐字节、PATCH 1,000 行且 1%、256 行/4 MiB 完整语句、单行超限及 200 MiB artifact admission，保通用 planner/ChangeSet 的独立 consumer。|
| S4 设计缺口 | 提示词将 storage key/完整 persisted 列与前端 effective compare/facts 分开；要求按真实消费者决定旧实现删除，列出 SQL 顺序/编码、IPC/mmap/FFI 资源 owner、恢复/CAS、预算诊断和性能归因的未知及停止条件。S3-only、S4 与联合候选分开，角色最多四槽且实施/独审分离。|
| Q18 | DC93 与计划将 BE-Q18 作为独立归档接口补缺；目标为同一只读事务中从权威 review projection 给 archive-only 候选响应 `review_version`，不改 Review GET ACL、关闭 CAS、digest/fingerprint。固定候选 `a1ca3bad93` 当时尚无专用节点结果，文档没有宣称前端前置已解除；生成时间预期不混入此项。|

## 证据边界与交接

直接依据包括 `p6-s3-e-capacity-stop.md`、`p6-s3-candidate-handoff.md`、`p6-s3-e-review.md` §61–64、`p6-s3-coordination.md` §16、`p6-design.md` §4.3/§10、`p6-execution-plan.md`、S1a handoff 与 Storage Mutation Contract、FE3 kickoff Q18 及最新 FE3b 复审。审核期间 Q18 独审报告作为后续独立提交出现；本次固定候选对它只作“下一对话核最新结果”的交接，不把后续提交倒填为 `3180f61d46` 的验证事实。

`3180f61d46` 后，独立 Q18 审核报告提交为 `963b220f81`。随后 `c1c77a3c38` 仅将并行计划 §5 的现场快照从笼统的“Docker 容器均无”精确为“未见运行中的 Docker 容器”；本人按该提交的单路径 diff 静态复核，符合原只读审计范围，不改变其他治理决策或上述结论。最终 **DOCS CLEAR** 绑定 `c1c77a3c38` 的治理文档及本报告所述范围。

下一对话应按 `p6-s4-design-discussion-prompt.md` 先讨论并固定设计、交独立设计审核，再按届时授权决定实施；节点取证、清理与产品门禁仍需各自固定执行稿和实际证据。
