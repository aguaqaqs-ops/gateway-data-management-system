# Comparison / Bundle Migration Execution Plan

本文是 comparison / bundle 后续迁移的临时执行台账。它不替代
`contracts/comparison.md`、`contracts/comparison-surface.md`、
`contracts/comparison-bundle.md`、`contracts/risk.md` 或相关 capability 设计；
它只记录接下来如何把旧实现中的业务语义迁移到干净的 vNext data surface。

## Scope

本阶段只处理 comparison / bundle / Workbench data surface：

- 抽取旧实现中的业务语义 oracle，包括转发通道、二次装置、通讯规约、ordered table、risk/sidebar/projection。
- 收敛正式 `ComparisonBundle` / `ComparisonSurface` contract，使 history compare 和 upload preview 最终都能消费同一类正式 data surface。
- 保持能力层 flow-neutral，不把 upload、submit、archive 或 history compare 状态机写进 comparison/bundle capability。

本阶段不处理：

- archive / formal flow / session permission / operation gating。
- 旧数据兼容、旧 OPFS record 迁移或旧 route consumer 迁移。
- 恢复 history workbench legacy path、`workbench_bundle_download` 或 preview-compatible history sidecar。
- Dolt immutable ref、archive execute domain flow 或 frontend archive journey。

Upload preview sidecar 暂时保留，因为当前正式预览仍依赖该读取路径；它是后续 bundle/data-surface cleanup 的边界，不是 history compare 或 formal flow 的兼容层。

## Principles

1. 旧实现只作为业务语义 oracle，不作为 vNext runtime fallback。
2. 旧字段名、旧 sidecar、旧 Workbench shape 不自动进入新 contract；必须逐项标注来源、迁移目标和保留/改名/废弃结论。
3. capability 输出应表达业务事实和展示事实，而不是表达某个前端组件的临时布局。
4. 大表 diff、risk 计算和 frontend Workbench 可以分阶段落地，但每个阶段都必须保持 contract 边界清楚。
5. 非兼容重构优先保证架构干净，不为了旧数据或旧代码路径保留额外分支。

## Slice Plan

| Slice | 名称 | 目标 | 非目标 | 验收口径 |
| --- | --- | --- | --- | --- |
| 1 | Oracle audit | 盘点旧实现语义来源，形成 mapping 表和手工 oracle cases。 | 不改 runtime，不优化算法。 | `comparison-bundle-oracle-audit.md` 覆盖转发通道、二次装置、通讯规约、ordered diff、risk/sidebar/projection。 |
| 2 | Formal bundle/surface contract | 固定正式 bundle layout、surface schema、artifact closure、Parquet row artifact 和 metadata 小 JSON 边界。 | 不做前端视觉重构，不引入旧 sidecar。 | history compare / upload preview 的 data surface contract 能表达多 pair、业务分组、risk、diagnostics。 |
| 3 | Business projections | 在 vNext capability 中实现转发通道、二次装置、通讯规约等业务 projection。 | 不直接复用旧 workbench runtime module。 | projection fixtures 与 Oracle cases 一致，frontend 不需要解析 SQL 表名来猜业务组。 |
| 4 | Large ordered diff / row diff | 处理 IEC104 ordered families、大表 row artifact、degraded/unsupported 语义和性能诊断后续优化。 | 不把流程问题混入 row diff 算法。 | 大表 diff 输出稳定 records/risk，degraded 情况可解释且不产生无意义重耗时。 |
| 5 | Risk annotations | 收敛 table-level、row-level、projection-level risk annotation contract。 | 不把旧 risk report shape 原样迁入正式 contract。 | risk 能在 table、row、secondary device projection、sidebar summary 中一致聚合。 |
| 6 | Frontend Workbench | 前端只消费正式 bundle/surface/projection/risk，完成多 pair 切换和业务视图展示。 | 不恢复 legacy Workbench download 分支。 | history compare 和 upload preview 的 Workbench 共享正式 loader 与只读展示模型。 |

Slice 2 的 contract 收口方案见 `comparison-bundle-formal-contract-scheme.md`。核心原则固定为：Surface 做轻索引，Projection 表达业务导航，Records 只存 row diff，Risk 表达风险事实和聚合，Bundle 只负责闭包和可下载边界。

## Pause Conditions

遇到以下情况应暂停讨论，而不是继续堆兼容分支：

