# P2-R6-EXT-W1 Stage B — Independent Contract Review

状态：`fail`

日期：2026-08-16

本记录是 Stage B 的独立只读 Contract review。审核只回答“语义是否闭合、是否存在隐式
兼容层或未定义值”，不审实现风格，不修改生产代码，不自称可进入 Stage C。

权威计划：[P2-R6-EXT-W1 ENUM/SET Import Execution Plan](../formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md)
权威设计：[P2-R6-EXT-W1 ENUM/SET Import Design](../formal/plans/p2-r6-ext-w1-enum-set-import-design.md)
冻结包：[P2-R6-EXT-W1 Stage B Contract Freeze](p2-r6-ext-w1-stage-b-contract-freeze.md)
决策记录：[ADR 0013](../formal/adr/0013-enum-set-v1-import-semantics.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
reviewed_commit_sha: 2fe7b1fed1fd9c1702335071d4f28aa8be01e626
freeze_head_sha_claimed: 2fe7b1fed1fd9c1702335071d4f28aa8be01e626
s5_validated_candidate: e7a6e42d961a75c5a35a385bd67d9417779c22b5
s5_is_ancestor: yes
stage_a_head_is_ancestor: yes
freeze_committed: no
reviewed_worktree: uncommitted Stage B freeze docs + format samples
production_code_changed: no
full_s6_run: no
formal_package_generated: no
package_version: v1
canonicalization_version: v1
review_scope: contracts/ADR/design/plan/golden-format only
```

HEAD 与 freeze 声称的 `freeze_head_sha` 均为 Stage A 收口 `2fe7b1fe`。S5 候选
`e7a6e42d` 仍是祖先。冻结语义在 worktree，尚未形成 freeze commit。本审核针对该
worktree 冻结包，不把未提交文档当作已发布 identity。

## Required questions

1. ENUM/SET 是否已从 unknown/STRINGIFY 路径完全退出，且无第二套 spelling？
   **否。** 成功规范化后的 spelling 是唯一的，STRINGIFY 也不得降级**已识别**的
   ENUM/SET。但族判定未闭合：整段 grammar 匹配失败、声明重复、越界、SET 空
   label、剥离后残留 token（例如 `CHARSET` 相对 `CHARACTER SET`）仍可落入
   unknown，从而走 `large_string` + `gateway.lossy=true`。这是隐式兼容层。

2. NULL、空 ENUM label、空 SET、声明顺序、非法/重复成员是否各有唯一失败或唯一
   canonical 形态？
   **值侧基本闭合，类型侧不完整。** NULL / 已声明的 ENUM `''` / 空 SET /
   非空 SET 各有唯一 Arrow 与 content 形态；值内未知或重复成员为
   `SQL_VALUE_ILLEGAL`。声明重复成员只写“fail closed”，未绑定稳定码，也未禁止
   将其当作 unknown。

3. charset/collation 是否被明确排除出 v1 schema identity，且非 ASCII label 不再被
   ASCII unknown 门误拒？
   **意图明确，前提不成立。** 已知 ENUM/SET 不走 ASCII unknown 门，charset/
   collation 修饰符不进 schema identity。若拼写未进入已知族，仍会撞上该门。

4. SET `list<utf8>` 与 content sequence 是否可逆、无逗号拼接歧义？
   **值编码层是。** `list<utf8>` ↔ 声明顺序的 length-prefixed string scalar
   frames；空 SET 为 count=0 的 sequence，不得编码为 null；逗号文本只是 Dolt
   输入形态，禁止作为 content preimage。

5. digest 是否覆盖声明顺序与值，且仍是 canonicalization v1、无新 tag/无 v2？
   **覆盖意图成立，单元格槽位未定义。** schema digest 含 normalized `sql_type`
   （因此含声明顺序）；ENUM 用 `0x20`，SET 用既有 `sequence`；算法标识保持
   `gateway-vnext:canonicalization-manifest:v1`。SET 的 `sequence_frame` 如何进入
   CanonicalizationManifest 单元格 preimage（是否再包一层 scalar tag）没有唯一
   读法，digest bytes 会分叉。

## Findings

### [P1] 冻结 ENUM/SET 族判定，禁止任何族内拼写落入 unknown/STRINGIFY — `docs/backend-vnext/refactoring/formal/contracts/repository-service.md:380-443`

§10 把 ENUM/SET 列入 exact mapping，并写 STRINGIFY 不得降级它们。§10.1 只对双引号、
反引号、反斜杠转义、未闭合引号、尾随逗号、空成员表写明“malformed，不得降为
unknown”。其余失败（声明重复、成员数/label 长度越界、SET 空 label、整段匹配失败、
修饰符剥离后的残留 token）只有“fail closed”或保持沉默。

实现若把“未匹配 grammar”当成 unknown，STRINGIFY 会把它们写成 `large_string` +
`gateway.lossy=true`。这直接违反本轮“完全退出 STRINGIFY / 无第二套路径”的冻结目标，
也会让非 ASCII label 再次撞上未知 type 的 ASCII 门。

必须补上闭合判定，建议唯一读法：

```text
strip CHARACTER SET / COLLATE（与 CHAR/VARCHAR 相同）
折叠 label 外空白，使结果符合 §10.1 无空格逗号分隔
若类型 keyword 为 ENUM 或 SET（大小写不敏感的整词）：
  满足 grammar 与全部约束 → 唯一 normalized spelling，已知类型
  否则 → SQL_TYPE_MALFORMED
  永不 unknown，永不 STRINGIFY
否则 → 沿用既有 known/unknown 规则
```

声明重复、越界、SET 空 label、含逗号的 SET label、括号后残留 token 一律归入
`SQL_TYPE_MALFORMED`。

### [P1] 冻结 SET 单元格就是 `sequence_frame` 本身 — `docs/backend-vnext/refactoring/formal/contracts/shared-canonical-encoding.md:114-131` 与 `canonical-storage-and-repository-boundary.md:90-99`

值编码禁止逗号拼接、ordinal 和未规范化输入顺序，这是对的。Shared Kernel
`row_frame` 的字段槽位仍是 `scalar_frame`；CanonicalizationManifest 又说“每个值
使用 tagged frame”，并让 SET 使用 collection `sequence`。

未禁止的读法包括：把 `sequence_frame` 再包进另一个 scalar tag，或把它当作
`encode_row` 的字段。两种 bytes 不同，且后一种会碰到“改 row_frame 就要升
`canonical_encoding_version`”的禁令。

必须补一句，建议唯一读法：

```text
ENUM 单元格 = string 或 null 的 scalar_frame
SET NULL 单元格 = null scalar_frame
SET 非 null 单元格 = sequence_frame 本身，不再外包 scalar tag
表 content digest 的行/列拼接沿用 CanonicalizationManifest 既有 per-cell 规则
不使用 Shared Kernel encode_row，也不改变 Canonical Row Hash Arrow mapping v1
不升 canonical_encoding_version
```

### [P2] 将 `SQL_*` 稳定码映射到既有 wire，不新增 public import code — `docs/backend-vnext/refactoring/formal/contracts/repository-service.md:441-443` 与 `528-536`

Parser/golden 冻结了 `SQL_TYPE_MALFORMED` / `SQL_VALUE_ILLEGAL`。Import 的 public
stable code 仍只有 `IMPORT_REJECTED`、`EXPECTED_COMMIT_MISMATCH`、
`VERIFICATION_FAILED_NOT_PUBLISHED`、`MANUAL_RECOVERY_REQUIRED`。若不写映射，
Stage C 可能把 `SQL_TYPE_MALFORMED` 加成第五个 import code，或在 read 路径把它
标成 `UNKNOWN_SQL_TYPE`（后者会再次打开 STRINGIFY）。

必须写明：`SQL_*` 只用于 parser/converter/golden；不新增 public import/read code。
建议映射：编译/admission 的畸形类型 → `IMPORT_REJECTED`；FULL_SCAN 非法值 →
`VERIFICATION_FAILED_NOT_PUBLISHED`；read 在 response 开始后的转换失败沿用既有
body 终止规则。Read 编译期畸形 ENUM/SET 不得使用 `UNKNOWN_SQL_TYPE`。

## Non-findings

以下已闭合，不构成 blocker：

- 成功路径只有一套 normalized `sql_type`；禁止 labels JSON、dictionary、正式
  `large_string`、SET scalar 退路、`gateway.lossy`。
- NULL ≠ 空 SET ≠ 非空 SET；ENUM 空字符串仅当声明含 `''`。
- charset/collation 不进 schema identity；label 内 `collate` 仍是 label。
- SET 值按声明顺序重排；comma-text 只作 driver 输入。
- package/canonicalization 保持 v1；不新增 scalar tag；既有 128 个 Shared Kernel
  case 不变。
- Canonical Row Hash 继续拒绝 `list`；与 Repository import Arrow 分属不同 mapping。
- 五份 fixture 仍全部是 positive accepted cases；本轮无迁移/旧 package 兼容层。

## Residual risks（不阻断本轮修复清单）

- Dolt 若折叠 ENUM label 大小写，catalog/manifest exact match 仍以 Dolt 投影后的
  spelling 为准；这不构成第二套 Contract spelling。
- 受信 producer 不应写入非法 ENUM；Dolt 把非法值收成已声明 `''` 时，v1 只比较
  driver 给出的 UTF-8 字符串，不另建探测。
- SET comma-text 不 trim；`"a, b"` 仅当声明含 `" b"` 才合法。
- Label 含 ASCII control 时，JSON manifest 既有 control 门可能拒绝；五份正向
  fixture 预期不含该形态。若修复族判定，可顺手写明 label/sql_type 是否允许
  ASCII control，但不单列为本轮 blocker。

## Verdict

```yaml
review_status: fail
stage_b_exit: fail
blocker_count: 2
required_fix_count: 3
allow_stage_c: no
production_code_changed_by_review: no
next: return to Stage B freeze fix; then a new independent Contract review
must_fix_before_stage_c:
  - ENUM/SET family classification never unknown/STRINGIFY
  - SET content cell is sequence_frame with no extra scalar wrap
  - SQL_* map onto existing wire codes; no new public import code
```

修复后重新提交 freeze；新审核会话从修复 commit/worktree 复核 SHA，不假定本次
结论自动转为 pass。
