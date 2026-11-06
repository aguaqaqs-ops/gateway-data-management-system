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
    ‖ backend 镜像依赖层调整（DC67 补充第 5 项；已完成 2026-10-31，tag `p6-backend-image-exit`）
 -> S2a SQL 解析器（Rust，test-only 差分）+ 删除旧扩展（DC70/DC81：与基准并行，exit 不再等待基准整体 exit）
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
- 测量方式（DC66）：
  - 每个负载在 ct108 上单次测量，正式测量前以一次 t1 旅程预热；偏离参考证据超过 10% 时补测；
  - 离线 composite 比较按输入与代码摘要复用；
  - 每个计时步骤之前保存 checkpoint，失败后从 checkpoint 续跑；
  - 工具缺陷由实施者按常设授权直接修正。
- 节点：`ct108-gw-dms` 独占。
- **授权（repository owner，2026-10-29）：** 授权重建对照基准，范围为设计 §6、§16.3 验收矩阵的全部场景与 DC63 第 1 项的子段拆分；只扩展测量工具，不改产品代码与 golden。同时授权 S1b exit 的推送、三节点同步与清理。

- **输入准备工具并行完善（owner，2026-11-05，DC79）：** 按[独立工具 kickoff](p6-baseline-input-preparation-kickoff.md)补实际表形态小样本预检及生成/验收分段复用；独立 worktree、05 focused 验证，当前 CT108 生成不中断。工具候选经定向审核后协调后续使用，不改本轮完整验收、停止规则或已通过场景，不为采用新工具重复大生成。
- **后续重开策略（owner，2026-11-05，DC79 补充）：** 当前若失败且按原停止规则获准重开，优先复用有效产物，需重生成时显式使用经审核的多路方案，不再默认单路完整重跑。空闲 05 可推进 kickoff §5.5 的 pair/W4 四任务调度与有界验证；当前流程不中断，正式计时口径与节点单飞不变。
- **停止后主动处置（owner，2026-11-05，DC80）：** 受影响运行先停止，诊断/最小修复/审核主动继续，不默认等待 owner 催办。本次 READY 闭包容量修正按[定向 kickoff](p6-ready-closure-capacity-kickoff.md)推进；满足精确产品差异、新镜像验证和证据不变条件后，从 W4 `v2-preview` 前快照副本恢复。原样重试、泛化绕过身份、无依据沿用证据均不在范围内。

### S1c — Submit 等待预算与人工恢复续行修订（DC65）

- **状态：已通过（repository owner，2026-10-31）。** 代码候选 V'=`ebd1b60a3f`，最终 HEAD `9f288ad504`（[S1c handoff](p6-s1c-handoff.md)）；[首次审核](p6-s1c-independent-review.md)为定向修订（F1–F4），[复审 1](p6-s1c-independent-rereview-1.md)通过；取证中发现的变更集排序缺陷按 DC69 并入，[DC69 修复复审](p6-s1c-dc69-rereview.md)通过，[取证复核 5](p6-s1c-evidence-check-5.md)证据通过，[终审](p6-s1c-final-review.md)判定具备 exit 条件。证据绑定 V'：04 六包权威 runner（含 backend Compose 旅程，backend/worker 为开发节点预构建镜像，RS 镜像 label 指向 V'）、05 t1、ct108 2× t4 三节点完整旅程与两项只读对照；真实数据范围按 DC71 第 1 项确认（DC33）。在 04 原门禁 worktree 对 `9f288ad504` 做 carried（六包可沿用，RS label 一致），附注 tag `p6-s1c-exit` 打在 `9f288ad504`，合入 main（`49d0846d86`）。
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
  - mutation planner 变更集排序缺陷的修复（DC69）：`_patch_mutations` 按 DELETE → UPDATE → INSERT 分阶段输出；PURE_RECOMPUTE 兜底分支在日志中记录异常堆栈。
- 验收：
  - 权威测试与五包静态检查；权威 runner 与容器门禁；
  - 2× t4 的 v1 Submit 在 ct108 上无人工干预完成；
  - Submit 结果与 `p6b2xwarmr5fix1030b` 保留卷的 Dolt 表哈希、canonical state 一致（DC65 修订第 4 项，DC64 第 4 项口径）；
  - 三节点旅程的 v3（回退到 v1 内容）Submit 成功，v3 commit 与同次运行 v1 commit 的表哈希一致（DC69）。
