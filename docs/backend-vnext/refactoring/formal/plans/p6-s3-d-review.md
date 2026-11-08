# Phase 6 S3 D 独立审核

**当前结论：D CHANGES；Owner 已恢复新候选执行通道。** 本人是 S3 D 的同一独立审核者。`f000e5b075408455a35e8ae3dededc28036c73c6` 的静态问题与 06 Rust fmt 失败保留原状；`5c47795062937a8db0315640a95ab763d2c2c8ab` 的首轮集中修订问题见 §3。新增固定产品候选 `1c25ea68e713fef8718ea499592628dc035a7e94` 仍有 §6 的 reader 可用性及可选 Risk key M finding，且无此候选的编译、功能或容器原件。此结论不是 D GO、S3 GO 或对 C 的重新审批。

## 1. 审核对象与边界

设计 `d49bb126b664af4b09097aee1a6f0b1bf58c9496`、kickoff 复审 `83ba4979044179256aa8c3d5d1d7b3424e648884` §5 已固定；A/B/C 的既有独审 GO 不重开。本人以仓库 AGENTS、testing conventions、比例化保障与 Rust 安全性能政策 v7、S3 design/kickoff/A–C handoff/review，以及 Comparison、Ordered Diff、Risk、Comparison Bundle/Surface、Snapshot Table Access、Shared Canonical Encoding、Storage/Repository Boundary、Operation Lifecycle 和 Performance owning Contract 为依据。

产品只读审核分别在 clean detached worktree `/home/dev/gdds-s3-d-review-f000e5b075`、`/home/dev/gdds-s3-d-review-5c477950` 和 `/home/dev/gdds-s3-d-review-1c25ea68` 进行，固定 HEAD、`legacy/` 链接和 worktree clean 已核。main 上与固定 SHA 无关的后续个人 WIP 或并行文档不纳入本轮产品结论。审核工作树和开发主机未运行编译、lint、测试、容器或性能测量；唯一测试者为 `/root/s3_d_test`。

本节目标是 Preview/History 共用 pair pipeline 的唯一 Rust compare + Arrow records 路由、facts 原序的 Risk 必要列、FULL 已知用途的 operation 内去重、同一 N1/M24 GiB/取消/截止与 closure 语义，并从 W3/W4 开始诊断。保留小元数据、replacement 和独立的 Submit mutation planner 等 consumer；E 才移除旧算法与临时 probe。D 不得留 Python 比较 fallback 或部署开关。

## 2. f000 首固定检查点与原始结果

本人对 f000 静态初审给出 CHANGES，已精确交原实施者同一职责内修复。核心问题包括：production 直接调用 codec FFI 重编码整表 IPC 而非借 C Arrow reader；keyless `UPDATE_ONLY` 状态/content 与 key transition 条件偏离旧控制流；ordered unchanged 快路径错误要求 before provenance；Python 小 metadata、Risk 事实投影、cache key/owner 和 Surface/Parquet 输出的 M 账不完整；Risk 事件重放须在当前额度、过滤、时钟、取消、deadline 和 closure 下执行；Composite 派生表须限定既有有界转换。f000 是第一轮实质审核，不因称为 checkpoint 而从同根修订次数中删除。

唯一测试者在 06 对 clean f000 只运行已审 Rust fmt→clippy 稿。`cargo fmt --all --check` 于 03:36:30Z 原始 exit1，`comparison_records.rs` 有格式差异；clippy 未启动，亦无 Rust test、backend focused、Compose 或 D 当前镜像结果。起止 HEAD=f000、六锁无漂，节点本人 marker 于 03:36:56Z 释放。原始 run 本地副本 `logs/remote-run-focused.log` SHA256=`6bd909e6ceeca3b168a078b0544c4a3e276be380de6c5895543ecc5a7a7a483c`；本轮不能记为编译或功能通过。

## 3. 5c 第一轮集中修订的固定静态复审

