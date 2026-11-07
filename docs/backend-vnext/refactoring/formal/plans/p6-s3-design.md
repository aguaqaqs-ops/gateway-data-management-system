# Phase 6 S3：比较与逐行记录详细设计

状态：独立 kickoff 审核候选；2026-11-07。设计完成不等于实施授权。配套 [kickoff](p6-s3-kickoff.md) 与 [独审提示词](p6-s3-review-prompt.md)。本轮仅文档，无产品、测试、部署或基准资源操作。

## 1. 固定起点与证据边界

本轮只读核对起点 main=`5dde965a65`，tracked/staged/untracked 均空；已有多处 detached 审核 worktree、`fe-vnext`、`p6-baseline` 等并行目录，均不改动。不存在同名 S3 文档。代码坐标均相对此起点；它的 vnext 树为 `56720104af34a1eb677336f57bdbc07444a56615`。

- S1a/b/c、S2a/b 已退出。`p6-s2b-exit` 注释指独审 `9220f3cdecba7df3e50fec00d77d1dd9efb0f678`；H=`3580e6649f4b0819156f7f560670b3deee237f42`，实际权威源 V=`a6876d560050285321fd9f62942d590a03f35d64`。依据 [E review 末节](p6-s2b-e-review.md)及 [E handoff](p6-s2b-e-handoff.md)，不能把文档 H 当实跑。
- 当前资源为 N1、单 active、worker envelope 32 GiB、reserve 8 GiB、显式 M24 GiB（25,769,803,776 B）；DC87 首段与 E 最终结论优先于早期 12/4/M8。06 的 96 GiB 是节点容量。
- BE-a/归档核验/BE-d 产品 `49403f21aa1f0c8c3d585d13a707a37fb6b7fcd0`，技术 GO `ccdd1eb39d`、handoff `233e6f788b` 后已完成正式退出：附注 tag `p6-be-a-d-exit` 对象 `66b9083941` 指向 `77b9aeea74b08b527ef1c78637e0cbe000b60d2f`；最新 [联合交接 §15](p6-be-a-d-joint-validation-preparation.md)、[执行计划](p6-execution-plan.md)和 [FE3b 核对 §9](../../../../frontend-vnext/reviews/fe3b-precondition-check.md)互相一致。这是对用户交接起点的更新，不重办退出。
- FE3b 尚在评估/修订；不作为本设计前置。原基准最近有 FULL、H2 与表哈希收口及压力测量准备（`0bf7218401`、`26d58ae7a7`、`eeda746819`），不能照抄 E 历史末尾的 OPEN，也不能将准备记为压力档通过。本轮不复核其远端原件、不接管其状态或 CT108。

必读治理依据：AGENTS、[testing conventions](../../../testing-conventions.md)、[比例化政策](../policies/proportional-assurance-and-risk-based-verification-policy.md)、[Rust 政策](../policies/rust-safety-and-performance-policy.md)。语义依据为 [P6 design §4.6/8–11/14–17](p6-design.md)、[DC43/44/47/48/53/54/55/78/81/83/84/87/88](p6-s0-owner-decisions.md)。[旧会话交接](p6-backend-session-handoff.md)明确只记录当时状态。

## 2. 实际调用链与保留边界

以下 backend 路径均在 `vnext/backend/src/gateway_backend/`；Rust 路径在 `vnext/rust/`。

| 入口/模块 | 已有生产行为 | S3 改动 |
| --- | --- | --- |
| `application/preview_jobs.py` → `application/pair_pipeline.py` | materialize 后按 pair assemble；FULL 有两个 pair | 在同一个 operation context 中传递去重域；不改 pair/身份策略 |
| `application/history/compare_jobs.py::_assemble_comparison/_run_pair_pipeline` → `run_history_pair_pipeline` | 共用比较、风险、surface，之后 bundle/checkpoint/READY | 只换计算与记录消费；不提前做 S5 按表拼接、并发回填 |
| `pair_pipeline.py::_run_comparison_risk_surface` | plan → `comparison_python_memory_upper` 准入 → `compare_plan` → `publish_records_closure` → `evaluate_risk` → `assemble_surface` | 替换 Python 行比较/记录预算与接口；保留 planner、失败/取消、surface 与业务编排 |
| `comparison/standard.py` | keyed、keyless multiset、表/模式分支及 facts 汇总；ordered 委派 | 数据热点迁入 Rust；小型 metadata 分类/组合保留 Python，不能删整文件假装完成 |
| `comparison/ordered.py` | gid/no、LIS、空白、单侧 unchanged 摘要 | 全部相关数据计算迁入共用 kernel |
| `comparison/artifacts.py` | `_publish_family` 排序、dict/JCS、`from_pylist`，写后完整解码；`open_records_closure`/restore/read 校验 | Rust records Arrow/JCS；Python writer 与真实读取边界保留 |
| `risk_evaluation/_facts.py/_engine.py` | `table.records` 元组消费；组合信号与预算、排序/编号 | Arrow batch 投影消费；业务规则继续 Python |
| `application/submit_jobs.py` → prepare import publication | 冻结/准备导入/恢复；publication 内调用 `plan_import_mutation` 与 `render_planned_import_mutation_dml`，不是 `compare_plan` 调用点 | 不把 Preview records 当存储 diff；SQL 渲染及存储 diff 接入留 S4 |

