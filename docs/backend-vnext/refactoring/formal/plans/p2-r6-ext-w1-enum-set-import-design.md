# P2-R6-EXT-W1 ENUM/SET Import Design

状态：Ready for implementation

日期：2026-08-16

适用阶段：Phase 2 — R6 external W1 package validation

Owner：Backend vNext Architecture（Contract、canonicalization、验收边界）与 Repository
Service（实现、测试、candidate evidence）

## 1. 背景与结论

当前允许的 medium 和 data2 均能完成 Dolt replay，但 production
`ImportManifest`/Arrow mapping 拒绝 `ENUM`/`SET`。因此 R6-EXT-W1 尚未 ready；不能生成正式
package、计算 `canonicalization_manifest_digest` 或开始 S6 capacity。

本项目尚未发布，没有外部 consumer 兼容性和历史数据迁移约束。本轮允许直接修改现有 v1
Contract、manifest model、Arrow mapping、producer 和测试；不增加兼容层、迁移分支或 v2
版本号。当前尚未发布的 one-off canonicalization scheme 不构成兼容承诺，可以被最终 v1
方案替换。

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
- 不在本轮扩大到新的 SQL 类型或重做无关的容量架构。

## 3. v1 类型语义

### 3.1 ENUM

`ENUM` 的逻辑值是声明中的 label，不是 ordinal。规范化类型必须保留 label 的精确顺序、
转义和大小写；声明顺序属于 schema identity。NULL 是独立状态，空字符串只有在声明允许
时才是合法 label。

推荐 Arrow 表示为 `utf8`（必要时使用 `large_string`），metadata 明确记录逻辑 SQL type
和声明 label 列表。不得以 Arrow dictionary index 作为 digest 或跨语言业务值。

### 3.2 SET

`SET` 的逻辑值是声明成员的有序子集。输入顺序不影响 canonical value，输出按声明顺序
排列。NULL、空集合和非空集合必须区分；未知成员、重复成员或无法证明的 driver value
在正式 import 中 fail closed。

默认 Arrow 设计为 `list<utf8>`，以避免用逗号拼接编码成员边界。若 Dolt provider 的稳定
值接口无法直接支持 nested Arrow，必须在 Contract 中明确、可逆的 canonical string 编码后
才允许退回 scalar 表示；不得静默采用普通 stringify。

### 3.3 Schema 与 content digest

- schema digest 包含规范化 SQL type、ENUM label/SET member 声明顺序、nullable、PK，以及
  已确认影响语义的 charset/collation；表和列顺序规则与 manifest 保持一致。
- content digest 对每个值使用带类型标签的 canonical encoding；NULL、空值、ordinal、SET
  成员顺序不能产生歧义。
- row/table 排序沿用现有 Contract 的权威规则；不得由不同 producer 自行排序。
- canonicalization algorithm 保持第一版标识（`...:v1`）。本轮是在首次发布前完成 v1 定稿，
  不增加 `v2`。

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

