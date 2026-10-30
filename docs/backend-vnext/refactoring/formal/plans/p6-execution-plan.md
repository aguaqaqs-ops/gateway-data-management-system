# Phase 6 执行计划

状态：**ACCEPTED — S0 文档（r4）经独立文档审核（首次审核与三次复审，第 3 次复审结论：通过）由 repository owner 于 2026-10-26 接受；实现授权范围见执行计划 §2 S0**

日期：2026-10-26（r4）；r1–r3 为 2026-10-26

审核：[S0 独立文档审核](p6-s0-independent-docs-review.md)；findings 处置见详细设计附录 A。

Owner：Backend vNext Architecture

入口：[S0 Owner 决议记录](p6-s0-owner-decisions.md)（DC37–DC55）→ [详细设计](p6-design.md) → 本文

B=`vnext/backend/src/gateway_backend/`，T=`vnext/backend/tests/`，R=`vnext/rust/`。本文写未来的步骤与期望证据；实际结果写入各阶段 handoff。

## 1. 执行形态

```text
S0  决议（DC37–DC55）、前置验证（已完成）、本设计与计划、独立文档审核、kickoff 小修、keyless 自然键评估
 -> S1a 摘要与存储 Contract（DC39、DC45 表级跳过与阈值）+ worker step 归因
 -> S1b 业务语义 Contract（DC40、DC41、DC49、参照解析器修复与语义定稿）+ 合成负载
 -> S1c Submit 等待预算与人工恢复续行修订（DC65，修订 2026-10-30）
 -> 重建对照基准（Python；工具开发可与 S1c 并行，正式测量在 S1c exit 之后）
 -> S2a SQL 解析器（Rust，flag 之后）+ 删除旧扩展
 -> S2b 上传侧数据路径与规范表存储（切换生产）
 -> S3  比较与逐行记录（Rust）
 -> S4  Submit 渲染直通
 -> S5  History 与跨操作缓存
 -> S6  收尾与 Phase 6 退出
```

阶段顺序依据见设计 §4–§12 与 DC50：先改 Contract、再改性能；每类 golden 只改一次（例外见设计 §4.6）；表摘要 → 解析器与存储 → 比较 → Submit → History。

每个实施阶段结束交独立审核，未通过不进入下一阶段。前置验证类工作（原型、测量）不做独立审核，结果在设计审核中复核（DC48 讨论）。

## 2. 阶段定义

### S0 — 剩余工作

- **独立文档审核：** 审核对象为本文、详细设计、决议记录 DC37–DC55 与 implementation-stages §9/§10 的改写；必须复核的代码事实见设计 §2.2（Submit 全量重写、Preview 全量物化基线、bundle 不含整表、上传 60 s 总时限、uv 不重建扩展）。审核报告模板沿用 [P5 执行计划 §8.8](p5-arch-closure-execution-plan.md)。
- **kickoff 小修**（不单独审核，随 S1a 审核）：`uv-consume.sh` 的 EXIT trap（`mktemp` 锁快照残留）；测试留下的 `repository-import-*.sqlite3-shm/-wal`；三项文档整理（讨论稿 §12）；RS defunct `dolt` 进程：交 RS owner 排查，修复若涉及 Dockerfile/Compose 则为强制重建项，可并入 S1a。
- **业务评估：** 重要 keyless 表是否定义自然键，**S1b kickoff 之前**由 owner 给出（owner 2026-10-26 修订：原为 S1a 之前；补键改变规范键与比较结果，属于 S1b 冻结的比较类 golden，故截止点改为 S1b kickoff 之前，S1a 不等待）；先由实施者做候选键普查（见下），owner 确认后，补键的规则改动放进 S1b。
- **定向复审：** 交同一审核者复审，逐项核对设计附录 A 的处置与 findings 的关闭标准（r2、r3 已经第 1、2 次复审，r4 待定向复核 F5 与 F13）。
- **接受：** 复审通过、owner 接受文档后给出实现授权。
- **接受与授权（repository owner，2026-10-26）：** 第 3 次复审结论为通过（[S0 独立文档审核](p6-s0-independent-docs-review.md) §8）；owner 接受本文、详细设计 r4 与决议记录 DC37–DC55。**实现授权范围：** kickoff 小修（含 RS defunct 进程的排查与小范围修复）、keyless 候选键普查（测量工具与报告，不改规则）、S1a。S1b 及之后各阶段另行授权。
- **kickoff 小修的审核方式（owner 2026-10-26 修订）：** 由实施者完成并在门禁节点 04 运行一次全量门禁，交 handoff 后回 S0 讨论会话做一轮轻量审核（同 DC48）；通过后开始 S1a。
- **keyless 候选键普查（owner 2026-10-26）：** 由实施者在调试节点 05 上对 t1–t4 做只出计数与列名的候选键普查，交报告；owner 检查确认并给出补键的具体要求，S0 讨论会话审核。

