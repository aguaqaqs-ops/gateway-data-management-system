# ADR 0006: Language-Neutral Fixture Oracle

状态：Superseded by ADR 0010

日期：2026-07-19

决策 owner：Backend vNext Conformance Architecture

关联阶段：Phase 0、Phase 1、Phase 8

> 本文是历史决策记录，不再定义现行 contract。现行 correctness 规则见
> [Correctness Golden and Fixture Contract](../contracts/fixture-oracle-and-conformance.md)
> 与 [ADR 0010](0010-minimal-golden-and-ordinary-ci.md)：不再建设 generic scenario
> manifest、closure、runner、harness/profile matrix、RunEvidence 或
> exact-commit phase gate。

## Context

把正式 fixtures 放在某个 Python/backend test root 会使语言实现成为事实 owner，并诱导继承 legacy 目录与内部步骤。Recovery、artifact 和跨语言 canonical contract 还需要统一 manifest、evidence 与 profile，而不是多套实现专属 golden。

## Decision

正式 oracle 根为 repository-level `vnext/fixtures/`。Scenario 按 `data/command/recovery` 执行语义组织，每个目录拥有无继承、无脚本的 declarative `scenario.yaml + input + expected` closure；stable dot ID、kebab path、subject 与 track 必须一致。Golden envelope 绑定唯一 semantic owner 与 contract version。

Runner core 与 subject harness registry 分离；支持 reference/integration/process-crash/provider-matrix profiles、四态 result、typed single fault、failure/recovery checkpoints、stable-read barrier 和 test-only evidence bundle。Git correctness materials 与外部 benchmark datasets 严格分离。Manifest/golden/protocol/result的精确schema与runner/harness authority由 [Fixture Oracle and Conformance Contract](../contracts/fixture-oracle-and-conformance.md) 唯一规定。

## Alternatives

- 继续使用 legacy/backend fixture root：拒绝，会把语言和旧内部结构变成 contract。
- 以样本来源作为目录主分类：拒绝，provenance 已能表达来源，执行语义更稳定。
- Scenario inheritance/DSL/scripts：拒绝，closure 与 digest 难以审查和跨语言执行。
- 保存完整数据库 dump 作为 recovery golden：拒绝，包含过多非 contract 状态。

## Consequences

同一 fixture 可验证 Python、Rust 与 Repository，差异能按 contract 分类。需要建设 manifest validator、harness registry、sanitization gate 和专用 crash lanes；既有测试材料需按 owner 选择性转写，不能直接搬目录。

## Required Verification

- Manifest/path/closure/digest lint 与 golden update approval tests。
- 三类 scenario、四种 profile 和 runner result contract tests。
- Fault arm/consume、restart/recovery、stable-read barrier tests。
- Sensitive data、size limits 和 external dataset identity validation。
