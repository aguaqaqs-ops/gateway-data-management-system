# P2-R6-EXT-W1 Stage E — Independent Implementation Review

状态：`pass`

日期：2026-08-16

本记录是 Stage C/D 实现之后的独立只读 implementation review。审核只回答执行计划
Stage E 的五个问题，不审实现风格，不修改生产代码，不运行 S6，不生成正式 package，
不重建 image。

权威计划：[P2-R6-EXT-W1 ENUM/SET Import Execution Plan](../formal/plans/p2-r6-ext-w1-enum-set-import-execution-plan.md)
权威设计：[P2-R6-EXT-W1 ENUM/SET Import Design](../formal/plans/p2-r6-ext-w1-enum-set-import-design.md)
决策记录：[ADR 0013](../formal/adr/0013-enum-set-v1-import-semantics.md)
Contract：[Repository Service](../formal/contracts/repository-service.md) §10.1
Stage C 记录：[P2-R6-EXT-W1 Stage C Parser/Model](p2-r6-ext-w1-stage-c-parser-model.md)
Stage D 记录：[P2-R6-EXT-W1 Stage D Arrow/Provider/Verification](p2-r6-ext-w1-stage-d-arrow-provider-verification.md)

## Entry identity

```yaml
branch: phase1/gate-ownership-repair
reviewed_commit_sha: 8425c41b85bfee3ade8c5b4320ada003e19beabb
stage_c_commit: 8425c41b85bfee3ade8c5b4320ada003e19beabb
stage_d_entry_head_sha: 8425c41b85bfee3ade8c5b4320ada003e19beabb
freeze_commit_sha: d03e8e94ff8ab10658050559a52beb350fdd8dd3
s5_validated_candidate: e7a6e42d961a75c5a35a385bd67d9417779c22b5
s5_is_ancestor: yes
freeze_is_ancestor: yes
stage_d_committed: no
reviewed_worktree: uncommitted Stage D Arrow/wire/golden + Stage D completion record
production_code_changed_by_review: no
full_s6_run: no
formal_package_generated: no
package_version: v1
canonicalization_version: v1
image_rebuilt: no
container_rebuild_required: no
review_scope: ENUM/SET parser, Arrow mapping, verification/read wire, golden, tests
```

HEAD 为 Stage C commit `8425c41b`。S5 候选 `e7a6e42d` 与 freeze `d03e8e94` 仍是祖先。
Stage D 实现在 worktree，尚未形成 commit。本审核针对该 worktree 实现（含 verification
/read wire 与 `sql-enum-set/v1` 25 case），不把未提交代码当作已发布 identity。

## Required questions

1. 是否存在第二套类型语义、隐式 stringify 或兼容分支？
   **否。** 族判定只产出唯一 normalized spelling 或 `SQL_TYPE_MALFORMED`。合法 ENUM
   为 `utf8`，SET 为 `list<utf8>`（item 不可空）；STRINGIFY 不得把族内类型写成
   `large_string` + `gateway.lossy`。畸形类型在 STRINGIFY 下仍是 `IMPORT_REJECTED`，
   不走 unmappable。W0 unknown 探针已改为 `YEAR`。`package_version` 锁死 `1`；无 v2
   字段、无旧 package 迁移层。Canonical Row Hash 仍拒绝 `list`。STRINGIFY 继续服务
   YEAR 等未知类型，以及既有 §12 `NONE+STRINGIFY` 不读 catalog；这不是 ENUM/SET
   第二套语义。畸形 ENUM/SET 由 package admission 与 `NONE+REJECT` / STRUCTURAL
   compile 覆盖。

2. digest 是否覆盖所有权威 schema/content facts？
   **cell 与 schema wire 已覆盖；package digest assembler 属于 Stage F。** schema
   identity 含 normalized `sql_type`（因此含声明顺序）、nullable、PK；charset /
   collation 不进 identity。Manifest 与 STRUCTURAL exact-match 比较这些字段。content
   单元格：ENUM 为 string/null `scalar_frame`；SET NULL 为 null scalar；SET 非 null
   为裸 `sequence_frame`（`encode_collection(SEQUENCE)`），空 SET 为 count=0 的
   sequence，不得写成 null，不走 `encode_row`。算法标识保持
   `gateway-vnext:canonicalization-manifest:v1`。128-case Shared Kernel corpus 未改。
   Repository 生产 `src/` 不 import Shared Kernel。`canonicalization_manifest_digest`
   对 Repository 仍是 opaque；树上没有 CanonicalizationManifest 生产 assembler。

