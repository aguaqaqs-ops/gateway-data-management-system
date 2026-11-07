# W4 prepare_import 局部续租诊断设计

2026-11-06，p6-backend-design；依据 Owner DC80。关联[单步诊断设计](p6-submit-single-step-diagnostic-plan.md)及[独立审核 §59–60](p6-submit-single-step-diagnostic-scope-review.md)。本文件形成待定向审核的具体范围，不是运行 GO。

**2026-11-07 Owner 执行流程补充：** 后续测试按[GC 修复计划的测试环境执行授权](p6-worker-gc-scheduling-repair-plan.md)推进；已通过范围内不再每个最终 manifest 另签 GO。下文旧候选专属 GO 的要求保留为历史过程，不覆盖该新授权；原输入/身份、必要守护和正式基准边界保持。

## 问题与解释边界

h 已在真实续租失败后 stall；新 observer 的降级、持续守护和回收已获 §59 核验，但失租附近没有 Python 业务帧。下一候选只回答：prepare 的哪一组既有调用仍未返回，以及延迟发生在 heartbeat helper 入口之前、进入 helper 时已越过真实 deadline，还是实际 LeaseSession.heartbeat 调用内部。调用内部滞留不能继续唯一归因为 SQLite、mutation lock、GC 或 GIL。

不重复已通过的合成 probe，不依次要求“小样本再完整 Submit”两轮诊断，不改业务 Contract、校验、TTL、heartbeat interval、drain timeout 或产品取消行为。局部候选成功只表示 prepare 完成，不能记为 Submit 完成、lease 根因关闭或正式基准结果。

## 输入、入口与唯一工作范围

- 只在 CT05 取得有效自有占用后执行；CT108 不增加负载。冻结产品 `1f9731dfc3a202cc2b7191d6726779ce40d5f91a` 和 §52 已核三镜像，保留真实 SQLite、LeaseSession、worker executor 线程及 RS parent catalog/materialization 读取。
- 复用 05 已运输核验的 `p6bw4s4h120261105b`、completed_through=v2-preview 的原始 checkpoint；accepted W4 10% input manifest 为 `4c5638df32973282507937c1232c09117b40023f8b03f3d94caf7c160f87aac7`，其余 source/input/cache/卷内容与镜像绑定沿既有精确核验。源 RS run-bound full identity 缺口仍仅按诊断输入例外记录，不能声称 carried。
- 新项目、幂等键、证据目录和三卷副本；不得使用失败 h 的活动卷或修改旧清单。通过一次真实 `POST /v1/workspaces/{workspace_id}/submit-attempts`，委托原 route、accept_submit_operation 和 acceptance transaction 创建 PREPARED attempt/QUEUED operation/PENDING prepare_import；不手写 DB 事实，不复制 acceptance 逻辑。只允许此一次 acceptance，不重跑 Preview，不进入后继 submit_import/await_import。
- 隔离栈只有一个 worker，候选专用 Compose override 明确 `restart: "no"`；保留 backend/RS 的原服务身份与行为。启动前确认来源没有其他可领取/恢复中的工作；实际被领取的 operation/step 必须为本次 acceptance 的目标 prepare。候选须给出避免 acceptance 与 worker 启动之间身份绑定竞态的具体顺序，未知任务不得执行。
- 使用外置诊断入口加载被冻结 worker 的原 production composition。对原 `WorkerRuntime._run_claim` 作薄包装：确认目标后原样调用；只有正常返回（包括原 executor join、ack 校验和 lifecycle 完成记录）后调用同一 runtime 的现有 `WorkerLifecycleController.request_drain()`。让原 run 循环在下一次 claim 前按 DRAINING 正常退出。异常原样传播，不将失败转成功。
- prepare 正常 `publish_successor` 事务保持，成功时 submit_import 应仍为 PENDING，不能实际领取或执行。`claim_limit=1` 不是总次数上限；不得用它冒充单步限制。不得在 prepare 执行中提前 SIGTERM/drain，也不改 180 秒 drain timeout。候选不得复制 run/heartbeat/handler/事务循环、删掉 join，或另造 worker 状态机。

## 最少观测与扰动

只用外置函数边界包装并原样委托，不改冻结源码文件或镜像内产品；具体绑定点与源码摘要须在候选列明。若无法做到，不偷偷复制函数或改镜像，先将具体差异交设计收窄。

粗阶段按既有函数入口/返回留记录：build input/parent resolution；projection/snapshot 与 parent materialization/mutation planning；canonical publication/round-trip 与 prepare 完成。实际可用边界如 `_build_prepare_import_build_input`、`_build_frozen_projection`、`build_import_mutation_snapshots`、`_materialize_parent_rows`、`plan_import_mutation`、`publish_canonicalization` 和外层 prepare/claim；允许同组多个既有函数事件，不为了人为拼出三个连续区间重写函数体。嵌套事件带深度，汇总不重复相加；保持返回值/异常，不输出业务行、SQL、凭据或 lease token。