- 旧实现语义与当前 vNext table rules / risk rules 发生冲突，且无法判断哪个更符合业务事实。
- 某个业务规则依赖旧 preview sidecar shape，迁移后会污染正式 `ComparisonSurface` contract。
- 需要新增 flow/API 状态才能表达 data surface；这通常说明 scope 误入 archive/formal flow。
- 大表 ordered diff 诊断显示问题在算法复杂度或数据结构，需要单独性能 slice，而不是在 projection/risk slice 顺手修改。
- 前端展示需要的字段无法由正式 bundle/surface 推导，需要重新确认 contract，而不是在组件内解析旧字段。

## Slice 1 Acceptance

- 新增 `comparison-bundle-oracle-audit.md`，列出旧实现语义来源、业务规则、新 vNext 目标落点和迁移结论。
- 首批覆盖：
  - `b{board}_n{link}_iec104_*` 转发通道 family、通道 label、board/link/protocol 解析。
  - `device` 与 `device_st/mx/co/sg/sp/cnt/sn/tap/other/disturb/cfg` 的 `dev_addr` / `gid` identity。
  - `net_cfg`、`prot_list`、`*_cfg`、`*_dev_cfg`、`dev103 -> nr103d` alias。
  - forward、secondary device、communication protocol、global parameters、unparsed 表分组。
  - table-level risk、row-level risk、secondary projection risk aggregation。
  - IEC104 ordered families、`gid/no`、pseudo blank、degraded/unsupported reason。
- 不改正式 runtime，不新增正式 contract 字段。

## Current Status

- Slice 1 已启动：旧实现语义盘点作为 Oracle，不作为 runtime fallback。
- Slice 2 方案已固定：正式 bundle/surface 使用 projection refs、risk refs、diagnostics refs 和 Parquet row records；不保留 history workbench legacy path 或 JSONL 正式 records 分支。
- Slice 3 已进入 Business Projection Core：先实现 flow-neutral projection capability 和 surface model 预留，不接前端、不写 bundle tar projection artifacts、不删除 upload preview sidecar。
- Slice 4 前置检查已新增 actual-data oracle runner：
  `gateway-data-management-system/backend/tools/comparison_oracle_compare.py`。
  当前只用 `business_large/large -> business_large/large-1` 对比旧
  `FormalTableCompareEngine` oracle 与 vNext comparison core；报告输出在
  `docs/_tmp/large_to_large1_oracle_compare.{json,md}`。
- `large -> large-1` 当前 oracle 结论：共同覆盖 137 张表，155 张表仅
  vNext 覆盖；共同表中 12 张 `b1_n*_iec104_syx_list` 旧实现输出 ordered
  records，vNext 判定 `ORDERED_AMBIGUOUS_MOVE_PLAN` degraded；`device_cfg`
  旧实现为 unchanged，vNext 输出 258 delete + 258 insert。这两个差异应作为
  Large Ordered Diff / Row Diff 和 device business identity/key rule 后续输入。
- Formal flow、archive、history compare route、operation polling 和 compat deletion 已完成到可继续 data-surface cleanup 的状态。
- 剩余重点从流程控制转向 comparison/bundle 的业务 projection、diff artifact、risk annotation 和 frontend Workbench 展示。

## Actual-Data Oracle Difference Triage

本节固定 `business_large/large -> business_large/large-1` 的旧实现/vNext 对比结论。
它只用于定位差异和安排后续 slice，不代表要把旧实现作为 runtime fallback。

- 历史覆盖结果：table union 292，common table 137，旧 preview/oracle 未展示而 vNext core 可计算的空 unchanged 表 155，missing in vNext 0。
- 覆盖差异结论：这 155 张表属于 surface visibility 策略问题；comparison core 保留全量表 facts，formal surface 过滤空 unchanged 表，不再把过滤结果作为前端统计展示。
- 共同表差异分类：13 张 common-table mismatch 中，12 张是
  `ORDERED_PLANNER_POLICY`，1 张是 `DEVICE_CFG_IDENTITY_POLICY`；未发现 missing-in-vNext。