3. NULL、空 SET、声明顺序、排序、非法值是否都有唯一测试 owner？
   **是，按语义屏障分层。** parser / Arrow / wire / content bytes 不是互相竞争的
   矩阵。权威 owner：

   - NULL vs 空 SET（Arrow）：`test_enum_set_record_batch_null_empty_and_metadata`
   - 已声明 ENUM `''` vs 未声明空串：`test_enum_set_legal_values_and_null_empty_distinction`
     与 `ENUM_SET_ILLEGAL_VALUES`
   - 声明顺序即 schema identity：`test_enum_set_declaration_order_is_identity`
   - SET 值按声明顺序、忽略输入顺序：同上 legal-values 测试
   - 非法值 fail-closed：`test_enum_set_illegal_values_fail_closed`
   - 畸形类型永不 unknown：`test_enum_set_malformed_type_never_unknown`
   - 编译畸形即使 STRINGIFY → `IMPORT_REJECTED`：
     `test_compile_malformed_enum_set_is_import_rejected_even_under_stringify`
   - read 编译期畸形 → `REQUEST_VALIDATION_FAILED`：`test_rows_preflight_error_matrix`
   - SET content 裸 sequence / 空 SET 非 null：golden `values.set.empty-not-null` /
     `values.set.null` 与 Shared Kernel Python/Rust consumers
   - catalog/STRUCTURAL/FULL_SCAN 共用 `compile_table_plan`：
     `test_full_scan_enum_set_batch_contract_matches_compiled_plan`
   - 无 `gateway.lossy` / dictionary / `large_string`：record-batch metadata 测试与
     `test_stringify_does_not_degrade_known_types`

   未发现仍把合法 ENUM/SET 当 unknown 的 stale 预期。Golden 25 case 稳定；`set-text`
   不进 `values.jsonl`，因为 Shared Kernel 不解释 SQL。行/表排序沿用既有 Contract，
   本轮未改 producer 排序。

4. 是否违反比例化保障和“新项目无迁移”原则？
   **否。** 直接修订现有 v1，无兼容字段、无 migration、无第五个 public import code。
   未新增 UID/helper/IPC/sidecar/evidence 状态机。Canonical Row Hash 不因 import
   `list<utf8>` 扩 mapping。畸形/非法值用参数表；纯解析未引入 `dolt init`。

5. 是否引入不必要的 image/deployment boundary 变化？
   **否。** Stage C/D 未改 Dockerfile、Compose、lockfile、entrypoint。本轮 image
   rebuild 延期到 Stage J；旧镜像不得表述为当前 HEAD 已验证。

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
- golden 与 unit 参数表、以及 `test_p2_r1_primitives.py` 的 known/unknown 探针对
  同一屏障有 smoke / 跨语言 conformance 重叠。它们不是第二套语义；审核阶段不删
  测试、不扩矩阵。
- Repository 测试专用 `sql_enum_set_frames.py` 只重建 §3.2 bytes，生产 `src/` 不
  import Shared Kernel。Shared Kernel 生产 primitive 独立消费同一 `values.jsonl`。

## Residual risks（不阻断 Stage F）

- Stage D 尚未形成 commit。新会话必须先提交当前 worktree，再从该 SHA 开始 Stage F，
  不得把本 worktree 当作已发布 identity。
- 正式 package digest assembler 不在树内。Stage F producer 必须用 Shared Kernel
  `encode_typed_scalar` / `encode_collection(SEQUENCE)`，禁止把
  `tests/support/sql_enum_set_frames.py` 当生产路径，也禁止 `encode_row`。
- 真实 Dolt SHOW CREATE 若带列级 `CHARSET`、`BINARY` 或 charset introducer：族判定
  fail-closed，不得 STRINGIFY。`CHARACTER SET` 作为 DDL tail 时，既有
  `_consume_column_modifiers` 不消费该修饰符；medium 的 328 列 ENUM 在 readiness
  已能被 catalog 读到，说明当前五份大概率不是该形态。若 Stage F 撞上，修 DDL
  修饰符或回到 Stage B 修订剥离规则。
- SET comma-text 按 `,` 拆分、不 trim；Dolt 若给出 int bitmask 或 tuple，v1
  fail-closed。
- 受信 producer 不应写入非法 ENUM；Dolt 把非法值收成已声明 `''` 时，v1 只比较
  driver 给出的 UTF-8 字符串。STRUCTURAL/NONE 不扫描值，非法值只在 FULL_SCAN/read
  转换失败。
- `test_p2_r1_primitives.py` / 部分 verification 函数名仍带 round 或 `unknown`，
  行为已不是 unknown；STRUCTURAL 无 ENUM 专测、package 测不断言 version 轴。不回
  Stage C/D 为这些缺口扩矩阵。

## Verdict

```yaml
review_status: pass
stage_e_exit: pass
blocker_count: 0
required_fix_count: 0
allow_stage_f: yes
production_code_changed_by_review: no
stage_d_committed: no
image_rebuilt: no
container_rebuild_required: no
next: Stage F — Five-fixture package generation; new session from Stage D commit
```

独立审核通过。允许进入 Stage F 数据验证。新会话须先复核 SHA 与 worktree，不得假定
本会话状态；Stage D 仍未形成 commit，Stage F 入口应基于随后的 Stage D commit。未授权
不得开始 production validator、S6 capacity、W2 或 container rebuild 宣称。
