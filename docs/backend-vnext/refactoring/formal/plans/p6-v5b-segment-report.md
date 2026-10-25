# Phase 6 前置验证 V5b：未归因耗时分段补测

日期：2026-10-25
范围：测量与分析；没有修改产品代码。

## 结论摘要

- 对 t4 v1 基线 commit 调用完整 `materialize_repository_ref` 路径，含独立 artifact 回读，得到 **293.490 s wall / 234.422 s thread CPU**。它解释了 V5 重传、v2 Preview `materialize_inputs` 比首个 v1 多出的 368–370 s 中约 79–80%；仍有约 75–76 s 未由本次独立调用重现。
- v1 Preview 的完整 pair、records closure、bundle 和回读验证合计 **643.980 s wall / 620.552 s CPU**；v2 Preview 为 **43.933 s / 41.795 s**。两者 CPU 差 **578.757 s**，与 V5 `assemble_preview` 的 v1-v2 差 **579.692 s** 相差不到 1 s。逐行 records closure 生成、全量读回与 bundle 处理解释了绝大部分 v1 的额外耗时。
- v2 的 artifact 读写、bundle 校验与 records closure 回读只有数秒，不能解释 V5 重传/v2 `assemble_preview` 高于 S5 capability 的约 100 s 固定差额。
- Submit build input 解析为 **67.202 s / 67.035 s CPU**；Submit checkpoint 序列化、读回与 pin 合计 **0.037 s / 0.009 s CPU**。两者解释 V5 `prepare_import` 超出 S5 adapter outer 的约 103.140 s 中约 67.239 s，另有约 35.901 s 未归因。

## 运行环境与证据位置

| 项目 | 值 |
| --- | --- |
| 节点 | SSH 别名 `ct108-gw-dms`，hostname `gw-dms-test` |
| 成功运行 HEAD | `5993bbb9d5b6d7036faf68b44a7c03febdd2abff`（起止相同） |
| 起止时间 | 2026-10-25 12:27:52–13:09:44 UTC |
| runner exit code | 0 |
| 原始运行日志 | `/home/dev/gdds-p6-logs/v5b/v5b-segments-final-retry2-20261025.log`，0600 |
| 分段 JSON | `/home/dev/gdds-p6-logs/v5b/segments-final-retry2.json`，0600 |
| artifact scratch | `/home/dev/gdds-p6-logs/v5b/segment-artifacts-20261025-final-retry2/`，0700 |
| 保留的 Compose project | `p6v5b-t4-20261025` |

这是 [V5 step 级归因报告](p6-v5-attribution-report.md) 后续的四段补测。报告与仓库中没有原始测量 JSON、日志、SQL、行值、摘要值、Repository ID 或 Dolt commit ID。测量文件与含真实表 artifact 的 scratch 都留在节点上，未清理。

成功运行前，t4 v1 Submit 栈仍由 V5 `--keep-stack` 保留；测量连接该栈的 Repository Service，以生产 HTTP/逐表 Arrow 读取路径读取 312 张表。测量函数在同一节点以单线程直接调用；wall 用 `perf_counter`，CPU 用 `thread_time`。artifact I/O 使用生产 `LocalArtifactStore` 实现，但写入本次新建的节点外私有 scratch。Repository Service 与文件系统缓存均不是冷启动条件，本报告不把这些数据当冷读基准。

**只有最后一次运行作为证据。** 早先的 harness 尝试分别遇到命令路径、参数签名和 Repository Service endpoint 问题；使用正确 endpoint 的第一次长运行在空基线 artifact 收集处触发 harness 自身校验错误。它没有产品失败。之后仅修改 benchmark 工具：对空基线中没有 artifact 的表不生成 pin ref，当前快照仍严格要求 artifact；并在 v1 bundle 完成后先写 checkpoint。最后的 retry2 在上述 HEAD 上通过。所有失败日志与 scratch 均保留。

## A. t4 v1 基线 commit 全量物化

这段先从 v1 上传侧建立 canonical binding，再经 `materialize_repository_ref` 读取完整 v1 commit，并把规范表 materialize 到本地 artifact store。下表的主调用总量不含后续显式 artifact 回读；“合计含回读”把这项单独增加。

