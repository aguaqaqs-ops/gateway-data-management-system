# Proportional Assurance and Risk-Based Verification Policy

状态：正式跨阶段政策（Accepted）

日期：2026-08-13

Policy ID：`gateway-vnext.proportional-assurance-and-risk-based-verification`

Owner：Backend vNext Architecture

适用范围：Phase 0–9及后续功能、维护、评审和生产硬化

决策依据：

- [ADR 0009: Proportional Assurance and Trusted Internal Repository](../adr/0009-proportional-assurance-and-trusted-internal-repository.md)
- [ADR 0010: Minimal Golden and Ordinary CI](../adr/0010-minimal-golden-and-ordinary-ci.md)
- [ADR 0012: Cooperative Artifact Cleanup and Proportional Assurance](../adr/0012-cooperative-artifact-cleanup-and-proportional-assurance.md)

## 1. Goal

安全、恢复、一致性、证据和测试投入必须与现实风险相称。系统优先保证业务事实正确、
外部输入边界安全、关键写入可解释以及主路径可维护；不为缺少当前威胁、consumer或损失依据的
假设建立通用安全框架、全故障点状态机或无限增长的证明墙。

本政策不是降低安全要求。它区分真正的安全边界、不可逆业务损失与可重建临时状态，让强保障
集中在高价值对象上，并防止局部低风险功能因逐轮审核演化成独立平台。

## 2. Default trust and deployment boundary

除owning contract或新ADR另有规定外，vNext采用以下默认边界：

- 少量协作者、可信内网、受控部署和单一组织信任域；
- 由部署方授权、能够以某服务euid执行代码、写该服务durable root或管理其宿主机/container的
  主体，属于该服务的可信部署组件，不作为同一服务内部功能的对抗者；
- 模块化单体内的模块、同一owner的worker和受控内部进程默认协作，不建立零信任内部协议；
- bearer、session或业务credential泄漏的影响按owning authentication contract处理，不通过
  某个局部filesystem、cache或temporary artifact机制声称补偿整个进程已经失守；
- multi-tenant不可信代码、第三方插件、共享RWX root、跨组织主体、外网直连或法规隔离不属于
  默认假设。进入任一场景前必须修订owning contract/ADR和验收场景。

同机内部进程不是天然可信；这里的“可信”是当前明确接受的部署假设。设计不得静默把它升级为
对抗边界，也不得在没有新决策的情况下宣称抵御同UID任意代码执行。

## 3. Baseline protections that always remain

比例化保障不能用来跳过低成本、行业常规且能阻断大故障域的问题。以下边界默认保留：

- HTTP/API认证与当前业务授权，secret最小暴露和日志脱敏；
- caller输入的schema、类型、大小、枚举、标识与资源上限；
- archive/path traversal、symlink/root逃逸、caller选择server pathname和跨scope误操作防护；
- 非shell执行或安全参数传递，禁止把不可信文本拼入shell/SQL/命令；
- 数据库事务、约束、幂等键和写入所需的CAS/precondition；
- container non-root、最小必要filesystem权限和受控dependency版本；
- 网络、文件、进程、线程和stream的有界使用及确定性释放；
- 错误和诊断不得泄漏secret、raw业务payload或server私有路径。

具体机制仍由owning contract决定；本节不要求为每项再建立独立evidence subsystem。

## 4. Risk classes and default assurance

每个新功能、重大重构和审核Finding先判断受影响对象，而不是从最强机制开始。

| Risk class | Typical objects | Default assurance |
| --- | --- | --- |
| **A — authoritative / irreversible / boundary** | 权威业务事实、commit/main、资金或审批结果、认证授权、跨Workspace/Repository写入、破坏性迁移、不可恢复delete | 强contract和negative tests；事务/CAS/幂等；关键crash/restart语义屏障；必要时人工确认、备份或rollback计划 |
| **B — durable recoverable operation** | operation状态、queue、checkpoint、可重放但影响用户可见结果的workflow | 明确owner和terminal语义；重试/接管；有限的故障注入；矛盾时fail closed或人工修复 |
| **C — derived / rebuildable / temporary** | cache、preview、projection中间件、临时package、scratch、可重算artifact | 普通校验、bounded资源、best-effort cleanup、重试和诊断；失败不得污染A类事实；允许人工处置罕见残差 |
| **D — internal implementation detail** | helper、adapter、纯转换、私有缓存键、测试材料 | 单元/contract测试与类型检查；没有独立consumer时不建立持久协议、版本轴或安全证明体系 |

风险等级由最严重的实际后果决定，但不得把“理论上可能出错”直接等同于A类。提出A类必须说明
权威对象、不可逆后果和当前调用路径；可从上游重放、重新计算或安全丢弃的对象通常是C类。

## 5. Design gate for additional assurance

新增安全、恢复、一致性、审计、治理或evidence机制前，设计/评审必须至少给出以下依据之一：

1. 当前可信边界内的具体威胁与可执行攻击路径；
2. 可量化或可说明的业务损失、不可逆数据风险或大故障域；
3. 已确认consumer、法律/合规或运维责任的明确要求；
4. 已发生或可稳定复现的故障，且较简单控制不足以解决。

同时记录：受保护资产、信任边界、风险等级、最小控制、失败处置、测试owner、明确非目标和
reopen condition。缺少这些信息时，默认选择标准平台能力与最小机制，不预建未来框架。

