# DC80 恢复后 v2-submit 停止复核

结论：**停止有效；当前不 GO，不放行重试。** 恢复运行已通过 `v2-preview`，随后在 `prepare_import` 失去租约续期预算，触发 `worker_stalled` 并 exit 1。已有证据不能确定具体阻塞调用；不得仅增大监控阈值或租约时间后继续。此前[恢复 GO](p6-ready-capacity-resume-final-review.md)只授权已经执行的那次恢复，不适用于失败后的新运行。本报告不接管基准 exit。

## 1. 对象与只读范围

2026-11-05 设计会话委托原独立审核会话接续有限停止复核。对象为 CT108 project `p6bw4s4h120261105b`，候选 `e798ec87a37330250b0c051162e7962dba1daa60`。原始证据根目录为 `/home/dev/gdds-p6-logs/baseline/scenarios/p6bw4s4h120261105b/`，自动停滞诊断子目录为 `s4-stall-20261105T200059999874Z/`。

审核经 BatchMode SSH 只读原始日志、run/state、checkpoint 元数据、已保存线程栈和容器状态，重算下列文件 SHA；在原 clean detached 候选 worktree 静态检查对应 heartbeat/lease/prepare handler。未运行测试、产品或测量，未重扫数据卷，未改阈值、产品、工具、源证据或设计。根因线索与不 GO 结论已直接回告实施者及设计。

## 2. 停止事实与证据解释

| 时间（UTC，2026-11-05） | 原始记录 |
| --- | --- |
| 18:14:34.996 | sampler/journey 启动，起止 HEAD 均为 e798 |
| 19:34:20.691 | `v2-preview` step PASS，wall 4,745.449s；Preview summary 631 表、628 changed、0 degraded/failed |
| 19:34:28.753 | 保存 `v2-submit` 前三卷 checkpoint，`completed_through=v2-preview` |
| 19:34:31.165 | Submit operation 开始，operation timeout 为 4,055s |
| 19:58:58.503 | 最后一次 `heartbeat_succeeded` |
| 19:59:31.031 | `lease_lost`，`error_category=heartbeat_busy_deadline` |
| 20:01:00.745 | `worker_stalled`，observed 121.497s，阈值 120s |
| 20:01:01.051 | `v2-submit` step_failed，wall 1,592.297s |
| 20:04:06.935 | sampler/journey exit 1；输入 provenance MATCH |

本次并未达到 4,055s operation timeout，也没有 R5 转人工恢复事件。成功 Preview 可作为该步的原始成功记录保存；失败 Submit 耗时不能作为成功场景样本。

自动诊断及最终 Compose 日志一致：operation `op-0dea430454c163cf782acd0f` 的 worker 事件为 143 次 `heartbeat_succeeded`、1 次 `claim_succeeded`、1 次 `lease_lost`，**0 次 `heartbeat_busy`**。选取的 control DB 行显示 operation/step 仍 RUNNING，step 名为 `prepare_import`、attempt 1，最后更新时间 19:58:58.382377、lease 到期时间 19:59:28.382377；submit attempt 的 `repository_operation_id` 为 null。没有仅靠日志流停更推断产品失去心跳：持久租约时间与显式 `lease_lost` 相互支持。

候选 `operations/worker_runtime.py` 的 `_heartbeat_until_due` 在调用 `session.heartbeat()` 前发现 `now >= lease_deadline` 时，同样发 `heartbeat_busy_deadline`；实际捕获 `StoreBusy` 则会另外发 `heartbeat_busy`。因此本次类别证明续期预算耗尽，**不证明 SQLite BUSY**。无重试事件使调度迟延或长时间占用 GIL 等成为待查方向，但不能据此定论。

抓取时 worker running、OOMKilled=false、RestartCount=0，backend/RS healthy。53 个已保存线程中 52 个 `futex_do_wait`、1 个 runnable；这只是内核等待状态，不能定位 Python/C 业务调用或断言死锁。`py-spy-unavailable.txt` 明确未安装 py-spy，没有 Python 用户态栈。诊断另保留 `control DB snapshot: JourneyFailure`；已得到的 selected rows 有效，但不能将诊断宣称为无缺失的完整 DB snapshot。

