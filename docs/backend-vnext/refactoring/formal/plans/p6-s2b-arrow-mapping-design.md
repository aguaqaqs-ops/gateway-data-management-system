# S2b 规范表 Arrow 映射 v1（技术候选）

状态：2026-11-06。技术候选已按 S2a 退出源码重核；固定候选 `1a4adaae05` 已通过[独立技术审核](p6-s2b-kickoff-review.md)，Owner 已以 DC85 批准 kickoff 及 A 节；实施范围见 A 任务单，后续切片不自动开工。

来源：DC46/DC47、[P6 设计 §8](p6-design.md#8-s2b上传侧数据路径与规范表存储)、[DC76](p6-s0-owner-decisions.md#dc76-s2b-输入约定与映射准备)、[DC84](p6-s0-owner-decisions.md)。S2a 源码基线为 `p6-s2a-exit^{commit}=53b676a6298d408ccda3a85ee73c7ea223a2311a`；本轮设计候选 main 为 `d368413861dbcce10691fb65e8dbaba2a208af68`。`business_schema_digest_of` 已核实列序无关但包含 `table_name`；不改变既有业务摘要，不承诺跨表名去重。

## 1. 已确认的业务前提与范围

- owner 确认输入 SQL dump 保证按 UTC 导出。TIMESTAMP 按现行 UTC 语义解释；DATETIME 仍是 civil value，不随机器时区转换。此约定不是新增时区推断或转换功能。
- 来源、类型与业务规则沿用现有数据；已有少数 SQL 文件约 100 MB，比目前约 70 MB 的大样本更大。约数是业务容量输入，不是已校验文件尺寸、新硬上限或额外性能门槛。
- 现有 parser 的文件上限 512 MiB，以及单表/总行数、单语句、单字段等独立预算不变。文件未超限不等于其他预算满足。100 MB 真实文件可留存供必要时核对，当前不是映射定稿的必需材料。
- 本方案只固定 backend 内部规范 IPC。parser 输出、Repository wire 与客户端 Parquet 保持各自 owner；不把三种物理映射混为一个接口，不建立旧格式兼容层。

## 2. 类型映射

映射输入为业务物化、规范投影后的声明 schema 和合法值；映射不决定业务列选择、有效键、伪 gid、行排序语义或诊断分类。

| 规范逻辑类型 | IPC 物理类型 | 值与声明的约束 |
| --- | --- | --- |
| signed / unsigned integer | Int64 / UInt64 | 按声明位宽校验范围，保留 signedness；不因物理拓宽而扩大接受范围 |
| boolean | Boolean | 仅声明布尔；普通整数和 BIT(1) 不自动转布尔 |
| FLOAT / DOUBLE | Float32 / Float64 | 沿用规范舍入、负零归一、subnormal 保留及非有限拒绝；FLOAT 不经 binary64 中间舍入 |
| DECIMAL | Utf8 | 规范十进制文本；不转浮点，precision/scale 保留在 schema；不以文本字典序替代数值比较 |
| CHAR / VARCHAR / TEXT | Utf8 | 保留已接受的精确文本；不 trim、case-fold 或 Unicode normalization |
| ENUM | Utf8 | 声明标签，非 ordinal；首版不用 dictionary 编码 |
| JSON | Utf8 | 沿用现有检查及文本保值；不新增 JCS、键排序、空白删除或结构等价语义 |
| DATE / DATETIME / TIMESTAMP / TIME | Utf8 | 沿用规范文本；TIMESTAMP 为 UTC，DATETIME 不转换；TIME 是可负且可超过 24 小时的 duration；零日期仍按现行规则拒绝 |
| BINARY / VARBINARY / BLOB | Binary | 保留现有规范字节；不增加字符串解码或填充规则 |
| BIT(n) | FixedSizeBinary(ceil(n/8)) | n 保留在 schema；沿用现行字节序、宽度/高位校验和前导零，不转整数或布尔 |
| SET | Utf8 | 按声明顺序用逗号连接成员；适用现有禁止空 label、含逗号 label、未声明/重复成员的规则；NULL 与空 SET 分别为 null 与空文本 |

NULL 使用 validity，字段可空性来自规范 schema。空表、全 NULL 列也按声明建型，不根据样本推断类型；未知/不支持类型沿用 owning capability 的诊断，不自动 stringify。

Utf8/Binary 的 small/large 选择按规范化后整列 payload 字节数确定：不超过 `2^31-1` 用普通类型，超过则用 LargeUtf8/LargeBinary。同一文件各 batch 的 schema 一致；不能由线程数、调度或输入 chunk 决定。即使使用 large，已有字段、行数与内存预算仍生效，不承诺任意大小输入。

## 3. 转换边界与身份

1. **parser → 规范投影**：S2a parser 的 BIT 为 Binary，列声明通过 descriptor 单独传递。S2b 在规范 schema 构造处校验 descriptor 并转换为上述存储类型；在 Rust Arrow 路径内完成，不为转换逐行往返 Python。业务 composite 过滤后交 Python 的现有例外不变。
2. **SET → 内容编码 / RS**：IPC 文本只是一种内部表示。计算业务摘要时按声明恢复成员序列，使用 Shared Canonical Encoding §3.2 的 sequence framing，不摘要逗号文本。向 Repository 交付时按其 Contract 转为 list<utf8>；NULL、空 SET 与 ENUM 空标签分别处理。
3. **物理列序**：schema field 按 canonical column name 的 UTF-8 字节升序写入；不沿用输入 DDL ordinal。现有 `business_schema_digest_of` 忽略列序，所以同一规范身份不得因 DDL 列序不同而生成不同 IPC bytes。外层 bound description 仍保留 DDL/export row-layout；reader 按外层列名从 IPC 选择并重排给 DDL、Repository export/replay 消费者，不能按原 ordinal 取物理列。
4. **唯一 metadata 写法**：schema 只允许 `gdds.canonical_mapping_version`，ASCII 值为 `1`。每个 field 只允许 `gdds.canonical_type`，值为 JCS UTF-8 JSON object，恰含 `logical_type`、`sql_type`、`declared_type`、`labels` 四个键。`logical_type` 仅为 `standard`/`json`/`enum`/`set`；`sql_type` 是规范投影声明经 `normalize_sql_type_spelling` 得到的唯一输出。`declared_type` 为 null 或恰含 `kind`、`bits`、`precision`、`scale`、`bit_width` 的 object；不适用的数值键保留为 null，适用键取声明整数。`kind` 沿用 Shared Kernel 的 `boolean`、`signed-integer`、`unsigned-integer`、`decimal`、`float32`、`float64`、`string`、`binary`、`bit`、`date`、`datetime`、`timestamp`、`time-duration`。SET 的 declared_type 为 null、labels 为声明序列；ENUM 的 kind 为 string、labels 为声明序列；JSON 的 kind 为 string、labels 为 null；其余 standard 的 labels 为 null。Unknown/不支持的声明不写入规范 IPC。字段名、序号和 nullability 只由 Arrow schema 表达。禁止同义键、别名、原始 SQL spelling、display name、charset 或其他不影响规范身份的 parser 细节。JCS 固定 object key order、UTF-8 编码、转义与无空白表示；全部 metadata 必须可由绑定的规范投影 schema 决定，不能复制原始 parser descriptor 的非规范细节。
5. **声明核对**：metadata、物理 Arrow type、field name/nullability 与绑定规范描述必须一致；未知 mapping version、未知 key、重复/矛盾声明或物理类型冲突拒绝读取，不能让 metadata 覆盖外层业务语义。metadata 不写 operation、项目、时间戳或额外实例 table name；现有业务 schema digest 自身含 table name，这一既有身份组成不改写。
6. **两种摘要**：业务表摘要继续使用 owning Contract 的规范标量及行 framing；Arrow 物理字节不作为业务摘要输入。内容地址沿用设计 §8.2 的组成并含 mapping version；raw SHA 只验证实际文件完整性，不与业务摘要互换。复用 `gateway-shared-kernel` 已有 framing 原语，不在 Python 或 Rust 新建第二套 hash 算法。

## 4. IPC file profile、读取与确定性

映射 v1 固定为一个 Rust Arrow IPC **file** profile，以便随机读取及只读 mmap；不另建 Python writer。使用 workspace 已钉的 Arrow 59.1.0；`FileWriter` 显式设置 `IpcWriteOptions::try_new(64, false, MetadataVersion::V5)`，64-byte alignment、V5 metadata、无压缩、无 dictionary。不添加 file footer 自定义 metadata。按规范行序每 65,536 行切一批，仅末批可不足；空表写 schema、0 个 record batch。metadata 序列化沿用 pinned Arrow 的 key 排序，不自造 FlatBuffer writer。

数组 buffer 规范如下：

- 每批 offset 从 0 开始；small UTF8/Binary 用 32-bit offsets，large 用 64-bit offsets，类型仍按 §2 的整列 payload 决定；每批只写自身 payload。Boolean values buffer 使用 `ceil(rows/8)` bytes，NULL 值位及末 byte 未使用位为 0。
- 本映射支持的每个字段都写 validity，包括 non-nullable 字段。all-valid 数组统一不带显式 null buffer，由标准 writer 生成 `ceil(rows/8)` 个全为 `0xff` 的 bytes（末 byte 未使用位也为 1）；含 NULL 的数组以标准 buffer 构造规范 validity，末 byte 未使用位为 0。NULL 的固定宽度/数值 slot 清零；NULL 字符串/二进制的相邻 offsets 相同、payload 长度为 0。
- writer padding 固定按所选 Arrow profile 输出。实现测试要覆盖批次边界、空表、全有效/含 NULL 和末批未满场景，不能依赖 sliced array 的偶然 offsets 或未初始化 padding。

keyed 按既有规范键排序，ordered 的物理 gid 布局与业务 no 顺序分别遵守 owning Contract；keyless 按既有行哈希排序并保留重复行。不得以 SQL 插入顺序、worker 完成顺序或 Arrow 默认比较代替 owning Contract。相同规范值/schema 在 N=1/N、输入 DDL 列序变化和 parser chunk 变化时生成相同 IPC bytes；固定向量校验 schema、值、业务摘要及字节布局。影响持久表示的 profile 变化同步升级 mapping version，不把 Arrow 依赖版本写入业务摘要。

reader API 由后端持有生命周期。最小候选为 `CanonicalTableStore.open(ref, bound_descriptor) -> ContextManager[ArtifactReadHandle]`；handle 只暴露 schema/batch reader，不暴露 path，local 实现持有只读 fd/mmap，并在同一映射上分块校验 raw SHA。相同 ref 的第二次 `open` 取得独立 handle；`close()` 幂等，关闭后 read 稳定失败。PyArrow IPC reader/C Stream 与 Rust 借用数组不得超过 handle 生命周期，关闭顺序为 arrays/reader 后 mapping。内存实现以 BufferReader 遵守同一协议。现有 `ArtifactStorePort.locate(ref) -> bytes` 保留给其真实消费者，直到每个消费者切换完成；Rust kernel 不接触路径或文件系统。复用 local store 现有 temp + fsync + rename。写后回读删除；计入 Rust `Vec` 到 `PyBytes` 复制及 caller 持有期。

T1/BaselineHead/TTL、四种 miss/corruption 恢复和精确 commit 回填由存储/恢复 Contract 定义，不在 mapping 重定义；健康 artifact 走 IPC handle，miss/corruption 才按精确 Dolt commit 校验后回填。

## 5. 独立向量、验收与容量输入

独立预期复用既有标量、parser、projection 与 Shared Kernel 向量，不复制完整语法矩阵，也不从当前 Rust 输出直接生成期待值。SET sequence framing 的独立期望来自 `vnext/fixtures/vectors/repository/sql-enum-set/v1/values.jsonl`。IPC 小向量的 schema/值、offset/validity、batch 与 footer 布局须按固定 profile 独立核对，标准 IPC reader 可用于核验，不为此建设第二个 writer。关键 vectors 至少覆盖：

- 整数/DECIMAL 边界、FLOAT 舍入、NULL/空值、BIT 非整字节位宽、ENUM/SET、UTC 时间与负/长 TIME、JSON 文本保值、空表与全 NULL 列。
- 同一 canonical schema 的两种 DDL 列序写出完全相同 IPC bytes；读取后按外层 row-layout 重新排序，验证 export/import replay 仍保持既有布局。
- 规范 SQL 声明相同、仅原始拼写/display name 不同时，metadata 与 IPC bytes 相同。
- descriptor → IPC → reader/consumer 的声明和值一致；错误 metadata/version/物理类型拒绝；N=1/N 与不同 chunk 确定性。
- small/large 阈值用 payload 计数纯边界测试，真实小值转换；不为阈值分支分配数 GiB。

06 只做了有界既有 parser 输入测量；范围、数字与证据见[容量输入报告](p6-s2b-capacity-input-census.md)。其 raw parser buffers 不能冒充 canonical 上界、IPC 或 RSS。切片 A 实现唯一纯内存 mapping/IPC codec，随固定向量记录真实 IPC bytes；B 接入业务 kernel，C 复用该 codec 集成 store/reader/refs 并校准实际业务 IPC 与 FULL 生命周期。worker 接线前定 M，接线后复核 worker 峰值。较大既有样本及集中大表分布在 B/C 校准时核对，不为当前准备生成整套输入或跑规模压力。正确性所需 t1–t4 端到端另按 kickoff §6 的节点职责完成，不因容量分阶段延期。

## 6. 状态与下一步

UTC、来源/类型不变及少数约 100 MB 输入范围来自 DC76；技术映射候选和 06 小样本单位输入已收口。整体 kickoff 已通过独立技术审核，Owner 已按 DC85 批准 kickoff 及 A 节；当前实现纯内存 codec，后续 store/worker 范围按分节安排。生产 M 数值及默认值需等 mapping、Rust kernel、IPC writer 与 FULL 生命周期测量完成，并在 worker 接线前结合部署内存 envelope 确定，不从 SQL 大小猜值。容量分阶段关闭点见 DC84 与报告。

## 7. 检查记录

2026-11-06 本轮包含设计文档及独立普查工具，没有修改产品或容器边界，不声明新容器门禁或 carried。06 的两样本、五包 Ruff/mypy、工具自身静态修复复核及精确版本/SHA 见[容量输入报告](p6-s2b-capacity-input-census.md#可复核记录)；本次文档修订不重跑测试。下面保留 2026-11-04 的原记录，仅证明当时的检查，不作当前工具或 S2b 产品证据。

### 7.1 2026-11-04 历史文档检查

本轮只修改设计/DC/计划正文与 kickoff，无产品或容器边界改动，不触发镜像重建，不声明新容器验证或 carried。开发主线检查起点为 `580f57fd01d1`；05 clean 已提交 checkout 为 `55e6c0083c6e3a05dc97dad86974afd645d89a8e`，两者 `vnext` tree 均为 `2791d3ff3dd62ff454d7e9cac43885d39da8bf96`。在 05 获取节点占用后，用受控 uv wrapper、`UV_OFFLINE=1`、`--no-sync` 完成五包 ruff/mypy，2026-11-04T13:07:36Z–13:07:38Z，exit 0；使用该节点本地预填充环境，无下载、无代理，起止 HEAD 相同。未运行 pytest/Compose/真实数据，完成后释放占用。

日志：05 `/home/dev/gdds-test-tmp/p6-s2b-mapping-static-20261104T130736Z.log`；SHA256 `ae679b85c643b0b2bd7f59c85fc4b098966057760a95d9cf1286543ab22355c0`。这只记录文档提交前检查，不替代 S2b 技术审核或实施验收。
