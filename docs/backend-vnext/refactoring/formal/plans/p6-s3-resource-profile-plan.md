# P6 S3 容量补测资源档：最小配置与执行候选

2026-11-08；**待原 E 独审的小范围方案，不是已实施/已通过的资源档**。本稿只处理 S3 完整 W3/W4 Preview 测量的 worker 资源配置和证据。产品改动、节点测试、容器构建及正式样本均尚未执行。依据 [DC95](p6-s0-owner-decisions.md#dc95-s3补测worker资源上调授权owner2026-11-08)、[S3 容量停止报告](p6-s3-e-capacity-stop.md)、[E 终审 §61–64](p6-s3-e-review.md)、[并行边界](p6-s3-s4-parallel-plan.md)及 [S4 kickoff §3](p6-s4-kickoff.md#3-路径所有权与三线协调)。

## 1. 已知预算、证据和条件

原 V=`774acf33a3f12eeccfbb440d9446ffde9c1c6d43`、H=`685c97f4e275e5e52b42ea403a07a5e96b0695b2` 仍为 `BLOCKED_CAPACITY`。CT108 原 W3 MODIFIED_ONLY warm 的 v1 Submit 在 M24 预约拒绝，v2 Preview 未到；原失败、私有归档及 04 carried 来源 worktree 保留。原失败的首次 stage、requested/live、表号未知，不从本次模拟倒填。

原归档只读复算已由原 E 审核者核收：固定 V774 clean worktree、原三卷 tar SHA `ba1b07d4e5d19824532f70a432dc0557cc7781904c26e4f1621a90a16cae4444`，631 张 canonical 表、683,508 行；实际 Arrow `Table.nbytes` 总计 152,303,216 B，canonical IPC mapping 总计 158,795,630 B。现行 `import_publication.py` 的逐表 Python 行对象预约式合计 26,716,516,480 B；按 reader 生命周期和 replay 预约重构的读者+replay 同驻留为 2,961,297,822 B，总计 **29,677,814,302 B（约 27.64 GiB）**。M24 的模拟在第 468 张表越界；M40/44/48 在这段模拟中没有越界。报告原件 `/home/dev/gdds-test-tmp/p6-s3-capacity-ro-control-v774-r1/captured/report.json` SHA256=`89fb32ffe03c87852fa4a0a9a688ca687b29066efb0e2ebc434bdbfecb5a5fc6`。该模拟没有全量 pre-adapter 预约、没有同时打开全部 reader，也没有构造行/SQL；它不是原 Submit 的实测 live 或首次抛点，更不能证明 M40 的完整旅程容量。

原固定性能 driver `/home/dev/gdds-test-tmp/p6-s3-e-tool-final-774acf33a3-fixed/preview-performance-driver.py` 实际调用 `real_dump_journey.py --scope t4-identity`：v1 Preview→Submit→Archive 建立基线，计时对象是 v2 Preview；明确省略重复 Preview、v2 Submit 和 History。因此 v1 单侧 Submit 是本次共同准备前置，不把另一个阶段的 v2 双侧 Submit 当作 S3 测量必经路径。v2 FULL Preview 的两侧比较/记录真实驻留仍未知；W3 FULL、W4 各模式与正式统计均未测。

CT108 guest `MemTotal=67,108,864 kB`（64 GiB）。本稿只读现场的 `MemAvailable=66,978,116 kB`，当时无节点 marker/运行容器；这是当前空闲快照，不是正式运行中的余量证明。原 W3 三容器 inspect：worker `HostConfig.Memory=32 GiB`，backend 与 Repository Service 均为 0（未设容器硬限）；worker 原 `memory.peak=1,212,547,072 B`、OOM 计数 0。旧原件没有 backend/Repository Service 的峰值，不能据低 worker 峰或低 RSS 把预算式调小，也不能据空闲快照保证运行中 guest 不受压。正式执行前在实际选定节点重新核工具链、缓存、输入、服务、端口、marker、`MemAvailable`；运行后补采三容器 `memory.peak`/`memory.events`、worker `memory.max`、host 可用内存，数值与发生时间分列。

## 2. 本轮唯一有限诊断档

| 项 | 现生产默认/原失败条件 | S3 新档诊断候选 |
| --- | ---: | ---: |
| worker hard envelope | 32 GiB = 34,359,738,368 B | **48 GiB = 51,539,607,552 B** |
| worker 工程 reserve | 8 GiB = 8,589,934,592 B | **8 GiB = 8,589,934,592 B** |
| 显式 operation M | 24 GiB = 25,769,803,776 B | **40 GiB = 42,949,672,960 B** |
| kernel N / active operation | 1 / 1 | **1 / 1** |
| guest 64 GiB 中非 worker 容器及系统名义余量 | 32 GiB | **16 GiB** |

选择 48/8/M40 是 **一次固定档的条件性诊断**，不是“已证足够”的生产档或无界试探。与上述 v1 重构账本相比，M40 尚余 13,271,858,658 B（约 12.36 GiB）给未复演的 operation 前段及后续必要阶段；这不是实测空闲内存。worker hard limit 留 16 GiB 给 Repository Service、backend、OS 与文件缓存。原 RS/backend 未设 hard limit，故在开始时核 guest 空闲，并在当次三容器记录各自 peak/events；若服务/系统实际压力侵蚀这 16 GiB，停止本档后续队列、留原始失败，不增 M 重试。保留 worker cgroup 限制、M 增长前拒绝、N1/单 active。当前不提高 CPU 配额，记录 32 vCPU guest 与实际 `Cpus_allowed_list`/容器配额；产品 kernel N 仍 1。

新档如能完成，只能说明 **48/8/M40 条件下**的该 workload/模式/同 worker 旅程和计时。原 M24 W3 失败保持独立，不能写成旧配置容量 PASS 或与旧硬件组混算提速。若要将新档作为 S3 退出资源条件，交接须明确条件、实际各项原件和独审结论；S3 exit/tag/push 仍按阶段手续另办。

## 3. 最小产品/工具改动与写入归属

1. `vnext/backend/src/gateway_backend/settings.py`：保留 `OperationWorkerSettings.kernel_memory_budget_bytes` **必填**、`memory_envelope_bytes` 默认 32 GiB、`memory_reserve_bytes` 固定 8 GiB；把“默认 32/8/M24”与**可显式配置的有限上限**分开。envelope 接受正整数且 `≤64 GiB`，M 接受正整数且 `≤56 GiB`，并保持 `M≤envelope−8 GiB`；既有 `mode="before"` 整数检查继续拒绝 bool、float、符号/非十进制字符串。移除 envelope 必须等于 32 GiB 的固定值断言，reserve 仍必须等于 8 GiB；其他固定租约/并发项不动。现 `WORKER_MAX_KERNEL_MEMORY_BYTES=24 GiB` 在此被用作绝对上限，实施时改名/拆为“可支持上限 56 GiB”和原默认部署数值，避免把可配上限误称默认 M。`kernel_threads` 的现有通用范围不在本轮改动；部署仍显式为 1，`max_in_flight=claim_limit=1`。
2. `vnext/deploy/compose.yaml`：只将现有 worker `GATEWAY_BACKEND_OPERATION_WORKER_MEMORY_ENVELOPE_BYTES` 与 `...KERNEL_MEMORY_BUDGET_BYTES` 两个同名宿主值接到 worker `mem_limit`/worker env。两处 envelope 使用同一个 `${...:-34359738368}`，M 使用 `${...:-25769803776}`；reserve 保持 `8589934592`，threads 保持 `1`。无新 profile 名、部署开关、sidecar 或默认资源漂移。Compose 默认仍生成 32/8/M24；本轮 driver 在一次候选中显式传 48/8/M40，启动校验与容器真实 `HostConfig.Memory`/`memory.max`必须逐值一致。
3. `vnext/backend/tests/test_worker_kernel_resources.py` 是设置语义权威 owner：保原默认、M 必填、N1/单 active 断言；加一组有意义的矩阵覆盖 48/8/M40 接受、默认 envelope 下 M>24 拒绝、M>envelope−8 拒绝、envelope>64 拒绝、M>56 拒绝、reserve 改值拒绝、bool/float/无效字符串拒绝。Compose 接线在现有部署/worker focused owner 或实际 `docker compose config` 核默认和显式档，不复制同一行为的整套测试。`real_dump_journey.py` 业务路径和 same-worker/cgroup guard 不改。
4. 固定在 worktree 外的 S3 性能 driver 与 outer 脚本由 S3 E 唯一责任人修改、固定 SHA 并先给原 E 独审；把 `--kernel-memory-budget-bytes`、Compose 注入值、`expected` worker env、`HostConfig.Memory`、`memory.max`、结果 profile 标识均改为同一个 **48/8/M40 固定档**，保留首业务观察起同 worker、正常 SIGTERM、cgroup/OOM、完整输入 SHA、成功后清理/失败后保留的原守卫。`t4-identity` 范围、真实 input/census、计时边界和 1 warm+3 样本顺序不改；不得在 driver 中自动切档或静默换 worker。对 RS/backend 的 cgroup peak/events 与 host `MemAvailable` 增加有限的当次资源读数，标明无原历史峰、非同瞬间总峰；不引入通用 observer。除非后续真实失败证明必须进一步归因，暂不加 `OperationMemoryBudget` 字段、部署诊断开关或内部 failure 日志。

写入次序：本稿独审后，S3 实施者只改以上 settings/Compose/对应 tests 与 S3 外置 driver；`import_publication.py`、`table_access/kernel.py` 不动。S4 已在 main 的 A 产品提交 `fb9c7fbcd95b411d7598ade2a93bc8a7e6514697` 及后续 WIP 属另线，Q18 审核文件亦属另 owner；本人只 stage 本稿及后续分配路径。S3 新档候选的完整 SHA/相对 V774、当前 main 和 S4 增量分列，不能把 S4 改善归为 S3-only。Compose 触发当前 HEAD 镜像重建/适用容器门禁；V774 旧镜像不能冒作新资源档验证。

## 4. 验证与首轮执行停止线

本稿阶段 **不运行**。代码独审通过后，先在专用空闲节点按 DC91 marker/离线工具链规则做 settings focused、Compose 默认/48/8/M40 展开核对、五 Python 包 Ruff/mypy；固定提交、clean detached worktree、原 E 复审，再用当前 HEAD 重建适用 backend/worker 镜像并跑受影响 backend 权威包及其 Compose。若某依赖/镜像输入变化，先按 DC67 补齐实际节点缓存；不在 CT201 跑测试。按包闭包与镜像等价分别依据当前来源和实际变更判定，不预写 carried。

首轮只固定 **W3 MODIFIED_ONLY warm**。命令骨架由独审后的外置 controller 在合格节点发起，node driver 保原子 marker，外层不重复取：

```text
ssh -o BatchMode=yes <本次合格节点别名> 'echo OK'
<固定且独审通过的 S3 outer controller> w3 MODIFIED_ONLY warm
  -> <同提交 fixed node driver> --scope t4-identity
     --v2-input-completeness MODIFIED_ONLY --s3-census <已验 SHA 的 2x.json>
     --kernel-threads 1 --kernel-memory-budget-bytes 42949672960
     [worker Compose envelope=51539607552, reserve=8589934592]
```

执行前固定 candidate/driver/输入 SHA、镜像 config digest+全部 DiffID、实际节点/配置/缓存、原子 marker 和无其他栈；同统计组预热与三次测量在同节点同配置。若 v1 Submit 或 v2 Preview 失败、资源 guard/身份/缓存前提不合、OOM/重启/正常停止失败、guest 可用内存或服务峰显示余量不足：保留原始日志/SHA及本人项目状态，停止后续 `r1–r3` 和其他 W3/W4 队列，按 DC68/产品 finding 规则分析，不无修改重试、不逐档加 M。首个 warm 成功也不是 1 warm+3 统计；随后 W3 FULL、W4 10% MO/FULL、100% 压力及正式样本只按已审固定队列推进。新的 `resource_verdict=PASS` 仍须与 `acceptance_complete`、业务成功和完整样本分别核，不以低 RSS 或未 OOM 代替预约证明。

尚未知：原 W3 first rejection 的精确调用位置和 live/request、S3 新档 v2 FULL Preview 实际峰、RS/backend 历史峰及新档运行峰、W3/W4 结果、时间目标和最终 S3 exit 资格。新档实际失败则据本档原件决定最小职责内修复或交 Owner；本稿不动 Submit 算法、golden、HTTP DTO、生产默认或 S4 范围。
