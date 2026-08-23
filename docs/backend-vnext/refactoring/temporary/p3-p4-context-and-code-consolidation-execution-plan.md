# P3→P4 Context and Code Consolidation Temporary Execution Plan

状态：Proposed for execution；Phase 3 已完成，`p3_exit: pass`、`p4_ready: yes`；
本计划不授权 P4 implementation

日期：2026-08-23

Owner：Backend vNext Architecture / Cleanup Implementer / Independent Acceptance

上游退出记录：

- [P3 Final Closure and P4/P5 Entry Handoff](../formal/plans/p3-final-closure-handoff.md)
- [P3-FINAL F5 Independent Acceptance Record](../formal/plans/p3-final-closure-f5-independent-acceptance.md)
- [P2–P3 Cleanup Manifest](../formal/plans/p2-p3-cleanup-manifest.yaml)（archive/tag 模式先例）

本文件是临时过程文档，不拥有 contract、wire、state machine、error、durable state 或
phase authorization 语义。最终 cleanup manifest 和 P4 active-context artifact 落入
`formal/` 后，本文件必须从默认树删除；其历史由 cleanup pre-tag 和 Git history 保留。

## 1. Objective and exit

本轮位于 P3 exit 与 P4 entry acceptance 之间，只完成两件事：

1. 收敛默认文档检索面，使 P4 不再从 P3 step/review/status 过程文档加载上下文；
2. 识别并删除或迁移可证明没有 production/release/contract consumer 的阶段性代码与工具。

本轮不是 P4 capability round，不编号为 P4-R1，也不改变 P3 历史 exit。完成条件：

- 有 clean、committed、可定位的 pre-cleanup baseline；
- annotated pre-cleanup tag 可恢复所有从默认树删除的文档和代码；
- 新 P4 active context 只引用 active architecture/contracts/policies、必要 handoff/evidence；
- active 文档不引用已从默认树删除的路径；
- 每个代码删除都有 consumer/import/export/script/deployment/test 证据和 owner disposition；
- 无 P3 public contract/reference deliverable 被误删；
- 适用测试、ruff、mypy、link/reference 与 container gates 通过；
- final cleanup manifest、handoff 和 independent acceptance 记录 candidate SHA、tag、删除清单、
  deferred register 与 `p4_implementation_authorized`；
- 临时 cleanup 过程文件从最终默认树移除；
- 最终状态保持：

```yaml
p3_exit: pass
p4_ready: yes
p3_p4_cleanup_exit: pass
p4_entry_context_ready: yes
p4_implementation_authorized: no_until_p4_entry_acceptance
p5_implementation_authorized: no
```

## 2. Hard boundaries

### 2.1 In scope

- formal/temporary 文档 inventory、authority classification、reverse-reference graph；
- 新建 P4 active-context index，缩减 README/default retrieval；
- 通过 annotated tag + manifest 从默认树移除已完成 step/review/attempt/process records；
- 审计 phase/gate/test/evidence-only Python/Rust/scripts；
- 删除或迁移逐项批准的 dead/evidence-only/test-support code；
- 同步删除被移除 production mechanism 的 mock、probe 和 mechanism-only tests；
- 比例化验证、clean candidate handoff 和独立验收。

### 2.2 Out of scope

- P4 Operation Store、worker、lease、heartbeat、takeover、drain 或 checkpoint runtime；
- P5 Workspace/Submit/finalize/confirmation/occupancy/T1/T3；
- 改变 Repository operation、marker/private ref/main CAS/reconciliation 权威；
- 修改 P3 capability contract、digest、artifact/wire/error 语义；
- production provider 选型、external-target adapter 或 multi-target durable schema；
- 为归档文档建立第二套可搜索 archive 目录；
- 以“清理”为由重命名全部模块、重排 package 或做无关格式化。

### 2.3 Phase/reopen rule

- 文档过程记录归档不重新打开 P3。
- 删除纯 dead/test/evidence support 不改变 `p3_exit`，但产生新的 P4 entry candidate SHA。
- 如果拟删除或改变 P3 public output、reference implementation、fixture oracle、digest、
  resource/cancellation boundary，必须停止并 reopen 对应 P3 R/Contract。
- 如果触碰 Dockerfile、Compose、entrypoint、deployment profile、container harness 或
  container-only runtime boundary，必须按 `AGENTS.md` 重建当前候选并运行相应 container gate。

## 3. Authority and retained context

### 3.1 必须保留为 active/normative

