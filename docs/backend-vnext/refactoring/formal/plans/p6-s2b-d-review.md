# S2b D 独立审核

结论：**D GO；本节无未关闭阻塞项**。固定产品 `93678f8439ec1393d496182f16ae5049b220242f`、固定 [handoff](p6-s2b-d-handoff.md) `abfe7cb66bd1550d4646bd54d287aa1b3625b71d`。日期：2026-11-06 UTC。本结论覆盖D的真实调用链、operation预约/控制、实际materialize局部校准及本候选必要容器边界；S2b最终runner/完整旅程与旧算法删除仍属E，不在此宣称S2b exit/S3 ready或全worker实测峰值。

启动文档 `63925fe47cf9653b217dde5f545579dd1c62f5ef`；C固定产品 `0048040af59214bf1113c820396ac4b306befe31`、handoff/容量 `7cd2b548c87fe0c07390078104714cb4055d5b5a`、独立GO `e9bef6efe8`保留其组件范围，不替代本节证据。

## 审核范围与方法

审核者为本节新建GPT-6.1-Sol/max，未派生额外角色。产品与测试由实施者修改；本审核只维护本报告、只读源码和06证据，不在CT201运行测试、编译或lint，不取得06占用。新detached worktree `/home/dev/gdds-test-tmp/s2b-d-review` 已建legacy链接；每轮固定候选后只读审核，最终固定产品93678及文档abfe7，后者的vnext树与前者无diff。实际worker materialize局部校准、最终容器组合证据和06释放均已独立核实。

依据实际 AGENTS、testing conventions、DC76–88、总/D kickoff、mapping、C handoff/容量/审核，以及 Snapshot Table Access、Snapshot Materialization、Canonical Storage §5、Operation Lifecycle、Rust policy、ADR 0012 和 proportional-assurance policy。Owner DC87 的显式配置是 12 GiB envelope、4 GiB reserve、M=8 GiB（8,589,934,592 B）上限、N=1/单 active；M 缺失拒启，不从 06 RAM 推导。W4 仍 OPEN，`1f9731dfc3` 诊断修复未自动合入；未操作原基准冻结资源。

## 一次性审核矩阵

| 对象与真实后果 | 既有 owner / 最小验证 | 当前结论 |
| --- | --- | --- |
| settings/startup，资源配置边界 | worker settings/lifecycle、进程池 owner；当前 Compose 实际限额 | required M、N范围、12/4/8配置及一次显式共享池初始化已核；936生产容器ready/stop与实际12GiB HostConfig/cgroup及settings一致，通过。 |
| 生产 caller 与规范内容，业务结果/冻结绑定 | Preview FULL 两侧、baseline、History exact commit、repository-ref 两种 policy、Submit T1/PREPARED、replay/export 原 owner | 列举的生产caller已接唯一Rust IPC；frozen format/repo/schema/source与真实缺失ABORT通过。raw/client Parquet真实用途保留，旧reference仅按E边界移交。 |
| operation 当前活跃内存，增长前资源拒绝 | parser/B/A 局部预算与真实 worker owner；FULL/borrow/mmap/wire/staging 合并 | parser/context/SQL-derived facts、mapping/wire/export、pair/records/bundle与Submit Python重叠预约及低M清理小步已核；BBC实际worker materialize FULL/t4局部校准通过。不用局部各M或C分进程RSS相加冒充总量。 |
| cancel/drain/lease/deadline、EOF/完成/发布与恢复，durable/A 类后果 | 原 ExecutionControl、LeaseSession、Preview/History/Submit recovery owner | C/native/reader/EOF、DC88真实Runtime drain/reclaim、pair/records/bundle及parent/publish分类和资源拒绝cleanup通过。无deadline传None，正式输出只经LeaseSession，936容器正常drain/exit0通过。 |
| 固定源码、环境与镜像，证据采信边界 | task-owned named ref/bundle、clean WT/节点占用/离线；影响面静态/必要容器 | fixed source同步/环境/实际结果、936离线镜像config与全部DiffIDs、49日志索引和18:52:58Z节点释放已核。原失败保留，局部PASS不回填整次FAIL。 |

审核测试语义屏障，不添加内部全排列、durable reservation、逐文件租约证明、allocator 框架或同 euid 对抗机制。跨 checkpoint 已释放的 buffer 不累计，未打开的历史文件只计磁盘。derived 内容 key/TTL cache 维护继续使用 C 的短 UoW，当前 Head/Archive CAS 保持真实事务 owner；不把这些缓存维护升级为新租约协议，也不以 cache 登记替代正式 operation 发布。

## 已核小步与证据

06 为 `gw-dms-06`，实施者 worktree `/home/dev/gdds-test-tmp/wt/p6-s2b-d-impl`。本审核先 BatchMode SSH，独立只读核 owner `session=p6-s2b-d-impl`、原子占用开始 14:47:31Z、prepare 日志 `logs/s2b-d-node-prepare.log` 外部 SHA `af803027f30e1e10b495fecdc8c20131d4d02f2e114b192f9753234fd4119c3d`。起始实际 remote HEAD `2c79d0947fe0d5e1d2f62a3f106a8e72f37706a3`，clean/legacy 齐全。

源码同步脚本 CT201 `/tmp/s2b-d-publish-source.sh` SHA `07bce72f3f513f7666cb05bf896913a8b2350c56c3ec4f95ed2e39e35a35b879`，06 `/home/dev/gdds-test-tmp/s2b-d-sync-source.sh` SHA `73ad4f7e9689a72fc59d952f8b97785aca6de6a9c379a357670f068cd3e23b51`。已核 fixed full SHA → task-owned named ref → bundle advertised ref/摘要 → remote actual previous HEAD/clean → fetch/checkout；同步 actual exit0 后另一次 call 确认 HEAD/clean 再测试。865 同步日志 CT201 `/tmp/s2b-d-sync-865d.log` SHA `1da9400ac8bc0cf86075b6ad688ce16b820bb8b3ad7160855154fdd1768bfbb0`。

最终同步`/tmp/s2b-d-sync-final-static.log` SHA `d54179870edd7881ed294b8a42996642079010054646a273ae642ccee1b8490d`已独立核：actual previous为BBC、task-owned advertised ref为936 fullSHA，bundle SHA `a6a97b8e4ba439a9abae53084ee806194fec1179251d4b6f372f18fc81abd2ef`，18:40:40Z完成checkout/clean后再做18:40:53Z static。ff399同步actual previous为77a4，`/tmp/s2b-d-sync-parserfix.log` SHA `548879b318f2e79ee6edf37bb5adb0c2d5f00f086e9d5fd1ddffcc13692085d3`亦已核；不以共享main相邻提交假定remote previous。

