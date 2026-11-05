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

## 5. B：INITIAL 小样本同步段诊断核对

2026-11-05 设计授权的 B probe 诊断事实与解释范围通过；**不改变不 GO 结论**。审核只读核对 05 原文件与 CT201 副本，未执行 probe 或追加矩阵。证据副本位于 `/home/dev/gdds-p6-logs/prepare-import-B-20261105/`；05 原日志目录为 `/home/dev/gdds-test-tmp/prepare-import-B-20261105/`，脚本为其外的 `prepare-import-B-probe.py`、`prepare-import-B-run.sh`。

实际代码取自 clean detached `/home/dev/gdds-prepare-import-e798-05`，起止 HEAD 均为 e798，五锁前后摘要相等。解释器复用 `/home/dev/gdds-p6-baseline-capacity-resume-413832-05/vnext/backend/.venv/bin/python`，probe 显式把 e798 的 backend/shared_kernel/contracts/client 源码置入 sys.path；日志确认 fixture/product 模块来自 e798，native build-input 为 `58436908aee9dd449f4d3e0542a6a8c1920b6d5e`，与 e798 Rust tree 匹配。这是有记录的诊断环境复用，不表述为最终候选完整环境门禁。

外置脚本使用现有 pure fixture、InMemoryArtifactStore 和 INITIAL parent，每档一张 12 列表、1k/10k 行；调用 publication adapter，没有启动 Dolt、Compose、数据库服务、网络调用或读取真实输入。wrapper 设置离线并清除代理；子进程监督器以 50ms 周期读取 RSS，设置合计 120s 与单子进程采样 RSS 2GiB 停止条件。两个子进程均 exit 0、stop_reason=null，总耗时 14.550407s，2026-11-05 20:19:49Z–20:20:03Z；postflight 20:20:26Z 记录占用释放。审核时该 worktree clean、节点占用标记不存在。

| 指标 | 1k | 10k |
| --- | --- | --- |
| publication wall / process CPU | 0.867190s / 0.873297s | 9.008104s / 9.033012s |
| plan_import_mutation wall | 0.541260s | 5.978178s |
| 累计最大 tick 间隙 | 36.347ms | 169.784ms |
| 子进程采样 RSS 峰值 | 178,663,424 bytes | 379,035,648 bytes |
| 返回/read-back/显式 cleanup 后累计 tick | 36.347ms | 169.784ms |

各过程 CPU 包含同进程其他线程；tick 最大值从启动起累计，不能当作各段独立 stall 时长，更不能直接归因 GIL。Parquet helper 的 wrapper 因生产代码已导入 alias，没有直接记录；`_open_projection_inputs` 耗时不能拆成单独 Arrow primitive。15s faulthandler 定时器未触发，两份 stacks 文件为空，不能当作有用户态栈定位。RSS 是 50ms 子进程采样，不含监督器、不是连续硬限额或完整生产服务内存曲线。

本结果仅说明这个 INITIAL 小样本没有重现几十秒心跳调度间隙。它不覆盖非 INITIAL parent 差分、真实 25.5GB 资源规模、持久制品存储、control DB/LeaseSession 心跳或 checkpoint 发布路径；不能排除这些条件下的 GIL/调度/锁问题，也不能把约 10 倍耗时变化外推为完整规模模型。下一步按设计从既有小元数据判断原运行是否完成 publication、是否进入 checkpoint 发布，再选择最小诊断，不增加无依据矩阵。

| 文件 | 本轮在 05 原文件与 CT201 副本均核对的 SHA256 |
| --- | --- |
| `run.log` | `ed223107006654795b574c7980b330f32a874ba85f8dac9f8e2578b69d2dbad9` |
| `probe.py`（05 为 `prepare-import-B-probe.py`） | `6234ad98e92d06d2c434f77169d03ecbf4a9b3f02ccb515ec321970e0750a58b` |
| `run.sh`（05 为 `prepare-import-B-run.sh`） | `3ef83dc537c7c87c9212468dc30724d83cd4e3920b5fdfba893345508c42a8f6` |
| `rows-1000.log` | `d6fee9c59f39cfc77e4422869cb4f8a63dcdde53b8349e328aaecf5ffd1b8c29` |
| `rows-10000.log` | `d7e7d7e4d0124336e792261495d5cf3bfa53d5b0b27c88a0d933888e5d64bc08` |
| `postflight.log` | `ee3c6ed854497244a736f201183f7399fcbd509f706738140e00c91f515e548e` |

本次追加只更新审核报告，不改产品、设计或既有证据，不构建镜像，不推送、不打 tag。

## 6. 后续小 DB 查询的证据限制

实施者随后报告：停止后只读查询得到 schema 43、DB 3,608,576 bytes/WAL 0/SHM 32,768 bytes、无 writer；operation/step checkpoint_ref 均 NULL、prior_output_refs 为空、attempt PREPARED、prepare 输出与 Repository 绑定相关字段 NULL，operation 仅保留四个原输入/Preview artifact 引用。**这些新增字段为实施者报告，本轮未独立核验。** 实施者明确查询通过内联 SSH heredoc 执行，未保存查询脚本、结果日志及摘要，也未记录 DB/WAL/SHM 前后身份；只有实施线程工具输出与读前 stat/NO_WRITER_CHECK，不能声称已经核验源文件前后不变。