至少保留下列类别；C1 可以增加，不能无证据减少：

- `AGENTS.md`、testing conventions；
- Architecture and Refactoring Plan、Implementation Stages；
- active contract taxonomy、business lifecycle、external effect/recovery、operation lifecycle、
  Repository Service、canonical storage/encoding、storage mutation、external target sync；
- cross-stage proportional assurance 与 Rust policy；
- 未被替代的 ADR；被替代 ADR 只按现有 lifecycle 规则保留 source pointer；
- P2 External Interface Handoff；
- P3 Capability Foundation Design；
- P3-R7 Mutation and Target Closure Handoff；
- P3 Final Closure Handoff；
- P3-FINAL F5 Independent Acceptance Record；
- P3 final benchmark raw evidence；
- 新 P4 Active Context Index 和本轮 final cleanup manifest/handoff。

### 3.2 默认 archive candidate

以下只表示候选；C1 必须做 reverse-reference 和 semantic-owner 审计后逐项确认：

- P3 `S0/S6/S7` entry/focused/independent review records；
- R1–R6 已完成的 step/execution/review 过程文档；
- 已由 P3 design、module handoff 和 final handoff 覆盖的重复状态 YAML；
- 中间 attempt、discussion summary、临时 grill/review notes；
- cleanup 自身的 C0/C1 inventory、working notes 和本临时执行计划。

不要把 archive candidate 复制到 `formal/archive/` 或新的普通目录。默认 archive medium 是
Git annotated tag + history；final tree 只保留 manifest/source pointer。

### 3.3 默认代码 disposition

| Candidate | Initial disposition | Rule |
| --- | --- | --- |
| `vnext/backend/benchmarks/p3_capability_diagnostics.py` | **KEEP_EVIDENCE_TOOL** | P3 F2 可复验入口；不进 production package |
| `external_target_sync/_reference_executor.py` | **KEEP_P3_REFERENCE_DELIVERABLE** | R7 conformance/reference output；删除需 reopen R7 |
| `gateway_backend.synthetic_w2` + `run_r6_s6_evidence.py` | **MOVE/REMOVE_CANDIDATE** | 当前只见历史 capacity evidence/tests；C4 核对 package/export/script consumer |
| `gateway_shared_kernel.testing` | **MOVE_CANDIDATE** | test-only surface 位于 production `src`；核对 wheel/fixture tooling consumer |
| Repository `matrix.py` / `workflow.py` / `workflow_worker.py` | **RETIRE_DECISION_REQUIRED** | 大型 P2 gate harness，但仍被 tests/README/target gate 引用 |
| Repository `target_gate.py` | **KEEP_UNTIL_PROFILE_RETIRED** | 当前由 Compose `repository-probe` profile 调用 |
| `test_p2_r1_audit_corrective.py` | **FOLLOW_HARNESS_DECISION** | 不可先于 owning harness/profile 独立删除 |
| Repository `candidate_a` provider | **KEEP** | 当前默认 Repository provider；不是 phase 临时代码 |
| Repository reconciliation/cleanup/admin/runtime | **KEEP** | production contract mechanism；禁止按文件名猜测临时性 |

## 4. Classification model

每个文档和代码 path 必须恰好归入一个 class：

```text
ACTIVE_INTERFACE      默认检索入口、handoff、entry context
NORMATIVE             contract/policy/active ADR/architecture
EVIDENCE_POINTER      最小可复核结果、raw evidence、source pointer
RETAIN_IN_PLACE       非默认入口但存在当前 consumer，不能移动
ARCHIVE_FROM_DEFAULT  仅历史/process；由 tag/history 恢复
MOVE_TEST_SUPPORT     有测试 consumer、无 production/release consumer
REMOVE_DEAD           无 consumer、无 authority、无 recovery value
DEFERRED              证据不足或 owner 尚未裁定
```

文档 path 至少记录：path、class、owner、reason、reverse references、semantic extraction target、
SHA-256、bytes、archive/recovery pointer。

代码 path/symbol 至少记录：path/symbol、public export、imports、scripts/CLI、package entrypoint、
Docker/Compose、tests/fixtures、runtime profile、owner contract、decision、required gates。

## 5. Conversation and context strategy

不要在一个超长对话中执行 C0–C7。每个新对话只读取冻结的上一步 artifact 和当前 step 的
直接 authority，不复制此前完整 transcript。

