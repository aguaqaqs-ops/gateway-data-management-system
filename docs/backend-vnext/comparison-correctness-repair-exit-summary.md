# 比较正确性与审核结果复用修复：交付摘要

产品与验收固定候选：`ef98a6045ff85fbaef3e2e4af2f89add953a6239`；本摘要为其后的文档提交。实施保存在独立提交链中，未推送、合回 main 或部署。

A 修复 History 单侧表冷/热缓存语义；B 对 12 类配置表分离存储键与比较键并提供行级差异；C 以严格证据控制纯结构变化的展示并保留审计；D 审核读取提交绑定的不可变 Preview 结果，涵盖权限、保护移交、FULL/MODIFIED_ONLY 和结果缺损时的处置；F 统一后端空页签标记和非空汇总。逐节审核及 finding 修复复审完成，前端外部审核关闭；E 全范围审核无未关闭阻断，见 [最终审核](e/final-review/review.md)。同家族 Sol 实施与审核依 Owner 本任务例外执行。

04 上 `ecb53090ee5374280cd711b2ad2236c9577465aa` 阶段 gate 通过：backend 实跑 4980 并行及 129 串行，容器门禁实跑，Rust 沿用合格的 `66f5b909ca80e7a35ae7db158ea64071242e03ce` 实际运行。此为 ecb 的原始证据；最终候选的包与容器结论以阶段门禁脚本结果为准，不手工沿用。

05 上 `dacbfeae6a2a58088548e49c95ef558a44e50962` 对两个代表表执行真实 History 逐键冷 miss/store、热 hit 补证，334/9822 行、整表新增及冷热一致性成立。原 t4 的全表缓存断言失败保留，Owner 接受新隔离副本补证作为例外，见最终审核。

`ecb53090` 的 number1 FULL Preview/Submit 成功但验收入口误读诊断键而 exit 1，原失败及现场保留。`ef98` 离线重放原始产物并完成结果断言，另在隔离副本执行一次 REJECT，核对结果、审计和保护保留；原现场仍 PENDING，不能称原入口通过。Owner 已接受派生副本证据并决定不重跑完整旅程。

05、06、07及04本任务节点占用已释放；Owner指定D/F外部审核树已回收，其他失败现场保留。未采独立实时 Docker HostConfig/profile 快照；保留启动 cgroup guard 与容器身份，不作性能/容量结论。backend/worker Compose revision 标签为默认 unknown，不冒称 HEAD。其他非阻断观察和原件索引见最终审核。
