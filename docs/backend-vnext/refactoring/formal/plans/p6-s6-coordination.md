# Phase 6 S6 设计协调记录

日期：2026-11-09。当前仅设计授权，未执行产品/测试/编译/镜像/原型/测量/清理，不push、不创建exit tag。

## 当前基线与交接

起点 main `c391524061f0ffbabc4fc95f3ceb713b1b99526e`，工作区 `/home/dev/gdds-s5-design-main`；clean现场及S5退出tag/原件摘要已核，产品树与S5 V2/H一致。当前文档候选由本页提交之后的Git HEAD解析，不写自身SHA。

入口：[设计](p6-s6-design.md)、[kickoff](p6-s6-kickoff.md)、[独审](p6-s6-design-review.md)。最终执行仍待设计独审及Owner实施确认。

## Owner本轮确认（原答复）

1. “采用真实 t4 最小收口（推荐）”：W1/W2为真实t4 N1/M24首次Preview→合法Submit/审批/Archive→原样重传Preview/无变更Submit，一次各项；替换旧2×t4与一暖三测，不自动升M40。
2. “采用现有完整包＋顺带采集（推荐）”：BE-c复用保存完整tar，实际bytes与理论1Mbps下限，新真实场景顺带完整GET，不补模式/规模矩阵，无下载性能退出门槛。
3. “采用以上收敛范围（推荐）”：保N1取消1–32线程曲线，不重复t1–t4全旅程/§16.3全矩阵；存储基于已有来源，门禁时长取最终runner分项，不重跑V8；保最终六包及最终HEAD容器、已确认t4，具体故障定向处理。

这些决定只改变设计与后续验收范围，不是执行许可，不将历史取消/UNKNOWN/失败写PASS。总设计/执行计划/Owner决议同步本轮范围，历史原审原件不改写。

## 缺口与角色

新建本轮独审`s6_design_review`，固定起点只读detached `/home/dev/gdds-reviews/p6-s6-design-c391524061`，legacy已接；初核F1旧early-exit Contract冲突、F2缺最小scope、F3响应后观察不能冒精确READY。原始结论见review，后续同一原审连续复审固定新候选。

协调者持续。未来每个新实施小节新建实施/独审/唯一测试等待角色，最多4活跃含协调，不递归扩队、不跨节复用；当前不创建实施/测试角色，不继承历史临时模型授权。

## 当前风险与下一步

- t4 M24当前完整最小链尚未验证，若预算拒绝需具体讨论，不能移用S4 M40。
- 真实计数须有实际来源，缺日志不是0；已有响应后计时保原观察标签。
- 当前无证实需新增删除的产品对象；通用外部目标planner、XML、risk与native测试适配有consumer。
- 设计完成前独核Contract修正文义、最小scope/停止点、独立预期和最终HEAD收口顺序；实施者只按明确scope执行，不自行扩大真实范围。
