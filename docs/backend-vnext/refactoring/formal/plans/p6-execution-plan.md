# Phase 6 执行计划

状态：**DRAFT r1 — 待独立文档审核；实现未授权**

日期：2026-10-26（r1）

Owner：Backend vNext Architecture

入口：[S0 Owner 决议记录](p6-s0-owner-decisions.md) → [详细设计](p6-design.md) → 本文

B=`vnext/backend/src/gateway_backend/`，T=`vnext/backend/tests/`，R=`vnext/rust/`。本文写未来的步骤与期望证据；实际结果写入各阶段 handoff。

## 1. 执行形态

```text
S0  决议（DC37–DC54）、前置验证（已完成）、本设计与计划、独立文档审核、kickoff 小修、keyless 自然键评估
 -> S1a 摘要与存储 Contract（DC39、DC45 表级跳过与阈值）+ worker step 归因
 -> S1b 业务语义 Contract（DC40、DC41、DC49、参照解析器修复与语义定稿）+ 合成负载
 -> 重建对照基准（Python）
 -> S2a SQL 解析器（Rust，flag 之后）+ 删除旧扩展
 -> S2b 上传侧数据路径与规范表存储（切换生产）
 -> S3  比较与逐行记录（Rust）
 -> S4  Submit 渲染直通
 -> S5  History 与跨操作缓存
 -> S6  收尾与 Phase 6 退出
```

阶段顺序依据见设计 §4–§12 与 DC50：先改 Contract、再改性能；每类 golden 只改一次；表摘要 → 解析器与存储 → 比较 → Submit → History。

每个实施阶段结束交独立审核，未通过不进入下一阶段。前置验证类工作（原型、测量）不做独立审核，结果在设计审核中复核（DC48 讨论）。

## 2. 阶段定义

### S0 — 剩余工作

- **独立文档审核：** 审核对象为本文、详细设计、决议记录 DC37–DC54 与 implementation-stages §9/§10 的改写；必须复核的代码事实见设计 §2.2（Submit 全量重写、Preview 全量物化基线、bundle 不含整表、上传 60 s 总时限、uv 不重建扩展）。审核报告模板沿用 [P5 执行计划 §8.8](p5-arch-closure-execution-plan.md)。
- **kickoff 小修**（不单独审核，随 S1a 审核）：`uv-consume.sh` 的 EXIT trap（`mktemp` 锁快照残留）；测试留下的 `repository-import-*.sqlite3-shm/-wal`；三项文档整理（讨论稿 §12）；RS defunct `dolt` 进程：交 RS owner 排查，修复若涉及 Dockerfile/Compose 则为强制重建项，可并入 S1a。
- **业务评估：** 重要 keyless 表是否定义自然键，S1a kickoff 之前由 owner 给出；结论可能影响 DC39 与 S3 对 keyless 的处理。
- **接受：** owner 接受文档后给出实现授权。

### S1a — 摘要与存储 Contract

- 目标：设计 §4。
- 前置：S0 接受；keyless 自然键评估已给出。
- 内容：
  1. 表摘要统一（设计 §4.1）：manifest 内容摘要改为 `raw_content_digest`；`STORAGE_PROJECTION_VERSION = "3"`；删除 `ordering_digest`；去掉重复计算。
  2. Preview 与 History 的结构性过滤（§4.2），含未变化 ordered 表不读不比，`before/current_ordered_digest` 改取自表摘要。
  3. Submit 表级跳过与 `ADAPTIVE_PATCH`（§4.3）：T1 冻结 policy、prepare checkpoint 绑定 parent manifest digest、有序表资格、阈值 1,000 行 / 1%；阈值复测。
  4. Contract 修订（§4.5）与 golden（storage-projection、mutation、包）。
  5. worker step 归因（§4.4），写入 handoff。
- 验收：
  - 计数断言（设计 §16.2 第 1、2 行）在 focused 测试与 t4 旅程中成立；
  - 新旧路径在 t4 v2 上的 Dolt 表哈希相同；
  - 规范状态摘要、snapshot 与 bundle digest、HTTP DTO 不变（golden 中只有 manifest digest 及其传播值变化）；
  - 权威 runner 六个包通过；容器门禁（Submit 路径与镜像内代码变化）。
