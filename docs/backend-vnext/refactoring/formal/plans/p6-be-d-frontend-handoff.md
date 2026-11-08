# BE-d 完整tar前端交接（Owner手动转发）

2026-11-07。协调者维护；**联合后端技术GO `ccdd1eb39d`、Owner已确认DC33范围，后续正式退出tag为`p6-be-a-d-exit`→77b9aeea74**，实际产品49403/tree567、handoff233e。下列同字节制品生成源仍为0ba生产encoder；当前实际API原件来自04新权威run mvzi，见§3。后端退出已完成，前端同制品OPFS互通仍pending。后端不改前端源码，前端由其owner修consumer与类型；实际encoder文件已交付。本页列已核consumer接缝及当前版本的接收预算澄清，不改变POSIX tar格式，不要求生成大输入。

## 1. 已审UTF-8 PAX接缝

现有 `frontend/src/features/bundle/posix-tar.ts::parsePaxPath` 先解码全部body，再按 `text.length/slice` 推进，使用字符数而非字节数。按[BE-d设计§2.1](p6-be-d-design.md#21-utf-8-pax与前端交接独审n1)，应在 Uint8Array 里读取ASCII length和空格，按整条UTF-8字节边界切记录、检查换行/总长度，再严格解码key/value；前缀自身位数须进入固定点。字面向量 `12 path=中\n` 为12bytes。维持path安全、重复成员、closure顺序及完整性校验。

后端将交同一真实encoder生成的完整可安装小tar，包含ASCII长路径、中文、非BMP及原manifest/closure/每文件和总length/SHA；前端须用同字节制品核解析/摘要/OPFS安装。不能各造只自测成功的fixture或拿ASCII替代Unicode互通。

## 2. 标准PAX size与资源界限接缝（实施盘点新增）

后端现有 `ArtifactRef.size_bytes` 允许非负I-JSON安全整数，合法域可超出ustar size字段（11位八进制，最大`8^11-1`）。D将按标准局部PAX `size=<十进制整数>`表达此时的真实成员size，普通header size为0，长度计划与编码使用同一事实，不自行增加合法产物大小上限。

现有前端只解析header `[124:136]` 的八进制size，`parsePaxPath`只消费path而忽略PAX size；因此该合法边界不能互通。请随UTF-8修复核标准PAX size覆盖：按字节读记录、验证十进制整数与安全整数范围，使用其有效成员size，仍与closure/实际完整响应核对。仅需encoder生成的header/length边界小向量，**不生成或传输>8GiB测试文件**；header向量与完整可安装tar分别标明，不能将缺payload的前缀冒充完整制品。

实施盘点发现前端 `PAX_LIMIT=1MiB` 不能覆盖当前后端metadata允许的路径域；2026-11-07设计者按实际代码核对后的定稿接收预算见§2.1。后端沿既有metadata边界有界分片，不截短/ASCII化路径，也不因此新增producer限制。修复与同制品验收仍由前端owner负责。

### 2.1 路径字节数与PAX接收预算（设计者只读澄清）

后端`bundle_assembly/contracts.py::validate_logical_path`**没有独立路径长度常量**。现有硬边界是manifest和closure的JSON各不超过`16 * 1024 * 1024 = 16,777,216 bytes`。下表是覆盖**当前bundle版本合法producer**的前端保守接收预算，不是新增后端path硬限制，也不是通用tar/PAX格式上限：

| 对象 | 前端可采用的接收上界 | 计数口径 |
| --- | --- | --- |
| 单个logical_path | `MAX_PATH_UTF8_BYTES = 8,388,608`（8 MiB） | path原值的UTF-8字节，不是JS.length；合法bundle实际严格小于该值 |
| 单局部PAX扩展头payload | `MAX_PAX_PAYLOAD_BYTES = 16,777,216`（16 MiB） | 包含各记录length前缀/空格/key=value/换行，不含512-byte tar header与padding |
| manifest / closure | 各`16,777,216`（16 MiB） | 维持既有JSON总预算，不能各自改成路径预算 |

推导：同一path在manifest的`closure.entries`与`closure_entries`各出现一次，`transport.py`校验二者一致及JCS；closure也有相同重复结构。每份JSON编码path所需字节至少为原UTF-8长度L，另有非零结构/字段开销，因此`2L + overhead <= 16,777,216`，即`L < 8,388,608`。**8 MiB不是保证可达的精确最大值**，具体合法长度还受其它metadata和JSON转义开销约束。

当前`artifacts/tar_stream.py`只生成path/size两种局部PAX记录。path记录长度满足`R = L + digits(R) + 7`；取前端保守L上界得`8,388,622 bytes`。size值最多`2^53 - 1`，对应记录最多25bytes，合计保守不超过`8,388,647 bytes`，小于16 MiB，故表中PAX预算覆盖当前合法输出。

前端须按header声明payload先检查预算、再分配/读入；严格UTF-8、路径安全、closure匹配、摘要和总长校验均保留。可用编码单元向量覆盖1 MiB以上及拒绝边界，不为证明预算构造伪称合法的满8 MiB bundle或重跑后端旅程。上述上界依赖本版本JSON重复结构、16 MiB cap及PAX只含path/size，未来改变时同步复核。设计者已确认这是既有实现/Contract的推导，无产品、Contract或退出tag变更。

## 3. 已实际生成的同字节制品

06 clean候选0ba通过生产 `assemble_bundle` → `prepare_bundle_download` / `gateway_backend.artifacts.tar_stream` 实际生成，沿已提交 `benchmarks.bundle_tar.verify_bundle_tar` 独立consumer核原metadata、全部普通成员/size/raw SHA和既有有界引用metadata；全部8文件摘要相符。普通成员数6（manifest+closure+4 entries），总长 **24576 bytes**，tar SHA256 **`b08a310c82162ecf559b9f82eca30548cc97a75cc0d8775e20b2bd24611332a2`**。该小制品没有records closure，`verified_logical_record_count=0`，不以此声称大数据或records逻辑消费覆盖；对应生产链路另有当前Compose/HTTP owner证据。

| 文件 | 可转发的实际本地副本 |
| --- | --- |
| 完整可安装tar | [bundle.tar](/home/dev/gdds-reviews/artifacts/p6-be-d/recovery-copy-9cctQXWi/recovery-lpNIMtZE/interop-0ba45e5ef8/bundle.tar) |
| 原发布metadata | [manifest.json](/home/dev/gdds-reviews/artifacts/p6-be-d/recovery-copy-9cctQXWi/recovery-lpNIMtZE/interop-0ba45e5ef8/manifest.json)、[artifact-closure.json](/home/dev/gdds-reviews/artifacts/p6-be-d/recovery-copy-9cctQXWi/recovery-lpNIMtZE/interop-0ba45e5ef8/artifact-closure.json) |
| 每文件length/SHA、成员映射、candidate | [index.json](/home/dev/gdds-reviews/artifacts/p6-be-d/recovery-copy-9cctQXWi/recovery-lpNIMtZE/interop-0ba45e5ef8/index.json) |
| 合法/畸形PAX字节向量 | [pax-records.json](/home/dev/gdds-reviews/artifacts/p6-be-d/recovery-copy-9cctQXWi/recovery-lpNIMtZE/interop-0ba45e5ef8/pax-records.json) |
| size边界索引（3个header-only bin同目录） | [size-vectors.json](/home/dev/gdds-reviews/artifacts/p6-be-d/recovery-copy-9cctQXWi/recovery-lpNIMtZE/interop-0ba45e5ef8/size-vectors.json) |
| 同候选实际生产GET OpenAPI | [production-openapi.json](/home/dev/gdds-reviews/artifacts/p6-be-d/recovery-copy-9cctQXWi/compose-output-eJGTujH4/production-openapi.json) |
| 当前联合候选49403生产GET OpenAPI | [production-openapi.json](/home/dev/gdds-reviews/artifacts/p6-be-ad-final-04-copy-mop1T4t8/p6-be-ad-final-04/resume-a-5OBTboKj/new-authority-compose-53h3ekqp/production-openapi.json)，SHA仍`977b22588c0e0bffcd58ee8618cdb704bfae4ca23d44ac019771d37f2c98b8a7` |

三条Parquet路径分别为 `shared/dir/`（dir重复70次）`rows.parquet`、`shared/目录/`（目录重复60次）`表.parquet`、`shared/😀/`（😀重复60次）`表.parquet`；原路径以index/closure为准，不由前端重写或ASCII化。size向量跨`8^11-1`、`8^11`及I-JSON max；**都不是完整tar**，索引明确`complete_tar=false`，仅作header/PAX解码边界，未生成大文件。

生成原run为06 `run-interop-generate-LZPb1TzQ`；consumer验证 `run-interop-verify-corrected-6TuXooMk` command/final0，12:04:06Z结束、完整HEAD/clean/owner真。原一次外置脚本被wrapper在consumer执行前拒绝已保留，按DC68只用公开支持python-c/import本提交consumer单次纠正，不exec外置代码。OpenAPI来自同一0ba实际小Compose的`GET /openapi.json`，SHA=`977b22588c0e0bffcd58ee8618cdb704bfae4ca23d44ac019771d37f2c98b8a7`；不是新造fixture schema。

前端使用上述**同一个bundle.tar**核解析、路径/摘要与OPFS安装，并回传修复提交、同文件SHA及专用节点证据；后端独立consumer不替代此结果。联合后端正式退出及本轮节点收尾已完成，见[最终交接§15](p6-be-a-d-joint-validation-preparation.md#15-联合正式退出完成与前端交接)。FE3解除依赖仍须前端自己的同字节证据，真正需要前端判断的后端阻塞将另给具体问题包并暂停该依赖。
