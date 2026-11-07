# BE-d 完整tar前端交接（Owner手动转发）

2026-11-07。协调者维护；D清单`cf2091eadd`、独立预检`e29a2c2926`，产品仍实施中，**尚无D产品GO或同制品互通结果**。后端不改前端源码，前端由其owner修consumer与类型；实际encoder制品/候选/SHA/长度随后补。本页新增两类已核consumer接缝，不改变现有POSIX tar格式，不要求生成大输入。

## 1. 已审UTF-8 PAX接缝

现有 `frontend/src/features/bundle/posix-tar.ts::parsePaxPath` 先解码全部body，再按 `text.length/slice` 推进，使用字符数而非字节数。按[BE-d设计§2.1](p6-be-d-design.md#21-utf-8-pax与前端交接独审n1)，应在 Uint8Array 里读取ASCII length和空格，按整条UTF-8字节边界切记录、检查换行/总长度，再严格解码key/value；前缀自身位数须进入固定点。字面向量 `12 path=中\n` 为12bytes。维持path安全、重复成员、closure顺序及完整性校验。

后端将交同一真实encoder生成的完整可安装小tar，包含ASCII长路径、中文、非BMP及原manifest/closure/每文件和总length/SHA；前端须用同字节制品核解析/摘要/OPFS安装。不能各造只自测成功的fixture或拿ASCII替代Unicode互通。

## 2. 标准PAX size与资源界限接缝（实施盘点新增）

后端现有 `ArtifactRef.size_bytes` 允许非负I-JSON安全整数，合法域可超出ustar size字段（11位八进制，最大`8^11-1`）。D将按标准局部PAX `size=<十进制整数>`表达此时的真实成员size，普通header size为0，长度计划与编码使用同一事实，不自行增加合法产物大小上限。

现有前端只解析header `[124:136]` 的八进制size，`parsePaxPath`只消费path而忽略PAX size；因此该合法边界不能互通。请随UTF-8修复核标准PAX size覆盖：按字节读记录、验证十进制整数与安全整数范围，使用其有效成员size，仍与closure/实际完整响应核对。仅需encoder生成的header/length边界小向量，**不生成或传输>8GiB测试文件**；header向量与完整可安装tar分别标明，不能将缺payload的前缀冒充完整制品。

实施者另核前端 `PAX_LIMIT=1MiB` 小于当前后端metadata允许的路径上界。后端按既有metadata边界有界分片，不额外截短/ASCII化路径或自行新增producer限制。前端owner应与owning Contract的合法域核对资源策略，不盲目取消其资源保障；若实际限制无法覆盖合法producer，反馈具体路径/字节数/影响供设计者澄清。当前无需要等待前端判断才能实施的后端阻塞；这些边界未修前不记互通通过。

## 3. 最终制品补件（待）

待D固定候选与06实际结果：生产OpenAPI、完整tar/原manifest/closure/成员映射与全部摘要、生成命令/节点/候选、ASCII/中文/非BMP同制品及PAX size边界向量、后端独审报告。前端修复提交与同字节安装证据由其owner提供；后端本节GO、联合后端验收和FE3解除依赖分别核收。真正需要前端判断的阻塞将另给明确问题包并暂停该依赖，其他已授权工作继续。
