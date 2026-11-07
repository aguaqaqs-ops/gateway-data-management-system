# Phase 6 S3 A：语义、接口和独立预期交接

状态：A 实施候选，待 06 focused 验证和独立复审。依据固定设计 `d49bb126`、kickoff §7.1、[Comparison](../../../contracts/comparison.md)、[Ordered Diff](../../../contracts/ordered-diff.md)、[Risk](../../../contracts/risk.md)、[Shared Canonical Encoding](../contracts/shared-canonical-encoding.md) 及当前已冻结 Python 控制流。本文只固定 B/C/D/E 的可验收输入与预期，不作为新的生产路径或 golden。现有 S1b 比较、风险、bundle golden 和三族 Parquet 固定向量均保持原值。

## 1. 单表接口和三个逻辑视图

内部接口为 `compare_table(input, context) -> TableComputation`；`summarize_ordered_side(current, effective_pair_policy, context)` 是不同 `task_kind`。`input` 必须携带有向两侧 Arrow owner/stream、完整 snapshot/table/schema/row layout 身份、有效比较列与键、规则正文和版本、模式/detail/scope/authority；`context` 携带现有 operation 共享池、M 剩余额度、取消和单调截止时间。进入前预约输入 owner、索引、排序、LIS、records、JCS scratch、writer 和同时存活的 FULL 前一 pair。增长前再检查；资源拒绝、取消和异常不返回半成品。输出 owner 在最后一个 facts 摘要、writer、risk 消费者结束后释放，跨 pair 保留只服务于已知同 key 的后续消费者，并计入 M。

`TableComputation` 的记录列为未裁剪的三族 Arrow 数据，提供 facts 顺序索引、artifact 顺序索引、额外事实列和逐族 count/content digest。对外只发布小型 facts、manifest/ref、surface 和 bundle。无整份 Python row tuple 兼容属性，operation-local handle 不进入 checkpoint/HTTP/持久 DTO。

Risk 的只读借用签名为 `iter_record_batches(table, family: STANDARD|ORDERED|BLANK, columns: tuple[str,...], order: FACTS) -> Iterator[RecordBatch]`，不是返回 `Table` 或全量 tuple。Risk 显式传 `order=FACTS`；producer 另用 `ARTIFACT` 索引，二者不能共用默认顺序。每批只包含所请求的合法列，保留 Arrow 类型，跨 batch 拼接后严格等于该族全局 facts 序；未知列、family 或已释放 owner 拒绝。可重复遍历供三种 row kind 规则消费；每批借用同一 operation owner，迭代提前关闭/异常/取消及最后消费者退出时释放借用和预算。`record_count(table,family)`、`has_records(table,family)` 返回精确计数/布尔存在性；`ordered_degraded(table)` 合并 ordered extension status、TABLE_DEGRADED 记录存在性和 diagnostics，不转元组。`has_visible_change/_risk_scope` 用 STANDARD 存在性，ordered unsupported 用合并布尔值；无行风险不打开批迭代。closure 仍通过现 `records_access` 当前 pair 验证。具体接口归属为 C 的 Arrow adapter 与 D 的 Python Risk 消费。