Rust `gateway-compute-core/src/comparison/mod.rs` 当前只导出 `ordered.rs` 的 GID_NO_V1 原型；没有 standard.rs/keyless.rs。原型输出结构体/记录 Vec、单独建池辅助函数不能直接冒充生产接口。复用已验证 LIS/编码算法并适配 S2b Arrow 映射与共享池，删除被取代的原型专属接口。

`gateway-compute-core/src/records.rs` 已有三族 schema 与 Python 固定 Parquet 向量读取，但 `read_records_parquet_v1` 复制 raw、收集全量 JSON rows 再 JCS；这是复用素材，不是 S3 有界 reader。`gateway-compute-python/src/lib.rs` 现有 parser、canonical Arrow、取消/预算与 `initialize_kernel_pool/shared_parser_pool` 接线，没有生产 comparison adapter。新增粗粒度比较/记录校验入口，使用同一进程池，不增第二池或网络服务。

## 3. 纯计算接口与语义

设计接口名为建议内部名，不是 HTTP/持久 DTO。`compare_table(input, context) -> TableComputation`：input 包含有向两侧 descriptor、Arrow owner/stream、有效 pair policy、schema view、artifact/detail policy 和完整版本。context 由现有 operation 提供共享池、remaining budget、取消与单调截止时间。输出为小型 table facts、三族可遍历 Arrow batches、各族 count/content_digest；不能携带文件路径或新持久引用。facts 的业务 digest 序列化保持现行逻辑视图，不能因移除 Python 元组漏掉原 digest 输入。

模块划分：comparison 下共用 projection/row identity/encoding、standard、keyless、ordered、结果汇总；records.rs 拥有三族 builder、全局排序和流式 JCS。复用 Shared Kernel 与 S2b codec，禁止另写 float/日期/SET 编码。Python 持有 schema 演进、table role、dataset replacement、风险和表级业务 policy；Rust 返回其需要的行计数/诊断数据。

必须归入 owning Contract 的现行细则（本轮已在 Comparison/Ordered Diff/Risk 追加候选条文，A 节核收，独审后才生产切换）：

| 不变量 | 精确定义/源 | Contract owner |
| --- | --- | --- |
| 标量 | float/decimal 的负零归正零；NULL 用 null frame，不等于空串/0；typed float records text 是规范 bits_hex，不变十进制 | Shared Canonical Encoding；Comparison 引用 |
| 列与文本 | canonical identifier 仅 ASCII fold；行字段按 UTF-8 unsigned byte 序；字符串不 trim/normalize；JCS object key 按 UTF-16 code unit，不能与业务排序混用 | Shared Canonical Encoding/Comparison |
| keyed | 有效键优先级与缺失/重复/忽略/改变的诊断保持；共有列比较，新增列不产生 schema-change record；整表新增/删除无逐行记录 | Comparison、`row_encoding.py` |
| keyless | 明确允许时按完整投影行 digest 的 multiset 差异；重复次数保留。added occurrence 从 before count 起，deleted 从 current count 起，身份用 `_row_occurrence_digest`；不是 set 去重，不输出 modified | Comparison、`standard.py::_compare_keyless` |
| ordered | 稳定 gid、绝对 no、伪 gid/空白 provenance 按 G8（4,000,000,000–4,294,967,295）；无效键保持降级，不能用输入行号替代 no | Ordered Diff/Canonical Storage |
| LIS 并列 | before 顺序下共同实体的 current positions，最长严格递增子序列；等长取 before-index 序列字典序最小者；`_backbone_indices` 为当前证据 | Ordered Diff |
| 空白 | gaps 按相邻真实 identity 锚定；首尾 None 使用现有空字符串排序；区间/occupancy digest、位置和计数保持 `_blank_gaps/_blank_extension/_occupancy_digest` | Ordered Diff |
| 两种记录排序 | facts standard：kind、identity（缺省空）、changed_columns；facts ordered：kind、current_position or before_position or 0、identity。产物：kind、identity bytes、before/current optional-position（缺省0）、完整行 JCS 文本兜底；必须区分，不以 Arrow batch 到达顺序替代 | Comparison/Ordered Diff、artifacts `_record_sort_key` |

