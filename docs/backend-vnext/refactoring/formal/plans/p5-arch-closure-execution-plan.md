# P5 架构收口执行计划

状态：**DRAFT — 待独立文档审核；实现未授权**

日期：2026-09-25

Owner：Backend vNext Architecture

入口：[Entry Brief](p5-arch-closure-s0-entry-brief.md) → [详细设计](p5-arch-closure-design.md) → 本文

B=`vnext/backend/src/gateway_backend/`，T=`vnext/backend/tests/`。本文写未来命令与期望证据；实际结果写入
各阶段 handoff。

## 1. 执行形态

```text
S0 文档与独立审核
  -> [前置：P5-5E slice exit pass]
  -> S1 结构修复（行为不变）
  -> S2 规范域比较 + commit 规范元数据 + comparison 去流程化
  -> S3 composite_signal 接入
  -> S4 项目身份与数据替换
  -> S5 清理、测量与收口验收
  -> P5 整体 exit review（另行进行，不由本计划签署）
```

阶段顺序依据：

- S1 先把重复编排与边界理顺，并以“golden 与 digest 不变”作为回归基准，这样 S2 的语义变更只需改一处；
- S2 是 S3/S4 的地基，两者都依赖规范快照与去流程化后的 comparison 入口；
- S3 先于 S4：静默丢失（R5）比无法识别误传（R6）更严重，而且 S3 的改动面更小。

每阶段结束交独立审核，审核结论按
[纵切指南 §6](../guides/slice-design-execution-and-review-guide.md) 给出；未通过不进入下一阶段。

## 2. 阶段定义

### S0 — 文档入口与独立审核

- 交付：Entry Brief、详细设计、本计划、ADR 0018–0021（Proposed）、P5 §2A.4.1 第二轮补充、
  Business Lifecycle 3.1.0 候选（设计附录 A）。
- 审核对象：本分支 `p5-arch-closure-docs` 的固定 commit；代码事实基线 `2172369803`。
- 通过后：ADR 状态改为 Accepted；Business Lifecycle 3.1.0 按附录 A 接受（实现分布在 S2/S4）；
  §2A.2 按 ADR 0021 修订；实现授权另行给出。

### S1 kickoff（5E slice exit 之后）

1. 把本分支合入 5E exit 后的主线；
2. 运行 `python -m tests.support.import_rules`，记录 S4 期间基线的变化；
3. 按设计 §2 复核 E 级事实；若有偏离，先修订设计对应章节再开工。

### S1 — 结构修复（行为不变）

- 目标：关闭设计 §9 标为 S1 的项。
- 行为约束：golden、业务 digest、HTTP DTO 与 compose 旅程结果均不变；只改导入路径的测试不改断言语义。
- 验收：
  - `tests/architecture_baseline.py` 只剩：A2 `http_arrow` 三条、A6 `repository_import_artifact` 及其导入方
    （S2 关闭）；不可达基线只剩 composite 相关模块（S3）与已登记延期项（`external_target_sync`、
    canonical row hash 路径）；运行时环基线为空。
  - backend unit、integration、serial 全绿；五包 ruff、mypy 通过。
  - bootstrap 组合改动涉及进程装配，因此在阶段末重建 current HEAD 镜像并运行既有 compose 旅程，
    结果与 5E exit 一致。

### S2 — 规范域比较、commit 规范元数据与 comparison 去流程化

- 目标：设计 §4、§5、§6（W1、W2、W3）。
- 验收：
  - 新测试 owner（设计 §12）通过，其中规范快照同一性与“同内容 → 全表 UNCHANGED”两项是阶段门槛；
  - `BROWSE_ONLY`/`SNAPSHOT_ONLY` 形态先与 legacy oracle 核对后再冻结测试；
  - golden 与 digest 按新语义一次性更新，更新理由写入 handoff；
  - 5E integrity incident 相关代码、路由、表与测试已删除，OpenAPI 测试同步更新；
  - 导入基线清空（S3 与已登记延期的不可达项除外）；
  - compose：扩展旅程“提交 X → 审核 → 归档 → 再次上传 X”，得到 Preview 全表 UNCHANGED 与
    `NO_CANONICAL_CHANGE`；规则表（显式键、忽略列、ordered）在非空基线上的 Preview 不降级；
    History ordered 旅程结果不变；阶段末重建镜像。

### S3 — composite_signal 接入

- 目标：设计 §8（W5）。
- 先验证 Dolt 对 `TEXT` 主键的行为；若拒绝，进入设计 §14 停止条件 2，由 storage_projection owner 以 ADR 处理后再继续。
- 验收：
  - composite 的 golden（规则变更后的规范形态）通过；
  - compose 旅程“仅修改 `logics.xml`”在 Preview 中可见，Submit 后进入 Repository，History 中可比较；
  - 无效 `logics.xml` 使 Preview FAILED 并给出明确诊断；
  - 不可达基线中 composite 与 XML 模块移除。

