# P2-R6-EXT-W1 ENUM/SET Import Execution Plan

状态：Stage K complete; R6-EXT-W1 handoff pass; phase_2_complete = no

日期：2026-08-16

关联设计：[P2-R6-EXT-W1 ENUM/SET Import Design](p2-r6-ext-w1-enum-set-import-design.md)

本文件是从当前 `not_ready` 状态到 production-package validator gate 的权威执行计划。
每个 stage 明确是否在同一会话继续、是否必须新开会话、审核点、产物和退出条件。任务提示词
只用于推进当前 stage，不替代本文件的 Contract 或验收标准。

## 0. 固定入口和不变量

```yaml
branch: phase1/gate-ownership-repair
current_head_at_planning: 63b83779cbde2d88be132aee4f6d7700741cf54c
s5_validated_candidate: e7a6e42d961a75c5a35a385bd67d9417779c22b5
current_status: R6-EXT-W1=yes; P2-R6-S6_ready=yes
published_package_compatibility: none
package_version: v1
canonicalization_version: v1
current_fixture_count: 5
current_hard_cap: at least 200MB, configurable
```

不得修改历史 S5 evidence、伪造 digest、把 Dolt preflight 写成 S6 PASS，或为当前五份数据
设置 rejection 预期。所有新 evidence 绑定实际 candidate SHA；外部 descriptor 继续只发布
脱敏摘要。

## 1. 会话和审核规则

- **同一会话继续**：纯只读检查、同一 stage 内的局部实现、focused unit tests 和文档更新。
- **新开会话**：跨越 Contract 决策、production validator gate、S6 capacity、W2、container
  rebuild 或审核结论的边界。新会话必须从上一 stage 的 commit/evidence 开始，先复核 SHA 和
  worktree，不假定上次会话状态。
- **独立审核**：Contract freeze、validator gate、最终 candidate/container gate 各有一个
  独立审核 stage；审核阶段只读，不顺手修改生产代码。
- **发现 blocker**：回到指定的实现 stage，形成修复 commit，再重新执行受影响的审核 stage；
  不在审核阶段直接扩大范围。

## 2. Stage A — Entry reconciliation

会话：新开会话；这是本计划的第一步。

任务：

- 复核当前 branch、HEAD、S5 ancestor、worktree clean；
- 复核 readiness record、外部 descriptor、medium/data2 摘要；
- 清点当前五份测试数据及其 size/SHA，确认均应落在当前至少 200MB hard cap 内；
- 记录分层容量配置和未来提高上限时的重测规则；
- 不运行 full S6，不生成正式 package。

产物：entry reconciliation record，包含 current HEAD、fixture matrix、配置快照和未决实现
范围。

退出条件：入口身份一致、五份 fixture 可定位、没有新的 blocker。

推进提示词：`复核入口 SHA、五份 fixture 和容量配置，生成 Entry reconciliation record。`

完成记录：[P2-R6-EXT-W1 Stage A Entry Reconciliation](../../temporary/p2-r6-ext-w1-stage-a-entry-reconciliation.md)

```yaml
stage_a_exit: pass
entry_head_sha: 63b83779cbde2d88be132aee4f6d7700741cf54c
five_fixtures_locatable: yes
new_blocker: no
```

## 3. Stage B — Contract design freeze

会话：Stage A 完成后新开会话。

任务：

- 定稿 ENUM/SET parser grammar、规范化 spelling、声明顺序和 collation 边界；
- 定稿 NULL/空值/非法值/重复成员行为；
- 定稿 Arrow representation 和 metadata；
- 定稿 schema/content canonical bytes、表列行排序和 digest 输入；
- 确认保持 package/canonicalization v1，不引入兼容字段或 v2 分支；
- 更新 Contract/ADR/design 文档和共享 golden vector 格式。

审核：独立 Contract review。审核只回答“语义是否闭合、是否存在隐式兼容层或未定义值”，
不审实现风格。

退出条件：Contract review 明确通过，或列出必须修复的有限问题；未通过不得进入生产代码。

推进提示词：`冻结 ENUM/SET v1 语义、Arrow 表示、digest 和异常规则，提交 Contract review。`

完成记录：[P2-R6-EXT-W1 Stage B Contract Freeze](../../temporary/p2-r6-ext-w1-stage-b-contract-freeze.md)

