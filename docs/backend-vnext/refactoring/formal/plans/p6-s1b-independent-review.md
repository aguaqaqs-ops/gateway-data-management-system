# Phase 6 S1b 独立审核（首次）

- 结论：**定向修订**。
- 日期：2026-10-28。
- 代码候选 H：`705b17c1a137ede6b4339376527b30a4c58288f7`；handoff：`2599799b53c2950c48e4564af65460e3ae7b34e0`；实施分支 `p6-s1b-impl`。
- 审核区间：`p6-s1a-exit..705b17c1a137`；其中 `p6-s1a-exit..ae3301d6d8` 是 kickoff 设计/授权修订，实施区间为 `ae3301d6d8..705b17c1a137`。handoff 提交仅增加文档。
- 依据：P6 设计 §5.1–§5.8、执行计划 §2 S1b/§8、DC56/DC61/DC62、owning Contracts、比例化保障政策和 S1b handoff。

## 1. 结论摘要

主体实施和已报告门禁成立，但三个已复现的代码缺陷阻塞 S1b exit：上传取消时暂存文件生命周期错误、只增列时漏报共有排除列的内容变化、ENUM 标签替换被误判为只增列。需定向修订并复审，不建议打 exit tag 或进入下一实施阶段。另有 N1 验收证据缺口，需补证或由 owner 明确接受延期；本报告不自行扩大性能门槛或要求产品计时插桩。

## 2. Findings

### S1b-F1 [P1]：直接取消上传任务会在线程结束前删除输入文件

- 类型：已证实缺陷；阻塞：是。
- 位置（H）：`vnext/backend/src/gateway_backend/http/orchestration/multipart_upload.py:55–72`。
- 依据：设计 §5.4 要求线程池中操作的完成/取消边界与断连释放得到保留。
- 触发：`_accept_staged_upload` 在线程内运行时，对外层 asyncio task 调用 `cancel()`（例如服务器关闭时取消请求任务）。`anyio.to_thread.run_sync(abandon_on_cancel=False)` 不足以屏蔽这种直接 asyncio cancellation；外层立即进入 `finally`，删除 `parsed.staging_dir`，线程仍继续使用其中的输入。
- 本次复现：用 Event 暂停线程中的受理函数，取消外层 task；得到 `CANCEL_RETURNED_THREAD_DONE False STAGING_EXISTS False`，释放线程后得到 `UPLOAD_THREAD_FILE_EXISTS False`。这证明生命周期竞争；未声称复现了真实 DB 的部分提交。
- 影响：正在进行的解压/校验或后续 artifact 读取可能失去输入；请求清理与仍在执行的受理事务脱离，违反该阶段明确要求的完成边界。
- 最小修正方向：使暂存清理归属于实际同步工作结束，或明确等待受理任务完成后再传播取消，覆盖原生 asyncio cancellation；保持正常失败路径的释放，不引入新的 durable 状态机。
- 关闭标准：以事件同步的测试证明取消返回/清理和线程完成顺序；线程执行期间输入仍可访问，完成或异常后暂存最终释放，并验证受理结果的既有事务语义。不能仅测 AnyIO CancelScope。

### S1b-F2 [P2]：只增列时对排除列单独做 multiset 比较，丢失行关联

- 类型：已证实缺陷；阻塞：是。
- 位置（H）：`vnext/backend/src/gateway_backend/capabilities/comparison/standard.py:681–690`；`ordered.py:692–709` 有同样的投影方式，应一并核对。
- 依据：设计 §5.1 只忽略新增列，共有列仍按既有语义判定变化；已有测试 `test_added_column_keeps_shared_excluded_value_changes_summary_only` 明确要求排除列内容变化保留 `content_changed`。
- 触发：表 `t(id PRIMARY KEY, aux VARCHAR(8))`，规则 `compare_excluded_columns=('aux',)`；行从 `(1,'a'),(2,'b')` 变为 `(1,'b'),(2,'a')`，同时增加 `note TEXT` 列。
- 实际：`UNCHANGED / content_changed=False / COLUMNS_ADDED`。同一行变化但不增加 note 时是 `UNCHANGED / content_changed=True / NONE`。两个表的 aux multiset 都是 `{a,b}`，新分支因此丢失 aux 与 id 的关联。
- 影响：Surface 依赖 `content_changed` 将这类表显示为 UPDATED；本例被错误显示为未变化。这不是要求为排除列生成逐行风险或 records。
- 最小修正方向：在忽略新增列的同时保留共有行内容的关联（例如比较共有完整行投影或按有效键关联排除值），同时保持物理行顺序无关。
- 关闭标准：上述交换值案例保留 summary-only 内容变化；只有新增列、仅物理行重排仍不报变化。核对 keyed、keyless 与 ordered 共用语义，避免复制内部步骤测试。