未变化 ordered：保留 planner 完整身份判断，在 assemble 的 table task 入口调用 `summarize_ordered_side(current, effective_pair_policy)`；使用本次共有列/规则，生成两侧相同 ordered/occupancy 摘要。不打开 before reader、不运行 LIS、不生成 records，不在上传时预计算，不往 manifest 加字段。

## 4. Arrow records 与 JCS

三族分别为 `standard-records/v1`、`ordered-records/v1`、`blank-records/v1`；contract metadata 为 `backend-vnext/comparison-records/v1`，`gateway-vnext.records.` 前缀的 family/schema_version/row_diff_detail_policy/contract_version 保持。下面 `?` 表示 nullable，其余 non-null；List 的 element nullable 保持现 schema，即使合法 producer 不输出 null element，也不得擅自收紧物理 schema。

```text
Scalar = Struct(kind:Utf8, text:Utf8?, raw_bytes:Binary?, boolean:Bool?,
                items:List<Utf8?>?, anomaly_json:Binary?)
Value = Struct(column_name:Utf8, value:Scalar)
Values = List<Value?>
Change = Struct(column_name:Utf8, before_value:Scalar?, current_value:Scalar?)
STANDARD（按此列序）:
 table_name:Utf8, record_kind:Utf8, row_identity:FixedSizeBinary(32)?,
 changed_columns:List<Utf8?>, before_values:Values, current_values:Values,
 field_changes:List<Change?>, diagnostics:List<Utf8?>
ORDERED:
 table_name:Utf8, record_kind:Utf8, semantic_kind:Utf8, entity_key_kind:Utf8,
 row_identity:FixedSizeBinary(32)?, before_position:Int64?, current_position:Int64?,
 changed_columns:List<Utf8?>, before_values:Values, current_values:Values,
 diagnostics:List<Utf8?>
BLANK:
 table_name:Utf8, record_kind:Utf8, semantic_kind:Utf8,
 interval:Struct(before_start:Int64?, before_end:Int64?, current_start:Int64?,
                 current_end:Int64?, row_count:Int64, interval_digest:FixedSizeBinary(32)?),
 before_occupancy:Int64, current_occupancy:Int64, diagnostics:List<Utf8?>
```

Scalar null 是 kind=null 且其余字段 null 的非空 struct；不得换成 struct null。integer/decimal 使用规范 text，float 使用 bits_hex；binary/bit 原字节；SET items 序列与 anomaly_json 的 JCS bytes 保持。detail policy 对 values/changes 的裁剪完全照现 `_record_to_row`，空列表与 null 不互换。排序先按 FULL 记录确定，再裁剪 detail（当前实现如此）。每族相同逻辑行重复检查保留，keyless occurrence 不能被误判重复。

JCS 内容为 `{kind:"comparison-records-content",family,schema_version,row_diff_detail_policy,rows:[...]}` 的规范字节；Binary/FixedBinary 在 JSON 中映射为 `{"bytes_hex":"小写hex"}`，不是 base64。Rust 流式向 SHA256 sink 写规范 envelope 与逐行对象；rows 之间单逗号，batch 边界不产生分隔符。对象字段按 JCS 顺序，列表保持顺序；禁止先构造全量 serde_json::Value。单行可变宽 payload、嵌套 list、排序 tie-break 编码也必须先计费。

producer 先建立全表排序索引，再按最终顺序输出 batch；不是宣称比较能 O(batch) 内存。输入 batch 可任意划分，输出 writer 固定重组为 1024 行 row group（末组不足），与现 writer 的 zstd、use_dictionary=False、schema metadata 和版本一致；不默认更换 large string/list。过大 offset/单行不能容纳则预算拒绝，不能截断。

Python 使用 Arrow C Stream/现有安全库导出 batch，`pa.Table.from_batches` 或 writer 等价列式入口直接写 Parquet；禁止 `from_pylist/to_pylist` 全表桥接。writer 完成后获取真实 raw SHA，publish manifest，再 closure，之后才 READY。移除本次新写 records 的整份 locate/decode/JCS 回读；保留 put/close/flush 异常、大小/count 校验、现有原子发布与小型 metadata 校验。失败不发布可用 closure，已写未引用文件走已有 cleanup。