| Conversation | Steps | Recommendation | Reason |
| --- | --- | --- | --- |
| A | C0 + C1 | **新开对话；两步保持同一对话** | inventory 与 classification 高度耦合，需要共享 reverse-reference 发现 |
| B | C2 + C3 | **新开对话；两步保持同一对话** | 只携带冻结 manifest，隔离 C0/C1 的搜索噪声；文档重写与归档必须同步 |
| C | C4 | **新开对话，单独完成** | 代码 consumer 审计风险不同；禁止受“必须删代码”预期影响 |
| D | C5 + C6 | **新开对话；实现与修复门禁保持同一对话** | 只携带 C4 approved list；失败时可原地修复和重跑 |
| E | C7 | **必须新开独立验收对话** | 不继承 implementer 解释，降低确认偏差并控制上下文 |

如果 C4 没有批准任何代码删除，C5 标记 `not_applicable`；仍建议用 Conversation D 独立完成
final verification/handoff，不把 Conversation B 的文档实现上下文带入候选封版。

最终审核不要返回编写本计划的原对话，也不要由 C2/C5 implementer 自审。应新开
Conversation E，提供本文件路径、final manifest/handoff、candidate SHA、pre-tag 和 gate logs。
若 E 要求纯机械 status/link 修正，回到 D 修复，再返回同一个 E 复核；若要求改变分类、
删除范围、代码或测试语义，则作废 candidate，重新开启相应实现对话并最终再开新的验收对话。

## 6. C0 — Entry, clean baseline and inventory freeze

### Objective

确认 P3 exit authority、现有用户改动、cleanup scope 和 archive identity；不删除文件。

### Required reads

- repository `AGENTS.md`；
- P3 final handoff 与 F5 acceptance；
- P3 capability design；
- proportional assurance policy；
- P2–P3 cleanup manifest；
- formal/temporary README；
- testing conventions。

### Actions

1. 执行 `git status --short --branch`、`git log`、`git diff --check`。
2. 逐项识别已有 dirty changes；不得覆盖、reset 或顺手吸收不明改动。
3. 本计划编写时观察到
   `p3-final-closure-execution-plan.md` 有一处未提交 normative-reference 修改：它新增 final
   handoff/F5 acceptance，但替换了 R7 handoff。实现开始时必须重新核对；建议同时保留 R7、
   final handoff 和 F5 acceptance 三个引用。
4. 形成 clean committed cleanup baseline；记录完整 SHA。
5. 生成文档/代码 inventory：path、size、hash、Git status、引用和候选分类。
6. 冻结 proposed tag names，例如：

```text
docs/p3-p4-cleanup-pre-YYYYMMDD
docs/p3-p4-cleanup-final-YYYYMMDD
```

7. C0 不创建 tag；等 C1 classification 完成、baseline clean 后再创建 pre-tag。

### Outputs

- temporary C0 inventory（machine-readable + short Markdown summary）；
- baseline SHA、dirty-worktree disposition；
- unresolved owner/escalation list。

### Exit / stop

`C0_exit: pass` 要求 baseline clean、所有现存 diff 有 owner。存在不明用户改动、P3 exit
状态不一致或无法恢复的 untracked evidence 时停止，不得开始删除。

### Conversation

**Conversation A，新开；C0 完成后继续同一对话执行 C1。**

## 7. C1 — Authority, evidence and consumer classification

### Objective

冻结逐 path disposition；C1 仍不删除文档或代码。

### Actions

1. 以 `rg --files` 建立 docs/source/tests/scripts/deploy/package inventory。
2. 对每个 archive 文档执行 reverse-reference 搜索；区分：
   - active normative dependency；
   - evidence/source pointer；
   - 仅由同批 process docs 相互引用。
3. 检查待归档文档是否仍拥有唯一规则；如有，先指定提取到 owning contract/design/handoff，
   C2 完成提取前不得归档。
4. 对代码候选仅记录 consumer graph，不作删除决定；代码最终裁定属于 C4。
5. 建立 formal manifest draft，沿用 P2–P3 manifest 的最小字段：

```yaml
schema: gateway.docs-code-lifecycle-cleanup.manifest
schema_version: 1
stage: p3-p4-context-code-consolidation
baseline_sha: <full sha>
archive_medium: git_annotated_tag_and_history
public_semantics_changed: false
paths:
  active: []
  normative: []
  evidence_pointer: []
  retain_in_place: []
  archive_from_default: []
  move_test_support: []
  remove_dead: []
  deferred: []
```