| 固定候选与范围 | 实际结果 | 06 日志 / 外部 SHA256 |
| --- | --- | --- |
| `c0fa4d57cc9f8468a95f3eb157ed8ffbc4117dc7`，首配置小步 | fmt-only 失败，未作为通过证据；865 修正格式 | `logs/s2b-d-step1-c0fa4d57cc.log` / `92be102845c11641d5f2485029dcf041f1b5d7c75ad8a286b753eae2794a4d13` |
| `865d814cab88b2c4979d8dc6924e55153c3aacab`，14:51:49–14:52:44Z | Rust fmt/all-target clippy/workspace tests/release/architecture CLI、force extension/tree、backend Ruff/mypy、171 focused PASS，整体 exit0，起止 HEAD/clean 一致 | `logs/s2b-d-step1-865d814cab.log` / `8a95f84013322b2e683da4daaf2b0b513e825eb1694ceaa444c729931a3dfba7` |
| `ff399ac0057e9aa28266b16fae12494101e67aca`，15:08:23–15:08:59Z | 同样完整 Rust 链、force extension/tree、backend Ruff/mypy、171 focused PASS，整体 exit0，起止 HEAD/clean 一致；包括新增 parser 局部 M 的 N1/N2 与中 M 坏宽 tuple | `logs/s2b-d-parser-ff399ac005.log` / `39adaa77014cb2e6dbefb7efaf88735f3913217882c9bc4cb4e9262f70b0d72d` |
| `c03c145f1bcfa4eb390cf3187a2be7465f6d1d05`，15:27:50–15:27:59Z | backend Ruff/mypy/tree、206 collected 中 205 PASS、旧 parser 六模块 reachability 1 FAIL，**整次 exit1，未记整步通过** | `logs/s2b-d-context-focused-c03c145f1b.log` / `18c92d35a1c8450f4768cb2f9e07083d6131df46b27229ea3f5dd7fe6f7fbc66` |
| `2d385ffcc79156c41fd6283f5236a5226fab41cb`，15:37:02–15:37:11Z | 生命周期/显式 caller control 修正、精确临时 baseline 后 backend Ruff/mypy/tree、208 focused PASS，整体 exit0，起止 HEAD/clean 一致 | `logs/s2b-d-context-focused-2d385ffcc7.log` / `cf7ebb67d97afe7e0a3da785734f43df259fe135169eb6ccf3c0633128e0bf64` |
| `ff1c98d1c694db11230d74bc3b7ac2caa285b2cb`，15:52:46–15:53:07Z | 完整 Rust 链/force extension/tree 实际通过；随后 backend Ruff 缺 Callable import，**整次 exit1，不是整次 PASS 来源** | `logs/s2b-d-ipc-control-ff1c98d1c6.log` / `fe5360db1ee94c6069648a06441362e71454c4dc47ad1a61d1286bf66c8e7212` |
| `23bd4b596284760db9f762587fd62ef738166249`，15:56:24–15:56:33Z | IPC/控制异常及有界读取修正后 backend Ruff/mypy/tree、220 focused PASS，整体 exit0/clean | `logs/s2b-d-ipc-focused-23bd4b5962.log` / `8eb08e97ffbc16796808d1ed4bdcc069fd5f05d842eb1725cb305cb89d945115` |
| `f45bcd7b6ab868654777271ebc2182f46a950f97`，16:02:15–16:02:24Z | tar metadata guard 与结果持有期修正后 backend Ruff/mypy/tree、256 focused PASS，整体 exit0/clean | `logs/s2b-d-archive-f45bcd7b6a.log` / `e7ba62872530a57deac1700941979bb198b3a1bc0e32063cb7a4ed58c4b8883e` |
| `5e6aa4a06913dd0df0f2bfda32bc1851e2bacea7`，首次上传 Preview/IPC | mypy Bound 类型收窄失败；未记通过，687d 修正 | `logs/s2b-d-preview-5e6aa4a069.log` / `60d8aea7b12d2e315a26dda9dd1b4312c44c42f64255905f5069e5d8ea893c3b` |
| `687d559ddcbd1e3d3d00c2d4e3797ddf030acdab`，16:31:16–16:31:25Z | backend Ruff/mypy/tree、256 PASS/1 FAIL；checkpoint reader 缺 repository 绑定被 strict IPC 拒绝，**整体 exit1** | `logs/s2b-d-preview-687d559ddc.log` / `bdcbf94bc044814c96676a4e6172f6c483979741532e4051b82847350802bb2d` |
| `2347126bb05fa762fba80bd788fd4b0f727abc42`，16:32:52–16:32:59Z | 绑定 payload.repository_id 后 backend Ruff/mypy/tree、121 定向 PASS，整体 exit0/clean | `logs/s2b-d-preview-2347126bb0.log` / `b6b3a1f349e42c5e289cf605454f9a2968f073fc35e245c46361553852cc1651` |
| `d14105ae5051bbd573c3404e4a582faded476fe9`，16:47:19–16:47:25Z | committed port 后 backend Ruff/mypy/tree、25 定向 PASS，整体 exit0/clean；仅该 owner 小步证据，不覆盖仍待修类型/控制/持有期 | `logs/s2b-d-committed-d14105ae50.log` / `a9f1469766686adfea046642872dce5df7d6ba93fe62ed7429cfc86bf710f3d8` |
| `9ea243160331ac04fa051abfe227487ff4b8001a`，16:53:03–16:53:10Z | backend Ruff/mypy/tree、57 PASS/2 FAIL，**整体 exit1**；过宽类型 Finding 的新 fixture 在 B 前置拒绝，另 test-only session close warning 被误转内容失败 | `logs/s2b-d-committed-9ea2431603.log` / `6366f688938c5024f921db0d7b4e010aa01dd2d409660a2e0dc86abf972cf2f8` |
| `9315d0966191c02186da3c600737aa25bfe586cc`，16:55:30–16:55:36Z | backend Ruff/mypy/tree、58 PASS，整体 exit0/clean；Preview18、C HTTP8、原 RepositoryRef protocol20/digest12 | `logs/s2b-d-committed-9315d09661.log` / `3f162081acfb6a0831a41df7acc38ad6ae98a365736f921d54d104ec7176d850` |
| `7a9eba1c11f4e23169ae89136878dc6a3720237c`，结束16:59:33Z | backend Ruff/mypy/tree、148 PASS/1 FAIL，**整体 exit1**；新低M fixture 的 description 不满足特殊设备身份，B 正确过滤为空，故未触发期待拒绝 | `logs/s2b-d-catalog-7a9eba1c11.log` / `85641dae62693c1f78443fcb3ed0ea46fb6e9aff20c1520b01336254190e749d` |
| `5325076e629ab1162cf9240cf508052dd43acd83`，17:00:21–17:00:23Z | 仅修既有特殊设备 fixture 身份后，backend Ruff/mypy/tree、business native owner35 PASS，整体 exit0/clean；不作为后来9b公式的执行结果 | `logs/s2b-d-catalog-5325076e62.log` / `29d3049cce23f9c879bee6bfbdc0d25b36ba6812a42576b3dc69c498404c73c4` |
| `84f1037ab3868a3e4cea2519d8b7ffbd782de114`，17:13:13–17:13:37Z | backend Ruff/mypy/tree、191 PASS/12 History FAIL，**整体 exit1**。其中 business native35 实际执行9b新公式并全过，不回填整组 PASS | `logs/s2b-d-export-84f1037ab3.log` / `f9b89a89e6e42ffeedaecc9699a7bcc92146135a75d46f7fea99dfd956265408` |
| `a3cec2914c19b0ae9803232d4781f71ff3e0b4a6`，17:26:32–17:26:46Z | backend Ruff/mypy/tree、139 PASS/1 FAIL，**整体 exit1**；行数 fault fixture 在构造冻结事实时先触发重复 PK，未作为 C 读取屏障证据 | `logs/s2b-d-export-a3cec2914c.log` / `80c5b38c78fdc5131dcc601e892b3a6536294d8ef336ca29a5df06e5e87cf018` |
| `beca6c334abf8786ab506e3d71b1a78f05d95bd4`，17:27:39–17:27:49Z | 合法冻结 PK1/2、仅 runtime wire 截断后 History27 PASS，整体 exit0/clean，原 rowcount 错误码断言保留 | `logs/s2b-d-export-beca6c334a.log` / `9caad12eed123e9344b4dfa931b0ed52bf0584337f975eaee6db045a401be4d0` |
| `e9585003d96b3d8bbd6e0801f48ab764fdc49dce`，17:28:45–17:28:48Z | backend Ruff/mypy/tree、client/store14 PASS，整体 exit0/clean；128 KiB 中 M 在 footer 展开前拒绝且不构造 ParquetFile | `logs/s2b-d-export-e9585003d9.log` / `a1aec35214e57ab13dcd3a81e1dcd6e97167cfa8544e09f677e2e3ba6f713d0e` |
| `a6dd87ea4a9bcbbdd68a29af358d998b6bfbe0e7`，17:45:55–17:46:02Z | backend Ruff/mypy/tree、114 PASS/18 builder fixture FAIL，**整体 exit1**；C9、prepare7、architecture90 通过，新参考 Arrow fixture 错把不可空 field 写成 nullable=True，被精确 guard 拒绝 | `logs/s2b-d-submit-a6dd87ea4a.log` / `42d3eb2f530cc09e1ba7b82230d38720078489d5ce54576ac8d560a9def3db80` |
| `17ceec610e32c21223fc80753d30f7e6b399d042`，17:47:54–17:47:56Z | 仅修 fixture field nullable 与其 source metadata 一致后，backend Ruff/mypy/tree、builder26 PASS，整体 exit0/clean；产品 guard 未放宽 | `logs/s2b-d-submit-17ceec610e.log` / `101e391669707ee08deb10c2d4409de6d83a0c826af60614455f3a955845a19e` |
| `20cacb157fa7d00a3ab7537fa0a56449268ed707` | mypy 的具体/port 注解与测试 chained-is 类型失败，尚未进入pytest；后续最小修正，不记PASS | `logs/s2b-d-control-20cacb157f.log` / `803a389ef5cf4ba194318b0dfa5c03905a2b1bf1abe530b22eeb16aea7649f9d` |
| `b5d3ffd28e6c25dfe9102f68d3731d5fca7fb6c4`，外置脚本首次 | 静态通过后脚本路径误写 tests/architecture，collected0、exit4，未触及pytest被测对象；按DC68修脚本从头一次重做 | `logs/s2b-d-control-b5d3ffd28e.log` / `32f62edd276fc56a268a3cbf386ef8ea6bd0a9919a4c7cfe3ab30e345244c7ca` |
| 同 `b5d3`，修脚本的实际421项 | 418 PASS/3 FAIL、**整体exit1**；两项新fixture把当前checkpoint与prior ref重复，真实Runtime fixture未模拟signal唤醒，均保留原记录 | `logs/s2b-d-control-fixed-b5d3ffd28e.log` / `c2690433a03d7af7d424037bfc9855652a00d42e1c860d500b06775c2e0a5270` |
| `7f61ceedf4a93842422338b58c876124a8af093c`，18:13:27–18:13:35Z | backend Ruff/mypy/tree、422 PASS、整体exit0/clean，含 lease/state/R5 与真实 fileDB Runtime drain→重领 | `logs/s2b-d-control-fixed-7f61ceedf4.log` / `bfad4f180647e3f11e5da71e1dee50443828381bde797da3b81a470c9a3cc7cb` |
| `a8f4d1ba02f7c256791d901d9c4ee473ea88aec8`，结束18:16:10Z | 180 PASS/2 FAIL、**整体exit1**；真实T1缺IPC在READY refs先抛未映射异常，另pair新import越public surface；均修真实owner，不放宽基线 | `logs/s2b-d-pair-control-a8f4d1ba02.log` / `4659607f8e37b084e7a63e6e8fbd60874f402ef4cfe45d82f98b7c3cce0d9f87` |
| `985e5e0ae83358be8118da901ed18bea7ebb75a9`，18:17:21–18:17:27Z | backend Ruff/mypy/tree、182 PASS、整体exit0/clean；pair/records控制穿透、Submit真实T1缺失与冻结重放owner通过 | `logs/s2b-d-pair-control-985e5e0ae8.log` / `b74d5ebb48aee81de9070be4d1d2e8fe48a7db66797b7b19a154a02aac0ad54b` |
| `7f472aadaf352f55e9216cb7a712475c9289aaca`，18:26:30–18:26:32Z | Ruff/tree通过后mypy redundant-cast与测试public属性导入失败，pytest未执行、整体exit1；预算公式未因此改动 | `logs/s2b-d-python-memory-7f472aadaf.log` / `14088b175910cba165f73238b009afe31a091dece3e80a2717e0c2fc33bbd2aa` |
| `b05c390a2a6547a1b2b21600116048508b32a484`，18:27:09–18:27:39Z | backend Ruff/mypy/tree、243 PASS、整体exit0/clean；现pair准入、prepare低M清占用与原Preview/History/records/package/checkpoint owners。尚不覆盖随后发现的ordered identity-hit及bundle漏项 | `logs/s2b-d-python-memory-b05c390a2a.log` / `07cd2ed8a1cccaced2ca3643d707e61c57b3631e9eced3433370644aab357ae4` |
| `bbcdd8c82cb6bb6c35ee411fb4c5ce1483fdf79b`，18:32:57–18:33:16Z | backend Ruff/mypy/tree、155 PASS、整体exit0/clean；ordered identity-hit/current读行准入、bundle完整closure读取前拒绝、Preview/History/bundle与architecture原owners | `logs/s2b-d-bundle-memory-bbcdd8c82c.log` / `b151e1fca9504c8677ca1bad8e98440a9a0badc13e8219f91f6044f14650a439` |
| `93678f8439ec1393d496182f16ae5049b220242f`，18:40:53–18:41:11Z | 五Python包Ruff/mypy、backend extension tree、C access10 PASS，整体exit0/clean；新增真实ArrowMemoryError多继承异常透传参数，不重跑已过Rust链或t4 | `logs/s2b-d-final-static-93678f8439.log` / `0498abcb38bb5b66977fb7fe80e40aef5bf9628158c4a9fc4a0947106483b3db` |

