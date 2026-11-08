# S3 E：W3 基线准备容量阻塞与 Owner 决策

2026-11-08；协调者记录。当前候选 `774acf33a3f12eeccfbb440d9446ffde9c1c6d43`。本报告不签 E GO，不豁免性能待项，不改变 S3/S4、生产 N/M 或部署边界。

## 1. 固定场景与实际结果

CT108 `gw-dms-test` 在 clean 774、Rust tree `9d4f84ce0897099402226c77c548c487c4912008` 上，按原审 CLEAR 的固定入口唯一运行 W3 `MODIFIED_ONLY warm`：外层开始14:03:17Z，node结束14:06:18Z、outer结束14:06:22Z，原 journey/node/outer 均 **exit1**，两次标准 capture 均0。命令为真实 Preview/Submit/Archive 基线准备及 v2 Preview 路径；没有替换比较算法或直接改 Repository。

空 initial 校验通过，v1 Preview 实际 SUCCEEDED（114.783秒），可见631表、changed631、degraded/failed均0；随后 v1 Submit 在14:05:57Z开始，操作 `op-b9453ef4993e76865434ad01` / `step-1` 最终 FAILED。**v1 Archive及受测 v2 Preview 未到，W3 READY/完成时间未知，不能用 v1 Preview 成绩代替。** 本次预热不是成功样本。

保持 N1、单 active、M=`25,769,803,776B`（24GiB），worker envelope=`34,359,738,368B`、reserve8GiB。worker cgroup peak=`1,212,547,072B`、进程 VmHWM=`871,400KiB`，`memory.events` high/max/oom/oom_kill均0。低RSS和无OOM不证明可以安全放宽预约上界。

## 2. 原件与独立核收

原控制根 `/home/dev/gdds-test-tmp/p6-s3-e-tool-final-774acf33a3-control/s3-e-perf-w3-mo-warm-774acf33a3/`：

| 原件 | SHA256 |
| --- | --- |
| `outer.log` | `6b181dc27a4ad1a87986419e9220ac8b1ec96759ab365417cff563218868b362` |
| `entry-captured/node.log` | `37961cb0f372fd298809aa21ab0c928aae39ebca6b186d8c1d581e259896e4ca` |
| `artifacts-captured/journey.log` | `0432bec8069afeb66226509e1f54134c9ce67c91df48a0521070efa9346ccf45` |
| `artifacts-captured/result.json` | `eef0f203c2c33241e2ba90ba209006383d4ae6446b713a9a98a1f6f5fdde415e` |
| worker `733d2c44cd9f-resources.json` | `936a04cc6f8d76c21bcb636e8d0dace84ff1c7195d53acb573b7fcda5bc0f020` |

后续只读诊断位于同 control 根的 `readonly-w3-diagnostic.log`，SHA=`850f3e1e89839bb879c126049e77574a8362d6eb4490d58217740a3f13f5e4f4`。唯一测试者先核本人project/volume标签、本人marker、容器已停止，使用 SQLite URI `mode=ro`、`PRAGMA query_only=1`，只取该operation/step的status和diagnostic，不启动服务、不改DB/卷/marker。两记录均给出 `RESOURCE_LIMIT_EXCEEDED` / `operation memory reservation exceeded`。

原E审核者在 `p6-s3-e-review.md` §55及后续连续只读核：捕获manifest全部SHA相符；终端文案与 `capabilities/table_access/kernel.py` 的 `OperationMemoryBudget.ensure` 拒绝逐字一致，`application/submit_jobs.py::_with_resource_failure_terminal` 透传。该证据只定位为操作账本 reserve 拒绝，**未观测首次拒绝的stage、need/live数值或具体表**。result的 `resource_verdict=PASS` 只表示资源事实采集完整，`acceptance_complete=false` 与业务失败不被覆盖。

## 3. 已排除、机制推断与影响

