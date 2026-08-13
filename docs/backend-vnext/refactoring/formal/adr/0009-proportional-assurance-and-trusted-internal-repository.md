# ADR 0009: Proportional Assurance and Trusted Internal Repository

状态：Accepted

日期：2026-08-02

决策 owner：Backend vNext Architecture

关联阶段：Phase 0–2及后续设计

## Context

Backend vNext面向少量协作者和单一信任域，严谨性要求以业务正确性、可维护性和
可恢复的主路径为主，不承担互不信任tenant、合规防篡改或零人工介入的高保障目标。

现有Phase 0–2设计把业务digest、测试fixture、交付证据和安全真实性混在同一套
closure/evidence体系中，并提前设计了细粒度ACL、全量readback、多阶段effect
classification、exact-commit sign-off和双存储通用表面。这些机制缺少当前业务
consumer或明确威胁，已经显著增加实现、测试和演进成本。

## Decision

### Proportional assurance

安全、恢复、一致性和交付控制必须对应至少一项明确依据：

- 当前可信边界中的具体威胁；
- 可说明的业务损失或不可逆数据风险；
- 已确认consumer的正确性要求；
- 已发生故障或可复现的高概率失败模式。

没有上述依据时，不预建签名、防篡改证据链、细粒度ACL、全量自动恢复、通用资源
治理或形式化发布框架。业务digest只证明owner定义的内容相等性；除非另有明确的
key和trust contract，不得把digest称为签名、来源认证或防篡改证明。

优先使用平台和标准协议已经提供的能力，例如私有网络、部署入口TLS、容器非root、
HTTP、Pydantic/OpenAPI、Arrow IPC、数据库事务和普通CI。低成本且能避免灾难性
错误的输入大小限制、服务端路径、`shell=False`、secret/log脱敏继续保留。

### Repository trust and scope

Repository Service继续作为独立内网服务，但v1采用单一信任域：

- production使用一个全局static bearer token；有效token可访问全部repository；
- 不建设CallerIdentity、per-repository ACL、policy generation或存在性隐藏；
- TLS由deployment ingress/sidecar拥有；同主机隔离网络可使用内部明文HTTP；
- token泄漏等价于完整Repository写权限泄漏，这是v1明确接受的信任边界。

Phase 2首版只交付已知consumer需要的Dolt-backed Versioned能力。CurrentTableStore、
cross-store inventory、通用resource policy、GC、backup/restore、repair和delete API
延期，直到出现明确consumer和验收场景。

### Contract and transport

保留三个distribution及单向依赖：

```text
gateway-repository-contracts <- gateway-repository-client
gateway-repository-contracts <- gateway-repository-service
```

`gateway-repository-contracts`缩减为薄Pydantic DTO与少量enum。Pydantic model和
FastAPI生成的OpenAPI是HTTP wire authority；不再维护自定义strict JSON/deep-freeze、
重复runtime validator、手写schema snapshot hash或每个对象独立版本轴。

- Service-owned ID使用普通UUID；provider token和idempotency key使用有基础长度限制
  的opaque string，不校验UUID版本或复杂canonical grammar。
- Error统一为`code + message + optional details/request_id`；HTTP status表达请求层
  结果，不公开通用`category/phase/recovery/effect`状态空间。
- Versioned row stream直接返回标准Arrow IPC HTTP body；不增加JSON/base64 frame
  envelope、checkpoint frame或末尾内容SHA。
- Versioned API和route使用显式`Versioned`命名，避免阻塞未来Current sibling API。

### Versioned write and recovery

Repository import package继续使用固定`manifest.json + replay.sql`的`tar+zstd`。
Service只检查固定regular file、大小、路径安全、manifest基本结构和upload SHA-256；
`replay.sql`是受信Backend生成的内部输入，不建设完整SQL grammar和semantic package
防篡改体系。

Import采用caller-selected `NONE | STRUCTURAL | FULL_SCAN` verification，默认
`STRUCTURAL`。简化的含义是拒绝默认全量校验、business digest、防篡改evidence和
通用effect taxonomy，不是取消caller选择：