| 逻辑视图 | 输入、顺序及字节口径 | owner/消费者 |
| --- | --- | --- |
| facts table/core | `row_encoding._table_digest_payload` 全字段：table 名、status/content、schema changes、before/current 与增删改/suppressed 计数、standard/ordered/blank 完整记录。standard 按 `(kind, identity or "", changed_columns)`；ordered 按 `(kind, current_position or before_position or 0, identity or "")`；blank 保留现扩展顺序及额外 `entity_key_kind`。值为 canonical scalar/collection frame 的小写 hex，null/省略不互换。table digest 为完整 table JCS；core digest 在 summary 已知后写完整 `{algorithm_version,kind,summary,tables}` JCS，tables 保留当前 facts 表序，不拼 table hashes。 | Rust 流式 JCS sink；Python 提供小 metadata/summary；`standard._build_facts` 只组小 envelope。`replacement.py` 保留独立 dataset-replacement/v1 envelope 和空 records。 |
| records artifact | `standard-records/v1`、`ordered-records/v1`、`blank-records/v1` 按完整记录的 `(kind, identity bytes or empty, before_position or 0, current_position or 0, full-row JCS text)` 排序，再按 detail policy 裁剪。JCS envelope 为 `comparison-records-content`/family/schema_version/row_diff_detail_policy/rows；binary 为 `{bytes_hex: lower-hex}`。batch 切分不影响逗号、顺序、count/content digest。Parquet raw SHA 只由实际文件产生。 | Rust records builder/JCS、Python Parquet writer 与 manifest/closure；真实 open/restore 用 Rust Arrow 批 validator 重算 schema/count/content，Python 检 raw。 |
| risk | 小 facts + standard facts 序的最小列 kind/identity/changed_columns、必要 values/positions；无行规则时不取 records。ordered 降级还取 extension status、`TABLE_DEGRADED` 存在性及 diagnostics。规则遍历和 filtered Emit 均保留。 | Python Risk；candidate 可在同一 operation 重放，当前 pair 的 cap/编号/绑定/closure/时间检查每次执行。 |

三族 Arrow 物理 schema **严格等于**现 `comparison/artifacts.py::_schema_for` 和 `rust/gateway-compute-core/src/records.rs`：公共 `Scalar=Struct(kind:Utf8,text:Utf8?,raw_bytes:Binary?,boolean:Bool?,items:List<Utf8?>?,anomaly_json:Binary?)`，`Value=Struct(column_name:Utf8,value:Scalar)`，`Values=List<Value?>`，`Change=Struct(column_name:Utf8,before_value:Scalar?,current_value:Scalar?)`。standard 列依次为 `table_name,record_kind,row_identity,changed_columns,before_values,current_values,field_changes,diagnostics`；ordered 为 `table_name,record_kind,semantic_kind,entity_key_kind,row_identity,before_position,current_position,changed_columns,before_values,current_values,diagnostics`；blank 为 `table_name,record_kind,semantic_kind,interval,before_occupancy,current_occupancy,diagnostics`，其中 interval 依次为 `before_start?,before_end?,current_start?,current_end?,row_count,interval_digest?`。`row_identity`/`interval_digest` 用 `FixedSizeBinary(32)?`，positions/counts/occupancies 用 Int64，列表元素 nullable 维持原样；Scalar 的 SQL NULL 是非空 struct `kind="null"` 加其余 null 字段。metadata 的 `gateway-vnext.records.` 前缀及 contract/family/schema/detail 四项、zstd、`use_dictionary=False`、固定 1024 row group 不变。不能把 BLANK facts 私有 `entity_key_kind` 加进 Parquet schema。

完整身份的实例：`t1` 和 `t2` 行字节、行数、规则和方向都相同，但业务 schema/projection schema 中 `table_name` 分别是 `t1`/`t2`。二者 key 不相等，必须 miss；不能剥离名称后声称 hit。FULL 的 baseline→initial 与 initial→modified 是不同有向输入；真实 0 hit 合法。相同完整 key 的人工重复任务才证明 map 命中；绑定后含表名 facts/records/manifest digest 重算。`task_kind=SINGLE_SIDE_ORDERED` 不与行比较共享条目。B/C 须记录 hit/miss 原因、额外保留不足安全 miss、消费者预算及最后引用释放；不承诺性能收益。

## 2. 实际消费者与退出归属

本清单按当前 backend `src`、benchmarks、Rust example 的 `.records`、extension `.records`、私有 digest helper、records 读取搜索核对；`records_closure.records` 是小型 artifact 条目，不能与行 tuple 混淆。

