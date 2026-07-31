# ADR 0009: Proportional Assurance and Trusted Internal Repository

状态：Accepted

日期：2026-07-31

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

Import成功检查固定为：

1. upload bytes的size和raw SHA-256匹配；
2. Dolt产生带operation marker的commit；
3. target ref指向该commit；
4. committed catalog的table set、schema和row count匹配manifest。

不提供`NONE | STRUCTURAL | FULL`选择，也不默认全量读取rows重算content digest。
业务no-change/comparison digest仍由相应capability owner拥有。

Operation只使用`QUEUED | RUNNING | SUCCEEDED | FAILED`。Mutation通过
`idempotency_key + internal request fingerprint`处理response-loss重放。单process
使用durable-root OS lock和per-repository进程内写锁，不建设lease、fencing、
ServiceEpoch或`UNKNOWN/APPLIED/VERIFIED`状态机。

启动恢复只处理遗留RUNNING import：找到matching operation commit则补齐成功结果；
未找到则使用原artifact和key重试一次；多commit、ref矛盾或无法判断时终止为
`FAILED / MANUAL_RECOVERY_REQUIRED`，允许人工修复。

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

正在进行的WP1-R1继续按2026-07-30旧设计完成，并形成独立checkpoint。该checkpoint
仅证明当时工作完成，不构成已发布wire contract，也不产生后续兼容义务。

WP1-R1 checkpoint之后：

1. 先执行Phase 2 contract和delivery skeleton简化；
2. 在开始修订后的WP1-R2之前，执行Phase 0–1简化；
3. 再按新的最小Versioned计划恢复Phase 2实现。

ADR 0008及现有Repository Service Contract、Phase 2 implementation plan和
traceability只继续拥有WP1-R1旧checkpoint；其WP1-R2+语义由本ADR和后续精简后的
owner contract/plan替代。

## Consequences

- WP1-R1中的strict wire、FailureDescriptor、stream envelope和schema snapshot允许
  在checkpoint后破坏性删除或改写。
- Phase 2不再以现有WP0 gate/closure、141项traceability和exact-commit exit作为
  交付前提。
- 少量罕见故障可能需要人工修复；这是以显著降低实现和运维复杂度换取的明确选择。
- 若信任边界升级为互不信任tenant、外网直连、法规防篡改或无人值守恢复，应新增
  ADR和威胁/故障验收场景，而不是静默恢复旧设计。

## Required verification

- 全局token的成功与失败路径通过HTTP集成测试。
- Upload hash、package路径/大小、Versioned CAS、idempotency和固定commit read通过。
- Import覆盖commit前中断、commit后响应前中断和人工修复分支。
- 标准Arrow IPC stream可被client直接读取，截断时由HTTP/Arrow失败。
- Phase 0–1 canonical encoding bytes、Python/Rust核心golden保持不变。
