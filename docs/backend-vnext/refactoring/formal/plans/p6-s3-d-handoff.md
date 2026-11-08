# Phase 6 S3 D 实施交接

状态：D 产品修订候选为本地 `main` 的 `1c25ea68e713fef8718ea499592628dc035a7e94`；独立增量复审和专用节点验证进行中，**尚无 D GO**。本页记录当前实现与待填证据，后续以独审报告及实际原始日志封口。固定设计 `d49bb126b664af4b09097aee1a6f0b1bf58c9496`，kickoff 复审 `83ba4979` §5 READY；A/B/C 的 GO 见协调记录，不当作 D 运行结果。

## 固定候选与生产边界

起点 `e05219b26e`；首个 D 中间产品 `f000e5b075408455a35e8ae3dededc28036c73c6`；第一轮集中产品 `5c47795062937a8db0315640a95ab763d2c2c8ab`；当前修订 `1c25ea68e713fef8718ea499592628dc035a7e94`，Rust tree `45acfe79a0b9bffdf701d5d42be590cba456f092`。当前候选 clean 提交只改 D 的 comparison/risk/pair pipeline、Rust coarse adapter、相关测试与当前诊断工具；五项 dependency-base 输入、锁、toolchain、基础镜像未改，不能因此把旧镜像说成已验证当前 HEAD。`git diff --cached --check` 在提交前为 0，专用节点结果待补。

Preview 与 History 的 pair pipeline 已走同一 `compare_plan_native`：普通表直接借 S2b canonical Arrow reader 及其唯一 backing owner，Rust B/C 完成 standard/keyless/ordered/未变化单侧摘要，Rust Arrow 三族 records、table/core 完整 JCS；小 metadata-only fact 带 `None` handle 参与同一个 `{algorithm_version,kind,summary,tables}` payload，summary 在 tables 前，不能拼 table hashes。`operation.seal()` 在全部 table/core digest 后缩 native portion；writer 与 Risk 再从同一个 operation M 预约，最后 consumer 退 owner。BLANK 私有 `entity_key_kind` 只进入 facts JCS，不进 Parquet。风险走 facts 原序的 `record_kind Utf8`、`row_identity FixedSizeBinary(32)?`、`changed_columns List<Utf8?>` 必要列视图；Rust 输出 batch 的 buffer/null/child charge 跟最后 batch，Python 按 batch 粗粒度转换供原 Risk 规则。`BROWSE_ONLY`/`SNAPSHOT_ONLY` 的 `COLUMNS_ADDED` 用 B keyless 共有列 multiset probe，公开 row/suppressed count 保持零，仅 content_changed 反映 multiset 差异。

去重仅在同一 operation 已声明的完整相同 DETAILED task 中保留有后续用途的成功结果；key 含表名、方向、双侧 descriptor/authority、reader 可用模式、ordered provenance、policy/rules/options/versions。单侧 ordered summary 是独立 task kind；replacement、无后续用途、异常/降级结果不留。可选 key 在 repr 前按有界输入预估并预约，过大或紧 M 安全 miss；必要 work 前可驱逐可重算结果，失败 attempt 的 metadata 预约局部退费。FULL 的两 pair 共用 session，但真实命中可为 0，不承诺跨表或变化任务命中，更不承诺 10–20% 收益。调用、输入读取与派发分别记真实次数；keyless 降级旧语义的两侧 Arrow drain 计读取而不伪计 Rust 调用。单侧摘要计一次 Rust 调用/一次读取；非记录共有列 probe 计一次/两次。

Risk 缓存只留纯候选 Emit/closure 事件，当前 pair 按原 emit 顺序重新核 cap、level、table/pair time、closure、取消与截止；同时触 table/pair cap 时 pair 优先，`_TableBudgetExceeded` 不增加 pair total，诊断预检正常 degraded 增加 pair total；pair 超限丢弃全部部分标注。当前 operation control 明确传给 `RiskExecutionContext`。Risk 仍是 Python 业务规则，没有新持久状态或计算服务。固定 N=1 active operation、32 GiB worker envelope、8 GiB reserve、显式 M=24 GiB=`25769803776`，均未改。