### S1a — 摘要与存储 Contract

- 目标：设计 §4。
- 前置：S0 接受；kickoff 小修经轻量审核通过。
- 内容：
  1. 表摘要统一与快照身份（设计 §4.1，DC58）：快照身份只用不读行即可得到的表级事实，删除 `fast_row_digest`；manifest 内容摘要改为 `raw_content_digest`；`STORAGE_PROJECTION_VERSION = "3"`；删除 `ordering_digest`（含 `import_publication.py` 的传递）；去掉重复计算。
  2. Preview 与 History 的结构性过滤（§4.2，完整条件），含未变化 ordered 表不读基线、不做行比较，其逻辑摘要与 occupancy 摘要用当前侧的行按本次有效 pair 策略计算（§4.1，DC55 第 1 项）。
  3. Submit 表级跳过与 `ADAPTIVE_PATCH`（§4.3）：T1 冻结 policy、prepare checkpoint 绑定 parent manifest digest、parent 行按 manifest 校验、有序表资格、阈值 1,000 行 / 1%；行级修改按批渲染（DC57：先用合成表预检 Dolt 语句形式，再复测）；阈值复测后冻结阈值与 INSERT、UPDATE、DELETE 的批量规则（DC55 第 5 项、DC57）。
  4. Contract 修订（设计 §14 中标注 S1a 的行）与 golden（storage-projection、mutation、导入包，设计 §4.6）。
  5. worker step 归因（§4.4）：每项 step 间隔与残差的来源、削减方案、处理阶段与 owner，写入 handoff。
  6. Repository Service 读取诊断（owner 2026-10-27 追加授权）：`versioned_read/arrow_bridge.py` 的 bridge worker 捕获异常时记录异常类型与消息（不记录行数据），补 focused 测试；最终门禁照常重建 repository-service 镜像。起因：S1a 测量中，回放工具以 root 身份在 RS 正在服务的 Dolt 仓库中写入，使 `.dolt/noms/manifest` 等文件变为 root 所有，RS 的后续读取一启动即失败，而 worker 吞掉了异常，日志只有“stream aborted”。测量工具改为在仓库副本上回放；被污染的 t4 栈停止并保留至清理，不再用于测量。
- 验收：
  - 设计 §16.2 中基线读取、比较派发与 Submit 的计数断言在 focused 测试中按公式成立（含手算示例），t4 旅程中记录；
  - 新旧路径在 t4 v2 上的 Dolt 表哈希相同；
  - 设计 §4.1 摘要变化与保值清单中“保值”的各项不变；摘要值改变的产物按 §4.1 的核对方式（屏蔽摘要字段后逐字节相同）核对；golden 只按 §4.6 变化；
  - 权威 runner 六个包通过；容器门禁（Submit 路径与镜像内代码变化）。
