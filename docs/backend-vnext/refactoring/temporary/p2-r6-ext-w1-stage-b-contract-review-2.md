# P2-R6-EXT-W1 Stage B — Independent Contract Review (re-review)

状态：`pass`

日期：2026-08-16

本记录是 Stage B freeze-fix 之后的独立只读 Contract 复审。审核只回答“语义是否闭合、
是否存在隐式兼容层或未定义值”，不审实现风格，不修改生产代码。首次 fail 记录保持
不变，不把该 fail 自动转为 pass。

权威计划：[P2-R6-EXT-W1 ENUM/SET Import Execution Plan](../formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md)
权威设计：[P2-R6-EXT-W1 ENUM/SET Import Design](../formal/plans/p2-r6-ext-w1-enum-set-import-design.md)
冻结包：[P2-R6-EXT-W1 Stage B Contract Freeze](p2-r6-ext-w1-stage-b-contract-freeze.md)
首次审核（fail，保持不变）：[P2-R6-EXT-W1 Stage B Contract Review](p2-r6-ext-w1-stage-b-contract-review.md)
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
reviewed_worktree: uncommitted Stage B freeze docs + freeze-fix + format samples
production_code_changed: no
full_s6_run: no
formal_package_generated: no
package_version: v1
canonicalization_version: v1
review_scope: contracts/ADR/design/plan/golden-format only
prior_review_status: fail
prior_required_fix_count: 3
```

HEAD 与 freeze 声称的 `freeze_head_sha` 均为 Stage A 收口 `2fe7b1fe`。S5 候选
`e7a6e42d` 仍是祖先。冻结语义在 worktree，尚未形成 freeze commit。本审核针对该
worktree 冻结包（含三项必补修复），不把未提交文档当作已发布 identity。生产路径
相对 HEAD 无变更。

## Required questions

1. ENUM/SET 是否已从 unknown/STRINGIFY 路径完全退出，且无第二套 spelling？
   **是。** 剥离列级 `CHARACTER SET`/`COLLATE` 并折叠 label 外空白后，第一个整词
   为 ENUM/SET 则要么唯一 normalized spelling，要么 `SQL_TYPE_MALFORMED`。声明
   重复、越界、SET 空 label、含逗号的 SET label、整段不匹配、括号后残留 token
   （含 `CHARSET` 相对已剥离的 `CHARACTER SET`）、超 64 KiB 一律不得落入
   unknown，STRINGIFY 也不得写成 `large_string` + `gateway.lossy`。成功路径只有
   一套 keyword 大写、括号外无空格逗号分隔、label 精确 UTF-8 的 spelling。

2. NULL、空 ENUM label、空 SET、声明顺序、非法/重复成员是否各有唯一失败或唯一
   canonical 形态？
   **是。** NULL / 已声明的 ENUM `''` / 空 SET / 非空 SET 各有唯一 Arrow 与
   content 形态。声明重复为 `SQL_TYPE_MALFORMED`；值内未知或重复成员、ordinal、
   无法证明的 driver 形态为 `SQL_VALUE_ILLEGAL`。SET 输出按声明顺序，忽略输入
   顺序。

3. charset/collation 是否被明确排除出 v1 schema identity，且非 ASCII label 不再被
   ASCII unknown 门误拒？
   **是。** 列修饰符不进 schema identity；label 内 `collate` 仍是 label。族内拼写
   不走未知 type 的 ASCII charset 门。非 ASCII UTF-8 label 合法。

4. SET `list<utf8>` 与 content sequence 是否可逆、无逗号拼接歧义？
   **是。** Repository Arrow 为 `list<utf8>`（list 可空性来自 catalog/manifest，
   item 不可空）。content 非 null 单元格就是 `sequence_frame` 本身，item 为声明
   顺序的 string scalar frame；空 SET 为 count=0 的 sequence，不得编码为 null。
   逗号文本只是 Dolt 输入形态，禁止作为 content preimage。SET label 禁止逗号，
   从类型侧去掉拼接歧义。

5. digest 是否覆盖声明顺序与值，且仍是 canonicalization v1、无新 tag/无 v2？
   **是。** schema digest 含 normalized `sql_type`（因此含声明顺序）、nullable、
   PK。ENUM 单元格为 string/null `scalar_frame`；SET NULL 为 null scalar；SET
   非 null 为裸 `sequence_frame`，不再外包 scalar tag，也不走 `encode_row`。
   算法标识保持 `gateway-vnext:canonicalization-manifest:v1`。无新 scalar tag、
   无 `canonical_encoding_version` v2、无第五个 public import code。

## Prior required fixes

| 首次审核必补项 | 复审结论 |
| --- | --- |
| ENUM/SET 族判定永不 unknown/STRINGIFY | 已写入 [repository-service.md](../formal/contracts/repository-service.md) §10 / §10.1 |
| SET 单元格就是 `sequence_frame` 本身 | 已写入 [shared-canonical-encoding.md](../formal/contracts/shared-canonical-encoding.md) §3.2 与 [canonical-storage-and-repository-boundary.md](../formal/contracts/canonical-storage-and-repository-boundary.md) §4 |
| `SQL_*` 映射既有 wire，不新增 public import code | 已写入 §10.1 / §11 / §13；编译畸形 → `IMPORT_REJECTED`；FULL_SCAN 非法值 → `VERIFICATION_FAILED_NOT_PUBLISHED`；read 编译期畸形 → `REQUEST_VALIDATION_FAILED`，不得用 `UNKNOWN_SQL_TYPE` |

## Findings

No findings.

## Non-findings

以下已闭合，不构成 blocker：

- 成功路径只有一套 normalized `sql_type`；禁止 labels JSON、dictionary、正式
  `large_string`、SET scalar 退路、`gateway.lossy`。
- 族内失败与未知 type 分轨：前者永不 STRINGIFY，后者仍走既有 REJECT/STRINGIFY。
- Canonical Row Hash 继续拒绝 `list`；与 Repository import Arrow 分属不同 mapping。
- package/canonicalization 保持 v1；既有 128 个 Shared Kernel case 不变。
- 五份 fixture 仍全部是 positive accepted cases；本轮无迁移/旧 package 兼容层。
- JSON `manifest.json` ASCII control 门拒绝含 control 的 `sql_type` 是既有
  admission 层，不是第二套类型语义。

## Residual risks（不阻断 Stage C）

- Dolt 若折叠 ENUM label 大小写，catalog/manifest exact match 仍以 Dolt 投影后的
  spelling 为准；这不构成第二套 Contract spelling。
- 受信 producer 不应写入非法 ENUM；Dolt 把非法值收成已声明 `''` 时，v1 只比较
  driver 给出的 UTF-8 字符串，不另建探测。STRUCTURAL/NONE 不扫描值，非法值只在
  FULL_SCAN/read 转换失败。
- SET comma-text 按 `,` 拆分、不 trim；`"a, b"` 仅当声明含 `" b"` 才合法。文本
  `"a,"` 产生空成员，属于 `SQL_VALUE_ILLEGAL`。
- 若 Dolt catalog 在 ENUM/SET 上发出未剥离的 `CHARSET`、`BINARY` 或 charset
  introducer，族判定会 `SQL_TYPE_MALFORMED` 并 `IMPORT_REJECTED`。这是唯一读法，
  不是 unknown 回退。Stage C/F 必须用真实 catalog spelling 验证五份正向 fixture
  能通过该 grammar；若不能，回到 Stage B 修订剥离规则，不得为通过而 STRINGIFY。
- CanonicalizationManifest 表级行/列拼接仍引用既有 per-cell 规则；本轮只冻结
  ENUM/SET 单元格槽位。该拼接对其它已映射类型同样适用，不构成本轮隐式兼容层。
- 格式样例 `values.jsonl` 含未在 README 列出的 `payload_base64url`。Stage D 填充
  完整 case 时以 §2.1 / README 的 expected 形状为准。

## Verdict

```yaml
review_status: pass
stage_b_exit: pass
blocker_count: 0
required_fix_count: 0
allow_stage_c: yes
production_code_changed_by_review: no
freeze_committed: no
next: Stage C — Parser/model implementation; new session from this review + freeze worktree/commit
```

独立审核通过。允许进入 Stage C。新会话须先复核 SHA 与 worktree，不得假定本会话
状态；freeze 仍未形成 commit，Stage C 入口应基于本 worktree 或随后的 docs-only
freeze commit。未授权不得开始 Arrow/provider 之外的 Stage D–K 宣称。
