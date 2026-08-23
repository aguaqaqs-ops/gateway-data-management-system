# ADR 0013: ENUM/SET v1 Import Semantics

状态：Accepted（独立 Contract review 通过；允许进入 Stage C）

日期：2026-08-16

决策 owner：Backend vNext Architecture

关联阶段：Phase 2 — R6-EXT-W1 package validation

依赖决策：
[ADR 0005](0005-shared-canonical-encoding.md)、
[ADR 0009](0009-proportional-assurance-and-trusted-internal-repository.md)、
[ADR 0010](0010-minimal-golden-and-ordinary-ci.md)

精确规则位于 owning contract，本文不复制 grammar 或字段表：

- source dump SQL grammar、statement allowlist、identifier unquote 和 dump 侧
  typed-scalar 识别：`table_access`（[P3-R2 Table Access and Parser Handoff](../plans/p3-r2-table-access-parser-handoff.md)）
- catalog/manifest `sql_type` 族判定、Arrow、fail-closed 转换、import/read wire
  映射：[Repository Service](../contracts/repository-service.md) §10.1
- content 单元格 bytes：[Shared Canonical Encoding](../contracts/shared-canonical-encoding.md) §3.2
- schema/content digest 输入：[Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md) §4
- golden 目录：[Correctness Golden and Fixture](../contracts/fixture-oracle-and-conformance.md)
  （Repository ENUM/SET corpus 仍由 Repository 拥有；dump parser fixtures 由
  `table_access` 拥有）

首次独立审核为 fail，有限清单见 tag `docs/p2-p3-cleanup-pre-20260817` 中的
`docs/backend-vnext/refactoring/temporary/p2-r6-ext-w1-stage-b-contract-review.md`
（已离开默认树）。下列第 7–9 条是对该清单的收口，不扩大范围。

## Context

当前五份外部 fixture 均能 Dolt replay，但 production `ImportManifest`/Arrow mapping
把 `ENUM`/`SET` 当作 unknown。STRINGIFY 会写入 `gateway.lossy=true` 且不承诺
digest 可比性，不能作为 W1 正式路径。项目尚未发布，没有外部 consumer 或历史
package 兼容义务；尚未发布的 one-off canonicalization scheme 不构成兼容承诺。

Shared Canonical Encoding v1 的 tag 表已闭合；Canonical Row Hash Arrow mapping v1
明确拒绝 `list`。需要在不升 package/canonicalization v2、不占用新 tag 的前提下，
把 ENUM/SET 收进首次发布前的 v1。

## Decision

1. 直接修订现有 v1 Contract。不增加兼容字段、迁移分支、`v2` 版本号或「先
   stringify 再 parse」路径。五份 fixture 全部是 positive accepted cases。
2. ENUM 逻辑值是声明 label，不是 ordinal。SET 逻辑值是声明成员按声明顺序排列的
   无重复子集。NULL、ENUM 空 label（仅当已声明）、空 SET 与非空 SET 各有唯一形态。
3. Repository import Arrow：ENUM 为 `utf8`，SET 为 `list<utf8>`。metadata 仅
   `gateway.logical_type` 与完整 `gateway.sql_type`。禁止 dictionary、`large_string`
   正式映射和 `gateway.lossy`。SET 不保留逗号拼接 scalar 退路。
4. Content encoding 复用既有 string tag 与 `sequence` framing，不新增 scalar tag。
   ENUM 与 VARCHAR 的类型差在 schema digest。既有 128 个 Shared Kernel case 不变。
5. charset/collation 列修饰符继续排除出 normalized grammar 与 schema identity。
   非 ASCII label 合法；`ENUM`/`SET` 族不走未知 type 的 ASCII charset 门。
6. Canonical Row Hash capability 本轮不接收 `list`；import FULL_SCAN 使用
   Repository Arrow，二者不是同一物理 mapping。
7. 族判定闭合：剥离 `CHARACTER SET`/`COLLATE` 并折叠 label 外空白后，若类型
   keyword 为 `ENUM`/`SET`，要么唯一 normalized spelling，要么
   `SQL_TYPE_MALFORMED`。声明重复、越界、SET 空 label、整段不匹配、残留 token
   不得落入 unknown/STRINGIFY。
