# DX Cross-Phase Interface Reconciliation

状态：Accepted — DX Complete

日期：2026-07-31

Owner：Backend vNext Architecture（跨阶段映射、依赖方向和清理顺序）

输入决策：

- [ADR 0009](../adr/0009-proportional-assurance-and-trusted-internal-repository.md)
- [ADR 0010](../adr/0010-minimal-golden-and-ordinary-ci.md)
- [Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)
- [Repository Service Contract](../contracts/repository-service.md)
- [Contract Taxonomy and Ownership](../contracts/contract-taxonomy-and-ownership.md)

本文闭合D2与D01之间的接口映射，不建立新的semantic owner。字段语义仍由上述
owning contracts定义；本文拥有它们的组合方式、package依赖和S02实施顺序。

## 1. Outcome and non-goals

DX确认：

- Backend local artifact与Repository artifact是两个nominal type，不共享class、
  ID namespace或serialization module；
- 两种ref都只表达opaque location identity和raw transport integrity；
- CanonicalizationManifest是Backend durable business authority，Repository import
  package是临时transport；
- Repository只执行package structural validation，不依赖Shared Kernel或业务digest；
- semantic digest、raw SHA、Repository CommitId和idempotency key保持不同语义域；
- ordinary package CI替代generic conformance/gate/evidence体系；
- S02可以开始，并按本文规定的小批次顺序执行。

DX不激活`/v1/` route，不创建Dolt durable layout，不决定legacy migration，也不重新
打开ADR 0009已接受的trust/auth/recovery边界。

## 2. Artifact nominal types

### 2.1 BackendArtifactRef

Backend `artifacts` module拥有内部/模块公共`BackendArtifactRef`：

```text
artifact_id
media_type
size_bytes
raw_sha256
```

- `artifact_id`由Backend ArtifactStore分配，在该store scope内opaque；
- equality首先按type + scoped `artifact_id`，其余字段是读取时integrity assertion；
- ref不携带schema version、logical path、semantic digest、content contract、
  retention class、resolver或access metadata；
- store可以content-addressed或random分配ID，但consumer不得解析；
- retention/pin/TTL/access作为store command、policy或独立record存在，不参与ref
  identity。

Capability result或owner manifest单独保存semantic metadata。删除generic
`ArtifactManifest`、`ContentContract`、`ContractBinding`和把content metadata复制进
ref的组合模型；owner-specific manifest仍可存在。

### 2.2 RepositoryArtifactRef

Repository `/v1/` wire拥有独立`RepositoryArtifactRef`：

```text
artifact_id
media_type
size_bytes
raw_sha256
```

- `artifact_id`是Repository生成的普通UUID，仅在所属Repository内有效；
- wire version由`/v1/`拥有，不在每个ref重复schema version；
- Repository不import Backend artifacts package；
- Backend不得把`BackendArtifactRef.artifact_id`转换或复制为Repository ArtifactId。

两个ref结构同形只是为了integrity handoff，不表示共享semantic type。Backend
Repository adapter必须显式执行upload映射。

## 3. Import handoff and checkpoint

固定顺序：

```text
Storage Projection
  -> durable CanonicalizationManifest
  -> RepositoryImportArtifact bytes
  -> BackendArtifactRef
  -> UploadArtifact(bytes + declared integrity)
  -> RepositoryArtifactRef
  -> SubmitVersionedImport
  -> RepositoryOperationId
  -> SUCCEEDED(commit/ref + echoed binding)
  -> Backend T3 finalize
```

在第一次Repository effect前，SubmitAttempt/Operation checkpoint至少绑定：

```text
backend_package_ref
canonicalization_manifest_ref
canonicalization_manifest_digest
upload_idempotency_key
import_idempotency_key
repository_id
target_ref
expected_commit_id
```

Upload成功或response-loss reconciliation后追加：

```text
repository_artifact_ref
```

Import接受后追加：

```text
repository_operation_id
```

规则：

- 同一Attempt只构建一次package；retry/takeover复用checkpoint；
- upload重试使用同一upload idempotency key、Backend ref和raw integrity；
- import重试/查询使用同一Repository ref、import idempotency key和operation identity；
- 不通过重新构建package或分配新key掩盖unknown outcome；
- Backend local package可以在Repository ref durable checkpoint后解除pin；
- Repository package在import成功后删除，失败/orphan按Repository policy处理；
- durable CanonicalizationManifest必须先于任一侧package清理；
- accepted Submission的SourcePackageArtifact retention独立于上述临时package。

## 4. Repository import package v1

Owning schema位于
[Canonical Storage and Repository Boundary](../contracts/canonical-storage-and-repository-boundary.md)；
Repository validation位于
[Repository Service Contract](../contracts/repository-service.md)。

DX已把原先未展开的`schema`字段闭合为owner contract中的physical columns与primary
key projection，并确认package仍只有`manifest.json + replay.sql`。本计划不复制
closed shape、排序或validation规则；实现必须直接引用上述两个owner contract。

跨owner handoff只增加以下组合不变量：

- Storage Projection生成package并拥有manifest业务绑定；
- Backend adapter只传输bytes与minimal raw integrity；
- Repository按自己的contract验证结构、保存opaque manifest binding并执行import；
- package不复制source/ruleset/projection/content/ordering digest；
- Repository不使用Shared Kernel解析或重算任何business digest。

Import operation request fingerprint至少绑定RepositoryId、RepositoryArtifactRef的
全部字段、target ref、expected commit和idempotency key。成功result除operation、
commit和target ref外，必须原样返回：

```text
artifact_id
canonicalization_manifest_digest
```

Backend T3必须同时核对artifact ID、manifest digest、expected parent和target ref；
Repository的structural success不能替代business digest validation。