固定 5c 的 17 个产品路径不改五个 uv lock、Cargo.lock、toolchain 或 backend dependency-base 输入；f000 的整表 codec 重编码已改为普通 SQL/History 的 `ArrowSnapshotTableReader.reopen().arrow_stream()`，`composite_signal_point` 仅以既有 `snapshot_arrow_input` 有界转换进入 Rust。C 的 facts/artifact 两序分离仍在：Risk 新导出 facts 原序的 kind、32 字节 identity 和 changed-columns Arrow 视图，物理 batch 的 owner 链沿 `charge_arrow_batches` 留到最后 buffer。metadata-only facts core 允许 `None` handle 但传完整 table payload；summary 位于 tables 前，跨 phase handle 要求同一 operation identity 且来源已 seal。这些是静态结构判断，当前候选尚待 06 动态证明 Parquet/JCS/owner/M。

**5c 首次明确发现的去重问题：** `production.py` 的 `ComparisonTaskSession.evict_for()` 在首个 pair 入口看到 `cached={}`，任何已声明重复 key 都“不在缓存”，立即 `close()` 清空声明、用途和 key charges。于是首个 producer 不会留候选，FULL 第二 pair 不可能命中；不能以“真实任务 0 hit 合法”解释。artifact 身份分支又只写 artifact/ordered metadata、忽略 `SnapshotTable.reader is None`：Contract 允许非失败表有同一 artifact/descriptor 但 reader 缺席，后一 pair 本应降级，却可重放前对成功事实。已交实施者修 first producer、reader availability 与必要新工作前驱逐/安全 miss，并要求可复用及 reader 缺席向量的 calls/reads/hits 独立测例。f000 曾提出完整 key/可选缓存不挤必要工作的一般约束，**但这两个具体失效是 5c 首次明确告知**；下一固定修订是它们的首轮针对性修复，不因同属“cache”大类机械累计两轮。当前 main WIP 不作 5c 修复证据。

**5c 首次明确发现的旧错误优先级差异：** `ArrowSnapshotTableReader.reopen()` 可抛稳定的 `TableAccessError(READER_CLOSED)`，5c 的 per-table catch 未纳入它，导致整个 operation 失败；旧 `_compare_task_safely` 将它变为普通 `TABLE_DEGRADED`。标准重复有效键另有已知旧诊断 `DUPLICATE_EFFECTIVE_KEY:<table>`，Rust/PyO3 传为 `ValueError` 后 5c 只取类型名 `ValueError`，使 facts/core/closure 摘要改变。标准 keyless `DEGRADE_NO_COMPARE_KEY` 的旧路径先 `_read_rows` 双侧，5c 在 reader 检查前直接返回该降级，reader 缺席/故障时错误优先级、record 及 digest 不同。Ordered 错误必须按**旧异常来源**区分：reader=None 和旧 `OrderedComparisonError` 走 ordered/blank 三族降级；`reopen()` 抛 `TableAccessError/OSError` 则由旧外层形成普通降级。本人已撤回“所有 ordered reader 错都应补 extension”的过宽说法，要求实现者以旧 Python 控制流及 Contract 为独立 expected。f000 曾提出 reader 错误要分类、keyless 控制流要保留，但上述具体异常/诊断/优先级直到固定 5c 才独立定位；下一固定修订按各具体 finding 的首次针对性修复计。

**5c 首次明确发现的候选有效性与跨阶段控制问题：** per-table 错误被转成 `DEGRADED` 后仍登记 task key，`commit_cache()` 会缓存 `(失败 fact, None)`，Risk 也可能缓存其事件；失败候选不应入图。声明阶段还把 `DATASET_REPLACEMENT` 的表当作可复用 task 计数，尽管实际 compare 直接返回、这些 task 零次消费。`pair_pipeline` 调 Risk 未传同一 operation 的 cancel probe/deadline，默认 `RiskExecutionContext` 在旧 `_check_pair/_check_table` 位置看不到它们；cache hit 的附加 kernel checkpoint 与 miss 响应不同。f000 有“失败不缓存、只留已知用途、当前控制重放”约束，但上述具体漏项直到 5c 才定位，下一固定修订是各项首轮针对性修复。实施者 main WIP 的修订只在下一固定 clean SHA 对源码及动态独立向量复核。

