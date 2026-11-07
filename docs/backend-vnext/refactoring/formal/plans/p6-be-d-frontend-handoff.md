# BE-d 完整tar前端交接（Owner手动转发）

2026-11-07。协调者维护；D代码/当前小Compose与制品固定于 **`0ba45e5ef83f54bfb2585f963f9518d32086f942`**，**本地里程碑已通过**（独审`6ad7e54fa0`、handoff`41386e12e6`核收`cd2d395fbc`）；04/05联合最终及前端同制品互通结果仍待。后端不改前端源码，前端由其owner修consumer与类型；实际encoder文件已交付见§3。本页新增两类已核consumer接缝，不改变现有POSIX tar格式，不要求生成大输入。

## 1. 已审UTF-8 PAX接缝

现有 `frontend/src/features/bundle/posix-tar.ts::parsePaxPath` 先解码全部body，再按 `text.length/slice` 推进，使用字符数而非字节数。按[BE-d设计§2.1](p6-be-d-design.md#21-utf-8-pax与前端交接独审n1)，应在 Uint8Array 里读取ASCII length和空格，按整条UTF-8字节边界切记录、检查换行/总长度，再严格解码key/value；前缀自身位数须进入固定点。字面向量 `12 path=中\n` 为12bytes。维持path安全、重复成员、closure顺序及完整性校验。

后端将交同一真实encoder生成的完整可安装小tar，包含ASCII长路径、中文、非BMP及原manifest/closure/每文件和总length/SHA；前端须用同字节制品核解析/摘要/OPFS安装。不能各造只自测成功的fixture或拿ASCII替代Unicode互通。

## 2. 标准PAX size与资源界限接缝（实施盘点新增）

后端现有 `ArtifactRef.size_bytes` 允许非负I-JSON安全整数，合法域可超出ustar size字段（11位八进制，最大`8^11-1`）。D将按标准局部PAX `size=<十进制整数>`表达此时的真实成员size，普通header size为0，长度计划与编码使用同一事实，不自行增加合法产物大小上限。

现有前端只解析header `[124:136]` 的八进制size，`parsePaxPath`只消费path而忽略PAX size；因此该合法边界不能互通。请随UTF-8修复核标准PAX size覆盖：按字节读记录、验证十进制整数与安全整数范围，使用其有效成员size，仍与closure/实际完整响应核对。仅需encoder生成的header/length边界小向量，**不生成或传输>8GiB测试文件**；header向量与完整可安装tar分别标明，不能将缺payload的前缀冒充完整制品。

实施者另核前端 `PAX_LIMIT=1MiB` 小于当前后端metadata允许的路径上界。后端按既有metadata边界有界分片，不额外截短/ASCII化路径或自行新增producer限制。前端owner应与owning Contract的合法域核对资源策略，不盲目取消其资源保障；若实际限制无法覆盖合法producer，反馈具体路径/字节数/影响供设计者澄清。当前无需要等待前端判断才能实施的后端阻塞；这些边界未修前不记互通通过。

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

三条Parquet路径分别为 `shared/dir/`（dir重复70次）`rows.parquet`、`shared/目录/`（目录重复60次）`表.parquet`、`shared/😀/`（😀重复60次）`表.parquet`；原路径以index/closure为准，不由前端重写或ASCII化。size向量跨`8^11-1`、`8^11`及I-JSON max；**都不是完整tar**，索引明确`complete_tar=false`，仅作header/PAX解码边界，未生成大文件。

生成原run为06 `run-interop-generate-LZPb1TzQ`；consumer验证 `run-interop-verify-corrected-6TuXooMk` command/final0，12:04:06Z结束、完整HEAD/clean/owner真。原一次外置脚本被wrapper在consumer执行前拒绝已保留，按DC68只用公开支持python-c/import本提交consumer单次纠正，不exec外置代码。OpenAPI来自同一0ba实际小Compose的`GET /openapi.json`，SHA=`977b22588c0e0bffcd58ee8618cdb704bfae4ca23d44ac019771d37f2c98b8a7`；不是新造fixture schema。

前端使用上述**同一个bundle.tar**核解析、路径/摘要与OPFS安装，并回传修复提交、同文件SHA及专用节点证据；后端现有独立consumer通过不替代这项结果。后台06已于12:05:51Z本人清理释放；04/05联合最终尚待。后端本节GO、联合后端验收和FE3解除依赖分别核收。真正需要前端判断的阻塞将另给具体问题包并暂停该依赖，其余已授权工作继续。
