# Phase 3 Capability Foundation Execution Plan

状态：正式执行规划基线（Accepted for staged planning）

日期：2026-08-18

阶段：P3-R1 complete；R2 detail plan pending；implementation authorization pending

Owner：Backend vNext Capability Architecture

## 1. Purpose and planning rule

本文把 [P3 Capability Foundation Design](p3-capability-foundation-design.md) 转换为可执行
的模块路线，但不一次性冻结所有低层步骤。R 级职责、依赖、handoff 和 exit gate 在本文
固定；当前 R 完成后，才根据真实实现结果细化下一个 R 的 S 级步骤。

```text
P3 master roadmap
  -> current P3-Rn plan
      -> Rn-Sn execution step
          -> review/remediation rounds
              -> Rn gate and handoff
                  -> next R detail plan
```

P2 可复用的是 staged execution、review、remediation、handoff 和 phase gate 的治理方式，
不复用 P2 的功能模块边界或 R 编号含义。

## 2. P3 module roadmap

模块划分依据 capability dependency、contract owner、artifact handoff、独立可验证输出、
风险/审核类型和单步上下文规模，而不是平均分配代码量。

| Module | Scope | Required handoff |
| --- | --- | --- |
| P3-R1 Capability Foundation | contract/test foundation、错误分类、已证明必要的 shared primitive、artifact/staging conformance、provider/import boundary checks | 可独立调用的 capability boundary |
| P3-R2 Table Access and Parser | table access protocol、SQL parser、XML parser、bounded rows/descriptors、parser diagnostics | descriptor/diagnostics/deferred row stream |
| P3-R3 Source Materialization and Snapshot | ruleset snapshot、canonical materialization、derived tables、`SnapshotTableArtifact`、reuse/fallback profile | immutable snapshot artifact closure |
| P3-R4 Storage Projection | canonical key/schema、storage digest、CanonicalizationManifest、RepositoryImportArtifact input | canonical storage projection |
| P3-R5 Comparison | comparison projection、standard diff、row records、`FULL`/`MODIFIED_ONLY`、dataset replacement | `ComparisonFacts`/records |
| P3-R6 Risk, Surface and Bundle | RiskEngine、risk facts、annotations、surface assembly、bundle closure | Preview-facing result closure |
| P3-R7 Mutation and Target Closure | `StorageMutationPlan`、`ChangeSetArtifact`、`ADAPTIVE_PATCH`、Dolt renderer、reference external executor、fault/benchmark closure | target-neutral ChangeSet and renderer results |

R2 内部必须保持 SQL parser、XML parser 和 materialization policy 的独立 provider seam。
R6 与 R7 不合并：risk/surface/bundle 与 storage mutation/target apply 的 owner、数据形态
和失败模型不同。

## 3. Standard S-step template

每个 R 在开始前只细化当前 R 的 S steps。默认模板如下，实际步骤可以合并或拆分：

| Step | Purpose | Output |
| --- | --- | --- |
| `S0` entry/handoff | scope freeze、输入检查、reopen review | accepted step brief |
| `S1` contract/skeleton | contract、port、fixture shape 或最小 walking path | compile/importable boundary |
| `S2` implementation | 单一主责逻辑和最小 provider | focused code and unit tests |
| `S3` conformance | golden、differential、failure、artifact round-trip | validation result |
| `S4` focused review | 针对当前风险的第一轮审核 | findings register |
| `S5` remediation | 修复、复测、必要时新增 regression fixture | closed findings or reopen |
| `S6` independent review | contract/storage/cross-language/recovery 等高风险项按需触发 | independent review result |
| `S7` module gate | 汇总测试、诊断、benchmark、docs 和 handoff | R exit handoff |

审核轮次不预设固定次数。S5 发现新问题时使用后续 remediation round；P1/P2 finding、
contract ambiguity、digest/storage mismatch、跨语言语义差异、资源上限和 recovery issue
必须在下一步前关闭或显式 reopen owning contract。

### 3.1 Applicability review rule