原先的 census字段/计数、日志采集退出问题已经修复；第三轮06 focused在774实测native/checker/Ruff/mypy均0、非serial74和serial3通过，原两失败不改。本次确已进入业务，不能按 DC68 命令错误重试，也不能作为原故障的第4次换候选试跑。

已确认 Submit 每个claimed step使用独立操作账本，Preview去重结果不会跨到Submit；Preview另一个operation的25,753,026,560B预约高水不能当作失败Submit的数值。现役 `infrastructure/repository_write/import_publication.py` 外层同时预约约2.469GiB replay上界；changed表按 `logical_size_bytes×32 + rows×(columns×1024 + 2048 + name_bytes×64) + 64KiB` 为Python scalar/行镜像/索引/变化集预约，累积到operation结束。它能够解释账本压力，尚不是已证首次抛点。

实施者从accepted源DDL/行数得到的非composite行头部粗估为20.338GiB，未扣canonical dropped列，也缺实际Arrow logical size，故仅作机制线索，不作安全放宽系数或选择新M的依据。可见631表共683,508行，含composite435行；非composite630表683,073行。

三workload的v1源包均为10,652,436B、SHA=`74974e5f3237ba372e81df95d448602d09713c3cdc8edf6ae5237352a78ebd4c`。因此W4 10%与100%及FULL运行共享当前受阻的基线前置；后续23样本全部**未运行/受阻**，不是已测失败，也没有median/range。D的六个两表诊断原件仍只证明部分起测，不能冒充最终完整负载。

## 4. 边界与可选路径

Owner本轮明确禁止擅改生产N/M、部署旋钮或扩入S4。S3 kickoff §3编排行明确“不实现S4”；`p6-design.md` §10、`p6-execution-plan.md` S4把直接从冻结IPC/mmap渲染SQL、消除逐行变化集、共用存储diff及 `replay.sql` 逐字节回归归入S4。故本轮不按RSS降低估算、不提前迁Submit算法、不缩输入或跳过正常验证/发布。

可由Owner选择：

1. **保持现有阶段边界。** 完成与此无关的04门禁、DC64真实范围及候选交接；S3 E仍为性能受阻、不签GO。将此容量问题交独立S4设计，解决后在N1/32-8/M24回补完整W3/W4。此项不将待补认作通过，也不自动豁免S3退出要求。
2. **另行授权测量基线准备的资源例外。** 仍经现有Submit/read/approve/Archive建立基线，仅对未计时准备采用Owner明确批准的临时envelope/M；准备结束后正常停止该worker，恢复新N1/32-8/M24 worker再开始v2测量，单独记录两段条件和生命周期。不得把较大准备预算写成M24容量成功；须先固定具体参数、脚本和资源guard并独审，当前没有这份例外授权或已执行稿，也不能保证不会遇其它容量上限。
3. **另行启动提前的S4相关工作。** 按S4 owning范围设计和独审，保SQL/replay逐字节及批量规则，完成其受影响验证后回到S3最终取证；不能把它作为普通S3 finding静默合入。

协调者建议先保持当前范围及失败事实，完成独立工作，**不盲抬M或自动提前S4**；若Owner要求本轮继续完整测量，优先明确是否允许第2项的测试准备例外，再由原角色把具体稿做成可复核结果。无论选择哪项，当前失败均保留，正式退出/tag/push另办。

## 5. 独立工作与资源状态

774完整fresh t1已在06实际通过独审；3a7 fresh t2–t4的业务/资源原件保留，按DC64与新t1/04结果最终核收，来源不改写成774实测。04受影响backend/RS权威runner已启动并继续原链，其余四包的同WT实际闭包前置已通过；最终exit/镜像出口仍待原件。最终H与E GO未完成。

CT108失败driver已正常停止容器并封存日志/镜像与完整资源事实，按DC80保留本人project资源和marker供诊断。尚未清理或重试；后续只在原审核者核收必要诊断后按固定自有资源收尾稿释放，不清他人标记/卷/镜像/输入，不长期占节点等待Owner回答。
