# Phase 6 S1b 第 2 次独立复审

- 结论：**代码与技术验收通过；阶段 exit 仍待 owner 处置 N1-1**。
- 日期：2026-10-29。
- 代码候选 H：`020deda2fd59839c9ae6e31660f6fd23d14304d2`；handoff：`1b3449c00a6f94c3784377f5556a1d9a7ec7c6d0`。
- 复审区间：`afbfaea8e2154326e25c29091f34ffb3c12cd8ab..020deda2fd59839c9ae6e31660f6fd23d14304d2`；后续 handoff 提交只更新文档。
- 依据：[第 1 次复审](p6-s1b-independent-rereview-1.md)、[handoff](p6-s1b-handoff.md)、P6 设计 §5.2/§16.2、Comparison Bundle Contract、DC62。

## 1. 结论摘要

F5 已修正：History 将比较读取需求和每个节点的完整导出需求分开传递，未变化普通表与 ordered 表均进入最终 bundle，内容共享保留各节点/侧绑定。缓存命中免读仍成立，因此 F4 一并关闭；F1–F3 保持此前关闭结论。本次没有新增阻塞代码 finding。

N1-2 保持关闭。N1-1 的 checkpoint-read/bundle 子段对照仍缺少可独立计算的时间戳，owner 尚未处置；本报告不将代码审核通过视为批准延期或授权阶段退出。owner 明确接受测量限制并记录后续处置，或补齐该项证据后，再按阶段流程办理 exit。

## 2. F5 与 F4 关闭核对

| 关闭标准 | 核对结果 |
| --- | --- |
| 比较需求与完整导出需求分开 | `compare_jobs.py` 保留 `_history_requested_tables`，另外按各 commit 的完整 canonical binding 构造 `export_tables`；两者分别传给 materialization request。 |
| 未变化表不再从 bundle 消失 | `repository_ref.py` 对 `selected_set ∪ export_set` 执行缓存查询/必要读取并生成 table set；`_with_readers_policy` 用 dataclasses.replace 保留新字段。History 全部节点均沿该路径物化。 |
| 缓存 hit 免读，miss 回填 | 暖缓存路径仍先查精确 row-layout key，再复用已校验 Parquet；没有恢复为先读 Dolt 再查缓存。独立复跑冷/暖缓存测试：冷场景第一侧读取普通/ordered 两表并回填，第二侧命中不读；暖场景两侧均不建 reader，bundle 数据与冷场景一致。 |
| 最终 bundle 内容与双侧绑定 | 扩展后的双节点普通表测试直接断言 before/current 的 `t` 数据均为 `id=1`，共享一个 SNAPSHOT_TABLE；ordered 测试断言两侧完整 gid/no/value（含 pseudo gid 行）及共享文件。原 F5 反例已被最终输出断言覆盖。 |
| 变化、新增、删除表 | 测试在最终 bundle 中分别断言 t 的前后值，以及 gone 只在 before、added 只在 current。 |
| 三节点共享不丢绑定 | 多 pair 测试直接断言同一 Parquet 的四个 pair/side/table 绑定及对应内容，且无重复绑定。 |
| 数据读取与完整性 | helper 通过 ArtifactStore.locate 校验 ref 后解析 Parquet，并比较规范标量值；不再只验证 operation 成功或 comparison digest。 |

本轮新增 `export_tables` 为内部 materialization 请求字段，无 durable schema、HTTP DTO、兼容层或旧路径。源码改动限于 History 请求接线、请求字段校验和读取/导出并集；没有修改 F1–F3 实现、golden 或既定业务分类。

## 3. 最终真实数据与性能证据

已读取 t1–t4 最终旅程原始日志，起止 HEAD 均为 H、exit 0：05 的 t1 21:52:40–21:56:36、t2 22:01:08–22:29:52、t3 22:30:26–23:27:34（2026-10-28 UTC）；ct108 t4 为 2026-10-28 23:28:35 至 2026-10-29 00:40:20 UTC。本次没有重跑完整旅程。

- t1–t3 bundle audit 日志中的各侧覆盖检查均为 PASS，missing/extra 为空，唯一 Parquet 均可读且行数匹配。该审计扫描了多份 closure 文档；本报告保留其扫描口径，不将文档数解释为独立成功 History operation 数。
- t4 的 `robust_script_retry` 明确绑定成功 History operation：1 个 operation、2 个输入节点、1 个 pair，before/current **各 312 张表**，missing/extra/duplicate **均为 0**；ordered 各 144 张，普通表共 336 个双侧绑定。**166** 个唯一 Parquet 全部通过 checksum、可读性、Surface ref 和行数校验；624 个绑定保留 **458** 次共享复用。286 张 UNCHANGED 和 26 张 UPDATED 表均有双侧绑定。
- t4 审计日志保留了此前诊断脚本的语法/路径等失败。采用最终 `robust_script_retry_exit=0` 段作为证据，未将前面的失败段改写为通过。
- 修正后 t4 History API **361.051s**，`materialize_inputs` **216.440s**，assemble **142.544s**；原始 step 日志支持后两项。此前漏表候选的 162.472s/78.822s 已在 handoff 明确作废。当前 API 比旧 H=705 少 383.084s，比 S1a 多 48.162s；该阶段没有新性能门槛。
- N1-1 仍无法从上述 aggregate 分离 checkpoint-read 与 bundle 子段，不推算或伪造该两段值。N1-2 原有真实缓存复用证据继续保留，本次不重复打开真实 control DB。

