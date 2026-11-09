# S6 设计独审记录

状态：固定设计候选待审。审核者为本轮新建`s6_design_review`，非S5/E复用。
设计者不代签。这里只记录设计审查，不运行产品检查，不代替CODE/EVIDENCE/EXIT_GO。

## R0 基线原始结论

对象`c391524061f0ffbabc4fc95f3ceb713b1b99526e`，区间`p6-s5-exit..c391524`；只读clean detached `/home/dev/gdds-reviews/p6-s6-design-c391524061`，已接legacy。以下逐字保留审核者首轮最终回复：

> 固定基线 `c391524061f0ffbabc4fc95f3ceb713b1b99526e`，审核工作区 clean、detached，已接 legacy；未修改文件、运行产品检查或访问 CT。此轮为基线缺口核查，不签整体设计 GO。
>
> 1. **F1：现行 Contract 内部矛盾，应文档修正。**  
>    `comparison.md:138–156、313、603` 一概承诺 early exit 零 reader，并允许省略 ordered extension；`ordered-diff.md:325` 同样保留旧说法，但 `:377` 要求未变 ordered 按当前 pair 策略计算 current 单侧摘要。实际 `comparison/production.py:906–910、951–1004` 正是 current 单侧读取并填 ordered/blank extension，缓存命中恢复相同事实。建议限定 metadata-only 零读取适用任务，明确 ordered miss 单侧摘要、hit 恢复；无需改算法或 golden。另将 early-exit 完整条件对齐 `row_encoding.py:292–320` 的 schema/storage view/projection 等绑定，不能仅写 raw digest 相等。
>
> 2. **F2：已确认的 W1/W2 链路缺少现成 CLI scope，计划必须列出最小工具实现。**  
>    `real_dump_journey.py:4164、4568` 仅有 `full / t4-identity / t4-v1-submit`：前者继续 v2/History，后两者分别提前结束或跳往 v2。新增一个 fresh t4 W1/W2 scope，复用现有首次 Preview→Submit→read/approve/Archive→repeat Preview/Submit 后结束即可；唯一主要测试 owner 为 `test_real_dump_journey.py`。不能直接运行 `full` 再声称范围已收敛。
>
> 3. **F3：计时名称必须明确限制。**  
>    `_preview():1817` 在 POST 响应后才取起点；`_poll_operation():1702` 可将终态观察代作可读观察，间隔 2 秒。现字段只能报告“受理响应后→首次可读/终态代理”，不能称精确受理到 READY。若增加请求前单调时钟，只增工具字段并保留原口径，不回填历史数值、不构建 profiling 平台。
>
> 4. **清理核查：目前没有证据支持按模块名称新增删除。**
>    - `comparison/standard.py、ordered.py` 保有 metadata、degraded facts 和 envelope consumer。
>    - `tests/support/table_access_sql.py:10、86` 是 native parser 的测试适配，不是保留的 Python SQL parser。
>    - `mutation_planning/_planner.py、_changeset.py、contracts.py、_artifacts.py` 是 S4 明确保留的通用 planner/外部目标契约；`_digest.py` 另有 `external_target_sync/_ledger_digest.py` consumer。
>    - `_repository_replay_renderer.py:104` 已调用唯一 Rust renderer，是保留 facade，不是旧 SQL 算法。
>    - Python XML parser 与 Risk 控制流亦有现役 consumer，不能按语言清理。
>
> 等待固定 S6 设计候选后，我会按同一编号连续复核上述处置及整体范围、成本与最终 HEAD 门禁顺序。

## 设计者处置（不是审核结论）

F1直接统一owning Contract旧条文；F2在设计§4.2/kickoff I列具体scope/参数/停止点及测试owner；F3使用现观察字段并明确限制，不新建时钟机制。清理矩阵逐项保留真实consumer，无新增产品删除。正式固定候选审及后续原文在此追加；未审核前不签整体GO。