865 的 host extension expected/installed Rust tree 均为 `0612992f8b22a7bafcf9747fa65bd1c5f2348874`，ff399 均为 `3553f3a0312076b8a166400e90d3478e14feb376`。使用离线 uv/Cargo、外置 D 专属 target/TMPDIR/log；未修改 C target 或证据。这些小步不是权威 runner 来源、不是正式 carried，也不是容器或实际 worker 容量结论。

首轮明确小问题已直接闭环：原 composition/bootstrap layer bypass 不能表达新 initializer 的精确边，865 在 `ext:compute` 判断前约束 source/target/entrypoint，并在现 architecture 参数表覆盖允许/拒绝例；未增加 import/cycle baseline。新增 pool subprocess owner 已加 integration 和有限 timeout。Rust policy v5 的精确 parser/initializer owner 由 root 在 `d215ae2e2f` 正式收口，不将其作为普通 Finding 放宽。

## parser 局部预算补项

root 已在 `c7e024574f` 将新规则归入 Snapshot Table Access 与 D kickoff，`89dbdfb495` 订正为既有 `RESOURCE_LIMIT_EXCEEDED` 错误码：parser 原有 source/row/field quota 缺少完整 live bytes，D 补当前 operation 剩余 `max_live_bytes`；分配前源序预预约，新增整体额度不足统一 document offset 0，原配额定位与成功语义保持，不重做旧 L4 全量差分。