轮次只按**具体同根问题**跟踪：f000 已明确的整表 codec FFI、keyless UPDATE_ONLY 状态/content、key transition、ordered unchanged provenance、Risk 必要列和 Python metadata/owner M 等，5c 提交了对应结构性修订，当前先核动态证据；若下一针对性修订仍留同一具体实质缺口，再结合连续两轮实际修复记录决定暂停受影响部分。5c 新定位项不因候选编号被预先算作第二轮。

本轮仍须核完成：按旧 Python 控制流独立生成 keyless/非记录/ordered/BLANK 与 Risk cap、过滤、诊断、closure 期望；真实 Preview MO/FULL、History、小 Compose；cache 失败/取消/超时不留半成品、最后用途退账、低 M 安全 miss；Risk 必要列最后 Arrow owner 与 Python batch 转换峰值；当前生产镜像重建和小 Compose。现有 5c 测试文件仅有两个普通 Standard fixed facts 例子，不能独自覆盖这些高风险路径。静态审核继续，不把未运行测试写成 PASS。

## 4. DC68 取证停止与恢复稿独核

本人只读核固定恢复说明 `7ca300def7b1f56b9dd4629184fc0fe72ebec35b`，即 [p6-s3-d-execution-stop.md](p6-s3-d-execution-stop.md)。它把 f000 产品 fmt exit1 与两次外层日志抓取 exit1 分开：首次脚本将 `PREP_LOG_SHA256=<hash>` 当纯 hash 比较；唯一纠正又将 `RUN_LOG_SHA256=<hash>` 当纯 hash 比较。第二次 SCP 自身 exit0，但组合命令 exit1、组合 stdout 未单独落盘，不能补记为原始完整日志。06 postflight SSH 本身 exit0 且本人 marker 已释放。本人事后曾做第三次纯本地只读 SHA 比较并表示 CLEAR；现明确撤回它作为恢复依据的结论，文件字节相同不能改写两次外层失败或取得 DC68 放行。

AGENTS DC68 的“重做再次失败……均停止交 owner”适用同根取证错误。本人当时的独立结论：**固定 `7ca300def7b1f56b9dd4629184fc0fe72ebec35b` 恢复说明及 `1719ca8f243180335ec9e9d1c6f3ec0585dbf284` 模板绑定补充可供 Owner 决定；未获确认时执行通道暂停**。其 §3 的下一候选标准 `sha256sum` 清单、清单外收据与 `sha256sum --check` 是针对已发生前缀解析故障的最小方案；不追加 f000 比较、不重跑旧 f000 fmt、不覆盖原件。同一 tester 后写的**未执行** `/home/dev/gdds-test-tmp/p6-s3-d-capture-template/capture-artifacts.sh` 本人已逐字静态 CLEAR，独立核其文件 SHA256=`1c8dd8c56518499dd98f2506333451d122f85f6bf525a757864534e0a6e2aa23` 与 1719 记录一致：活动收据位于新本地捕获目录外，远端拒覆盖并生成标准清单，SCP 与本地 `sha256sum --check` 各保原 exit/stdout/stderr，无标签 hash 提取或自动重试。此 CLEAR 只覆盖通用捕获模板；下一固定候选的完整 source/node/run/调用字面稿仍须本人核 HEAD、路径、命令及 SHA。恢复稿及模板均不是 D GO 或对旧失败的豁免。