- Ordered syx 结论：12 张 `b1_n{3,4,7,8,11,12,13,14,15,16,17,18}_iec104_syx_list`
  旧实现均输出 `BLANK_INSERT_INTERVAL=1`、`DATA_INSERT=5`、`MOVE=3`，vNext 均因
  `ORDERED_AMBIGUOUS_MOVE_PLAN` 进入 degraded。planner input 显示这些表约 9822/9828 行，shared real keys 约 8828/8829，position changed 7，topology core size 12；旧实现 backbone planner 可选择 3 个 move keys 并 replay exact，vNext 当前 single-move 判据过窄。
- `device_cfg` 结论：旧实现为 `UNCHANGED`，vNext 为 `MODIFIED` 且输出
  `DELETE=258`、`INSERT=258`。raw primary key `no` 在前后两侧各自唯一但完全不匹配；`gid` 前后 distinct set 相同但只有 6 个 distinct value 且重复。候选原因是 raw PK 不稳定、update-only unmatched rows 输出策略不同、业务 identity 可能需要基于 `gid` 加额外 disambiguator 或 projection/business-equivalent 判据。

后续推荐拆分：

1. **Ordered SYX Backbone Planner Alignment**：迁入干净的 backbone planner 能力或等价 formal planner，至少覆盖当前 12 张 syx 的 3-move + blank insert + data insert exact replay；保留 degraded fast-path，但不要把可解释的 ordered case 降级。
2. **Device CFG Identity / Update-only Alignment**：重新定义 `device_cfg` 的 compare identity 和 update-only suppression。需要明确 raw PK `no` 是导入序号还是业务 identity，`gid` 重复时是否要组合其他列形成业务 key，以及 business-equivalent unchanged 是否应压制 delete/insert records。
3. **Coverage Policy Decision**：空 unchanged 表已作为 formal surface 展示策略处理。comparison core 可以继续计算全量表，surface/frontend 决定空表、unchanged 表和 unparsed 表如何展示。

## Surface Visibility / Ordered Backbone Implementation Notes

- 空 unchanged 表策略已收口为 surface visibility 内部过滤：comparison core 仍保留全量表 facts；formal surface payload 的 `tables` 只包含可见表，不再发布 `hidden_tables`、hidden count 或 hidden reason 统计。
- `SurfaceSummary.table_count` 表示 visible table count。business projection 的 `UNPARSED_TABLES` 只接收可见表集合，不消费 empty filtered tables。
- Ordered planner 已接入 vNext backbone planner seam：unique single-move 失败后，在 topology core 预算内生成 backbone candidates，选择唯一最佳 backbone，再复用现有 semantic ops、blank interval synthesis、replay validation、Parquet records 和 risk 规则。
- 仍保留 degraded fast-path：candidate 超预算、多解无法唯一选择或 replay 失败时继续 `ORDERED_AMBIGUOUS_MOVE_PLAN`，不写误导 records。
- UPDATE_ONLY scope 已正式化：standard diff 先构造 raw records，再按
  `artifact_scope=UPDATE_ONLY` 抑制 row-level insert/delete，只保留 update records。
  suppression 后无业务 records 时，vNext 使用 `BUSINESS_EQUIVALENT` 表达 raw 有变化但业务 diff 为空。
- `device_cfg` 不再作为 table-name 特例处理；它通过通用 UPDATE_ONLY 规则收敛 raw primary key churn。
  后续只保留二次装置 projection identity 的展示细化，不再把 large 样本中的 `device_cfg` 差异视为 comparison identity bug。
- Risk Annotation Contract Baseline 已进入正式后端 contract：risk facts 消费
  `ComparisonTableFact.row_change_stats` 与正式 records artifacts，UPDATE_ONLY suppressed
  insert/delete 不生成风险，`BUSINESS_EQUIVALENT` 默认无 risk annotation。
- Standard/device point risk 对齐旧 oracle 语义：standard insert/delete/update 输出
  `STANDARD_INSERT`、`STANDARD_DELETE`、`STANDARD_UPDATE`；二次装置点表 name-only update
  输出 `DEVICE_POINT_NAME_UPDATE` low risk，非 name 内容 update 输出
  `DEVICE_POINT_CONTENT_UPDATE` medium-high risk。
- Ordered/degraded risk 保持正式 records/facts 驱动：ordered records 继续输出 move、
  replacement、middle/tail interval、name/content update 等风险；degraded/unsupported 表输出
  UNKNOWN review-required risk。projection-level risk aggregation 与前端展示增强留到后续 Workbench slice。