```yaml
stage_b_status: review_pass
stage_b_exit: pass
freeze_head_sha: d03e8e94ff8ab10658050559a52beb350fdd8dd3
freeze_committed: yes
production_code_changed: no
prior_review_record: docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-b-contract-review.md
prior_review_status: fail
rereview_record: docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-b-contract-review-2.md
rereview_status: pass
next: Stage C — Parser/model implementation
```

独立审核只读；`stage_b_exit: pass` 只能由新开审核写入。首次审核为 `fail`，三项缺口
已补入 owning contract，复审通过。允许进入 Stage C。

## 4. Stage C — Parser/model implementation

会话：Contract review 通过后新开会话；同一会话内完成实现与 focused unit tests。

任务：

- 更新 contracts/model 和 manifest validation；
- 实现 ENUM/SET 的 bounded parser 与规范化；
- 拒绝 malformed、越界、重复或无法证明的类型和值；
- 为纯解析/校验逻辑增加参数化 unit tests，不创建 Dolt fixture；
- 保持 package v1，删除不再需要的临时 unknown-type workaround。

验证：

```bash
cd vnext/repository_service
uv run pytest -m unit tests/test_p2_r1_primitives.py tests/test_arrow_mapping_plan.py tests/test_import_package.py
```

退出条件：parser/model unit tests 通过，Contract 字段和错误映射一致。

推进提示词：`实现 ENUM/SET parser、manifest model 和 unit tests，保持 v1 单一语义。`

完成记录：[P2-R6-EXT-W1 Stage C Parser/Model](../../temporary/p2-r6-ext-w1-stage-c-parser-model.md)

```yaml
stage_c_exit: pass
stage_c_entry_head_sha: d03e8e94ff8ab10658050559a52beb350fdd8dd3
freeze_commit_sha: d03e8e94ff8ab10658050559a52beb350fdd8dd3
focused_unit: 235 passed
repository_service_unit: 1376 passed, 1 skipped
ruff_mypy: pass
image_rebuilt: no
production_code_changed: yes
next: Stage D — Arrow/provider/verification implementation
```

parser/model 与 focused/unit 已通过。ENUM/SET 为已知类型；族内失败不再落入
unknown/STRINGIFY。verification/read wire、golden 完整 case 与五份 package 属于
Stage D。

## 5. Stage D — Arrow/provider/verification implementation

会话：Stage C 完成后可同一会话继续；若触及跨包 contract，则新开会话并重新复核入口 SHA。

任务：

- 实现 Arrow schema/value conversion；
- 实现 SET 声明顺序 canonicalization、NULL/empty distinction 和非法值 fail-closed；
- 让 catalog、STRUCTURAL、FULL_SCAN 共用同一 compiled mapping；
- 更新 producer、manifest validator 和 verification error mapping；
- 增加 Python/其他 producer-consumer 的 golden vectors；
- 补充 no-lossy-stringify 断言和 metadata 检查。

验证：

```bash
cd vnext/repository_service
uv run pytest -m unit
```

退出条件：全部 unit tests 通过，mapping 不再把 ENUM/SET 判为 unknown，golden vectors 稳定。

推进提示词：`完成 Arrow、provider、verification 和跨语言 golden vectors，运行 repository_service unit。`

完成记录：[P2-R6-EXT-W1 Stage D Arrow/Provider/Verification](../../temporary/p2-r6-ext-w1-stage-d-arrow-provider-verification.md)

```yaml
stage_d_exit: pass
stage_d_entry_head_sha: 8425c41b85bfee3ade8c5b4320ada003e19beabb
stage_c_commit: 8425c41b85bfee3ade8c5b4320ada003e19beabb
focused_unit: not_separately_gated
repository_service_unit: 1408 passed, 1 skipped
shared_kernel_values_golden: 10 passed
rust_values_golden: pass
canonical_128_case_corpus: unchanged
ruff_mypy: pass
image_rebuilt: no
production_code_changed: yes
golden_corpus_filled: yes
verification_wire_updated: yes
next: Stage E — Implementation review
```

verification/read wire 已把 `SQL_TYPE_MALFORMED` 映到既有 public code。golden 25 case
稳定；Shared Kernel 只消费 `values.jsonl` encode bytes。五份 package 属于 Stage F。

## 6. Stage E — Implementation review

会话：必须新开独立审核会话；只读检查，不直接修改代码。

审核内容：

- 是否存在第二套类型语义、隐式 stringify 或兼容分支；
- digest 是否覆盖所有权威 schema/content facts；
- NULL、空 SET、声明顺序、排序、非法值是否都有唯一测试 owner；
- 是否违反比例化保障和“新项目无迁移”原则；
- 是否引入不必要的 image/deployment boundary 变化。