- 真实数据：t1–t4 完整旅程（t1–t3 在 05，t4 在 ct108），业务结果按新 Contract 核对。
- 证据范围（owner 2026-10-27）：S1a 的验收（阈值复测、Dolt 表哈希、t1–t4 旅程、DC58 核对、权威 runner 与容器门禁）在最终候选上重新运行，不沿用此前候选的结果；worker step 归因按 DC59 已接受的阶段级分解，不随候选重跑（DC60）。
- **状态：已通过（repository owner，2026-10-27）。** 产品候选 `7d0ce6220a`，handoff `a5098fe8b6`（[S1a handoff](p6-s1a-handoff.md)）；[独立审核](p6-s1a-independent-review.md)首次结论为定向修订（F1–F3、N1–N2），第一次复审通过。验收证据均绑定 `7d0ce6220a`：04 六包权威 runner（含 RS 镜像重建与 Compose 旅程）、05 t1–t3、ct108 t4 与阈值/表哈希复测；owner 确认真实数据范围为 t1–t4 完整旅程（DC33）。合入后在 04 原门禁 worktree 对 exit 提交做 carried，附注 tag `p6-s1a-exit`。

### S1b — 业务语义 Contract

- 目标：设计 §5。
- 前置：S1a exit；keyless 自然键评估已由 owner 给出。
- 内容：
  1. 只增列（§5.1）；
  2. bundle 补齐整表与导出缓存（§5.2）；整表新增或删除改为整表浏览（§5.3）；
  3. 慢速上传：空闲超时、总上限、新错误码、受理移到线程池（§5.4）；
  4. 参照解析器的缺陷修复与语义定稿（§5.5；P 项已由 owner 在 kickoff 确认，DC62 第 2 项）；零日期维持拒绝；FLOAT 直接舍入在 Shared Kernel 修复（DC55 第 4 项）；
  4a. 按 DC56 改规则：11 张表补显式键（`forwardtbl_lst_*` 用 8 个精确名，DC62 第 1 项），17 张表加入 BROWSE_ONLY 名单（规则集版本随之提升）；storage-projection 中的规则集与 manifest golden 按设计 §4.6 的例外行在本阶段更新一次，与比较类 golden 一起冻结；
  5. 合成 2× t4 与 W4 生成工具、测量 runbook（§5.6）；
  6. Contract 修订（设计 §14 中标注 S1b 的行）与 golden（comparison、risk、surface、bundle、table-access、shared-kernel 编码向量，设计 §4.6）；
  7. worker 在 step 完成后立即唤醒（设计 §5.7，DC61 第 1–4 项）；
  8. `build-repository-service-image.sh` 的锁快照用 EXIT trap 清理，测试隔离 TMPDIR（DC61 第 5 项）。
- 验收：
  - 只增列的表不降级、无风险；Submit 仍生成版本；
  - Preview 与 History 的 bundle 含全部表，重复导出命中导出缓存，内容相同而 schema 不同时不误命中；
  - 上传在低速下不因总时长失败、空闲超时返回新错误码；
  - 参照解析器对 V6 列出的输入给出确定诊断，不抛未捕获异常；新增接受的值有合成往返用例；
  - t1–t4 旅程的 step 间隔不再出现接近 heartbeat 周期的等待，超过 1 s 的在 handoff 中逐项说明（DC61）；权威 runner 后节点 TMPDIR 不留锁快照文件；
  - 权威 runner 与容器门禁。
- 真实数据：t1–t4 完整旅程；t3 覆盖只增列（即原 testdata1）。另核对 step 间隔（DC61）、补键 11 张表的比较结果、新增 BROWSE_ONLY 17 张表的处理、重复导出命中导出缓存；t4 的 checkpoint 读取与 bundle 段耗时与 S1a 对比，不设门槛（DC62 第 4、5 项）。
- **kickoff 确认与授权（repository owner，2026-10-28）：** DC62；授权 S1b，范围为设计 §5.1–§5.8 及对应的 Contract 与 golden 修订。
- **状态：已通过（repository owner，2026-10-29）。** 代码候选 `020deda2fd`，handoff `1b3449c00a`（[S1b handoff](p6-s1b-handoff.md)）；[首次审核](p6-s1b-independent-review.md)与[第二审核人报告](p6-s1b-independent-review-b.md)结论为定向修订（F1–F4、N1），[第 1 次复审](p6-s1b-independent-rereview-1.md)新增 F5，[第 2 次复审](p6-s1b-independent-rereview-2.md)通过，[终审](p6-s1b-final-review.md)判定具备 exit 条件。验收证据均绑定 `020deda2fd`：04 权威 runner（backend 与 repository_service 运行，其余四包沿用 V=`91401f0146`，RS 镜像按 label carried）、05 t1–t3、ct108 t4 与最终卷只读审计；N1-1 按 DC63 第 1 项接受测量限制，真实数据范围按 DC63 第 2 项确认（DC33）。合入（`321f3b8523`）后在 04 原门禁 worktree 对 exit 提交做 carried，附注 tag `p6-s1b-exit`。

