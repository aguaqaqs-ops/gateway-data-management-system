# Frontend Surface Simplification

本文定义 backend vNext surface / bundle 与前端展示一起简化的设计原则。目标不是复刻旧 preview bundle / Workbench bundle 的文件形状，而是在减少冗余结构的同时，保证旧实现的用户可见能力可以完整复原。

本文件是前后端协作策略，不替代 `contracts/comparison-surface.md`、`contracts/comparison-bundle.md`、`capabilities/surface-assembly.md` 或 `capabilities/bundle-assembly.md`。

新前端直接消费 vNext core 产物，不为 legacy 前端或旧 bundle 形状建设兼容层或适配输出（[前端 kickoff](../frontend-vnext/frontend-kickoff.md) FD1，owner 2026-11-02）。业务分组与表格展示由后端产出，见 [BE-b 设计草案](../frontend-vnext/be-b-navigation-and-presentation-draft.md)（FD6）。

## 目标

- 把 vNext surface 设计成 thin index，而不是旧 preview bundle 的重建。
- 保留完整用户可见能力：表导航、diff 浏览、risk 浏览、diagnostics、离线 bundle、history pair 切换。
- 减少重复事实：table summary、risk summary、sidebar projection、preview index 不在多个文件中重复维护。
- 让 Dolt native provider 和 ordered diff compute 只需要输出标准 comparison/risk facts，不直接绑定前端旧形状。

## 核心原则

1. 事实不丢。

   用户可见能力依赖的事实必须存在于 vNext core artifacts：`ComparisonFacts`、`ComparisonRecordsClosure`、`RiskReport`、`RiskAnnotationArtifact`、diagnostics artifacts、`ComparisonSurface` 和 `ComparisonBundle`。

2. 展示可派生。

   旧实现中为前端方便而生成的重复索引（变更/风险筛选、徽章计数、表列表），由前端从 surface/risk 派生，不作为 core truth 重复保存。业务分组与表格展示依赖行数据与业务规则，由后端产出（FD6），不属于前端派生。

3. 不设适配层。

   不生成旧 Workbench 或旧 preview bundle 形状的输出（FD1）。

4. 验收看功能，不看旧文件同构。

   vNext 不要求生成与旧 bundle 一模一样的目录、字段或嵌套结构。验收标准是旧的用户可见功能能从 vNext core 完整实现。

## 简化后的两层

```text
ComparisonSurface
  thin display index for one directed pair

ComparisonBundle
  closed delivery unit for one or more surfaces and artifacts
```

`ComparisonSurface` 只保留：

- pair/view metadata。
- table list。
- table status / change kind / row stats。
- records refs。
- risk report / annotation refs。
- diagnostics refs。
- ordered extension reserved slot。

`ComparisonBundle` 只保留：

- bundle manifest。
- pair surfaces。
- artifact closure。
- bundle-relative refs。
- optional shared snapshot/input table artifacts。


## Legacy Capability Coverage

| 旧用户可见能力 | vNext 来源 | 第一版策略 |
| --- | --- | --- |
| 表列表 | `ComparisonSurface.tables` | core 保留 |
| 变更表筛选 | `SurfaceTable.change_kind`、`SurfaceView.changed_table_count` | 前端派生 |
| 表级新增/删除/更新/schema/degraded 状态 | `ComparisonTableFact -> SurfaceTable` | core 保留 |
| 行级新增/删除/修改浏览 | `ComparisonRecordsArtifact` refs | core 引用，records 不内联 |
| 大表分页/懒加载 | records artifact + future page/index manifest | 第一版预留，前端按 artifact 读取 |
| 只看风险 | `RiskReport`、`RiskAnnotationArtifact` refs | 前端派生 |
| 风险等级和原因 | `RiskReport.tables`、`RiskAnnotation.reasons` | core 保留 |
| 风险定位 | `RiskTarget`、annotation refs | core 保留，ordered interval 后续补充 |
| diagnostics 展示 | surface diagnostics refs、comparison/risk diagnostics artifacts | core 引用 |
| 离线加载 | `ComparisonBundle` + artifact closure | core 保留 |
| history 2/3 节点 pair 切换 | `ComparisonBundle.pairs` | core 保留 |
| Workbench 只读打开 | `ComparisonBundle` | 新前端直接加载 |
| 业务分组、节点与页签；表名、列名与列序 | surface `projections`（业务导航）与 `SurfaceTable`/`SurfaceColumn` 展示字段 | 后端产出（FD6、BE-b，见 [BE-b 设计草案](../frontend-vnext/be-b-navigation-and-presentation-draft.md)） |
| preview-specific submit/review/upload 操作入口 | flow envelope /正式业务 API | 不进入 surface/bundle core |