## 5. Digest and identity ownership

| Identity/digest | Owner | Consumer | Repository action |
| --- | --- | --- | --- |
| raw SHA-256 of artifact bytes | 对应ArtifactStore/service | upload、reopen、checkpoint | 增量重算并比较 |
| Shared Kernel row/raw-content/table-schema | Shared Kernel/Row Hash capability | Python/Rust compute | 不消费 |
| SourcePackage content digest | Workspace Input | Preview/Submit/audit | 不消费 |
| ruleset/projection digest | Table Rules/Storage Projection | cache/manifest | 不消费 |
| CanonicalizationManifest digest | Storage Projection | Submit finalize/audit | opaque保存并echo |
| business content/ordering digest | Storage/ordered business owner | no-change/finalize/compare | 不消费 |
| Repository CommitId | Repository Service | Backend immutable read/ref | 生成并返回 |
| idempotency key/request fingerprint | effect owner | retry/reconciliation | 按Repository contract执行 |

禁止：

- 使用raw SHA代替business content equality；
- 使用CommitId代替CanonicalizationManifest digest；
- 把semantic digest放回generic ArtifactRef；
- Repository重新计算canonical row/business digest；
- 为package、test run或CI新增self-digest/evidence digest。

## 6. Package dependency closure

Production依赖固定为：

```text
gateway-shared-kernel
  <- gateway-backend

gateway-compute-core
  <- gateway-compute-python adapter
  <- gateway-backend

gateway-repository-contracts
  <- gateway-repository-client
  <- gateway-backend

gateway-repository-contracts
  <- gateway-repository-service
```

附加规则：

- Backend只通过client/contracts访问Repository，不import service；
- repository contracts/client/service均不依赖Shared Kernel、Backend、Rust compute或
  generic conformance package；
- repository service不依赖client；
- Rust core不依赖PyO3、Backend artifact或Repository DTO；
- `gateway-conformance` distribution删除；保留测试迁回semantic owner package；
- Shared Kernel删除`conformance` optional extra、closure/schema validator和
  Repository consumer支持；
- package只声明其source实际import的direct dependency，lockfile随删除更新。

## 7. Ordinary CI ownership

S02完成后的持续命令：

| Owner | Required commands/check |
| --- | --- |
| Shared Kernel Python | ruff、strict mypy、pytest；直接跑全部canonical cases |
| Rust workspace | fmt、clippy、test、release build；直接跑全部canonical cases |
| Backend | ruff、strict mypy、pytest；row-hash golden、ordinary artifact round-trip |
| Repository contracts/client/service | 各自ruff、strict mypy、pytest |
| Native boundary | installed release wheel import/compute/GIL smoke |
| Integration | Backend package → Repository upload/import/read真实纵切就绪后执行 |
| Container | 一个Compose health/native smoke |

不存在独立gate router、affected-scope closure、phase protection、attempt bundle、
profile matrix或exact-commit evidence。Repository package tests不得通过依赖Shared
Kernel canonical corpus获得通过。

## 8. S02 commit sequence

每个revision独立提交并在其owner范围内保持green：

五轮跨对话执行、定向验证和handoff格式见
[S02 Code Cleanup Execution Checklist](s02-code-cleanup-execution-checklist.md)。

1. `S02-C1 delivery-control removal`
   - 删除Phase 2 gate/router/closure/traceability运行时引用、命令和CI；
   - 恢复普通package test入口。
2. `S02-C2 canonical test simplification`
   - 保留128 cases和Python/Rust核心；
   - 删除vector manifest/schema/generator、Shared Kernel conformance extra、
     Repository consumer和generic conformance distribution；
   - 把mixed-scalar golden迁回Backend/Rust owner tests。
3. `S02-C3 compute and Backend artifact boundary`
   - 切换Row Hash boundary v1；
   - 以minimal `BackendArtifactRef`替换旧generic envelope；
   - ordinary reopen只做raw integrity、Arrow parse和fixed schema。
4. `S02-C4 thin Repository packages`
   - 用Pydantic/stdlib Versioned DTO和simple error替换旧strict/JCS/problem/stream；
   - 删除Shared Kernel dev dependency；
   - 暂不注册stub route。
5. `S02-C5 cross-phase regression`
   - 运行第7节全部当前可用命令、installed wheel和Compose smoke；
   - 搜索旧authority和已删除schema/script引用；
   - 记录尚未实现的P2 feature入口，不把缺失feature伪装为pass。

如果一个revision同时触及两个owner且不能各自验证，应再拆分，不能扩大commit。

## 9. Compatibility and rollback

当前没有激活Repository business wire、production durable layout或外部consumer，
因此S02直接删除旧DTO和schema：

- 不提供ArtifactRef v1 compatibility parser；
- 不提供Row Hash boundary v1 fallback；
- 不保留Repository old/new wire adapter；
- 不迁移generic conformance evidence或Phase 1 identity bundle；
- Git history和D01/DX checkpoint提供回溯。

每个S02 commit可按文件边界revert；一旦未来P2写入真实durable commit，rollback必须
遵守Repository contract，不能用代码revert删除数据。

## 10. DX exit checklist

- ArtifactRef两个scope、字段、mapping和cleanup owner唯一；
- package closed shape、manifest binding、result echo和T3核对闭合；
- 每个保留digest/identity具有唯一owner和consumer；
- Backend/Shared Kernel/Rust/Repository package依赖无环且无conformance反向依赖；
- ordinary CI命令与测试迁移owner明确；
- S02 commit顺序、兼容策略和rollback明确；
- formal中D01、DX、S02状态一致；
- 尚未修改代码、fixture、schema、lockfile或CI。

DX与S02现已完成，下一入口是`P2-R1`，不是直接开始后续 P2 feature delivery。