公式审核已指出并要求覆盖真实阶段：Phase A catalog/DDL/diagnostics、jobs ordinals/splits/specs、plans/labels；全部 chunk builders；merge capacity 重叠与 Arrow validity/offset 转换；adapter metadata。坏 tuple 的 Fault/ParserDiagnostic 克隆与字符串在最终截断前同时存活，另有超出 schema 宽度的临时 `Vec<Lit>`，不能仅以合法列数或 row_offsets 代替；版本注释 INSERT 的统计亦须覆盖。02711→ff399 已补这些分项：Scanner 统计 tuple 宽度/span，版本注释使用长度上界；row slots/capacity、诊断克隆、builder headers、当前 tuple scratch 按 active≤N 计。实现无 atomic 竞抢，checked 源序拒绝；消息模板 256 B、SET 64 members、JSON depth 100 有当前 owner 依据。ff399的有界资源拒绝、128KiB坏宽tuple、N1/N2稳定定位已核；后续生产available/retained Arrow接续与BBC实际8GiB materialize校准已在后文闭合，不以parser小步单独预判总容量。

root `64ae545964` 将公共 SnapshotTableArtifact wrapper 目标归入 Canonical Storage 3.8/Table Access：canonical arrow-ipc/none/显式 repository scope，raw parquet/zstd/repository_id=null；客户端仍有界导出真正 Parquet。本审核按严格新载荷、冻结绑定、外层列序与真实用途核实现，不要求旧格式兼容或平行 union。Preview/History canonical checkpoint 与 Submit frozen closure 的特定 owner 仍须要求 canonical 格式/期望 scope，不能因 generic reader 支持 raw 用途而继续接受旧 canonical Parquet。

## 生产 Arrow 接线与生命周期

fa2efdb0f2→c03将真实claimed handler/recovery绑定同一operation context，传部署M/N与明确捕获的ExecutionControlProbe；native monitor不现取ContextVar。生产上传调用Table Access native parser，真实Arrow source的SQL materialization走B；adapter的N默认None，只消费已初始化固定池，inspect也检查初始化。当时尚存的旧projection/规范Parquet路径在后续实际caller组完成切换，不以这一早期小步声称完整D。

该 API 以实际 Arrow 根 backing 和 mapping 范围去重。本审核指出 SQL 函数局部 reserve 退出时 upstream bytes 仍存活、reader.close 时 ParsedTable/closed reader 仍持有 descriptor；2d385 已由读取调用层在 locate 前预约并覆盖整个 side，按返回 bytes 对象绑定避免 parser 双计，descriptor metadata 保守持有到 operation 结束，不增 allocator 跟踪。active context 原无条件覆盖 caller probe/finite deadline 的问题也已修：统一 OR 合并真实停止条件、保留最早 finite（两者无值仍 None），合并 context 继续给输出 reader，并在 stream/batches EOF 核对。208 focused 中新增 owner 回归已核；上述具体问题关闭，不等于完整 D 总 M 通过。

现 high_water_bytes 计 retained backing 与显式 reserve/envelope，不计尚未进入该计数器的 native 临时阶段；准确名称为 charged/reserved highwater。它与 stage admission cap、实际 RSS 分列，不称 retained-only 或完整实测峰值，不强制新 profiler。M 正确性仍须由同一时刻已有预约加可解释 local cap 的上界及增长前拒绝独立证明。

c03 的 reachability 失败按 root 正式 `35291ba046` 处理：六项旧 parser `table_access.{sql,_sql_reader,_sql_scan,_sql_statements,_sql_types,_sql_values}` 只在 D 期间临时差分参考。固定 c03 生产搜索仅有 sql.py 定义与 facade 导出，没有业务 caller；tests/support 与旧差分工具仍使用。E 必须移交独立预期后删除实现、差分入口及六 entries，不能保留到 S2b exit，不加 IMPORT/cycle 或假 import。C 的五个新能力临时条目仍须在 D 真正接线后删；已真实接通的 snapshot_materialization.native 一项已移除，其余未假接。

