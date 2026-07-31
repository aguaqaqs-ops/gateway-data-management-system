# Temporary Refactoring Documents

本目录保存重构讨论过程中的临时材料，包括提案、备选方案、开放问题、实验记录和阶段性结论。

临时文档规则：

- 必须标记 `Draft`、讨论主题和适用阶段。
- 可以保留未决问题和被否决方案。
- 不作为正式实现依据，也不定义稳定 contract。
- 讨论收口后，将最终结论重新整理到 `../formal/`、正式阶段计划或 ADR。
- 正式结论落地后，临时文档应标记 `Resolved` 并归档或删除，避免搜索时与正式规则混淆。

Phase 1 临时文档建议放在：

```text
temporary/phase-1/
  contract-taxonomy-notes.md
  open-questions.md
  experiments.md
```

当前讨论记录：

- [Architecture Simplification Execution Plan](architecture-simplification-execution-plan.md)
  （Active；先闭合Phase 0–2设计，再协调联合代码清理）
- [Phase 0 Baseline and Oracle](phase-0/baseline-and-oracle-notes.md)
- [Project Environment Preparation](project-environment-preparation.md)
- [Phase 1 Closure Sign-off](phase-1/phase-1-closure-signoff.md)（Phase 1 已于
  2026-07-27 收口；其余 Phase 1 临时材料保留为历史证据）
- [Phase 2 Interactive Design Session Guide](phase-2/interactive-design-session-guide.md)
  （Round 0–11、Consolidated Review、consumer check与F0已于2026-07-30收口；
  旧设计只继续支持WP1-R1 checkpoint，之后由ADR 0009替代）
- [T2 Phase 2 Simplification Implementation Checklist](phase-2/t2-simplification-implementation-checklist.md)
  （D2已完成；代码执行等待Phase 0–1设计与cross-phase reconciliation）

不得把临时文档直接改名为正式文档；正式文档需要去除讨论过程，并重新表述 owner、规则、版本和验收标准。