静态 handler 将构建/发布 prepare package 放在 executor 路径，worker runtime 在另一线程维持续租；失去预算后的异常路径等待 executor `thread.join()`。这与“租约失效后进程仍在、操作仍非终态”的现场相容，尚不足定位造成首次迟延的具体函数。sampler 的 Submit 并发内存采样峰值为 25,485,312,000 bytes，整次保守峰值为 27,151,761,408 bytes；作为定位资源开销的线索，不据此归因 OOM。

## 3. 收束与最小后续条件

失败后同 manifest 的 `compare-state` exit 0、MATCH、issues 为空；绑定的 state SHA 与现文件相等。run/state 均保留结束时间、exit 1 和 `failure_step=v2-submit`。checkpoint 元数据记录三个快照及各自摘要，完成点为 `v2-preview`；本轮未重新哈希快照内容，不宣称新来源快照已获得恢复放行。

20:10:01Z postflight 记录项目无 container/network、无 Dolt/pytest/Cargo、8000 空闲、launcher 已退出、worktree clean，三个原卷保留；随后释放自有节点占用。审核读取时 CT108 无运行容器，标记不存在。未继续启动剩余场景。

后续最小路径：

1. 继续从已有源码、有限元数据和失败制品定位 `prepare_import` 内导致续租预算耗尽的调用。区分调度/GIL、锁等待和实际存储争用；若现有证据不足，先提出有界诊断范围和需捕获的信号，由设计安排实施，不能用完整正式重跑代替定位。
2. 根因明确后实施对应最小修正并取得定向验证，保持 lease/CAS、输出内容与输入绑定语义。实际产品或工具变化按原范围重新审核，不以提高 120s 停止阈值消除已有 lease_lost。
3. 优先评估保留的 `v2-submit` 前 checkpoint，避免无依据重跑成功 Preview。最终必须固定新候选、新 project/evidence、源快照关系及运行时复制摘要校验。既有 `--capacity-fix-resume` 精确钉住旧来源 `p6bw4s4h120261105a` 和 `v2-preview`；不能仅换参数把它用于此次新来源。新转换及分段 provenance 要明确绑定原 13 步、e798 Preview 和修正后 Submit。
4. 新恢复候选的受影响验证、镜像及闭包身份满足既有规则后，再独立核对恢复条件。当前不授权重试，不要求重复已通过且未受影响的场景。

## 4. 直接核对的 SHA256

相对路径基于上述证据根；`D/` 代表自动停滞诊断子目录。

| 文件 | SHA256 |
| --- | --- |
| `launch.log` | `6b5a40958b973d5c699b0efe22b4a5b4b4c66eae00db51bd5fba7072f99d486b` |
| `resources.json` | `b3ab0beb128fb038261137100388678250d57ba74c58bfa0780da5e2acc704e4` |
| `compare-state.log` | `a0f1311e4f20ce1f8be87e6d7c05bc0f912527cfcddbc20d16c022ffff5f3931` |
| `evidence/run.json` | `b1c0c939f090b3e95981791f8de44aeafa1ce5ff35d0dac603df3b6ffbd08317` |
| `evidence/state.json` | `f86e5bf4fda11ee37b17a4b08319955fe9df7c7a14b7c398c5480ded79bdf9e0` |
| `D/all-container-logs.txt` | `e0ec1c07cd659c02f84b540ef84e9ebe873930b5e21668d1338875cc493ab9a4` |
| `D/control-db-selected-rows.json` | `1b61c7cd5239780765e7aa0764c47d828080413bf33d1030d3dddaa7e69d14f7` |
| `D/stall.json` | `fc8b4dee709eb3f5b2ac8bc17541735ce0719cb4c1417b40ace2f066e58dfd62` |
| `postflight-after-v2-submit-failure.log` | `a988f26df02ff715623165b1c3856c3d2b7f6adb75a9258cc37a735d0f711bc7` |
| `node-lock-release.log` | `2af305965535153c01ce77cacf12e0c536627c3632928b438d41d34226fe3f09` |

本轮报告基于 main `e89dc0db35bd5d921096e2380c33adb59b19a399`，只新增本文，不触发镜像重建，不改变上次已审 H 镜像身份及 04 结果；也不增加任何容器门禁或恢复成功声明。未推送、未打 tag。