Owner 后在 `733c4551e5` 所记录的问题中明确回复“确认并继续”，因此**仅下一新候选的 D 执行通道已恢复**；无需重问相同许可。f000 原始 fmt1、两次 capture1 和组合 stdout 缺口原样保留。测试者仍须先交下一固定 HEAD 的完整字面稿，由本人核 CLEAR 后才在专用节点执行；Owner 恢复不把 5c 静态 CHANGES 或旧模板升级成产品/执行通过。

## 5. 当前验证与镜像判定

1c25 触及实际 PyO3 比较/risk production route 与真实数据诊断工具，必须在本轮收敛后的当前候选于专用节点强制 native 重装、核 build input，进行 focused/Contract、真实 Preview/History/Compose 与当前 backend/worker 容器门禁；C 旧镜像仅证明 C 时的路径，不能充当 D 生产路由通过。五锁/toolchain/base 输入未变时，可按完整输入身份复用既有 dependency-base，但必须记录来源、config digest 和全部 RootFS DiffID。04 权威 runner/carried 与最终容器、05 t1–t3、CT108 正式性能/t4 仍各按节点职责和 DC33 判定；06 W3/W4 只能称诊断，未做正式性能测量。当前最后经验证的镜像 revision 仍是 C 产品 `854d3888a9de49a666f209145756befec1dd2532`，1c25 无当前镜像结果；重建延期至 D 候选收敛后的 06 小 Compose/04 必要门禁。

## 6. 1c25 固定集中修订的增量静态复审

本人在 clean detached 1c25 worktree 核 HEAD 与 Rust tree `45acfe79a0b9bffdf701d5d42be590cba456f092`、`legacy/` exclude、`5c..1c25` diff check。11 个产品路径不改五锁、Cargo.lock、toolchain 或 dependency-base 基础镜像。`evict_for()` 在首个 producer 无缓存时保留 session；`commit_cache()` 将所有声明用途计消费而只留成功完整 fact；replacement 不声明 row task；可选 comparison key 在 `repr` 前作 16 MiB 预约和保守输入预检；失败 attempt 的 metadata charge 在重算前退还。旧 reader closed、keyless 先读、已知重复键诊断、ordered 内外层降级来源及 operation Risk cancel/deadline 接线均已有针对性代码和独立旧 Python/Contract 向量。新 Risk hit/miss 测例覆盖过滤先 cap、table/pair 同时 cap、表超时不计 pair total、诊断预检、当前 closure、取消/截止与 FakeClock 调用数。上述仅为源码与测试设计检查，未将新增测试声明为通过。

**5c reader availability 同一具体根因的首轮针对性修复仍未闭合。** 1c25 的 artifact key 纳入 `reader-none`/reader 类型，却不纳入后续 reader 的可重开状态；`session.lookup()` 命中只做 operation checkpoint。现有测例是 closed first→ready second，首个 DEGRADED 自然不入 cache；反向 ready first→closed second 在同 artifact、descriptor、reader 类型下会命中先前成功 fact，旧 `_read_rows` 应形成普通 `TableAccessError` 降级。即使复用同一 reader 实例，也可在两 pair 间关闭。已交原实施者用旧 Python oracle 补反向 status/facts-core/calls/reads/hit 向量，并在命中前验证当前 reader 或保守 safe miss。此为针对 5c 明确 reader 可用性问题的**第一轮**修复未成；尚未满足连续两轮实修失败的暂停条件。

**1c25 首次定位的独立 M finding。** Risk `_evaluate_table_impl` 可选 cache 分支先 `repr` 包含 table/facts 全局 diagnostics、ruleset、options 的完整 key，再 lookup，却未给该构造和保留的 key 作同池前置预算。`ComparisonFacts.diagnostics` 合同仅检查 tuple/非空字符串；Risk 预检的字节上限只作用于单表投影诊断。临近 M 时可选缓存会先分配未计 Python key。已交实施者在 `repr` 前用局部预算或大输入 safe miss，保留 key 后收费；此为新 finding，不和 reader 同根累计轮次。

