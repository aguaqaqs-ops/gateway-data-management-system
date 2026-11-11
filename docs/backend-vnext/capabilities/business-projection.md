# Business Navigation

BE-b 以单份 `backend-vnext/business-navigation/v1` 替代旧五份 business-projection 设计。每个成功 pair 必须恰好一份导航，五个固定组按顺序认领表；共享表使用双侧集合谓词。replacement 在同份产物中按侧独立构造，不跨数据集对齐。

正式形状、十二个稳定诊断、局部 facts/table_scope、筛选类型资格、完整性证明与降级见 [Business Navigation Contract](../contracts/business-navigation.md)。B2 提供纯 producer/validator 与参数化测试；B3/B4 承接实际 flow、projection refs、发布闭包与 golden。旧五产物、UNPARSED_TABLES、单值筛选和无导航自动平铺均不作为兼容目标。

`capabilities/business_navigation` 只消费 comparison/risk owner 的事实，不重做比较或风险算法；共享表每侧线性扫描，无变化时复用 current 计数。资源由原 operation 的 M/checkpoint 提供。复合信号只认领 `composite_signal_point` 的一个整表页签，并对其他共享测点按地址 65532 筛选；不生成 points/formulas 产物。