| 子段 | Wall (s) | Thread CPU (s) | 计数与说明 |
| --- | ---: | ---: | --- |
| Repository Service catalog、逐表 open/stream、close | 56.902 | 4.622 | 312 张表、246,794 行；逐表 open+stream wall 中位数 0.118 s，p95 0.497 s，最大 8.946 s（`device_st`，54,150 行） |
| Python 物化与 digest 残余 | 229.110 | 228.858 | `materialize_repository_ref` inclusive 减去实测 RS 与 ArtifactStore 调用；包含逐表物化/投影工作 |
| ArtifactStore 写入 | 6.994 | 0.459 | 624 次写入 |
| 物化过程内的 ArtifactStore 读取 | 0.340 | 0.340 | 1,248 次读取 |
| **`materialize_repository_ref` 主调用** | **293.346** | **234.278** | 312 张表、246,794 行 |
| 显式全量 artifact 回读校验 | 0.143 | 0.143 | 624 个 artifact |
| **主调用加回读校验** | **293.490** | **234.422** | 对应下文与 V5 的完整路径比较 |

逐表 open+stream 的 wall 合计约 56.849 s，接近 RS 读取阶段总 wall 56.902 s；客户端线程在 RS 请求调用中的 CPU 为 4.622 s（不是远端 RS 进程 CPU）。wall 与客户端 CPU 的差距说明多数时间不在调用方 Python 计算中，但本次没有单独采集远端 RS/Dolt 进程的 CPU。物化本身则主要是约 229 s 的单线程 Python 计算。

### 与 V5 `materialize_inputs` 对照

| V5 step | V5 wall (s) | 相对 v1 的增加 (s) | V5b A 含回读 (s) | 未由 A 重现 (s) |
| --- | ---: | ---: | ---: | ---: |
| v1 Preview | 931.434 | — | 293.490 | — |
| v1 重传 Preview（changed=0） | 1,299.601 | 368.167 | 293.490 | 74.678 |
| v2 Preview（changed=26） | 1,301.010 | 369.576 | 293.490 | 76.086 |

因此 V5 重传/v2 的约 370 s 增量**不等于**本次完整基线物化路径：A 解释约 79–80%，另约 75 s 仍在 V5 worker step 边界内未被独立调用重现。History 的 V5 `materialize_inputs` 为 730.835 s，按两个 commit 平均约 365.4 s/commit，也比本次 A 多约 71.9 s/commit；两者方向一致，表明完整 worker step 还有本测量未覆盖的成本。没有产品插桩，不能把残差进一步归到特定内部调用。

## 输入包物化准备（与 A、B 分开）

为了给 Preview pair 提供实际 canonical input，测量工具还调用了 S5 使用的上传侧 materialization。它不是 A 的基线 commit 物化，也不是 B 的 bundle 阶段。以下是 recorder 的逐段数据；`materialization_artifact_write` 是这些阶段内 ArtifactStore.put 调用的子计数，不应再加到阶段合计。

| 上传侧阶段 | v1 wall / CPU (s) | v2 wall / CPU (s) |
| --- | ---: | ---: |
| source package staging | 0.673 / 0.437 | 0.657 / 0.422 |
| SQL parse | 140.488 / 140.469 | 140.429 / 140.410 |
| XML parse | 0.060 / 0.060 | 0.061 / 0.061 |
| business materialization | 209.252 / 209.233 | 210.320 / 210.291 |
| canonical projection and table digest | 217.416 / 217.394 | 216.657 / 216.638 |
| canonical artifact write（recorded stage 1） | 163.319 / 156.519 | 160.924 / 154.042 |
| canonical artifact write（recorded stage 2） | 0.107 / 0.096 | 0.106 / 0.095 |
| materialization ArtifactStore.put 子计数（嵌套，不加总） | 7.317 / 0.552 | 7.406 / 0.549 |
| 阶段 wall/CPU 合计（不计嵌套子计数） | **731.315 / 724.209** | **729.154 / 721.959** |

v1 为 312 张表、246,794 行；v2 为 312 张表、246,874 行。核心阶段耗时几乎相同，与 S5 上传侧 materialization capability 的 v1 724.955 s、v2 729.743 s 接近。这说明变化量较小不会跳过全量 SQL parse、business materialization 与 canonical projection；该工作仍依赖 Phase 6 上传侧数据路径优化。

