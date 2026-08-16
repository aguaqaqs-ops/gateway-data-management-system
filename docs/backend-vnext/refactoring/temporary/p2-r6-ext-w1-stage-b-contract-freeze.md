# P2-R6-EXT-W1 Stage B — Contract Freeze

状态：`review_pass`

日期：2026-08-16

本记录冻结 ENUM/SET v1 语义。没有修改生产代码，没有运行 S6，没有生成正式
package，也没有改写历史 S5 evidence。独立复审已通过，见
[P2-R6-EXT-W1 Stage B Contract Review 2](p2-r6-ext-w1-stage-b-contract-review-2.md)。

权威计划：[P2-R6-EXT-W1 ENUM/SET Import Execution Plan](../formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md)
权威设计：[P2-R6-EXT-W1 ENUM/SET Import Design](../formal/plans/p2-r6-ext-w1-enum-set-import-design.md)
决策记录：[ADR 0013](../formal/adr/0013-enum-set-v1-import-semantics.md)
首次审核（fail，保持不变）：[P2-R6-EXT-W1 Stage B Contract Review](p2-r6-ext-w1-stage-b-contract-review.md)
复审（pass）：[P2-R6-EXT-W1 Stage B Contract Review 2](p2-r6-ext-w1-stage-b-contract-review-2.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
stage_b_entry_head_sha: 2fe7b1fed1fd9c1702335071d4f28aa8be01e626
stage_a_entry_head_sha: 63b83779cbde2d88be132aee4f6d7700741cf54c
stage_a_commit: 2fe7b1fed1fd9c1702335071d4f28aa8be01e626
s5_validated_candidate: e7a6e42d961a75c5a35a385bd67d9417779c22b5
s5_is_ancestor: yes
production_code_changed: no
full_s6_run: no
formal_package_generated: no
package_version: v1
canonicalization_version: v1
published_package_compatibility: none
prior_review_status: fail
freeze_fix: three_required_items
```

Stage B 从 Stage A 收口 commit `2fe7b1fe` 开始。`63b83779` 与 S5 候选 `e7a6e42d`
仍是祖先。本会话只改 formal contracts/ADR/design/plan、fixture 格式样例和本记录。

本 freeze 的文档增量（相对 `2fe7b1fe`，不含生产代码）：

```text
docs/backend-vnext/refactoring/formal/adr/0013-enum-set-v1-import-semantics.md
docs/backend-vnext/refactoring/formal/contracts/canonical-row-hash-compute-boundary.md
docs/backend-vnext/refactoring/formal/contracts/canonical-storage-and-repository-boundary.md
docs/backend-vnext/refactoring/formal/contracts/fixture-oracle-and-conformance.md
docs/backend-vnext/refactoring/formal/contracts/repository-service.md
docs/backend-vnext/refactoring/formal/contracts/shared-canonical-encoding.md
docs/backend-vnext/refactoring/formal/plans/p2-r6-ext-w1-enum-set-import-design.md
docs/backend-vnext/refactoring/formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md
docs/backend-vnext/refactoring/formal/README.md
docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-b-contract-freeze.md
vnext/fixtures/vectors/repository/sql-enum-set/v1/
```

## Freeze summary

Owning contracts：

| 主题 | Owner |
| --- | --- |
| SQL grammar、族判定、catalog exact match、Repository Arrow、wire 映射 | [repository-service.md](../formal/contracts/repository-service.md) §10.1 |
| content 单元格 bytes（不新增 tag） | [shared-canonical-encoding.md](../formal/contracts/shared-canonical-encoding.md) §3.2 |
| CanonicalizationManifest schema/content 输入 | [canonical-storage-and-repository-boundary.md](../formal/contracts/canonical-storage-and-repository-boundary.md) §4 |
| Canonical Row Hash Arrow 仍拒绝 `list` | [canonical-row-hash-compute-boundary.md](../formal/contracts/canonical-row-hash-compute-boundary.md) §1 |
| golden JSONL 格式 | [fixture-oracle-and-conformance.md](../formal/contracts/fixture-oracle-and-conformance.md) §2.1 |

闭合规则：

- `ENUM`/`SET` 族判定：keyword 为 ENUM/SET 时要么唯一 normalized spelling，要么
  `SQL_TYPE_MALFORMED`。声明重复、越界、SET 空 label、整段不匹配、残留 token
  **不得**落入 unknown/STRINGIFY。
- 规范化 spelling 保留声明顺序与 label 精确 UTF-8；charset/collation 修饰符不进入
  schema identity。
- 非 ASCII label 合法；族内拼写不走未知 type 的 ASCII charset 门。ENUM/SET
  `sql_type` 上限 64 KiB。
- NULL、ENUM 空 label（仅当已声明）、空 SET、非空 SET 各有唯一形态。
- ENUM Arrow `utf8`；SET Arrow `list<utf8>`。metadata 仅 `gateway.logical_type` 与
  `gateway.sql_type`。禁止 `gateway.lossy`、dictionary、正式 `large_string`、SET
  scalar 退路。
- parser/golden 稳定码：`SQL_VALUE_ILLEGAL` / `SQL_TYPE_MALFORMED`。wire 映射到既有
  `IMPORT_REJECTED` / `VERIFICATION_FAILED_NOT_PUBLISHED`；read 编译期不得使用
  `UNKNOWN_SQL_TYPE`。不新增第五个 public import code。
- content 单元格：ENUM = string/null `scalar_frame`；SET 非 null = `sequence_frame`
  本身，不再外包 scalar tag；不走 `encode_row`。算法标识保持
  `gateway-vnext:canonicalization-manifest:v1`。无 v2、无新 tag。
- 既有 128 个 Shared Kernel case 不变。新 corpus：
  `vnext/fixtures/vectors/repository/sql-enum-set/v1/`（本 stage 仅格式样例）。

明确拒绝：旧 package wire 兼容、STRINGIFY 作为 W1 替代、「先 stringify 再 parse」、
dictionary 业务值、静默 ordinal、族内 unknown 回退。五份 fixture 仍全部是 positive
accepted cases。

```yaml
R6-EXT-W1: no
P2-R6-S6_ready: no
canonicalization_manifest_digest: not_computed
container_rebuild_required_for_this_docs_commit: no
production_retest_required: yes
phase_2_complete: no
must_not_start_until_later_stages:
  - Arrow/provider/verification production code  # Stage D after C
  - five-fixture package generation
  - production validator execution
  - S6 capacity, W2, concurrency matrix
  - image rebuild as EXT-W1 proof
allow_stage_c: yes
```

## Independent Contract review

首次审核为 fail，记录保持不变。三项必补修复后由新开只读会话复审通过。

```yaml
prior_review_status: fail
prior_review_record: docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-b-contract-review.md
freeze_fix_applied:
  - ENUM/SET family classification never unknown/STRINGIFY
  - SET content cell is sequence_frame with no extra scalar wrap
  - SQL_* map onto existing wire codes; no new public import code
review_status: pass
review_record: docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-b-contract-review-2.md
stage_b_exit: pass
allow_stage_c: yes
```
