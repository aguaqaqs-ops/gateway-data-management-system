# S2b kickoff 独立审核

状态：**READY_FOR_OWNER**（2026-11-06）。固定设计候选 `1a4adaae05069ef7e2c758bfaf1d363e9b2bebf1` 的 kickoff、mapping 与容量输入已闭合，无剩余技术 Finding；本结论不是 S2b 产品实施授权。审核基线 `51a8aa7e7abc19da695e210f574ba9c70d9bbfab`，S2a exit 为附注 `p6-s2a-exit`（`53b676a6298d408ccda3a85ee73c7ea223a2311a`）。审核在独立 detached worktree `/home/dev/gdds-test-tmp/s2b-kickoff-review` 进行，已建 legacy 链接；未重审已退出阶段，未运行产品、测试、基准或操作 CT108。

按本轮 Owner 澄清的文档职责，审核者直接修正 mapping/capacity 的 metadata、writer bitmap/profile、公式、版本证据绑定与校准时点，并精确修正 kickoff 的 FULL 并存、M 预约、lease 发布边界及强引用/TTL 措辞。主设计已复核这些文档修改并统一提交上述固定候选；产品/测试代码与原证据均未由审核者修改。其余实施文档和工具由审核者独立复核。

## 1. 已核对的源码与设计边界

类型映射的业务方向与实际 S2a descriptor/column builder 一致：整数拓宽仍按声明校验、FLOAT 保持 Float32、BIT 显式转换为定宽字节、SET 用文本存储而用成员序列 framing 摘要。现有 `sql-enum-set/v1/values.jsonl` 已提供独立 framing 向量；不需要第二套 Python IPC 实现。IPC 字节摘要与业务摘要必须保持各自角色。

实际共享消费者已独立核对：Preview/History 的 Repository 物化仍使用 `ARTIFACTS_REQUIRED`，Repository publication 使用 `READERS_REQUIRED`；`_digest.py` 同时服务 Repository、composite、artifact 验证；`import_replay.py` 仍调用 `materialize_canonical_source_rows`。kickoff §2 按实际 caller 列出保留/替换边界，不整文件删除共享能力，不允许旧算法换名成为永久回退。§5.4 已将三项 Python-only reader 生命周期证明分别移交到 IPC handle reopen/close、reader error 失效和真实 worker EOF/发布前检查。

现有 ArtifactStorePort 仅有 `put(bytes, ref)` 和 `locate(ref)->bytes`，LocalArtifactStore 实际 `Path.read_bytes()`。映射 §4 已给出 `CanonicalTableStore.open(ref, bound_descriptor) -> ContextManager[ArtifactReadHandle]`：Python 持有文件/只读映射和借用寿命、独立 reopen、幂等 close、关闭后读取失败；Rust core 不接管文件 I/O。写入复用临时文件/fsync/rename，引用与 TTL 复用保护表/lookup/expiry；head 与未释放冻结引用不按 TTL 过期，最后强引用释放与 TTL 记录同事务，保留共享保护及四种恢复语义，不新建安全平台或持久证据状态机。

## 2. 本轮技术问题的闭合

1. IPC file profile 固定 Arrow 59.1.0、alignment=64/V5/非 legacy、无压缩/dictionary、每 65,536 行切批及空表 0 批；metadata 单一键与四字段声明、null 值槽、offset 基准及 small/large 全列选择明确。已核本地 pinned writer：metadata key 排序、无 null buffer 时写全 `0xff` validity，non-nullable 也写；Boolean values 为 bit-packed。标准 buffer 构造规范 NULL/tail bits，不自造 writer。
2. composite 过滤保留原诊断。`_catalog._read_devices` 校验全部 device 行；`_bind._require_special_device` 区分空表和非空但没有特殊设备的错误。只把命中行交 Python 时，Arrow 侧必须先完成需要的全列校验并保留原表非空/匹配数事实；点表也必须保留过滤前所需列与地址类型校验。该项不改变既有业务规则。
3. kickoff §5 明确 worker startup 显式初始化共享池、真实 control→probe→adapter 的调用链、分配/增长前预约。N 正确性默认 1、调优起点 4；M 包括源输入、Arrow、投影/排序/复制、IPC 输出、当前操作的 mmap 和 FULL 同时驻留，按生命周期和共享分配计数，总预约 ≤ M；不是 RSS 上限。数值按 DC84 在 worker 接线前确定，不凭小样本猜 GiB。
4. IPC 物理列按 canonical 列名 UTF-8 排序，metadata 仅写规范投影声明可决定的值。`business_schema_digest` 与 DDL 列序无关，不能让同一内容地址随 DDL 列序、display name 或原始 SQL 拼写产生不同字节。该 digest 现含规范表名；内容地址不再额外添加实例表名，但不承诺跨不同表名去重，不为此改业务摘要。

