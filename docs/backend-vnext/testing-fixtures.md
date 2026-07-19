# Testing Fixtures

状态：已按 Phase 0 formal contract 更新

本文只说明测试材料入口；目录、manifest、naming、provenance、golden、runner 和 CI 的唯一正式规范是 [Fixture Oracle and Conformance Contract](refactoring/formal/contracts/fixture-oracle-and-conformance.md)。Canonical bytes 与 vectors 由 [Shared Canonical Encoding Contract](refactoring/formal/contracts/shared-canonical-encoding.md) 规定。

## 正式根目录

跨 Python、Rust 和 Repository Service 的正式 fixture 位于 repository-level：

```text
vnext/fixtures/
  scenarios/
    data/<subject>/<scenario>/
    command/<subject>/<scenario>/
    recovery/<subject>/<scenario>/
  shared/
  vectors/
```

每个 scenario 使用 declarative `scenario.yaml`、`input/` 和 `expected/` closure。手写最小样本与脱敏回归样本通过 manifest `provenance` 区分，不作为目录层级。正式 scenario 不依赖实现语言的 test root；组件测试目录只保存不构成跨实现 contract/oracle 的私有小型材料。

## Git 内材料

- Scenario-local closure 不超过 1 MiB；shared correctness asset 不超过 5 MiB。
- 第一版不使用 Git LFS。
- `SANITIZED_REGRESSION` 必须包含脱敏 policy/version、审批和不可逆性证据。
- 原始业务 SQL、内部路径、敏感日志和可逆映射不得进入 Git。
- Golden 只能通过 owner 审核的 candidate diff 更新，测试运行不得自动 bless。

## 外部 dataset

Benchmark 与大型/敏感 dataset 位于仓库外，不与 correctness fixture 混合。每个可报告 dataset 必须提供 `dataset.yaml`，固定 safe ID/revision、provenance、validation、logical composition/change chain、generator version/seed（如适用）和 content identity。缺失或 identity mismatch 是 `HARNESS_ERROR`，不得视为通过。

Benchmark 只评价 vNext production public entrypoint；具体 profile、环境、指标和 baseline gate 见 [Performance Measurement and Baseline Contract](refactoring/formal/contracts/performance-measurement-and-baseline.md)。

## 执行入口

普通 correctness CI 从 `vnext/fixtures/` manifest 发现 required scenarios/vectors，再由 subject harness registry 调用 production/reference entrypoint。实现私有 unit tests 可以使用各自 test runner，但不能替代正式 conformance lane，也不能把私有 fixture 提升为跨语言 oracle。
