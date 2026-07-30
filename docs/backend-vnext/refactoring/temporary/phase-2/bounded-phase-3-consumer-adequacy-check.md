# Phase 2 — Bounded Phase 3 Consumer-Adequacy Check

状态：**Confirmed PASS / Formalization Authorized**

日期：2026-07-30

适用范围：Phase 2 Repository Service public contract 对已知 Phase 3 Capability
Foundation consumer 的最小充分性检查。

本文件不设计 Phase 3 capability、业务状态机或实现计划，不拥有 Decision
语义，也不替代 formal contract。Phase 2 Decision Ledger、
[Consolidated Design Review](consolidated-design-review.md) 与 accepted formal
authority 仍是语义来源。

## 1. Check boundary

依据 `P2-R11-D08` 与 `P2-R11-D24`，本次只检查以下链路：

```text
SnapshotTableArtifact + frozen table rules
  -> storage_projection
  -> CanonicalizationManifest + RepositoryImportArtifact
  -> Repository Client upload
  -> SubmitImport / GetOperation
  -> requested verification evidence
  -> commit-pinned readback
```

明确不检查或决定：

- storage/comparison projection 的具体业务列规则、算法或 provider；
- Snapshot、Comparison、Risk、Surface、Bundle capability 设计；
- SubmitAttempt、Workspace、Submission 或 Operation Runtime 状态机细节；
- Phase 3 package、WP、gate、Rust/Python provider 和性能优化方案；
- CurrentTableStore 的 Phase 3 使用方式；
- Phase 3 production implementation。

## 2. Authority facts

已知 Phase 3 consumer 需要：

1. 从 frozen Preview-bound `SnapshotTableArtifact` 与 frozen table rules 生成一次
   canonical artifact；
2. 由 Storage Projection 拥有
   `CanonicalizationManifest`、`RepositoryImportArtifact` 内容、版本和 digest；
3. 通过 Repository Client 传输 artifact，不感知 Dolt、server path 或 repository
   volume；
4. 用稳定 RepositoryId、base CommitId、target ref、artifact identity 和
   idempotency identity 发起异步 import；
5. 在 timeout、disconnect、takeover 或 unknown outcome 后查询原 operation，而不是
   blind replay；
6. 对需要业务 finalize 的 Submit 显式请求并检查 FULL verification evidence；
7. 以返回的 immutable CommitId 进行 catalog、row stream、export 或 fallback
   readback；
8. 由 application-owned Repository Port 映射 Phase 2 SDK/wire，不把完整 wire
   contract 复制进 domain。

Phase 2 accepted design 已把 verification 从 service-wide FULL-only 改为
caller-explicit `NONE | STRUCTURAL | FULL`。这不削弱已知 Phase 3 Submit consumer：
该 consumer 可以固定请求 `FULL`，并检查 `completed_verification_level` 和对应
`SnapshotManifest` evidence；其他 caller 不被迫承担相同成本。

## 3. Consumer coverage matrix

| Consumer requirement | Phase 2 coverage | Owning decisions / surface | Result |
| --- | --- | --- | --- |
| Storage Projection 独立拥有 canonical content | Repository Service只消费closed artifact，不选择列、key、pseudo gid或业务规则 | `P2-R0-D06/D07`、`P2-R4-D01` | COVERED |
| 一次构建、稳定版本与digest | Upload和Submit分别绑定content contract、raw/content digest；operation request digest阻止换artifact重放 | `P2-R4-D01`、`P2-R5-D01/D02`、`P2-R8-D03` | COVERED |
| 大型artifact跨进程传输 | Repository-bound one-shot authenticated streaming upload；close/size/digest/manifest后发布ArtifactRef | `P2-R8-D03/D04`、`P2-R11-D18` | COVERED |
| 不重复全表serialization | canonical SQL replay直接由bounded executor消费，不先转Python rows/JSON或生成第二份等价SQL | `P2-R4-D01`、`P2-R11-D19` | COVERED |
| 异步SubmitImport | Closed action返回OperationRef；请求包含base commit、target publication policy、ArtifactRef/digest、verification level及idempotency key | `P2-R2-D03/D04`、`P2-R6-D09/D11`、`P2-R11-D16/D21` | COVERED |
| 并发保护 | Known Submit可选择`CHECK_EXPECTED`并传expected target；LWW仍要求base CommitId，且必须显式选择 | `P2-R6-D11` | COVERED |
| Lost response与takeover | GetOperation、durable journal、effect-start、private operation ref、fencing与evidence-first reconciliation | `P2-R5-D01～D03`、`P2-R6-D01～D07/D10` | COVERED |
| FULL业务验收 | Caller显式请求FULL；result保存requested/completed level和FULL SnapshotManifest evidence | `P2-R6-D09/D15`、`P2-R10-D04` | COVERED |
| Verification失败不误重放 | FULL mismatch为`FAILED + effect=APPLIED`；返回commit/publication/failure evidence，不自动重放或回滚 | `P2-R6-D15` | COVERED |
| Immutable readback | Resolve/pin CommitId，catalog/stream/export绑定同一snapshot；Arrow stream有完整性、backpressure和cancel语义 | `P2-R3-D01～D05/D07/D10`、`P2-R6-D13` | COVERED |
| Raw technical diff fallback | RepositoryRawDiff完整时返回provider-neutral records，否则UNSUPPORTED并由caller stream两个commit | `P2-R3-D08` | COVERED |
| Application Repository Port | Fake/Local/Remote SDK与closed Remote wire可由infrastructure adapter映射，domain不依赖HTTP/Dolt/path | `P2-R10-D02`、`P2-R11-D10` | COVERED |
| Capability/version discovery | Service公开wire/capability/resource limits，unknown/breaking schema按closed compatibility处理 | `P2-R2-D05/D25`、`P2-R8-D04`、`P2-R10-D01/D06` | COVERED |
| Consumer-ready交付点 | WP7-R4交付VerifyCommit、inventory、write conformance及真实Local/Remote handoff | `P2-R11-D21/D24` | COVERED |