R1-S0 及后续每个 R 的 entry review 都是适用性审查，不是对既有实现或设计的无条件继承。
Legacy 和 Phase 1 代码只提供行为、边界和实现证据；如果复用会违反当前 owning
contract、P3 并发/容量目标、artifact/digest boundary、恢复语义或依赖规则，必须暂停
相关实现。

资产盘点至少检查：

```text
owner and contract authority
semantic fit with P3
dependency direction and cycles
tests and actual behavior evidence
capacity/concurrency/resource fit
artifact/digest reuse feasibility
failure/cancel/recovery boundary
duplicate implementation or mutable shared state
```

发现按以下方式处理：

| Finding | Required action |
| --- | --- |
| implementation bug, contract remains valid | fix and add regression test |
| contract conflicts with P3 decision | stop; reopen owning contract/ADR before code |
| owner/dependency boundary is wrong | revise module/import boundary and architecture test |
| performance/resource gap | record validation-passed measurement and reconsider provider |
| consistency/recovery/security gap | blocking finding; no workaround-only closure |
| low-impact naming/local detail | record and continue |

以下情况必须阻止 R entry 或继续实现：shared primitive 不满足 canonical contract、artifact
boundary 无法表达 immutable handoff、存在实际 capability cycle、digest/sort/scalar
语义冲突、关键失败/恢复不变量没有可执行证明，或复用会违反已接受的安全/容量边界。

正确处理顺序为：

```text
evidence -> issue register -> owning contract/ADR decision
         -> fixture/test update -> re-review -> implementation
```

本项目尚未发布，明确错误不因 legacy compatibility 被保留。Legacy 仅是 reference oracle。

## 4. Step context package

每个最终执行步骤必须自包含：

- 目标、非目标和当前 R 边界；
- 上游 contract/ADR 和已确认 invariant；
- 输入、输出、owner、允许修改路径和禁止触碰路径；
- 测试、benchmark、故障注入和静态检查命令；
- review checklist、预期 findings 和 escalation rule；
- exit criteria、handoff artifact 和 reopen conditions；
- 预计上下文规模。若一个步骤同时引入多个独立 contract、跨越多个 owner 或无法在一个
  有限上下文中解释完整，则必须拆分。

### 4.1 Generic execution template

每个 R 的详细计划应复制以下字段并按当前模块填写，不得只写“实现并测试”：

```yaml
step_id:
module:
status:
objective:
non_goals: []
upstream_contracts: []
owners: []
allowed_paths: []
forbidden_paths: []
inputs: []
outputs: []
invariants: []
tests: []
benchmarks: []
fault_cases: []
review_focus: []
reopen_conditions: []
handoff_artifacts: []
review_rounds:
  focused: required
  independent: risk_based
```

Step handoff 必须包含 tested tip、实际命令和结果、未解决但已接受的 deferred items、
changed contract/fixture references，以及下一 step 的 entry prerequisites。

## 5. Independent tests and intermediate artifacts

每个 capability 必须可独立测试，不要求完整 HTTP、Workspace、Operation Runtime 或 Dolt
集成链：

| Module | Standalone input |
| --- | --- |
| R1 | scalar、diagnostic、admission 和 contract fixtures |
| R2 | SQL/XML bytes、descriptor、bounded row stream |
| R3 | parser output + ruleset snapshot |
| R4 | `SnapshotTableArtifact` |
| R5 | snapshot/comparison projection |
| R6 | `ComparisonFacts` + ruleset snapshot |
| R7 | before/after canonical storage snapshot、`ChangeSetArtifact` |

小型稳定语义 fixture 进入 `vnext/fixtures/golden` 或 `vnext/fixtures/vectors`，由 owner
review 后提交。测试生成的中间 artifact 使用 `tmp_path` 或专用 `ArtifactStore` staging
root，必须带 manifest/schema/raw/content digest，测试结束后清理，不依赖工作区永久路径。

纯 parser、type mapping、projection、comparison、risk 和 planner 测试不得创建 Dolt；真实
Repository/readback 只在独立 integration 层验证。R7 默认使用 in-memory reference executor；
SQLite 仅作为部分 dialect/conformance 辅助，不能称为 PostgreSQL production validation。

