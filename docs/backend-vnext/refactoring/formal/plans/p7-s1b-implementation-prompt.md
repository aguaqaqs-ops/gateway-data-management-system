# P7-S1b 新会话实施入口

Owner 于 2026-11-11 授权新会话连续完成 S1b A–F 至本地 exit；每小节创建新实施/独审上下文，只有真实阻塞才等待回复。当前会话仅准备实施输入，未运行产品测试或实施代码。

完整任务提示词按现行流程放仓库外：[S1b A–F 实施提示词](/home/dev/gdds-stage-exchange/p7-s1b/prompts/p7-s1b-implementation.md)。新会话选择 `gpt-6.1-terra` / high，再完整读取该文件执行；实施者 `gpt-6.1-sol` / high，独审 `gpt-6-astra` / xhigh（复杂判断可 max）。不创建 Luna/max 或其他专职测试角色；focused 由实施者完成，自动门禁由协调者触发。

正式输入：[详细设计](p7-s1b-statistics-and-query-design.md)、[实施计划](p7-s1b-execution-plan.md)、[S0 最新授权 §11](p7-s0-owner-decisions.md#11-s1b-实施至-exit-授权当前角色与暂停资源2026-11-11)。当前文档核收结论与 SHA256 见[最新 Astra 审核](/home/dev/gdds-stage-exchange/p7-s1b/reviews/design-workflow-rereview.md)，旧 GO 仅绑定旧稿。角色依据 main 的 P7-D26/D27 及 BE-b 执行计划 §2，不沿用早期 S1a 三角色模板。

授权包含必要实现、验证、修复复审、本地提交和满足条件后的本地附注 `p7-s1b-exit`，不包含 push、部署或 S2。暂停时可保留本人合法持有的必要资源；自动门禁正常收尾及恢复前现场核对不变。实际真实输入/节点仍按 DC33 一次确认，不影响其他已授权实施推进。