### 重建对照基准

- 前置：S1b exit。正式测量（ct108 场景与 04 最终 runner）另以 S1c exit 为前置，在 p6-s1c-exit 的产品上进行；工具开发与 05 验证可先行（DC65 修订第 1、3 项）。
- 内容：设计 §6，覆盖设计 §16.3 验收矩阵中的全部场景；记录写入基准 handoff，作为 S2a–S6 的对照。
- 另含：t4 checkpoint 读取与 bundle 子段的拆分，用不进入候选的诊断计时完成，与 S1a 子段对照；未消除的差距转 S2b kickoff（DC63 第 1 项）。
- 节点：`ct108-gw-dms` 独占。
- **授权（repository owner，2026-10-29）：** 授权重建对照基准，范围为设计 §6、§16.3 验收矩阵的全部场景与 DC63 第 1 项的子段拆分；只扩展测量工具，不改产品代码与 golden。同时授权 S1b exit 的推送、三节点同步与清理。

### S1c — Submit 等待预算与人工恢复续行修订（DC65）

- 目标：
  - Submit 的 `await_import_result` 在 Repository Service 健康运行时持续对账，不因单次 60 s 轮询到期而消耗恢复会话；总等待上界与 Repository Service 导入上限对齐（DC65 方案 B）。
  - 人工恢复命令（`RESUME_RECONCILE`、`RETRY_FROM_CHECKPOINT`）被接受后，step 由运行中的 worker 继续执行，每条命令授予一次恢复会话（DC65 修订第 2 项）。
- 前置：S1b exit。在重建对照基准的正式测量之前完成；需要 ct108 取证时，与基准会话协调，不并用。
- 内容：
  - `operations/recovery.py` 与 `application/submit_jobs.py` 的会话计数规则；
  - 人工恢复命令的状态转换与领取；
  - P4 R5 设计 §6–§7、P5-5B 设计 §13.1 与 operator recovery 条款；
  - 权威测试：
    - 健康等待不消耗会话；超出上界转人工恢复；
    - 崩溃、lease 丢失与结果未知仍计数；
    - drain 在单次轮询内响应；
    - safe handoff 后的重新领取不增加 `attempt_count`；
    - 恢复命令后无需重启即被领取并完成；命令授予的会话再次失败时回到人工恢复；
    - 命令后重启 worker 不判为会话用尽。
- 验收：
  - 权威测试与五包静态检查；权威 runner 与容器门禁；
  - 2× t4 的 v1 Submit 在 ct108 上无人工干预完成；
  - Submit 结果与 `p6b2xwarmr5fix1030b` 保留卷的 Dolt 表哈希、canonical state 一致（DC65 修订第 4 项，DC64 第 4 项口径）。
- 真实数据：在 kickoff 写明、退出前由 owner 确认（DC33）。
- **授权（repository owner，2026-10-29；修订 2026-10-30）：** DC65 及其修订。

### S2a — SQL 解析器

- 目标：设计 §7。
- 前置：S1b exit（语义已定稿）；重建对照基准已完成。
- 内容：补齐诊断与语料；PyO3 adapter；worker 级共享线程池；feature flag 之后接入（只差分）；删除旧扩展并调整 Dockerfile 与 `rust` 包的排除（DC52）。
- 验收：五层语料通过；t1–t4 逐值差异 0；1 与 N 线程逐字节相同；旧扩展相关代码、golden、Contract 已删除；新扩展的构建输入检查、`rust` 包排除的去除与 `import_rules` 基线同步核对；权威 runner 与容器门禁（Dockerfile 变化）。
- 真实数据：只做第 ④ 层逐值差分（05；t4 也可在 05，DC50 补充）。

