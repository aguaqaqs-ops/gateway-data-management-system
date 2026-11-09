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

## R1 固定候选原始结论

以下为同一审核者原文：

**R1：HOLD（需文档小修后连续复审），不签整体设计 GO。**

审核对象：`d4b952c778a03899393c0f475fedc6f7d0ac45df`，区间 `p6-s5-exit..d4b952`。工作区 `/home/dev/gdds-reviews/p6-s6-design-d4b952c778` 为 clean detached，legacy 已接。只读核对文档、源码及引用；未修改文件、运行产品检查或访问测试 CT。区间含并行 FE3 文档合入，其验收不由本审代签。

- **F1 部分关闭，剩余一处措辞过宽。**  
  Summary Early Exit、ordered-diff 旧条款已正确区分 metadata-only 与 ordered 单侧摘要/缓存恢复。可是 `comparison.md:302` 新 provider 表写“ordered表保留ordered/blank extension”，覆盖面大于实际行为：`comparison/ordered.py::_compare_single_side` 对正常整表新增/删除返回 `ADDED_TABLE/DELETED_TABLE`，不产生上述 extension。应限定为两侧存在且适用 ordered 比较的任务，并明确不改变整表增删路径。只需文档修正，不能为了满足新措辞改产品或 golden。

- **F2 设计处置关闭；产品实现仍未执行。**  
  新 `t4-w1-w2` scope、fresh/MODIFIED_ONLY 约束、repeat 后停止、无变更 mutation/main/head 断言和唯一测试 owner 已明确。小修：设计§4.2 的 `_run_dataset` 应为实际 `_run_tier`（`real_dump_journey.py:2967`）。

- **F3 设计处置关闭。**  
  已准确限定受理响应后起点、2秒轮询、首次可读/终态代理，明确不冒精确 READY、median 或同条件提速。BE-c 将 READY 前组装与 GET 封装/发送分开，范围和限制充分。

- **F4 新增：计数和独立预期来源尚未具体到可执行，阻塞设计整体 GO。**  
  `kickoff:28–31`、设计§4.2目前仅写“现指标”“已有独立代表预期”“必要工具采集在I/II固定”。实施者仍需决定关键验收如何成立。应补一张紧凑来源表：
  1. `pair_pipeline.py` 的 `s3_pair_metrics` 按真实 operation/pair 归属，分别消费 kernel、ordered、restore、records validation、rebind；不能拿 `native input_reads` 当 Dolt 请求。
  2. W2 **逻辑基线需求**与**实际RS行请求**分开。明确前者的既有 owner/断言来源；后者指定限定业务窗口的 access 日志、完整性和正校准依据。无法观察的字段保持 UNKNOWN，并明确是否由既有测试证明承担，不临场把缺日志解释为零。
  3. 写明标准 datasets/census 和 S4 已核独立旧源 expected 的具体归档入口/固定版本及摘要，明确完整 catalog/schema/count与代表 keyed/ordered/keyless/composite 的各自来源、SET 逻辑映射规则。若既有材料不适用于本轮 t4 v1，先停止补来源，不能从新结果生成 expected。

其他已核：三项 Owner 收敛决定落实；最终六包实跑和最终 H 本机重建/容器要求保留；外置结果避免自身 SHA 循环；未知与取消项没有变为 PASS；N1/M24、节点池、离线规则、DC68 与角色新建规则一致；清理矩阵保留有真实 consumer 的 Python 职责，未发现需要新增产品删除的证据。

另建议将总设计§1.1仍直接写“规模2×t4…完整场景”的目标句标明历史背景并指向§12现行范围，以免只读摘要者误执行旧矩阵。现§16已有明确覆盖声明，此项为非阻塞一致性修订。

### 设计者R1修订

收窄provider表到两侧有效ordered任务，整表增删不要求extension；订正`_run_tier`；设计§4.2.1固定datasets/census、旧B独立oracle及SET摘要、分层计数与实际HTTP正校准、缺失停止规则；kickoff链接该表；总设计目标句明确历史背景。待原审复核，不自签关闭。