### S1b-F3 [P2]：ENUM/SET 的标签被大写化后进入兼容判断

- 类型：已证实缺陷；阻塞：是。
- 位置（H）：`vnext/backend/src/gateway_backend/capabilities/comparison/row_encoding.py:414–423`，其调用的 `_column_signature` 在第 411 行对整个 SQL spelling 调用 `upper()`。
- 依据：设计 §5.1 只允许 ENUM/SET 标签集合的严格增加；当前解析器 `_enum_value` 对标签执行精确成员判断，标签字符串不是大小写无关的类型关键字。
- 触发：`e ENUM('a','b')` 改为 `e ENUM('A','b')`，同时新增 `note TEXT`；数据均使用仍存在的 `'b'`，避免行变化干扰。
- 实际：`UNCHANGED / COLUMNS_ADDED / incompatible_columns=()`，无 schema-change record。旧标签 `a` 已删除并被 `A` 替换，理应走 incompatible 路径，不能因 note 新增而抑制 schema 风险。
- 原因：新兼容函数先使用旧的整串大写 signature 短路为 True，绕过后续精确标签比较。旧 helper 本身早已存在，本 finding 针对 S1b 新增的 COLUMNS_ADDED 豁免路径。
- 最小修正方向：对 ENUM/SET 先解析类型及原始标签，按标签精确比较；仅规范化类型关键字，不改写字符串字面量。
- 关闭标准：上述标签替换加新增列分类为 INCOMPATIBLE，保留 schema 风险；ENUM/SET 的真正只增成员（包括中间插入）仍分类为 COLUMNS_ADDED。对两种类型使用共享参数表。

### N1：验收证据尚有两个未闭合项

- 类型：验收证据缺口；不另判产品缺陷，exit 前须补证或 owner 明确处置。
- DC62 第 4 项与设计 §5.2 要求 t4 checkpoint 读取、bundle 子段与 S1a 对照。handoff 诚实说明只有 aggregate，不能从中隔离两段，但将其延期不等于已经满足要求。“不设性能门槛”和“不在产品中插桩”也不自动取消对照要求。
- DC62 第 5 项要求真实旅程核对重复导出命中缓存。handoff 引用了缓存单元测试和 repeat Preview 的 0 changed rows；后者只能证明比较结果，不直接证明缓存命中。当前报告没有给出真实旅程中缓存命中的直接证据。
- 处置方向：利用已有非产品诊断/保留制品补充可核对证据，或由 owner 明确接受测量限制并指定 S2b 的后续任务。不要求重跑全量旅程来替代定向取证，也不新增产品观测机制。

## 3. 验收核对

| 项目 | 核对结果 |
| --- | --- |
| 只增列、共有列比较及风险 | 常规场景与 t3 证据通过；F2、F3 阻塞边界语义冻结。 |
| Preview/History 全表 bundle、绑定与内容共享 | 核对 pair pipeline、surface closure、History 全量物化及 bundle 去重；相关 focused 通过。没有发现新增绑定遗漏。 |
| 导出缓存 | repository + row-layout + writer version、TTL/protection、损坏回退的代码及 focused 通过；真实旅程命中证明见 N1。 |
| 上传 idle/total 与 HTTP 408 | 常量、错误映射和现有 focused 通过；受理线程的取消生命周期见 F1。 |
| SQL parser 与 FLOAT | 核对 BIT、binary introducer、转义、类型注释、JSON 深度/代理/非有限值及 binary32 单次舍入改动；parser focused 通过。未独立重做 Rust 差分。 |
| DC56 显式键/BROWSE_ONLY | 规则采用精确名单；strict key 失败语义和 v4 golden 已更新。真实数据逐表审计采用 handoff 引用证据。 |
| worker 唤醒与快照清理 | runtime 在 executor finally 和停止信号唤醒，等待仍受 heartbeat/drain 截止约束；scheduler focused 通过；04 postcheck lock snapshot 为 0。 |
| 六包门禁/carried | 04 原始 V/H runner 和 compare 日志支持 handoff：四包无变化沿用；backend/RS 在 H 实际重跑，exit 0。 |
| t1–t4 完整旅程 | 原始日志起止 H、exit 0 与 handoff 相符；本次不重跑全旅程。step 间隔最大 0.039/0.207/0.416/0.696 秒。 |
| 合成负载、性能对照 | 生成器/runbook 与 handoff 的 2×t4、W4 记录已审阅；未独立重跑生成器。子段计时缺口见 N1，不设新的性能门槛。 |