- 真实数据：t1–t4 完整旅程（t1–t3 在 05，t4 在 ct108），业务结果按新 Contract 核对。

### S1b — 业务语义 Contract

- 目标：设计 §5。
- 前置：S1a exit。
- 内容：
  1. 只增列（§5.1）；
  2. bundle 补齐整表与导出缓存（§5.2）；整表新增或删除改为整表浏览（§5.3）；
  3. 慢速上传：空闲超时、总上限、新错误码、受理移到线程池（§5.4）；
  4. 参照解析器的缺陷修复与语义定稿（§5.5；kickoff 时 owner 逐项确认）；
  5. 合成 2× t4 与 W4 生成工具、测量 runbook（§5.6）；
  6. Contract 修订（§5.7）与 golden。
- 验收：
  - 只增列的表不降级、无风险；Submit 仍生成版本；
  - Preview 与 History 的 bundle 含全部表，重复导出命中导出缓存；
  - 上传在低速下不因总时长失败、空闲超时返回新错误码；
  - 参照解析器对 V6 列出的输入给出确定诊断，不抛未捕获异常；
  - 权威 runner 与容器门禁。
- 真实数据：t1–t4 完整旅程；t3 覆盖只增列（即原 testdata1）。

### 重建对照基准

- 前置：S1b exit。
- 内容：设计 §6；记录写入基准 handoff，作为 S2a–S6 的对照。
- 节点：`ct108-gw-dms` 独占。

### S2a — SQL 解析器

- 目标：设计 §7。
- 前置：S1b exit（语义已定稿）。
- 内容：补齐诊断与语料；PyO3 adapter；worker 级共享线程池；feature flag 之后接入（只差分）；删除旧扩展并调整 Dockerfile 与 `rust` 包的排除（DC52）。
- 验收：五层语料通过；t1–t4 逐值差异 0；1 与 N 线程逐字节相同；旧扩展相关代码、golden、Contract 已删除；`import_rules` 基线相应更新；权威 runner 与容器门禁（Dockerfile 变化）。
- 真实数据：只做第 ④ 层逐值差分（05；t4 也可在 05，DC50 补充）。

### S2b — 上传侧数据路径与规范表存储

- 目标：设计 §8。
- 前置：S2a exit；设计核对项（上传侧原始表的使用方、磁盘估算）已完成。
- 内容：数据路径合并 kernel；Arrow 列映射 v1；规范表存储（内容地址、IPC、读取校验、BaselineHead 正式引用与 TTL）；N/M 准入与 pyarrow 线程池；feature flag 切换生产；Canonical Storage §5 修订。
- 验收：t1–t4 端到端摘要与基准一致；存储的权威测试；计数断言；W1–W3 测量（ct108）；权威 runner 与容器门禁。
- 真实数据：t1–t4 端到端摘要一致；测本阶段相关负载。

### S3 — 比较与逐行记录

- 目标：设计 §9。
- 前置：S2b exit。
- 内容：共用比较内核（standard、keyless、ordered）；逐行记录 Arrow 与 `content_digest`；记录写入改为 pyarrow 由 Arrow batch 写；单次操作内去重；分歧点写进 Contract；feature flag 接入。
- 验收：差分（语料、随机、t1–t4）逐字节一致；记录 golden 逐字节一致；去重开关不改结果；W3、W4 测量；权威 runner 与容器门禁。

### S4 — Submit

- 目标：设计 §10。
- 前置：S3 exit。
- 内容：渲染直通；存储 diff 共用内核；阈值定稿。
- 验收：`replay.sql` 与 S1a 产物逐字节一致；计数断言；S1–S4 完成时间；权威 runner 与容器门禁（Submit Compose 旅程）。

### S5 — History 与跨操作缓存