- 所有level都强制upload size/raw SHA、package safety、operation marker、expected
  parent和target ref CAS；
- `STRUCTURAL`额外核对committed catalog的table set、schema和row count；
- `FULL_SCAN`在private candidate commit上分批扫描全部user table，要求Arrow/type
  conversion成功且实际row count匹配manifest；不重算canonical/business digest；
- `NONE`跳过catalog structural/full scan，caller承担低保障选择的风险。

验证在target ref publication之前完成。请求和operation保存requested policy，成功
result返回completed policy；Backend finalize核对二者一致。业务no-change/comparison
digest仍由相应capability owner拥有。

Operation只使用`QUEUED | RUNNING | SUCCEEDED | FAILED`。Mutation通过
`idempotency_key + internal request fingerprint`处理response-loss重放。单process
使用durable-root OS lock和per-repository进程内写锁，不建设lease、fencing、
ServiceEpoch或`UNKNOWN/APPLIED/VERIFIED`状态机。

启动恢复处理durable QUEUED/RUNNING import：QUEUED重新入队；遗留RUNNING在main已
发布matching commit时补齐成功结果，在private ref存在唯一candidate时继续verification/
CAS，完全未找到且artifact完整时使用原artifact和key自动重试一次；多commit、ref矛盾
或无法判断时终止为
`FAILED / MANUAL_RECOVERY_REQUIRED`。正常validation/provider failure直接终止，不做
隐藏重试。

### Synchronous create and upload

`CreateRepository`和`UploadArtifact`是同步幂等操作，不创建Operation。

- Create在server-owned staging初始化Dolt、initial empty commit和默认`main`，
  完成后atomic publish；response loss通过idempotency返回原结果。
- Upload在单个HTTP请求中bounded streaming、增量计算size/SHA并atomic publish；
  不提供multipart或range resume。
- `SubmitVersionedImport`是V1唯一异步业务Operation。

Import的`expected_commit_id`同时是新commit parent和target ref CAS预期，且V1始终
必填，不提供LWW、force或关闭CAS的选项。table/schema CAS不在V1：commit CAS已经覆盖
整个snapshot，允许无关table变化将引入partial merge/rebase语义。V1不提供standalone
`CompareAndSetVersionedRef`；rollback、promotion或审批发布出现真实consumer后再
additive加入。

未知Dolt SQL type另由caller选择`REJECT | STRINGIFY`，默认`REJECT`。`STRINGIFY`只
作为非严谨场景的显式逃生口：未知列以Dolt返回文本映射为Arrow `large_string`，保留
NULL并标记原始SQL type与`lossy=true`；它不承诺跨Dolt版本的文本稳定性，也不产生
canonical/business digest保证。该policy与verification正交并由result回显。

### Artifact, capacity and disaster recovery

已确认package通常10–100 MB、极端约200 MB；日常10–200次/天、极端1,000次/天，
且峰值跨多个Repository，单Repository通常一周写入一次。Versioned commit永久保留，
package只是临时输入：

- success result持久化后删除本地package；
- orphan和普通失败使用可配置TTL做best-effort cleanup；
- RUNNING和`MANUAL_RECOVERY_REQUIRED`引用不得自动删除；
- 上游业务流程独立推送外部package备份，Repository Service不集成备份系统。

V1只建设简单的upload/import并发上限、per-repository single writer和free-disk
admission，不建设通用ResourcePolicy或quota/accounting subsystem。Dolt对重复数据
的实际增量存储必须测量，不提前承诺去重率。

Repository Service不提供public backup/restore API。部署方对quiescent durable root
做一致性volume snapshot并由operator恢复。恢复到最近snapshot之后允许人工重放
外部package；CommitId可能改变且外部引用允许人工修正，不承诺RPO/RTO或每commit
同步备份。

### Compatibility activation