8. SET 非 null 的 content 单元格就是 `sequence_frame` 本身，不再外包 scalar tag；
   不使用 `encode_row`，不升 `canonical_encoding_version`。
9. `SQL_TYPE_MALFORMED` / `SQL_VALUE_ILLEGAL` 只用于 parser/golden。编译/admission
   畸形类型 → `IMPORT_REJECTED`；FULL_SCAN 非法值 →
   `VERIFICATION_FAILED_NOT_PUBLISHED`；read 编译期不得使用 `UNKNOWN_SQL_TYPE`。
   不新增第五个 public import code。
10. SQL grammar 双边界（P3-R2-S0，2026-08-19）：`table_access` 拥有 source dump
    parser grammar；Repository Service 拥有 catalog/manifest validation。二者共享
    known type 闭合集和 ENUM/SET fail-closed codes，**不得**共享 parser
    implementation，也不得创建 `sql_utils`、`capabilities/common` 或
    `capabilities/utils`。dump parser 映射 Shared Kernel typed scalar，不产出
    Arrow；Arrow 与 import wire 仍只属于 Repository §10 / §10.1。本条不改变第
    1–9 条的 ENUM/SET 值、content encoding 或 public import code。

## Alternatives

- 保留 ENUM/SET 为 unknown + STRINGIFY：拒绝。无法通过 production validator，也不能
  计算可比 digest。
- 把族内畸形拼写当 unknown：拒绝。STRINGIFY 会写成 `large_string` + `gateway.lossy`，
  构成隐式兼容层。
- 新增 scalar tag 或 canonical encoding v2：拒绝。无已发布 consumer，且会把未发布的
  v1 tag 表扩成第二套版本轴。
- 把 SET `sequence_frame` 再包进 scalar tag 或送入 `encode_row`：拒绝。digest bytes
  会分叉，且会碰到升 `canonical_encoding_version` 的禁令。
- 把 `SQL_*` 加成第五个 import code：拒绝。public wire 已有闭合四码。
- SET 正式物理类型为逗号拼接 `utf8`：拒绝。成员边界依赖「label 不含逗号」这一额外
  约束；`list<utf8>` 把边界放进 Arrow，comma-text 只作为 Dolt driver 输入形态。
- 把 charset/collation 纳入 schema identity：拒绝。与 CHAR/VARCHAR 既有规则和
  provider-independent UTF-8 binary 比较不一致；label 已是精确 UTF-8。
- 同步扩展 Canonical Row Hash 以接受 `list`：拒绝。本轮 consumer 是 import
  validator，不是该 capability；扩大其 Arrow 闭合集会超出比例化范围。
- 让 Repository 与 `table_access` 共享 SQL parser implementation 或建立
  `sql_utils`：拒绝。dump grammar 与 catalog/manifest validation 是不同边界；
  共享实现会把 Repository DTO/Arrow 泄漏进 capability leaf。

## Consequences

- Stage C 必须把 ENUM/SET 从 unknown 测试预期中移出；族内失败映射既有 import/read
  code，不得标成 `UNKNOWN_SQL_TYPE`。
- producer 按 v1 digest 输入计算 `canonicalization_manifest_digest`；SET 单元格放入
  裸 `sequence_frame`。Repository 仍不重算业务 digest。
- 独立 corpus `vnext/fixtures/vectors/repository/sql-enum-set/v1/` 由 Repository
  语义拥有；Shared Kernel corpus 保持 128 case。dump parser 的 ENUM/SET 用例由
  `table_access` 自有 fixture 证明 `SQL_TYPE_MALFORMED` / `SQL_VALUE_ILLEGAL`
  对齐，不得把 Repository corpus 提升为通用 loader。
- Backend `table_access` 不得 import `gateway_repository_service` 或复用
  Repository DDL helpers。known type 闭合集仍以 Repository §10 为权威；实现各自
  维护。

## Required Verification

独立 Contract review 已通过。首次审核 fail 记录保持不变。后续 unit、golden、五份
fixture validator 与 capacity 按执行计划 Stage C–I 证明，不由本 ADR 替代。
P3-R2-S0 双边界修订不重新打开 ENUM/SET 值语义；dump parser 实现与 boundary tests
由 [P3-R2 Table Access and Parser Handoff](../plans/p3-r2-table-access-parser-handoff.md)
封存。
