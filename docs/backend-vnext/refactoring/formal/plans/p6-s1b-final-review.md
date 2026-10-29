# Phase 6 S1b 终审

- 结论：**具备 exit 条件**。代码、权威 runner、容器门禁和真实数据验收均已满足执行计划 §2 S1b；没有未关闭的阻塞 finding。办理 exit 前，owner 需书面完成两项处置：N1-1 与 DC33 真实数据范围确认（§4）。进入下一阶段“重建对照基准”需 owner 另行授权。
- 日期：2026-10-29。
- 对象：代码候选 H=`020deda2fd59839c9ae6e31660f6fd23d14304d2`，handoff `1b3449c00a6f94c3784377f5556a1d9a7ec7c6d0`，分支 `p6-s1b-impl`。审核区间 `p6-s1a-exit..020deda2fd`，其中 `p6-s1a-exit..ae3301d6d8` 是 kickoff 设计与授权文档。
- 依据：执行计划 §2 S1b/§8、DC56/DC61/DC62、P6 设计 §5/§6，以及四份审核报告（§1）。

## 1. 审核链与 finding 状态

| 报告 | 提交 | 结论 | 处理结果 |
| --- | --- | --- | --- |
| [首次审核](p6-s1b-independent-review.md) | `06fec22cd0` | 定向修订：F1–F3、N1 | F1–F3 在复审 1 关闭 |
| [第二审核人](p6-s1b-independent-review-b.md) | `79cde99c6a` | 定向修订：新增 F4，O1/O2 不阻塞 | F4 在复审 2 关闭；O1/O2 见 §4.3 |
| [复审 1](p6-s1b-independent-rereview-1.md) | `4d8fc3567b` | 定向修订：新增 F5，N1-2 关闭 | F5 在复审 2 关闭 |
| [复审 2](p6-s1b-independent-rereview-2.md) | `4ef84bb03a` | 代码与技术验收通过，N1-1 待 owner 处置 | — |

F1–F5 全部关闭，N1-2 关闭。剩余只有 N1-1，属于 owner 处置项，不涉及产品缺陷。

## 2. 验收逐项核对（执行计划 §2 S1b）

| 验收项 | 最终候选上的证据 | 结论 |
| --- | --- | --- |
| 只增列的表不降级、无风险；Submit 仍生成版本 | t3 v2 共 193 张表，33 张 COLUMNS_ADDED，无 SCHEMA_CHANGE 风险，无 degraded/failed 表；四档 Submit 均有 repository commit。F2/F3 的边界由共享参数测试覆盖。 | 满足 |
| Preview 与 History 的 bundle 含全部表 | t4 两侧各 312 张表绑定，缺失、多余、重复均为 0；166 个 Parquet 全部校验通过。t1–t3 逐 pair 核对 PASS（复审 2 §3）。 | 满足 |
| 重复导出命中缓存；内容相同而 schema 不同时不误命中 | N1-2 真实卷计数：651/651 个 cache 项同时有 protection intent 和 manifest 引用。命中免读与 miss 回填由调用计数测试证明；schema、ENUM 标签、writer 版本不同时不命中由用例覆盖。 | 满足 |
| 低速上传不因总时长失败；空闲超时返回新错误码 | idle 60 s、总上限、`UPLOAD_STREAM_TIMEOUT`/408（IDLE/TOTAL）的测试未变。取消生命周期 F1 已关闭。 | 满足 |
| 参照解析器对 V6 输入给出确定诊断，新增接受值有往返用例 | 首次审核核对过，DC62 第 2 项逐条一致；之后的修订没有改动解析器。 | 满足 |
| step 间隔不出现接近 heartbeat 的等待，超过 1 s 的逐项说明 | **终审补测**（§3.2），使用最终候选的卷：最大间隔 t1 0.038 s、t2 0.186 s、t3 0.380 s、t4 0.601 s，各档 12 个间隔中超过 1 s 的为 0。 | 满足 |
| 权威 runner 后节点 TMPDIR 不留锁快照文件 | 04 的 `/home/dev/gdds-test-tmp` 中没有构建脚本留下的 `mktemp` 快照。现有 `uv-*.lock` 是 uv 自己的进程锁文件，不属于 DC61 的范围。 | 满足 |
| 权威 runner 与容器门禁 | 04 runner 在 H 上 exit 0，起止 HEAD 均为 H，结束时 clean；backend 与 RS 在 H 上实际运行（含 backend Compose）。其余四包沿用 V=`91401f0146`，复审 2 已独立复算。RS 镜像按 build-input/source-tree label 判定 carried。 | 满足 |
| 真实数据：t1–t4 完整旅程 | 05 上的 t1–t3 和 ct108 上的 t4 均在 H 完成，exit 0。 | 满足；范围待 owner 确认（§4.2） |
| 真实数据：补键 11 张表、BROWSE_ONLY 17 张表 | **终审补测**（§3.2）：11 张显式键表的有效比较键不匹配数为 0；17 张 BROWSE_ONLY 表都没有比较键，各档状态与前候选审计一致。 | 满足 |
| 真实数据：t4 checkpoint 读取、bundle 段与 S1a 对比 | 只有 step 级聚合，子段无法拆分。 | **N1-1，待 owner 处置** |