6. 对 proposed archive/remove paths 保存 SHA-256、bytes 和 recovery tag pointer。
7. 独立列出 P4 default context，目标是让新对话通常只需读取约 8–12 个直接文档，不加载
   P3 step/review matrix。
8. C1 pass 后创建 annotated pre-cleanup tag，并把 tag object/commit 记录进 manifest draft。

### Exit / stop

- 所有 path 已分类；
- unresolved escalation 为 0，或全部标为 `DEFERRED/retain`；
- active semantics 不只存在于 archive candidate；
- annotated pre-tag 可解析到 clean baseline；
- 此时才允许 `C1_exit: pass`。

### Conversation

**继续 Conversation A。** 完成后提交 C0/C1 artifact，并结束该对话；不要在 A 中直接删除。

## 8. C2 — P4 active-context and authority consolidation

### Objective

先建立新的默认入口并提取必要语义，再移除旧过程文档。

### Actions

1. 新建 `formal/plans/p4-active-context-index.md`，只组织检索，不复制 contract 规则。
2. P4 默认读取顺序建议：
   1. P4 Active Context Index；
   2. P3 final handoff + F5 acceptance；
   3. Implementation Stages 的 P4 section；
   4. Operation Lifecycle；
   5. External Effect and Recovery；
   6. Business Lifecycle and State；
   7. Repository Service；
   8. P3 Capability Design 及 P4 直接依赖 contracts；
   9. proportional assurance/testing conventions。
3. 缩减 formal README：只列顶层入口、active contracts/policies/ADRs 和 final handoff；移除
   S-step/review/execution-plan 的默认清单。
4. 更新顶层 refactoring/backend-vnext README 与 Implementation Stages 的 default pointer。
5. 将 C1 发现的唯一规则提取到 owning contract/design/handoff；不得在 P4 index 建第二份规则。
6. 明确：`p3_exit: pass` 保持历史事实，P4 implementation 仍未授权。

### Exit / stop

- P4 index 可独立回答 owner、entry prerequisites、P3 handoff、P4 non-goals 和默认 reads；
- active contract 语义未复制；
- 尚未删除的 archive candidates 已不再是默认入口；
- 如果提取规则需要改变 contract，停止并启动对应 owner review，不进入 C3。

### Conversation

**Conversation B，新开；读取 C1 frozen manifest，C2 完成后同一对话继续 C3。**

## 9. C3 — Documentation archive/removal and link closure

### Objective

从默认树移除已确认的 P3 process/history 文档，同时保持可恢复性和 active link closure。

### Actions

1. 仅删除 C1 manifest 中 `ARCHIVE_FROM_DEFAULT` 的显式 path；禁止宽目录 glob 删除。
2. 用 `apply_patch` 删除文件；禁止 broad `rm -rf`、`git reset` 或 checkout 覆盖。
3. 不创建普通 archive 副本；pre-tag 是主要恢复介质。
4. 更新 active docs 的链接，使其指向 owning contract、module/final handoff、F5 acceptance 或
   manifest source pointer。
5. 保留 R7 handoff、P3 final handoff、F5 acceptance 和 raw benchmark evidence，除非 C1 有
   更强 owner 证据并经显式批准。
6. 从默认树删除 temporary discussion/attempt notes；本 cleanup plan 和 C0/C1 records 暂留到
   C6 seal 前。
7. 运行：
   - `git diff --check`；
   - repository-scoped Markdown relative-link validation；
   - 对每个删除 path 执行 active reverse-reference scan；
   - 确认 active docs 不依赖 archive path。
8. 建立独立 docs-cleanup commit；不要和代码删除混为一个提交。

### Exit / stop

- broken active links = 0；
- active docs reference archive paths = 0，除明确 tag/source pointer；
- public semantics changed = false；
- docs cleanup commit 可单独 revert；
- 任一 active consumer 仍需原 path 时，改为 `RETAIN_IN_PLACE`，不得伪造 link closure。

### Conversation

**继续 Conversation B。** C3 pass 后结束该对话，输出 docs candidate SHA 和 manifest diff。

## 10. C4 — Code consumer audit and removal authorization

### Objective

对阶段性代码做独立、证据化裁定。C4 默认只读，不修改代码。

### Required checks per candidate

```text
public __init__/__all__ export
Python/Rust imports and dynamic import strings
package scripts/entrypoints
Dockerfile/Compose/entrypoint/healthcheck/profile
README/runbook/operator command
tests/fixtures/golden/vector tooling
current production/runtime code path
owner contract or final handoff role
failure/recovery evidence value
```