- 真实数据（DC66 第 4 项及其 2026-10-31 修订，DC69）：05 的 t1 冒烟；ct108 的 2× t4 三节点完整旅程一次（预构建 V' 镜像，冷 History，五个 checkpoint，保留卷），v1 Submit 结果与 `p6b2xwarmr5fix1030b` 保留卷只读对照，v3 commit 与同次 v1 commit 对照。kickoff 写明，退出前由 owner 确认（DC33）。
- **授权（repository owner，2026-10-29；修订 2026-10-30、2026-10-31）：** DC65 及其修订；DC66 及其修订；DC69。

### backend 镜像依赖层调整（DC67 补充第 5 项）

- **状态：已完成（2026-10-31）。** 附注 tag `p6-backend-image-exit`（`72dd45a47b`），合入 main；证据见 [handoff](p6-backend-image-deps-handoff.md) 与 [证据复核 2](p6-backend-image-deps-evidence-check-2.md)。DC67 补充第 2 项的替代记录见 DC67。S2a 的这一前置已满足。
- 目标：backend/worker 镜像可在测试节点离线构建。新增按锁定输入打 tag 的 backend dependency-base 镜像与预置依赖开关（参照 Repository Service 与 client e2e 的做法）；Dockerfile 的依赖层只取决于锁定输入，本地源码在其后复制，此后的步骤不再联网；最终运行镜像与现状等价。完成后，DC67 补充第 2 项（在开发节点预构建整镜像）改为“锁定输入变化时在开发节点预构建 dependency-base，节点离线自建 backend/worker 镜像”，在本任务 exit 时记录。
- 前置：无（基于 main `26738ae5c4`）。可与 S1c、重建对照基准并行；取证需独占 04，与 S1c 协调，不并用节点。S1c 先合入时，合并 main 后再取证。
- 内容：
  - backend Dockerfile、新增 dependency-base Dockerfile 与构建脚本 `vnext/scripts/build-backend-dependency-base.sh`；
  - compose.yaml 的 build 参数与预置开关（默认保持现有行为）；
  - test_input_closure.py 中 backend 闭包记录 dependency-base 镜像、本机 image ID 与开关；
  - 对应测试（test_backend_dockerfile_contract.py、脚本测试、test_test_input_closure.py）。
  - 不改应用代码、Contract、golden 与依赖锁。AGENTS.md 与 testing-conventions 的条文建议写入 handoff，由维护这两份文件的会话同步。
- 验收（DC64 流程）：
  - focused 测试与五包静态检查；
  - 04 上以 `GATEWAY_DOCKER_BUILD_NETWORK=none`、预置模式构建候选镜像成功；对 repository_client 与 rust 源码做无害改动后离线重建成功（改动不进入候选）；
  - 与 main `26738ae5c4` 现有 Dockerfile 构建的镜像做等价核对（已安装包集合、应用源码、runtime ENV 与 CMD）；
  - 04 权威 runner 与容器门禁（Dockerfile、Compose 变化），环境按 DC67 补充（UV_OFFLINE=1、CARGO_NET_OFFLINE=true、backend 预置开关）。
- 真实数据：不改应用代码，不跑；镜像等价核对出现构建产物以外的差异时交 owner 决定是否补 t1 冒烟（DC33）。
- 分支：短期分支 `p6-backend-image-deps`；handoff 为 `p6-backend-image-deps-handoff.md`；exit 由 owner 确认后合入，附注 tag `p6-backend-image-exit`。
- **授权（repository owner，2026-10-30）：** DC67 补充第 5 项；本节安排。

### S2a — SQL 解析器