## B. 完整 Preview pair、records closure 与 bundle

B 直接调用生产 Preview pair pipeline、records closure 生成、`assemble_bundle`、bundle 校验和 records closure 全量回读。v1 基线由生产空 SQL materialization 生成，v2 基线是已测量的 v1 commit。pair pipeline 已包含 records closure 生成；下表把该子阶段单列用于归因，但计算总量时不重复相加。ArtifactStore I/O 数值也是外层 stage 的嵌套计数。

| B 子段 | v1 wall / CPU (s) | v2 wall / CPU (s) | 备注 |
| --- | ---: | ---: | --- |
| pair pipeline（含 records closure） | 504.544 / 492.765 | 41.753 / 40.693 | v1/v2 当前表均 312 张 |
| └ records closure generation（上行的子阶段） | 317.878 / 312.789 | 1.073 / 0.307 | v1 223 closure entries、250,471 条记录；v2 36 entries、168 条记录 |
| comparison capability | 148.916 / 148.886 | 39.790 / 39.786 | 原有 S5 capability 已覆盖此类比较成本 |
| risk evaluation | 37.019 / 30.371 | 0.336 / 0.057 | 原有 S5 capability 已覆盖此类风险成本 |
| surface artifact closure generation | 0.012 / 0.012 | 0.002 / 0.002 |  |
| `assemble_bundle` | 42.881 / 31.530 | 1.985 / 0.911 | v1/v2 bundle artifact 分别 1,073 / 101 个 |
| bundle explicit readback validation | 1.037 / 1.037 | 0.095 / 0.095 |  |
| records closure full readback validation | 95.506 / 95.207 | 0.098 / 0.094 | v1 全读 250,471 条记录；v2 全读 168 条 |
| **B 完整计时（不重复加子阶段与 I/O 计数）** | **643.980 / 620.552** | **43.933 / 41.795** | pair + surface closure + bundle + 两项回读/校验 |

ArtifactStore 调用计数和累计调用时间如下。读写计时在对应 pair/bundle 外层阶段内，不能作为额外时长叠加。

| ArtifactStore 范围 | v1 次数与 wall (s) | v2 次数与 wall (s) |
| --- | ---: | ---: |
| pair pipeline reads / writes | 2,143 / 1,073；read 0.650，write 12.228 | 199 / 101；read 0.052，write 1.116 |
| bundle assembly reads / writes | 5,992 / 1,075；read 1.734，write 12.070 | 534 / 103；read 0.128，write 1.137 |

v1-v2 的 B 完整 wall 差为 600.047 s；thread CPU 差为 **578.757 s**。V5 `assemble_preview` wall 差为 723.714−144.022 = **579.692 s**。CPU 增量与 V5 step wall 增量只差 0.935 s；B wall 增量比 V5 多 20.355 s，边界/本地 artifact I/O 存在约 3.5% 的差异。

按 V5b 的 B 细分，records closure generation 增量为 316.805 s，全量 records closure 回读增量为 95.408 s，`assemble_bundle` 增量为 40.896 s，显式 bundle 校验增量为 0.941 s。合计约 **454.2 s**，约为 V5 约 580 s v1 assemble 差额的 78%；这是 S5 原 capability 测量未覆盖的逐行记录生成、闭包读回与 bundle work。其余 comparison planning/comparison/risk/surface 能力差约 145.9 s，接近 S5 已测能力差（176.255−39.598 = 136.657 s）。所以 v1 的额外开销主要来自逐行 `ROW_ADDED` closure 路径，而不是隐藏的单纯 bundle 容器序列化。

### 固定约 100 s assemble 差额

对 v2，完整 B 为 43.933 s，其中 comparison/planning/risk/surface capability 合计 40.528 s；剩余 records closure、bundle、ArtifactStore I/O 与两类回读/校验合计只有 **3.405 s**。S5 v2 `assemble_preview` 为 144.022 s，S5 Preview capability 为 39.598 s，差 104.424 s。B 中 measured artifact reads/writes 与显式回读都不能解释这约 100 s；它仍是 worker assemble step 的未归因固定成本。v1 的全 records closure readback 是约 95.5 s，但它随 250,471 条记录出现，不是 v2 的固定成本。