产物：implementation review record，包含 reviewed SHA、发现项、是否允许进入数据验证。

退出条件：无 blocker finding；否则回到 Stage C/D 修复后重新审核。

推进提示词：`只读审核 ENUM/SET 实现、digest、测试 owner 和 v1 架构边界。`

完成记录：[P2-R6-EXT-W1 Stage E Implementation Review](../../temporary/p2-r6-ext-w1-stage-e-implementation-review.md)

```yaml
stage_e_exit: pass
reviewed_commit_sha: 8425c41b85bfee3ade8c5b4320ada003e19beabb
stage_c_commit: 8425c41b85bfee3ade8c5b4320ada003e19beabb
stage_d_committed: yes
reviewed_worktree: Stage D included in closing commit
s5_is_ancestor: yes
blocker_count: 0
allow_stage_f: yes
production_code_changed_by_review: no
image_rebuilt: no
next: Stage F — Five-fixture package generation
```

独立审核只读；`stage_e_exit: pass` 只能由新开审核写入。无 blocker finding。允许进入
Stage F。新会话须从本收口 commit 复核 SHA 与 worktree，不得假定上次会话状态。

## 7. Stage F — Five-fixture package generation

会话：implementation review 通过后新开会话。

任务：

- 对当前五份 fixture 逐一执行 source integrity 和 Dolt replay；
- 使用正式 producer 生成 package；
- 计算 package size/SHA、manifest digest、schema/content summary；
- 记录分层容量配置、临时目录、清理结果和运行时版本；
- 不把 replay preflight 或 package generation 单独宣称为 validator pass。

要求：五份 fixture 全部是 positive accepted cases；不能通过替换 SQL 类型、过滤列或 stringify
来规避失败。

退出条件：五份 package 均生成，摘要和 digest 可复现，临时资源清零。

推进提示词：`用正式 producer 为五份 fixture 生成 v1 package 和可复现 digest。`

完成记录：[P2-R6-EXT-W1 Stage F Five-fixture Packages](../../temporary/p2-r6-ext-w1-stage-f-five-fixture-packages.md)

```yaml
stage_f_exit: pass
stage_f_entry_head_sha: 02502f9aaf69d1c7573b9e0b4212b8b3a18e286d
stage_e_reviewed_commit_sha: 8425c41b85bfee3ade8c5b4320ada003e19beabb
five_packages_generated: yes
small_cut_reproduced: yes
production_validator_result: not_run
image_rebuilt: no
temp_resources_cleared: yes
next: Stage G — Production validator execution
```

五份 v1 package 已生成，digest 可复现，临时 Dolt HOME 已清零。未运行 production
validator，未宣称 S6 PASS。新会话须从本收口 worktree/commit 复核 SHA，不得假定
上次会话状态。

## 8. Stage G — Production validator execution

会话：Stage F 后新开会话；这是本轮的主要验收执行阶段。

任务：

- 对五份 package 运行 production `validate_and_extract_import_package()`；
- 验证 manifest/catalog exact match、Arrow schema、row count、raw SHA/size；
- 验证 ENUM/SET 不触发 unknown/unmappable 或隐式 stringify；
- 验证 validator failure 时无 Dolt commit/ref effect；
- 复核 package reopen、截断、digest 错误和错误 metadata 的拒绝语义；
- 形成 per-fixture validator report 和待审核的 aggregate report。

退出条件：五份全部产生 validator 结果，package、candidate 和配置引用完整；尚未发布 gate
通过结论。

推进提示词：`运行五份正式 package 的 production validator，生成待审核的 validator evidence。`

完成记录：[P2-R6-EXT-W1 Stage G Production Validator](../../temporary/p2-r6-ext-w1-stage-g-production-validator.md)

```yaml
stage_g_exit: pass
stage_g_entry_head_sha: b11922135b30c70af668218fd558d0c77138a3c2
stage_f_commit_sha: b11922135b30c70af668218fd558d0c77138a3c2
five_packages_validated: yes
full_scan_reject: pass
enum_set_unknown_or_lossy: no
negative_probes: pass
production_validator_result: pending_review
gate_published: no
image_rebuilt: no
temp_resources_cleared: yes
next: Stage H — Validator gate review
```

