# Phase 6 S3 D 独立审核

**当前结论：D CHANGES，执行通道暂停。** 本人是 S3 D 的同一独立审核者。`f000e5b075408455a35e8ae3dededc28036c73c6` 是首个固定实现检查点；其静态问题与 06 Rust fmt 失败均保留原状。`5c47795062937a8db0315640a95ab763d2c2c8ab` 是其后第一轮集中修订的固定产品候选，仍有 §3 所列去重失效，且尚无当前候选的编译、功能或容器证据。此结论不是 D GO、S3 GO 或对 C 的重新审批。

## 1. 审核对象与边界

设计 `d49bb126b664af4b09097aee1a6f0b1bf58c9496`、kickoff 复审 `83ba4979044179256aa8c3d5d1d7b3424e648884` §5 已固定；A/B/C 的既有独审 GO 不重开。本人以仓库 AGENTS、testing conventions、比例化保障与 Rust 安全性能政策 v7、S3 design/kickoff/A–C handoff/review，以及 Comparison、Ordered Diff、Risk、Comparison Bundle/Surface、Snapshot Table Access、Shared Canonical Encoding、Storage/Repository Boundary、Operation Lifecycle 和 Performance owning Contract 为依据。

产品只读审核分别在 clean detached worktree `/home/dev/gdds-s3-d-review-f000e5b075` 和 `/home/dev/gdds-s3-d-review-5c477950` 进行，固定 HEAD、`legacy/` 链接和 worktree clean 已核。main 上与固定 SHA 无关的后续个人 WIP 或并行文档不纳入本轮产品结论。审核工作树和开发主机未运行编译、lint、测试、容器或性能测量；唯一测试者为 `/root/s3_d_test`。

本节目标是 Preview/History 共用 pair pipeline 的唯一 Rust compare + Arrow records 路由、facts 原序的 Risk 必要列、FULL 已知用途的 operation 内去重、同一 N1/M24 GiB/取消/截止与 closure 语义，并从 W3/W4 开始诊断。保留小元数据、replacement 和独立的 Submit mutation planner 等 consumer；E 才移除旧算法与临时 probe。D 不得留 Python 比较 fallback 或部署开关。

## 2. f000 首固定检查点与原始结果

本人对 f000 静态初审给出 CHANGES，已精确交原实施者同一职责内修复。核心问题包括：production 直接调用 codec FFI 重编码整表 IPC 而非借 C Arrow reader；keyless `UPDATE_ONLY` 状态/content 与 key transition 条件偏离旧控制流；ordered unchanged 快路径错误要求 before provenance；Python 小 metadata、Risk 事实投影、cache key/owner 和 Surface/Parquet 输出的 M 账不完整；Risk 事件重放须在当前额度、过滤、时钟、取消、deadline 和 closure 下执行；Composite 派生表须限定既有有界转换。f000 是第一轮实质审核，不因称为 checkpoint 而从同根修订次数中删除。

唯一测试者在 06 对 clean f000 只运行已审 Rust fmt→clippy 稿。`cargo fmt --all --check` 于 03:36:30Z 原始 exit1，`comparison_records.rs` 有格式差异；clippy 未启动，亦无 Rust test、backend focused、Compose 或 D 当前镜像结果。起止 HEAD=f000、六锁无漂，节点本人 marker 于 03:36:56Z 释放。原始 run 本地副本 `logs/remote-run-focused.log` SHA256=`6bd909e6ceeca3b168a078b0544c4a3e276be380de6c5895543ecc5a7a7a483c`；本轮不能记为编译或功能通过。

## 3. 5c 第一轮集中修订的固定静态复审

固定 5c 的 17 个产品路径不改五个 uv lock、Cargo.lock、toolchain 或 backend dependency-base 输入；f000 的整表 codec 重编码已改为普通 SQL/History 的 `ArrowSnapshotTableReader.reopen().arrow_stream()`，`composite_signal_point` 仅以既有 `snapshot_arrow_input` 有界转换进入 Rust。C 的 facts/artifact 两序分离仍在：Risk 新导出 facts 原序的 kind、32 字节 identity 和 changed-columns Arrow 视图，物理 batch 的 owner 链沿 `charge_arrow_batches` 留到最后 buffer。metadata-only facts core 允许 `None` handle 但传完整 table payload；summary 位于 tables 前，跨 phase handle 要求同一 operation identity 且来源已 seal。这些是静态结构判断，当前候选尚待 06 动态证明 Parquet/JCS/owner/M。