该限制不影响第 2 节已经直接核验的自动 selected rows 和停止结论。若这些补充字段准确，也仅支持 control DB 未登记 prepare 输出/checkpoint；候选执行顺序为 publication 制品写入及 reader 关闭、checkpoint 制品生成、保护引用、lease checkpoint 发布，NULL 不能定位此前哪个步骤尚未完成，也不能排除 artifact store 中的孤儿文件。未扫描 store 或重查数据库，不为补日志要求重复取证，不补造历史记录。已把此限制通知设计及实施者；后续获准计数应从执行时保留原始命令、输出与摘要。当前不 GO 保持不变。

## 7. 已保存的有限输入 metadata 核对

三份脚本及日志已在 CT108 证据根的 `shape-metadata/` 中保存，本轮直接读取并重算 SHA，与交付一致；未重新执行脚本。v1 读取 input summary、expected manifest 及其引用的三个 census；v2 读取 expected manifest 引用的 dataset manifest；v3 限定目标 W4 10% census。脚本没有调用业务、数据库、Parquet/SQL 解析或扫描 artifact store，日志均 exit 0，分别记录 20:37:04Z、20:39:59Z、20:42:14Z 起止时间。

v3 日志绑定目标 census SHA `04952cb5523b9b6d44530654994bcad2a692a132697cacc2f157a7e8c66eea67` 与 expected manifest SHA `4c5638df32973282507937c1232c09117b40023f8b03f3d94caf7c160f87aac7`。八个 dataset 的已输出物化/复合阶段状态均 COMPLETE；t4 v1/v2 的总行数为 873,863/873,160，各 639 表。各自 `ordered_projection.tables` 仅覆盖 144 表，其中前三项均为 9,822 行；这不是全部 639 表的行数前三名。v1 将多个 census 混合排序所得 9,828 不能替代目标 v3 计数。dataset manifest 身份 MATCH，但无表级 stats；现有输出没有列数、类型分布或行宽，不能将缺失项视为零或足以决定完整规模 probe。

读取量存在可直接从脚本核算的非阻塞遗漏：v2 在有界读取后再次 `read_bytes()` 计算 dataset SHA，未累计 2,991 bytes；v3 同样再次读取 census，未累计 314,389 bytes。日志累计 2,368,567 bytes，应加上两次重复读取，实际 JSON 读取总量为 **2,685,947 bytes**，仍低于 16,777,216-byte 许可上限。已通知实施者与设计如实补注，不重跑或改写原日志；不将计数器描述为覆盖全部实际读取的硬上限。此处未核验新的 canonical artifact descriptor 或新增 DB 查询。

| 文件 | 脚本 SHA256 | 日志 SHA256 |
| --- | --- | --- |
| `read-submit-shape-metadata`（`.py` / `.log`） | `0c7819619e27c7a2998e74e0a158674f56ab41a1fe04b8f9e770971e638ff3f3` | `574ef32841050c2535d850c9e2d2f49b71267b842f34b516dea224fdab761636` |
| `read-dataset-manifest-shape-v2` | `e61c7db71accd1a14be8b620cb88930ab217258b85c2a934d279310c17e60b5c` | `ab59a2c608ce3be08b23ddf887ab01bc5a883746085788097d755190a0984420` |
| `read-w4-10pct-census-shape-v3` | `21129955ffd7459c2b386832349d7f03d0f9c9f101ae999b2e584a581653213b` | `82798ebd7e08a3dee3580cb57ab8934bb56fb9931fc73e05be7a67b676085156` |

诊断记录及上述限定解释可接受；它们不定位停滞根因、不证明 publication 进度，也不放行扩大实验或恢复。当前不 GO 不变。本轮仅追加本文，未运行测试、未改产品或证据、未推送。

## 8. Canonical / STA descriptor 聚合核对

新增诊断从本次 W4 Submit 的精确 operation ID 读取 canonical closure/manifest 完整 Ref，再按已核对的 local_store 确定性路径读取 JSON descriptor；不查真实行、Parquet 或 SQL，不扫描 artifact store。读取器使用 SQLite `mode=ro`、`query_only`，拒绝非空 WAL，检查 DB size/mtime 与 WAL 大小前后相等；artifact 读取验证 sidecar Ref、长度与 raw SHA，缓存已读 Ref，closure 与 canonical manifest 表集合相等且无重复。此次独立保存的脚本/日志不补造第 6 节未保存查询的历史证据。

