# P3-R6 Risk, Surface and Bundle Design Baseline

状态：Accepted design baseline；detail plan accepted for staged execution；implementation authorization pending

日期：2026-08-21

Owner：Backend vNext Risk, Surface and Bundle Capabilities

上游设计：[P3 Capability Foundation Design](p3-capability-foundation-design.md)

上游 handoff：[P3-R5 Comparison Handoff](p3-r5-comparison-handoff.md)

相关 contract：[Risk Contract](../../../contracts/risk.md)、[Comparison Surface Contract](../../../contracts/comparison-surface.md)、[Comparison Bundle Contract](../../../contracts/comparison-bundle.md)

本文是 P3-R6 的正式设计基线，不授权实现。R6 只负责 flow-neutral comparison risk、surface assembly 和 bundle assembly；HTTP、Workspace、Preview/Submit、Operation Runtime、static-risk production provider 和 artifact retention wiring 保持在后续阶段。

## 1. Objective

R6 将 R5 的 immutable `ComparisonFacts` 和可选 records closure 转换为可复验的 risk evaluation、thin comparison surface 和闭合 comparison bundle。

```text
ComparisonFacts + optional records closure + frozen RiskRulesetSnapshot
  -> comparison risk evaluation / annotation closure
  -> ComparisonSurface
  -> ComparisonBundle + final artifact closure
```

R6 的结果必须 deterministic、bounded、flow-neutral，并且不得改变 `ComparisonFacts` 的语义或授权状态。

## 2. Scope and non-goals

### 2.1 In scope

- comparison risk facts、规则执行、summary、annotation artifact 和 report；
- surface table projection、diagnostics/ref validation、surface digest；
- single-pair 和 multi-pair bundle assembly、relative ref rewrite、manifest、closure 和 bundle digest；
- R6 自有的 resource caps、failure matrix、fixtures、benchmark evidence 和 architecture checks；
- `DEGRADED`、`FAILED`、`CANCELLED`、`IDENTITY_GATE_BLOCKED`、`DATASET_REPLACEMENT` 和 no-record table 的下游表示。

### 2.2 Out of scope

- static-risk rules/provider/registry/production aggregation；
- Rust risk kernel、跨语言 risk differential 和 P6 性能优化；
- HTTP、Workspace、Preview/Submit、History/Archive flow、Operation Runtime、artifact retention/GC；
- surface/bundle cache、distributed ownership、new helper/service/security principal；
- comparison algorithm、R5 records schema、identity assessment 或 continuation persistence。

## 3. Authority and ownership

1. R5 `ComparisonFacts`、records closure、status和digest是 comparison authority；R6 不重新推断比较事实。
2. `Ruleset Activation and Migration` / Table Rules and Risk Policy 拥有 ruleset snapshot 的激活、版本和 digest authority。
3. Risk capability 拥有 risk evaluation、annotation schema、risk model 和 risk digest；只消费 frozen `RiskRulesetSnapshot`。
4. Surface capability 拥有 surface schema、surface projection 和 surface digest；不拥有 risk rule。
5. Bundle capability 拥有 bundle manifest、bundle-relative refs、final closure 和 bundle digest；不拥有 comparison 或 risk 计算。
6. Flow/application 后续拥有 confirmation persistence、expiry/revocation、权限和 READY 生命周期。

任何 `RISK_ONLY` 规则不得改变 comparison semantics。改变 comparison behavior 必须 reopen R5 owning contract/ADR。

## 4. Result and failure semantics

### 4.1 Aggregate precedence

整体状态优先级冻结为：

```text
FAILED > DEGRADED > BUSINESS_EQUIVALENT > UNCHANGED
```

- primary pair failure 使整体 `FAILED`；
- optional baseline pair failure 使整体最多 `DEGRADED`；
- 单表 degraded 不阻塞其他表；
- cancellation/timeout 是独立 terminal status，不发布 `ComparisonFacts`、risk READY 或 bundle READY；
- `IDENTITY_GATE_BLOCKED` 只发布 assessment/diagnostics；
- `DATASET_REPLACEMENT` 不生成 row-level risk 或 records。

### 4.2 Degraded table

每个 planned table 必须产生 terminal table fact。degraded table 使用显式 closure entry：

```text
status = DEGRADED
records_ref = none
diagnostics = complete bounded diagnostic set
```

不得写 partial Parquet，也不得伪造空 records artifact。Risk 输出 configured degraded/`UNKNOWN` annotation；Surface 使用 `DEGRADED_NOTICE`；Bundle closure 包含 diagnostic entry。

### 4.3 Closure atomicity