### S4 — 项目身份与数据替换

- 目标：设计 §7（W4）。
- 验收：
  - 身份规则 v1 使用合成夹具覆盖旧验收矩阵的判定类别（同项目、不同项目、排除 `no`、缺表、空表、列集合不一致）；
  - 初始空基线的 pair 为 `NOT_APPLICABLE`，首次提交不需要确认；
  - 替换事实、比较级风险、双侧导出；
  - 受理：缺失、多余、摘要不符、理由长度、重放；
  - Archive 身份异常处置与 StartArchive 校验；
  - Business Lifecycle 3.1.0 身份相关条款实现完毕；
  - compose 旅程：跨项目上传 → 替换 Preview → 带确认提交 → 审核 → 带理由处置 → 归档，
    另加 `UNVERIFIABLE` 分支；阶段末重建镜像。

### S5 — 清理、测量与收口验收

- 处置不可达基线：删除或在 owning 设计中登记延期（owner、理由、重开条件）；登记后的条目保留在基线中并加注释。
- 按 ADR 0018–0021 与设计 §11 修订 owning 文档（总纲 §7、Contract Taxonomy、R3/R4/R5 设计、5E §6.6、P5 §2A.2 与 §6.1）。
- 按设计 §13 完成代表性链路测量，形成 Phase 6 候选列表。
- 最终门禁：fresh 构建 current HEAD 镜像；全部 compose 旅程 0 skipped；`./vnext/scripts/run-tests.sh` 全量；五包静态检查。
- 交付 `pass_recommended` 与证据包；按 [P5 §2A.5](p5-business-vertical-slices-design.md) 逐项对照，由独立验收记录收口结论。

## 3. 路径预算

“必改”是阶段目标所必需的路径；“条件”只有在出现可复现缺口时才启用，启用时须在 handoff 中说明。

| 阶段 | 必改（B） | 必改（T） | 条件 |
| --- | --- | --- | --- |
| S1 | `application/submission/{ports,abort_transaction,finalize_transaction}.py`、`application/submit_jobs.py`；新增 submission 下层保护释放模块与 `application/submission/artifact_refs.py`；`domain/submission/models.py`；删除 `artifacts/nominal_refs.py` 的 domain 依赖；`infrastructure/repository_write/*`；`http/{runtime,dependencies,history_reader}.py` 迁出，`http/orchestration/{source_package_admission,preview_acceptance,history_compare,multipart_stream,multipart_upload}.py`、`http/schemas/{history,constraints}.py`；新增 `bootstrap/composition.py`，修改 `bootstrap/{operation_worker,http_server}.py`、`app.py`；`application/{preview_jobs,job_definitions,payloads}.py`、`application/history/{compare_jobs,compare,compare_bindings,contracts,ports}.py`、`application/workspace/preview.py`、`application/archive/ports.py`；新增 Application 共享 step 构建、pair 流水线与控制事务协议模块；`operations/contracts.py`；`domain/submission/policies.py`；`capabilities/{table_rules,composite_signal}/contracts.py`、`capabilities/source_package_staging`（公开成员枚举入口）、`capabilities/snapshot_materialization/contracts.py`（Snapshot/Summary 编解码）、`capabilities/comparison/{standard,ordered}.py` 及新增共享行编码模块；`infrastructure/control_db/{database,sqlite_baseline,sqlite_mapping,sqlite_history_compare}.py`；删除 `cache/`、`canonicalization_{cells,manifest}.py`、`capabilities/comparison/provider.py`、`capabilities/snapshot_materialization/cache.py`、`capabilities/{comparison_projection,business_projection}/`；`compute.py` 与 `canonical_row_hash_ipc.py` 移入 `capabilities/canonical_row_hash/`；`synthetic_w2.py`、`application/{synthetic_jobs,external_effect_stub}.py` 移出生产包 | `test_architecture.py`、`architecture_baseline.py`；受影响测试只更新导入路径；`support/` 接收 synthetic 模块；删除 `test_canonicalization_manifest.py` 及被删模块的测试 | Rust 架构检查中的 Python 路径断言 |
| S2 | `capabilities/table_rules/{contracts,resolver}.py`（`ComparisonRuleView`、`compare_excluded_columns`）；`capabilities/storage_projection/{contracts,project,import_replay,package}.py` 及新增规范投影与包渲染入口；`capabilities/snapshot_materialization/{contracts,repository_ref}.py`；`capabilities/comparison/*`（入口、规划、规则视图消费、`__init__`）；`capabilities/surface_assembly/{contracts,_assembly}.py`（身份标注输入）；`infrastructure/repository_read/http_arrow.py`；`application/preview_jobs.py` 与 S1 抽出的流水线模块、`application/history/{compare_jobs,compare,contracts,ports}.py`、`application/submit_jobs.py`、`application/submission/{accept,accept_transaction,contracts,ports}.py`；删除 `repository_import_artifact.py`；`domain/workspace/models.py`（PreviewResult）、`domain/submission/models.py`；`infrastructure/control_db/{migrations,sqlite_workspace,sqlite_submission,sqlite_history_compare,sqlite_history,database}.py`；`http/routes/history.py`、删除 `http/orchestration/history_integrity.py`、`http/{errors}.py`、`http/schemas/{preview,history}.py`；新增 `CommitCanonicalMetadataPort` 的 adapter | 设计 §12 中 S2 相关 owner；更新 `test_preview_job_*`、`test_history_compare_*`、`test_submit_*`、`test_repository_ref_materialization_*`、`test_comparison_*`、`test_storage_projection_*`、`test_http_openapi.py`；删除 `test_history_compare_integrity.py` 等；compose 旅程扩展 | `snapshot_materialization/scalar_encoding.py` 与 `sql_declared_types.py`（仅当规范快照同一性失败且根因在编码） |
| S3 | `capabilities/table_rules/registry.py`（composite 规则）；`application/preview_jobs.py` 或 S1 抽出的物化模块（业务物化）；`capabilities/snapshot_materialization/compose.py` 接线所需的公开入口 | composite golden；`test_preview_job_materialize.py`；compose 旅程 | `capabilities/storage_projection/project.py`（`TEXT` 主键规范化，须先有 ADR） |
| S4 | 新增 `capabilities/project_identity/`；`capabilities/comparison`（替换事实）；`capabilities/risk_evaluation`（比较级规则）；`capabilities/bundle_assembly`（双侧导出，如需）；`application/preview_jobs.py` 或流水线模块；`application/submission/{accept,accept_transaction,contracts,errors,review}.py`；`domain/submission/models.py`、`domain/workspace/models.py`、`domain/archive/models.py`；`application/archive/{queries,start,contracts,audit}.py`；`application/history/projection.py`；`infrastructure/control_db/{migrations,sqlite_workspace,sqlite_submission,sqlite_archive,sqlite_review}.py`；`http/schemas/{submit,preview,archive,review,history}.py`、`http/errors.py`、`http/orchestration/{submit_acceptance,archive,review}.py` | 设计 §12 中 S4 相关 owner；`test_http_auth_matrix.py`、`test_http_openapi.py`；compose 旅程 | — |
| S5 | 不可达模块处置涉及的路径；owning 文档 | `architecture_baseline.py` | 测量脚本只放在 `vnext/backend/benchmarks/`，不进入生产包 |