## C. Submit prepare build input 解析

C 使用 v2 ready closure 与冻结 canonical table artifacts，直接计时 ready closure 加载/验证、frozen binding 解析、parent 表名查询、manifest 载入，以及逐表 artifact open/verify 和 keyed row decode。

| C 子段 | Wall (s) | Thread CPU (s) | 计数 |
| --- | ---: | ---: | --- |
| prepare Preview ready closure | 0.377 | 0.365 |  |
| load ready closure and verify refs | 0.381 | 0.381 | 1,352 次 artifact reads，closure 包含 1,351 个 refs |
| publish frozen canonical table-set closure | 0.030 | 0.019 |  |
| resolve frozen canonical snapshot bindings | 0.222 | 0.222 | 314 次 artifact reads |
| query parent commit table names | 0.033 | 0.018 | 312 个 parent table names；移除表 0 |
| load frozen canonical manifest | 0.046 | 0.046 | 1 次 artifact read |
| read/verify frozen rows table by table | 66.113 | 65.984 | 312 张表、246,874 行；artifact open/verify 33.782 s，keyed row decode 32.331 s |
| **C 合计** | **67.202** | **67.035** | 312 张冻结表全部读取并校验 |

逐表 open/verify wall 中位数 0.0029 s、p95 0.471 s、最大 13.245 s；keyed row decode 中位数 0.00065 s、p95 0.465 s、最大 14.290 s。读取与校验的 wall/CPU 几乎相同，主要是单线程处理，不是等待 parent name query。

## D. Preview 与 Submit checkpoint 序列化、读回与 pin

| D 侧 | serialize/verify/publish wall / CPU (s) | checkpoint readback wall / CPU (s) | pin transaction wall / CPU (s) | pins |
| --- | ---: | ---: | ---: | ---: |
| Preview | 0.0113 / 0.0009 | 0.0005 / 0.0005 | 0.0474 / 0.0293 | 1,702 |
| Submit | 0.0112 / 0.0009 | 0.0006 / 0.0006 | 0.0251 / 0.0075 | 1,355 |

D 使用生产 checkpoint prepare/readback 和 pin API，以及本次测量 scratch 下的新 control DB；没有运行完整 worker step 的控制流。Preview 三个子段合计为 0.0592 s wall / 0.0307 s CPU；Submit 合计为 0.0369 s / 0.0089 s。Preview assemble-state artifact 与 ready closure 的准备在 D 计时前完成，没有计入这 0.0592 s；C 中以 v2 refs 测得相邻的 ready closure 准备/读回为 0.377/0.381 s。因而 D 的 Preview 数值只表示 checkpoint envelope、读回与 pin 的耗时下界，不代表整个 worker checkpoint 准备流程。

### 与 V5 Submit prepare 对照

V5 `prepare_import` step 为 477.120 s；S5 prepare adapter outer 为 373.980 s，差 103.140 s。C 加 Submit D 为 67.239 s，约解释 65%；其中约 66.1 s 是逐表打开、校验与读取冻结 canonical rows。checkpoint 序列化与 pin 只有约 0.037 s，并非百秒项。**仍有约 35.901 s 未由 C/D 解释**，本次没有测 Submit 的 mutation planning/render 或完整 worker prepare orchestration；不能将残差强行归到其中某一个函数。

## 对 Phase 6 设计的含义与测量边界

- **DC39 / S1a：** V5b 实测基线 commit 全量 materialize 含读回约 293.5 s。只读变化表可以避免对未变化的基线表做这段全量读取/物化；但 V5 worker 中仍有约 75 s 残差，S1a 后的 end-to-end 对照应继续量出 operation wall，不能只用本次能力调用替代。
- **DC41 / S1b：** v1 的 250,471 条逐行 records closure 生成约 317.9 s，之后全量读回约 95.5 s；表级导出/closure 设计可避免这两项按每行构造和回读的成本。v1-v2 `assemble_bundle` 差约 40.9 s。D9/B9 的整表打包与导出缓存针对重复整表读写；需要在新实现中确认 bundle 仍完整验证，但不重复解码整份逐行 closure。
- **D10 / S4：** 仅写变化表减少 Dolt mutation/replay，不会自动消除 C 中约 66 s 的冻结表读取与校验，也不会消除完整上传侧解析/投影。prepare 的约 36 s 残差仍需在 worker 端到端新路径复核。
- **checkpoint/pin：** D 的实测总成本低于 0.1 s；不应把它当成当前 100 s assemble 或 Submit 缺口的主要优化目标。
- **尚未解释的差额：** 基线物化约 75 s、v2/retransmit assemble 固定约 100 s、Submit prepare 约 36 s。按 owner 决议没有产品插桩；当前直接函数测量无法拆开 worker context、step orchestration 和 artifact 生命周期管理中的边界差异。应在 S1/S2 重建基准后比较完整 worker step，若仍影响设计再由 owner 决定是否需要插桩。