- 目标：设计 §11。
- 前置：S3、S4 exit。
- 内容：diff/risk 缓存与 finalize 登记引用；History 按表拼接；Dolt 并发读取（≤ RS 容量，503 退避）；H2 冷读验收。
- 验收：H1–H3 计数断言与门槛；缓存只缓存纯函数结果的权威测试；权威 runner 与容器门禁。

### S6 — 收尾

- 目标：设计 §12。
- 内容：加速曲线定 N；删除生产 feature flag；2× t4 全部负载取证（W1–W4、H1–H3、S1–S4）；存储报告；门禁时长重新剖析；Phase 6 退出。
- 验收：设计 §1.1 全部门槛与 §16.2 全部计数断言；Phase 6 退出审核。
- 真实数据：2× t4 全部负载（1 次预热加 3 次测量）与 t1–t4 完整旅程。

## 3. 路径预算（主要改动面）

| 阶段 | 主要路径 |
| --- | --- |
| S1a | B`capabilities/storage_projection/`（`_digest.py`、`project.py`、`publish.py`、`contracts.py`、`import_replay.py`）、B`capabilities/table_rules/contracts.py`、B`capabilities/mutation_planning/`、B`capabilities/comparison/standard.py` 与 `ordered.py`、B`application/preview_jobs.py`、B`application/history/compare_jobs.py`、B`application/submission/import_builder.py`、B`infrastructure/repository_write/import_publication.py`、B`application/submit_jobs.py`；golden：storage-projection、mutation |
| S1b | B`capabilities/comparison/`（`row_encoding.py`、`contracts.py`、`artifacts.py`）、B`capabilities/risk_evaluation/`、B`capabilities/surface_assembly/`、B`capabilities/bundle_assembly/`、B`application/pair_pipeline.py`、B`http/orchestration/`（`multipart_stream.py`、`multipart_upload.py`）、B`application/workspace/upload_limits.py`、B`capabilities/table_access/`（参照解析器修复）、`vnext/backend/benchmarks/`（合成负载）；control DB 基线 schema（导出缓存 owner） |
| S2a | R`gateway-compute-core/src/table_access/`、R`gateway-compute-python*`（新 adapter，删除旧 crate 内容）、B`capabilities/table_access/`（flag 接入）、B`capabilities/canonical_row_hash/`（删除）、`vnext/backend/Dockerfile`、`vnext/scripts/run-tests.sh`（去掉排除）、`vnext/scripts/native_kernel_component.sh`（删除） |
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

设计 §17 的停止条件之外：

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

- 每个实施阶段：实施者在新对话中按提示词完成，交 handoff；独立审核者在只读 detached worktree 中审核，有问题修复后复审；通过后打 tag、合入、推送（经授权）。
- 门禁基础设施改动（如 DC48 类）做一轮轻量审核；原型与测量不做独立审核，结果作为设计输入。
- 同一节点同一时间只给一个会话做测量或门禁；使用前确认空闲。

### 8.3 handoff

每阶段 handoff 至少包含：改动清单与提交；Contract 与 golden 的变化及理由；计数断言与测量结果（节点、HEAD、起止时间、exit code、日志位置）；权威 runner 与容器门禁的逐包结果（运行或沿用、来源 V、来源日志）；真实数据范围与结果；偏差与未决；节点上需要清理的内容。

### 8.4 真实数据与调试取证

沿用 DC30、DC33：调试期间只跑 focused 测试与出问题的那一段真实数据；收敛后在最终门禁提交上完整运行权威 runner 一次、运行真实数据一次作为证据；真实数据范围在 kickoff 写明、退出前由 owner 确认。真实数据不进 Git（DC22）；含真实数据的中间产物放在节点 worktree 外，阶段结束后经 owner 授权清理。

### 8.5 提示词与审核报告模板

沿用 [P5 执行计划 §8.7、§8.8](p5-arch-closure-execution-plan.md) 的结构；Phase 6 的提示词另须写明：节点分工与空闲确认、短期分支与 bundle 同步、feature flag 约定、不改写参照实现（差分阶段）、不绕过 auto-mode 分类器的拒绝。
