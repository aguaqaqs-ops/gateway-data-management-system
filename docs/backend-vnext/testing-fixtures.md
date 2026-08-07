# Testing Fixtures

状态：已按简化后的 Phase 0–1 formal contract 更新

本文只说明测试材料入口；当前 fixture 语义由 [Fixture Oracle and Conformance Contract](refactoring/formal/contracts/fixture-oracle-and-conformance.md) 拥有。Canonical bytes 与 vectors 由 [Shared Canonical Encoding Contract](refactoring/formal/contracts/shared-canonical-encoding.md) 规定。

## 正式根目录

跨 Python、Rust 和 Repository Service 的正式 fixture 位于 repository-level：

```text
vnext/fixtures/
  golden/
  vectors/
```

Python 与 Rust owner tests 直接读取只读 golden/vector 材料；canonical encoding corpus
固定为 128 cases，必须 zero skip/xfail，Repository Service 不消费该 corpus。Canonical
Row Hash mixed-scalar golden 直接保存 request、Arrow input 和 expected hashes/result。

## Git 内材料

- 测试材料由 Git 和普通 code review 提供版本控制，不保存 fixture self-hash。
- 原始业务 SQL、内部路径、敏感日志和可逆映射不得进入 Git。
- Golden 只能通过 owner 审核的普通 diff 更新，测试运行不得自动 bless。

## 外部 dataset

Benchmark 与大型/敏感 dataset 位于仓库外，不与 correctness fixture 混合。每个可报告
dataset 由对应 owner 的 runbook 记录 dataset ID/revision、环境和 raw results。

Benchmark 只评价 vNext production public entrypoint；具体 profile、环境、指标和 baseline gate 见 [Performance Measurement and Baseline Contract](refactoring/formal/contracts/performance-measurement-and-baseline.md)。

## 执行入口

测试分层、marker 语义、执行脚本与性能约束由 [Testing Conventions](testing-conventions.md)
拥有；本节只说明 fixture 材料如何被消费。

普通 package CI 直接运行 owner 的 ruff、mypy、pytest 或 Cargo checks。Python reference
与 Rust provider 直接比较保留 corpus 和 mixed-scalar golden；不存在 current-authority
的 generic scenario manifest、runner、profile matrix、RunEvidence、gate 或 bless
framework。