- 目标：设计 §7。
- 前置：S1b exit（语义已定稿）；backend 镜像依赖层调整已合入（DC67 补充第 5 项）。开发在 S1c exit 合入后开始，与重建对照基准的正式测量并行，分支 `p6-s2a`，基于 merge commit `49d0846d86`（DC71 第 2 项）；ct108 在基准测量期间不使用，04 由基准的最终 runner 优先。**DC81（owner，2026-11-05）解除 exit 对基准整体 exit 的依赖**：核对现有证据及合入影响后办理，不默认重跑全部，不由设计替代独立证据审核。
- 内容：补齐诊断与语料；PyO3 adapter；adapter 内进程共享线程池（worker 启动接线在 S2b）；test-only 双实现差分入口，生产仍走 Python（DC72 第 3、6 项）；删除旧扩展并调整 Dockerfile 与 `rust` 包的排除（DC52）。
- **收尾来源（2026-11-06）：** 原产品 `3b3d9c97bc`、handoff `c3c95282bf`、证据复核 `7c5cc2a49efb` 保留；与 main 的 READY 32768 修正整合后，由新实施者（Luna/max）和独立审核者（Astra/high）完成影响核对、必要定向门禁及退出审核，结果见下方退出记录。原基准 W4 租约问题继续由原线处理。
- **kickoff 确认（repository owner，2026-10-31）：** [kickoff](p6-s2a-kickoff.md) 与[审核](p6-s2a-kickoff-review.md)，DC72。
- **已退出（2026-11-06）：** 附注 `p6-s2a-exit` 指向 `53b676a6298d408ccda3a85ee73c7ea223a2311a`。产品候选 `3b037adf4caf33f65e124a34f56f12f42e529641` 已通过 04 五个 Python 包权威 runner（含所需容器旅程）及 06 focused/五包静态检查；Rust 直接沿用原 `3b3d9c97bc`，原第④层逐值差分证据保持有效。最终 H 在原 04 来源工作区的六包闭包比较全部可沿用，RS 镜像身份匹配，独立审核者已给 exit/tag GO；精确来源、最终日志及 SHA 记录在 tag 注释和[收尾审核](p6-s2a-closeout-review.md)。首次 `38ccf8234f` 的失败 runner 保留，不作为任何包来源。原基准 W4 租约故障仍由原线跟踪。后续状态文档不移动此退出 tag，也不冒称为新的门禁来源。
- 验收：五层语料通过；t1–t4 逐值差异 0；1 与 N 线程逐字节相同；旧扩展相关代码、golden、Contract 已删除；新扩展的构建输入检查、`rust` 包排除的去除与 `import_rules` 基线同步核对；权威 runner 与容器门禁（Dockerfile 变化）。
- 真实数据：只做第 ④ 层逐值差分（05；t4 也可在 05，DC50 补充）。

### S2b — 上传侧数据路径与规范表存储

- **准备收口，尚未授权产品开工（2026-11-06）：** [kickoff 设计输入](p6-s2b-kickoff.md) 正在已退出的 S2a 基线上重核消费者、映射与覆盖。容量/M 按 DC84 分步收口，DC63 基准子段继续独立待补；技术稿经独立审核后再由 owner 确认产品实施范围。
- **推进原则更新（DC81，2026-11-05）：** owner 将新开会话推进 S2a 收尾及 S2b 讨论；全量基准由原线继续，不再统一阻塞后续开发。先收口功能、映射、恢复语义与必要资源预算；未交付性能分段明确待补，允许后续小范围定向返工。迭代只做受影响范围验证，完整门禁集中到必要候选，不重复已通过的测量。S2b kickoff 仍须核对，不把本次流程调整表述为所有准备项/性能退出条件已通过。
- **性能指标解释（DC81 补充，2026-11-06）：** 当前性能指标不是不可调整的硬性门槛。W2 或其他纯性能目标未达时，以实测、物理限制和调整影响交 owner 讨论；现有目标、未知项及测量来源如实保留，不自行判为通过或取消取证。具体验收时点仍在 kickoff 中收口；正确性、资源上限、租约及超时造成的业务失败不适用这一性能解释。
- **W2 时点已定（DC83，2026-11-06）：** 功能退出与性能复核分开；30 秒目标及统计口径保留，CT108 可用时补测、最迟 S6 收口，未知不记通过。功能候选仍完成正确性、恢复、资源边界和必要权威/容器门禁；handoff 跟踪待测版本、负责人及返工影响。
- **容量与 W1 时点已定（DC84，2026-11-06）：** kickoff 先依据现有输入和保守估算，映射/固定向量/纯 kernel 先行；writer 完成后校准 IPC，worker 接线前定 M 并核 FULL 峰值，最终候选仍验证资源边界。W1 原则上从 S2b 做诊断测量，若 CT108 至功能 exit 仍无窗口，允许延期、最迟 S6；W3 从 S3 起测，S6 正式取证。阶段诊断、功能验证和正式阈值判定分别记录，不用未知数值放行。
- **设计输入补充（DC76）：** UTC 导出与既有来源/类型由 owner 确认；少数约 100 MB SQL 纳入容量准备。[映射设计候选](p6-s2b-arrow-mapping-design.md)已形成，技术细则待审核；按映射→容量普查→N/M/唯一 Rust 路径与清理→kickoff 收口推进，不改变当前基准范围。
- **容量输入补充（DC77）：** 首版/长期仓库数为 1,000/10,000，年均每仓库 6–12 次提交；单项目 5 版/日为尚未发生的假设压力，500 仓库同日上传为跨仓库极端场景，不默认组合。S2b 先测单位物理成本并参数化外推，区分 head、durable 历史与临时/TTL；不新增规模门禁或 Phase 7 并发/横向扩展实现。