与 D 新读取预约有关的两项基础边界已关闭。LocalArtifactStore 原整份 read 后才核 ref.size，损坏 oversize 文件可先超预约；现 opened fd 核 size 后 read(ref.size+1)，现 fault owner 证明 oversize 在 body read 前拒绝，错误/root 语义保留。tarfile 的 PAX/GNU 扩展头由 archive.next 在业务 expanded/entry quota 前读取；独立只读核 06 Python 3.14.6 `_proc_pax`/`_proc_gnulong` 的 read(self.size) 及 global PAX 每 member 的 dict.copy 后，由 root `62eb84d7e6` 归 owning Contract。

f45 的 task-local TarInfo 在 tarfile 初始化首 header 前装入；PAX/GNU/sparse 仍委托 pinned stdlib 原 parser，metadata read proxy 在增长前累计保守工作量，递归同 proxy 不双计、finally 恢复；global 字典浅复制另按容量预约，archive 生命周期内不提前释放。内部 header allowance（256 MiB ceiling、按 operation 剩余份额限）与普通 entry/path/expanded 预约分列相加，SourcePackage 返回 entries/path metadata 接续至 operation 结束。正常 PAX/global/GNU 与低额度拒绝同一小表通过，无部分产物；未新增格式支持或禁所有扩展头，不再扩全 tar 生态矩阵。

23bd 的 C store/mmap 控制小步也已关闭：mapping 打开前预约，实际地址范围的共享 views 计一次、独立 reopen 分计；同 mapping 上 SHA 有 checkpoint 回调，inspect 接 finite deadline。put/EOF/返回前核 control；Python 控制异常经 Arrow C Stream 被包装成 ValueError 时，native owner 在异常路径先复核真实 context，再保留控制类别，无 stop 才保留原错误。现 EOF owner 收紧为 InterruptedError 且 before_write/文件均未发生。Reader/schema/borrower 先于 mapping 关闭，operation ExitStack 兜底；Rust tree `137d499975f3c104ae9c3268b9e12befb2817ba1` 与上述已实际通过完整链一致。该结论仍不代替完整 canonical caller 接入。

## 上传 Preview 的 IPC 调用链

b10→2347126已将uploaded Preview的真实SQL/business Arrow接至B projection，再由C唯一Rust IPC writer发布明确repository的canonical manifest；lookup/register保持derived短UoW，正式checkpoint仍走LeaseSession。当时C store与storage_projection.native两条temporary已删除；repository_arrow/application C access随后由真实committed caller接通，最终C五项均删除。

本审核指出的两项实际重叠/额外 IO 已修：composite 例外先在临时 envelope 下有界转换，删除 Python 列表/array wrappers 后把 backing 转入 retained 预约，再进入 native cap 计算，跨调用保持实际 backing；fresh 写入返回独立 reopen 的已验证 Arrow reader，不立即整份 SHA/IPC 读回，真实 cache hit 仍核 C 健康。scope/缺字段与独立 reader 的现 owner 小例保留。

2347126修复恢复checkpoint缺期望repository的实际失败。当时baseline尚有旧raw路径，最终committed/Submit组已在frozen/canonical owner强制`canonical_required`；cache-hit控制异常亦在后续owner复审闭环。不以234早期repo小步代替最终严格格式证据。

## committed port 的实际接线

root `af1706a93718eaba925991a7e3616b1ba59000b4` 正式归属小型 `committed_tables` port：Snapshot Materialization 定义，application/C access 实现，composition 注入 Preview/History/publication 的实际选表/导出路径；INITIAL/identity-only 不读行，缺 port/identity 不回退 Python rows。7edc→d141 已接 Preview baseline/History，checkpoint 同时要求 IPC 与 payload.repository_id，已真实可达的 application C access/repository_arrow 两项临时 baseline 删除，C 原五项现均有实际消费者。

d141 的显式 cache-control 异常穿透已核。HTTP spool/活跃 mapping 和 eager wire 转换在实际增长前预约，进入 native 时再次 min(operation remaining, local cap)，不让转换与 Rust 各用原剩余额度。test-only reference port 沿 root 授权保留至 E 的独立预期移交；生产缺 identity/port 双参数 owner 已通过，没有生产特权或 fallback。多 session 的 selected/exact pin 断言取代旧单 session 假设合理。

本组的三项明确修正已在9315收口：整个RepositoryRef request的merged control scope覆盖`_with_artifacts`，cache-miss output arrays在预约释放前销掉真实引用；transferred reader的cleanup不再恢复yield后checkpoint，stop后close的实际mapping释放owner通过，且memory.close有finally保障。公开open_committed与reader EOF仍核停止条件。58项原owner支持该小步；publication READERS_REQUIRED、Submit/replay/client Parquet及DC88后续独立组亦已闭合，见下文。

本审核撤回一项过宽的类型 Finding：起初因 Repository Service wire/A 支持 BOOLEAN/DATE/TIME/TIMESTAMP/DECIMAL/BINARY/BIT，要求 C bridge 补全；9ea 的新 HTTP 全类型用例在进入 wire 前即被 B 的既有 `UNSUPPORTED_TABLE` 拒绝。复核旧 `project.py::_resolve_declared_scalar_type`、Rust `supported_projection_column` 及 Canonical Storage §5.2 后确认，这些类型没有当前 canonical projection consumer，A 能表示不等于 B 允许。root 裁决的 9315 已删除额外转换/用例，保留真实控制/持有期修正；不改 B 白名单、不新增 A 重复组件测试，不重写旧提交。这是 Finding 范围纠正，不把失败用例改记为通过。

root `b046865757e76a20d873408dbad42e547b8c6818` 明确实际容量验收可先用既有 t4 FULL 双上传侧/INITIAL fixture，经真实注册 handler、Runtime/LeaseSession 到 materialize checkpoint/后继 PENDING。该阶段的 RSS/charged reservations/stage caps 仍不等于整个 worker capacity。后续 comparison 双侧 rows/cell frames、keyed/keyless/ordered 索引及 records，records Arrow/Parquet spool 与 Submit replay/USTAR/zstd 的真实重叠仍需在现 caller 边界并入 M；原局部 quota 可做上界，不能藏入 4 GiB runtime reserve。普通表错误降级必须显式穿透 control/resource 拒绝，避免 reader 停止被转成 TABLE_DEGRADED。本审核已定位并下发，按现 owner 最小包络与必要阶段证据核，不提前迁移 S3。

## SQL catalog 与无 XML 的 composite 预算