五份 package 均通过 production extract 与 FULL_SCAN+REJECT。ENUM/SET 无 unknown /
lossy。失败探针证明截断/digest/metadata 拒绝且无 main/private-ref 效果。未发布
gate 通过结论，未宣称 S6 PASS。新会话须从本收口 worktree/commit 复核 SHA，不得
假定上次会话状态。

## 9. Stage H — Validator gate review

会话：必须新开独立审核会话；只读审核，不直接修复生产代码或重跑未授权的容量测试。

审核内容：

- 五份 validator 结果是否全部 PASS；
- manifest/catalog exact match、Arrow schema、row count、raw SHA/size 是否闭合；
- ENUM/SET 是否没有 unknown/unmappable 或隐式 stringify；
- validator failure/no-effect、reopen、截断、digest 错误和 metadata 错误证据是否充分；
- candidate SHA、package SHA、配置快照和运行时版本是否一致；旧 image 结果不得替代当前 HEAD。

产物：独立 validator gate review record。

退出条件：审核通过后正式发布 `canonicalization_manifest_digest` 到本轮 evidence，并将
`P2-R6-S6_ready` 改为 `yes`（仍不代表 S6 capacity PASS）；发现 blocker 则回到 Stage C、D
或 G，修复后重新执行受影响阶段。

推进提示词：`只读审核五份 validator evidence，确认 package gate 通过并发布 v1 digest。`

完成记录：[P2-R6-EXT-W1 Stage H Validator Gate Review](../../temporary/p2-r6-ext-w1-stage-h-validator-gate-review.md)

```yaml
stage_h_exit: pass
reviewed_commit_sha: 7f068a2454addaded6eecd450e05571d6c939e8c
stage_g_commit_sha: 7f068a2454addaded6eecd450e05571d6c939e8c
five_packages_validated: yes
full_scan_reject: pass
enum_set_unknown_or_lossy: no
negative_probes: pass
gate_published: yes
production_validator_result: pass
P2-R6-S6_ready: yes
R6-EXT-W1: no
s6_capacity: not_run
blocker_count: 0
production_code_changed_by_review: no
image_rebuilt: no
next: Stage I — S6 capacity and W2 handoff
```

独立审核只读；`stage_h_exit: pass` 只能由新开审核写入。无 blocker finding。五份
v1 digest 已发布到本轮 evidence，`P2-R6-S6_ready=yes`。仍不代表 S6 capacity
PASS。新会话须从本收口 commit 复核 SHA 与 worktree，不得假定上次会话状态。

## 10. Stage I — S6 capacity and W2 handoff

会话：Stage H review 通过后新开会话。

任务：

- 在五份正向 fixture 上执行 S6 capacity；
- 记录 raw/package/decoded/batch/staging 各层资源；
- 执行规定的 concurrency matrix；
- 选择并验证 W2，保持同一 v1 Contract；
- 超限样本若未来加入，只验证 admission rejection，不改变当前五份 fixture 的 positive 结果。

退出条件：S6 capacity、W2 和 concurrency matrix 分别有独立 evidence；任何容量失败回到
容量配置或实现 stage，不修改 Contract 以掩盖问题。

推进提示词：`在 validator gate 通过的五份 package 上执行 S6 capacity、W2 和 concurrency matrix。`

完成记录：

- [P2-R6-EXT-W1 Stage I S6 Capacity](../../temporary/p2-r6-ext-w1-stage-i-s6-capacity.md)
- [P2-R6-EXT-W1 Stage I W2](../../temporary/p2-r6-ext-w1-stage-i-w2.md)
- [P2-R6-EXT-W1 Stage I Concurrency Matrix](../../temporary/p2-r6-ext-w1-stage-i-concurrency-matrix.md)

```yaml
stage_i_exit: pass
stage_i_entry_head_sha: 108cb90d75884acfd6c6f9cd388edc9c20a33aaf
stage_h_reviewed_commit_sha: 7f068a2454addaded6eecd450e05571d6c939e8c
s5_validated_candidate: e7a6e42d961a75c5a35a385bd67d9417779c22b5
s6_capacity: pass
w2: pass
concurrency_matrix: pass
R6-EXT-W1: yes
P2-R6-S6_ready: yes
contract_changed: no
image_rebuilt: no
next: Stage J — Final image and lifecycle gates
```

五份正向 package HTTP FULL_SCAN 全部 accepted。synthetic W2 replay 201681690 bytes
（192.3 MiB，180–199 MiB 带内、低于 200 MiB cap），v1 package HTTP FULL_SCAN pass。
concurrency 1/4/8 与第 9 路 `503 SERVICE_NOT_READY` pass；8 路 import
`peak_running=4`。未改 Contract，未重建 image。