- **容量方案确认（owner，2026-11-04）：** DC77 容量分层、独立突发场景、测量后外推与 Phase 7 扩展方向已确认；尚未指定硬件数量、磁盘规格、N/M 数值或完成时限，不替代整体 kickoff 审核及开工确认。
- 目标：设计 §8。
- 前置：S2a exit；S1c exit（DC65）；上传侧原始表使用方核清，容量/M 的分步校准计划与前期保守预算按 DC84 审核闭合。
- 内容：数据路径合并 kernel；Arrow 列映射 v1；规范表存储（内容地址、IPC、读取校验、BaselineHead 正式引用与 TTL）；N/M 准入、worker 级共享线程池接线与 pyarrow 线程池；直接接入唯一 Rust 生产路径并验证后清理被替代 Python 算法/临时差分入口（DC78；池接线仍按 DC72 第 6 项）；Canonical Storage §5 修订。
- 验收：t1–t4 端到端摘要与基准一致；存储读取校验、Dolt 兜底与冻结产物四种状态的权威测试；计数断言；W1 诊断按 DC84 安排，W3 起测归 S3；权威 runner 与容器门禁。**W2 性能复核与功能 exit 分开**（DC83、设计 §16.1）：30 秒目标保留，CT108 可用时补测、最迟 S6 收口；待补或未达不写 PASS，结果及调整方案交 owner。
- 真实数据：t1–t4 端到端摘要一致；测本阶段相关负载。

### S3 — 比较与逐行记录

- 目标：设计 §9。
- 前置：S2b exit。
- 内容：共用比较内核（standard、keyless、ordered）；逐行记录 Arrow 与 `content_digest`；记录写入改为 pyarrow 由 Arrow batch 写，删除发布后回读（保留读取校验）；风险按 Arrow 分批消费；单次操作内去重（键含规则与版本）；Comparison 与 Risk 的缓存条款修订（设计 §14）；分歧点按现行行为写进 Contract；替换期差分后验证唯一 Rust 路径，删除被替代 Python 算法和重复测试（DC78）。
- 验收：差分（语料、随机、t1–t4）逐字节一致；记录 golden 逐字节一致；去重开关不改结果；W3、W4（含 FULL 一次与 100% 压力档，只报告）测量，W4 中不存在未计入的逐行 Python 转换；权威 runner 与容器门禁。

### S4 — Submit

- 目标：设计 §10。
- 前置：S3 exit。
- 清理：Rust 渲染与存储 diff 接入验证后删除被替代 Python 算法及重复测试（DC78）；DC45 的通用规划器等独立职责继续保留，不按语言盲删。
- 内容：渲染直通；存储 diff 共用内核；用最终渲染器复测 S1a 冻结的阈值与批量规则（须调整时作为例外交 owner）。S1a 终审登记（2026-10-27）：UPDATE、DELETE 分批时每加一行重渲染整批（`_render_limited_mutation_batches`），渲染量随批大小平方增长；整表重建对 parent 每行生成逐键 DELETE，代价随重建表行数放大。t4 未见可测回退，S4 改为按增量累计完整语句字节分批，批次划分与 SQL 字节不变。
- 验收：同一输入的 `replay.sql` 与 S1a 产物逐字节一致；设计 §16.2 的 Submit 计数；S1–S4 完成时间（main 前移）；权威 runner 与容器门禁（Submit Compose 旅程）。

### S5 — History 与跨操作缓存

- 目标：设计 §11。
- 前置：S3、S4 exit。
- 内容：diff/risk 缓存（只缓存纯函数结果，pair 上限在汇总绑定）与 finalize 登记引用；History 按表拼接（完整条件）；Dolt 并发读取（≤ min(N, RS 容量)，503 有界退避，继承取消与截止时间）；H2 冷读验收。
- 验收：设计 §16.3 中 H1、H1-FULL、H1-回填、H2、H2-三节点（只报告）、H3 各场景；计数断言按 §16.2 的条件判定；缓存只缓存纯函数结果的权威测试；权威 runner 与容器门禁。