- Business Projection Surface/Bundle Integration 已完成后端闭环：upload preview 与 history compare
  formal flow 在 surface finalize 前生成 pair-local business projections；`ComparisonSurface`
  只暴露 `projections/{projection_id}.json` refs 和轻量 summary；bundle 写入
  `pairs/{pair_id}/projections/*` projection payload 与 diagnostics。
- Projection 输入默认加载 `net_cfg`、`device`、`app_cfg` 行，其它表作为 metadata/existence
  参与导航、candidate resolution 和 unparsed 归类；hidden empty unchanged tables 不进入
  `UNPARSED_TABLES`。二次装置 projection 首项发布 `device` metadata tab（装置总表），
  通讯规约 projection 首项发布 `net_cfg` metadata tab（网口配置表），普通二次装置 item
  的 change/risk 只由其业务 tabs 汇总，不混入 `device` metadata 主表；共享测点表按
  `dev_addr`/`gid` 拆分到具体装置 item。全局参数 projection 按
  `project`、`prot_list`、`app_cfg` metadata、`app_cfg.table_cfg` 派生目标表的顺序生成 item。
  `app_cfg.table_cfg` 派生只引用同一 visible surface 中存在的表，空表名、缺失目标、filtered
  target 或重复 target 只产生非阻断 diagnostics，不影响 bundle READY。前端继续通过
  `comparison_surface.projections[]` 读取 formal business projection artifacts，不新增接口或恢复
  legacy sidebar DTO；projection-level row-risk 精确匹配继续留到后续 slice。
- Frontend Formal Surface UI Coverage 已覆盖 baseline：formal history Workbench 读取
  surface summary、summary-only/degraded notice 表使用稳定空态、`BUSINESS_EQUIVALENT`
  与 UPDATE_ONLY suppressed stats 使用正式状态提示。empty unchanged filtered tables 不再
  作为 `hidden_tables` chip 或 hidden count 展示，正式前端 read model 不再承载 hidden table 展示状态。
- Frontend Formal Risk UI baseline 已覆盖：formal history Workbench 用户视图显示 active table
  风险摘要、review-required/UNKNOWN 风险 reason codes 和表级 annotation reasons；risk-only /
  diff-and-risk 空态区分“只有表级风险”。projection-level row-to-device 精确风险归属仍留后续 slice。
- Risk serialization cleanup 已进入正式边界：无 annotation 的表在 upload preview 与 formal
  history comparison 中序列化为 `risk_level: null`、`annotation_count: 0`，不再补
  `UNKNOWN`；`UNKNOWN` 只保留给 risk engine 明确产出的 review-required annotation。
  所有公开 `annotation_ref`/manifest ref 必须闭合为真实
  `backend-vnext/risk-annotations/v1` artifact，旧的
  `legacy-risk-annotation-sidecar/v1` placeholder bundle 不兼容，需要重新上传或重新比较。
- Upload Preview Formalization 已建立正式读取路径：upload preview 后端 tar 继续保留
  preview-compatible sidecar，同时保证 `comparison_surface.json` 中的 `projections/*` refs
  有闭合 artifact；前端 upload preview loader 优先读取 `comparison_surface_ref` 与 formal
  business projection artifacts，`buildFormalWorkbenchReadModel` 在 history compare 与 upload
  preview 中共享同一套 projection/read model 导航。
- 旧 upload preview `preview_index.sidebar_trees` 与 `secondary_device_projection` 只作为 fallback
  暂留。后续 cleanup slice 可以删除旧 preview sidebar/secondary projection fallback 和 legacy adapter
  sidecar；若真实 upload preview bundle 缺少 projection artifacts 或 surface refs 不闭合，应先修
  backend artifact closure，不在前端按表名猜测业务导航。
- Preview alias metadata now follows the visible surface boundary: aliases retained for comparison-core
  reuse are published to `preview_index.json` and the strategy manifest only when both logical and
  canonical tables are visible in the same pair. This prevents hidden empty/unchanged tables from
  producing invalid frontend alias references.
- Upload preview now closes every published snapshot table ref with a bundle-local Parquet artifact.
  The frontend reads these `before/current` table refs directly; descriptor JSON is metadata only and
  must not be emitted at a row-data ref. Multiple visible tables may share the same bundle-relative
  snapshot Parquet ref when a published visible alias maps them to one canonical table; the shared ref
  is still a real Parquet artifact and appears only once in the bundle artifact closure.