7a9 已将生产 Arrow SQL 物化结果接入 B catalog filter，只把过滤后的 facts 转回 Python。所有 filtered Arrow backing 先预约，逐 batch 在 facts 增长前预约，返回 catalog metadata 持有至 operation 结束，不依赖 XML 的存在。35 项 owner 包含低 M 在非空特殊设备事实转换前拒绝及 temporary 释放；首轮错误身份 fixture 的失败与修正均保留。

本审核另指出无 XML 时 `_bind` 仍生成每 point 的 payload JSON/CompositeSignalPointRow，`_derived_table` 同时保 encoded_rows/hash，不能因 XML envelope 缺失而漏计。9b 给出 SQL-derived 生命周期上界：payload 64 倍按 facts/SET/binary≤8、escaped JSON bytes/Unicode≤30、encoded frame/hash scratch≤16 分项覆盖；重复字段名与 row/cell/container 项独立，Arrow backing 与后续列式转换另有预约，保留至 operation 结束。84f 的35项 business native owner 实际覆盖当前公式且全过，此具体问题按 SQLfacts 范围关闭；不以532结果回填、不另跑全量XML或旧容量，84f 整体 History 失败仍保留。

## 客户端 Parquet、History 与 schema 身份

84f→e958 的客户端 surface/full/replacement bundle 调用唯一列式出口，把 canonical Arrow 真正转换为原 Parquet profile；保留 DDL 列序、logical/source schema、SET empty/null/list、float bits 文本及 batch/ordered metadata。known repository 从 payload 贯穿，cache 沿 repository/layout/writer key；SHA、schema/count 与明确 layout/repository metadata 共同核健康命中，不重写健康文件。每1024行转换、ordered numeric no 的索引/有界 gather、row-group metadata、spool→bytes/put 重叠均并入当前 M。raw Parquet 真实用途沿原边界，Submit 的 canonical closure/manifest 来源未被 client Parquet 替换。

本审核要求 cache-hit 在 ParquetFile 前单独覆盖 footer/schema/row-group 展开，e958 沿本产品 writer 的标准 footer 长度先预约64倍，再由标准 reader 解析；清 file/raw/schema 后才释放。中 M 同一 owner 实际证明 reader 未构造，不扩任意外来 Parquet、格式 parser 或防篡改协议。14项 client/store 与27项 History 实证支持该组局部 GO。

History fixture 迁移保持原业务断言：NULL gid 改为冻结 canonical pseudo 4,000,000,000，非法 no99 改连续位置交换，原 ROW_MOVED/row_modified=0 与 blank 断言保留；坏 no 的拒绝仍由既有 projection integrity owner 拥有。跨真实 sessions 断言代替单 session 假设，warm operation 共享真实 C index，明确 client Parquet cache 不作 canonical 恢复来源。行数故障先生成合法冻结 PK1/2 facts，再只让 runtime wire 截断一行，现读取 owner 的 REPOSITORY_ROW_COUNT_MISMATCH 断言通过，没有把前置 B 拒绝当 C 行数证据。

root `56ca09b0d673b2c5ab0a84c1cb959df24f9bd652` 拥有 port 新显式 `CanonicalTableIdentity`：application 沿现 compute_schema_digest，在 cache/source 前核 canonical 列声明/原列序/PK 与 name/count/raw digest；INT→BIGINT 同值不得绕过。DDL key 从绑定的 exact catalog 解析，无新 digest/version 或反向依赖。a3cec 的9个 C owner 已实际覆盖该 schema 拒绝；本审核再指出 guard 自身须先做元数据准入，2dad 已把现 descriptor count/bytes/min remaining 预检与8倍临时预约放到整列 copy/digest 前，a6dd 的 C9 owner 又实际全过，此顺序问题关闭。

Submit 后续仍有实际 Python replay/image consumer：独立源码核 `_keyed_rows_from_frozen_artifact` 只构造 typed replay image 并核列/行数，`row_digest_from_image` 是 MutationPlanning ADAPTIVE_PATCH 的 JSON row-image 摘要域，不能当作被替代的 table business hash 删除。保留其现 owner/语义，纳入 Submit 当前 M；不为已冻结 C 内容增加重复 B 全表验证。

a6dd→17ce 的 Submit 接口小步已核：T1 `_open_projection_inputs` 只按 known repository/strict canonical IPC 读取冻结 ref，不重选源；新 reader 转交前关闭原 reader/batch borrower。两个实际 bootstrap composition 注入同一 C parent READERS_REQUIRED port，以 expected exact commit/manifest identity 恢复需要的 parent 表。PREPARED 原 checkpoint/package 重放 owner 与禁止重新发布断言保留，规则切换仍用 T1 冻结 manifest；26项 builder 通过。

985e 已接 pair plan/compare/records/risk/surface 前后实际 context checkpoint，records callback沿本次probe；standard与records普通降级/error包装显式穿透 InterruptedError/TimeoutError/MemoryError。parent row转换同样穿透，Submit publish用真实probe/可选deadline并在返回后复核。真实T1缺IPC替换原mock publication failure后，先在READY refs暴露未映射的 CheckpointPublicationError；现build-input owning边界仅把该冻结完整性错误映射现Submit publication失败，verify_refs自身只包装ManifestVerificationError，不吞lease/CAS/stop/resource且不尝试source恢复。182项实证中原FAIL/ABORT/占用释放与PREPARED重放断言均保留；这些控制/冻结缺口关闭。

固定17ce的实际consumer搜索另核：旧 parse_sql/project_canonical_table_set/materialize_projected_snapshot/_read_and_materialize_table/build_import_projection_snapshots 无应用/基础设施真实调用。compose仅留旧reader型catalog reference给E清理，生产非空Arrow表走B，空集无行算法；不以模块可达替代真实调用链证据。

## Python 调用层总预约

b05 在实际comparison plan后、Python rows读取前按未压缩Arrow logical bytes与row/cell/name对象包络预约，保持FULL多个pair返回结果到operation结束；不以压缩Parquet长度推展开。Submit changed/parent tables在typed image/index/mutation前独立预约，render/package临时2528MiB包络覆盖现16MiB manifest与200MiB replay上限下的Unicode、join/bytes、USTAR/zstd及验证重叠，函数返回不携带包bytes后释放；readback另按实际bytes与128KiB流式上传scratch保留，既有HTTP client以64KiB分块上传。READY refs丢弃验证短预约，checkpoint/manifest JSON对象及返回bytes按32倍包络保守持有至end；不把前一checkpoint或已释放磁盘历史累计为RAM。

