# ADR 0011: Artifact Directory-Broker Reclaim

状态：Superseded by [ADR 0012](0012-cooperative-artifact-cleanup-and-proportional-assurance.md)

日期：2026-08-12

决策 owner：Backend vNext Repository Storage / P2-R9-S2

关联阶段：Phase 2（P2-R6 operational closure / P2-R9-S2 artifact cleanup）

> 2026-08-13：本ADR记录Round 18–22采用过的设计，但不再是v1实现或评审权威。
> ADR 0012恢复ADR 0009的单一信任域与比例化保障，directory-broker及其同euid对抗
> 证明将在前向简化中移除。

## Context

Contract §12 要求 import 成功且结果已持久化后删除本地 package；§17 要求 package
成功后清理。同 euid prove-only 路径（truncate + 证明 size-0、不 pathname unlink）会
在每次成功删除后永久留下 generation-bound sidecar 与零长度 inode。tombstone budget
只能延缓，不能消除仓库有限寿命，也不能把 `O(n)` 残差称为合规收敛。

Linux 没有 compare-inode-and-unlink 原子操作。对拥有目录写权限的非协作同-euid
actor，任何 `stat` / `open` / `fstat` → `unlink` / `rename` / `rmdir` 序列都保留
最后一道换名竞态。因此**不得**声称「同 euid 安全 pathname unlink」。

## Decision

### Impossibility（硬性设计门）

在「Service 与攻击者共享 euid，且二者对目标目录均有写权限」的威胁模型下，不存在
仅靠 pathname 的 inode-CAS unlink。任何同 euid reclaim helper 都不是安全边界。

### Ownership boundary（等价 ownership）

`artifacts/<repo>/ready/`（及同协议下的 stage 目录项修改）的 **目录项修改权** 归
独立安全主体 `artifact-broker`：

- 目录 owner 为 broker UID；`gateway`（Service）对该目录 **无写**（不可
  `unlink` / `rename` / `rmdir` / `linkat-create` / `mkdir` 子项）。
- 所有目录项变异经本地 Unix-domain socket helper：peer credential 鉴权、SCM_RIGHTS
  传递已持有的 inode fd，请求携带 `(name, expected_dev, expected_ino, op)`；broker
  在独占目录写权限下复核后执行。
- TCB = broker helper + kernel + durable-root single-writer 部署假设。同机其他
  `gateway` euid 进程视为不可协作，但因无目录写权限而不能换名竞态。

### Rejected alternatives

- 同 euid pathname reclaim / `.reclaim-*` 私有目录：被竞态否决。
- 仅硬化 tombstone budget（原子 reservation / 全 inventory）：可改善可控性，但
  **不满足** Contract 成功清理语义；明确禁止作为 S2→S3 合规路径。
- 把 reclaim 推迟到 S3：在宣称 S2 完成的前提下不可接受。

### Semantic consequences（Contract 层）

成功 cleanup 后，Service-owned filesystem 对象不得随成功次数 `O(n)` 永久净增；
允许严格常数残差（实现私有）。清理失败仍不得改写已成功 commit / operation。

### Restore（ineligible）语义冻结

| exact ready | 允许动作 | 可否 clear intent |
| --- | --- | --- |
| 缺席 | broker 将 expected inode link 到 ready 名 | 仅当 ready 复核 `(dev,ino,full size)` 成功 |
| 已是 expected 满 size | 幂等成功 | 是 |
| foreign regular / symlink / open EIO·EPERM | 不得因创建 matching verify 而 clear intent；verify 至多诊断 hardlink | 否 |
| victim size-0 | 失败 | 否 |

clear intent 之后，admission 打开 `artifact_id.hex` 不得接受与 deleted inode 不一致的
foreign bytes。

### Abort → 路径 3（S2 no-go）

若 Compose/镜像无法引入第二 UID + helper、或无法在不给 `gateway` 目录写权限下完成
upload/admission/delete、或本 ADR 威胁模型无法测试证明：保持 `S3 ready = no`，以
诚实文档暂停；**不得**退回纯 budget 合规叙事。

### Tombstone budget

若保留 `artifact_tombstone_budget`，仅作过渡 circuit breaker（projected reservation、
全 inventory、有界重试/分页），**不是** Contract 合规证明。

## Consequences

- Dockerfile / Compose：双用户、entrypoint 拉起 broker、ready 树所有权迁移。
- 触碰 deployment boundary → checklist §1.1 Compose/build 定向门禁。
- 存量 `.deleting-*` / `.detach-*` / `.unlink-verify-*` / `.unlink-stage-*` 必须有
  broker reclaim 收敛路径。
- 测试 profile 可用同 UID in-process broker 作为 **功能** 替身；OS 隔离证明属于
  容器门禁，不得把 in-process 替身称为跨主体安全证明。

## Related authority

- [Repository Service Contract](../contracts/repository-service.md) §12 / §17
- [P2-R6 Operational Closure Execution Plan](../plans/p2-r6-operational-closure-execution-plan.md) §4.1
- [ADR 0009 Proportional Assurance](0009-proportional-assurance-and-trusted-internal-repository.md)