**仍需修复：** `production.py` 的 `ComparisonTaskSession.evict_for()` 在首个 pair 入口看到 `cached={}`，任何已声明重复 key 都“不在缓存”，立即 `close()` 清空声明、用途和 key charges。于是首个 producer 不会留候选，FULL 第二 pair 不可能命中；这是实际控制流确定的失效，不应以“真实任务 0 hit 合法”解释。已交实施者修 first producer 与必要新工作前驱逐/安全 miss，并要求真实可复用输入的 calls/reads/hits 独立测例。实施者已在 main WIP 报告修订，下一固定 SHA 才复审，不把 WIP 当 5c 的修复证据。

本轮仍须核完成：按旧 Python 控制流独立生成 keyless/非记录/ordered/BLANK 与 Risk cap、过滤、诊断、closure 期望；真实 Preview MO/FULL、History、小 Compose；cache 失败/取消/超时不留半成品、最后用途退账、低 M 安全 miss；Risk 必要列最后 Arrow owner 与 Python batch 转换峰值；当前生产镜像重建和小 Compose。现有 5c 测试文件仅有两个普通 Standard fixed facts 例子，不能独自覆盖这些高风险路径。静态审核继续，不把未运行测试写成 PASS。

## 4. DC68 取证停止与恢复稿独核

本人只读核固定恢复说明 `7ca300def7b1f56b9dd4629184fc0fe72ebec35b`，即 [p6-s3-d-execution-stop.md](p6-s3-d-execution-stop.md)。它把 f000 产品 fmt exit1 与两次外层日志抓取 exit1 分开：首次脚本将 `PREP_LOG_SHA256=<hash>` 当纯 hash 比较；唯一纠正又将 `RUN_LOG_SHA256=<hash>` 当纯 hash 比较。第二次 SCP 自身 exit0，但组合命令 exit1、组合 stdout 未单独落盘，不能补记为原始完整日志。06 postflight SSH 本身 exit0 且本人 marker 已释放。本人事后曾做第三次纯本地只读 SHA 比较并表示 CLEAR；现明确撤回它作为恢复依据的结论，文件字节相同不能改写两次外层失败或取得 DC68 放行。

AGENTS DC68 的“重做再次失败……均停止交 owner”适用同根取证错误。本人的独立结论：**7ca 恢复说明可供 Owner 决定，执行通道仍暂停**。其 §3 的下一候选标准 `sha256sum` 清单、清单外收据与 `sha256sum --check` 是针对已发生前缀解析故障的最小方案；不追加 f000 比较、不重跑旧 f000 fmt、不覆盖原件。具体新候选脚本和捕获模板尚须同一独审逐字核对象、路径、命令及 SHA，且 Owner 放行前不得执行。此稿本身不是执行 CLEAR、D GO 或对旧失败的豁免。

## 5. 当前验证与镜像判定

5c 触及实际 PyO3 比较/risk production route，必须在本轮收敛后的当前候选于专用节点强制 native 重装、核 build input，进行 focused/Contract、真实 Preview/History/Compose 与当前 backend/worker 容器门禁；C 旧镜像仅证明 C 时的路径，不能充当 D 生产路由通过。五锁/toolchain/base 输入未变时，可按完整输入身份复用既有 dependency-base，但必须记录来源、config digest 和全部 RootFS DiffID。04 权威 runner/carried 与最终容器、05 t1–t3、CT108 正式性能/t4 仍各按节点职责和 DC33 判定；06 W3/W4 只能称诊断，未做正式性能测量。当前最后经验证的镜像 revision 仍是 C 产品 `854d3888a9de49a666f209145756befec1dd2532`，5c 无当前镜像结果；重建延期至执行通道恢复及 D 候选收敛后的 06 小 Compose/04 必要门禁。