### Candidate-specific rules

- `synthetic_w2`：若只被历史 evidence script/tests 使用，优先移动到 `tests/support` 或删除
  script+module+mechanism-only tests；不得破坏仍声明的 capacity gate。
- `gateway_shared_kernel.testing`：若 wheel/runtime consumer 为零，迁到 test support；同时检查
  cross-language fixture command 是否依赖 installed package path。
- Repository matrix/workflow：必须先对 `repository-probe` profile 作明确 `KEEP/RETIRE` 决定。
  profile 保留则 harness 保留；profile 退休才允许把 Compose、README、target gate、workflow、
  tests 作为一个 owner bundle 处理。
- external-target reference executor：默认 KEEP；“当前无 production consumer”不是删除 P3
  reference deliverable 的充分理由。
- 名称含 `legacy/temp/reference/noop` 不是删除证据。

### Outputs

- code disposition table，逐 path/symbol 为 `KEEP/MOVE/REMOVE/DEFER`；
- approved code-change bundles；
- 每 bundle 的 owner、risk、tests、container applicability 和 reopen 判定；
- 如果没有安全删除项，明确 `C5: not_applicable`，这也是有效结果。

### Exit / stop

只有 `REMOVE/MOVE` 项 consumer graph 闭合、owner 同意且 gate 明确时 C4 pass。Repository
profile、public export、fixture oracle 或 P3 deliverable 有歧义时标为 DEFER，不得猜测。

### Conversation

**Conversation C，新开且只做 C4。** 不继承 B 的“已经清理很多文档，因此也应删代码”预期。

## 11. C5 — Approved code cleanup implementation

### Objective

只实施 C4 明确批准的 bundle；无批准项则标记 not applicable。

### Actions

1. 每个 owner bundle 单独修改，优先保持独立 commit。
2. 删除代码时同步删除：
   - mechanism-only mocks/probes；
   - 只证明已删除内部步骤的 tests；
   - package exports、scripts、README/Compose 接线；
   - 不再真实的 architecture allowlist。
3. 保留 contract behavior tests；不得因为删除 reference/helper 而削弱 public invariant。
4. test-support relocation 不得被 production package import。
5. 若实现中发现新 consumer，立即停止该 bundle 并改为 DEFER，不扩张范围。
6. 任何 P3 semantic/public output 变化作废本 cleanup 路径并 reopen owner。

### Verification during implementation

- 先跑 touched package focused/unit tests；
- 每个 touched Python package 跑 `ruff check .` 和 `mypy`；
- Repository serial tests 仍用 `-m serial -n 0`；
- marker、Dolt fixture、dependency pin 和 Docker rules 严格遵守 `AGENTS.md`。

### Conversation

**Conversation D，新开。** C5 与 C6 保持同一对话，使 gate failure 可以由同一 implementer
修复；不要把 C4 原始搜索输出全部带入，只携带 approved table。

## 12. C6 — Final verification, manifest and implementer handoff

### Objective

封印新的 P4 entry candidate，并从默认树移除 cleanup 过程材料。

### Gate matrix

| Change | Minimum gate |
| --- | --- |
| docs/index/link only | link/reference validation、`git diff --check`、manifest/path/hash audit |
| Python test-support/module move | touched package focused + unit、ruff、mypy、import/export scan |
| shared/repository contract-adjacent code | authoritative applicable tests + five-package ruff/mypy |
| timing-sensitive tests | serial group `-n 0` |
| Docker/Compose/profile/container harness | current HEAD rebuild + corresponding container/Compose smoke |
| dependency/lock/Dockerfile | lock hash rules + current HEAD rebuild |

如运行全 vNext source gate，legacy oracle 只能使用既有 exact-nodeid disposition，不得排除整个
test file，也不得把 external fixture 写成 gap closed。

### Actions

1. 确认 candidate clean committed SHA；source/test/docs patch identity 不能代替 commit。
2. 完成 formal `p3-p4-cleanup-manifest.yaml`，记录 baseline/candidate、pre-tag、counts、paths、
   hashes、public semantics、tests、container applicability、deferred register。
3. 形成 P3→P4 cleanup handoff，明确 P4 默认入口与未授权实现边界。
4. 从默认树删除：本临时计划、C0/C1 inventory、working review notes；pre-tag/history 保留它们。
5. 更新 temporary README，不能留下指向已删除 cleanup process 文件的链接。
6. 创建 proposed final annotated tag；tag 指向 final clean candidate，避免文档自引用 SHA。
7. 输出 implementer evidence report，不自行签发 independent acceptance。

