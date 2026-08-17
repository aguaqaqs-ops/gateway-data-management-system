# ADR 0012: Cooperative Artifact Cleanup and Proportional Assurance

状态：Accepted

日期：2026-08-13

决策 owner：Backend vNext Architecture / Repository Storage

关联阶段：Phase 2（P2-R6 operational closure / P2-R9-S2 artifact cleanup）

Supersedes：[ADR 0011 Artifact Directory-Broker Reclaim](0011-artifact-directory-broker-reclaim.md)

## Context

[ADR 0009](0009-proportional-assurance-and-trusted-internal-repository.md)把v1冻结为单一信任域：
安全、恢复和一致性投入必须对应当前可信边界中的具体威胁、可说明的业务损失、已确认
consumer要求或已发生的高概率故障。Repository import package通常为10–200 MB临时输入；
成功后的权威数据是Dolt commit与持久化operation result，package可由上游备份重放。

ADR 0011把artifact cleanup的威胁模型提高为「Service与非协作攻击者共享euid，且双方均可
修改目标目录项」，并据此引入双UID directory-broker、SCM_RIGHTS、pidfd bind、独立helper
生命周期以及quarantine/detach/unlink-verify/stage、generation、receipt和residual proof状态机。
这套机制证明的是局部目录项隔离，但同euid任意代码执行通常还意味着Service内存、token、
进程、SQLite或其他同UID状态已经失守；当前部署没有不可信插件、tenant代码、共享RWX root或
独立合规要求支持该攻击模型。

截至本决策，`tests/test_artifact_cleanup.py`已达11,667行、181个测试函数，broker/client/
server/cleaner等相关生产模块也形成数千行专用协议。复杂度本身已经产生新的启动、锁、IPC、
资源边界和部署故障面，保障成本与临时package的业务风险不成比例。

## Decision

### Trust boundary

V1延续ADR 0009的单一信任域：

- 由部署方授权、能以Service euid执行代码、写durable root或管理宿主机/container的主体，
  属于可信部署组件，不作为artifact cleanup的对抗者；
- bearer token只授予HTTP业务能力，本决策不把token本身解释为本地文件系统能力；但一旦攻击者
  已取得上述本地执行/写权限，v1不再为artifact目录建立单独的更强安全边界；
- Service仍不信任HTTP输入、archive成员、caller提供的标识或路径，也不允许caller选择本地
  pathname；这些外部输入边界继续fail closed。

因此，v1不保证抵御同euid非协作actor在`stat/open/fstat`与`unlink/rename`之间恶意替换
pathname。实现和评审不得把该范围外性质重新设为S2、S3或发布硬门。

### Baseline hardening retained

「不对抗同euid actor」不等于取消基础安全与数据保护。以下低成本边界继续保留：

- server-generated artifact ID与server-owned root，拒绝caller path和root逃逸；
- `dirfd`相对操作、`O_NOFOLLOW`/不跟随symlink、regular-file与必要的scope检查；
- bounded upload、size/SHA、非shell执行、secret/log脱敏和container non-root；
- durable-root single-writer lock、per-artifact admission pin和统一durable eligibility判断；
- 不删除PENDING/QUEUED/RUNNING或`MANUAL_RECOVERY_REQUIRED`引用的package；
- cleanup不得改写已经成功的commit或operation result。

这些检查面向错误输入、普通实现缺陷和协作并发；它们不是同euid恶意换名的安全证明。

### Cooperative cleanup protocol

新写路径不再创建cleanup sidecar或专用ownership proof。最小协议为：

1. 只枚举server-owned exact artifact/known staging shape；未知、畸形、symlink或越界对象只做
   脱敏诊断；
2. 取得artifact admission pin，并从control DB统一重读eligibility；
3. 对exact ready名执行普通`dirfd`相对unlink；协作的worker、recovery、admin和cleaner必须
   复用同一锁与eligibility路径；
4. 仅在artifact已经eligible后把`ENOENT`视为幂等完成；其他I/O错误保留状态、记录日志并由
   后续sweep重试；
