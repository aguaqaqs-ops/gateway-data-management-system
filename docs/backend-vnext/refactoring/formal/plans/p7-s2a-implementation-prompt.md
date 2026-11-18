# P7-S2a 新会话实施入口

Owner 于2026-11-11授权新会话按已审计划连续推进S2a A–F至本地exit；仅实质阻塞暂停受影响工作等待回复，其余自主推进。本会话只准备提示词和登记授权，未开始产品编码或测试。

完整任务提示词按现行流程放仓库外：[S2a A–F实施提示词](/home/dev/gdds-stage-exchange/p7-s2a/prompts/p7-s2a-implementation.md)。新会话选择 `gpt-6.1-terra` / high，完整读取后执行。每包实施 `gpt-6.2-sol` / high，独审 `gpt-6-astra` / xhigh（复杂判断可max）；新上下文与风险规则按main AGENTS，F新独审覆盖全阶段。不创建专职测试/监视agent；实施者做focused，协调者触发CI阶段门禁。现有门禁脚本固定04，其他验证按获准资源池现场选择。

正式输入：[详细实施计划](p7-s2a-execution-plan.md)、[S2设计](p7-s2-design.md)、[S0最新授权§14](p7-s0-owner-decisions.md#14-s2a-实施至-exit-授权与-ci-分工2026-11-11)。设计GO绑定 `d7345b211c603f698129e2f6660a0120d0fd038f`，见[最终Astra审核](/home/dev/gdds-stage-exchange/p7-s2a/reviews/readiness-finalization.md)；此后仅授权/状态引用调整不冒称属于旧文件摘要，也不重做无变化技术设计全审。源码增量仍在实施前核实。

授权覆盖S2a实现、必要验证、正常修复复审、本地提交及条件满足后的本地附注 `p7-s2a-exit`，不push/上线、不提前实施S2b。双worker 16GiB测试档和DC33具体真实范围仍须在准备时集中落实适用确认；不要求新增/扩容节点，也不因等待运行确认停止无依赖编码。CI承担门禁执行与证据归集，不能替代独审或未执行的真实数据旅程。