真正读取（open/restore/bundle closure）仍由 Python 定位、raw SHA 与 Parquet reader 校验；逐 batch 把 Arrow 交 Rust 的 schema/count/JCS validator，结束前不暴露为已验证闭包。读取损坏、缺失、错误 metadata/schema/count/content、普通 I/O 均保持原失败边界。restore 的源属于真实读取；目标新写不为性能要求再完整读一次。不新建持久 validation token。

**逐字节比较分三层**：①逻辑行/JCS bytes 与 content_digest 必须相同；②manifest/业务 facts/surface/bundle 的冻结语义与 golden 不变（scope refs 按既定规则绑定）；③Parquet raw SHA 代表文件本身，不能用①相等冒称③相等。先复用 writer 参数/1024 row groups验证已有 raw golden；若同 Arrow 输入仍无法保 raw，提交最小反例、writer差异及受影响 manifest/closure/bundle 清单给 Owner；选择保持 writer 或批准格式变化，推荐前者。禁止更新 golden 抹平差异。

## 5. 风险与单操作去重

风险引擎仍在 Python。table facts 负责计数/schema/degraded/composite 标识；行规则通过 `iter_record_batches(table,family,columns)` 消费同一内存 owner，仅提取 kind、identity、changed_columns、规则需要的 values/positions。`_facts.py` 不再重建整个 ComparisonRecord tuple；`has_visible_change` 改用等价记录 count/事实。无行规则的计数风险不读 records。需要多遍时重放内存批引用，不读刚写的 Parquet。

保持 `_engine.py` 的表排序、规则顺序、severity/reason/target、标注 ID、per-table/pair 上限、截断/降级语义；风险消费顺序采用现 facts 顺序的索引视图，不能错误沿用产物排序。先产生不套 pair cap 的有界单表候选标注，再在 pair 汇总按原遍历顺序执行 cap、编号和组合信号规则；达到原限制时照原失败/降级行为，不静默丢弃。若移除 pair cap 使单表计算超过现 per-table/time预算，照原策略结束，不能借去重扩大上限。

去重 map 仅存于一次 operation 的 context，覆盖 FULL 两 pair。纯输入 key 必须包括：方向与两侧内容身份（内容 digest + schema/业务 schema/比较 schema + row count + canonical/projection/scalar版本 + row layout/存储身份）、effective keys、共有/排除列、完整 comparison/risk rules 主体及版本、ordered policy、存储规则、comparison mode/options/detail/artifact scope、算法/记录格式版本及输入 authority。不能只靠 version 或内容 digest。

输出是未绑定显示名的纯计算结果/未套 pair cap 的单表风险候选；表名、显示名、标注编号、pair cap、组合信号在当前汇总绑定。**完整身份仍保留 schema 内含表名**：S2b 业务 schema 与 projection digest 可能绑定名称，不重新定义 nameless digest；不同表名因此 miss 是正确结果。相同任务在多个 pair 重复才是可靠命中场景。绑定后重算含 table_name 的 records content_digest/manifest 和 facts digest，不跨表直接复用带表名 bytes。先用真实完整身份列 hit/miss 原因再报告收益。

map 不存失败、取消、超时或半成品；命中仍检查取消/截止与消费者预算。owner 共享只计一次 backing buffers，风险/写入/重绑定分配单独计费；超预算停止该计算，不留不可见引用。operation 结束全释放。验证开关只在测试注入，不加部署开关。S5 才设计跨操作缓存、TTL/持久引用、History 回填与 H1/H2/H3。

## 6. 生命周期、资源与失败

Arrow/mmap owner 经现 S2b handle 生命周期跨 FFI 持有；Rust detach/GIL 释放期间不得借用可失效 Python buffer。输出 batches 持有独立 Arc/安全导出 owner，最后一个 Python/Rust 消费者释放才退预算；取消、writer错误、生成器提前关闭也释放。FFI panic/异常转换、native crash 外部恢复沿现 adapter/runtime；不把 panic 当普通表降级。core 无文件 I/O、first-party unsafe、无未受限 Rayon fan-out。

按 `M >= pinned inputs + indexes/sort/LIS + record buffers + JCS scratch + per-thread temporaries + writer buffers/spool/raw copy + risk annotations + retained pair results + dedup live outputs` 准入；映射文件不等于零 RSS，Arrow slice 共用 backing 按实际 owner 计费。先在分配前上界准入，增长前追加检查，不能执行后记账。FULL 第一 pair 留存与第二 pair计算重叠计入；消费者完成即释放大 records，保留必要小 facts/refs，不照搬现 Python envelope 一直保到 operation 结束。