- Descriptor placeholders and JSON diff envelopes are not part of the formal contract. Upload preview now closes
  snapshot and comparison-record refs with their actual Parquet bytes before bundle assembly; malformed,
  missing, or JSON-backed row refs make the bundle invalid instead of publishing a placeholder.
- Upload preview `diff_artifact_ref` is a direct Parquet records ref, not a JSON envelope. Standard
  modified tables use `CURRENT_INLINE`; ordered modified tables use `CURRENT_SLOTTED` and publish the
  ordered position column so the frontend can reconstruct before/after/move/interval display rows.
- FULL upload preview now publishes pair-scoped surfaces instead of collapsing everything into one
  `before_to_current` view. When an archived baseline source package is available, the backend
  materializes it before marking the workspace's new initial ready and emits both
  `baseline_to_initial` and `initial_to_modified`; `initial_to_modified` remains the default view and
  the submit binding authority. If the baseline is explicit empty, an empty snapshot is materialized
  and used as the baseline side. If the archived baseline source cannot be resolved, FULL upload still
  returns READY with only `initial_to_modified` and records the skipped baseline-pair reason in
  preview diagnostics/strategy metadata.
- Submit finalize now also writes a durable `backend-vnext/snapshot-rows-archive/v1` artifact for the
  FINAL source snapshot and stores its ref on the submission/archive node. FULL upload prefers this
  artifact for archived baseline restore; a hit skips archived source package staging, SQL parse and
  materialization for `baseline_to_initial`. The source package remains the fallback path for missing
  or invalid archive artifacts, and benchmark events report
  `submit.finalize.snapshot_rows_archive_write` and `upload.full.baseline_snapshot_rows_restore`.
- Upload preview bundle refs are pair-scoped for multi-surface publication:
  `pairs/{view_id}/tables/{before|current}/*.parquet`,
  `pairs/{view_id}/comparison/records/*`, `pairs/{view_id}/risk/*`, and
  `pairs/{view_id}/projections/*`. The bundle still writes a top-level `comparison_surface.json` for
  the default view, while `preview_index.views[].derived_artifacts.comparison_surface_ref` points to
  each view's formal `pairs/{view_id}/comparison-surface.json`.
- Upload preview snapshot export is visibility-driven, current-preferred, and single-sided: it only exports
  refs for visible `surface.tables`. Non-empty `BROWSE_ONLY` tables remain visible browse tables, do not
  enter row comparison or produce records artifacts, and export current snapshot Parquet when current data
  exists; before snapshot Parquet is exported only when current data is unavailable. Snapshot Parquet is written directly to the bundle root and records Parquet is copied from
  the records store as a file-backed artifact. Snapshot Parquet encode builds Polars frames column-wise
  instead of per-row dicts, pre-binds cached Parquet scalar normalizers per descriptor column, preserves
  descriptor column order and existing bundle refs, and supports table-level thread parallelism for explicit
  benchmark or deployment override. Default export remains serial after large-package benchmarking showed
  both 2-worker and 4-worker runs were not consistently faster for this workload, with
  `BACKEND_VNEXT_UPLOAD_PREVIEW_SNAPSHOT_EXPORT_WORKERS=1|2|4` available for benchmark comparison or
  production override. Benchmark events now split snapshot encoding, records copy, bundle writing, and tar
  creation under the upload benchmark run id, and snapshot encode reports worker strategy and top slow
  tables. Snapshot encode also reports logical table count versus actual export task count after
  same-bundle alias ref dedupe and snapshot-only fast candidate ref dedupe. The snapshot-only dedupe
  may let ordered/logical tables share one browse Parquet ref when they have the same selected side and
  the same `fast_row_digest + export schema + row count + scalar/parquet writer contract`; it does not
  publish comparison aliases and does not merge records, risk annotations, table facts or logical table
  identity. The same fast candidate key remains a bundle-local physical artifact optimization only and
  must not be used as a persistent Parquet artifact cache key without a separate validation design.
  Snapshot encode also reports dry-run cache reuse diagnostics on exact `row_layout_digest` eligibility.
  Large first-upload baseline before the columnar export change:
  137 tables / ~223k rows / ~2.8MB Parquet with snapshot encode around 19.8s; columnar export reduced
  it to roughly 9s, while table-level thread parallelism remains opt-in because it was not consistently
  faster on the current large sample.