资源拒绝先复核本次真实context，再沿现LeaseSession应用失败事务：Preview/History释放保护，prepare转原ABORT并释放workspace/repository占用，现243项含真实2GiB准入拒绝清理。此为可报告MemoryError，不声称native abort/OOM kill可恢复。独立复审发现并关闭两处具体漏项：ordered健康identity-hit仍读current rows构造ordered/occupancy digest，现只预约实际current侧；bundle把closure全部raw bytes同时留planned/generated并整份验证，现application包装按binary4倍/JSON64倍及binding metadata在读取前预约、保留到end，覆盖健康/BROWSE/REPLACEMENT表。capability未反向依赖TableAccess，现checkpoint组合freshlease与actualkernel control，返回前复核，broad异常保留stop/deadline/resource。bbcdd的155项实际证明ordered低M拒绝及bundle在locate前拒绝；结合b05，预算/低M清理小步GO，不代替实际worker局部校准。

另独立读取06 pinned PyArrow error.pxi确认ArrowMemoryError同时继承MemoryError/ArrowException；C access健康cache catch若只透传Interrupted/Timeout会将其误判恢复miss。93678已在现except先透传MemoryError，原cache-control owner补该具体异常并10项通过；不是native OOM-kill恢复机制。

## 正常 drain 的语义收口

实际接线发现未 checkpoint 的纯计算若以 retryable failure 表达 drain，会消耗原三个恢复会话；现有普通 safe-handoff 则要求本 session 最新 checkpoint。独立核现 LeaseSession/R5 后将该取舍交 root/Owner，未让实施者冒用外部 healthy-wait 或直接修改语义。Owner 已选 A，root 在 `0ff0af96f3` 登记 DC88/lifecycle/recovery/D 稿。

7f61 已实现并通过独立复审：真实 registry 仅为 PURE_RECOMPUTE 配置application cooperative callback，R5 generic之前保留控制类别，R3无native/application反向依赖。LeaseSession在原mutation lock/fresh事务中按有效lease/CAS及real drain释放到RETRY_WAIT；保留checkpoint（可空）、prior outputs、attempt与业务保护，独立drain/operator marker令下claim不增不重置并恢复授权session。cancel经原应用builder，失租禁写，EXTERNAL不启guard/callback；无schema/status/空checkpoint或新状态机。

本审核指出并修正了普通 InterruptedError 在SQLfacts路径被漏判、composite返回FAILED前缺实际control复核、新资源诊断大小写违反R5格式，以及fresh reload等待期间Runtime可置lease_lost的二次屏障。7f61 的合法内部资源码、调用边界 checkpoint与reload后_ensure_open已核；fixture分离current/prior refs、真实notify_stop_signal不改产品语义。422项现owner实证含取消/失租/租约/claim与operator及真实fileDB Runtime drain→重领（None deadline），DC88小步GO，不冒整D/最终容器通过。

## 实际 worker materialize 局部校准

固定BBC在06的18:39:04–18:39:46Z，经真实preview_composition_bundle、build_worker_runtime、Kernel registry与LeaseSession执行materialize_inputs；LocalArtifactStore读既有t4两包，只有INITIAL空catalog使用既有fixture。外置wrapper只观察真实context/进程数据并在原handler结束后stop，不替换算法或提前控制；实际heartbeat连续成功，materialize SUCCEEDED并有checkpoint、assemble PENDING、operation RUNNING，无executor_failed/失租。该范围局部校准通过，不是全Preview/Submit旅程、正式性能或全worker实测峰值。

两包为5,597,503 B / SHA `95408cc3cfd5bee4f7e53ab1b556e58c3335535b16e8791059029e59d5da1675` 与5,596,595 B / SHA `5a7cd54d9b996be55c34b7bb766eb01ad5c1b7c4fa9bd1e72f5c4741baee3611`。M=8,589,934,592 B、N=1、deadline=None；两个side均实际经过staging/parser/XML/B/A到checkpoint。记录的stage已有预约加本次local cap均不超过M。

| 本次真实进程/预约口径 | bytes |
| --- | ---: |
| VmHWM / ru_maxrss | 675,241,984 |
| handler返回时VmRSS；runtime退出时VmRSS | 604,913,664 / 526,581,760 |
| charged/reserved highwater | 3,976,940,733 |
| handler返回时仍预约 | 370,623,992 |

不把这些值相加，不把native阶段cap当实际分配，单独pool初始化与VmHWM≤12GiB也不作为生产startup或容器硬limit证明。93678仅修改本次INITIAL路径不调用的cache异常分类、对应测试和builder-only Cargo jobs ARG；局部校准不重跑，最终容器在93678实际构建。

脚本`/home/dev/gdds-test-tmp/s2b-d-worker-capacity.py` SHA `8003ab50bcac06b3b6edc4da6c27722f7c11dd4ef3c34909825218b69f8f8783`。首driver被uv-consume拒绝工程外script、未触对象，`logs/s2b-d-worker-capacity-bbcdd8c82c.log` SHA `0d731eb77faf0f925c8a8316c77475c9e3535217efece99d04526c1bc07f2292`、exit2保留；按DC68一次修正driver为lock-check/treechecker后用同锁定venv执行已审外置script，driver SHA `14e0dc9aac95b5fb5bec54e9687f0a5da640361b8f7aaec96b85ce99549ac845`。实际日志`logs/s2b-d-worker-capacity-fixed-bbcdd8c82c.log` SHA `103c084d8f2eb68d820f101f6eeaa3375073f98939c192a426ed61d6a56beb5a`、exit0，报告`s2b-d-capacity/worker-t4-bbcdd8c82c/report.json` SHA `0fa7b17b6710b803fc27838ed8fbea864b6937a0817687046de164fd1044d626`已独立读取。此为外置诊断校准，不伪装权威runner或carried闭包。

## 当前容器判断

Current product candidate: `93678f8439ec1393d496182f16ae5049b220242f`。Container rebuild required: **yes**，命中 settings/env/startup/Compose、production composition、shutdown/control、实际filesystem/read boundary及本候选Dockerfile builder-only Cargo jobs=4。C最后验证image revision为`0048040af5`，仅作C回归来源。D脚本SHA `1e56e8aace2636b994048d620545a762e5c02f597411181b32c0db879144f355`与probe SHA `d65e7f4e540a8461b885be6cbb888e0c1bb6f792b21bff2a1580122df39a1fdd`已核本地/06一致，前置逐项核当前五依赖input与d054、base config/全DiffIDs、固定clean候选与ownedproject。