### S2b — 上传侧数据路径与规范表存储

- 目标：设计 §8。
- 前置：S2a exit；S1c exit（DC65）；设计核对项（上传侧原始表的使用方、磁盘估算）已完成。
- 内容：数据路径合并 kernel；Arrow 列映射 v1；规范表存储（内容地址、IPC、读取校验、BaselineHead 正式引用与 TTL）；N/M 准入与 pyarrow 线程池；feature flag 切换生产；Canonical Storage §5 修订。
- 验收：t1–t4 端到端摘要与基准一致；存储读取校验、Dolt 兜底与冻结产物四种状态的权威测试；计数断言；W1–W3 测量（ct108）；**W2 可达性检查点**（设计 §16.1：剩余成本不能在 30 s 内闭合时停止，交 owner）；权威 runner 与容器门禁。
- 真实数据：t1–t4 端到端摘要一致；测本阶段相关负载。

### S3 — 比较与逐行记录

- 目标：设计 §9。
- 前置：S2b exit。
- 内容：共用比较内核（standard、keyless、ordered）；逐行记录 Arrow 与 `content_digest`；记录写入改为 pyarrow 由 Arrow batch 写，删除发布后回读（保留读取校验）；风险按 Arrow 分批消费；单次操作内去重（键含规则与版本）；Comparison 与 Risk 的缓存条款修订（设计 §14）；分歧点按现行行为写进 Contract；feature flag 接入。
- 验收：差分（语料、随机、t1–t4）逐字节一致；记录 golden 逐字节一致；去重开关不改结果；W3、W4（含 FULL 一次与 100% 压力档，只报告）测量，W4 中不存在未计入的逐行 Python 转换；权威 runner 与容器门禁。

### S4 — Submit

- 目标：设计 §10。
- 前置：S3 exit。
- 内容：渲染直通；存储 diff 共用内核；用最终渲染器复测 S1a 冻结的阈值与批量规则（须调整时作为例外交 owner）。S1a 终审登记（2026-10-27）：UPDATE、DELETE 分批时每加一行重渲染整批（`_render_limited_mutation_batches`），渲染量随批大小平方增长；整表重建对 parent 每行生成逐键 DELETE，代价随重建表行数放大。t4 未见可测回退，S4 改为按增量累计完整语句字节分批，批次划分与 SQL 字节不变。
- 验收：同一输入的 `replay.sql` 与 S1a 产物逐字节一致；设计 §16.2 的 Submit 计数；S1–S4 完成时间（main 前移）；权威 runner 与容器门禁（Submit Compose 旅程）。

### S5 — History 与跨操作缓存

- 目标：设计 §11。
- 前置：S3、S4 exit。
- 内容：diff/risk 缓存（只缓存纯函数结果，pair 上限在汇总绑定）与 finalize 登记引用；History 按表拼接（完整条件）；Dolt 并发读取（≤ min(N, RS 容量)，503 有界退避，继承取消与截止时间）；H2 冷读验收。
- 验收：设计 §16.3 中 H1、H1-FULL、H1-回填、H2、H2-三节点（只报告）、H3 各场景；计数断言按 §16.2 的条件判定；缓存只缓存纯函数结果的权威测试；权威 runner 与容器门禁。

### S6 — 收尾

- 目标：设计 §12。
- 内容：加速曲线定 N；删除生产 feature flag；按设计 §16.3 验收矩阵完成全部场景取证；存储报告；门禁时长重新剖析；Phase 6 退出。
- 验收：设计 §16.3 全部场景（门槛项达标、只报告项有记录）与 §16.2 全部计数断言；最终提交上完整运行权威 runner（六个包）与容器门禁各一次；Phase 6 退出审核。
- 真实数据：2× t4 全部负载（1 次预热加 3 次测量）与 t1–t4 完整旅程。

## 3. 路径预算（主要改动面）