5. 成功result先持久化，cleanup后执行。cleanup失败不回滚业务成功；普通失败/orphan仍按TTL
   best effort处理，磁盘压力由free-disk admission和运维诊断控制。

正常成功路径的目标是package消失，且实现不得主动为每次成功永久创建新dentry。但这是一项
功能与容量目标，不再要求directory-broker、inode-CAS unlink证明、严格常数残差证明或
tombstone budget作为Contract合规门。

### Removed v1 mechanisms

以下机制不是v1要求，前向简化时删除，不再独立修补：

- 双UID `artifact-broker`、broker socket/control socket、SCM_RIGHTS与pidfd bind；
- broker专用peer/capability/角色矩阵和helper supervision；
- 新建`.deleting-*`、`.detach-*`、`.unlink-verify-*`、`.unlink-stage-*`、`.reclaim-*`；
- active delete intent generation、residual receipt/proof以及与其绑定的restore/reclaim状态机；
- 只为上述永久sidecar服务的`artifact_tombstone_budget`和projected reservation。

既有control DB版本不得倒退。可以保留不再写入的兼容列，除非现有constraint要求新的前向
migration；不得为了代码整洁执行高风险破坏性schema downgrade。已有sidecar或legacy cleanup
metadata只需要一条有界兼容路径：在root lock下，eligible且可解释者best effort收敛；protected、
畸形或矛盾者保留并诊断，允许operator处理。不得继续维护完整对抗竞态矩阵。

### Proportional verification

测试按业务后果而不是历史修复轮次分层：

- Dolt commit/main CAS、control DB transaction、跨repository/root误操作等不可逆或大故障域
  不变量保持强验证；
- artifact cleanup直接验证生命周期eligibility、protected retention、正常删除、I/O重试、
  restart、协作admission race和路径/symlink边界；
- 崩溃测试覆盖「业务成功持久化前」「成功后cleanup前」「cleanup失败后重试」三个语义屏障，
  不穷举每两个系统调用之间的调度窗口；
- `r8_*`、`r9_*`至`r22_*`等按实现轮次命名的broker/sidecar证明不再是权威门禁。保留的回归
  必须改写为Contract行为测试；其余随生产机制删除。

测试规模没有机械行数配额，但同一不变量只保留一处权威断言，同构shape使用共享参数表，
不得为范围外同euid对抗者重新建立探针墙。

## Consequences

- 生产部署回到单一Service安全主体；artifact目录由Service正常拥有。删除broker会触碰
  Dockerfile、entrypoint、Compose、UID/GID、socket和readiness，最终候选必须按
  testing conventions重建当前HEAD并执行Compose门禁，中间提交不重复构建。
- 实现显著减少私有协议、持久化状态组合和测试数量；代价是明确不抵御已取得同euid本地执行
  能力的非协作actor。
- cleanup泄漏主要是容量/可用性问题；free-disk admission、日志、重试与必要的人工处置是v1
  的接受方式。
- 本ADR不降低Dolt commit、target ref CAS、operation result、跨root路径安全或protected
  artifact retention的保障强度。

## Reopen conditions

出现以下任一条件时，必须新增ADR和具体威胁/验收场景后再考虑privilege-separated broker或
等价隔离，不得静默恢复ADR 0011：

- 同机运行不可信插件、tenant代码或其他非协作本地进程；
- multi-node/shared writable root、共享RWX volume或互不信任container共同修改目录；
- artifact成为不可重建的权威数据，或错误清理产生明确不可接受的业务损失；
- 法规、合规或安全评审明确要求进程级目录项隔离；
- 已发生可复现的同euid恶意换名攻击，而不是普通协作并发bug。

## Related authority

- [ADR 0009 Proportional Assurance](0009-proportional-assurance-and-trusted-internal-repository.md)
- [Repository Service Contract](../contracts/repository-service.md) §3 / §12 / §17
- [P2 External Interface Handoff](../plans/p2-external-interface-handoff.md)
- [Testing Conventions](../../../testing-conventions.md)