续租只包三个现有边界：

1. `_run_claim` 取得原传入的 monotonic claim_anchor；
2. `_heartbeat_until_due` 入口/返回记录原参数 lease_deadline、返回的 heartbeat_succeeded/renewal_anchor 与异常类别；
3. 同一 `LeaseSession.heartbeat` 的入口/返回及异常类别。

记录 monotonic_ns、线程 ID、事件名和必要的 operation/step 关联；UTC 仅用于日志对齐。expected due 只能由实际 claim/renewal anchor 加原 interval 派生，并标 `derived`；helper 入口不是 run 循环内的实际 loop-entry，DB UTC expiry 不是 runtime monotonic deadline。暂不新增 mutation-lock/UOW 内部细分，也不因未记录这些字段就补造推断。

RSS 复用既有每 5 秒轻量外部采样，按时间对齐而不在每行或 heartbeat 内额外读进程树。使用标准有界日志输出，每条最多 2 KiB、总量最多 4096 条/8 MiB；45 分钟正常 10 秒 heartbeat 下约 270 轮，四个入/出事件约 1080 条，另留阶段/异常余量。无逐行事件、GC callback、stack profiler、热路径 fsync 或自定义持久队列。写入/达到上限等观测失败明确记录为诊断缺口并按候选停止路径收束，不能忽略必要守护失效或将其判产品故障。事件日志有调度/I/O扰动，所得耗时不能视为正式性能。

本候选用绑定源码的诊断入口 ready 记录、worker PID/starttime/镜像和必要 guardian 就绪来核启动，不再调用 py-spy，也不要求有效栈作为 acceptance 前置条件；h 已证明该输入下可选栈持续缺失，本次改用明确函数边界回答缺口，不重复旧 canary。

## 一次性预算、停止与收尾

保留 45 分钟绝对观察上限与 3600 秒外层硬上限，候选明确各自起算点并保证初始化/清理也受外层约束。h 的 prepare/失败窗口约 2114 秒，只支持覆盖既存故障窗口的选择，不是完成时间估算；本次不逐次加时、不在执行中重置 deadline。启动 MemAvailable ≥48 GiB，既有逐文件系统剩余空间算法及 worker RSS 40 GiB/host available 8 GiB/disk free 10 GiB 停止线保持。

lease_lost、cancel、业务失败、120 秒 stall、身份/必要资源/观测故障或预算触发后，不再进入新工作，保留最后事件。真实 worker 内部仍按原 fence/join 语义处理：失租不等于线程立即终止，不强杀 Python 线程。外层有界停止只作用于自有诊断进程/容器，记录正常退出、强制终止和回收事实；不能将强制终止称为 prepare 正常完成。保留三卷及原始证据，所有自有进程/容器/网络确认静止后才释放锁，未确认则保留占用报告处理，不自动重试。

完整 controller 摘要在文件关闭后由外层另记，不能在自身日志内写入其“最终摘要”。结果区分 acceptance 次数、目标 claim 次数、prepare 状态、后继 PENDING/未 claim、诊断事件缺口、失租/取消、清理与锁；原输入/state MATCH 不作为业务成功。

## 准备、验证与审核

新唯一实施者 `01a1b107-11ba-7681-a7cf-afb1591a67d2` 准备，接续审核者 `01a182d8-4dfd-7441-b9db-4deefdc4e0ac` 独立审核。设计范围通过后才准备外置候选；不新建角色。优先复用原身份/副本/guardian/收尾 helper，候选只增加必要入口与观测，不创建通用框架。

Owner 于 2026-11-06 明确：既定设计范围内的常规审核修复，由实施者与审核者直接闭环。发现、修订、必要定向测试、精确清单复审及符合既定范围的一次 GO 直接投递对方，不把协调者中继或回执作为接续条件；阶段结果与异常简要同步设计即可。只有涉及设计/Contract、范围或预算变化、证据沿用例外、新的 Owner 取舍，或直接通信失效时才交协调者处理。该流程适用于当前候选 b；已解除的接管前只读限制不再作为停工理由，候选专属一次 GO 和实际失败停止规则继续有效。

CT05 少量 focused 工具测试覆盖：原 runtime 正常委托、prepare 成功后才 drain 且无第二 claim；异常/错误目标不被转成功；deadline/anchor 字段真实与派生标识；观测有界与未回收不解锁。测试不证明现场根因，不跑完整 runner、已通过的 Compose 小旅程或合成大输入。产品镜像不变，不以外置工具无变更为由省略对实际 Compose override/入口/no-restart 的具体接线审核；实际候选运行核容器身份及退出事实。

最终候选冻结源码/工具/override/输入/预算/固定命令的 manifest，提交准备及 focused 记录。审核者针对精确 manifest 给一次运行 GO 后才允许 acceptance 和节点诊断；旧 h GO 已消耗。本文件不授权正式测量恢复、合入产品、推送或清理历史证据。