| 阶段 | 主要路径 |
| --- | --- |
| S1a | B`capabilities/storage_projection/`（`_digest.py`、`project.py`、`publish.py`、`contracts.py`、`package.py`、`import_replay.py`）、B`capabilities/table_rules/contracts.py`、B`capabilities/mutation_planning/`、B`capabilities/comparison/standard.py` 与 `ordered.py`、B`application/preview_jobs.py`、B`application/history/compare_jobs.py`、B`application/submission/import_builder.py`、B`infrastructure/repository_write/import_publication.py`、B`application/submit_jobs.py`；golden：storage-projection、mutation |
| S1b | `vnext/shared_kernel/src/gateway_shared_kernel/scalar.py`（FLOAT 直接舍入）与 shared-kernel 编码向量 golden、B`capabilities/comparison/`（`row_encoding.py`、`contracts.py`、`artifacts.py`）、B`capabilities/risk_evaluation/`、B`capabilities/surface_assembly/`、B`capabilities/bundle_assembly/`、B`application/pair_pipeline.py`、B`http/orchestration/`（`multipart_stream.py`、`multipart_upload.py`）、B`application/workspace/upload_limits.py`、B`capabilities/table_access/`（参照解析器修复）、B`capabilities/table_rules/`（DC56 规则改动）与 storage-projection 规则集、manifest golden、`vnext/backend/benchmarks/`（合成负载）；control DB 基线 schema（导出缓存 owner）；B`operations/worker_runtime.py`、B`bootstrap/operation_worker.py`（DC61）；`vnext/scripts/build-repository-service-image.sh` 与其测试（DC61） |
| S2a | R`gateway-compute-core/src/table_access/`、R`gateway-compute-python*`（新 adapter，删除旧 crate 内容）、B`capabilities/table_access/`（flag 接入）、B`capabilities/canonical_row_hash/`（删除）、`vnext/backend/Dockerfile`、`vnext/scripts/run-tests.sh`（去掉排除）、`vnext/scripts/check-rust-extension-build-input.sh`（核对新扩展）、`vnext/scripts/native_kernel_component.sh`（删除）、T`architecture_baseline.py` 与 `import_rules` 基线 |
| S2b | R`gateway-compute-core/src/`（物化、投影、摘要模块）、B`capabilities/snapshot_materialization/`、B`capabilities/storage_projection/`、B`artifacts/` 与 B`infrastructure/artifact_store/`、control DB 基线 schema（BaselineHead owner）、B`settings.py`（N、M）、B`bootstrap/operation_worker.py`（线程池） |
| S3 | R`gateway-compute-core/src/comparison/`、B`capabilities/comparison/`、B`capabilities/risk_evaluation/`（接口） |
| S4 | R`gateway-compute-core/src/`（渲染）、B`capabilities/mutation_planning/`、B`infrastructure/repository_write/import_publication.py` |
| S5 | B`application/history/`、B`capabilities/comparison/`（缓存接口）、B`application/submission/finalize*.py`、B`infrastructure/repository_read/`（并发与 503 退避）、control DB 基线 schema（缓存 owner） |
| S6 | feature flag 删除涉及的全部入口；测量 runbook |

每阶段 kickoff 时对照当前 HEAD 复核路径预算，偏离先修订设计再开工。

## 4. 测试归属与比例化

按设计 §15：每个不变量一个权威测试 owner；测试按业务行为命名；删除生产机制（旧扩展、Python 生产路径）时同步删除其 mock 与证明探针。Rust 侧：单元测试、proptest（stable）与确定性测试进入 `rust` 包；需要 Python 解释器的测试用 pytest 测已安装的扩展（DC48）。

## 5. 命令草案

```bash
# 调试节点 05：focused 测试（Rust 改动后先强制重装扩展）
cd vnext/backend && ../scripts/uv-consume.sh -C . sync --reinstall-package gateway-compute-python
../scripts/uv-consume.sh -C . run pytest -m unit <focused paths>

# 调试节点 05：Rust 静态检查（CARGO_TARGET_DIR 在 worktree 外）
cd vnext/rust && cargo fmt --all --check && \
  CARGO_TARGET_DIR=/home/dev/gdds-test-tmp/<任务>-cargo-target \
  cargo clippy --workspace --locked --offline --all-targets -- -D warnings

# 门禁节点 04：阶段最终提交的权威 runner（clean detached worktree；先重建 RS 镜像）
./vnext/scripts/build-repository-service-image.sh
GATEWAY_TEST_WORKERS=48 ./vnext/scripts/run-tests.sh

# 参考节点 ct108：真实数据 t4 旅程与测量（独占）
# real_dump_journey.py 与各测量工具；日志开头记录 hostname、起止时间与 HEAD
```