## Core / Derived / Removed

### Core 必须保留

- `comparison_digest`、`surface_digest`、`bundle_digest`。
- surface table index。
- table-level status and stats。
- records refs and records manifest refs。
- risk report refs and annotation refs。
- diagnostics refs。
- artifact closure。

### 前端可派生

- changed-only / risk-only filtered views。
- table tab ordering。
- table badge counts。
- per-view risk summary shortcut。
- preview index style table list。

派生规则需要稳定、可测试；如果派生逻辑变重或被多个前端重复实现，可后续抽成独立 projection capability。

### 不再保留为 core truth

- 与 `ComparisonSurface.tables` 重复的 preview index table summary。
- 与 `RiskReport` 重复的 surface 内完整 risk payload。
- 与 records artifact 重复的 row records inline payload。
- preview token、preview revision、submit binding、target set binding。
- host path、cache-local ref、repository internal ref。

## 前后端责任边界

Backend vNext 负责：

- 产生 `ComparisonFacts`、records、risk、surface、bundle 和 artifact closure。
- 保证 refs 可重写、可校验、可离线加载。
- 保证 degraded/unsupported 表有 diagnostics 和 review-required risk。
- 产出业务导航与表格展示字段（FD6）。

Frontend 负责：

- 从 thin surface 派生 UI 导航、筛选、tab、badge。
- 按 refs 加载 records/risk/diagnostics artifacts。
- 不从 row records 自行推断 risk。
- 不依赖 preview/upload/submit 字段出现在 generic surface/bundle 中。

共同约定：

- 如果某个旧功能无法从 vNext core 复原，必须补覆盖矩阵后再实现。
- 不为了短期 UI 方便把 flow state 写回 surface core。
- 新增展示需求优先判断是 core fact 还是前端派生。

## 第一版取舍

第一版固定选择：

- `ComparisonSurface` 是 thin index。
- `ComparisonBundle` 是 artifact closure carrier。
- 不实现 Workbench adapter（FD1）。
- 业务导航由后端产出（FD6，BE-b）。
- 不实现 ordered semantic display，只保留 extension。
- 不实现 surface/bundle cache，只保留 key 边界。

## First Implementation Minimal Cut

第一版实现闭环：

```text
Snapshot materialization
  -> Comparison compute
  -> Risk evaluation without risk cache
  -> Thin surface assembly
  -> Bundle assembly without cache
```

第一版明确不实现：

```text
comparison_surface_cache
risk_evaluation_cache
flow_assembly_cache
ordered semantic diff
projection_table_cache
formal projection artifact cache
repository server export artifact cache
```

Repository server table cache 例外：第一版可以实现简化跨 session 技术 cache，用于降低 Dolt catalog/describe/count/root metadata IO；但先不实现 TTL、pin、eviction 和大对象 export artifact cleanup。完整策略见 `artifacts.md` 和 `capabilities/repository-ref-materialization.md`。

后续可能变化：

- Dolt native provider 已有第一版设计；实现和 benchmark 完成后，确认 native output 到 `ComparisonRecords` 的映射。
- Ordered diff contract/capability 已有第一版设计；实现完成后，按 `contracts/ordered-diff.md` 补充 ordered records、interval/move navigation、pseudo blank、table processing mode 和 ordered risk target 映射。

## 验收标准

- 旧用户可见能力在覆盖矩阵中都有 vNext 来源。
- Core surface/bundle 不包含 preview token、submit binding、workspace/history state、host path 或 cache-local ref。
- Frontend 能仅依赖 surface + artifact refs 完成普通表 diff 浏览。
- Risk-only 浏览只依赖 `RiskReport` 和 `RiskAnnotationArtifact`，不从 diff records 推断风险。
- History 3 节点可通过 `ComparisonBundle.pairs` 切换两个 pair。
- 新增展示字段前必须先判断是 core fact 还是前端派生。