| 当前访问点 | 所需信息与迁移/删除 owner | 验收断言 |
| --- | --- | --- |
| `comparison/standard.py::_with_table_digest/_build_facts`、`row_encoding.py::_table_digest_payload/_record_digest_payload/_ordered_extension_digest_payload/_blank_extension_digest_payload` | B/C 以完整 facts payload JCS 流与小 metadata 替换行 tuple 热点；`_value_digest_payload` 的 canonical frame 语义仍需拥有。 | table/core/comparison digest 与 S1b golden 等值；core 输入为完整 table payload 字节。 |
| `comparison/replacement.py` | B/C 保留独立 replacement 小 metadata helper、空记录与无 closure；不把它接成 detailed row task。 | replacement envelope/digest 不变。 |
| `comparison/artifacts.py::_records_by_family/_record_to_row/_publish_family/_record_sort_key/_content_digest` | C 用未裁剪 Arrow、artifact 序索引、detail 投影和流式 JCS 替换；移除生产整份 row dict 路径。 | 三族每字段/nullable/metadata、1024 row group、JCS/content/raw 分层、重复记录拒绝。 |
| `comparison/artifacts.py::open_records_closure/read_records_artifact/restore_records_closure` | C 保留 Python store 定位、raw/ref/manifest 和 I/O 失败；Rust/PyO3 批 validator 校 schema/count/content。`read_records_artifact` 当前全表 `tuple[dict]` 只在测试直接使用，测试迁 Arrow batches 后删该全表接口。 | raw、schema、count、content 各类损坏 fail closed；新写目标不整份读回，restore 源真实校验。 |
| `risk_evaluation/_facts.py::extract_risk_facts/has_visible_change/_risk_scope/_ordered_unsupported` | C/D 将 `records=table.records` 改为 handle/count/存在性，保留 schema/degraded record 可见性与 ordered 三来源；不只看增删改计数。 | 仅 schema、TABLE_DEGRADED、ordered diagnostics 也保留风险分支。 |
| `risk_evaluation/_engine.py::_emit_row_risks/未知 target 循环/_require_records_closure` | C/D 按 facts 序投影最少列，保留三种 kind 顺序、匹配/抑制/不可用、未知 target 和当前 pair closure 校验；由 Python 重放 Emit/control steps。 | §3 向量；不从 Parquet 读回当前 records；0 全份 tuple 转换。 |
| `surface_assembly/_assembly.py`、`pair_pipeline.py`、`preview_jobs.py`、History pipeline | C/D 只消费小 facts、record counts、extension metadata、closure entry/ref；Preview/History 的 pair、风险、surface 业务编排不换 owner。 | FULL 两 pair/History、closure 完整与 READY 屏障。 |
| `bundle_assembly/_assembly.py`、`benchmarks/bundle_tar.py::open_records_closure` | C 保持 bundle 原 raw/ref closure 边界；benchmark 的 `open_records_closure` 是真实完整 records 验证入口，随新 validator 接线。冻结基准 worktree/产物不改。 | 不把每次下载升级为全份 Parquet 语义解码；真实 open 仍逐 batch 完整验证。 |
| `benchmarks/p6_v1_ordered_diff.py`、`benchmarks/real_dump_census.py` | E 在生产 adapter 稳定后，把直接遍历三族 `.records` 或 `compare_plan/table_fact.records` 的活动工具改为批/计数接口；若只服务旧原型，删工具。原固定参考线工作树不改。 | 工具不保留隐藏的整份 tuple oracle；活动测量口径注明迁移。 |
| `rust/gateway-compute-core/examples/ordered_compare.rs` | B 删除/迁移旧 Vec 原型 example，若保留则使用新 kernel 入口；旧原型只可作临时差分支持并在 E 删除。 | Cargo all-targets 无旧生产路径。 |
| `tests/test_comparison_{standard,ordered,blank,records,artifacts,batch_boundary,canonical_domain,rule_roles,planning,replacement}.py`、`test_risk_evaluation.py/test_risk_contracts.py` | B/C/D 把行期望移到独立向量与实际 adapter；保留 planner/schema/业务规则测试，删除被取代实现的 mock/测试；E 核无临时 oracle。 | 断言与唯一 owner 对齐，冻结 golden 不改。 |

