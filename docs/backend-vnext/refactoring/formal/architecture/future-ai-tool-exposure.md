# 未来扩展方向：分析能力工具化与 AI 编排

- 状态：**方向记录（Exploratory Direction）**。本文不是 Contract 或 ADR，不改变任何现行阶段的范围，不授权实现。
- 日期：2026-09-27
- Owner：Backend vNext Architecture
- 适用时机：P5 架构收口完成、P5 整体 exit 之后
- 事实基线：`main` @ `218c211240`（代码与 `465b53746a` 相同）
- 索引：[架构总纲 §16](architecture-and-refactoring-plan.md#16-未来扩展方向)

## 1. 问题

未来是否可以把业务数据解析、差异比较、风险评估等能力从业务流程中剥离，封装为 MCP 工具或其他形式，供 AI 模型动态编排
或调用；当前架构在 [P5 架构收口](../plans/p5-arch-closure-execution-plan.md)之后能否支撑这一改造。

## 2. 结论

1. 可行。收口后的能力层已经具备单独调用的条件，改造不需要重建核心架构。
2. 能力按性质分两类处理：
   - **分析类**（解析、物化、规范投影、比较、风险评估、结果组装）：无副作用、可复现，可以开放给模型自由编排；
   - **业务动作类**（Submit、Review、Archive、身份确认等产生权威事实的操作）：只能经现有 HTTP API、以调用者身份执行，
     不能由模型绕过 Application 直接调用能力层。
3. 收口本身是这次改造的前置条件（§3.2）。收口期间不为工具化增加任何机制。
4. 启动时机为 P5 整体 exit 之后，并且需要已确认的使用方（§7）。

## 3. 现状依据

### 3.1 已具备的条件

**能力层依赖干净。** `capabilities/` 下各能力只依赖同层能力、`artifacts` 包与 `gateway_shared_kernel`，不依赖 application、
domain、infrastructure、operations 或 http。该方向由 `tests/support/import_rules.py` 与 `tests/architecture_baseline.py`
强制执行，基线只减不增（P5 §2A.2）。2026-09-27 的依赖事实：

| 能力 | 用途 | 同层依赖（除 `artifacts`） |
| --- | --- | --- |
| `table_access` | SQL 与 XML 解析 | 无 |
| `source_package_staging` | 上传包解包与受限成员枚举 | 无 |
| `table_rules` | 表规则（存储与比较规则视图） | 无 |
| `composite_signal` | `logics.xml` 组合信号 | `table_access` |
| `snapshot_materialization` | 业务快照物化 | `table_access`、`table_rules`、`composite_signal` |
| `storage_projection` | 规范投影与 manifest | `snapshot_materialization`、`table_rules` |
| `comparison` | 差异比较 | `snapshot_materialization` |
| `risk_evaluation` | 风险评估 | `comparison` |
| `surface_assembly` | 比较结果汇总 | `comparison`、`risk_evaluation` |
| `bundle_assembly` | 导出包组装 | `surface_assembly` |
| `mutation_planning` | Repository 写入的 DML 规划 | `storage_projection` |

**能力层没有隐藏的 I/O。** 能力层中没有网络、子进程或数据库调用。产物读写经 `ArtifactStorePort`（已有
`InMemoryArtifactStore`）；Repository 读取经 `RepositoryTableAccessProvider`、`RepositoryRefSession` 等 Protocol 端口；
取消检测经各能力的 `CancelProbe`。第三方依赖只有 pyarrow。因此能力可以在没有控制库、没有 Dolt 的环境中运行。

**规则是带摘要的数据。** 风险规则集是带 digest 的 `RiskRulesetSnapshot` 文档；S2a 之后比较规则为带 digest 的
`ComparisonRuleSet`（ADR 0018）。工具调用的结果可以按“输入摘要 + 规则集摘要”复现、缓存与核对。

**HTTP API 已覆盖主要只读查询，并有异步模式。** 生产路由包括 `/v1/history`、`/v1/history-compares`（含 bundle）、
`/v1/workspaces/{workspace_id}/preview-results/{preview_result_id}`（含 bundle）、`/v1/operations/{operation_id}` 等，
由 OpenAPI 测试约束。长任务采用“受理 → operation → 轮询”，可以直接对应工具的异步调用。

**确定性与规范化。** 业务 digest、规范状态摘要与 Python/Rust 一致的 canonical 编码（ADR 0005）使工具结果可验证，
不依赖调用次序或进程状态。

### 3.2 收口前的障碍与收口的处置

| 障碍（收口前） | 收口处置 | 阶段 |
| --- | --- | --- |
| comparison 公共面混有上传模式、pair 角色、History 视图等流程词汇（导出 99 个名字） | 公共输入只剩 `pair_id`、两侧规范快照、`ComparisonRuleSet`、执行模式（[ADR 0021](../adr/0021-flow-neutral-comparison-entry.md)） | S1、S2a |
| 流程拓扑与 step plumbing 分散在 Preview、Submit、History 三个 job 模块 | 流程拓扑归 Application，抽出 `application/pair_pipeline.py` 与 `application/job_steps.py` | S1 |
| Application 私自从规则构造比较策略（`_project_table_policy`） | 比较规则视图由 table_rules 提供（[ADR 0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)） | S2a |
| 两侧不在同一规范域比较，结果受列序与存储形态影响 | 比较在规范域进行，按列名与有效键对齐，列序不是业务状态 | S2a、S2b |
| 项目身份判定与比较耦合 | 身份评估移入 `project_identity`（[ADR 0020](../adr/0020-project-identity-and-dataset-replacement-in-p5.md)） | S4 |
| 包根模块与不可达代码 | 删除或登记延期 | S1、S5 |

收口完成后，能力层满足 [Contract Taxonomy](../contracts/contract-taxonomy-and-ownership.md) §4.4 “capability contract 与流程
无关”的要求，这是能力可以脱离业务流程单独调用的前提。

## 4. 能力分类

| 能力 | 可否作为工具开放 | 说明 |
| --- | --- | --- |
| `table_access`、`source_package_staging` | 可以，经临时分析用例（§5.2） | 输入来自调用方，适用上传受理的上限与 archive/path 边界 |
| `snapshot_materialization`、`storage_projection` | 可以，经临时分析用例 | 输出是产物句柄与摘要，不直接返回行数据 |
| `comparison`、`risk_evaluation` | 可以 | 规则集的使用见 §5.5 |
| `surface_assembly`、`bundle_assembly` | 可以，作为结果摘要与导出 | 摘要优先，明细分页下钻（§5.3） |
| `project_identity`（S4 新增） | 只开放评估结果 | 身份确认属于业务动作，仍由用户在 Submit 受理时给出 |
| `mutation_planning` | 不开放 | Repository 写入规划，只在 Submit prepare 内部使用 |
| `canonical_row_hash`、`external_target_sync` | 不开放 | 前者是内部内核，后者已登记延期 |
| Submit、Review、Archive、身份确认 | 不作为能力工具开放 | 只能经现有 HTTP API 以调用者身份执行；模型最多发起请求，确认与授权规则不变 |

## 5. 需补齐的条件

### 5.1 两类工具的边界

分析类工具只产生非权威的派生结果。任何权威事实（PreviewResult、SubmitAttempt、Submission、Review、Archive、Repository
commit）只能由现有 Application 用例在其事务、CAS、幂等与权限规则下产生。模型编排不得绕过 Application 直接调用能力层
改写权威状态，也不得把分析类工具的结果当作提交判定的依据。

### 5.2 临时分析用例

现在能力只在 Preview、Submit、History 的 job 中调用，结果写入控制库。要支持“拿两个包直接比较、不入库、不提交”，需要在
Application 新增临时分析用例：

- 使用会话级或临时产物存储，产物有 TTL 与总量上限，按现行 artifact cleanup 规则回收（ADR 0012）；
- 不产生 Repository 效果，不写控制库中的业务表；
- 结果标注为非权威，并带输入摘要与规则集摘要；
- 输入经现有上传受理的大小、成员数与路径校验。

能力层已支持这种用法（`ArtifactStorePort`、Protocol 端口），缺的是这个用例、它的资源上限与测试 owner。

### 5.3 接口形态：句柄、摘要与分页下钻

真实数据中单个 `dbcfg.sql` 约 80MB，比较记录量大，工具返回值不能携带 Arrow 数据或整表行数据：

- 工具之间传递服务端产物句柄（不透明 ID），句柄只指向服务端拥有的产物，不接受任意主机路径；
- 先返回 surface 级摘要（表级变化计数、风险等级与原因码）；
- 明细通过分页下钻工具获取，单页有行数与字节上限；
- 长任务返回 operation 句柄，由轮询工具获取状态。

### 5.4 调用方与信任边界

按 [ADR 0012](../adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)，同机 Service 进程属于同一信任域；AI 客户端
（MCP 客户端）不属于该信任域，是新的调用方。它必须经现有的认证、授权、exact scope 与资源上限；
[AGENTS.md](../../../../../AGENTS.md) 列出的 API 认证授权、caller 输入、path/archive/symlink 越界、资源上限等基础边界
不能因“内部工具”而放宽。是否为 AI 客户端引入独立身份（服务账号）或只沿用用户令牌，须在 ADR 中决定（§8）。

### 5.5 规则集的使用

权威比较只使用运行期注册的规则集（DC10）。若允许模型传入自定义规则集做假设分析：

- 结果必须标注为非权威，并带自定义规则集的 digest；
- 不得进入 Preview、Submit 或 History 的权威记录；
- 自定义规则集经与注册规则相同的校验（列处置、键与 ordered 约束）。

### 5.6 打包

能力层目前位于 `gateway_backend` 包内。第一步不需要拆包：MCP 服务可以作为与 HTTP、worker 并列的新入口（composition root）
复用能力层。只有出现 backend 之外的复用方时，才把 `capabilities/` 与 `artifacts/` 拆为独立发行包（形式与现有
`shared_kernel` 相同）。依赖图已是由门禁约束的 DAG，拆分主要是机械迁移；拆分后镜像与依赖锁按 AGENTS.md 的规则处理。

## 6. 建议路线

| 期 | 内容 | 进入条件 | 新增信任机制 |
| --- | --- | --- | --- |
| 0（收口期间） | 不增加任何工具化机制；只守住收口目标：能力去流程化、契约可序列化、入口单一 | 已在进行 | 无 |
| 1 | 只读 MCP 服务，作为现有 HTTP API 的客户端：History 查询与比较、Preview 结果与 bundle、operation 状态 | P5 整体 exit；有确认的使用方 | 无（沿用用户令牌与现有授权） |
| 2 | 临时分析用例与无副作用分析工具：解析、物化、投影、比较、风险评估、摘要与分页下钻 | 第 1 期可用；ADR 已接受（§8） | 由 ADR 决定 |
| 3（按需） | 拆出独立能力包 | 出现 backend 之外的复用方 | 无 |

第 1 期改动最小：MCP 服务只是 HTTP 客户端，不改变 backend 的边界，可以单独部署与回退。第 2 期开始改变 Application
用例与资源模型，须先写 ADR。

## 7. 不做事项

- 收口期间不为工具化增加机制；新机制须对应已确认的使用方（[比例化保障政策](../policies/proportional-assurance-and-risk-based-verification-policy.md)）。
- 不让模型绕过 Application 产生权威事实；不把模型输出作为提交、审核或归档的判定依据。
- 不在工具接口中暴露服务端路径、`repository_path`、`run_dir`（架构总纲 §13）。
- 不为 AI 客户端建立绕开现有认证授权的通道。
- 不把 Repository Service 直接暴露给 AI 客户端；Repository 仍只服务 backend（架构总纲 §9）。

## 8. 启动前须决定的事项

1. 协议形态：MCP、OpenAPI 生成的函数工具，或两者并存；MCP 服务的部署位置（同机进程或独立容器）。
2. AI 客户端的身份：沿用用户令牌，还是引入服务账号；服务账号的 scope 与审计方式。
3. 临时分析的资源模型：并发上限、单任务输入大小、产物 TTL 与总量上限、配额归属。
4. 自定义规则集是否开放（§5.5）。
5. 结果保留与审计：非权威结果是否需要保留、保留多久、能否导出。
6. 第 2 期的 ADR 与测试 owner：临时分析用例的不变量（不写权威状态、不产生 Repository 效果、资源上限）由哪些测试证明。

## 9. 相关文档

- [架构总纲](architecture-and-refactoring-plan.md) §7（Capability 架构）、§9（Repository Service）、§13（完成标准）
- [P5 架构收口详细设计](../plans/p5-arch-closure-design.md)与[执行计划](../plans/p5-arch-closure-execution-plan.md)
- [ADR 0018](../adr/0018-canonical-domain-comparison-and-comparison-rule-view.md)、[ADR 0020](../adr/0020-project-identity-and-dataset-replacement-in-p5.md)、
  [ADR 0021](../adr/0021-flow-neutral-comparison-entry.md)、[ADR 0012](../adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)
- [Contract Taxonomy](../contracts/contract-taxonomy-and-ownership.md) §4.4