### Exit / stop

- worktree clean；
- manifest 与 Git diff/path counts 一致；
- pre/final tags 可解析；
- broken links、active archive references、unclassified paths、open P1/P2 均为 0；
- applicable gates pass；
- `p4_implementation_authorized` 仍为 `no_until_p4_entry_acceptance`。

### Conversation

**继续 Conversation D。** 完成后结束实现对话，不在 D 中执行最终独立验收。

## 13. C7 — Independent final acceptance

### Objective

独立判断 cleanup 是否减少默认上下文、保持 contract/evidence 可恢复、且没有把 P3/P4 边界
静默改变。

### Required inputs

- final candidate SHA 和 parent/base SHA；
- annotated pre/final tags；
- formal cleanup manifest 与 handoff；
- exact docs/code diff；
- test/static/container logs；
- C4 approved/deferred table；
- archive recovery commands/sample；
- worktree status。

### Audit checklist

1. tag/commit/path/hash identity 可复核；
2. active/normative docs 未被归档，contract 规则没有只留在 Git history；
3. P4 default index 不复制 owner semantics，默认读取量显著下降；
4. deleted/moved code 无 runtime/release/deployment consumer；
5. tests 没有因删除机制而削弱 public invariant；
6. Repository profile/harness disposition 与 Compose/runbook 一致；
7. R7 reference executor、Repository reconciliation 和 P4/P5 boundary 未漂移；
8. applicable source/static/container gates 与 current candidate 对齐；
9. `p3_exit: pass` 保持，P4 implementation 未被提前授权；
10. 无 open P1/P2、broken links、dirty worktree 或未分类残留。

### Decision

```yaml
p3_p4_cleanup_exit: pass | pending | blocked
p4_entry_context_ready: yes | no
p4_implementation_authorized: no_until_p4_entry_acceptance
```

### Conversation

**必须新开 Conversation E。不要返回编写本计划的当前对话作为正式最终审核。**

若 E 只要求机械 status/link 修正，回到 Conversation D 修改，再返回同一个 E 复核。若 E
要求重新分类或改变代码范围，原 candidate 作废；重新开实现对话，完成后再开新的独立验收
对话，不能让已有条件性结论自动升级为 pass。

## 14. Implementer handoff format

````markdown
# P3→P4 Cleanup Implementer Evidence Report

## Decision
- recommendation: PASS / BLOCK / REOPEN
- baseline_sha:
- candidate_sha:
- pre_cleanup_tag:
- final_cleanup_tag:
- worktree: clean/dirty

## Scope
- docs archived/deleted count:
- active docs retained count:
- code bundles changed:
- deferred bundles:
- public semantics changed: yes/no

## Context result
- P4 default index:
- default direct-read document count:
- active archive references:
- broken links:
- unclassified paths:

## Code disposition
| Path/symbol | Decision | Consumer evidence | Owner | Gate |
| --- | --- | --- | --- | --- |

## Verification
| Command | SHA | Exit | Result | Duration | Log |
| --- | --- | ---: | --- | ---: | --- |

## Container applicability
- rebuild required: yes/no
- reason:
- image identity/result:

## Recovery
- sample archived path:
- recovery command/result:
- manifest/hash match:

## Findings
- open P1:
- open P2:
- open P3/P4:
- deviations:

## Recommended status
```yaml
p3_exit: pass
p4_ready: yes
p3_p4_cleanup_exit: pending_independent_acceptance
p4_entry_context_ready: pending_independent_acceptance
p4_implementation_authorized: no_until_p4_entry_acceptance
```
````

## 15. Final stop conditions

立即停止删除并保留/恢复 candidate，如果出现：

- active contract/ADR/handoff 只能从 archive tag 找到；
- 归档后 active docs 存在断链或仍以过程文档为 authority；
- public import、entrypoint、Compose、operator runbook 或 release gate 使用待删代码；
- P3 digest/artifact/reference executor/cancellation/resource semantics 改变；
- Repository operation/reconciliation/cleanup authority 被移动到 P4；
- 为减少文件数而删除仍证明 contract invariant 的唯一测试；
- current candidate 缺少适用 container rebuild；
- open P1/P2、未知 dirty change、tag 不可恢复或 manifest/path/hash 不一致。

文件数量减少不是 pass 条件。只有默认检索面更小、authority 更清晰、行为证据不减弱且所有
删除可恢复时，本轮才可通过。
