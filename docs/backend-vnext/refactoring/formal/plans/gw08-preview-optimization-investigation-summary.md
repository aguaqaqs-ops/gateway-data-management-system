# Preview 全阶段优化决策调查总结

日期：2026-11-14。

**完成：**基于规则修复后的固定产品基准，调查 Preview 全链路并完成独立集中分析。推荐仅把 bundle 同一 source 或 final 校验屏障内相邻的第二次定位作为局部纸面设计入口：保留完整字节校验、不同阶段的验证、新写对象读回及 READY 保护。收益未知，尚不批准实施。旧空 baseline 的 annotation 发布量与约 22 秒 risk 不适用于现行规则；首轮 bundle 成员复用已包含。其余阶段保持现状，未选方向不自动转交。

**偏差：**Astra 核查测试节点既有归档时未取得节点占用；未写改原件内容，可能更新 atime，未核执行时空闲。原始观察与流程偏差均保留，不作为新的合规运行或门禁。调查发现 replacement 成功路径存在重复 export 调用，但旧三次 FULL 样本未覆盖该分支，不能据旧时间估算收益。

**验证：**本轮只读调查，未运行测试、构建或真实 Preview；不构成正式代码独审或阶段验收。此前业务修复的全量 runner、容器及真实旅程仍为 deferred。原始证据、适用性、失败与未知见[交接区证据索引](/home/dev/gdds-stage-exchange/gw08-preview-optimization-investigation/EVIDENCE-INDEX.md)。

**遗留：**如后续考虑实施，先核公开调用方、adapter、错误与保护语义，再判断局部成本是否值得；不成立或收益不足则保持现状。新增真实 Preview 额度为零，任何新真实运行须 Owner 另行确认输入、模式、次数和目的。完整结论及条件性问题单见[综合报告](/home/dev/gdds-stage-exchange/gw08-preview-optimization-investigation/REPORT.md)。