完整 worker `materialize_inputs`、`assemble_preview` 和 `prepare_import` 不是本工具可独立调用的能力函数：它们依赖 operation/step 上下文、worker 控制流及 step state 生命周期。V5 提供其 end-to-end step wall；V5b 仅对可以直接调用的生产 capability/application 函数计时，并把 records closure generation、ArtifactStore 调用、读回校验、parent names、checkpoint 与 pin 单独计时。没有运行产品代码之外的伪 worker，也没有添加产品插桩。

## 工具改动与验证

只改 `vnext/backend/benchmarks/s5_v5b_segment_measurement.py`，没有产品代码改动。工具提交（均在 main，未推送）：

- `722a5e4` 初始 V5b 分段工具。
- `cd21d28` 修正 Repository read metrics 调用签名，并把 v2 包准备移到 v1 基线物化之后。
- `30e386d` 要求显式 Repository Service endpoint，避免误连 host 8000。
- `5993bbb` 空基线表无 artifact 时跳过 pin ref 收集；严格验证当前快照 artifact，并在 v1 bundle 后 checkpoint。

最后一次工具改动后运行 backend `ruff check benchmarks/s5_v5b_segment_measurement.py` 与 backend `mypy`，均通过（mypy 486 个 source files）。没有运行测试；没有改 Phase 6 讨论稿、决议记录或 implementation-stages。

## 节点上待 owner 清理的内容

**本任务没有删除文件、分支/ref，也没有拆除 Compose。** owner 处理以下保留项：

- `ct108-gw-dms`：Compose project `p6v5b-t4-20261025`（含 control DB、Repository Service Dolt 数据与容器卷）；t4 run `/home/dev/gateway-real-dumps/runs/p6v5b-t4-20261025/`（state 与 secrets）；`/home/dev/gateway-real-dumps/` 中本旅程准备的数据。
- `ct108-gw-dms`：`/home/dev/gdds-p6-logs/v5b/` 下的成功/失败日志、JSON、scratch、launcher 与上传的 Git bundle；此前失败的 partial scratch 包括 `segment-artifacts-20261025/`、`segment-artifacts-20261025-retry1/`、`segment-artifacts-20261025-final/`。scratch 含真实数据生成的 artifact。
- `ct108-gw-dms`：V7 报告留待 V5b 后清理的 `/home/dev/gdds-p6-v7/`，包括复制的 Repository Service 仓库、token、生成 SQL 与一次性脚本。
- `ct108-gw-dms-05`：V8 报告中的 `/home/dev/gdds-p6-logs/v8/` 运行证据，以及 remote ref `refs/remotes/p6-local/main`；owner 已核对 Compose/Dolt/8000 端口无残留。该节点另有 V6 会话，不在本任务中处理。
- 开发主机：`/tmp/p6-v5b-722a5e4.bundle`、`/tmp/p6-v5b-cd21d283.bundle`、`/tmp/p6-v5b-30e386d8.bundle`、`/tmp/p6-v5b-5993bbb9.bundle`、`/tmp/run-p6-v5b-retry2.py`；以及 V8 证据 `/tmp/p6-v8-phases-current.tsv`、`/tmp/p6-v8-components.jsonl`、`/tmp/p6-v8-phases.tsv`、`/tmp/gdds-p6-v8-current-main.bundle`。
- `ct108-gw-dms-05`：V8 上传的 `/home/dev/gdds-p6-v8-current-main.bundle`。
- `ct108-gw-dms-04`：本次 V5b/V7/V8 工作没有已知遗留项。