T2/T3没有已发布wire兼容义务。T2只建立薄DTO骨架，不注册stub业务route或冻结
OpenAPI snapshot。首个真实纵切从`/v1/`激活FastAPI OpenAPI；V1允许additive扩展，
breaking field/semantics change使用`/v2/`。

### Future CurrentTableStore

未来CurrentTableStore作为additive sibling capability加入，而不是现在预建generic
dual-store framework：

- 共享RepositoryId、认证、ArtifactRef、基础Operation和logical table/Arrow types；
- Current拥有独立generation、mutation DTO、SQLite adapter和`/current/` route；
- Versioned拥有CommitId、ref、import和`/versioned/` route；
- 不引入`StoreKind`通用mutation union、自动routing、跨store transaction或
  consistency；
- repository layout保留可加法升级的format version，未来通过layout migration增加
  Current component，不提前创建空数据库或marker。

Current重新进入范围前必须具备真实caller、操作集合、数据生命周期和验收场景。

## Transition

WP1-R1已按2026-07-30旧设计完成并形成独立checkpoint。该checkpoint仅证明当时
工作完成，不构成已发布wire contract，也不产生后续兼容义务。

WP1-R1 checkpoint之后先完成Phase 2简化设计，再完成Phase 0–1同原则简化设计和
cross-phase interface reconciliation。两阶段设计闭合后，Phase 0–2代码简化作为
同一执行阶段分批提交，最后按新的最小Versioned计划恢复Phase 2 feature实现。

2026-08-01 follow-up：上述设计阶段与S02联合代码清理现已全部闭合；cross-phase结果见
[DX Reconciliation](../plans/dx-cross-phase-interface-reconciliation.md)。下一入口为
`P2-R1`，不直接启动后续 Repository feature。

2026-08-13 follow-up：[ADR 0012](0012-cooperative-artifact-cleanup-and-proportional-assurance.md)
将artifact cleanup重新对齐本ADR的单一信任域。ADR 0011曾引入的同euid非协作actor、
双UID directory-broker及其证明墙不再是v1安全或阶段退出要求。

先设计后联合清理避免Phase 2刚替换Artifact/contract，随后又因Phase 0–1 owner
调整重复返工；“联合”只表示同一执行计划，不允许把删除压成一个不可审查的大提交。

ADR 0008、旧traceability和historical Phase 2材料只继续解释WP1-R1 checkpoint；
WP1-R2+语义由本ADR、精简后的Repository Service Contract和Phase 2 plan拥有。

## Consequences

- WP1-R1中的strict wire、FailureDescriptor、stream envelope和schema snapshot允许
  在checkpoint后破坏性删除或改写。
- Phase 2不再以现有WP0 gate/closure、141项traceability和exact-commit exit作为
  交付前提。
- Phase 0–2代码清理推迟到两阶段设计共同闭合，期间旧gate只代表历史checkpoint，
  不得阻止正式设计更新。
- 少量罕见故障可能需要人工修复；这是以显著降低实现和运维复杂度换取的明确选择。
- 若信任边界升级为互不信任tenant、外网直连、法规防篡改或无人值守恢复，应新增
  ADR和威胁/故障验收场景，而不是静默恢复旧设计。

## Required verification

- 全局token的成功与失败路径通过HTTP集成测试。
- Upload hash、package路径/大小、Versioned CAS、idempotency和固定commit read通过。
- Create同步创建initial commit/main且response-loss幂等。
- Upload同步流式处理通常10–100 MB、至少一个接近200 MB的边界样本。
- Import覆盖commit前中断、commit后响应前中断和人工修复分支。
- NONE/STRUCTURAL/FULL_SCAN、REJECT/STRINGIFY和private-ref-before-publication矩阵通过。
- 标准Arrow IPC stream可被client直接读取，截断时由HTTP/Arrow失败。
- Success package被清理，RUNNING/manual-recovery package不被误删。
- Phase 0–1 canonical encoding bytes、Python/Rust核心golden保持不变。