## 4. 实际执行的检查

本地审核 worktree：`/home/dev/gdds-p6-logs/s1b/review-initial-wt`，detached 于 handoff 提交；只读源码与文档。05 新建同路径 detached worktree 于 H，链接该节点本地 legacy；测试前确认 SSH、空闲进程/容器及 LAN 缓存 HTTP 200。没有在开发主机运行测试。

| 检查 | 结果与来源 |
| --- | --- |
| Git 状态/范围/差异 | H 至 handoff 只有 handoff 文档；本地和 05 审核 worktree 均 clean。主 checkout 原有 AGENTS.md、testing-conventions.md 修改未触碰。 |
| 三项最小复现 | 05 `gw-dms-test-05`，14:13:46–14:13:47 UTC，H；日志 `/home/dev/gdds-p6-logs/s1b/review-initial-repros.log` 保存在开发节点；远程 Python 正常结束。使用已有 H 环境及审核 worktree 源码，禁写 bytecode，输出无真实数据。 |
| 相关 focused | 05 14:15:03–14:15:05 UTC，起止 H，**145 passed**，`FOCUSED_EXIT=0`；`review-initial-focused.log` 在 05 与开发节点均有副本。 |
| 五包静态检查 | 05 14:18:47–14:19:11 UTC，H 审核 worktree，依次执行五包已有 H 环境的 `python -m ruff check . --no-cache` 与 `python -m mypy --cache-dir <外部目录>`，全部通过，命令 exit 0，worktree 仍 clean。 |
| 门禁取证 | 04 `04-runner-80ce756619.log`、`04-runner-H2-backend-rs-705b17.log`、`04-carried-manifest-compare-H2-705b17.log`、`04-H2-runner-postcheck.log`；逐项抽查 HEAD、时间、包结果和 compare。 |
| 真实数据取证 | 05 三份 `05-t[1-3]-final-H2-705b17c1a1.log` 和 `05-step-gaps-verify-final-H2-705b17.log`；ct108 `ct108-t4-journey-H2-705b17c1a1.log`、`ct108-step-gaps-final-H2-705b17.log`。 |

Focused 命令用已同步 H 的 backend `.venv/bin/python -m pytest`，显式 `PYTHONPATH=<审核 worktree>/vnext/backend/src`，选择 `test_comparison_standard.py`、`test_comparison_ordered.py`、`test_snapshot_export_cache.py`、`test_upload_streaming.py`、`test_operation_worker_scheduler.py`、`test_bundle_assembly.py`、`test_table_access_sql_parser.py`，`-n 0`；TMPDIR 为 `/home/dev/gdds-test-tmp`，pytest/Hypothesis 缓存移到 worktree 外。此 focused 是独立审核验证，不冒充权威 runner 来源。

## 5. 镜像记录、限制与下一步

- 当前审核代码 HEAD 为 H；此次仅出审核报告，没有生产代码、依赖、deployment 或 container harness 改动，不触发新镜像构建。未重新 tag 镜像或重跑 Compose。
- 最后验证的 RS build-input revision 为 `4158ea39d48157081c24d03a294c5a7eb3f866a0`，source-tree 为 `sha256:1d23f369fef72e559fa35e09240d09e15e9eeb4d9fe8e5bc0a035b879bae8e00`，与 H postcheck 一致。postcheck 本机 image ID 为 `sha256:bc65d874981c3f88f8095da8dcda722a545ffcc024954a0f63ad5ed780f2b19d`；不以重复构建后的 image ID 差异否定 source-tree 身份。backend/RS 容器证据取自 H runner，其余四包直接沿用 V。
- 本次 focused 全绿不关闭 F1–F3；这些反例不在现有测试覆盖内。未宣称完整审核了所有未来输入组合，亦未新增同 euid 恶意攻击模型。
- 修订后先在 05 定向验证反例；最终候选的包闭包与容器边界依既有规则重新判定。N1 由 owner 处置后，交同一审核会话复审。
- 本次新增的本地/05 `review-initial-wt`、05 `/home/dev/gdds-test-tmp/s1b-review-pytest-cache`、`s1b-review-mypy` 与可能生成的 `s1b-review-hypothesis`、两份审核日志留给 owner 后续清理；未删除原有证据、卷、缓存或 worktree，未推送或打 tag。