结果：`14 COVERED / 0 BLOCKING GAP`。

## 4. Exact consumer call shape

本检查确认 Phase 2 public primitives 足以让后续 Phase 3 adapter 组成以下流程；
这不是新增业务 workflow：

```text
UploadArtifact(
  repository_id,
  content_contract,
  media_type,
  size,
  raw_digest,
  upload_idempotency_key,
  intended_action=SUBMIT_IMPORT
) -> ArtifactRef

SubmitImport(
  repository_id,
  base_commit_id,
  target_ref,
  concurrency_mode=CHECK_EXPECTED,
  expected_target_commit_id,
  artifact_ref,
  artifact_digest,
  verification_level=FULL,
  idempotency_key
) -> OperationRef

GetOperation(OperationRef)
  -> commit_id
  -> target publication evidence
  -> requested/completed verification level
  -> FULL SnapshotManifest evidence or typed failure/effect

StreamTableRows(
  repository_id,
  read_binding=EXACT(commit_id),
  ...
)
```

已知业务 Submit 推荐使用`CHECK_EXPECTED + FULL`，但这是 Phase 3/application
owner 对自身 use case 的选择，不是 Repository Service 对所有 caller 的隐藏默认。

## 5. Formalization obligations

以下是既有决定的精确落盘要求，不是新的架构问题：

| ID | F0 obligation | Owner |
| --- | --- | --- |
| CA-F01 | 固定`RepositoryImportArtifact v1`的closed media/package schema、manifest entry、canonical SQL replay grammar、content digest preimage和compatibility规则 | Storage Projection content owner + Repository artifact/parser boundary |
| CA-F02 | 固定`SubmitImport` closed request/result schema，包括base、target、ArtifactRef/digest、concurrency union、verification level、idempotency、commit/publication和level-specific evidence | Repository Service wire/import owner |
| CA-F03 | 固定verification evidence discriminated union：NONE effect evidence、STRUCTURAL evidence、FULL `SnapshotManifest`；禁止consumer把裸`VERIFIED`解释为FULL | Repository verification/readback owner |
| CA-F04 | 在Application Repository Port示例中只保留Phase 3所需最小方法，并由Remote adapter映射SDK DTO；不得向domain泄漏HTTP、Dolt或path | Phase 3 application port owner + Phase 2 client owner |
| CA-F05 | 将旧formal FULL-only通用规则改为caller-selected policy，同时明确已知Submit T3仍检查FULL completed level和matching evidence | Repository verification owner + business lifecycle/recovery owner |
| CA-F06 | 在WP7-R4 consumer-ready evidence中加入owner-published artifact fixture、upload→Submit→poll→EXACT readback及Fake/Local/Remote canonical observation | Phase 2 implementation/conformance plan |

上述schema中的字段名、enum encoding、digest preimage和media type由formal owner在F0
精确定义；只要保持accepted语义，不需要重开Round。

## 6. Deferred Phase 3 responsibilities

以下问题有Phase 2所需primitive，但仍必须在Phase 3/4详细设计时由业务owner裁决：

- `SnapshotTableArtifact`到canonical SQL replay的确切生成算法与provider；
- storage projection失败、规则升级和schema alignment的业务处理；
- SubmitAttempt如何保存ArtifactRef、OperationRef、manifest digest和checkpoint；
- `FAILED + effect=APPLIED`时业务Attempt如何保持、人工处理或发起后续显式effect；
- Phase 3 Repository Port最小方法集及application error mapping；
- 哪些业务journey选择FULL、CHECK_EXPECTED和EXACT；
- capability benchmark、Rust/Python provider route与fallback。

这些事项不要求Repository Service理解Workspace、Submission或business finalize，
因此不阻塞Phase 2 formalization或实现。

## 7. Reopen and blocking result

### 7.1 Blocking gaps

无。

### 7.2 Phase 2 decisions requiring reopen

无。

### 7.3 Reopen triggers retained

只有后续 accepted Phase 3 consumer evidence证明下列任一事实时，才重开对应Phase 2
decision：

- closed canonical SQL replay无法表达合法canonical tables/types；
- one-shot upload的完整重传成本不满足已确认workload；
- FULL evidence无法提供业务T3所需的stable canonical fields；
- Local/Remote SDK无法保持相同application semantics；
- immutable commit stream/export不能承载所需readback。

## 8. Check conclusion

结论：**PASS — READY FOR F0 FORMAL CLOSURE AFTER USER AUTHORIZATION**。

Phase 2 public contract足以承载当前已知Phase 3 storage projection/import/readback
consumer。无需提前展开Phase 3设计，也无需重开Round 0–11。

下一停止点仍是Formalization stop。只有用户明确回复
“整体设计确认，可以 formalize”后，才能修改formal authority并生成Phase 2正式
implementation design/delivery plan。
