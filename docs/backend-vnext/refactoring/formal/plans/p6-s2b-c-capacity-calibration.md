# S2b C 容量校准与 D 配置前置

状态：C 的既有输入组件校准已完成。2026-11-06 Owner 已选择 A：worker envelope 12 GiB、reserve 4 GiB、显式初始 M=8 GiB/上限 8 GiB，N=1、单 active；D 负责配置接线与实际验收。M 缺失仍须拒启，不建立隐式默认。本文不声明 worker 容量、完整 operation 或 W1/W2 性能通过。

后续配置更新（2026-11-07）：E 补齐完整 t3 校准并独审后，Owner 已按 [DC87](p6-s0-owner-decisions.md#dc87-s2b-单-worker-的显式资源配置) 选择最终 32 GiB envelope / 8 GiB reserve / 显式 M24 GiB，替代此前 E 的 24/8/M16 及本文 C 当时的 12/4/8 选择。本文保留 C 原始测量与当时判断，不回填 E 结果为 C 的完整 worker 证明。

依据：[C 任务](p6-s2b-c-kickoff.md)、DC42/DC84/DC86、[映射](p6-s2b-arrow-mapping-design.md)、[原输入普查](p6-s2b-capacity-input-census.md)。所有执行在 06 `gw-dms-06`，N=1，clean/committed worktree `/home/dev/gdds-test-tmp/wt/p6-s2b-c-impl`；与 pytest workers、06 的 16 vCPU/32 GiB 分开。06 不提供正式 CT108 性能结果。

## 1. 实测范围与来源

第一组工具实际调用 Rust parser → B SQL materialization/catalog filter/canonical projection → A 唯一 IPC codec → 带保护的 local store → SHA/profile 核验 → 活跃 mmap/read handles。保留两侧 package/SQL bytes、parser/canonical/filter arrays、滤后 Python catalog facts，再同时打开所有本次需要的不同内容 mapping。相同 ref 只打开一次；未打开的其他历史 artifact 不计 RAM。

这是一条真实组件 FULL 生命周期，不是 Preview/History/Submit worker 全旅程。XML、AST/composite 与实际 operation orchestration 不在第一组测量里；第二组使用同一已核 t4 pair，实际调用 parser/filter/catalog → XML parser → AST/binder → composite → 现有 derived-table reader，保留双侧结果。第二组不运行 projection/IPC/store，也不重跑第一组。HTTP 恢复 spool 由实际 adapter 小测试验证有界和失败清理，尚无大样本 worker spool 峰值。

第一组的 311 张 t4 规范表来自 SQL 保留表，不含随后生成的 `composite_signal_point`。其每侧 435 行与现有 typed reader 已在补项中实际构造，但其 B/IPC 副本仍需 D 的真实 operation 复核；不把 311 当作最终业务表集合数，也不将两组分进程结果改写成一次完整生产 FULL。

两组均复用 06 已有 `/home/dev/gateway-real-dumps/datasets.json` 与 package。校验 manifest 的压缩 bytes/SHA，SQL 单成员至多 512 MiB，拒绝重复/未知成员及非普通文件；不生成或扩大输入。没有直接公网、转发代理、Dolt 真实数据旅程、Compose 或 CT108 测量。

| 校准 | 实际源码 | UTC 起止（2026-11-06） | 结果 |
| --- | --- | --- | --- |
| t1 v1/v2 B/A/store FULL 组件 | `f3e2ef67845336ae3d3fb50750890271871352b2` | 13:48:56–13:49:04 | exit 0 |
| t4 首次，同 4 GiB 局部预算 | 同上 | 13:49:36–13:49:50 | projection resource 拒绝，保留失败/部分文件，不是 PASS |
| 修正 keyed 跨行预约后的同 t4、同 4 GiB 一次复验 | `3ae27b98ff2eed7b92acbd7c7aa33c4f1bbc2a72` | 13:58:22–13:58:52 | exit 0；经 root 授权与独立审核后执行 |
| t4 XML/AST/composite 窄补项 | `d574717d0e9b396529db9be20c7d8c92f43d5b55` | 14:08:30–14:08:44（含扩展重装） | exit 0 |

以上来源不重新标作最终 C HEAD 上的测量，也不是正式 carried。后续 Rust 改动只将同五份 golden 改为编译期嵌入并保留原标签；后端改动为错误分类/架构入口/目标 schema 期望，不改变上述容量算法或输入。

## 2. 输入与大表分布

| 输入 | SQL bytes | SQL SHA256 | package bytes |
| --- | ---: | --- | ---: |
| t1 v1 | 1,296,177 | `f8da5b9608981f91ba4cef66e593a6e2299386871d53af71ba203802140748f5` | 107,115 |
| t1 v2 | 1,296,079 | `8fdbd3d207b81e933da9a4812b97239737541e574e7be4777dffa4f0c80ec059` | 107,066 |
| t4 v1 | 79,446,967 | `b3089d8a734651eb6dd439f11951699d176b7c1b3794bb55142d4532e8d721e8` | 5,597,503 |
| t4 v2 | 79,269,322 | `65358db2cfba310f145446698d6d20b580ba3b805d520bd3ff9ae33a12ad01af` | 5,596,595 |

package SHA 分别为 t1 `42794011d74b6c906e35bc5c79610fc0305020ae966f8f0df4449337b95ea8b2` / `4019737fc8fe35e90792dcef722537bf09338110ace8cc09f35e004cc7095bd0`，t4 `95408cc3cfd5bee4f7e53ab1b556e58c3335535b16e8791059029e59d5da1675` / `5a7cd54d9b996be55c34b7bb766eb01ad5c1b7c4fa9bd1e72f5c4741baee3611`。

| 组件结果 | t1 双侧 | t4 双侧 |
| --- | ---: | ---: |
| 每侧 canonical 表数 | 124 / 124 | 311 / 311 |
| 每侧 canonical 行数 | 3,729 / 3,727 | 246,359 / 246,439 |
| parser buffers 逐表求和 | 2,818,862 B | 195,208,942 B |
| canonical buffers 逐表求和 | 1,766,720 B | 117,516,276 B |
| filter buffers 求和 | 4,738 B | 336,454 B |
| 滤后 Python device/point facts | 10 | 872 |
| 每侧 IPC bytes（包括同内容复用的逻辑总量） | 1,959,328 / 1,959,328 B | 61,848,206 / 61,862,862 B |
| MODIFIED 内容命中 | 120 / 124 | 284 / 311 |
| 本次 unique active mapping bytes | 1,995,984 B | 85,457,516 B |
| 实际 objects+ref sidecars 磁盘 | 2,028,291 B | 85,542,936 B |
| 最大单表 IPC（用于单文件 atomic staging 推导） | 519,170 B | 21,363,522 B |

buffer 求和是 Arrow backing spans 口径，不能当 allocator capacity 或 RSS。mapping 以不同内容 ref 去重，只计本 operation 的活跃文件一次。磁盘不含 control DB、原始 package 与其他历史文件；没有据此推算长期 TTL/项目数量容量。

t4 最大 canonical 表为匿名 parser index 233：54,150 行、43 列，parser/canonical buffers 均 21,087,590 B，IPC 21,363,522 B。t1 最大表 index 58：1,302 行、43 列、buffers 480,621 B。少数集中大表已实际覆盖；没有以平均每表大小替代分布。

## 3. 4 GiB 拒绝的归因与最小修正

首次 t4 在 B keyed projection resource 检查处拒绝。原失败日志没有记录进程 HWM，因此旧失败 RSS 为 unknown，不能从成功复验回填。

只读比对原失败 control DB 的 232 个已登记 artifact ID 与成功运行 338 个 unique ID 的插入序列，原序列逐项等于新序列前 232 项；成功 JSON 的未命中表序列同为 338 项。因此将原首次未发布表定位为 v1 index 233 是有来源的确定性前缀推断，不是原失败日志直接记录。

原 projection 对每行 `working.reserve(scratch * 2)`；scratch 包括所有 retained 列的临时 scalar/frame/hash 开销，但跨行保留的对象仅 key frames、hash 和 Row。整行临时对象每轮释放。仅最小全行累计项即 `54,150 × 43 × 3,072 = 7,152,998,400 B`，已超过本次 4 GiB。

按 root 授权及独立复核，改为同模块 SQL materialize 已有的 keys-only 上界：每行累计 `key_count × 256 + Σ key_cell.scratch_bytes`。保留整行 `ensure(scratch * 4)`、row/hash/sort/output 及 adapter 所有预算；不改 M、业务摘要或资源错误类别。单项 200×100、单 key、16 MiB 的有限回归以原业务 oracle 验证；同一真实 t4 pair 在相同 B `max_live_bytes=4 GiB` / A `max_codec_peak_bytes=4 GiB` 下仅复验一次并通过。

## 4. RSS、page cache、预约和磁盘分别解释

| 进程实测 | t1 FULL 组件 | t4 FULL 组件 | t4 XML/AST/composite 补项 |
| --- | ---: | ---: | ---: |
| `ru_maxrss` bytes | 141,443,072 | 821,837,824 | 669,552,640 |
| 本次 `/proc` 采样最大 VmHWM bytes | 146,022,400 | 830,758,912 | 669,552,640 |
| 双侧/活跃 mapping 时 RssAnon bytes | 92,364,800 | 688,877,568 | 616,558,592（补项结束） |
| 同时 RssFile bytes | 53,657,600 | 141,881,344 | 52,862,976 |

`ru_maxrss` 与 `/proc` 原始窗口值分列，二者采样/内核统计口径不强行相等。t4 关闭 mappings 后 `/proc` RSS 为 744,591,360 B，其他输入/arrays/facts 仍保留；不把 allocator 未立即归还页面当 mapping 泄漏。

06 cgroup 的起始 `file` 约 30.5 GB，包含节点此前构建/文件缓存，不是本 worker 数据。记录 `memory.current`、anon/file/file_mapped 原值用于解释环境，不能把整个 cgroup filecache 加到 operation M 或称作本次 RSS。临时文件页和 mmap 会进入 filecache，与进程 RssFile/磁盘有重叠；三者不能相加宣称实际 RAM。

预约按同时存活关系计算，而非 SQL 大小乘固定系数：

```text
operation reservation = retained inputs + parser/canonical/filter facts
                      + active unique mappings
                      + max(current B working + uncounted borrowed input,
                            current A codec + uncounted borrowed input,
                            wire conversion + uncounted borrowed spool,
                            other actually overlapping stage scratch)
```

FULL 两侧的 retained facts 必须同计；顺序发生的 B 与 A 自有峰值取活动阶段最大值，不能无条件把两个局部上限相加。同 mapping 的多个 Arrow view 只计一次；独立 reopen 确实产生两个 mapping 时不能假去重成一个。

公式的 `uncounted` 指尚未计入 retained/parser/mapping 项的借用输入；已经计入的同一缓冲区不再相加。

codec 内部 writer Vec、Arrow encoded-data、当前 batch、累计 IPC 及 `Vec → PyBytes` 复制由 A 的 checked local budget 约束；payload 的传输至少存在两个 IPC 长度的同时 bytes，但 Vec capacity、库内部 scratch 与 RSS 不能仅从文件长度得出。本次没有分段 allocator profiler；B sort/filter/row encoding 的预约按实现保守式推导，不冒称实测分段 RSS。

最大 atomic staging IPC bytes 从最大 ref 长度推导，t4 为 21,363,522 B，不是 I/O 采样瞬时高水位。修复旧目标时可能与原目标同时占磁盘；新对象写入时临时文件 rename 后成为最终文件，不能把同一文件双计为两个持久副本。HTTP wire spool 另受实际 source byte quota 约束，不混入 canonical IPC bytes。

补项的每侧 XML 为 890,874 B、22,286 events、431 formulas、435 derived rows；每侧 formula AST JSON UTF-8 合计 409,338 B，point payload JSON 合计 314,185 B。实际调用现有 XML/AST/binder/derived-row owner，没有复制算法。两进程 `ru_maxrss` 直接相加为 1,491,390,464 B（约 1.389 GiB），包含重复 runtime、package/SQL/parser/filter，是保守工程估算；它不是实际同时峰值，也不是严格 RSS 上界。

## 5. 给 Owner 的两档部署选项

Owner 已选择下表 A；B 保留为未选备选。这些数值是**显式部署初始值**，不是隐式产品默认。D 中 M 未设置仍应拒绝启动；A 的配置选择不代替真实 worker 峰值、增长前拒绝与资源边界验收。

| 选项 | worker memory envelope | 工程 reserve | 显式初始 M | 可配 M 上限 | 适用范围 |
| --- | ---: | ---: | ---: | ---: | --- |
| A（Owner 已选） | 12 GiB | 4 GiB | 8 GiB | 8 GiB | 已测 t1/t4 量级、N=1/单 active operation，D 复核实际路径 |
| B（未选备选） | 24 GiB | 8 GiB | 8 GiB | 16 GiB | 更大单 operation 输入或所选 N 的额外余量；提高至 16 GiB 前须另行批准与实际验收 |

两档均满足 `M <= envelope - reserve`。工程 reserve 用于 Python/runtime/allocator 保留、线程栈、服务控制与 cgroup filecache 余量；数值是保守部署建议，不是已测严格非 operation 上界。B 不授权提高 maxinflight、多 worker 或 operation 并发；未来并发另行设计。

8 GiB 的依据是上述组件事实、保留项与已经实际通过的单阶段 4 GiB 局部预算；不从 06 的 32 GiB 推导。现有上限仍为 package compressed 256 MiB / expanded 1 GiB、SQL 512 MiB、XML 64 MiB、`max_xml_nodes=1,000,000` 等各自 owner 的准入边界；这些最大值不承诺同时全部接收。字段、行数、声明、语句和内存预算仍分别生效，额度不足在增长前明确拒绝，不以 OOM 作为正常额度拒绝手段，不继续发布部分结果；M 不是严格 RSS 封顶，不承诺系统永不 OOM。

## 6. D 必须关闭的事项

- 按 Owner 已选 A 落实真实生产 envelope/reserve/M 初始值和上限，保持 N=1/单 active；M 缺失、非正或 `M+reserve` 超过约定并实际配置的 worker envelope 时 startup 拒绝。D 绑定部署声明与 Compose limit 并验证，较大的宿主 limit 本身不构成拒绝条件，不为此建立新 cgroup 框架。
- 在实际单 active worker、所选 N、同池生命周期中，让 Preview FULL 两侧、History exact commit hit/miss、Submit/T1/PREPARED、wire spool/转换与 publication staging 进入同一 operation 预约；增长前检查，测试单表拒绝、FULL 重叠及资源失败不发布。
- 区分 borrowed mapping、B/A 自有分配及 Python/adapter 复制；共享 view 不重复预约，独立 mapping 不误去重。未打开的全局历史文件只计磁盘。
- 实际 control/cancel/drain/lease_lost 与有限 deadline 由 D 接线；C 使用 N=1/NeverCancel 的组件结果不能代替这些验证。实际 worker 复核 RSS/cgroup/预约差异，不重做无必要的生成输入/全旅程。
- M 是可拒绝的资源边界，不是“所有输入上限必定成功”的承诺。S2b 最终 04 门禁、t1–t4 正确性与 W1/W2 的 DC83/DC84 时点保持。

## 7. 证据索引

前缀均为 06 `/home/dev/gdds-test-tmp/`，日志均含 hostname、起止 UTC/HEAD、clean 与 exit；实际运行时使用本机预填 uv/Cargo 缓存与离线环境，无代理。

| 证据 | SHA256 |
| --- | --- |
| `s2b-c-capacity/t1-f3e2.json` | `e01635b685afcb11caa0484d9332f252351dcc56d3a2fe20c5c098c8daf08ab4` |
| `logs/s2b-c-capacity-t1-f3e2.log` | `43bf642115a11663661b90ad9258e038c29cbef4281fcf648e8afc4e268f123f` |
| 原失败 `logs/s2b-c-capacity-t4-f3e2.log` | `50229980fac628db09dcf6a0e5b6071b8c655f4cf93b3a5d55f4488f00d1ff6a` |
| 修正 focused `logs/s2b-c-key-3ae2.log`（50 PASS） | `305e4c53746dc20935324da187fcc141e78c7a8f8009f80420e5f3c37f4dc3d4` |
| `s2b-c-capacity/t4-3ae2-rerun.json` | `d5aba0e9908199870f0460ddebdae9c2a6fd0cf1564ca53d3268697b29785d17` |
| `logs/s2b-c-capacity-t4-3ae2-rerun.log` | `295b3a459ed4b4941866c0640d0abb83c2e3bd75f89a87fc30837578ce1f205a` |
| `s2b-c-capacity/composite-d574.json` | `50016b1d83a928fb1060f9f13299f8f1db66ee24948901b0af826064009553fb` |
| `logs/s2b-c-composite-d574.log` | `26d2a6d89093e95caea4c91243839d7da35e0beb535e95777fe2fd36e0338cce` |

原失败 `s2b-c-capacity/t4-f3e2-artifacts/`、成功 `t4-3ae2-rerun-artifacts/` 的 control DB、objects 与 sidecars 均保留，不用新结果覆盖旧失败。工具单独 mypy 首次仅传 benchmark 导致 editable source 被当 untyped 的失败日志为 `logs/s2b-c-capacity-tool-f3e2.log`，SHA `a55cada6ec3fcf42b7dc2a25a83cb75e8c531d0afd37170ea5033acb9c87b128`；改为同时检查 src+tool 后通过，`logs/s2b-c-capacity-tool-f3e2-path.log` SHA `dbdf9155141def4140269c418b325ccf87bbc8e57c2faa803d0987f9cca7d03d`，未改 typing 规则或重做输入。
