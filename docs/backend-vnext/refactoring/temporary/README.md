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

- [Phase 0 Baseline and Oracle](phase-0/baseline-and-oracle-notes.md)
- [Project Environment Preparation](project-environment-preparation.md)

不得把临时文档直接改名为正式文档；正式文档需要去除讨论过程，并重新表述 owner、规则、版本和验收标准。