固定环境沿用 DC48 门禁脚本：`umask 022`、`HOME=/root`、`LC_ALL=C.UTF-8`、`TMPDIR=/home/dev/gdds-test-tmp`、`PATH` 含 `/home/dev/.cargo/bin`。

## 6. 镜像重建判定

按 AGENTS“Docker / Compose 验证”。Phase 6 中以下阶段必然触发重建：S2a（Dockerfile 与 adapter）、任何改动 `vnext/rust` 的阶段（backend 闭包含 Rust workspace，扩展编入镜像）、S1b（control DB 基线 schema 与 HTTP 接线变化，若涉及）。阶段退出可按镜像身份等价 `carried`，门禁 worktree 保留到阶段 exit 合入之后（DC51）。

## 7. 停止规则

设计 §17 的停止条件（含 S2b 的 W2 可达性检查点）之外：

- runner exit 非 0 时先处理该失败，不继续 carried 或后续验收（AGENTS）；
- auto-mode 分类器拒绝的命令不改写绕过，停下报告；
- 节点不可用或前提不满足时等待，不回退到开发主机；
- 真实数据或测量结果与基准不一致且无法归因时停止。

## 8. 阶段推进约定

### 8.1 授权、提交与阶段边界

- 直接在 `main` 上提交；需要与其他会话并行时用单独的 linked worktree 与短期分支，合回用 merge commit，不改写已被引用的提交。
- 阶段边界用附注 tag `p6-sNN-exit`（例如 `p6-s1a-exit`）；审核对象为 `<上一阶段 tag>..<候选提交>`。
- 未经 owner 授权不推送；节点同步用 git bundle，不经 GitHub（DC36）。

### 8.2 实施者与审核者

- 每个实施阶段：实施者在新对话中按提示词完成，先交代码候选；独立审核者在只读 detached worktree 中审核代码，有问题修复后复审；代码通过后在最终候选上运行一次完整证据，由同一审核会话做证据复核（DC64 第 1 项）；通过后打 tag、合入、推送（经授权）。
- 门禁基础设施改动（如 DC48 类）做一轮轻量审核；原型与测量不做独立审核，结果作为设计输入。
- 同一节点同一时间只给一个会话做测量或门禁；使用前确认空闲。

### 8.3 handoff

每阶段 handoff 至少包含：改动清单与提交；Contract 与 golden 的变化及理由；计数断言与测量结果（节点、HEAD、起止时间、exit code、日志位置）；权威 runner 与容器门禁的逐包结果（运行或沿用、来源 V、来源日志）；真实数据范围与结果；偏差与未决；节点上需要清理的内容。

### 8.4 真实数据与调试取证

沿用 DC30、DC33，按 DC64 修订：调试期间只跑 focused 测试与出问题的那一段真实数据；收敛后先在节点 05 做门禁前预检（[P5 执行计划 §8.9](p5-arch-closure-execution-plan.md)），交代码候选审核；代码通过后，在最终候选上完整运行权威 runner 一次、运行真实数据一次作为证据；证据之后的修订按受影响步骤重跑（DC64 第 2 项），不适用时整档重跑；真实数据范围在 kickoff 写明、退出前由 owner 确认。真实数据不进 Git（DC22）；含真实数据的中间产物放在节点 worktree 外，阶段结束后经 owner 授权清理。

### 8.5 提示词与审核报告模板

沿用 [P5 执行计划 §8.7、§8.8](p5-arch-closure-execution-plan.md) 的结构；Phase 6 的提示词另须写明：节点分工与空闲确认、短期分支与 bundle 同步、feature flag 约定、不改写参照实现（差分阶段）、不绕过 auto-mode 分类器的拒绝。