## 3. 终审补充核对

### 3.1 F5 代码

`afbfaea8..020deda2` 的生产代码改动共三个文件，约 50 行，内容如下：

- History 为每个节点传入全部 canonical 表名，作为 `export_tables`。
- 请求校验分别处理 `requested_tables` 和 `export_tables`。
- materialization 对两者的并集先查缓存，只在 miss 时读取。

`export_tables` 只是内部请求字段，没有 durable schema、HTTP DTO 或兼容路径。不在任一集合中的表仍走原来的 summary 路径。改动与复审 2 的描述一致，没有发现新问题。

### 3.2 最终候选真实卷只读审计

两份复审对显式键、BROWSE_ONLY 和 step 间隔的审计用的都是前候选 `afbfaea8` 的卷，最终候选 H 的卷还没有这项审计。终审在 H 保留的旅程卷上补做了一次只读审计：

- control DB 以 `mode=ro&immutable=1` 打开，artifact 只读，只输出计数和表名，不输出行值。
- step 间隔取同一 operation 内相邻 step 的 `started_at_us − completed_at_us`。
- Surface 比较为每张表取以下字段做投影：状态、change kind、content_changed、展示策略、比较键与忽略列、schema evolution、不兼容列、有效键、风险标注数与 reason codes、行统计。表引用和 ID 不在投影内。用投影摘要比较 H 与 `afbfaea8` 两套卷。

| 档位 | operation / 成功 step / 间隔数 | 最大间隔 | >1 s | 显式键在 Surface 中 / 有数据 / 不匹配 | BROWSE_ONLY（v2） | Surface 投影 H vs afb |
| --- | --- | ---: | ---: | --- | --- | --- |
| t1 | 6 / 18 / 12 | 0.038 s | 0 | 11 / 2 / 0 | 10 UNCHANGED、7 缺席；比较键 0；标注 0 | 4 份 Surface，3 个摘要全部相同 |
| t2 | 6 / 18 / 12 | 0.186 s | 0 | 11 / 5 / 0 | 11 UNCHANGED、6 缺席；比较键 0；标注 0 | 4 份 Surface，3 个摘要全部相同 |
| t3 | 6 / 18 / 12 | 0.380 s | 0 | 11 / 5 / 0 | 12 UNCHANGED、5 缺席；比较键 0；标注 0 | 4 份 Surface，3 个摘要全部相同 |
| t4 | 6 / 18 / 12 | 0.601 s | 0 | 11 / 6 / 0 | 15 UNCHANGED、2 缺席；比较键 0；标注 0 | 4 份 Surface，3 个摘要全部相同 |

- 各档 BROWSE_ONLY 的分布与前候选审计（`10/7`、`11/6`、`12/5`、`15/2`）一致。
- v1 Preview（整表新增）上 BROWSE_ONLY 表的标注数等于其新增表数（10/11/12/15）。这来自整表新增的表级风险标注，与前候选相同。
- t3 的 v1 Surface 中显式键表只有 10 张，因为 `comm_user_data` 在 v2 才出现（ADDED_TABLE）。
- **结论：** F5 没有改变任何 Surface 的表级结果，前候选的显式键与 BROWSE_ONLY 审计结论可以直接绑定到 H。最终候选的 step 间隔满足 DC61。

### 3.3 合入可行性与门禁 worktree

- `git merge-tree --write-tree main 1b3449c00a` 无冲突。分支相对 `ae3301d6d8` 没有改动 AGENTS.md、testing-conventions.md、执行计划或 owner 决议记录。
- 主 checkout 中未提交的 AGENTS.md 与 testing-conventions.md 修改与合入无关，合入时不要把它们带进去。
- 04 门禁 worktree `/home/dev/gdds-p6-logs/s1b/04-wt` 位于 H 且 clean，可直接用于 exit 提交的 carried 判定（DC51）。

## 4. owner 处置项

### 4.1 N1-1：t4 checkpoint 读取与 bundle 子段对照（建议接受测量限制并转交）

