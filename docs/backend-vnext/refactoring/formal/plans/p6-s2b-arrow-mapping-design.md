# S2b 规范表 Arrow 映射 v1（设计候选）

状态：2026-11-04，设计候选，待独立审核并纳入正式 S2b kickoff；不是实施授权或证据结论。

来源：DC46/DC47、[P6 设计 §8](p6-design.md#8-s2b上传侧数据路径与规范表存储)、[DC76](p6-s0-owner-decisions.md#dc76-s2b-输入约定与映射准备)。源码核对基线 main `580f57fd01d122189d7c4a6b037e668a9531d803`；parser 输出核对 S2a 候选 `3b3d9c97bcb6d79d6c087099fbe6353f170bf68f`。S2a 合入后核对差异，不重新判定其证据。

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
3. **版本与 metadata**：规范 IPC 使用独立映射版本 `1`，不得复用已删除旧 row-hash capability 的接口或误认 RS mapping。schema metadata 记录映射版本；field metadata 记录足以解释值的规范逻辑声明（kind、适用的 bits/precision/scale/bit_width、ENUM/SET 标签及规范 SQL type）；字段名、顺序、可空性在 Arrow schema 中表达。具体键名在实现 Contract 中固定为单一写法，不提供别名。
4. **声明核对**：metadata、物理 schema 与绑定的规范描述必须一致；冲突按损坏/不支持处理，不凭 metadata 覆盖权威业务语义。metadata 不写 operation、项目、时间戳或表名等实例信息；现有内容地址不含表名，实际表名/项目绑定保留在外层引用。
5. **两种摘要**：业务表摘要继续使用 owning Contract 的规范标量及行 framing；Arrow 物理字节不作为业务摘要输入。内容地址沿用设计 §8.2 的组成并含映射版本；raw SHA 只验证实际文件完整性，不与业务摘要互换。

## 4. 写入、读取和确定性

- 不压缩 IPC，Rust 编码、Python ArtifactStore 落盘；mmap 读取、raw SHA 校验及临时文件原子 rename 沿用设计。读取校验保留，写后回读删除。
- keyed 按既有规范键排序，ordered 物理存放按 gid、业务顺序仍按 no；keyless 按既有行哈希排序并保留全部重复行。排序实现不能用 SQL 插入顺序、worker 完成顺序或 Arrow 默认比较规则替代 owning Contract。
- 同一实现版本固定列/metadata 顺序、batch 划分、writer 选项及 null buffer 的规范输出；排除时间戳等不稳定字段。相同规范输入在 Rust 路径的 N=1/N 及不同 parser chunk 下生成相同规范 IPC；固定向量校验声明、值及字节布局。替换期可借 Python 冻结结果验证语义，不为新 IPC 格式建设第二套 Python 算法（DC78）。reader/writer 使用同一个版本化 profile；影响持久物理表示的规则变化同步修订映射版本及测试，不把依赖版本加入业务摘要。
- 未经确认不增加第二种持久格式。唯一 Rust 生产路径使用规范 IPC 与既有引用/恢复语义，不建设 Python 回退或双格式兼容（DC78）；T1、BaselineHead、TTL 和缺失后的四种恢复状态不在映射层重定义。

## 5. 验收与容量输入

复用现有标量、parser 和投影 owner 的向量，不再复制其完整语法矩阵。新增测试只证明实际映射边界：

- 整数/DECIMAL 边界、FLOAT 舍入、NULL/空值、BIT 非整字节位宽、ENUM/SET、UTC 时间与负/长 TIME、JSON 文本保值、空表与全 NULL 列。
- parser descriptor → 规范 IPC → 读取/既有导出路径的声明和值一致，业务摘要、行数和重复行保值；错误 metadata/物理类型组合拒绝。RS 映射验收仍由原 owner 负责。
- small/large 阈值用纯边界测试，实际转换用适当大小的数据覆盖；不为阈值分支强制分配数 GiB 的普通单元测试。
- 不同线程、chunk 和固定向量的确定性归映射 owner；真实数据端到端结果仍由现有 comparator 判定。容量与 W2 不由映射测试冒充。

容量普查应分别记录总输入、最大表、最大列 payload、最长字段/语句、行数分布、规范 IPC、导出副本、临时高水位和峰值内存。已有 V6 158.7 MB 合成输入增加的是表，不能据此断言少数大表的完整路径已验证。优先复用现有样本，在获安排的 05 设计输入普查中补充保持类型与业务约束的大表分布；实际 100 MB 样本只在分布代表性不足时再协调。任何生成规则与取证范围先写入普查方案；不修改当前基准输入、golden 或正式测量口径。

## 6. 状态与下一步

owner 已确认 UTC、来源/类型不变及少数约 100 MB 输入，并允许落成方案。本文技术细则待审核；S2a exit、原始表使用方核对、磁盘预算、N/M、唯一 Rust 路径与旧算法清理细则及正式 kickoff 仍是各自待办。下一步先形成容量普查和 N/M 方案，不把文件大小上限当作内存可承受承诺，不因极端输入少见而跳过预算拒绝与无部分写入的既有边界。

## 7. 本次文档提交检查

本轮只修改设计/DC/计划正文与 kickoff，无产品或容器边界改动，不触发镜像重建，不声明新容器验证或 carried。开发主线检查起点为 `580f57fd01d1`；05 clean 已提交 checkout 为 `55e6c0083c6e3a05dc97dad86974afd645d89a8e`，两者 `vnext` tree 均为 `2791d3ff3dd62ff454d7e9cac43885d39da8bf96`。在 05 获取节点占用后，用受控 uv wrapper、`UV_OFFLINE=1`、`--no-sync` 完成五包 ruff/mypy，2026-11-04T13:07:36Z–13:07:38Z，exit 0；使用该节点本地预填充环境，无下载、无代理，起止 HEAD 相同。未运行 pytest/Compose/真实数据，完成后释放占用。

日志：05 `/home/dev/gdds-test-tmp/p6-s2b-mapping-static-20261104T130736Z.log`；SHA256 `ae679b85c643b0b2bd7f59c85fc4b098966057760a95d9cf1286543ab22355c0`。这只记录文档提交前检查，不替代 S2b 技术审核或实施验收。