跨 R handoff 只传 immutable artifact/ref，不共享可变 Python object、provider-private object
或线程池状态。artifact 缺失/损坏必须走明确 fallback 或新 attempt，不让测试隐式重建成功。

## 6. Benchmark policy

P3 必须有诊断性 benchmark，但不设置“超过旧实现多少”的 numeric gate。测量分三层：

1. capability/component：parser、materialization、projection、comparison、risk、mutation；
2. cross-capability：以 immutable artifact 串联相邻 R，观察序列化和 peak RSS；
3. multi-pair：`1/2/4/8` pair，观察 wall time、CPU、RSS、queue wait、staging high-water
   和 cancellation latency。

benchmark 只统计 correctness-passed runs，并记录 dataset ID/revision、provider、环境、
warm/cold setup、raw samples、统计方法和限制。组件 benchmark 用于 provider/优化决策；
正式 end-to-end performance claim 延后到真实 P5 production path/P7 optimization phase。
普通 CI 不默认执行完整 benchmark matrix，除非出现已接受的容量或 regression target。

## 7. R gate and handoff

R 只有在以下条件满足后才关闭：

- contract owner 和输入输出边界明确；
- focused unit/conformance/differential/failure tests 通过；
- artifact closure 和 cleanup 边界通过；
- 与当前风险相称的 review/independent review 完成；
- benchmark 或资源诊断结果已记录（若该 R 涉及数据面性能）；
- 无未处理 P1/P2 finding、未决 contract ambiguity 或隐式跨 R 依赖；
- handoff 记录 tested tip、命令、结果、已知限制、deferred items 和下一个 R 的 entry。

R 之间默认串行。R 内只有不共享未稳定 contract、不会改变对方 owner 语义的工作可以并行。

## 8. Cross-phase markers

| Future item | Phase marker |
| --- | --- |
| durable operation、drain、checkpoint、takeover | P4 |
| Workspace、HTTP、PreviewResult、artifact retention wiring | P5A |
| Submit/finalize、Dolt effect、external ChangeSet wiring | P5B |
| Rust coverage expansion、risk kernels | P6 |
| global concurrency/cache tuning | P7 |
| shadow/cutover | P8 |
| cleanup/production hardening | P9 |
| PostgreSQL production adapter/e2e | future target-specific |
| online ruleset watcher/hot activation | future optional |
| `STORAGE_BREAKING` migration executor | future migration work |

## 9. Current status

```yaml
p3_design: accepted
p3_execution_plan: accepted_for_staged_planning
current_module: P3-R2
current_module_detail: R1 gate pass; R2 detail plan pending
p3_r1_s0: completed
p3_r1_s0_inventory: p3-r1-s0-asset-inventory.md
p3_r1_s1: completed
p3_r1_s2: completed
p3_r1_s3: completed
p3_r1_s4: completed
p3_r1_s4_review: p3-r1-s4-focused-review.md
p3_r1_s5: not_required
p3_r1_s5_note: no S4 P1/P2 findings; S6 independently retested final candidate
p3_r1_s6: completed
p3_r1_s6_review: p3-r1-s6-independent-review.md
p3_r1_s7: completed
p3_r1_s7_handoff: p3-r1-capability-foundation-handoff.md
p3_r1_exit: pass
p3_r2_ready: yes
p3_implementation_authorized: no
```

## 10. Normative references

- [P3 Capability Foundation Design](p3-capability-foundation-design.md)
- [P3 Active Context Index](p3-active-context-index.md)
- [P3-R1 Capability Foundation Handoff](p3-r1-capability-foundation-handoff.md)
- [Implementation Stages](implementation-stages.md)
- [Performance Measurement and Baseline](../contracts/performance-measurement-and-baseline.md)
- [Fixture Oracle and Conformance](../contracts/fixture-oracle-and-conformance.md)
- [Contract Taxonomy and Ownership](../contracts/contract-taxonomy-and-ownership.md)