实际 `ExecutionControl` 没有 operation deadline。本阶段沿用现行调用者无截止时的 `None`，有明确有限截止的调用者原样传入 adapter/core；不得借用可续租的 lease deadline 或性能目标构造新固定时限。取消、drain 与 lease lost 的 probe/终态按原 Runtime 区分，不能把后两者发布成用户取消。

实施顺序已消除 writer 的循环依赖：A 包含唯一纯内存 mapping/IPC codec 和独立固定向量，B 接业务 kernel，C 复用该 codec 做 store/reader/ref/recovery 与完整业务 IPC/FULL 校准，之后 D 接 worker、E 收唯一生产路径并删除旧算法。A 的 bytes/profile 验收不依赖未来 C。arrow-ipc/arrow-select 由 dev-deps 转生产闭包时仍按实际锁/feature/DC67 和镜像边界验收，不因版本相同豁免。

## 3. 已接受的容量与时点安排

新规范 IPC writer 尚不存在。kickoff 前要求它的实际 IPC/RSS 再据此定生产 M，会形成循环依赖。DC84 已接受的顺序是：本轮 06 两个有界样本量取源文件与现有 Arrow buffers，未知单列；第一小步实现真实 writer 后校准 IPC，worker 接线前定 M 并校准已实现 kernel/IPC 的 FULL 峰值，接线后最终功能候选复核实际资源边界。不得把原始 buffers 直接冒称规范投影上界，伪 gid/composite 增量另计。不把新 writer 实测/M 定值作为 kickoff 前置，也不建设临时 Python IPC。

W2 已由 DC83 分离，不重复请求决定。原设计 §16.3 明确 W1 在 S2b 起测、W3 在 S3 起测，正式阈值均到 S6 取证；表后明确只在取证运行判门槛。S2b 的正确性和结构断言继续保留。DC84 已接受：若 CT108 直到功能退出仍无可用窗口，W1 诊断起测可延期，最迟 S6。这不是借 W2 决议自动豁免其他场景，也不是全部产品开工授权。

t1–t4 的正确性仍由最终功能候选完成，05/CT108 分工与完整同档旅程要求不变；DC83/84 不豁免 t4 正确性。未来退出窗口不足时再按既定协调/Owner 明确换节点安排处理，不把未来 t4 窗口变成本节准备或第一小步 kernel 的新门槛。

本轮已完成最小普查：06 已有 t1 单 SQL（约 1.3 MB）和已跟踪的两行 NULL/string/bool fixture，单输入最多 2 MiB、N=1，只消费现有 S2a Arrow 输出，不写 IPC、不测 RSS、不跑旅程；工具和实际证据均已核对，见 §4。该输入支持映射/有界纯 kernel 第一步，不据 t1 比例推生产 M 或宣称大表容量通过。较大既有样本与集中大表分布核对归真实 writer/FULL 校准节点，不先生成新输入。Phase 7 总容量、500 路积压、多 worker 与排队策略不作为本阶段第一小步门槛。W4 已发生租约故障由原线继续处置，不标作普通性能 pending，也不默认由 S2b 修复。

## 4. 复审与最终结论

`5faa2c8a67db7ff96a17cb2f2d9312e806cfb774` 的 DC84、design 与 execution-plan 修订已独立核对通过；分步容量与 W1 决定落文一致，worker 接线前的校准只要求当时已实现 kernel/IPC 的 FULL 驻留，实际 worker 在接线后最终复核，未形成新的循环依赖。固定候选的三份文档与 owning 决议、现有源码一致，已核对最终 diff；历史检查与本轮证据分开记录。

