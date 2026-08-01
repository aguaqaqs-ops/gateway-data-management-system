# ADR 0004: Raw Source Artifact and Canonical Dolt Storage

状态：Accepted

日期：2026-07-19

决策 owner：Backend vNext Storage Projection Architecture

关联阶段：Phase 2、Phase 3、Slice 5A/5B

2026-08-02 amendment：canonical content owner继续有效；Repository Service使用
caller-selected NONE/STRUCTURAL/FULL_SCAN，默认STRUCTURAL，但任何level都不消费
business digest或旧full-manifest evidence。ADR 0010进一步确认：产生有效
Submission/commit的SourcePackageArtifact保持submission durable；
`NO_CANONICAL_CHANGE`不提升retention；完整CanonicalizationManifest由Backend
durable保存，临时Repository package只携带结构字段和opaque manifest digest。

## Context

Legacy 要求 Dolt 尽量保存原始 SQL schema/data，并在比较时构建临时 projection table。该做法重复消耗 CPU/I/O，且不稳定列会放大无业务意义的历史 diff 和存储。原始上传 bytes 已可由 immutable artifact 独立保存，因此不需要让 Dolt 同时承担 raw package authority。

## Decision

SourcePackageArtifact 是原始上传权威；Dolt 只保存由版本化 table rules/storage projection 生成的 canonical business tables。Storage projection 可删除已证明无业务、结构、顺序、审计或恢复意义的列，必须保持 retained row 完整性并 fail closed。Comparison projection 是独立边界。

Ordered table第一版保留`no`，以`gid`为主键；real gid为
`1..3_999_999_999`，blank pseudo gid从`4_000_000_000`确定分配。每次import绑定
CanonicalizationManifest和immutable RepositoryImportArtifact。Repository按caller
选择执行自身verification；业务content digest由Storage Projection/业务owner持有。
SnapshotTableArtifact只在current Preview/active Attempt期间pin；
首版不长期复制full-row archive。RepositoryImportArtifact在Backend store和
Repository Service中分别使用不同nominal ref/ID scope；两种ref都只保留opaque ID、
media type、size和raw SHA，semantic metadata属于上述业务manifest。
精确规则由
[Canonical Storage and Repository Boundary Contract](../contracts/canonical-storage-and-repository-boundary.md)
唯一规定。

## Alternatives

- Dolt 继续完整保存 raw schema/rows：拒绝，因为重复 raw authority 并保留不稳定数据。
- 比较时临时投影：拒绝作为主路径，避免每次比较重复成本。
- 删除 ordered `no` 并建立 position/edge table：延后；罕见漂移不足以证明双表复杂度。
- 自动 surrogate key/dedup：拒绝，会隐藏数据语义错误或丢行。
- 规则升级时迁移全部历史：拒绝第一版采用；使用 versioned alignment/fallback。

## Consequences

Dolt export 是 canonical schema，不能单独复原原始 DDL/删除列；原始审计回到 durable SourcePackageArtifact。Submit 增加一次 storage projection，但后续 read/diff 可直接使用 canonical state。规则升级可能产生 degraded comparison；旧 Dolt migration/compatibility 仍需独立 cutover 决策。

## Required Verification

- Raw artifact restore、canonical manifest、row-count/key 和 dropped-column fixtures。
- Ordered gid/no、pseudo blank、position shift 和 reserved-range vectors。
- Repository structural result与business-owned digest边界。
- Durable SourcePackageArtifact、Backend CanonicalizationManifest与临时
  structural package分离。
- Projection version mismatch 进入 alignment/fallback，不使用不安全 native diff。
