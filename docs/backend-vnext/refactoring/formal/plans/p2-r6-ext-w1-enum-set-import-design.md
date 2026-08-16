# P2-R6-EXT-W1 ENUM/SET Import Design

状态：Frozen（独立 Contract review 通过；允许进入 Stage C）

日期：2026-08-16

适用阶段：Phase 2 — R6 external W1 package validation

Owner：Backend vNext Architecture（Contract、canonicalization、验收边界）与 Repository
Service（实现、测试、candidate evidence）

权威语义不再由本文拥有。精确规则：

- SQL grammar、Arrow、fail-closed 转换：[Repository Service](../contracts/repository-service.md) §10.1
- content bytes：[Shared Canonical Encoding](../contracts/shared-canonical-encoding.md) §3.2
- schema/content digest 输入：[Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md) §4
- golden 格式：[Correctness Golden and Fixture](../contracts/fixture-oracle-and-conformance.md) §2.1
- 决策记录：[ADR 0013](../adr/0013-enum-set-v1-import-semantics.md)
- 冻结包：[P2-R6-EXT-W1 Stage B Contract Freeze](../../temporary/p2-r6-ext-w1-stage-b-contract-freeze.md)

## 1. 背景与结论

当前允许的 medium 和 data2 均能完成 Dolt replay，但在 Contract freeze 落地实现前，
production `ImportManifest`/Arrow mapping 仍拒绝 `ENUM`/`SET`。因此 R6-EXT-W1 尚未
ready；不能生成正式 package、计算 `canonicalization_manifest_digest` 或开始 S6
capacity。

本项目尚未发布，没有外部 consumer 兼容性和历史数据迁移约束。本轮直接修订现有 v1
Contract；不增加兼容层、迁移分支或 v2 版本号。尚未发布的 one-off canonicalization
scheme 不构成兼容承诺，已被 v1 定稿替换其内容定义，算法标识保持
`gateway-vnext:canonicalization-manifest:v1`。

## 2. 目标与非目标

目标：

- 为 `ENUM` 和 `SET` 建立一个完整、可审计、跨语言一致的 v1 语义；
- 让当前五份测试数据全部能够生成正式 repository import package 并通过 production
  validator；
- 将 package/raw/schema/content digest 与 Arrow 物理表示闭合；
- 在 validator gate 通过后再进入 S6、W2、concurrency matrix、S7 和 S10。

非目标：

- 不保留旧 manifest/package 的 wire 兼容；
- 不为尚未存在的外部 consumer 提供 migration；
- 不把 `STRINGIFY` 作为正式 import W1 的替代方案；
- 不在本轮扩大到新的 SQL 类型或重做无关的容量架构；
- 不把 Canonical Row Hash capability 的 Arrow mapping 扩展为 `list`。

## 3. v1 类型语义

正文已冻结在 owning contract。摘要如下，冲突时以 contract 为准。

### 3.1 ENUM

逻辑值是声明 label，不是 ordinal。规范化 spelling 保留 label 精确顺序、`''` 转义、
大小写与 UTF-8。NULL 独立；空字符串仅当声明含 `''` 时合法。Repository Arrow 为
`utf8`，metadata 为 `gateway.logical_type=enum` 与完整 `gateway.sql_type`。禁止
dictionary、`large_string` 正式映射和 `gateway.lossy`。content 使用 string tag
`0x20`。

### 3.2 SET

逻辑值是声明成员按声明顺序排列的无重复子集。NULL、空集合与非空集合必须区分。
未知/重复成员与无法证明的 driver value fail closed。Repository Arrow 为
`list<utf8>`；comma-text 只作为 Dolt 输入形态。v1 不保留 scalar 物理退路。content
使用 string-item `sequence`；空 SET 是长度为 0 的 sequence。

### 3.3 Schema 与 content digest

- schema digest 包含 normalized `sql_type`（因此含声明顺序）、nullable、PK。charset /
  collation 修饰符不属于 v1 schema identity。表按 canonical name bytes 排序，列保持
  DDL order。
- content digest 单元格：ENUM 为 string/null `scalar_frame`；SET 非 null 为
  `sequence_frame` 本身，不再外包 scalar tag。不走 `encode_row`，不升 v2。
- row/table 排序沿用现有 Contract；producer 不得自行排序。
- 算法标识保持 `gateway-vnext:canonicalization-manifest:v1`。

## 4. 容量与数据范围

10–100MB 是常见 package 体积，不是拒绝阈值。当前 upload/admission hard cap 至少覆盖
200MB，并以配置项提供未来提高上限的能力。限制分层定义为：raw upload bytes、解包后
package bytes、单批 decoded row bytes 和 staging/free-disk 预算；配置快照必须进入验证
evidence。

当前五份测试数据全部是正向可接受样本：

- 五份都验证 source size/SHA、replay/catalog、package generation 和 production validator；
- 五份都不得因当前 hard cap 被拒绝；
- 未来构造真正超限样本时，单独验证 bounded admission、错误码、无 Dolt effect 和 cleanup，
  不把它计为成功 package 或 S6 capacity PASS。

## 5. 实现边界与验收

实现顺序固定为：contracts/model → SQL/catalog parser → Arrow schema/value conversion →
manifest validation/verification → package producer/digest → cross-language golden vectors。

独立 Contract review 已通过，见
[P2-R6-EXT-W1 Stage B Contract Review 2](../../temporary/p2-r6-ext-w1-stage-b-contract-review-2.md)。
首次 fail 记录保持不变。允许开始 parser/model 生产代码（Stage C）。

validator gate 的通过条件：

1. 五份数据均生成正式 package；
2. `validate_and_extract_import_package()` 全部通过；
3. manifest 与 Dolt catalog exact match；
4. 无 `ENUM/SET` unmappable、无隐式 stringify；
5. digest 可重复计算，golden vectors 跨语言一致；
6. raw size/SHA、配置快照和清理结果均有 evidence。

validator gate 通过后，才开始 S6 capacity；最终 candidate 仍需按 testing conventions 执行
五个包的 ruff/mypy，并在最终 HEAD 重建 image 和运行 container gates。纯 Python/Contract
中间提交可延期重建。