## 4. 测试归属与比例化

- 唯一 owner 见设计 §12；同一不变量不在多处重复证明。
- 同构错误（确认缺失/多余/摘要不符、规则集校验）使用模块级参数表。
- 纯规则、解析与规范投影测试不引入 Dolt；真实 Dolt 只用于 integration 与 compose。
- 新增持久事实（PreviewResult 身份结论、身份确认、Archive 身份异常事件）属于权威 A 类：覆盖事务、
  幂等、重放与并发代表点，沿用 5B/5C/5D 的测试模式，不建立全故障点矩阵。

## 5. 命令草案

```bash
# 五包静态（提交前必跑）
for p in shared_kernel repository_contracts repository_client repository_service backend; do
  (cd vnext/$p && ../scripts/uv-consume.sh -C . run ruff check . && ../scripts/uv-consume.sh -C . run mypy)
done

# 导入边界现状
cd vnext/backend && ../scripts/uv-consume.sh -C . run python -m tests.support.import_rules

# 阶段 focused（按阶段替换文件集）
cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest -m unit -q
cd vnext/backend && ../scripts/uv-consume.sh -C . run pytest -m integration -q

# 阶段末与 S5 权威全量
./vnext/scripts/run-tests.sh
```

compose 旅程的运行方式、镜像重建与 provenance 记录沿用
[testing-conventions](../../../testing-conventions.md) 与 5D/5E 的 §6.3 最小格式。

## 6. 镜像重建判定

| 阶段 | 是否重建 | 理由 |
| --- | --- | --- |
| S1 | 是 | 进程组合（bootstrap、worker、HTTP 装配）改动，需要证明启动、装配与旅程不变 |
| S2 | 是 | compose 旅程与 HTTP DTO 改变；control DB migration 在启动时执行 |
| S3 | 是 | 新增 compose 旅程 |
| S4 | 是 | 新增 compose 旅程与 HTTP DTO |
| S5 | 是（fresh） | 最终候选不得用旧镜像证明 |

Dockerfile、依赖锁与 Compose 预期不变；如需修改，按 AGENTS.md 的镜像规则执行并记录。

## 7. 停止规则

设计 §14 任一停止条件出现时，暂停当前阶段，在 handoff 记录触发事实并交 owner 处理；不得以兼容代码、
Application 特判或新增基线条目绕过。