- **现状：**
  - DC62 第 4 项限定只能用现有旅程输出和 step 时间戳，不能在产品中加插桩。
  - S1a 的子段数值来自不进入候选的诊断分支（DC59），而 S1b 把 Parquet 导出移入了 `materialize_inputs`。所以 step 级数值无法与 S1a 的子段一一对应。
- **可用的对照（t4，API 秒）：**
  - History：S1a 312.889 s；S1b 361.051 s（`materialize_inputs` 216.440 s，assemble 142.544 s）。
  - 增加的 48 s 对应新 Contract 的成本：两个节点各 312 张表都要整表导出并绑定，其中 458 次复用来自内容共享。
  - v1/repeat/v2 Preview：S1a 1,546.1/872.6/1,007.3 s，S1b 792.2/685.7/792.2 s。
  - 运行环境差异未隔离，以上不作因果断言。
- **建议决议：**
  - 接受“step 级记录满足 DC62 第 4 项在给定手段下可达的范围”。
  - checkpoint 读取与 bundle 子段的拆分转交下一阶段“重建对照基准”。该阶段在 ct108 独占测量，可以按 S1a 的方式用不进入候选的诊断计时完成拆分。
  - 未消除的差距按 DC62 第 4 项转 S2b kickoff。
  - 这项不需要再改 S1b 的产品代码。

### 4.2 DC33：真实数据范围确认

DC62 第 5 项写明的范围是 t1–t4 完整旅程，以及 step 间隔、补键 11 张表、BROWSE_ONLY 17 张表、重复导出命中缓存四项核对。这些均已在 H 上完成（§2、§3.2）。请 owner 确认以此作为 S1b 的真实数据证据。

### 4.3 不阻塞的遗留项（建议登记，不阻塞 exit）

- **O1：** `bootstrap/operation_worker.py` 的信号处理函数在主线程调用 `Event.set`，存在很窄的自锁窗口；这个模式在 S1b 之前就已存在。建议登记到 worker runtime 的后续维护。
- **O2：** JSON 中的 `1e400` 被 `json.loads` 解析为 inf，绕过了 DC62 2e 对非有限值的拒绝，而 MySQL 会拒绝该值。建议作为语义确认项列入 S2a kickoff（S2a 要与参照实现做差分），由 owner 决定是否与 2e 一并拒绝。

## 5. exit 办理步骤（owner 授权后）

1. 在 owner 决议记录中登记 §4.1–§4.3 的处置，并把执行计划 §2 S1b 的状态更新为已通过，写明候选、handoff、审核链与证据绑定。
2. 在 main 上用 merge commit 合入 `p6-s1b-impl`（`--no-ff`，不改写已审核提交）。不要带入主 checkout 中未提交的修改。
3. 在 04 的 `04-wt` 上检出 exit 提交，按与来源 runner 相同的环境和 `HYPOTHESIS_STORAGE_DIRECTORY` 计算六包 manifest，逐项 compare：
   - rust、shared_kernel、repository_contracts、repository_client 的来源为 V=`91401f0146`（`04-runner-final-91401f0146.log`）；
   - backend、repository_service 的来源为 H（`04-runner-f5-020deda2.log`）；
   - RS 镜像 label 在 exit 提交上重算。
   全部判定可沿用后，在 exit 提交上打附注 tag `p6-s1b-exit`。
4. 推送和三节点 git bundle 同步需 owner 授权。
5. 合入之后，经 owner 授权，按 handoff 的“F5 保留与清理清单”及各审核报告列出的 worktree、日志和缓存进行清理。真实数据卷和含真实数据的 scratch 按 §8.4 清理。

## 6. 本次执行记录

- 开发节点只读 git 和文档，没有在开发节点运行测试。三节点 SSH 连接正常；审计前确认三节点都没有运行中的容器、pytest、runner 或 Dolt server。
- 05 `gw-dms-test-05`，2026-10-29 01:52:16–01:52:18Z：审计 t1–t3，exit 0。日志：`/home/dev/gdds-p6-logs/s1b/final-review-audit-020deda2-gw-dms-test-05.log`。
- ct108 `gw-dms-test`，01:52:18–01:52:19Z：审计 t4，exit 0。日志：`/home/dev/gdds-p6-logs/s1b/final-review-audit-020deda2-gw-dms-test.log`。
- 两份日志已复制到开发节点同路径。审计脚本保存在开发节点 `/home/dev/gdds-p6-logs/s1b/review2-claude/final_audit.py`，节点副本在 `/home/dev/gdds-test-tmp/s1b-review2/`。
- 镜像：本次只提交审核文档，不触发重建。H 的容器证据取自 04 runner 和 RS label。
- 没有写入任何 worktree、卷或镜像，没有推送、打 tag 或合入。新增的清理项为上述两份日志和节点上的脚本副本。