`583b69c838533a28cdc30d9aeb6c36ab30270cf2` 的两文件普查工具已审核。固定输入尺寸、stream tar 成员检查、非零失败和匿名输出符合本次范围。报告明确区分 logical bytes、buffer reference spans、逐表 unique backing buffers，既不称分配器 capacity，也不称 RSS 或新 IPC。

06 证据已独立通过 SSH 只读核对；运行 HEAD 为 `a3f49290628caf5c1cb626bac6cc7b26cb2c5f00`，工具同 `583b69c838`，起止 HEAD 一致、两次 exit 0。以下时刻均为 2026-11-06 UTC：`06:05:51–06:05:52Z` 的 t1 单位输入 132 表/6,093 行/151,751 值；logical bytes=1,405,885，逐表 unique backing buffer bytes 之和=1,409,489。`06:06:12–06:06:13Z` 的两行 fixture 为 37/45 bytes，与审核者运行前手算一致：INT64 16 B、两列 UTF8 各 14 B、Boolean 1 B 合为 45 B；logical 口径每列 UTF8 少计末 offsets 的 4 B，合为 37 B。逐表 JSON 重新求和一致，t1 最大表 1,678 行、最大表 buffer 480,621 bytes、最大列 span 42,105 bytes；三个最大值独立统计，不推定为同表/列。这些是小样本分布，不能推生产 M 或大表通过。源码工作区 clean；扩展 build input expected/installed 均为 `61a76caa0e789aef1eea53a8c98d4c4c3cbb2af4`。

证据目录：06 `/home/dev/gdds-test-tmp/p6-s2b-capacity-census-583b/`。

| 日志 | SHA256 |
| --- | --- |
| `t1-v1-census.log` | `26ce38f1b079acb89c8b30b37b230764859d7590ee81d881ad5819e0c7dc3f13` |
| `types-fixture-census.log` | `8fae4260335301f007549e98ece8762fb4bd7c77ea3c3008237bcc74b257acf6` |
| `extension-build-input.log` | `71eb0e20532a08a5c09c0d55e2fe2a8dc55f5caa233239dda15989ac5dabfd12` |

五包 Ruff/mypy 通过；工具独立 mypy 首次发现四处 `int(object)` 静态错误，失败日志 `python-static-checks.log` SHA256 `a62739ff431268bcc9dc0aade828e4fd67530da06c05cc8bffc9965f8864ed93` 保留。已审 `f5dafdfce8` 的 `_report_int` 类型收窄修复：计数字段/结果不变，既有样本继续绑定原实际版本，不重跑样本。06 clean `d368413861dbcce10691fb65e8dbaba2a208af68` 于 `06:13:48Z` 重跑工具 Ruff、显式 mypy 与 wrapper bash syntax，全部 exit 0、起止 HEAD 一致，日志 `tool-fix-static-checks.log` SHA256 `b86851471ac438ad447fa8f62c39a9e9f08fccb87315466aa568f966bd0b4006` 已独立核对。该修复不改变产品或需要新的容器门禁。

固定候选与上述修复静态检查提交的 `vnext` tree 同为 `02524028281cdb050ccb65eda2436e7fe21a2e4a`；其后仅文档修改，本报告复用同代码检查，`git show --check` 通过，不重跑全量。最后实际产品 image revision/source-tree 仍由 [S2a 退出审核](p6-s2a-closeout-review.md) 的 V `3b037ad` 及最终 `53b676a` 绑定记录证明；本轮不触发镜像重建，不将该记录称为准备工具候选的新容器门禁或 carried。未来 A 若改变生产依赖闭包，按实际变更在该轮最终候选运行必要容器门禁；S2b 阶段退出必须绑定最终 HEAD，只有满足 AGENTS 同节点/同 worktree 等价规则才可沿用。

待 Owner 决定的是确认整体 kickoff 及首节 A 的明确产品授权；DC83/84 不再重复征询。M/default/max、部署 envelope/reserve、完整业务 IPC/FULL 与实际 worker 资源复核是已指定时点的后续实施责任，当前没有这些实现结果，也不声称通过。t1–t4 正确性、结构计数、恢复与最终权威/容器门禁均保留；W4 继续原线处置。