Compose 的 `composite_signal_point` 是现有 `MaterializedTableReader` 派生输入例外，沿现有 bounded Python 行转换生成 canonical Arrow；D 在派生 `encoded_rows` 分配前预约并覆盖其与新 Arrow 的重叠驻留，不能宣称全生产零 Python 行转换。更早的 `composite.rows` 由原 producer 创建，当前 D 费用证明只覆盖转换前既存派生 rows 与新 copy 的长期重叠，不冒称该最早 producer 已在增长前计费。普通 SQL/History 直接借原 canonical Arrow。

## 独立 expected 与修复链

小型 facts、JCS、status/diagnostics、三族、Risk 的 expected 来源为冻结旧 Python 控制流、A 的 Risk Contract 固定向量与 C 的三族原件；新 Rust 输出不回填 expected。当前 D focused 中旧 Python `compare_plan` 仅在替换期测试侧作临时 oracle；E 删除旧实现前必须把这批动态 expected 固定为具体 payload/digest/断言，之后删该 oracle。`test_comparison_s3_contract_vectors.py` 的 cap、预检和 filtered Emit 注释/期望已独立按旧控制流写定；D 新 hit/miss 用同一预期，不把 cache 输出当预期。

| 根因 | 固定修订与验证向量 | 状态 |
| --- | --- | --- |
| `f000` 直接 canonical codec 再编码整张 Arrow、额外复制/错误 M 入口 | `5c` 改借 S2b reader/backing；当前无生产 codec import | 待 06 当前镜像和资源实核 |
| keyless UPDATE_ONLY suppressed status/content、允许 source-key transition、ordered unchanged provenance、schema record 与三视图次序 | `5c` 接 B/C 合同，`1c25` focused 比旧 facts/core/digest/records | 待 06 focused |
| 必要列 risk view 类型/owner、metadata/core/seal、可选缓存挤占必要 M | `5c` Rust typed facts-order view、same-operation sealed handle、same M；`1c25` 大 key preadmit/safe miss、失败 metadata 退费 | 待独审及 M 向量 |
| 5c dedup 首 producer self-close、artifact reader-none 错 hit、replacement 0 use、降级结果误留 | `1c25` 保首 producer、key 加 reader mode、跳 replacement、degraded 只计消费不缓存；真实两 pair calls1/reads2/hit1、单 pair 0 留存、closed→ready 0 hit | 待 06 focused，真实 W3/W4 hit 待测 |
| reader 错误/取消优先级、ordered 旧外层与内层降级形态、keyless DEGRADE 读先于 metadata、重复键诊断 | `1c25` 源错误分类、Arrow C Stream 取消交错重核、两侧 drain、`DUPLICATE_EFFECTIVE_KEY:<table>` 窄映射；旧 oracle 对照 | 待 06 focused |
| Risk hit 误跳当前 control/cap/closure | `1c25` 传 operation control，新增 table/pair cap、table time、预检、filter、closure、取消/截止 hit/miss 固定矩阵 | 待 06 focused |

中间 `f000` 在 06 的唯一实际检查仅 `cargo fmt --all --check` exit 1（`comparison_records.rs` 十处格式差异），随后首败停，clippy 未运行；原 run 日志 SHA256 `6bd909e6ceeca3b168a078b0544c4a3e276be380de6c5895543ecc5a7a7a483c`、clean HEAD/六锁无漂移。取证 postflight SHA 解析自身连续失败并保原件；Owner 已按独审恢复决议明确“确认并继续”，新候选从全新已审 literal 稿恢复。不能把 `f000` 记为产品算法失败、D 编译通过或旧结果 carried。`1c25` 目前尚未运行 Rust fmt/clippy/test、backend focused、Compose 或真实诊断。