`snapshot_materialization/_digest.py::_table_digest_payload` 是 snapshot 专属同名 helper，S3 不接管。`application/preview_jobs.py`、`surface_assembly` 和 `risk/_engine.py` 中遍历 `closure.records` 的位置消费的是小型 closure entries，继续保留。Rust `read_records_parquet_v1` 现仅由 Rust 固定向量使用，尚未证明 backend 真实读取边界；C 接 PyO3 adapter 时须通过 backend 测试。

## 3. 独立预期和覆盖移交

下表的 expected 来自上述 owning Contract、现 `row_encoding.py`/`standard.py`/`ordered.py`/`artifacts.py`/`risk/_engine.py` 的冻结行为，或现 S1b golden；**不从新 Rust 输出生成**。`test_comparison_s3_contract_vectors.py` 已把风险关键分支落成小 facts 单元断言，其余交 B/C/D/E 在实际 adapter 可用时接入。测试输入按单一业务维度增量展开，避免同构用例堆叠。

| ID / 归属 | 固定输入 | 独立 expected 与来源 |
| --- | --- | --- |
| C1 / B | typed float `-0/+0`、decimal 负零、NULL/空串/0、UTF-8 非 ASCII 两列、JCS object key `\ue000` 与 `\U00010000`。 | 数值负零相等，NULL 分别不等于空串/0；业务列按 UTF-8 byte 序，JCS key 按 UTF-16 code unit（supplementary key 在 `\ue000` 前）。float records text 为规范 bits_hex；Shared Canonical Encoding + Comparison。 |
| C2 / B | keyless before 同投影行 2 份、current 3 份；反向再比较。 | 正向仅 1 个 ROW_ADDED，occurrence=2；反向仅 1 个 ROW_DELETED，occurrence=2；无 ROW_MODIFIED；Comparison multiset 条文与 `standard._compare_keyless`。 |
| C3 / B | ordered 共同实体 before `[a,b,c]`、current 绝对位置 `[2,1,3]`。 | 等长 LIS 取 before-index 字典序更小的 `[a,c]`，而非 `[b,c]`；Ordered Diff 与 `_backbone_indices`。空白首尾锚为 None、排序时空串，真实锚相邻不跨界；GID/no 绝对位置、伪 gid G8 范围不变。 |
| C4 / B/C | 只有新增列；另例删除列或有效键改变；整表新增/删除。 | 新增列按共有列比较，无 SCHEMA_CHANGE record；删除列/键变按原诊断与降级；整表新增/删除无逐行 records。Comparison v3。 |
| C5 / C | 每族一条含 nullable/nested 值；同一逻辑表输入按 1、7、1024+1 任意 batches；三族各一次 detail policy。 | Arrow schema/metadata 与本页 §1 精确相同；逻辑行/JCS/content digest 不受 batch 划分；输出 row groups 固定 1024/末尾余数；raw SHA 单独比原 writer，不能由 content 推断。`artifacts._schema_for/_content_digest`、现固定 Parquet 向量。 |
| C6 / C | 修改一份 Parquet 的 raw、schema metadata/nullable、record count、单行 content；独立轮次。 | open/restore 各类损坏分别拒绝，不发布已验证 closure；`artifacts._decode_records` 当前读侧承诺。真实 adapter 测，不只 Rust fixture。 |
| R1 / D | table cap2/pair cap3；A 三 Emit、B 两 Emit、C 一 Emit。 | A 第三 Emit 抛 table budget，A 降级标注 count1 **不计** pair total；B 后 total2，C 后 total3，自然结束，最终三表 count `(1,2,1)`、有 closure。Risk §S3 与 `_engine.evaluate_risk` except 分支；已落可执行测试。 |
| R2 / D | 同 R1，但 A 诊断两项且 `max_diagnostics_per_table=1`。 | A 预检正常返回 degraded，计 pair total1；B 后 total3；C 首 Emit 触 pair budget，丢全部部分标注，三表 count0/诊断 `max_annotations_per_pair exceeded`，无 closure。Risk §S3；已落可执行测试。 |
| R3 / D | pair 剩余0；刚好 K 后自然结束；K+1 个可见或等级过滤 Emit；table/pair 同时触界。 | 剩余0 的下一 Emit 即 pair 超限；刚好 K 自然结束成功；K+1 即使过滤也超限；双界 pair 优先，丢整 pair 部分标注。`_engine.emit` 在过滤前检查；过滤分支已落测试。 |
| R4 / D | 相同完整候选，首次/命中时 pair 剩余不同；首次 closure 有效，命中时 closure 缺失、comparison digest 错、facts digest 错；closure check 前后各一上限触发例。 | 当前 pair 重新套 cap/编号/closure/clock，不能复用前次结果或验证结论；closure check 到达则按相应原失败分支，若前面的 Emit 已超 pair cap 则直接 pair degraded。Risk §S3 与 `_require_records_closure`。 |
| R5 / D | 普通表与 `composite_signal_point` 相同增删改计数、ordered degraded 与未知 target 各一。 | 普通表按表/行/未知 target 顺序；composite 只 emit 一项 UNKNOWN，不走普通分支；ordered degraded 合并 status/record/diagnostic 三来源。`_engine._evaluate_table`、`_facts._ordered_unsupported`。 |
| K1 / D | 相同完整任务两次；只变方向、规则正文/版本、schema/key/scope、RiskOptions/diagnostics/selected tables、含名称 schema 的 `t1`→`t2`。 | 仅完全相同命中；上述各维 miss，包括 `t1`/`t2`。on/off 的 facts/records/risk/bundle 等值按各表重绑定后的摘要比较；S3 design §5/9.2，Comparison/Risk Contract。 |
| O1 / B/D | unchanged ordered，before reader 计数器与当前 reader 计数器。 | 当前侧仅一次单侧摘要，before=0、LIS=0、records=0，两侧 ordered/occupancy digest 相同；Comparison/Ordered Diff。 |