06在18:43:47–18:45:59Z实际离线构建backend/worker并执行HTTP readiness/正常停止owner，HTTP **1 PASS**且运行镜像与本次构建ID一致，backend本机ID `sha256:b1cfc1b955b6c44d4e3a92321f23dbd0e7f2edb4acd8679e9bb1d64fd0060f02`。依赖基底config `sha256:b5b5422411de38e5ba08243343edb32c39cb01dc7cfcb1564bcb4b4d55e4b92a`与全部19 DiffIDs实比一致。但随后worker oneoff在第三次poll已退出，**整次exit1**，`logs/s2b-d-container-93678f8439.log` SHA `daa9d38d0d0e96f5f06b86bf776992fa1bbfcc22066e4325754e2076ace55227`保留，不作整体PASS。

driver的空`mappings=[]`与现sqlite_mapping第72行非空要求冲突，足以解释startup早退；前置审核漏核该fixture约束。原driver在取worker日志前已rm/down，原stderr缺失，不能称已观察settings_invalid诊断。root授权同936同images仅以现HTTP gate合法mapping复验worker startup/settings/cgroup/stop，所有退出路径先保logs/inspect再cleanup；原HTTP局部PASS保留、不回填原整体FAIL。这不是DC68“未触对象”的重试。

worker-only首driver另遇不支持的`compose run --no-build`，实际CLI在create/start前拒绝，`logs/s2b-d-worker-container-diagnostic-93678f8439.log` SHA `cb0877b2870d19eb0ec6e7d149de23380feea1f337153abbbb604da1c0038cd4`、exit1保留。独立只读核节点`compose run --help`后，按DC68一次删除该flag，保`--pull never`/默认不build及前后原worker本机ID断言，合法fixture不变；fixed driver SHA `c3ba7fa8fea5f30580c68f57b8a29b9d7d989af598b3cc0350686cbef2d6d8e5`。

该fixed在06的18:51:28–18:51:41Z实际exit0/clean，`logs/s2b-d-worker-container-diagnostic-fixed-93678f8439.log` SHA `f8744950738a3e75c93f59aea644d11452cfb4678ebc6f53c8bbd32178e6e1cb`。原worker镜像本机ID `sha256:cfa0d7cd053c5aaac6d0779ef743a5e8afa973450f97a69f1ba80bc6ca31a073`前后不变，实际PID1为生产operation_worker，日志ready→drain_started→worker_exited，stopped inspect ExitCode0/OOMKilled=false。HostConfig.Memory与exec可见memory.max均12,884,901,888 B，实读settings为12/4/8 GiB与N1；`worker-diagnostic-fixed/worker-config-memory.json` SHA `edcbda45d1cb34c95a37648d186f5957a6ddd4007a618d1d3bb16f375a63b036`。这些结果与原HTTP局部PASS共同关闭当前D必要容器边界，不声称原整次容器脚本通过。

最终identity位于`/home/dev/gdds-test-tmp/artifacts/s2b-d-93678f8439/worker-diagnostic-fixed/`：`candidate-image-identities.json` SHA `7bd6657c38eb6ebfbe8ce0645cd2bc6679421cff952ec3f32bcb17686b73683f`，`candidate-images.tar` SHA `3f50a790025abbf55f99c9cfe145d1b98bb65bf583456fb26d93b85cdf9f9359`。本审核另只读提取归档config重算摘要/全部DiffIDs，逐项与JSON及当前Docker inspect RootFS相合，不用跨节点inspect ID代config。

| 当前936镜像 | config digest | 全DiffID数 |
| --- | --- | ---: |
| backend | `sha256:577a055c6797a35b2475ddc70cf5d64bc2ac289af0d9956efd46cccafada77e8` | 13 |
| worker | `sha256:05ad1486646ba59079eb928540f52d72a18cc48e47e8fc0d7cb477fdc318983c` | 13 |
| repository-service | `sha256:0ef5b6c494ee677712ad78dc9a2083cbeb3ac7947fb3ada7c855f5eb0da18187` | 28 |

RS实际source-tree label为`sha256:13cb42af44a23c4b847d3888665eaa8983e79f7d41801cdd3a2d34517b9e00e2`，build-input revision `c52e9fad62e14b016ed814d0799e08e6d97e82b3`，image revision936；backend/worker为该固定clean候选本次实际离线build，未虚构其空`__build_input__`为host treechecker证明。最终04权威runner/container、正式carried与t1–t4正确性留E/S2b最终候选，不在D重复全量门禁。

最终复核时共享main HEAD为abfe7，仅handoff文档变更，936..abfe7的vnext树无diff；本报告提交也仅修改docs。本轮需要的936重建与必要边界已实际完成，文档提交不触发再次构建；本报告不虚构这些focused组为权威runner来源或正式镜像carried。

## 最终证据、E移交与释放

固定handoff abfe7已独立核，原无重复table business hash的职责说明已纠正，MutationPlanning row-image保留。06 `artifacts/s2b-d-evidence-index-final.json`为49个distinct日志，SHA `a0b742a16886029da6746d819300f813e65e49a40caa59ff8418a456f3caa44f`；本审核逐项重算49个实际日志SHA均相合，原45份索引未被覆盖，真实失败/CLI未触对象/后续PASS分别保留。没有D产品阻塞遗留。

materialize局部实际RSS与其他pair/Submit预算及低M清理证据分别记录，不称全worker实测峰值；完整旅程留E，不作为D新增前置。C五项新能力temporary已随真实consumer删除；六项旧parser及测试`_ReferenceCommittedTables`/reference helpers按正式D/E范围保留，E移交独立预期后删除实现/临时条目。raw/client Parquet是实际协议consumer，不随旧算法误删。

E另迁移real_dump_journey._offline_composite_comparison→real_dump_census的旧parse_sql/materialize_sql_snapshot/project_canonical_table_set/materialize_projected_snapshot工具consumer。compare_composite_packages原本就是production projection/comparison的六项counts producer，迁移后只证明跨层一致性；真正golden/fixed vectors保持独立来源，不用新Rust actual反写expected，优先复用已有验证值，不新造整套census/双实现旅程。04权威runner按包闭包决定实际运行/合格来源沿用并覆盖Rust，最终container/carried及既定t1–t4留E；W4仍OPEN、1f9731仍诊断候选，D不接管原基准冻结资源。

06在18:52:58Z closeout exit0，`logs/s2b-d-closeout-93678f8439.log` SHA `7cdafad65fc639fe8c72b6e6add5d529899527398fd1ecc89accafb08080982d`已独立核。保原owner SHA一致后释放本session busy，actual remote936/clean、D容器/卷/network均零；后续只读另查busy目录不存在。五locks/Cargo/selector与C无diff，缓存、WT、镜像、输入和归档保留。D GO后本审核角色结束，不进入E。