### S6 — 收尾

- **待决提案：** DC74 草案建议在本阶段随现有旅程完成 BE-c（t4/2× t4 的完整 bundle 体积），整包下载另列只报告。未确认前不改变既定验收矩阵。

- 目标：设计 §12。
- 内容：加速曲线定 N；核对各阶段旧算法与临时差分设施已清理（DC78）；按设计 §16.3 验收矩阵完成全部场景取证；存储报告；门禁时长重新剖析；Phase 6 退出。
- 验收：设计 §16.3 全部场景（门槛项达标、只报告项有记录）与 §16.2 全部计数断言；最终提交上完整运行权威 runner（六个包）与容器门禁各一次；Phase 6 退出审核。
- 真实数据：2× t4 全部负载（1 次预热加 3 次测量）与 t1–t4 完整旅程。

### 前端对接前的后端小任务 BE-a / BE-d（安排草案）

- 业务范围依据 `ebb004738330` 的前端 kickoff §5；[任务提示词草案](p6-be-a-d-kickoff.md)待审核和 owner 确认，S2a exit 合入 main 后、FE3 前发出。建议 BE-a 后 BE-d；并行 S2b 时明确文件归属。
- BE-a 删除退回修改状态/动作/事件及基线 schema 约束，并补两创建接口的成功状态 OpenAPI；按 DC75 增加 Workspace 占用指针的一致查询投影及 withdraw_own_submission 权限（含本人 GET review、WITHDRAW 与 replay）。方向由 owner 2026-11-04 确认，详细条款/验收见 [BE-a 设计补充](p6-be-a-design.md)，BE-a kickoff 审核已通过（`fcbfb4c1a0`），非阻塞测试归属建议已采纳，待 owner 实施确认；这包含授权语义变更，不是纯 DTO 小修。BE-d 闭合 Preview/History 的整包 tar 下载并同步旅程工具；不引入 BE-b 导航产物。
- 本行是计划正文，不记录实施审核结果或 exit 状态。两任务验收、真实数据建议和停止规则见草案。

## 3. 路径预算（主要改动面）

| 阶段 | 主要路径 |
| --- | --- |
| S1a | B`capabilities/storage_projection/`（`_digest.py`、`project.py`、`publish.py`、`contracts.py`、`package.py`、`import_replay.py`）、B`capabilities/table_rules/contracts.py`、B`capabilities/mutation_planning/`、B`capabilities/comparison/standard.py` 与 `ordered.py`、B`application/preview_jobs.py`、B`application/history/compare_jobs.py`、B`application/submission/import_builder.py`、B`infrastructure/repository_write/import_publication.py`、B`application/submit_jobs.py`；golden：storage-projection、mutation |
| S1b | `vnext/shared_kernel/src/gateway_shared_kernel/scalar.py`（FLOAT 直接舍入）与 shared-kernel 编码向量 golden、B`capabilities/comparison/`（`row_encoding.py`、`contracts.py`、`artifacts.py`）、B`capabilities/risk_evaluation/`、B`capabilities/surface_assembly/`、B`capabilities/bundle_assembly/`、B`application/pair_pipeline.py`、B`http/orchestration/`（`multipart_stream.py`、`multipart_upload.py`）、B`application/workspace/upload_limits.py`、B`capabilities/table_access/`（参照解析器修复）、B`capabilities/table_rules/`（DC56 规则改动）与 storage-projection 规则集、manifest golden、`vnext/backend/benchmarks/`（合成负载）；control DB 基线 schema（导出缓存 owner）；B`operations/worker_runtime.py`、B`bootstrap/operation_worker.py`（DC61）；`vnext/scripts/build-repository-service-image.sh` 与其测试（DC61） |
| S2a | R`gateway-compute-core/src/table_access/`、R`gateway-compute-python`（复用为新 parser adapter）、R`gateway-compute-python-impl`（删除）、B`capabilities/table_access/`（O2 参照语义修正）、T`support/table_access_sql.py`（test-only 双实现入口）、B`capabilities/canonical_row_hash/`（删除）、`vnext/backend/Dockerfile`、`vnext/scripts/run-tests.sh`（去掉排除）、`vnext/scripts/check-rust-extension-build-input.sh`（核对新扩展）、`vnext/scripts/native_kernel_component.sh`（删除）、T`architecture_baseline.py` 与 `import_rules` 基线 |
| S2b | R`gateway-compute-core/src/`（物化、投影、摘要模块）、B`capabilities/snapshot_materialization/`、B`capabilities/storage_projection/`、B`artifacts/` 与 B`infrastructure/artifact_store/`、control DB 基线 schema（BaselineHead owner）、B`settings.py`（N、M）、B`bootstrap/operation_worker.py`（线程池） |
| S3 | R`gateway-compute-core/src/comparison/`、B`capabilities/comparison/`、B`capabilities/risk_evaluation/`（接口） |
| S4 | R`gateway-compute-core/src/`（渲染）、B`capabilities/mutation_planning/`、B`infrastructure/repository_write/import_publication.py` |
| S5 | B`application/history/`、B`capabilities/comparison/`（缓存接口）、B`application/submission/finalize*.py`、B`infrastructure/repository_read/`（并发与 503 退避）、control DB 基线 schema（缓存 owner） |
| S6 | 唯一生产路径与各阶段旧算法清理核对；测量 runbook |