### A 在 06 的固定向量执行映射

下列 nodeid/fixture 是 A 目前可执行的 Contract 证据。C/D 接入后复用这些 expected，改调用新 PyO3 adapter，不以新 Rust 输出回写预期。`C6` 的私有 Python validator 测试只是当前读侧基线；C 必须把同一损坏输入迁到实际 adapter，并删除被替代的私有测试入口。

| ID | 06 nodeid / 现有 fixture | 固定 expected 与来源 |
| --- | --- | --- |
| C1 | `shared_kernel/tests/test_canonical_cases.py::test_canonical_case_matches_python_reference` 读 `vnext/fixtures/vectors/shared-kernel/canonical-encoding/v1/{scalar,digest,jcs}.jsonl`；新增 `shared_kernel/tests/test_jcs.py::test_canonicalize_jcs_supplementary_key_precedes_later_bmp_key`；现 `shared_kernel/tests/test_framing.py::test_encode_row_sorts_by_canonical_utf8_bytes`。 | case `scalar.float64.negative-zero` frame base64url `FAgAAAAAAAAAAA`，`scalar.decimal.canonical-zero` 为 `EgEw`，`scalar.null.empty` 为 `AAA`、`scalar.string.empty` 为 `IAA`，多字节 `你好` 为 `IAbkvaDlpb0`；`digest.row.mixed-fields-permuted-{a,b}` 同为 `AgFhAQEBAWIAAA`、`sha256:401578531a0add4dd48daa932190b0f1fff21f90cd2378a112c32199b1a80f39`。补例 U+10000 在 U+E000 前：JCS bytes `7b22f0908080223a312c22ee8080223a327d`；Shared Kernel v1 固定向量/UTF-16 Contract。 |
| C2 | `backend/tests/test_comparison_standard.py::test_raw_primary_key_fallback_compares_keyless_rows_as_a_multiset`；`backend/tests/test_comparison_s3_contract_vectors.py::test_keyless_third_copy_uses_frozen_occurrence_two_identity`。 | 现集成例 `(added,deleted,modified)=(1,1,0)` 且无 KEY_DEGRADED；纯 occurrence=2 的前缀 bytes 为 `keyless-row-occurrence:v1\0` + 上述 frozen row digest ASCII + `02`，再按 `gateway-vnext:row:v1\0` 域 SHA，结果 `sha256:a30dfdfae0f29e7d4a7da411578d351fac59a100052dc8fd2135f6940f4ba2bb`。before 两份/current 三份时只加 occurrence2，反向只删 occurrence2；Comparison §S3 与现 `_compare_keyless`。 |
| C3 | `backend/tests/test_comparison_ordered.py::test_backbone_is_the_earliest_longest_increasing_run_in_before_order`、`::test_backbone_reports_moves_blank_intervals_and_summarised_shifts`；`backend/tests/test_comparison_blank.py::test_blank_interval_shift_is_delete_and_insert_without_move_pairing`。 | positions `(2,1,3)` 的主干索引 `(0,2)`（before `[a,c]`）；空白区间 shift 为 delete+insert，无 move 配对；Ordered Diff §S3 与冻结 `_backbone_indices`。 |
| C4 | `backend/tests/test_comparison_standard.py::test_added_columns_compare_common_columns_without_schema_status_or_record`、`::test_removed_column_is_classified_separately_from_incompatible_schema`、`::test_changed_effective_key_degrades_without_positional_fallback`、`::test_keyless_table_addition_is_table_level_without_row_records`、`::test_whole_table_deletion_is_table_level_without_row_records`。 | 新增 note：`COLUMNS_ADDED`、selected `(id,name)`、current-only `(note)`、无 schema record；删除列 `COLUMNS_REMOVED`；key 变化降级；整表增删无逐行 records。Comparison v3 与现断言。 |
| C5 | Rust `records::tests::python_{standard,ordered,blank}_vector_has_the_same_logical_digest` 读 `vnext/fixtures/vectors/comparison/records/{standard,ordered,blank}-v1.parquet.b64`；`backend/tests/test_comparison_artifacts.py::test_publish_uses_independent_ordered_and_blank_artifacts`、`backend/tests/test_comparison_records.py::test_records_preserve_null_binary_float_decimal_and_temporal_values`、`backend/tests/test_comparison_s3_contract_vectors.py::test_records_writer_uses_1024_rows_then_one_row_group`。 | 冻结 `(family,version,count,content_digest)` 分别为 `(STANDARD,standard-records/v1,1,sha256:22bfb26abb0aaeb3d279cdae0614d2733bebbd8cdf8021cfa6751c690db561d4)`、`(ORDERED,ordered-records/v1,1,sha256:887e686f96583a28c31f82788608ebd10491b80eb98dc9ab2ada7389ec50468b)`、`(BLANK,blank-records/v1,2,sha256:5f7d095129a4fdbeba84392206fa857740ecdca6b466f9cc8177d2264bf9c17a)`；detail 均 FULL，输出组 `(1024,1)`；Rust 现固定 Python Parquet 向量和 `artifacts._write_parquet`。raw SHA 另比原 fixture 文件，不以 content 推导。 |
| C6 | `backend/tests/test_comparison_artifacts.py::test_corrupt_parquet_is_rejected_before_closure_is_consumed`、`::test_reopen_rejects_records_over_per_table_limit_before_materialization`；新增 `backend/tests/test_comparison_s3_contract_vectors.py::test_records_fixed_vector_rejects_independent_semantic_corruption` 读 standard-v1 fixture。 | raw 错拒绝；schema metadata 错 `schema mismatch`、同 schema 0 行对期望1行 `count mismatch`、同 schema 改 ROW_MODIFIED 为 ROW_ADDED 对冻结 `sha256:22bf...` 得 `content digest mismatch`。这三种变化独立重写 Parquet，防止 raw 校验遮住语义校验；现 `artifacts._validate_parquet_bytes` 承诺。 |