下列任一变化属于架构升级门，不能在普通代码审核中直接引入：

- 新OS UID/GID、安全主体、privilege-separated helper或独立service；
- 新自定义IPC/RPC、capability/token/peer credential或进程监督协议；
- 只为recovery/security/evidence存在的新durable状态机、journal、receipt、generation或版本轴；
- quarantine、sidecar、tombstone、shadow copy或per-operation proof的持续创建；
- multi-tenant隔离、同机非协作进程、shared writer/RWX root或恶意本地actor威胁模型；
- 穷举syscall/线程调度窗口、跨进程攻击schedule或形式化evidence closure的测试体系。

上述机制只有在owning contract明确需要且ADR比较过更简单替代方案后才能进入主路径。审核者可
列出安全探针供实现者验证已接受的高风险边界，但不得用探针本身扩大威胁模型。

## 6. Verification policy

### 6.1 Test semantic barriers

测试证明外部行为和业务语义屏障，而不是穷举内部步骤：

- 对A类对象覆盖effect前失败、effect后response loss、重复请求、stale precondition和恢复；
- 对B类对象覆盖claim/terminal状态、retry/takeover和一个代表性的矛盾分支；
- 对C类对象覆盖正常路径、边界输入、失败不污染A类事实、后续重试或可诊断；
- 对D类对象覆盖公开给owner的最小输入输出，不为私有函数复制production状态机。

只在已发生故障、并发不变量无法由更高层测试表达，或owning contract明确要求时增加精确
barrier测试。不得默认在每两个system call、transaction statement或线程事件之间注入竞态。

### 6.2 One owner per invariant

- 每个Contract不变量只有一个权威测试owner；其他层只做必要integration smoke，不复制矩阵；
- 同构shape使用共享参数表，组合矩阵必须说明每个维度会改变哪条行为；
- 测试按业务/Contract行为命名，不按审核round、finding编号或实现技巧命名；
- production机制被删除时，其mock、fixture、probe和historical proof一并删除；Git历史负责考古；
- 单文件或单功能测试明显主导所在包、测试代码远大于被保护的低风险实现，或新增测试主要证明
  私有interleaving时，必须先做owner/风险/重复性复核，再继续追加。

没有统一的行数或test/production比例硬门；数字容易被拆文件规避。评审应依据风险等级、独立
不变量数量、维护成本和实际故障收益判断，并优先删重、参数化或提升到语义屏障。

### 6.3 Irreversible actions

不可逆业务数据删除、覆盖、外部发布或权限变更保持强验证，但强度集中在：

- exact target/scope与授权；
- transaction/CAS/idempotency或plan/confirm边界；
- effect前后结果可解释；
- 失败不扩大到其他aggregate；
- 必要的backup/rollback/operator路径。

这不自动要求每个内部unlink、temp cleanup或derived cache eviction获得同等证明。临时、可重建
对象按C类处理，除非它同时是唯一恢复证据或其误删会破坏A类事实。

## 7. Phase and review application

每个Phase、WP或纵切在设计入口做一次轻量风险登记，不建立新的通用risk平台。最少记录：

```text
authoritative facts:
recoverable durable state:
derived/temporary state:
external trust boundaries:
accepted deployment assumptions:
highest risk class:
required semantic barriers:
explicitly out of scope:
reopen conditions:
```

代码审核Finding必须先映射到已接受边界：

- 边界内且影响A/B类对象：按相应强度修复并验证；
- 边界内但只影响C/D类：优先简单修复、重试、诊断或删除复杂机制；
- 只在未接受的更强威胁模型下成立：记录为reopen候选，不得直接成为当前release blocker；
- Finding暴露的是为范围外威胁新增机制自身的bug：优先删除或降级该机制，不循环加固。

Phase 3及之后的capability、Operation Runtime、业务纵切、性能优化、cutover和production
hardening均受本政策约束。Phase 9的“安全审计/生产硬化”不是重新打开所有理论威胁；它只验证
当时accepted contracts、部署边界和已登记风险。

## 8. Examples

- Canonical bytes和business digest有跨语言/业务consumer，属于A/B类边界；保留必要golden，
  但不需要fixture自签名、run evidence closure或每次exact-commit证明。
- Repository commit/main CAS是A类；临时import package成功后的cleanup是C类。前者保留强
  transaction/recovery测试，后者使用协作锁、best-effort删除、重试和容量诊断。
- Preview cache、comparison临时batch和可重建projection默认是C类；不能因理论cache poisoning
  引入独立安全主体，除非外部不可信输入可越过现有校验污染A类事实。
- Operation effect marker在确实用于response-loss恢复时是B类；没有external effect的纯compute
  failure不需要复制通用effect taxonomy、journal或receipt。

## 9. Reopen and exception process

当默认信任边界、风险等级或业务损失发生变化时：

1. 更新owning contract的事实与验收；
2. 新增或修订ADR，明确威胁、替代方案和迁移；
3. 更新本政策引用的阶段计划/测试owner；
4. 再实现更强机制和安全探针。

紧急已利用漏洞可以先做最小containment，但不得把临时措施静默固化成长期架构。事后必须补齐
owner、边界、移除或正式接受决策。
