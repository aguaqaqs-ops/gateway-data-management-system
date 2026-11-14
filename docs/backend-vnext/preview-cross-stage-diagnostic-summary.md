# Preview 跨阶段诊断总结

本轮比较 canonical、table export、risk、business presentation 和 comparison cache 的实际工作。建议下一步只设计 risk annotation 发布与闭包校验的局部调查：同一 content 和 manifest 在逐件发布后验证，闭包阶段又验证；先判断能否在保留完整保护、错误和最终校验屏障的前提下减少重复工作。未实施优化，也未证明可节省多少。

一次普通 FULL 的业务结果和完整 scoped 内容对照通过；risk 空侧成本主要落在发布及校验，而非规则计算。逐表关联显示 export 的少数大表转换成本可见，但行数不能单独预测耗时或证明并行安全。本轮保持串行，不设阈值。

与计划的偏差：容器日志分块把时间戳插入一条 risk 表观测字段名，该条不能用于表关联；其余关键指标及业务对照仍保留原件。资源利用率统计仍不完整，不能判断 CPU、磁盘或内存瓶颈。一次 FULL 是单样本，不能声明稳定提速、容量或 08 实测。

验证：必要 focused、五包静态检查、一次 FULL 的完整业务对照通过；历史失败和上述未测限制如实保留，见[验证原件](../../../gdds-stage-exchange/gw08-preview-cross-stage-diagnostic/gate/)。未做正式独审、阶段放行、部署或推送。后续若无法保留校验与保护边界，或无法减少实际工作，应停止该候选。