本轮审核读取的是 CT201 `/home/dev/gdds-p6-logs/baseline/submit-shape-20261105b/` 中实际存在的脚本和源日志。源日志记录 `hostname=gw-dms-test`、20:54:32Z、精确 operation ID、RESULT=MATCH；实施者曾把文件路径称为 CT108 路径，审核在 CT108 按该路径取脚本时返回不存在；随后实施者明确脚本仅保存在 CT201，以 `cat "$SCRIPT" | ssh ct108-gw-dms 'python3 -I -'` 送入远端执行，SSH 输出由 CT201 的 `tee "$LOG"` 落盘，未向 CT108 复制脚本。本报告不宣称比对了 CT108 磁盘副本。原源日志为 0600，本轮仅程序读取必要字段和计算摘要，未输出或转发 ENUM/SET 定义值或完整 DDL。

源日志 SHA `d7e3c94e6119f5631594f5e13ef0fb070586fb083fff76251f9570a03798a41d`、读取脚本 SHA `3b4938184517d4395929cfbd1c8c15157a7a06df6a6233b90f92bb91f35c83bc` 均与 sanitized 文件绑定相等。程序将源类型值归并为类型族，汇总与 sanitized 完全一致，合计 7,538 列；其余聚合字段逐项相等。sanitized 文件 `canonical-sta-metadata-sanitized-v2.log` SHA 为 `005dbb31497c1408328e91e3808b63c5e6d2ff998f7efd97480048873160f396`。

| 聚合项 | 已核日志结果 |
| --- | --- |
| canonical / STA 表数 | 两者均 631 |
| descriptor 总行数 / 总列数 / nullable 列数 | 682,805 / 7,538 / 6,785 |
| 按行数前三的实际行×列配对 | 92,428×5；84,285×33；54,150×43 |
| 按列数前三的实际列×行配对 | 97×5；97×5；51×14,790 |

不能混拼不属于同一张表的最大行数与最大列数。descriptor 行数也不等于第 7 节 source census 的 873,863/873,160 行；两者处于不同物化/投影口径。此处证明已有元数据的规模与类型族聚合，不独立验证每行内容，不证明 prepare publication 完成，不把 W4 Submit 误写为 H2 失败。

首次读取器错误要求 closure 内嵌的 STA Ref 也出现在 operation 顶层 artifact_refs，在读取首个 STA 前以 `TABLE_MANIFEST_REF_NOT_BOUND` 停止。v2 删除这个额外要求，仍验证 operation 绑定的 closure/manifest、每个内嵌精确 Ref 的 sidecar/内容身份，并新增 canonical 名称重复拒绝；这是限定诊断读取器修正，没有改变产品验证。

预算记录另有不足：v2 用 65,536 bytes 作为首轮预留，但首轮已读取的 closure payload 自身为 149,748 bytes，故记录的累计 5,015,645 bytes 不能作为完整实际累计。无需再读制品即可给保守上界：v2 此轮完整计量为 `5,015,645−2,751,483=2,264,162` bytes；v1 在首个 STA 前停止且所用 Ref 与 v2 相同，读取集合为成功轮前缀，保守也按整个 v2 量计算。因此此前读取及两轮合计 **不超过 `2,685,947+2×2,264,162=7,214,271` bytes**，仍低于 16 MiB。保留原日志并补注即可，不要求追加取证；这不是新的根因诊断关卡。

shape 统计和预算上界支持继续选择有代表性的最小诊断，不授权 631 表重放、25GB 放大实验或恢复。当前不 GO 的原因仍为租约失效根因未定位，与上述累计记录笔误无关。仅追加审核报告，未运行测试、未改产品或证据、未推送。

## 9. 停止 handoff 与既存 status 字段

已核对 `p6-baseline@97702280c3bd5b8adda756fbf8546bb441ef23dd`：仅追加 handoff，记录 W4 Submit 不 GO、统计口径、7,214,271-byte 保守上界、CT201 脚本/日志经 SSH stdin 执行的来源、原始输出 0600 和 B2 仅为独立有界诊断，未宣布恢复。补充记录与本报告结论一致，不修改既有 H2 结果。

直接读取 CT108 已保存诊断文件的白名单字段，未读取现场 `/proc` 或重新运行 Docker inspect。`worker-pid-985828/thread-1183413/status.txt` SHA `84f93361fd8b7fb332f47757f285c8956006f36bc46119496d48f6c4c7523500`：VmRSS 23,996,624 kB、VmSwap 0 kB、Threads 53、CPU allowed list 与 handoff 一致。`docker-inspect-worker.json` SHA `afe3daa22567288a77720c7462bc2cb4e1fc330ca275ff06117b522ac91970e1`：Running=true、OOMKilled=false，Memory/MemorySwap/NanoCpus/CpuQuota/CpuPeriod 均为 0。实施者的路径修正日志 SHA `703c134da882f29f721764e0e3ebb5e7c88e217dbe793fd313c83ada749f5df4` 与所选原文件相符；首次顶层未命中的日志 `ca529637e622388d6936762b5938beab9208c6e316a0707aab89d671ddf81be8` 保留为路径误报。

这些值只描述停滞捕获时的该进程状态及未设置的 Docker 配额，不能证明宿主无压力、全程无 swap 或定位 GIL/调度根因。没有新增现场采集、测试或大规模诊断；当前不 GO 不变。