每阶段 kickoff 时对照当前 HEAD 复核路径预算，偏离先修订设计再开工。

## 4. 测试归属与比例化

按设计 §15：每个不变量一个权威测试 owner；测试按业务行为命名；删除生产机制（旧扩展、Python 生产路径）时同步删除其 mock 与证明探针。Rust 侧：单元测试、proptest（stable）与确定性测试进入 `rust` 包；需要 Python 解释器的测试用 pytest 测已安装的扩展（DC48）。

## 5. 命令草案

2026-11-06 节点补充（DC82）：S2b 日常 Rust/Contract/focused 与小规模 Compose 可在 `ct107-gw-dms-06`；前端静态、单元、构建、截图和 mock e2e 优先在 `ct109-gw-dms-07`。04/06/07 同宿主且 Owner 确认资源宽裕，日常自主并行，不设常规整宿主互斥或向原基准线申请窗口；CT108 正式测量与这些节点物理隔离。下面 05 的调试命令在 06 按本节点占用规则同样适用，06 初始 Cargo jobs/pytest workers 建议 4；真实数据和最终门禁节点不因本补充迁移。具体约束见 AGENTS 与[节点核对报告](p6-node-06-07-readiness.md)。

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

设计 §17 的停止条件（W2 性能复核时点按 DC83 与 S2b 功能退出分开）之外：

其中纯性能指标按 DC81 补充及 DC83 处理：保留本次未达或未知的结果，带实测、物理约束与具体方案交 owner 讨论，不将旧阈值解释为不可调整的永久阻塞；不自动改变目标、运行预算或证据口径。以下执行失败与正确性停止规则不变。

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
- 自 2026-11-04 起（DC73），后端分设两个常设会话：
  - 设计会话 `p6-backend-design`：负责 DC、设计与本计划的修订，以及 kickoff 与实施提示词；
  - 审核会话 `p6-backend-review`：负责 kickoff 审核、代码审核、证据复核、停止复核与 exit 办理。
  - 两会话经 owner 转交，分工与交接面见 DC73。

### 8.3 handoff

每阶段 handoff 至少包含：改动清单与提交；Contract 与 golden 的变化及理由；计数断言与测量结果（节点、HEAD、起止时间、exit code、日志位置）；权威 runner 与容器门禁的逐包结果（运行或沿用、来源 V、来源日志）；真实数据范围与结果；偏差与未决；节点上需要清理的内容。

### 8.4 真实数据与调试取证

沿用 DC30、DC33，按 DC64 修订：调试期间只跑 focused 测试与出问题的那一段真实数据；收敛后先在节点 05 做门禁前预检（[P5 执行计划 §8.9](p5-arch-closure-execution-plan.md)），交代码候选审核；代码通过后，在最终候选上完整运行权威 runner 一次、运行真实数据一次作为证据；证据之后的修订按受影响步骤重跑（DC64 第 2 项），不适用时整档重跑；真实数据范围在 kickoff 写明、退出前由 owner 确认。真实数据不进 Git（DC22）；含真实数据的中间产物放在节点 worktree 外，阶段结束后经 owner 授权清理。

### 8.5 提示词与审核报告模板

沿用 [P5 执行计划 §8.7、§8.8](p5-arch-closure-execution-plan.md) 的结构；Phase 6 的提示词另须写明：节点分工与空闲确认、短期分支与 bundle 同步、DC78 的唯一生产路径与旧算法清理约定、不改写临时参照实现（替换期差分）、不绕过 auto-mode 分类器的拒绝。