初始 N1/M24 不变；06 focused 建议 Cargo jobs4/pytest4，与 N 分开。记录 charged high-water、RSS/cgroup及 writer 高水位，不能把它们相加冒总峰值。若 W4 全变化或 FULL 超 M，给表行数/宽度、分项预约、实际峰值与拒绝位置，优先减少重复驻留，再由 Owner 决定范围/配置，不静默抬 M。

取消/截止在导入批、索引构建、排序比较循环、LIS、记录/JCS批、writer与风险批检查；复用现 deadline 与错误码。保持 effect 前纯重算 drain 重排队（DC88）、冻结四状态、已有事务/CAS、保护引用和 READY屏障。不得把派生去重结果升级成恢复状态机。

## 7. 变更与覆盖移交清单

| 对象 | S3 责任/退出证据 |
| --- | --- |
| Rust comparison/records、compute-python adapter；backend comparison/pair_pipeline/risk | 上述生产接入；粗粒度 Arrow 输入输出、实际调用计数 |
| Comparison / Ordered Diff / Risk owning Contract | A 写入 §3 现行语义、批接口和单操作纯函数；Risk pair cap/编号绑定；不授权 S5 cache |
| comparison-bundle / comparison-surface / snapshot-table-access | 核对三族 schema、digest/closure/读取边界；仅必要内部接口说明，HTTP/tar不变 |
| Shared Canonical Encoding、Canonical Storage、artifacts.md、operation lifecycle | 引用既有 scalar/schema/保护/失败条款；不改规范身份或恢复状态 |
| `test_comparison_{standard,ordered,blank,records,artifacts,batch_boundary,canonical_domain,rule_roles,planning,replacement}.py` | 业务断言迁到独立固定向量与生产adapter；planner/schema/模式测试继续 Python |
| `test_risk_evaluation.py/test_risk_contracts.py` | 保留规则预期；改 Arrow 输入；开关一致性、cap边界与标注排序 |
| `test_ordered_compare_compose.py/test_ordered_submit_bisect_compose.py`、Preview/History编排测试 | 唯一生产路径、实际读/派发/调用计数、冻结/Submit回归 |
| `vnext/rust/fixtures/vectors/comparison/records/*` 及现 comparison/bundle golden | 冻结 expected；新增向量必须由 Contract 手算/已核 Python基线给出来源，不能由新 Rust 自证 |

删除顺序：临时差分 → Arrow adapter接入 → 验证通过 → 删除 Python keyed/keyless/ordered热点、`_record_to_row` 热路径和整份读取JCS实现、临时引擎选择及重复测试；保留仍有独立 consumer 的 planner、DTO、小metadata序列化、存储mutation与Submit规划器。删除前逐 symbol 搜索实际消费者，形成“断言→新 owner”的 handoff 表；不能留改名 oracle。原型 records reader 的固定向量移交新流式 validator后删除旧全量实现。

## 8. 外部边界与待决事项

FE3b 稳定面：HTTP接受/查询、pair_id与FULL两个pair、surface/bundle digest、三族Parquet/manifest/closure、tar/PAX下载、审核/归档核验/关闭、submission_disposition与工作区占用指针。S3 不改这些语义；前端最新核对§9已关闭PAX预算与历史提示澄清，不重复提问。任何实际接口变更列出字段/consumer/制品例子，由 Owner 转前端；不猜会话ID、不改前端文档。

S4 保留存储键全保留列diff、SQL直通、阈值/批量规则复测；S3只给可复用投影/identity接口。S5保留跨操作diff/risk缓存、引用登记、History按表拼接并发及回填。原基准只交换适用共享修复/输入身份/证据引用，不修改冻结worktree/镜像/卷。

当前没有需要立即改变核心方案的 Owner 问题；以下为启动/退出决策，不预判批准：

| 决策场景与证据 | 影响与选项 | 推荐 |
| --- | --- | --- |
| 比较/记录/风险均替换，S2b原t4沿用只证明旧算法 | 最终真实数据范围可选全部 fresh 或经具体影响证明部分沿用 | t1–t4差分；05 fresh t1–t3功能旅程，CT108 t4待窗口，退出前DC33确认；不默认继承S2b的06例外 |
| CT108原基准独占，S3要求W3/W4起测 | 可等窗口，或先06诊断但正式性能仍未知 | 先06小型分段诊断；经Owner协调CT108窗口；无窗口列待补项及退出影响，不取消S3验证 |
| 1024组/现writer仍出现raw golden差异（尚未发生） | 保持writer或批准产物格式变更，后者可能影响bundle | 保持现格式；仅有最小反例时升级决策 |

这些未知项没有被记成通过。设计独审可提出明确问题；设计者负责决策性澄清，不承担实施日常催进度。