Risk annotation/evaluation、surface 和 bundle 各自拥有 immutable intermediate result。只有 bundle assembly 才产生最终 bundle closure：重写 refs、校验所有 manifest/content digests、写 manifest 并原子发布。中间结果不得单独宣称最终 READY。

## 5. Risk contract baseline

R6 comparison risk 输入固定为：

```text
ComparisonFacts
optional ComparisonRecordsClosure access
frozen RiskRulesetSnapshot
risk_contract_version
risk_model_version
risk_options
artifact_policy
```

static-risk 使用 `SnapshotTableArtifact` 的独立输入留作未来 capability seam，不加入 R6 `RiskEvaluationInput` 的 optional 字段。

R6 v1 ruleset 通过 frozen registry snapshot 提供，至少包含：

- table added/deleted；
- schema changed/schema-only changed；
- row added/deleted/modified；
- key/schema degraded；
- ordered unsupported；
- comparison failed；
- `composite_signal_point` 表级例外。

每条 annotation 必须有 stable `reason_code`。默认等级沿用 Risk Contract：

```text
TABLE_ADDED -> MEDIUM_LOW
TABLE_DELETED -> MEDIUM_HIGH
SCHEMA_CHANGED -> MEDIUM_HIGH
ROW_ADDED -> MEDIUM_LOW
ROW_DELETED -> MEDIUM_LOW
ROW_MODIFIED -> MEDIUM_HIGH
DEGRADED / ORDERED_UNSUPPORTED -> UNKNOWN
COMPARISON_FAILED -> HIGH
```

`risk_evaluation_digest` 包含 comparison digest、contract/model version、ruleset digest、options、table risk digests 和 annotation manifest digests；不包含 operation id、flow id、host path 或 artifact refs。

## 6. Surface and bundle baseline

Surface 只消费 `ComparisonFacts`、optional records closure、optional `RiskReport` 和 validated artifact refs。它不读取 full rows、不计算 risk、不包含 flow state。

第一版只实现 `STANDARD_TABLE_BROWSER`；row records 通过 refs，不内联到 surface。所有 refs 必须为 operation-relative 或 bundle-relative logical refs，禁止 host path、cache-local ref、repository ref、commit hash、preview token、submit binding 和 workspace state。

Bundle 第一版实现 `SINGLE_PAIR` / `MULTI_PAIR`，并负责：

- pair surface 组织；
- snapshot/records/risk/diagnostic artifacts 闭合；
- bundle-relative ref rewrite；
- manifest、closure 和 bundle digest；
- cross-pair shared snapshot artifact 的去重和 ref 保持。

Bundle 不计算 comparison/risk/surface，不写 flow envelope，不实现 bundle cache。

## 7. Confirmation and identity boundary

R6 只传播和校验 R5 提供的 immutable assessment/confirmation digest。继续确认和 submit confirmation 保持独立字段、独立 subject digest 和独立审计事实；expiry、revocation、actor policy、policy version、replay/concurrency 和持久化由后续 flow/application owner 负责。R6 不允许普通 caller 伪造 `NOT_APPLICABLE` 或绕过 identity gate。

## 8. Provider and benchmark policy

R6 的 production candidate provider 是 bounded Python reference provider。R6 必须通过 Python golden、digest、failure、budget 和 closure tests；Rust risk provider、跨语言 differential 和性能优化属于 P6，不阻塞 R6 module gate，也不作 native risk parity 声明。

Benchmark 只记录 correctness-passed runs，覆盖 single pair 和 `1/2/4/8` multi-pair profile，记录 wall time、CPU、RSS、queue wait、annotation/artifact bytes 和 cancellation latency；无 numeric performance pass/fail gate。

## 9. Acceptance and reopen

R6 必须证明：

- 相同 facts/ruleset/options 得到稳定 risk、surface、bundle digests；
- ruleset snapshot、annotation manifest 和 bundle closure 可复验；
- degraded、failed、cancelled、missing artifact 不会产生虚假 READY；
- no-record degraded table 有完整 diagnostic closure entry；
- refs 无 host/cache-local path，bundle 可从 closure 重放；
- capability 不 import flow、旧业务模块、Repository/Dolt、HTTP 或 Operation Runtime；
- Python reference provider 的 golden/failure/budget tests 通过。

必须 reopen R6 或其 owning contract 的情况：改变 failure precedence、将 static risk 塞入 comparison risk input、risk rule 改变 comparison semantics、partial artifact 发布、确认语义进入 capability、引入新 service/helper/security principal、或将 R6 扩展到 P5 flow。
