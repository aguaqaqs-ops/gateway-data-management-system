# Phase 6 S3 E 独立审核

状态：**审核中，尚无 E GO**。本报告由 E 独立审核者连续记录初审、修复复审和集中证据核收；实施者的 handoff 与测试者的原始结果均不能代替本结论。

## 1. 固定起点与范围

E 起点为 D 产品 `a9da0c59277e3179f34d646eabcd9c185917ae05`、Rust tree `b5f2439384d859bd32df3e3e24979f4f63f0f91b`、handoff `d1aad819be5e632a66f0f8cbbd3722a5ebafee36`，独立 D GO 见 `055707a98436128c7484c92877df3fc17d33035f` 的 D review §35。A/B/C 各自独审 GO 已核：A `f28c89eff5ac1e653facb21229c3b5a7d281f971`，B `17fd6739b809f048ac7b2f45cb784c144e2d98ad`，C `ce217c0ad77783a4a3c0eba3f0033bce356aaa3c`。本轮接受这些限定结论，不重开设计或用其代替 E 的产品和集中门禁。

本人先在 `/home/dev/gdds-s3-e-review` 建立固定 detached worktree，HEAD=`d1aad819be5e632a66f0f8cbbd3722a5ebafee36`，tracked clean，`legacy/` 已链接并由 exclude 忽略。只读核根 AGENTS、testing-conventions、比例化/Rust 政策、S3 design/kickoff、A–D 最终 handoff/review、协调末节和 E role brief。开发主机与审核 worktree未执行测试、编译、lint、容器或测量；后续每个产品候选仅在固定 clean detached 对象审核。

## 2. 首轮删除边界清点

当前 D 产品的 Preview/History pair pipeline 只调用 `compare_plan_native`，它对普通变化表走同一 Rust comparison/Arrow records 路径，Risk 读取 facts 序必要列；其少量单侧、非记录角色、early exit、无效 schema/key 和 ordered 退化仍借旧 Python 小 metadata helper。这些可达分支须抽为明确 metadata 路径再删旧 keyed/keyless/ordered 行算法。`replacement.py` 的独立 envelope、Submit mutation planner、无 native handle 的小 Standard/Ordered/BLANK records 出版、真实 Parquet open/read/restore validator 和 bundle raw/ref consumer 仍有实际用途，不能按文件名整删。最终须逐 symbol 证明生产行比较只有一个入口，不留 Python fallback、临时 probe 或永久动态旧 oracle。

删除前须在 06 clean 固定旧源先冻结 C 两处、D 多处动态 `compare_plan`/旧 writer expected，核 nodeid、输入身份、旧源码 blob、调用数、facts/table/core/records/closure/Risk 的必要摘要与原字节；来源是 A 前实现 `4d5a4b0d98ee2942a26eba794ce9f36a6826a9ec` 的旧 Python/Contract/golden，不能从新 Rust 输出回填。本人独立核得 `ordered.py` 与 `row_encoding.py` 在 4d5 和 a9 的 Git blob 完全相同；`standard.py` 仅在 `_build_facts` 增可选 `core_digest`，旧调用仍走原 JCS 分支；`artifacts.py` 已加 C/D 新读写代码，需单独锁定旧 writer 函数与固定原字节。取证插件和运行字面稿尚待独核，不能据此记冻结完成。

旧 consumer 还包括 `test_comparison_standard/ordered/blank/artifacts/records/rule_roles/planning/replacement`、C/D 测试、`tests/support/history_compare_oracle.py` 与 `compose_gate_harness.py`、`benchmarks/real_dump_census.py`，以及 B probe/差分 CLI 与旧 ordered prototype。对这些逐项决定保留业务断言、改现役路由或删除重复断言；不可只迁 C/D 后留旧算法给其他测试。Rust 未用的 direct `parquet`、`base64` 与 workspace/lock 闭包按实际引用最小裁剪，锁变化后 CT201 dependency-base 必须重备并按 config digest 与全部 DiffID 预填实际节点。

## 3. 集中证据待核

三项 Owner 已授权最小修复只限 worker claim 间 GC、cold catalog bounded16 COUNT/同 key in-flight、两个 ChangeSet hash-only JCS consumer；保持原 GC 状态、join 后收集、catalog 错误释放与 8 项/16 MiB、JCS bytes API/错误/摘要。不得带原基准部署/诊断框架，也不得重复移植已在 main 的 READY32768。

最终 V 固定代码独审后，06 focused/五包 Ruff+mypy/Rust fmt+Clippy 和适用小容器；04 clean 已提交同一来源 WT 的权威逐包及容器、05 fresh t1–t3、CT108 fresh t4 与 W3/W4 完整 Preview/必要正式统计分别核原始 exit、HEAD、输入、离线缓存、身份与清理。DC33 已确认四档 v1/repeat MO、v2 FULL，包含 Submit、真实 read/approve、History；不重复申请。D 的 06 两表/631表 partial 与 2x Risk 47.022 秒只作预警，不能称完整 READY 或 worker 32 GiB 包络已证。Risk 仍需最小分段与 DC47 语言边界评估；未经 Owner 决定不迁 Rust、不改 N1/M24 或冻结 golden。

当前起点 `d1aad` 相对 D 产品仅交接文档；本次只读初审不触发镜像重建。最后已验证的 D 小 Compose 镜像 revision 为 `a9da`，其不同两套 backend/worker config 与 DiffID 见 D review §31/33；它们不是 E 最终候选的容器门禁。E 产品触及 Rust/worker 与锁时必须对最终 V 的当前镜像重建并按权威入口核收；V→H 是否可 carried 待同节点同来源 WT 的逐包闭包及镜像身份等价实测，不能预判。

## 4. 三项共享修复的首次静态复核

固定候选 `6fae41957540040ca71dceef0632ef63e71f9681` 含分开的 GC `028aff2da7e613ba9241be8f16ae9e86a71b0060`、catalog `c6a2792901ad9e1c90c401b455258685c4f4e2e0`、JCS `968e8ec7ee3f3b51d68026998917b6d199fd9a85` 与本报告初稿。本人在该固定 clean detached WT 逐项比精确来源 Git blob 和产品 diff：GC runtime 与 `0c97cb9c09` 完全相同，catalog 四条路径与最终测试修订 `4497ded8ff` 完全相同，JCS 四条产品路径及 backend mutation 测试与 `1f9731dfc3` 相同；JCS 测试另有一项 UTF-16 supplementary/BMP 键序向量。GC 测试在原来源上另有当前 DC88 pure drain/attempt 语义场景，scheduler 的 gc patch 入口与 shutdown 事件断言按当前代码适配。三项都未携入诊断部署、READY 重复修复或新 N/M；我未发现超出 Owner 授权的产品差异，**静态 CLEAR，可在 06 运行受影响 focused**，尚无当前提交的运行 PASS。

GC 只在已确认 executor join 后恢复进入前的自动 GC 状态，成功 claim 在下一 anchor 前做空闲收集；busy/empty 不全收集，join 未确认不收集。catalog 仍保独立 import 路线，immutable 目录按最多 16 表带 ordinal 的 COUNT，in-flight Future 按 key 共享并在失败时释放；原 8 项/16 MiB 上限未改。JCS 保原 bytes API，只把 ChangeSet 两处 hash-only consumer 改为有界 sink，最终 digest 类型和错误映射未变。这些是源码判断；实际原值/错误/并发与 worker 完成性以节点结果为准。