日志位于各节点 `/home/dev/gdds-p6-logs/s1b/`：`05-t[1-3]-f5-020deda2.log`、`05-f5-t1-history-bundle-audit-final.log`、`05-f5-t2-history-bundle-audit.log`、`05-f5-t3-history-bundle-audit.log`、`ct108-t4-f5-020deda2.log`、`ct108-t4-history-bundle-audit-f5-020deda2.log`、`ct108-t4-step-audit-f5-020deda2.log`。

## 4. 本次独立执行与门禁核对

| 检查 | 节点、时间（2026-10-29 UTC）与结果 |
| --- | --- |
| 独立 focused | 05 `gw-dms-test-05`，01:25:06–01:25:16；History jobs + export cache，`-m unit -n 0`，**34 passed、1 warning，exit 0**。warning 为既有 Starlette/httpx 弃用提示。 |
| 五包静态检查 | 05，01:25:39–01:26:02；各包 Ruff/mypy 全通过，exit 0。 |
| 四包 carried 独立复算 | 04 `gw-dms-test-04`，01:25:53–01:25:58；在保留的原门禁 `04-wt`（H，clean）重算 rust/shared_kernel/repository_contracts/repository_client manifest，直接 compare 来源 V=`91401f014699cf99feba05675762cada2847e459` 的实际 runner manifests。四包均“可沿用”，changed_components 为空，总摘要与 handoff 一致，exit 0。 |
| backend/RS 当前门禁 | 只读核对 `04-runner-f5-020deda2.log`：2026-10-28 21:29:57–21:50:16，起止 H、clean、两包 passed、runner_exit=0；起始 manifest 与 handoff 摘要一致。 |

独立审核 worktree：开发节点 `/home/dev/gdds-p6-logs/s1b/review-r2-wt` detached 于 handoff，05 同路径 detached 于 H；均链接各节点本地 legacy。05 运行前确认无其他测试/Dolt server 或 active Docker 容器，04 carried 前确认原门禁 worktree clean 且无其他测试。没有在开发节点执行测试。

05 首次命令误用候选目录下不存在的 `.venv`，pytest 未启动即 exit 127；随后根据原 focused 日志确认使用该节点 `/home/dev/gateway-data-management-system/vnext/<package>/.venv` 的已备环境，以显式 `PYTHONPATH=<审核 worktree>/vnext/backend/src` 运行审核源码后通过。未因此下载依赖、改源码或改锁。LAN 服务按 handoff 已停止，本次全部使用本机预置环境，无需远程缓存获取。bytecode 禁写，TMPDIR 为 `/home/dev/gdds-test-tmp`，检查缓存在 worktree 外，运行结束审核 worktree 仍 clean。

新日志：05 `review-r2-focused.log`（首次未启动记录）、`review-r2-focused-retry.log`、`review-r2-static.log`；04 `review-r2-carried.log` 与 `review-r2-manifests/`。成功检查日志已复制到开发节点同路径。四包 carried 本次重算补充了当前 H 的直接证据，不以中间候选的 carried 结果充当实际来源。

## 5. 镜像、剩余前置与交付

当前审核代码 HEAD 为 H。本次只提交审核文档，无 image/deployment/container harness 改动，不触发新镜像构建或 Compose 重跑。H 的 backend/RS 容器证据取自本轮权威 runner。

04 当前 RS image inspect 核对 image ID `sha256:b66c7fef0b8dd6c6b6d66e0463862e109f1d44cd8614e96fe93564bd8a2a4dd9`、build-input revision `4158ea39d48157081c24d03a294c5a7eb3f866a0`、source-tree `sha256:1d23f369fef72e559fa35e09240d09e15e9eeb4d9fe8e5bc0a035b879bae8e00` 与 handoff 一致。未重新 tag 镜像。

F1–F5 均关闭，N1-2 关闭。**唯一剩余阶段前置是 owner 对 N1-1 的明确处置**；不需要因该测量限制继续改产品代码。若接受延期，应记录接受的限制及后续节点；否则补齐要求的证据。阶段 exit 提交仍依既有规则完成最终 carried 绑定。

新增清理项为开发节点/05 `review-r2-wt`、05 `/home/dev/gdds-test-tmp/s1b-r2-*` 缓存、04 `review-r2-manifests/` 及本次日志。全部保留供 owner 后续清理；未删除旧证据、卷、镜像、bundle 或 worktree，未推送、未打 tag。主 checkout 原有 AGENTS.md 与 testing-conventions.md 修改未触碰。