**待补动态覆盖。** 当前 D 产品向量已有成功 Standard、keyless、非记录及 ordered 降级，但成功 ORDERED+BLANK 的 `compare_plan_native`/pair pipeline、facts 原序 Risk 与 artifact 排序三视图、三族 Parquet 接线尚缺一个小型旧 oracle 对照；C adapter 的直接测试不能代替 D 生产接线。已交实施者补 move+blank 及必要 metadata-only 单侧向量。`bd752e4c62f0d7d5204094bf2befbc77bf7b3e50` 的 D handoff 初稿明确当前无 D 运行证据、T4 `--s3-census` 仅 partial Preview、E 才删旧算法/oracle；本人的静态核读不将其签为 GO。1c25 的 06 fmt-scratch 字面稿静态 CLEAR 见 §7；执行与 focused 原件仍待核。

## 7. 当前缓存备料与 06 机械反馈稿

本人逐字静态核 CT108 cache-only 预填稿 `/home/dev/gdds-test-tmp/p6-s3-d-ct108-cache-prefill/prefill-ct108.sh` SHA256=`cfe4432e057f4ea56433bfda68f5539cc179d39aa58c9a749295eb62445a7b38`，只在本节点空闲后取得本人标志，source 固定 SHA、LAN 传输，已有 tag 只验、缺失才验 archive 后 load；失败保原 exit 并仅在严格确认本人 marker/无进程时释放，不覆盖他人资源。本人随后独核 CT201 原始总日志 SHA256=`96c3f6db0b5cb0ac082b35860ddb109cef97d4c2e23933bf21699eb53b672ed8`：`heavy-dev-01` 2026-11-08T04:24:18–04:25:39Z；CT108 `gw-dms-test` 初始 tag missing（预检 exit42 为显式分支），源 archive SHA256=`fb30d4666cf5466c66ca464c9db7103457cec92f4eb9003980f6c1a2e3dfc136`、identity/input/verifier 三 SHA 在源与目标均核 0，04:25:01–17Z load。目标 `docker save` 经同一 verifier 核 Rust base config=`sha256:7ea53b11a01d2d52b4af8fa073cd76ecbaf7dc385b88cc9d0ce8205a7c941ff1` 与全 5 DiffID、dependency config=`sha256:15a18396cec14ec488f47c7a1c7fe73575ea2849c77e24593cfcf0ed99f41c9c` 与全 19 DiffID，两个 `IDENTITY_MATCH`；目标重存 tar SHA 与源归档可不同，镜像身份按 config/全 DiffID 判。本人 marker 04:24:22Z 获取、04:25:39Z 释放，remote 与 overall exit0。此为 CT108 依赖缓存准备，未运行 D 产品、编译、测试或性能。

本人对固定 1c25 的 06 Rust fmt scratch/source/node/postflight 全字面稿和标准清单捕获稿已静态 CLEAR：`prepare-and-format.sh` SHA256=`560137ec3d35d794dd31608bdda9cb74c4238b0f2adc59b598b117a1f2c46bb9`、`capture-format-artifacts.sh` SHA256=`c7088ca70c5b1ab209c3e0be1438b72f7e5708a91ea9ec98b1c060a33ef6ca92`、通用 `capture-artifacts.sh` SHA256=`1c8dd8c56518499dd98f2506333451d122f85f6bf525a757864534e0a6e2aa23`。此前未执行草稿把 SSH stdin 脚本的 `$0` 当文件 SHA，已在最终稿删除；又补 AGENTS 要求的独立 BatchMode `echo OK`。稿只在 06 独立 scratch 运行 `cargo fmt --all`，捕获六锁、patch/原 exit、本人标志安全释放和标准 manifest；不会把 scratch 格式化出口 0 记为固定候选 `cargo fmt --all --check` 通过。当前尚未收到此稿的执行原件。