Risk 纯候选不是最终标注列表。每次消费先做当前 pair 诊断预检，逐事件执行上限→等级过滤→编号/append→原时间检查；closure 控制步骤在原位执行。达到 cap 提前停止时的序列不完整，不得缓存。若候选存储超 M，放弃额外缓存并继续当次惰性求值，不使本来可执行的业务计算失败。R1/R2 的正常返回与异常分支不同，是风险去重实现验收的最小反例。

## 4. 验证与边界

A 的 06 focused 命令（测试者在 clean、已提交 worktree 与已预填充离线环境执行，先 `ssh -o BatchMode=yes ct107-gw-dms-06 'echo OK'`；下列为按包顺序的最小 nodeid 集，测试者另跑阶段要求的五包 ruff/mypy）：

```bash
cd vnext/shared_kernel
UV_OFFLINE=1 ../scripts/uv-consume.sh -C . run pytest -q tests/test_canonical_cases.py tests/test_jcs.py::test_canonicalize_jcs_supplementary_key_precedes_later_bmp_key tests/test_framing.py::test_encode_row_sorts_by_canonical_utf8_bytes
cd ../backend
UV_OFFLINE=1 ../scripts/uv-consume.sh -C . run pytest -q -n 0 tests/test_comparison_s3_contract_vectors.py tests/test_comparison_standard.py::test_raw_primary_key_fallback_compares_keyless_rows_as_a_multiset tests/test_comparison_standard.py::test_added_columns_compare_common_columns_without_schema_status_or_record tests/test_comparison_standard.py::test_removed_column_is_classified_separately_from_incompatible_schema tests/test_comparison_standard.py::test_changed_effective_key_degrades_without_positional_fallback tests/test_comparison_standard.py::test_keyless_table_addition_is_table_level_without_row_records tests/test_comparison_standard.py::test_whole_table_deletion_is_table_level_without_row_records tests/test_comparison_ordered.py::test_backbone_is_the_earliest_longest_increasing_run_in_before_order tests/test_comparison_ordered.py::test_backbone_reports_moves_blank_intervals_and_summarised_shifts tests/test_comparison_blank.py::test_blank_interval_shift_is_delete_and_insert_without_move_pairing tests/test_comparison_artifacts.py::test_publish_uses_independent_ordered_and_blank_artifacts tests/test_comparison_artifacts.py::test_corrupt_parquet_is_rejected_before_closure_is_consumed tests/test_comparison_artifacts.py::test_reopen_rejects_records_over_per_table_limit_before_materialization tests/test_comparison_records.py::test_records_preserve_null_binary_float_decimal_and_temporal_values
cd ../rust
CARGO_NET_OFFLINE=true CARGO_BUILD_JOBS=4 cargo test -p gateway-compute-core --locked --offline records::tests::python_
```

本 A 轮未改 Docker/Compose、依赖或 container-only runtime。`Container rebuild required: no`；当前 HEAD 的容器门禁状态为 `deferred`，最后已验证 image revision/source-tree 及执行点由阶段协调者填写，不能把祖先镜像写成当前 HEAD 已通过。B/C/D 的生产接入、差分、真实数据、容器/权威门禁及最终 golden 对照按 kickoff 的后续节执行。