## 诊断入口与未填证据

当前工具 `vnext/backend/benchmarks/real_dump_journey.py` 的 `--s3-census` 显式读 accepted T4 census，不再把 P5 census 硬编码用于 W3/W4；`--tier t4 --scope t4-identity` 仅做 v1 Submit/Archive 基线准备和 v2 Preview 后停止，`--v2-input-completeness MODIFIED_ONLY|FULL` 才是 Preview 两种输入形态，FULL 同时提供 v1 initial package 并验两个 pair。`--scope full` 是完整 API 旅程，不是 Preview FULL。`--validate-inputs --tier t4 --s3-census ...` 只校两份 T4 包和 census；其余六 dataset 在 accepted catalog 中但无包，不当作缺失。输入源为 CT108 accepted `w4-generator-correction-20261105b`，root 自有字节副本已在 CT201 `/home/dev/gdds-test-tmp/p6-s3-input-copy-20261108/source/roots/{2x,w4-10pct,w4-100pct}` 与 `source/census/*.json`，copy manifest SHA256 `cc175d99a627cd7e2e40364847dc9cfc59fb2b342b543c2f3ba6e89e2d5216b3`；原冻结输入、卷、镜像不改。目标节点 LAN 预填、当前 HEAD/input/census SHA 与 marker 由唯一 tester 在执行时核。06 不跑完整 W3 旅程；小 History/Compose 用 focused/小 Compose 覆盖，完整 t4 功能旅程只在 CT108 现场及 Owner 最终 DC33 范围下执行。

当前 `s3_pair_metrics` 记录真实 native calls/input reads/dispatches/cache hits、Rust input read/index+compare/records build、facts JCS、Parquet 写、Python 风险必要列转换、surface/table export 及 charged high-water。`upstream_projection_seconds` 与 `bundle_assembly_seconds` 当前标 `null`，不能把合并计时冒充独立测量。诊断还需现场 RSS/cgroup、真实 0/非 0 hit 及写后全份回读次数。W3 2×T4 MO/FULL、W4 ~10% MO/FULL 与 W4 100% 压力目前**未执行**；06 即使起测也只是非正式诊断，CT108 1 预热+3 测量、中位数/范围及 READY/完成门槛尚未知，失败不记成功。正式 CT108 窗口与退出 DC33 范围由 root/Owner 确认。

当前候选触碰 Rust/worker 生产，阶段退出需要当前镜像与容器门禁；`f000` 未验证镜像，C 旧镜像仅为 C 来源而非 D 当前 HEAD。06 focused、05 t1–t3、04 权威 runner/carried、CT108 正式/真实 t4 均待对应节点的 clean 提交、离线缓存、本机镜像/marker 现场原件；后续在本页逐条补 hostname、起止 UTC、HEAD、raw exit、日志 SHA、依赖 base config 与全部 DiffID、运行或沿用来源。

## E 必须接住的删除边界

E 在固定 D expected 后删除被替代 Python keyed/keyless/ordered 比较热点、逐行 records writer/全量回读、C/B 临时桥与动态旧 oracle；逐 consumer 核 `comparison/standard.py`、`ordered.py`、`artifacts._record_to_row`、`real_dump_census`、`history_compare_oracle`、`compose_gate_harness`、`test_comparison_s3_d_production.py` 的旧 `compare_plan` expected。保留 Submit mutation planner、replacement、普通 metadata helper 及仍有真实 consumer 的 DTO；按实际 consumer 决定 unused `parquet`/`base64` direct dependency 删除与新锁/base 取证。不得留生产 fallback/开关、永久 oracle 或改 FE/S4/S5 冻结面。E 的最终事实/制品/HTTP/容器与真实数据取证需接 D 当前单一路线，D 中间候选不能替代阶段退出结论。