## 11. Stage J — Final image and lifecycle gates

会话：所有 production code、Contract 和测试定稿后新开会话。

任务：

- 运行五个包的 ruff 与 mypy；
- 运行 focused、unit、integration、serial 测试；
- 按当前 HEAD 重建 image；
- 运行 Compose lifecycle、S7 和必要的 S10 final gates；
- 记录 image revision、source-tree SHA、lockfile/input identity 和全部 gate 结果。

退出条件：当前 HEAD 的 image/container evidence 完整，不能引用旧 image 作为最终证明。

推进提示词：`重建当前 HEAD image，执行全量质量检查、Compose lifecycle、S7 和 S10 final gates。`

完成记录：[P2-R6-EXT-W1 Stage J Final Image and Lifecycle](../../temporary/p2-r6-ext-w1-stage-j-final-image-lifecycle.md)

```yaml
stage_j_exit: pass
stage_j_entry_head_sha: 656a66bf04714cce987c85649246c3767b2586e2
stage_i_close_sha: 656a66bf04714cce987c85649246c3767b2586e2
s5_validated_candidate: e7a6e42d961a75c5a35a385bd67d9417779c22b5
image_rebuilt: yes
image_id: sha256:57e2ec06eaf2201f8d97fa96b6951429c85670ccfa040bc51275dfd29a281296
image_matches_build_context: true
five_package_ruff_mypy: pass
source_run_tests: pass
compose_restart_replay: pass
small_cut_container_full_scan: pass
enum_set_unknown_or_lossy: no
phase_2_complete: no
production_code_changed: no
next: Stage K — Final handoff
```

当前 HEAD image 已重建并拉回本机。五包 ruff/mypy 与
`run-tests.sh --ignore=tests/test_import_compose_e2e.py` 通过。Compose restart/replay
与 small_cut 容器 FULL_SCAN+REJECT 通过，ENUM/SET unknown/lossy=0。未宣称
Phase 2 完成；缺失的 versioned-read compose e2e、restored snapshot 与 v8 formal
仍归 P2-R6-S7/S10。新会话须从本收口 commit 复核 SHA 与 worktree，不得假定
上次会话状态。

## 12. Stage K — Final handoff

会话：必须新开独立审核会话。

审核内容：

- 五份 fixture、package、digest、validator、capacity、W2、container evidence 是否闭合；
- 历史 S5 evidence 是否保持不变；
- readiness、external descriptor、candidate/image SHA 是否一致；
- 是否仍有未声明的 blocker 或 deferred retest；
- `phase_2_complete` 是否满足现有 testing conventions。

产物：final handoff record、更新后的状态结论和脱敏 external descriptor（如需发布）。

推进提示词：`只读审核最终 candidate、五份数据、validator/capacity/container evidence 并形成 handoff。`

完成记录：[P2-R6-EXT-W1 Stage K Final Handoff](../../temporary/p2-r6-ext-w1-stage-k-final-handoff.md)
脱敏 descriptor：[P2-R6-EXT-W1 external descriptor](../../temporary/p2-r6-ext-w1-external-descriptor.yaml)

```yaml
stage_k_exit: pass
stage_k_reviewed_documentation_head_sha: 352d9097ddf26fb3e68397430f45d2e479473e51
container_validated_code_sha: 656a66bf04714cce987c85649246c3767b2586e2
image_id: sha256:57e2ec06eaf2201f8d97fa96b6951429c85670ccfa040bc51275dfd29a281296
R6-EXT-W1: yes
P2-R6-S6_ready: yes
validator_gate: pass
s6_capacity: pass
w2: pass
concurrency_matrix: pass
container_gate_for_validated_code: pass
history_s5_unchanged: yes
new_blocker_count: 0
phase_2_complete: no
production_retest_required: yes
deferred_scope: P2-R6-S7/S10 versioned-read, restored snapshot, v8 formal
next: P2-R6-S7/S10 operational closure
```

Stage K 确认五份正向 fixture、v1 package/digest、production validator、S6/W2/concurrency
与 Stage J image/container evidence 闭合；历史 S5 evidence 未变更。Stage J image 绑定
`656a66bf` 的 production candidate，Stage K 仅新增文档和脱敏 descriptor，不把文档 SHA
冒充 image candidate。`phase_2_complete=no` 保持不变，未完成的 S7/S10 gate 继续由
P2-R6 Operational Closure 负责。
